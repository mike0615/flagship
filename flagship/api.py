"""TLS-verified XenAPI XML-RPC transport. No automatic mutation retries."""
import http.client
import socket
import threading
import xmlrpc.client
from urllib.parse import urlsplit
from .journal import JournalError, OBJECT_CLASSES
from .protocol import decode_reference_result, decode_import_result
from .tls import TrustPolicy, MODE_INSECURE


def wire_value(value):
    """XAPI integers use decimal strings, including values larger than int32."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if not -(2**63) <= value < 2**63:
            raise ValueError('XAPI integer is outside signed 64-bit range')
        return str(value)
    if isinstance(value, dict):
        return {str(k): wire_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [wire_value(v) for v in value]
    return value


class APIError(RuntimeError):
    def __init__(self, details):
        self.details = tuple(str(x) for x in details)
        # Error arguments can contain session references or user-supplied secrets.
        super().__init__(self.details[0] if self.details else 'UNKNOWN_API_ERROR')


class TrustedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection whose TLS layer is set up by a TrustPolicy.

    The policy runs the handshake and, for pinned hosts, compares the
    certificate fingerprint before http.client sends the request line, so a
    refused certificate never sees credentials or session references."""

    def __init__(self, host, port, policy, timeout):
        super().__init__(host, port, timeout=timeout)
        self.policy = policy

    def connect(self):
        raw = socket.create_connection((self.host, self.port), self.timeout, self.source_address)
        try:
            raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        try:
            self.sock = self.policy.wrap(raw, self.host, self.port)
        except BaseException:
            raw.close()
            raise


class Transport(xmlrpc.client.SafeTransport):
    def __init__(self, context, timeout=30, policy=None):
        super().__init__(context=context)
        self.timeout = timeout
        self.policy = policy

    def request(self, host, handler, request_body, verbose=False):
        # stdlib Transport.request retries disconnects, unsafe for mutations.
        return self.single_request(host, handler, request_body, verbose)

    def make_connection(self, host):
        if self.policy is None:
            connection = super().make_connection(host)
            connection.timeout = self.timeout
            return connection
        if self._connection and host == self._connection[0]:
            return self._connection[1]
        chost, self._extra_headers, _x509 = self.get_host_info(host)
        parts = urlsplit('//' + chost)
        connection = TrustedHTTPSConnection(parts.hostname, parts.port or 443, self.policy, self.timeout)
        self._connection = host, connection
        return connection


class Client:
    classes = ('pool', 'host', 'VM', 'SR', 'network', 'VDI', 'VBD', 'VIF',
               'PIF', 'PBD', 'task', 'message', 'VM_metrics', 'host_metrics', 'PGPU')

    def __init__(self, endpoint, ca_file=None, journal=None, insecure=False, pins=None, known=None):
        """ca_file: trust only this CA PEM. insecure: skip all certificate checks.
        pins: {host:port: sha256} accepted for this session. known: KnownCerts
        store of "Always trust" pins. Without these, the system CA store and host
        name are verified (the default)."""
        parts = urlsplit(endpoint)
        if (parts.scheme != 'https' or not parts.hostname or parts.username or
                parts.password or parts.query or parts.fragment or parts.path not in ('', '/')):
            raise ValueError('Use https://hostname[:port] without credentials or a path')
        self.endpoint = endpoint.rstrip('/')
        self.journal = journal
        self.journal_failed = False
        self.identities = {}
        self.task_origins = {}
        self.task_states = {}
        self.created_refs = {}
        self.lock = threading.RLock()
        self.session = None
        self.host = parts.hostname
        self.port = parts.port or 443
        self.trust = TrustPolicy(ca_file, insecure=insecure, pins=pins, known=known)
        # Context for the coordinator as decided now (kept for callers/tests).
        self.ssl_context = self.trust.context(self.host, self.port)
        self.proxy = xmlrpc.client.ServerProxy(
            self.endpoint + '/', allow_none=True,
            transport=Transport(self.ssl_context, policy=self.trust))

    @property
    def tls_mode(self):
        """'verified', 'pinned' or 'insecure' for the coordinator connection."""
        return self.trust.mode(self.host, self.port)

    @property
    def insecure(self):
        return self.tls_mode == MODE_INSECURE

    def _rpc(self, name, *args):
        with self.lock:
            result = getattr(self.proxy, name)(*(wire_value(arg) for arg in args))
        if not isinstance(result, dict) or 'Status' not in result:
            raise APIError(['INVALID_RESPONSE'])
        if result['Status'] != 'Success':
            raise APIError(result.get('ErrorDescription', ['UNKNOWN_API_ERROR']))
        return result.get('Value')

    def login(self, username, password):
        self.session = self._rpc('session.login_with_password', username, password,
                                 '1.0', 'flagship')

    def call(self, name, *args):
        if not self.session:
            raise APIError(['SESSION_INVALID'])
        mutation = self.is_mutation(name)
        op_id = None
        if mutation and self.journal:
            if self.journal_failed:
                raise JournalError('Further changes are blocked after a journal failure. Inspect the pool and restart after correcting storage.')
            op_id = self.journal.intent(name, self.affected_objects(name, args))
        try:
            result = self._rpc(name, self.session, *args)
        except Exception as exc:
            if op_id:
                try:
                    self.journal.outcome(op_id, 'server_failure' if isinstance(exc, APIError) else 'unknown', error=exc)
                except JournalError:
                    self.journal_failed = True
                    raise
            raise
        if op_id:
            ref = result if isinstance(result, str) and (name.startswith('Async.') or self.returns_reference(name)) else None
            try:
                self.journal.outcome(op_id, 'returned', result_ref=ref)
            except JournalError:
                self.journal_failed = True
                raise JournalError('Server operation returned but its outcome could not be saved. Returned reference: ' +
                                   (ref or '(none)') + '. Inspect server state before retrying.') from None
            if name.startswith('Async.') and ref:
                self.task_origins[ref] = (op_id, name.removeprefix('Async.'))
            elif ref and self.returns_reference(name):
                self.created_refs[ref] = name.partition('.')[0]
        self.observe(name, args, result)
        return result

    @staticmethod
    def is_mutation(name):
        base = name.removeprefix('Async.')
        kind, _, action = base.partition('.')
        return (kind in OBJECT_CLASSES and bool(action) and
                not action.startswith(('get_', 'assert_', 'check_', 'query_', 'compute_')))

    @staticmethod
    def returns_reference(name):
        kind, _, action = name.removeprefix('Async.').partition('.')
        return kind in OBJECT_CLASSES and action in ('create', 'clone', 'copy', 'snapshot', 'checkpoint')

    def affected_objects(self, name, args):
        refs = []
        base = name.removeprefix('Async.')
        if args and isinstance(args[0], str):
            refs.append(args[0])
        elif args and isinstance(args[0], dict):
            refs.extend(args[0][key] for key in ('VM', 'VDI', 'SR', 'network', 'host') if key in args[0])
        indices = {'VM.copy': (2,), 'VM.pool_migrate': (1,), 'VIF.move': (1,), 'VBD.insert': (1,)}
        refs.extend(args[i] for i in indices.get(base, ()) if len(args) > i)
        return [dict(self.identities[ref], ref=ref) for ref in refs if isinstance(ref, str) and ref in self.identities]

    def observe(self, name, args, result):
        kind, _, action = name.partition('.')
        if kind in OBJECT_CLASSES:
            if action == 'get_all_records' and isinstance(result, dict):
                for ref, record in result.items():
                    if isinstance(record, dict) and isinstance(record.get('uuid'), str):
                        self.identities[ref] = {'class': kind, 'uuid': record['uuid']}
            elif action == 'get_record' and args and isinstance(result, dict) and isinstance(result.get('uuid'), str):
                self.identities[args[0]] = {'class': kind, 'uuid': result['uuid']}
        if (action == 'get_record' and args and isinstance(result, dict) and isinstance(result.get('uuid'), str)
                and args[0] in self.created_refs and self.journal and not self.journal_failed and not self.journal.failed):
            try:
                self.journal.identity(kind, args[0], result['uuid'])
                self.created_refs.pop(args[0], None)
            except JournalError:
                self.journal_failed = True
                raise
        if name == 'task.get_record' and args and self.journal and not self.journal_failed and not self.journal.failed and args[0] in self.task_origins and isinstance(result, dict):
            ref = args[0]
            state = (result.get('uuid'), result.get('status'))
            if self.task_states.get(ref) == state:
                return
            op_id, method = self.task_origins[ref]
            object_ref = None
            if result.get('status') == 'success' and (self.returns_reference(method) or method == 'HTTP.import'):
                try:
                    decoder = decode_import_result if method == 'HTTP.import' else decode_reference_result
                    object_ref = decoder(result.get('result', ''))
                except ValueError:
                    pass
            try:
                self.journal.task(op_id, ref, result, result_ref=object_ref)
                if object_ref:
                    self.created_refs[object_ref] = 'VM' if method == 'HTTP.import' else method.partition('.')[0]
                self.task_states[ref] = state
            except JournalError:
                self.journal_failed = True
                raise

    def logout(self):
        try:
            if self.session:
                self.call('session.logout')
        finally:
            self.session = None
            self.proxy('close')()

    def inventory(self):
        records, errors = {}, {}
        for cls in self.classes:
            try:
                records[cls] = self.call(cls + '.get_all_records')
            except APIError as exc:
                if exc.details and exc.details[0] == 'SESSION_INVALID':
                    raise
                records[cls] = {}
                errors[cls] = str(exc)
        return records, errors

    def vm_action(self, ref, action, *args):
        allowed = {'start', 'clean_shutdown', 'clean_reboot', 'hard_shutdown',
                   'hard_reboot', 'pause', 'unpause', 'suspend', 'resume',
                   'clone', 'snapshot', 'revert', 'pool_migrate', 'provision',
                   'set_name_label', 'set_name_description', 'set_memory_limits',
                   'set_VCPUs_max', 'set_VCPUs_at_startup', 'destroy'}
        if action not in allowed:
            raise ValueError('Unsupported VM action')
        prefix = 'VM.' if action.startswith('set_') else 'Async.VM.'
        return self.call(prefix + action, ref, *args)

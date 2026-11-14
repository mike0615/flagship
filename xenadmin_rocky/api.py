"""TLS-verified XenAPI XML-RPC transport. No automatic mutation retries."""
import ssl
import threading
import xmlrpc.client
from urllib.parse import urlsplit


class APIError(RuntimeError):
    def __init__(self, details):
        self.details = tuple(str(x) for x in details)
        # Error arguments can contain session references or user-supplied secrets.
        super().__init__(self.details[0] if self.details else 'UNKNOWN_API_ERROR')


class Transport(xmlrpc.client.SafeTransport):
    def __init__(self, context, timeout=30):
        super().__init__(context=context)
        self.timeout = timeout

    def request(self, host, handler, request_body, verbose=False):
        # stdlib Transport.request retries disconnects, unsafe for mutations.
        return self.single_request(host, handler, request_body, verbose)

    def make_connection(self, host):
        connection = super().make_connection(host)
        connection.timeout = self.timeout
        return connection


class Client:
    classes = ('pool', 'host', 'VM', 'SR', 'network', 'VDI', 'VBD', 'VIF',
               'PIF', 'task', 'message', 'VM_metrics', 'host_metrics')

    def __init__(self, endpoint, ca_file=None):
        parts = urlsplit(endpoint)
        if (parts.scheme != 'https' or not parts.hostname or parts.username or
                parts.password or parts.query or parts.fragment or parts.path not in ('', '/')):
            raise ValueError('Use https://hostname[:port] without credentials or a path')
        self.endpoint = endpoint.rstrip('/')
        self.lock = threading.RLock()
        self.session = None
        self.proxy = xmlrpc.client.ServerProxy(
            self.endpoint + '/', allow_none=True,
            transport=Transport(ssl.create_default_context(cafile=ca_file)))

    def _rpc(self, name, *args):
        with self.lock:
            result = getattr(self.proxy, name)(*args)
        if not isinstance(result, dict) or 'Status' not in result:
            raise APIError(['INVALID_RESPONSE'])
        if result['Status'] != 'Success':
            raise APIError(result.get('ErrorDescription', ['UNKNOWN_API_ERROR']))
        return result.get('Value')

    def login(self, username, password):
        self.session = self._rpc('session.login_with_password', username, password,
                                 '1.0', 'xenadmin-rocky')

    def call(self, name, *args):
        if not self.session:
            raise APIError(['SESSION_INVALID'])
        return self._rpc(name, self.session, *args)

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

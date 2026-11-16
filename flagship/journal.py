"""Private, fsync'd operation records. Journals never drive automatic RPC replay."""
from collections import deque
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import threading
from urllib.parse import urlsplit
import uuid

MAX_RECORD = 512 * 1024
OBJECT_CLASSES = {'VM', 'VDI', 'VBD', 'VIF', 'SR', 'network', 'host', 'pool', 'task', 'PIF', 'PBD', 'message'}


class JournalError(ValueError):
    pass


def error_code(exc):
    text = getattr(exc, 'reason', None) or (getattr(exc, 'details', None) or [''])[0]
    return text if isinstance(text, str) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}', text) else type(exc).__name__


def safe_report(report):
    if not isinstance(report, dict):
        return {}
    result = {key: report[key] for key in ('stage', 'label', 'status', 'operation', 'copied_template_disks',
                                         'cpus', 'memory_mib', 'transfer_bytes', 'transfer_total', 'partial_file', 'output_file', 'source_file', 'sha256') if key in report}
    result['resources'] = {key: value for key, value in report.get('resources', {}).items()
                           if key in OBJECT_CLASSES | {'CD'} and isinstance(value, str)}
    result['tasks'] = [{key: task[key] for key in ('method', 'task', 'status', 'progress', 'uuid') if key in task}
                       for task in report.get('tasks', []) if isinstance(task, dict)]
    return result


class OperationJournal:
    def __init__(self, directory=None):
        if directory is None:
            from .migrate import journal_dir, migrate_legacy
            migrate_legacy()
            directory = journal_dir()
        self.directory = Path(directory)
        self.path = None
        self.fd = None
        self.failed = False
        self.closed = False
        self.lock = threading.RLock()
        self.flow = None
        self._last_report = None

    def _open(self):
        if self.fd is not None:
            return
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            raise OSError('Journal directory must be a directory owned by the current user')
        directory_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            if os.fstat(directory_fd).st_uid != os.getuid():
                raise OSError('Wrong journal directory owner')
            os.fchmod(directory_fd, 0o700)
            filename = 'operations-' + str(uuid.uuid4()) + '.jsonl'
            self.fd = os.open(filename, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_EXCL |
                              os.O_CLOEXEC | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
            os.fsync(directory_fd)
            self.path = self.directory / filename
        finally:
            os.close(directory_fd)

    def _append(self, event, **fields):
        with self.lock:
            if self.failed or self.closed:
                raise JournalError('Operation journal is unavailable. Inspect server state and correct storage before restarting the client.')
            entry = dict(event=event, time=datetime.now(timezone.utc).isoformat(), flow=self.flow, **fields)
            try:
                payload = (json.dumps(entry, ensure_ascii=True, allow_nan=False) + '\n').encode('utf-8')
                if len(payload) > MAX_RECORD:
                    raise ValueError('Journal record too large')
                self._open()
                remaining = memoryview(payload)
                while remaining:
                    count = os.write(self.fd, remaining)
                    if count <= 0:
                        raise OSError('Short journal write')
                    remaining = remaining[count:]
                os.fsync(self.fd)
            except Exception:
                self.failed = True
                raise JournalError('Cannot persist operation journal. Further changes are blocked; inspect the pool before retrying.') from None
            return entry

    def begin(self, label, endpoint=None):
        with self.lock:
            self.flow = str(uuid.uuid4())
            self._last_report = None
            fields = {'label': label}
            if isinstance(endpoint, str):
                parsed = urlsplit(endpoint)
                if parsed.scheme == 'https' and parsed.hostname and not (parsed.username or parsed.password or parsed.query or parsed.fragment) and parsed.path in ('', '/'):
                    fields['endpoint'] = endpoint
            self._append('workflow_begin', **fields)
            return self.flow

    def finish(self, status, report=None, error=None):
        fields = {'status': status}
        if report is not None:
            fields['report'] = safe_report(report)
        if error:
            fields.update(error_type=type(error).__name__, error_code=error_code(error))
        self._append('workflow_end', **fields)
        self.flow = None

    def workflow(self, report):
        safe = safe_report(report)
        # Progress percentages can change every second; persist structural transitions.
        comparable = dict(safe, tasks=[{k: v for k, v in task.items() if k != 'progress'} for task in safe['tasks']])
        comparable.pop('transfer_bytes', None)
        fingerprint = json.dumps(comparable, sort_keys=True)
        with self.lock:
            if fingerprint != self._last_report:
                self._append('workflow_progress', report=safe)
                self._last_report = fingerprint

    def intent(self, method, objects=()):
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*', method):
            raise JournalError('Invalid method name for the operation journal')
        op_id = str(uuid.uuid4())
        self._append('intent', op_id=op_id, method=method, objects=list(objects))
        return op_id

    def outcome(self, op_id, status, result_ref=None, error=None):
        fields = {'op_id': op_id, 'status': status}
        if isinstance(result_ref, str) and result_ref:
            fields['result_ref'] = result_ref
        if error:
            fields.update(error_type=type(error).__name__, error_code=error_code(error))
        self._append('outcome', **fields)

    def identity(self, kind, ref, object_uuid):
        self._append('object_identity', object_class=kind, ref=ref, uuid=object_uuid)

    def task(self, op_id, ref, record, result_ref=None):
        state = record.get('status')
        fields = {'op_id': op_id, 'task': ref, 'status': state if isinstance(state, str) else 'unknown'}
        if isinstance(record.get('uuid'), str):
            fields['uuid'] = record['uuid']
        if result_ref:
            fields['result_ref'] = result_ref
        errors = record.get('error_info') or []
        if errors and isinstance(errors[0], str) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}', errors[0]):
            fields['error_code'] = errors[0]
        self._append('task_state', **fields)

    def close(self):
        with self.lock:
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None
            self.closed = True

    def history(self, limit=3000):
        records = deque(maxlen=limit)
        warnings = []
        if not self.directory.exists():
            return [], []
        if self.directory.is_symlink() or self.directory.stat().st_uid != os.getuid():
            return [], ['Untrusted journal directory']
        candidates = []
        for path in self.directory.glob('operations-*.jsonl'):
            try:
                candidates.append((path.lstat().st_mtime_ns, path))
            except OSError:
                warnings.append(path.name + ': unavailable')
        if len(candidates) > 100:
            warnings.append('Showing at most the 100 most recent journal files; older files remain on disk')
        count = 0
        for _, path in sorted(candidates)[-100:]:
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd, 'rb') as stream:
                    if os.fstat(stream.fileno()).st_uid != os.getuid():
                        raise OSError('Wrong journal owner')
                    while True:
                        line = stream.readline(MAX_RECORD + 1)
                        if not line:
                            break
                        if len(line) > MAX_RECORD:
                            raise ValueError('Oversized journal record')
                        if not line.endswith(b'\n'):
                            warnings.append(path.name + ': incomplete final record; inspect preceding intents')
                            break
                        entry = json.loads(line)
                        if (not isinstance(entry, dict) or not isinstance(entry.get('time'), str) or
                                not isinstance(entry.get('event'), str)):
                            raise ValueError('Invalid journal record')
                        for key in ('op_id', 'method', 'status'):
                            if key in entry and not isinstance(entry[key], str):
                                raise ValueError('Invalid journal field type')
                        count += 1
                        entry['journal_file'] = path.name
                        records.append(entry)
            except (OSError, ValueError, UnicodeError):
                warnings.append(path.name + ': could not read complete history')
        if count > limit:
            warnings.append('Showing only the last {} events; older records remain on disk'.format(limit))
        return sorted(records, key=lambda r: r.get('time', '')), warnings


def recovery_needed(records):
    """Identify unresolved/uncertain outcomes for review, never for automatic replay."""
    intents = {r['op_id']: r for r in records if r.get('event') == 'intent' and r.get('op_id')}
    outcomes = {r['op_id']: r for r in records if r.get('event') == 'outcome' and r.get('op_id')}
    tasks = {r['op_id']: r for r in records if r.get('event') == 'task_state' and r.get('op_id')}
    review = []
    for op_id, intent in intents.items():
        outcome = outcomes.get(op_id)
        state = None
        if outcome is None:
            state = 'no_recorded_outcome'
        elif outcome.get('status') == 'unknown':
            state = 'unknown_server_outcome'
        elif outcome.get('status') == 'returned' and intent.get('method', '').startswith('Async.'):
            if tasks.get(op_id, {}).get('status') not in ('success', 'failure', 'cancelled'):
                state = 'task_outcome_unconfirmed'
        if state:
            review.append(dict(op_id=op_id, method=intent.get('method'), time=intent.get('time'),
                               state=state, objects=intent.get('objects', []),
                               returned_ref=(outcome or {}).get('result_ref'), task=tasks.get(op_id)))
    for record in records:
        report = record.get('report', {})
        if (record.get('event') == 'workflow_end' and record.get('status') == 'interrupted_or_failed'
                and isinstance(report, dict) and (report.get('resources') or report.get('tasks'))):
            review.append({'flow': record.get('flow'), 'time': record.get('time'),
                           'state': 'interrupted_workflow_inspect_recorded_objects',
                           'report': report, 'error_code': record.get('error_code')})
    return review


def save_json_private(path, data):
    """Save an explicit export without exposing infrastructure metadata via umask."""
    payload = (json.dumps(data, indent=2, ensure_ascii=True, default=str) + '\n').encode('utf-8')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        if os.fstat(fd).st_uid != os.getuid():
            raise OSError('Export destination must be owned by the current user')
        os.fchmod(fd, 0o600)
        os.ftruncate(fd, 0)
        remaining = memoryview(payload)
        while remaining:
            count = os.write(fd, remaining)
            if count <= 0:
                raise OSError('Short export write')
            remaining = remaining[count:]
        os.fsync(fd)
    finally:
        os.close(fd)

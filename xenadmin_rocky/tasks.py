"""Track submitted tasks without retrying their associated mutations."""
from .api import APIError


class TaskTracker:
    terminal = frozenset(('success', 'failure', 'cancelled', 'unavailable'))

    def __init__(self):
        self.tasks = {}

    def add(self, ref, operation, target):
        if not isinstance(ref, str) or not ref or ref == 'OpaqueRef:NULL':
            raise ValueError('Server did not return a valid task reference; refresh before retrying')
        self.tasks[ref] = {'operation': operation, 'target': target, 'status': 'pending',
                           'progress': 0.0, 'error_code': ''}

    @property
    def pending(self):
        return any(task['status'] not in self.terminal for task in self.tasks.values())

    def poll(self, client):
        records = {}
        for ref, task in list(self.tasks.items()):
            if task['status'] in self.terminal:
                continue
            try:
                record = client.call('task.get_record', ref)
            except APIError as exc:
                if str(exc) == 'SESSION_INVALID':
                    raise
                task.update(status='unavailable', error_code=str(exc))
                continue
            status = record.get('status', 'unavailable')
            if status not in ('pending', 'cancelling', 'success', 'failure', 'cancelled'):
                status = 'unavailable'
            try:
                progress = min(1.0, max(0.0, float(record.get('progress', 0))))
            except (ValueError, TypeError):
                progress = 0.0
            errors = record.get('error_info') or []
            task.update(status=status, progress=progress, error_code=str(errors[0]) if errors else '')
            records[ref] = record
        return records

    def summary(self):
        return '\n'.join('{} — {}: {} ({:.0%}){}'.format(
            task['target'], task['operation'], task['status'], task['progress'],
            ' [' + task['error_code'] + ']' if task['error_code'] else '')
            for task in self.tasks.values())


def request_cancellation(client, ref):
    record = client.call('task.get_record', ref)
    if record.get('status') == 'cancelling':
        return {'resources': {'task': ref}, 'status': 'cancelling'}
    if record.get('status') != 'pending':
        raise ValueError('This task has already finished; no cancellation was submitted')
    if 'cancel' not in record.get('allowed_operations', []):
        raise ValueError('The server does not allow cancellation of this task')
    client.call('task.cancel', ref)
    return {'resources': {'task': ref}, 'status': 'cancellation_requested'}

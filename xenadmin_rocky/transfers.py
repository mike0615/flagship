"""Task-confirmed XVA archive transfers with durable intents and private partials."""
import hashlib
import os
from pathlib import Path
import stat
import uuid
from .api import APIError
from .httpstream import request, TransferError
from .journal import JournalError
from .protocol import decode_reference_result
from .xva import XVAEnvelope
from .workflows import Provisioner, WorkflowError, NULL


class XVATransfer(Provisioner):
    def __init__(self, client, transport=request, **options):
        super().__init__(client, **options)
        if not client.journal or client.journal_failed:
            raise JournalError('Archive transfers require an available private operation journal')
        self.transport = transport
        self.partial = self.output = self.source_path = None
        self.transferred = 0
        self.total = None
        self.sha256 = None
        self.op_id = None
        self.deadline = None

    def report(self):
        return {'stage': self.stage, 'label': self.stage, 'resources': dict(self.resources),
                'tasks': [dict(task) for task in self.tasks], 'transfer_bytes': self.transferred,
                'transfer_total': self.total, 'partial_file': str(self.partial) if self.partial else None,
                'output_file': str(self.output) if self.output else None,
                'source_file': str(self.source_path) if self.source_path else None, 'sha256': self.sha256}

    def announce(self):
        report = self.report()
        self.client.journal.workflow(report)
        self.progress(report)

    def checkpoint(self):
        super().checkpoint()
        if self.deadline is not None and self.clock() >= self.deadline:
            raise TimeoutError('Archive transfer timed out; inspect the task before retrying')

    def begin(self, operation, object_ref):
        task = self.call('task.create', 'XVA '+operation, 'Native archive transfer')
        if not isinstance(task, str) or not task or task == NULL:
            raise ValueError('Server did not return a valid transfer task')
        record = self.call('task.get_record', task)
        self.tasks.append({'method': 'HTTP.'+operation, 'task': task,
                           'uuid': record.get('uuid'), 'status': record.get('status', 'pending')})
        objects = self.client.affected_objects('VM.export' if operation == 'export' else 'SR.import', (object_ref,))
        objects.append({'class': 'task', 'ref': task, 'uuid': record.get('uuid')})
        if self.partial:
            objects.append({'class': 'file', 'path': str(self.partial), 'final_path': str(self.output)})
        if self.source_path:
            objects.append({'class': 'file', 'path': str(self.source_path)})
        self.op_id = self.client.journal.intent('HTTP.'+operation, objects)
        self.client.task_origins[task] = (self.op_id, 'HTTP.'+operation)
        self.deadline = self.clock()+self.timeout
        self.announce()  # Persist recovery paths/task before sending the HTTP request.
        return task

    def observe_transfer(self, count):
        self.transferred = count
        self.announce()

    def wait_task(self, task):
        self.stage = 'Confirming archive task outcome'
        self.deadline = self.clock()+self.timeout
        while True:
            self.checkpoint()
            record = self.client.call('task.get_record', task)
            self.tasks[-1].update(status=record.get('status'), progress=record.get('progress', 0))
            self.announce()
            if record.get('status') == 'success': return record
            if record.get('status') in ('failure', 'cancelled'):
                raise APIError(record.get('error_info') or ['TRANSFER_TASK_FAILED'])
            if record.get('status') not in ('pending', 'cancelling'):
                raise ValueError('Unknown transfer task outcome; inspect the server')
            self.stop.wait(self.interval)

    def failed(self, exc):
        if self.op_id:
            try: self.client.journal.outcome(self.op_id, 'unknown', error=exc)
            except JournalError: self.client.journal_failed = True
        reason = str(exc) if isinstance(exc, (APIError, ValueError, TransferError)) else type(exc).__name__
        error = WorkflowError(self.stage, reason, self.resources, self.tasks)
        error.report = dict(self.report(), reason=reason)
        return error

    @staticmethod
    def sync_directory(path):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)

    def export_vm(self, vm, filename):
        response = None
        try:
            record = self.call('VM.get_record', vm)
            if record.get('is_control_domain') or record.get('power_state') != 'Halted' or not record.get('uuid'):
                raise ValueError('Export requires a halted guest, template or snapshot with a known UUID')
            self.resources['VM'] = vm
            self.output = Path(filename).absolute()
            if self.output.exists() or self.output.is_symlink():
                raise ValueError('Choose a new export filename; existing files are never overwritten')
            self.partial = self.output.with_name('.'+self.output.name+'.'+uuid.uuid4().hex+'.partial')
            fd = os.open(self.partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as output:
                task = self.begin('export', vm)
                self.stage = 'Receiving XVA archive'
                self.announce()
                response = self.transport(self.client, 'GET', '/export',
                    {'uuid': record['uuid'], 'task_id': task, 'use_compression': 'false'}, checkpoint=self.checkpoint)
                digest = hashlib.sha256()
                envelope = XVAEnvelope()
                for chunk in response.chunks():
                    self.checkpoint()
                    output.write(chunk)
                    envelope.feed(chunk)
                    digest.update(chunk)
                    self.observe_transfer(self.transferred+len(chunk))
                response.close(); response = None
                if not self.transferred: raise ValueError('Host returned an empty export')
                envelope.finish()  # A task can finish before a close-delimited body is truncated.
                self.wait_task(task)
                output.flush(); os.fsync(output.fileno())
                self.sha256 = digest.hexdigest()
            self.stage = 'Publishing confirmed XVA archive'
            self.announce()
            os.link(self.partial, self.output, follow_symlinks=False)
            self.sync_directory(self.output.parent)
            self.partial.unlink()
            self.sync_directory(self.output.parent)
            self.client.journal.outcome(self.op_id, 'returned')
            self.stage = 'XVA export completed'
            self.announce()
            return self.report()
        except Exception as exc:
            raise self.failed(exc) from None
        finally:
            if response: response.close()

    def import_vm(self, filename, sr, network):
        response = None
        try:
            storage = self.call('SR.get_record', sr)
            if storage.get('content_type') != 'user' or 'vdi_create' not in storage.get('allowed_operations', []):
                raise ValueError('Choose writable user storage for the imported VM')
            self.call('network.get_record', network)
            previous = self.call('VM.get_all_records')
            previous_uuids = {record.get('uuid') for record in previous.values()}
            self.resources['SR'] = sr
            self.source_path = Path(filename).absolute()
            fd = os.open(self.source_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or not before.st_size:
                os.close(fd)
                raise ValueError('Choose a nonempty regular XVA archive file')
            with os.fdopen(fd, 'rb') as source:
                self.total = before.st_size
                task = self.begin('import', sr)
                self.stage = 'Uploading XVA archive'
                self.announce()
                digest = hashlib.sha256()
                class Reader:
                    def read(inner, count):
                        block = source.read(count)
                        digest.update(block)
                        return block
                response = self.transport(self.client, 'PUT', '/import',
                    {'task_id': task, 'sr_id': sr, 'restore': 'false', 'force': 'false'},
                    source=Reader(), size=self.total, checkpoint=self.checkpoint, progress=self.observe_transfer)
                received = 0
                for chunk in response.chunks():
                    self.checkpoint()
                    received += len(chunk)
                    if received > 1024*1024: raise ValueError('Import response exceeded the supported size')
                response.close(); response = None
                after = os.fstat(source.fileno())
                if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                    raise ValueError('Archive changed during import; inspect the server task before retrying')
                self.sha256 = digest.hexdigest()
            result = self.wait_task(task)
            vm = decode_reference_result(result.get('result', ''))
            machine = self.call('VM.get_record', vm)
            if vm in previous or machine.get('uuid') in previous_uuids or machine.get('is_control_domain'):
                raise ValueError('Import returned a pre-existing VM; no device or power changes were made')
            self.resources['VM'] = vm
            if machine.get('power_state') != 'Halted':
                raise ValueError('Imported VM is not halted; inspect it before changing its devices')
            for vif in machine.get('VIFs', []):
                if self.call('VIF.get_record', vif).get('VM') != vm:
                    raise ValueError('Imported adapter does not belong to the new VM')
                self.async_call('VIF.move', vif, network)
            self.client.journal.outcome(self.op_id, 'returned', result_ref=vm)
            self.stage = 'XVA import completed; review guest devices before starting'
            self.announce()
            return self.report()
        except Exception as exc:
            raise self.failed(exc) from None
        finally:
            if response: response.close()

import copy
import hashlib
import json
import io
import tarfile
import os
from pathlib import Path
import stat
import tempfile
import unittest
from flagship.api import Client, APIError
from flagship.journal import OperationJournal
from flagship.transfers import XVATransfer
from flagship.workflows import WorkflowError


class Pool:
    def __init__(self):
        self.calls = []
        self.vms = {'old-vm': {'uuid':'old-uuid', 'power_state':'Halted', 'VIFs':[]}}
        self.tasks = {}
        self.vif_network = 'old-network'
        self.counter = 0

    def rpc(self, name, session, *args):
        self.calls.append((name, args))
        if name == 'VM.get_record': return copy.deepcopy(self.vms[args[0]])
        if name == 'VM.get_all_records': return copy.deepcopy(self.vms)
        if name == 'SR.get_record':
            return {'uuid':'sr-uuid', 'content_type':'user', 'allowed_operations':['vdi_create']}
        if name == 'network.get_record': return {'uuid':'network-uuid'}
        if name == 'task.create':
            self.counter += 1
            ref = 'task-'+str(self.counter)
            self.tasks[ref] = {'uuid':ref+'-uuid', 'status':'pending', 'progress':0}
            return ref
        if name == 'task.get_record': return copy.deepcopy(self.tasks[args[0]])
        if name == 'VIF.get_record': return {'VM':'new-vm', 'uuid':'vif-uuid'}
        if name == 'Async.VIF.move':
            self.vif_network = args[1]
            self.tasks['move-task'] = {'uuid':'move-uuid', 'status':'success'}
            return 'move-task'
        raise AssertionError(name)


class Reply:
    def __init__(self, blocks, finish): self.blocks, self.finish, self.closed = blocks, finish, False
    def chunks(self):
        for block in self.blocks: yield block
        self.finish()
    def close(self): self.closed = True


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.journal = OperationJournal(self.directory/'journals')
        self.pool = Pool()
        self.client = Client('https://pool.test', journal=self.journal)
        self.client.session = 'private-session'
        self.client._rpc = self.pool.rpc
        self.journal.begin('Transfer test', self.client.endpoint)
        self.status = 'success'
        self.existing_result = False
        self.network_failure = False
        self.requests = []
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode='w', format=tarfile.USTAR_FORMAT) as tar:
            info = tarfile.TarInfo('ova.xml'); info.size = 4
            tar.addfile(info, io.BytesIO(b'meta'))
        self.archive = archive.getvalue()

    def tearDown(self):
        self.journal.close()
        self.temporary.cleanup()

    def transport(self, client, method, path, parameters, **options):
        events, _ = self.journal.history()
        self.assertTrue(any(e.get('event')=='intent' and e.get('method')=='HTTP.'+('export' if method=='GET' else 'import') for e in events))
        self.requests.append((method, path, parameters))
        if self.network_failure: raise ConnectionResetError('No replay')
        def finish():
            task = self.pool.tasks[parameters['task_id']]
            task.update(status=self.status, progress=1, error_info=['INJECTED_FAILURE'])
            if method == 'PUT':
                ref = 'old-vm' if self.existing_result else 'new-vm'
                if not self.existing_result:
                    self.pool.vms[ref] = {'uuid':'new-uuid', 'power_state':'Halted', 'VIFs':['new-vif']}
                task['result'] = '<value><array><data><value><string>'+ref+'</string></value></data></array></value>'
        if method == 'PUT':
            data = options['source'].read(options['size'])
            self.assertEqual(data, self.archive)
            options['progress'](len(data))
            return Reply([b'ignored-host-response'], finish)
        return Reply([self.archive[:789], self.archive[789:]], finish)

    def engine(self): return XVATransfer(self.client, transport=self.transport, interval=0, timeout=1)

    def test_export_publishes_only_confirmed_task_and_records_digest(self):
        target = self.directory/'vm.xva'
        result = self.engine().export_vm('old-vm', target)
        self.assertEqual(target.read_bytes(), self.archive)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertEqual(result['sha256'], hashlib.sha256(self.archive).hexdigest())
        self.assertFalse(list(self.directory.glob('*.partial')))
        self.assertEqual(result['tasks'][0]['status'], 'success')
        self.assertEqual(self.requests[0][2]['use_compression'], 'false')
        records, _ = self.journal.history()
        self.assertNotIn('private-session', json.dumps(records))
        self.assertTrue(any(e.get('event')=='workflow_progress' and e['report'].get('partial_file') for e in records))

    def test_failed_server_task_keeps_private_partial_and_no_final_archive(self):
        self.status = 'failure'
        target = self.directory/'vm.xva'
        with self.assertRaises(WorkflowError) as caught: self.engine().export_vm('old-vm', target)
        self.assertFalse(target.exists())
        partial = Path(caught.exception.report['partial_file'])
        self.assertEqual(partial.read_bytes(), self.archive)
        self.assertEqual(stat.S_IMODE(partial.stat().st_mode), 0o600)
        self.assertEqual(len(self.requests), 1)
        self.assertIn('INJECTED_FAILURE', caught.exception.reason)

    def test_existing_file_and_running_vm_are_never_exported(self):
        target = self.directory/'existing.xva';target.write_bytes(b'keep')
        with self.assertRaises(WorkflowError): self.engine().export_vm('old-vm', target)
        self.pool.vms['old-vm']['power_state'] = 'Running'
        with self.assertRaises(WorkflowError): self.engine().export_vm('old-vm', self.directory/'new.xva')
        self.assertEqual(target.read_bytes(), b'keep')
        self.assertFalse(self.requests)
        self.assertFalse(any(name=='task.create' for name,_ in self.pool.calls))

    def test_network_failure_keeps_recovery_task_and_never_replays(self):
        self.network_failure = True
        with self.assertRaises(WorkflowError) as caught:
            self.engine().export_vm('old-vm', self.directory/'vm.xva')
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(len(caught.exception.tasks), 1)
        records, _ = self.journal.history()
        self.assertTrue(any(e.get('event')=='outcome' and e.get('status')=='unknown' for e in records))

    def test_import_creates_halted_guest_maps_network_and_keeps_source(self):
        source = self.directory/'vm.xva';source.write_bytes(self.archive)
        result = self.engine().import_vm(source, 'sr', 'chosen-network')
        self.assertEqual(result['resources']['VM'], 'new-vm')
        self.assertEqual(self.pool.vms['new-vm']['power_state'], 'Halted')
        self.assertEqual(self.pool.vif_network, 'chosen-network')
        self.assertEqual(source.read_bytes(), self.archive)
        self.assertEqual(self.requests[0][2]['restore'], 'false')
        self.assertEqual(self.requests[0][2]['force'], 'false')
        self.assertFalse(any(name.startswith('Async.VM.') for name,_ in self.pool.calls))
        records, _ = self.journal.history()
        self.assertTrue(any(e.get('event')=='object_identity' and e.get('uuid')=='new-uuid' for e in records))

    def test_import_refuses_device_changes_on_preexisting_result(self):
        self.existing_result = True
        source = self.directory/'vm.xva';source.write_bytes(self.archive)
        with self.assertRaises(WorkflowError): self.engine().import_vm(source, 'sr', 'network')
        self.assertFalse(any(name=='Async.VIF.move' for name,_ in self.pool.calls))

    def test_invalid_archive_never_creates_server_task(self):
        source = self.directory/'bad.xva'; source.write_bytes(b'not an archive')
        with self.assertRaises(WorkflowError): self.engine().import_vm(source, 'sr', 'network')
        self.assertFalse(self.requests)
        self.assertFalse(any(name == 'task.create' for name, _ in self.pool.calls))

    def test_nonregular_empty_and_symlink_sources_send_nothing(self):
        empty = self.directory/'empty.xva';empty.touch()
        link = self.directory/'link.xva';link.symlink_to(empty)
        fifo = self.directory/'fifo.xva';os.mkfifo(fifo)
        for source in (empty, link, fifo):
            with self.assertRaises(WorkflowError): self.engine().import_vm(source, 'sr', 'network')
        self.assertFalse(self.requests)
        self.assertFalse(any(name=='task.create' for name,_ in self.pool.calls))


if __name__ == '__main__': unittest.main()

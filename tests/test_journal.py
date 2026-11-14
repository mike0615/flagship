import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from xenadmin_rocky.api import Client, APIError
from xenadmin_rocky.journal import OperationJournal, JournalError, recovery_needed


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name) / 'journal'
        self.journal = OperationJournal(self.directory)
        self.client = Client('https://pool.example.test', journal=self.journal)
        self.client.session = 'private-api-session'
        self.client._rpc = Mock(return_value='server-task')

    def tearDown(self):
        self.journal.close()
        self.temp.cleanup()

    def events(self):
        records, warnings = self.journal.history()
        self.assertFalse(warnings, warnings)
        return records

    def test_private_permissions_and_no_credentials_or_raw_arguments(self):
        self.client.call('Async.VIF.create', {'VM': 'vm', 'other_config': {'password': 'never-record-this'}})
        self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.journal.path.stat().st_mode), 0o600)
        text = self.journal.path.read_text()
        self.assertNotIn('never-record-this', text)
        self.assertNotIn('private-api-session', text)
        self.assertNotIn('other_config', text)
        self.assertIn('Async.VIF.create', text)

    def test_getters_and_session_logout_do_not_create_journal(self):
        self.client.call('VM.get_record', 'vm')
        self.client.call('session.logout')
        self.assertFalse(self.directory.exists())

    def test_intent_is_readable_before_server_call(self):
        def rpc(*args):
            self.assertEqual(self.events()[-1]['event'], 'intent')
            return 'server-task'
        self.client._rpc = rpc
        self.client.call('Async.VM.start', 'vm', False, False)
        self.assertEqual([r['event'] for r in self.events()], ['intent', 'outcome'])

    def test_failure_to_persist_intent_prevents_server_call(self):
        with patch.object(self.journal, 'intent', side_effect=JournalError('disk full')):
            with self.assertRaises(JournalError):
                self.client.call('Async.VM.start', 'vm', False, False)
        self.client._rpc.assert_not_called()

    def test_lost_connection_is_unknown_and_not_replayed(self):
        self.client._rpc.side_effect = ConnectionResetError()
        with self.assertRaises(ConnectionResetError):
            self.client.call('Async.VM.start', 'vm', False, False)
        self.assertEqual(self.client._rpc.call_count, 1)
        self.assertEqual(self.events()[-1]['status'], 'unknown')
        self.assertEqual(recovery_needed(self.events())[0]['state'], 'unknown_server_outcome')

    def test_result_write_failure_blocks_further_mutations_but_allows_reads(self):
        with patch.object(self.journal, 'outcome', side_effect=JournalError('disk full')):
            with self.assertRaisesRegex(JournalError, 'server-task'):
                self.client.call('Async.VM.start', 'vm', False, False)
        with self.assertRaises(JournalError):
            self.client.call('Async.VM.start', 'vm', False, False)
        self.client._rpc.assert_called_once()
        self.client._rpc.return_value = {'uuid': 'vm-uuid'}
        self.client.call('VM.get_record', 'vm')
        self.assertEqual(self.client._rpc.call_count, 2)

    def test_uuid_identity_is_recorded_without_full_object(self):
        self.client._rpc.return_value = {'uuid': 'stable-uuid', 'password': 'never-copy-object'}
        self.client.call('VM.get_record', 'vm-ref')
        self.client._rpc.return_value = ''
        self.client.call('VM.set_name_label', 'vm-ref', 'private-new-label')
        intent = next(r for r in self.events() if r['event'] == 'intent')
        self.assertEqual(intent['objects'], [{'class': 'VM', 'uuid': 'stable-uuid', 'ref': 'vm-ref'}])
        self.assertNotIn('never-copy-object', self.journal.path.read_text())
        self.assertNotIn('private-new-label', self.journal.path.read_text())

    def test_terminal_task_state_and_uuid_survive_new_journal_instance(self):
        self.client.call('Async.VM.clone', 'template', 'name')
        self.client._rpc.return_value = {'uuid': 'stable-task-uuid', 'status': 'success',
                                         'result': '<value><string>new-vm</string></value>'}
        self.client.call('task.get_record', 'server-task')
        self.client.call('task.get_record', 'server-task')
        self.journal.close()
        reopened = OperationJournal(self.directory)
        records, warnings = reopened.history()
        self.assertFalse(warnings)
        states = [r for r in records if r['event'] == 'task_state']
        self.assertEqual(len(states), 1)
        self.assertEqual(states[0]['uuid'], 'stable-task-uuid')
        self.assertEqual(states[0]['result_ref'], 'new-vm')
        self.assertEqual(recovery_needed(records), [])

    def test_api_error_arguments_are_not_recorded(self):
        self.client._rpc.side_effect = APIError(['PERMISSION_DENIED', 'private-password'])
        with self.assertRaises(APIError):
            self.client.call('VM.set_name_label', 'vm', 'new')
        self.assertNotIn('private-password', self.journal.path.read_text())
        self.assertEqual(self.events()[-1]['status'], 'server_failure')

    def test_reports_whitelist_fields_and_deduplicate_percentage_updates(self):
        self.journal.begin('Create VM', 'https://user:private-password@pool/')
        report = {'stage': 'VM.clone', 'password': 'private-password', 'resources': {'VM': 'vm', 'password': 'private-password'},
                  'tasks': [{'method': 'VM.clone', 'task': 'task', 'status': 'pending', 'progress': 0,
                             'session': 'private-session'}]}
        self.journal.workflow(report)
        report['tasks'][0]['progress'] = 0.5
        self.journal.workflow(report)
        text = self.journal.path.read_text()
        self.assertNotIn('private-password', text)
        self.assertNotIn('private-session', text)
        self.assertEqual(len([r for r in self.events() if r['event'] == 'workflow_progress']), 1)

    def test_symlink_directory_is_rejected(self):
        destination = Path(self.temp.name) / 'destination'
        destination.mkdir()
        self.directory.symlink_to(destination, target_is_directory=True)
        with self.assertRaises(JournalError):
            self.journal.intent('VM.set_name_label')
        self.assertFalse(list(destination.iterdir()))

    def test_partial_final_record_preserves_prior_intent_and_warns(self):
        self.journal.intent('VM.set_name_label')
        self.journal.close()
        with self.journal.path.open('ab') as stream:
            stream.write(b'{"event":')
        records, warnings = self.journal.history()
        self.assertEqual(len(records), 1)
        self.assertIn('incomplete final record', warnings[0])
        self.assertEqual(recovery_needed(records)[0]['state'], 'no_recorded_outcome')

    def test_process_exit_after_intent_preserves_recovery_record(self):
        code = ('import os; from xenadmin_rocky.journal import OperationJournal; '
                'j=OperationJournal(' + repr(str(self.directory)) + '); '
                'j.intent("Async.VM.start"); os._exit(17)')
        result = subprocess.run([sys.executable, '-c', code])
        self.assertEqual(result.returncode, 17)
        records, warnings = self.journal.history()
        self.assertFalse(warnings)
        self.assertEqual(recovery_needed(records)[0]['method'], 'Async.VM.start')

    def test_created_object_identity_is_durable_when_uuid_is_observed(self):
        self.client.call('Async.VM.clone', 'template', 'new-name')
        self.client._rpc.return_value = {'uuid': 'task-uuid', 'status': 'success',
                                         'result': '<value><string>created-vm</string></value>'}
        self.client.call('task.get_record', 'server-task')
        self.client._rpc.return_value = {'uuid': 'stable-created-uuid'}
        self.client.call('VM.get_record', 'created-vm')
        identity = [r for r in self.events() if r['event'] == 'object_identity'][0]
        self.assertEqual(identity['uuid'], 'stable-created-uuid')
        self.assertEqual(identity['object_class'], 'VM')

    def test_interrupted_workflow_with_known_resources_requires_review(self):
        self.journal.begin('Add disk')
        self.journal.finish('interrupted_or_failed', report={'resources': {'VDI': 'created-disk'}})
        review = recovery_needed(self.events())
        self.assertEqual(review[0]['state'], 'interrupted_workflow_inspect_recorded_objects')
        self.assertEqual(review[0]['report']['resources']['VDI'], 'created-disk')

    def test_invalid_record_types_warn_instead_of_crashing_history(self):
        self.journal.intent('VM.set_name_label')
        self.journal.close()
        with self.journal.path.open('ab') as stream:
            stream.write(b'{"event":"intent","time":{},"op_id":"bad"}\n')
        records, warnings = self.journal.history()
        self.assertEqual(len(records), 1)
        self.assertTrue(warnings)

    def test_complete_device_workflow_records_uuid_and_confirmed_tasks(self):
        from test_devices import DevicePool
        from xenadmin_rocky.devices import DeviceManager
        pool = DevicePool(running=True)
        self.client._rpc = lambda method, session, *args: pool.call(method, *args)
        self.journal.begin('Add disk', self.client.endpoint)
        report = DeviceManager(self.client, progress=self.journal.workflow).execute(
            'add_disk', 'guest', sr='selected-sr', name='Extra disk', size_gib=50)
        self.journal.finish('completed', report=report)
        records = self.events()
        self.assertEqual(recovery_needed(records), [])
        self.assertTrue(any(r.get('event') == 'object_identity' and r.get('uuid') == 'added-disk-uuid' for r in records))
        self.assertTrue(any(r.get('event') == 'intent' and r.get('method') == 'Async.VBD.plug' for r in records))
        self.assertTrue(pool.vbds[report['resources']['VBD']]['currently_attached'])

    def test_fsync_failure_before_request_blocks_server_changes(self):
        with patch('xenadmin_rocky.journal.os.fsync', side_effect=OSError('simulated disk failure')):
            with self.assertRaises(JournalError):
                self.client.call('Async.VM.start', 'vm', False, False)
        self.client._rpc.assert_not_called()
        self.assertTrue(self.journal.failed)

    def test_explicit_export_is_private_even_when_replacing_permissive_file(self):
        from xenadmin_rocky.journal import save_json_private
        destination = Path(self.temp.name) / 'export.json'
        destination.write_text('old')
        destination.chmod(0o644)
        save_json_private(destination, {'resources': {'VM': 'vm'}})
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
        self.assertEqual(json.loads(destination.read_text())['resources']['VM'], 'vm')

    def test_explicit_export_refuses_symlink_without_modifying_target(self):
        from xenadmin_rocky.journal import save_json_private
        target = Path(self.temp.name) / 'original'
        target.write_text('keep')
        link = Path(self.temp.name) / 'export.json'
        link.symlink_to(target)
        with self.assertRaises(OSError):
            save_json_private(link, {'new': 'data'})
        self.assertEqual(target.read_text(), 'keep')

    def test_inventory_export_handles_xmlrpc_timestamps(self):
        from xmlrpc.client import DateTime
        from xenadmin_rocky.journal import save_json_private
        from xenadmin_rocky.redaction import safe_record
        destination = Path(self.temp.name) / 'inventory.json'
        save_json_private(destination, safe_record({'created': DateTime('20261114T12:00:00')}))
        self.assertEqual(json.loads(destination.read_text())['created'], '20261114T12:00:00')

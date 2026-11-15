import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock
from flagship.recovery import inspect_by_uuid
from flagship.journal import OperationJournal

OBJECT_UUID = '00000000-0000-4000-8000-000000000001'


class RecoveryTests(unittest.TestCase):
    def test_inspection_resolves_new_reference_by_uuid_and_only_uses_getters(self):
        client = Mock()
        client.call.side_effect = ['current-server-reference', {'uuid': OBJECT_UUID, 'password': 'never-export'}]
        report = inspect_by_uuid(client, 'VM', OBJECT_UUID)
        self.assertEqual(client.call.call_args_list[0].args, ('VM.get_by_uuid', OBJECT_UUID))
        self.assertEqual(client.call.call_args_list[1].args, ('VM.get_record', 'current-server-reference'))
        self.assertEqual(report['record']['password'], '[redacted]')
        self.assertEqual(report['current_reference'], 'current-server-reference')

    def test_invalid_class_and_opaque_reference_do_not_reach_server(self):
        client = Mock()
        for kind, value in [('session', OBJECT_UUID), ('VM', 'OpaqueRef:old-reference')]:
            with self.assertRaises(ValueError):
                inspect_by_uuid(client, kind, value)
        client.call.assert_not_called()

    def test_headless_cli_help_imports_without_display(self):
        environment = dict(os.environ)
        environment.pop('DISPLAY', None)
        result = subprocess.run([sys.executable, '-m', 'flagship.recovery', '--help'],
                                env=environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('inspect', result.stdout)

    def test_headless_history_reopens_saved_intent_and_does_not_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = OperationJournal(directory)
            journal.intent('Async.VM.start')
            journal.close()
            result = subprocess.run([sys.executable, '-m', 'flagship.recovery', 'history', '--directory', directory],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('no_recorded_outcome', result.stdout)
            self.assertIn('Async.VM.start', result.stdout)
            self.assertEqual(len(list(Path(directory).glob('*.jsonl'))), 1)

    def test_wrong_server_identity_is_not_presented_as_the_requested_object(self):
        client = Mock()
        client.call.side_effect = ['ref', {'uuid': '00000000-0000-4000-8000-000000000002'}]
        with self.assertRaisesRegex(ValueError, 'identity'):
            inspect_by_uuid(client, 'VM', OBJECT_UUID)

import os
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch
from flagship.app import Application
from flagship.device_panel import DevicePanel
from flagship.history import HistoryDialog
from flagship.journal import OperationJournal
from flagship.workflows import GiB


@unittest.skipUnless(os.environ.get('DISPLAY'), 'requires X display (use xvfb-run)')
class DevicePanelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.journal = OperationJournal(Path(self.temp.name)/'journals')
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = Application(self.root, journal=self.journal)
        self.app.client = Mock()
        self.app.records = {
            'VM': {'guest': {'name_label': 'Example guest', 'power_state': 'Halted'}},
            'VBD': {'connection': {'VM': 'guest', 'VDI': 'data', 'type': 'Disk', 'userdevice': '0', 'mode': 'RW'}},
            'VDI': {'data': {'name_label': 'Example disk', 'virtual_size': str(20*GiB), 'uuid': 'disk-uuid', 'type': 'user'}},
            'VIF': {'adapter': {'VM': 'guest', 'network': 'network', 'device': '0', 'MAC': '02:11:22:33:44:55'}},
            'network': {'network': {'name_label': 'Example network'}}}
        self.app.start_device_operation = Mock()
        self.panel = DevicePanel(self.app, 'guest')

    def tearDown(self):
        self.app.jobs.shutdown(wait=True)
        self.journal.close()
        self.root.destroy()
        self.temp.cleanup()

    def select_disk(self):
        self.panel.tables['disk'].selection_set('connection')

    def test_tables_show_disk_capacity_and_adapter_mac(self):
        disk = self.panel.tables['disk'].item('connection')['values']
        nic = self.panel.tables['nic'].item('adapter')['values']
        self.assertIn('20 GiB', disk)
        self.assertIn('02:11:22:33:44:55', nic)
        self.app.start_device_operation.assert_not_called()

    @patch('flagship.device_panel.messagebox.askyesno', return_value=False)
    def test_declined_detach_does_not_submit(self, confirm):
        self.select_disk()
        self.panel.action('detach_disk')
        confirm.assert_called_once()
        self.app.start_device_operation.assert_not_called()

    @patch('flagship.device_panel.messagebox.askyesno', return_value=True)
    def test_confirmed_detach_has_no_delete_flag(self, confirm):
        self.select_disk()
        self.panel.action('detach_disk')
        self.app.start_device_operation.assert_called_once_with('detach_disk', 'guest', {'vbd': 'connection'})

    @patch('flagship.device_panel.messagebox.askyesno')
    @patch('flagship.device_panel.simpledialog.askstring', return_value='wrong')
    def test_wrong_delete_uuid_never_submits(self, ask, confirm):
        self.select_disk()
        self.panel.action('delete_disk')
        confirm.assert_not_called()
        self.app.start_device_operation.assert_not_called()

    @patch('flagship.device_panel.messagebox.askyesno', return_value=True)
    @patch('flagship.device_panel.simpledialog.askstring', return_value='disk-uuid')
    def test_delete_uuid_is_forwarded_for_fresh_server_validation(self, ask, confirm):
        self.select_disk()
        self.panel.action('delete_disk')
        self.app.start_device_operation.assert_called_once_with('delete_disk', 'guest',
                                                                {'vbd': 'connection', 'confirmation_uuid': 'disk-uuid'})

    @patch('flagship.device_panel.messagebox.showerror')
    def test_window_from_old_connection_cannot_change_new_pool(self, error):
        self.app.client = Mock()
        self.select_disk()
        self.panel.action('detach_disk')
        error.assert_called_once()
        self.app.start_device_operation.assert_not_called()

    @patch('flagship.device_panel.messagebox.askyesno')
    def test_cancelled_resource_choice_never_submits(self, confirm):
        self.panel.choose = Mock(return_value=(False, None))
        self.panel.action('add_nic')
        confirm.assert_not_called()
        self.app.start_device_operation.assert_not_called()

    def test_history_reopens_unconfirmed_intent_without_server_calls(self):
        self.journal.intent('Async.VM.start')
        self.journal.close()
        history = HistoryDialog(self.root, OperationJournal(self.journal.directory))
        self.assertEqual(len(history.records), 1)
        self.assertTrue(history.window.winfo_exists())
        self.app.client.call.assert_not_called()

    def test_offline_help_index_opens_recovery_chapter_without_server(self):
        from flagship.help import HelpDialog
        docs = Path(self.temp.name)/'docs'
        docs.mkdir()
        (docs/'USER_GUIDE.md').write_text('# User guide\nStart here.\n')
        (docs/'RECOVERY.md').write_text('# Recovery\nInspect saved intent before retrying.\n')
        help_window = HelpDialog(self.root, docs)
        help_window.select_chapter('RECOVERY.md')
        self.assertIn('Inspect saved intent', help_window.text.get('1.0', 'end'))
        self.app.client.call.assert_not_called()

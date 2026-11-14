"""Behavior checks with a real Tk interpreter, without a hypervisor."""
import os
import tkinter as tk
import unittest
from unittest.mock import Mock, patch
from xenadmin_rocky.app import Application


@unittest.skipUnless(os.environ.get('DISPLAY'), 'requires X display (use xvfb-run)')
class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = Application(self.root)
        self.app.client = Mock()
        self.app.records = {'VM': {'vm-1': {'name_label': 'Test guest', 'uuid': 'uuid-1',
            'power_state': 'Halted', 'allowed_operations': ['start'], 'is_a_template': False}},
            'host': {'host-1': {'name_label': 'Test host'}},
            'VBD': {'disk-1': {'VM': 'vm-1', 'VDI': 'vdi-1'}}}
        self.app.populate()
        item = next(k for k, v in self.app.items.items() if v == ('VM', 'vm-1'))
        self.app.tree.selection_set(item)

    def tearDown(self):
        self.app.jobs.shutdown(wait=True)
        self.root.destroy()

    def test_select_guest_shows_related_disk(self):
        self.app.show()
        self.assertIn('disk-1', self.app.views['Storage'].get('1.0', 'end'))
        self.assertIn('Test guest', self.app.views['General'].get('1.0', 'end'))

    @patch('xenadmin_rocky.app.messagebox.showwarning')
    def test_disallowed_operation_never_reaches_server(self, warning):
        self.app.action('hard_shutdown')
        warning.assert_called_once()
        self.app.client.vm_action.assert_not_called()

    @patch('xenadmin_rocky.app.messagebox.askyesno', return_value=False)
    def test_declining_confirmation_never_reaches_server(self, confirm):
        self.app.action('start')
        confirm.assert_called_once()
        self.app.client.vm_action.assert_not_called()

    def test_filter_matches_uuid(self):
        self.app.search.set('uuid-1')
        self.assertEqual(list(self.app.items.values()), [('VM', 'vm-1')])

    def test_filter_no_match_is_empty(self):
        self.app.search.set('does-not-exist')
        self.assertEqual(self.app.items, {})

    def test_task_monitor_pauses_on_session_loss_without_resubmitting(self):
        from xenadmin_rocky.api import APIError
        self.app.tracker.add('OpaqueRef:task', 'start', 'Test guest')
        self.app.client.call.side_effect = APIError(['SESSION_INVALID'])
        self.app.submit = lambda work, done, label: done(work())
        self.app.poll_tasks()
        self.assertTrue(self.app.monitor_paused)
        self.assertIn('paused', self.app.status.get())
        self.app.poll_tasks()
        self.app.client.call.assert_called_once_with('task.get_record', 'OpaqueRef:task')
        self.app.client.vm_action.assert_not_called()

    def test_task_success_is_visible_in_tasks_view(self):
        self.app.tracker.add('OpaqueRef:task', 'start', 'Test guest')
        self.app.client.call.return_value = {'status': 'success', 'progress': '1'}
        self.app.submit = lambda work, done, label: done(work())
        self.app.poll_tasks()
        self.assertIn('success (100%)', self.app.views['Tasks'].get('1.0', 'end'))

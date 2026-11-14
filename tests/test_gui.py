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

    def prepare_wizard(self):
        from xenadmin_rocky.wizard import NewVMDialog
        self.app.records['VM']['template'] = {'name_label': 'Template', 'is_a_template': True}
        self.app.records['SR'] = {'sr': {'name_label': 'Storage', 'allowed_operations': ['vdi_create']}}
        self.app.records['network'] = {'network': {'name_label': 'Network'}}
        self.app.start_provisioning = Mock()
        return NewVMDialog(self.app)

    def test_creation_review_is_read_only_until_explicit_create(self):
        dialog = self.prepare_wizard()
        dialog.review()
        self.assertIsNotNone(dialog.plan)
        self.app.client.call.assert_not_called()
        self.app.start_provisioning.assert_not_called()
        dialog.create()
        self.app.start_provisioning.assert_called_once_with(dialog.plan)

    @patch('xenadmin_rocky.wizard.messagebox.showerror')
    def test_invalid_creation_form_cannot_submit(self, error):
        dialog = self.prepare_wizard()
        dialog.values['Memory (MiB)'].set('0')
        dialog.review()
        self.assertIsNone(dialog.plan)
        error.assert_called_once()
        dialog.create()
        self.app.start_provisioning.assert_not_called()
        dialog.window.destroy()

    @patch('xenadmin_rocky.wizard.messagebox.showinfo')
    def test_busy_monitor_does_not_discard_reviewed_creation_plan(self, info):
        dialog = self.prepare_wizard()
        dialog.review()
        self.app.busy = True
        dialog.create()
        self.assertTrue(dialog.window.winfo_exists())
        self.app.start_provisioning.assert_not_called()
        info.assert_called_once()
        self.app.busy = False
        dialog.create()
        self.app.start_provisioning.assert_called_once()

    @patch('xenadmin_rocky.app.simpledialog.askinteger')
    @patch('xenadmin_rocky.app.messagebox.showwarning')
    def test_running_vm_hardware_editor_never_requests_changes(self, warning, ask):
        self.app.records['VM']['vm-1']['power_state'] = 'Running'
        self.app.hardware()
        warning.assert_called_once()
        ask.assert_not_called()
        self.app.client.call.assert_not_called()

    @patch('xenadmin_rocky.app.messagebox.showerror')
    def test_failed_workflow_retains_complete_report_without_oversized_dialog(self, error):
        from concurrent.futures import Future
        from xenadmin_rocky.workflows import WorkflowError
        tasks = [{'task': 'task-' + str(n), 'status': 'success'} for n in range(30)]
        failure = WorkflowError('VM.provision', 'INJECTED_FAILURE', {'VM': 'created-vm'}, tasks)
        future = Future()
        future.set_exception(failure)
        self.app.results.put((future, Mock()))
        self.app.poll()
        self.assertEqual(self.app.last_workflow_report['tasks'], tasks)
        self.assertEqual(self.app.last_workflow_report['resources']['VM'], 'created-vm')
        self.assertIn('Save workflow report', error.call_args.args[1])
        self.assertLess(len(error.call_args.args[1]), 600)

    @patch('xenadmin_rocky.app.choose_resource', return_value=(True, 'task'))
    @patch('xenadmin_rocky.app.messagebox.askyesno', return_value=False)
    def test_declined_task_cancellation_never_submits(self, confirm, choose):
        self.app.records['task'] = {'task': {'name_label': 'Example task', 'status': 'pending', 'allowed_operations': ['cancel']}}
        self.app.submit = Mock()
        self.app.cancel_task()
        confirm.assert_called_once()
        self.app.submit.assert_not_called()
        self.app.client.call.assert_not_called()

    @patch('xenadmin_rocky.app.choose_resource', return_value=(True, 'host-1'))
    @patch('xenadmin_rocky.app.messagebox.askyesno', return_value=True)
    def test_migration_uses_named_host_selector_and_reviews_destination(self, confirm, choose):
        self.app.records['VM']['vm-1']['allowed_operations'].append('pool_migrate')
        self.app.submit = Mock()
        self.app.action('pool_migrate')
        self.assertIn('Test host', confirm.call_args.args[1])
        self.app.submit.call_args.args[0]()
        self.app.client.vm_action.assert_called_once_with('vm-1', 'pool_migrate', 'host-1', {})
        self.assertTrue(self.app.submit.call_args.kwargs['mutation'])

    def test_failed_remote_logout_clears_local_pool_and_task_context(self):
        self.app.client.logout.side_effect = OSError('connection lost')
        self.app.tracker.add('old-task', 'start', 'Old guest')
        self.app.last_workflow_report = {'tasks': [{'task': 'old-pool-task', 'status': 'pending'}]}
        self.app.submit = lambda work, done, label: done(work())
        self.app.disconnect()
        self.assertIsNone(self.app.client)
        self.assertIsNone(self.app.last_workflow_report)
        self.assertEqual(self.app.records, {})
        self.assertEqual(self.app.tracker.tasks, {})
        self.assertIn('not confirmed', self.app.status.get())

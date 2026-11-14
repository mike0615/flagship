import unittest
from unittest.mock import Mock
from xenadmin_rocky.tasks import TaskTracker
from xenadmin_rocky.api import APIError


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.tracker = TaskTracker()
        self.tracker.add('OpaqueRef:task', 'start', 'Example guest')
        self.client = Mock()

    def test_pending_is_not_success(self):
        self.assertTrue(self.tracker.pending)
        self.assertIn('pending', self.tracker.summary())

    def test_failure_remains_failure_and_does_not_resubmit(self):
        self.client.call.return_value = {'status': 'failure', 'progress': '0.4',
                                         'error_info': ['VM_BAD_POWER_STATE', 'private-details']}
        self.tracker.poll(self.client)
        self.assertFalse(self.tracker.pending)
        self.assertIn('failure', self.tracker.summary())
        self.assertNotIn('private-details', self.tracker.summary())
        self.tracker.poll(self.client)
        self.client.call.assert_called_once_with('task.get_record', 'OpaqueRef:task')

    def test_success_is_reported_after_server_confirmation(self):
        self.client.call.return_value = {'status': 'success', 'progress': '1'}
        self.tracker.poll(self.client)
        self.assertFalse(self.tracker.pending)
        self.assertIn('success (100%)', self.tracker.summary())

    def test_expired_session_does_not_change_task_outcome(self):
        self.client.call.side_effect = APIError(['SESSION_INVALID'])
        with self.assertRaises(APIError):
            self.tracker.poll(self.client)
        self.assertTrue(self.tracker.pending)
        self.assertNotIn('success', self.tracker.summary())

    def test_missing_task_is_unavailable_not_success(self):
        self.client.call.side_effect = APIError(['HANDLE_INVALID'])
        self.tracker.poll(self.client)
        self.assertFalse(self.tracker.pending)
        self.assertIn('unavailable', self.tracker.summary())

    def test_malformed_task_ref_is_rejected(self):
        for value in ('', None, {}, 0, 'OpaqueRef:NULL'):
            with self.assertRaises(ValueError):
                self.tracker.add(value, 'start', 'guest')

    def test_progress_is_bounded(self):
        self.client.call.return_value = {'status': 'pending', 'progress': '2'}
        self.tracker.poll(self.client)
        self.assertIn('(100%)', self.tracker.summary())
        self.assertTrue(self.tracker.pending)

    def test_task_reference_is_opaque(self):
        self.tracker.add('server-task-42', 'snapshot', 'guest')
        self.assertIn('server-task-42', self.tracker.tasks)

    def test_cancellation_request_does_not_claim_task_cancelled(self):
        from xenadmin_rocky.tasks import request_cancellation
        client = Mock()
        client.call.side_effect = [{'status': 'pending', 'allowed_operations': ['cancel']}, '']
        report = request_cancellation(client, 'server-task')
        self.assertEqual(report['status'], 'cancellation_requested')
        self.assertEqual(client.call.call_args.args, ('task.cancel', 'server-task'))

    def test_finished_task_is_not_cancelled(self):
        from xenadmin_rocky.tasks import request_cancellation
        client = Mock()
        client.call.return_value = {'status': 'success', 'allowed_operations': []}
        with self.assertRaises(ValueError):
            request_cancellation(client, 'server-task')
        client.call.assert_called_once_with('task.get_record', 'server-task')

    def test_non_cancellable_task_is_not_submitted(self):
        from xenadmin_rocky.tasks import request_cancellation
        client = Mock()
        client.call.return_value = {'status': 'pending', 'allowed_operations': []}
        with self.assertRaises(ValueError):
            request_cancellation(client, 'server-task')
        client.call.assert_called_once()

    def test_already_cancelling_task_is_not_requested_again(self):
        from xenadmin_rocky.tasks import request_cancellation
        client = Mock()
        client.call.return_value = {'status': 'cancelling', 'allowed_operations': []}
        self.assertEqual(request_cancellation(client, 'server-task')['status'], 'cancelling')
        client.call.assert_called_once()

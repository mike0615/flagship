import unittest
from unittest.mock import Mock
from flagship.api import Client, APIError, Transport
from flagship.app import safe_record


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.client = Client('https://pool.example.test')
        self.client.session = 'secret-session'
        self.proxy = self.client.proxy = Mock()

    def test_reject_insecure_or_credential_urls(self):
        for url in ('http://host', 'https://u:p@host', 'https://host/path',
                    'https://host/?session=x', 'https://host/#x'):
            with self.assertRaises(ValueError):
                Client(url)

    def test_secure_context_and_timeout(self):
        import ssl
        c = Client('https://pool.example.test')
        transport = c.proxy('transport')
        self.assertTrue(transport.context.check_hostname)
        self.assertEqual(transport.context.verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(transport.timeout, 30)

    def test_mutation_not_retried(self):
        t = Transport(None)
        t.single_request = Mock(side_effect=ConnectionResetError())
        with self.assertRaises(ConnectionResetError):
            t.request('host', '/', b'x')
        self.assertEqual(t.single_request.call_count, 1)

    def test_start_signature(self):
        getattr(self.proxy, 'Async.VM.start').return_value = {'Status': 'Success', 'Value': 'task'}
        self.assertEqual(self.client.vm_action('vm', 'start', False, False), 'task')
        getattr(self.proxy, 'Async.VM.start').assert_called_once_with('secret-session', 'vm', False, False)

    def test_setter_is_synchronous(self):
        getattr(self.proxy, 'VM.set_name_label').return_value = {'Status': 'Success', 'Value': ''}
        self.client.vm_action('vm', 'set_name_label', 'new')
        getattr(self.proxy, 'VM.set_name_label').assert_called_once_with('secret-session', 'vm', 'new')

    def test_error_does_not_expose_arguments(self):
        getattr(self.proxy, 'VM.get_record').return_value = {'Status': 'Failure',
                                               'ErrorDescription': ['SESSION_INVALID', 'secret-session']}
        with self.assertRaises(APIError) as caught:
            self.client.call('VM.get_record', 'vm')
        self.assertEqual(str(caught.exception), 'SESSION_INVALID')

    def test_inventory_permission_failure_is_visible(self):
        def rpc(name, *args):
            if name == 'SR.get_all_records':
                raise APIError(['RBAC_PERMISSION_DENIED'])
            return {'ref': {}}
        self.client._rpc = rpc
        records, errors = self.client.inventory()
        self.assertEqual(records['SR'], {})
        self.assertEqual(errors['SR'], 'RBAC_PERMISSION_DENIED')
        self.assertIn('VM', records)

    def test_expired_session_aborts_inventory(self):
        self.client._rpc = Mock(side_effect=APIError(['SESSION_INVALID']))
        with self.assertRaises(APIError):
            self.client.inventory()

    def test_no_unlisted_mutations(self):
        with self.assertRaises(ValueError):
            self.client.vm_action('vm', 'erase_everything')

    def test_redaction_is_recursive(self):
        result = safe_record({'password': 'p', 'nested': [{'session_id': 's',
                              'location': 'https://x?session_id=s', 'name_label': 'vm'}]})
        self.assertNotIn('https://', str(result))
        self.assertEqual(result['nested'][0]['session_id'], '[redacted]')
        self.assertEqual(result['nested'][0]['name_label'], 'vm')

    def test_logout_clears_session_even_on_error(self):
        self.client._rpc = Mock(side_effect=APIError(['SESSION_INVALID']))
        with self.assertRaises(APIError):
            self.client.logout()
        self.assertIsNone(self.client.session)


if __name__ == '__main__':
    unittest.main()

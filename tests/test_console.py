import io
import ssl
import unittest
from unittest.mock import Mock, patch
from flagship.console import ConsoleError, console_target, open_console


class ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock(endpoint='https://pool.test', session='private-session')
        self.vm = {'power_state': 'Running', 'resident_on': 'host'}
        self.record = {'VM': 'vm', 'protocol': 'rfb', 'uuid': 'console-uuid',
                       'location': 'https://member.test/console?ref=console-ref'}
        def call(name, *args):
            return {'VM.get_record': self.vm, 'host.get_record': {'address': 'member.test'},
                    'VM.get_consoles': ['console-ref'], 'console.get_record': self.record}[name]
        self.client.call.side_effect = call

    def test_fresh_ownership_and_host_resolution(self):
        self.assertEqual(console_target(self.client, 'vm'),
                         ('member.test', 443, '/console?ref=console-ref'))
        self.client.call.assert_any_call('VM.get_record', 'vm')
        self.client.call.assert_any_call('host.get_record', 'host')
        self.record['location'] = 'https://member.test/console?uuid=console-uuid'
        self.assertIn('uuid=console-uuid', console_target(self.client, 'vm')[2])

    def test_rejects_credential_forwarding_targets(self):
        for location in ('http://member.test/console?ref=console-ref',
                         'https://attacker.test/console?ref=console-ref',
                         'https://member.test:8443/console?ref=console-ref',
                         'https://member.test/other?ref=console-ref',
                         'https://member.test/console?ref=other',
                         'https://member.test/console?ref=console-ref&session_id=secret',
                         'https://u:p@member.test/console?ref=console-ref',
                         'https://member.test/console?ref=console-ref#fragment',
                         'https://member.test/console?ref=console-ref\r\nX:yes'):
            with self.subTest(location=location):
                self.record['location'] = location
                with self.assertRaises(ConsoleError):
                    console_target(self.client, 'vm')

    def test_refuses_foreign_console_and_stopped_vm(self):
        self.record['VM'] = 'another-vm'
        with self.assertRaises(ConsoleError): console_target(self.client, 'vm')
        self.vm['power_state'] = 'Halted'
        with self.assertRaises(ConsoleError): console_target(self.client, 'vm')

    def socket(self, response):
        connection = Mock()
        connection.makefile.return_value = io.BytesIO(response)
        self.client.ssl_context.wrap_socket.return_value = connection
        return connection

    @patch('flagship.console.socket.create_connection')
    def test_tunnel_preserves_buffered_frame_and_cookie_not_url(self, connect):
        connection = self.socket(b'HTTP/1.1 200 OK\r\nServer: xapi\r\n\r\nRFB 003.008\n')
        tunnel = open_console(self.client, 'vm')
        self.assertEqual(tunnel.read(12), b'RFB 003.008\n')
        request = connection.sendall.call_args.args[0]
        self.assertIn(b'Cookie: session_id=private-session\r\n', request)
        self.assertNotIn(b'private-session', request.split(b'\r\n')[0])
        self.client.ssl_context.wrap_socket.assert_called_once_with(connect.return_value, server_hostname='member.test')
        tunnel.close()
        connection.close.assert_called_once()

    @patch('flagship.console.socket.create_connection')
    def test_refused_or_oversized_response_never_retried_or_exposed(self, connect):
        for response in (b'HTTP/1.1 302 private-session\r\n\r\n',
                         b'HTTP/1.1 403 private-session\r\n\r\n',
                         b'HTTP/1.1 200 OK\r\n' + b'a'*17000):
            connection = self.socket(response)
            with self.assertRaises(ConsoleError) as caught:
                open_console(self.client, 'vm')
            self.assertNotIn('private-session', str(caught.exception))
            connection.close.assert_called_once()
        self.assertEqual(connect.call_count, 3)

    @patch('flagship.console.socket.create_connection')
    def test_tls_failure_sends_no_session(self, connect):
        self.client.ssl_context.wrap_socket.side_effect = ssl.SSLCertVerificationError('untrusted')
        with self.assertRaises(ssl.SSLCertVerificationError): open_console(self.client, 'vm')
        connect.return_value.sendall.assert_not_called()
        connect.return_value.close.assert_called_once()


if __name__ == '__main__': unittest.main()

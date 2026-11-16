import io
import ssl
import unittest
from unittest.mock import Mock, patch
from flagship.httpstream import request, Response, TransferError


class HTTPStreamTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock(endpoint='https://pool.test', session='private-session')
        self.client.call.return_value = {'host': {'address': 'member.test'}}

    def connection(self, data):
        connection = Mock()
        connection.makefile.return_value = io.BytesIO(data)
        return connection

    @patch('flagship.httpstream.socket.create_connection')
    def test_export_streams_chunked_and_keeps_cookie_out_of_url(self, connect):
        connection = self.connection(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n2;ext=yes\r\nde\r\n0\r\nDigest: ignored\r\n\r\n')
        self.client.trust.wrap.return_value = connection
        response = request(self.client, 'GET', '/export', {'uuid': 'vm-uuid'})
        try: self.assertEqual(b''.join(response.chunks()), b'abcde')
        finally: response.close()
        wire = connection.sendall.call_args.args[0]
        self.assertIn(b'Cookie: session_id=private-session', wire)
        self.assertNotIn(b'private-session', wire.split(b'\r\n')[0])
        self.client.trust.wrap.assert_called_once_with(connect.return_value, 'pool.test', 443)

    @patch('flagship.httpstream.socket.create_connection')
    def test_upload_follows_verified_prebody_redirect_then_sends_once(self, connect):
        first = self.connection(b'HTTP/1.1 307 Redirect\r\nLocation: https://member.test/import?sr_id=storage&session_id=private-session\r\n\r\n')
        second = self.connection(b'HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok')
        self.client.trust.wrap.side_effect = [first, second]
        progress = Mock()
        response = request(self.client, 'PUT', '/import', {'sr_id':'storage'}, io.BytesIO(b'payload'), 7, progress=progress)
        try: self.assertEqual(b''.join(response.chunks()), b'ok')
        finally: response.close()
        self.assertEqual(first.sendall.call_count, 1)
        self.assertEqual(second.sendall.call_args_list[1].args, (b'payload',))
        self.assertNotIn(b'session_id=', second.sendall.call_args_list[0].args[0].split(b'\r\n')[0])
        progress.assert_called_once_with(7)
        self.assertEqual(connect.call_args_list[1].args[0], ('member.test', 443))

    @patch('flagship.httpstream.socket.create_connection')
    def test_redirects_cannot_forward_credentials_or_change_import_parameters(self, connect):
        for location in ('https://attacker.test/import?sr_id=storage',
                         'http://member.test/import?sr_id=storage',
                         'https://member.test:8443/import?sr_id=storage',
                         'https://member.test/import?sr_id=other',
                         'https://member.test/export?sr_id=storage',
                         'https://u:p@member.test/import?sr_id=storage'):
            with self.subTest(location=location):
                connection = self.connection(('HTTP/1.1 307 Redirect\r\nLocation: '+location+'\r\n\r\n').encode())
                self.client.trust.wrap.return_value = connection
                source = io.BytesIO(b'payload')
                with self.assertRaises(TransferError):
                    request(self.client, 'PUT', '/import', {'sr_id':'storage'}, source, 7)
                self.assertEqual(source.tell(), 0)
                self.assertEqual(connection.sendall.call_count, 1)
        self.assertEqual(connect.call_count, 6)

    @patch('flagship.httpstream.socket.create_connection')
    def test_failed_upload_is_not_retried_and_body_error_is_not_exposed(self, connect):
        connection = self.connection(b'HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 500 private-session\r\n\r\n')
        self.client.trust.wrap.return_value = connection
        with self.assertRaises(TransferError) as caught:
            request(self.client, 'PUT', '/import', {}, io.BytesIO(b'data'), 4)
        self.assertNotIn('private-session', str(caught.exception))
        connect.assert_called_once()
        self.assertEqual(connection.sendall.call_count, 2)

    @patch('flagship.httpstream.socket.create_connection')
    def test_xapi_early_200_with_matching_task_streams_body_without_second_status(self,connect):
        connection=self.connection(b'HTTP/1.1 200 OK\r\nTask-Id: own-task\r\nConnection: close\r\n\r\n')
        self.client.trust.wrap.return_value=connection
        response=request(self.client,'PUT','/import',{'task_id':'own-task'},io.BytesIO(b'data'),4)
        try: self.assertEqual(list(response.chunks()),[])
        finally: response.close()
        self.assertEqual(connection.sendall.call_args_list[1].args,(b'data',))

    @patch('flagship.httpstream.socket.create_connection')
    def test_mismatched_early_200_cannot_receive_archive(self,connect):
        connection=self.connection(b'HTTP/1.1 200 OK\r\nTask-Id: other-task\r\n\r\n')
        self.client.trust.wrap.return_value=connection
        source=io.BytesIO(b'data')
        with self.assertRaises(TransferError): request(self.client,'PUT','/import',{'task_id':'own-task'},source,4)
        self.assertEqual(source.tell(),0)
        self.assertEqual(connection.sendall.call_count,1)

    @patch('flagship.httpstream.socket.create_connection')
    def test_tls_failure_prevents_cookie_or_upload_send(self, connect):
        self.client.trust.wrap.side_effect = ssl.SSLCertVerificationError('untrusted')
        with self.assertRaises(ssl.SSLCertVerificationError):
            request(self.client, 'GET', '/export', {})
        connect.return_value.sendall.assert_not_called()
        connect.return_value.close.assert_called_once()

    @patch('flagship.httpstream.socket.create_connection')
    def test_upload_waits_for_continue_and_checks_source_length(self, connect):
        for reply, source in ((b'HTTP/1.1 417 Refused\r\n\r\n', io.BytesIO(b'data')),
                              (b'HTTP/1.1 200 OK\r\n\r\n', io.BytesIO(b'data')),
                              (b'HTTP/1.1 100 Continue\r\n\r\n', io.BytesIO(b''))):
            connection = self.connection(reply)
            self.client.trust.wrap.return_value = connection
            with self.assertRaises(TransferError):
                request(self.client, 'PUT', '/import', {}, source, 4)
            self.assertEqual(connection.sendall.call_count, 1)

    def test_ambiguous_truncated_and_malformed_body_framing_is_refused(self):
        for headers, data in (({'content-length':'5'}, b'ab'),
                              ({'content-length':'-1'}, b''),
                              ({'content-length':'2','transfer-encoding':'chunked'}, b''),
                              ({'transfer-encoding':'chunked'}, b'zzz\r\n'),
                              ({'transfer-encoding':'chunked'}, b'3\r\nabcNO'),
                              ({'transfer-encoding':'chunked'}, b'0\r\n'),
                              ({'content-encoding':'gzip'}, b'compressed')):
            response = Response(self.connection(data));response.headers=headers
            try:
                with self.assertRaises(TransferError): list(response.chunks())
            finally: response.close()

    @patch('flagship.httpstream.socket.create_connection')
    def test_duplicate_lengths_and_oversized_headers_are_rejected(self, connect):
        for reply in (b'HTTP/1.1 200 OK\r\nContent-Length: 1\r\nContent-Length: 1\r\n\r\n',
                      b'HTTP/1.1 200 OK\r\nHeader: '+b'x'*5000+b'\r\n\r\n'):
            self.client.trust.wrap.return_value = self.connection(reply)
            with self.assertRaises(TransferError): request(self.client, 'GET', '/export', {})


if __name__ == '__main__': unittest.main()

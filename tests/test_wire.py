"""Exercise actual HTTPS XML-RPC, envelope decoding and certificate trust."""
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import threading
import unittest
from xmlrpc.server import SimpleXMLRPCServer
from xenadmin_rocky.api import Client, APIError


@unittest.skipUnless(shutil.which('openssl'), 'openssl is required for ephemeral test certificates')
class WireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.cert = Path(cls.temp.name) / 'cert.pem'
        key = Path(cls.temp.name) / 'key.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-days', '1', '-keyout', str(key), '-out', str(cls.cert),
                        '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost'],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.server = SimpleXMLRPCServer(('127.0.0.1', 0), logRequests=False, allow_none=True)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(cls.cert), str(key))
        cls.server.socket = context.wrap_socket(cls.server.socket, server_side=True)
        cls.calls = []
        def dispatch(method, args):
            cls.calls.append((method, args))
            if method == 'session.login_with_password':
                return {'Status': 'Success', 'Value': 'test-session'}
            if method == 'session.logout':
                return {'Status': 'Success', 'Value': ''}
            if method == 'Async.VM.start':
                return {'Status': 'Failure', 'ErrorDescription': ['VM_BAD_POWER_STATE', 'vm']}
            return {'Status': 'Success', 'Value': {'vm': {'name_label': 'Wire guest'}}}
        cls.server.register_instance(type('Dispatcher', (), {'_dispatch': staticmethod(dispatch)})())
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def test_trusted_wire_login_inventory_and_logout(self):
        client = Client('https://localhost:' + str(self.port), str(self.cert))
        client.login('test-user', 'test-only-password')
        records = client.call('VM.get_all_records')
        self.assertEqual(records['vm']['name_label'], 'Wire guest')
        self.assertIn(('VM.get_all_records', ('test-session',)), self.calls)
        client.logout()
        self.assertIsNone(client.session)

    def test_untrusted_certificate_rejected(self):
        client = Client('https://localhost:' + str(self.port))
        with self.assertRaises(ssl.SSLCertVerificationError):
            client.login('test-user', 'test-only-password')

    def test_wrong_hostname_rejected_even_with_trusted_ca(self):
        client = Client('https://127.0.0.1:' + str(self.port), str(self.cert))
        with self.assertRaises(ssl.SSLCertVerificationError):
            client.login('test-user', 'test-only-password')

    def test_real_wire_api_error_is_not_success(self):
        client = Client('https://localhost:' + str(self.port), str(self.cert))
        client.login('test-user', 'test-only-password')
        with self.assertRaises(APIError) as caught:
            client.vm_action('vm', 'start', False, False)
        self.assertEqual(str(caught.exception), 'VM_BAD_POWER_STATE')
        client.logout()

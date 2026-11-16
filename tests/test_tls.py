"""Self-signed certificate handling against real TLS servers on 127.0.0.1 only."""
import hashlib
import os
from pathlib import Path
import shutil
import socket
import ssl
import stat
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from xmlrpc.server import SimpleXMLRPCServer

from flagship import tls
from flagship.api import Client
from flagship.console import open_console
from flagship.tls import (CertificateChanged, CertificateUntrusted, KnownCerts, TrustPolicy,
                          fingerprint, host_key, normalize_fingerprint)


def make_cert(directory, name, cn='localhost', san='DNS:localhost'):
    cert, key = Path(directory) / (name + '.pem'), Path(directory) / (name + '.key')
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '2',
                    '-keyout', str(key), '-out', str(cert), '-subj', '/O=Flagship test/CN=' + cn,
                    '-addext', 'subjectAltName=' + san],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    der = ssl.PEM_cert_to_DER_cert(cert.read_text())
    return cert, key, fingerprint(der)


@unittest.skipUnless(shutil.which('openssl'), 'openssl is required for ephemeral test certificates')
class XmlRpcTrustTests(unittest.TestCase):
    """XML-RPC transport: verify failure, pin accept, pin mismatch reject, insecure accept."""

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.cert, key, cls.fp = make_cert(cls.temp.name, 'server')
        _, _, cls.other_fp = make_cert(cls.temp.name, 'other')
        cls.server = SimpleXMLRPCServer(('127.0.0.1', 0), logRequests=False, allow_none=True)
        # Clients that refuse the certificate hang up after the handshake; that is expected.
        cls.server.handle_error = lambda request, address: None
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(cls.cert), str(key))
        cls.server.socket = context.wrap_socket(cls.server.socket, server_side=True)
        cls.calls = []
        def dispatch(method, args):
            cls.calls.append((method, args))
            if method == 'session.login_with_password':
                return {'Status': 'Success', 'Value': 'test-session'}
            return {'Status': 'Success', 'Value': ''}
        cls.server.register_instance(type('D', (), {'_dispatch': staticmethod(dispatch)})())
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def setUp(self):
        self.calls.clear()
        self.store_dir = tempfile.TemporaryDirectory()
        self.known = KnownCerts(Path(self.store_dir.name) / 'flagship' / 'known_certs.json')

    def tearDown(self):
        self.store_dir.cleanup()

    def url(self, host='localhost'):
        return 'https://%s:%d' % (host, self.port)

    def test_default_still_verifies_and_reports_certificate(self):
        client = Client(self.url(), known=self.known)
        self.assertEqual(client.tls_mode, tls.MODE_VERIFY)
        with self.assertRaises(CertificateUntrusted) as caught:
            client.login('root', 'test-only-password')
        self.assertIsInstance(caught.exception, ssl.SSLCertVerificationError)
        info = caught.exception.info
        self.assertEqual(info.sha256, self.fp)
        self.assertEqual(info.key, host_key('localhost', self.port))
        self.assertTrue(info.self_signed)
        self.assertIn('CN=localhost', info.subject)
        self.assertEqual(info.subject, info.issuer)
        self.assertTrue(info.not_before and info.not_after)
        self.assertIn('localhost', info.names)
        self.assertTrue(any('self-signed' in p for p in info.problems()))
        self.assertEqual(self.calls, [])  # no credentials reached the server

    def test_ca_pem_option_still_works(self):
        client = Client(self.url(), str(self.cert))
        client.login('root', 'test-only-password')
        self.assertEqual(client.tls_mode, tls.MODE_VERIFY)

    def test_session_pin_accepts_self_signed(self):
        client = Client(self.url(), pins={host_key('localhost', self.port): self.fp.upper()})
        self.assertEqual(client.tls_mode, tls.MODE_PINNED)
        client.login('root', 'test-only-password')
        self.assertEqual(client.session, 'test-session')

    def test_pin_accepts_hostname_mismatch(self):
        # Certificate names localhost only; connecting by IP fails verification...
        with self.assertRaises(CertificateUntrusted) as caught:
            Client(self.url('127.0.0.1'), str(self.cert)).login('root', 'x')
        self.assertFalse(caught.exception.info.name_ok)
        self.assertTrue(any('does not match' in p for p in caught.exception.info.problems()))
        # ...but is accepted once the fingerprint is pinned for 127.0.0.1.
        self.known.remember(caught.exception.info)
        client = Client(self.url('127.0.0.1'), known=self.known)
        client.login('root', 'test-only-password')
        self.assertEqual(client.session, 'test-session')

    def test_saved_pin_accepts_and_file_is_private(self):
        with self.assertRaises(CertificateUntrusted) as caught:
            Client(self.url(), known=self.known).login('root', 'x')
        self.known.remember(caught.exception.info)
        mode = stat.S_IMODE(os.stat(self.known.path).st_mode)
        self.assertEqual(mode, 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(self.known.path.parent).st_mode), 0o700)
        self.assertEqual(self.known.get('localhost', self.port), self.fp)
        client = Client(self.url(), known=self.known)
        client.login('root', 'test-only-password')
        self.assertEqual(client.session, 'test-session')
        self.assertTrue(self.known.forget(host_key('localhost', self.port)))
        self.assertEqual(self.known.get('localhost', self.port), '')

    def test_changed_certificate_is_refused_before_credentials(self):
        client = Client(self.url(), pins={host_key('localhost', self.port): self.other_fp})
        with self.assertRaises(CertificateChanged) as caught:
            client.login('root', 'test-only-password')
        self.assertEqual(caught.exception.pinned, self.other_fp)
        self.assertEqual(caught.exception.info.sha256, self.fp)
        self.assertEqual(self.calls, [])

    def test_changed_saved_pin_is_refused_even_with_valid_ca(self):
        info = tls.CertInfo('localhost', self.port, ssl.PEM_cert_to_DER_cert(self.cert.read_text()))
        info.sha256 = self.other_fp
        self.known.remember(info)
        with self.assertRaises(CertificateChanged):
            Client(self.url(), str(self.cert), known=self.known).login('root', 'x')
        self.assertEqual(self.calls, [])

    def test_insecure_accepts_without_any_pin(self):
        client = Client(self.url('127.0.0.1'), insecure=True, known=self.known)
        self.assertTrue(client.insecure)
        client.login('root', 'test-only-password')
        self.assertEqual(client.session, 'test-session')
        self.assertEqual(self.known.load(), {})

    def test_fetch_certificate_reads_leaf(self):
        info = tls.fetch_certificate('127.0.0.1', self.port)
        self.assertEqual(info.sha256, self.fp)

    def test_stdlib_fallback_parser(self):
        info = tls.CertInfo.__new__(tls.CertInfo)
        info.host, info.port, info.der = 'localhost', self.port, ssl.PEM_cert_to_DER_cert(self.cert.read_text())
        info.subject = info.issuer = info.not_before = info.not_after = ''
        info.names, info.self_signed, info.expired = [], False, False
        tls._describe_stdlib(info)
        if not hasattr(ssl._ssl, '_test_decode_cert'):
            self.skipTest('CPython test decoder unavailable')
        self.assertIn('CN=localhost', info.subject)
        self.assertTrue(info.self_signed)
        self.assertIn('localhost', info.names)
        self.assertTrue(info.not_after)


class ConsoleServer:
    """Plain TLS listener that records every byte it receives."""

    def __init__(self, cert, key):
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(str(cert), str(key))
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(4)
        self.port = self.listener.getsockname()[1]
        self.received = b''
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        while True:
            try:
                raw, _ = self.listener.accept()
            except OSError:
                return
            try:
                with self.context.wrap_socket(raw, server_side=True) as conn:
                    conn.settimeout(5)
                    data = b''
                    while b'\r\n\r\n' not in data:
                        chunk = conn.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                    self.received += data
                    if data:
                        conn.sendall(b'HTTP/1.1 200 OK\r\n\r\nRFB 003.008\n')
            except (OSError, ssl.SSLError):
                pass

    def close(self):
        self.listener.close()


@unittest.skipUnless(shutil.which('openssl'), 'openssl is required for ephemeral test certificates')
class ConsoleTrustTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cert, key, cls.fp = make_cert(cls.temp.name, 'member', cn='member', san='DNS:member')
        _, _, cls.other_fp = make_cert(cls.temp.name, 'other')
        cls.server = ConsoleServer(cert, key)

    @classmethod
    def tearDownClass(cls):
        cls.server.close()
        cls.temp.cleanup()

    def setUp(self):
        self.server.received = b''

    def client(self, policy):
        client = Mock()
        client.session = 'private-session'
        client.trust = policy
        return client

    def open(self, policy):
        target = ('127.0.0.1', self.server.port, '/console?ref=c')
        with patch('flagship.console.console_target', return_value=target):
            return open_console(self.client(policy), 'vm', timeout=5)

    def test_console_verify_failure_sends_nothing(self):
        with self.assertRaises(CertificateUntrusted):
            self.open(TrustPolicy())
        self.assertEqual(self.server.received, b'')

    def test_console_pin_accept(self):
        tunnel = self.open(TrustPolicy(pins={host_key('127.0.0.1', self.server.port): self.fp}))
        self.assertEqual(tunnel.read(12), b'RFB 003.008\n')
        tunnel.close()
        self.assertIn(b'Cookie: session_id=private-session', self.server.received)

    def test_console_pin_mismatch_never_sends_session(self):
        with self.assertRaises(CertificateChanged):
            self.open(TrustPolicy(pins={host_key('127.0.0.1', self.server.port): self.other_fp}))
        self.assertNotIn(b'private-session', self.server.received)

    def test_console_insecure_accept(self):
        tunnel = self.open(TrustPolicy(insecure=True))
        self.assertEqual(tunnel.read(12), b'RFB 003.008\n')
        tunnel.close()


class FingerprintTests(unittest.TestCase):
    def test_normalize_forms(self):
        digest = hashlib.sha256(b'x').hexdigest()
        canonical = ':'.join(digest[i:i + 2] for i in range(0, 64, 2))
        for value in (digest, digest.upper(), canonical.upper(), 'sha256:' + digest, ' ' + canonical + ' '):
            self.assertEqual(normalize_fingerprint(value), canonical)
        for bad in ('', 'abc', digest[:-2] + 'zz', digest + '00'):
            with self.assertRaises(ValueError):
                normalize_fingerprint(bad)

    def test_host_keys_and_names(self):
        self.assertEqual(host_key('XCP.Example.', None), 'xcp.example:443')
        self.assertEqual(host_key('::1', 8443), '[::1]:8443')
        self.assertTrue(tls.name_matches('*.example.test', 'xcp1.example.test'))
        self.assertFalse(tls.name_matches('*.example.test', 'example.test'))
        self.assertTrue(tls.name_matches('127.0.0.1', '127.0.0.1'))
        self.assertFalse(tls.name_matches('localhost', '127.0.0.1'))

    def test_store_ignores_corrupt_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'known_certs.json'
            path.write_text('{not json')
            self.assertEqual(KnownCerts(path).load(), {})

    def test_default_store_location_follows_xdg(self):
        with patch.dict(os.environ, {'XDG_CONFIG_HOME': '/tmp/xdg-test'}):
            self.assertEqual(str(tls.known_certs_path()), '/tmp/xdg-test/flagship/known_certs.json')


class RecoveryFlagTests(unittest.TestCase):
    def args(self, **overrides):
        values = dict(endpoint='https://localhost:8443', ca_file=None, pin=None, insecure=False, no_saved_pins=True)
        values.update(overrides)
        return Mock(**values)

    def test_insecure_and_pin_flags(self):
        from flagship.recovery import make_client
        self.assertEqual(make_client(self.args(insecure=True)).tls_mode, tls.MODE_INSECURE)
        digest = 'ab' * 32
        client = make_client(self.args(pin=digest))
        self.assertEqual(client.tls_mode, tls.MODE_PINNED)
        self.assertEqual(client.trust.pinned('localhost', 8443), ':'.join(['ab'] * 32))
        self.assertEqual(make_client(self.args()).tls_mode, tls.MODE_VERIFY)
        with self.assertRaises(ValueError):
            make_client(self.args(pin='nope'))


if __name__ == '__main__':
    unittest.main()

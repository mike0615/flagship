"""Trust dialog, insecure checkbox and status indicator with a real Tk interpreter."""
import os
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from flagship import tls
from flagship.app import Application
from flagship.tls import CertificateChanged, CertificateUntrusted, KnownCerts


def sample_info():
    info = tls.CertInfo.__new__(tls.CertInfo)
    info.host, info.port, info.der = 'xcp-ng.example.test', 443, b''
    info.sha256 = ':'.join(['ab'] * 32)
    info.subject = info.issuer = 'CN=xcp-ng.example.test'
    info.names = ['xcp-ng.example.test']
    info.not_before, info.not_after = '2026-01-01 00:00 EST', '2036-01-01 00:00 EST'
    info.self_signed, info.expired, info.verify_error = True, False, 'self-signed certificate'
    return info


@unittest.skipUnless(os.environ.get('DISPLAY'), 'requires X display (use xvfb-run)')
class TrustGuiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.known = KnownCerts(Path(self.temp.name) / 'known_certs.json')
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = Application(self.root, known=self.known)

    def tearDown(self):
        self.app.jobs.shutdown(wait=True)
        self.root.destroy()
        self.temp.cleanup()

    def test_trust_dialog_buttons_and_fields(self):
        from flagship.trust_dialog import TrustDialog
        dialog = TrustDialog(self.root, sample_info(), wait=False)
        self.assertEqual(dialog.once_button.cget('text'), 'Connect once')
        self.assertEqual(dialog.always_button.cget('text'), 'Always trust this certificate')
        self.assertEqual(dialog.cancel_button.cget('text'), 'Cancel')
        self.assertIn('AB:AB', dialog.fields['SHA-256'].cget('text'))
        self.assertIn('2036', dialog.fields['Valid until'].cget('text'))
        dialog.choose('always')
        self.assertEqual(dialog.result, 'always')

    def test_changed_dialog_shows_previous_fingerprint(self):
        from flagship.trust_dialog import TrustDialog
        dialog = TrustDialog(self.root, sample_info(), changed=True, old_fingerprint=':'.join(['cd'] * 32), wait=False)
        self.assertIn('changed', dialog.window.title())
        self.assertIn('CD:CD', dialog.fields['Previously trusted'].cget('text'))
        dialog.cancel()
        self.assertIsNone(dialog.result)

    def test_connect_dialog_has_insecure_checkbox_and_warning(self):
        dialog = self.app.connect()
        self.assertEqual(dialog.insecure_check.cget('text'), 'Ignore SSL certificate errors (insecure)')
        self.assertFalse(dialog.insecure.get())
        self.assertFalse(dialog.insecure_warning.winfo_ismapped() or dialog.insecure_warning.grid_info())
        dialog.insecure_check.invoke()
        self.assertTrue(dialog.insecure.get())
        self.assertTrue(dialog.insecure_warning.grid_info())
        self.assertIn('CA PEM file (optional)', dialog.fields)
        dialog.destroy()

    def test_insecure_checkbox_reaches_client(self):
        with patch('flagship.app.Client') as client_class:
            self.app.start_connect('https://127.0.0.1', 'root', 'pw', None, True)
            self.app.jobs.submit(lambda: None).result()
            self.assertTrue(client_class.call_args.kwargs['insecure'])
            self.assertIs(client_class.call_args.kwargs['known'], self.known)

    def test_status_bar_indicator(self):
        self.app.client = Mock(tls_mode=tls.MODE_INSECURE)
        self.app.update_tls_indicator()
        self.assertEqual(self.app.tls_indicator.cget('text'), '\u26a0 Insecure TLS')
        self.app.client = Mock(tls_mode=tls.MODE_VERIFY)
        self.app.update_tls_indicator()
        self.assertEqual(self.app.tls_indicator.cget('text'), '')

    def _deliver(self, result):
        """Run a connect 'done' callback as poll() would."""
        done = {}
        def fake_submit(work, callback, label, **_kw):
            done['cb'] = callback
        with patch.object(self.app, 'submit', side_effect=fake_submit):
            self.app.start_connect('https://xcp-ng.example.test', 'root', 'pw')
        return done['cb']

    def test_always_trust_saves_pin_and_retries_with_it(self):
        callback = self._deliver(None)
        exc = CertificateUntrusted(sample_info(), 'self-signed certificate')
        with patch.object(self.app, 'ask_trust', return_value='always'), \
                patch.object(self.app, 'start_connect') as retry:
            callback(('certificate', exc))
        self.assertEqual(self.known.get('xcp-ng.example.test', 443), ':'.join(['ab'] * 32))
        self.assertEqual(retry.call_args.args[5], {'xcp-ng.example.test:443': ':'.join(['ab'] * 32)})

    def test_connect_once_does_not_save(self):
        callback = self._deliver(None)
        exc = CertificateChanged(sample_info(), ':'.join(['cd'] * 32))
        with patch.object(self.app, 'ask_trust', return_value='once'), \
                patch.object(self.app, 'start_connect') as retry:
            callback(('certificate', exc))
        self.assertEqual(self.known.load(), {})
        retry.assert_called_once()

    def test_cancel_does_not_connect(self):
        callback = self._deliver(None)
        exc = CertificateChanged(sample_info(), ':'.join(['cd'] * 32))
        with patch.object(self.app, 'ask_trust', return_value=None), \
                patch.object(self.app, 'start_connect') as retry:
            callback(('certificate', exc))
        retry.assert_not_called()
        self.assertIsNone(self.app.client)
        self.assertIn('not trusted', self.app.status.get())


if __name__ == '__main__':
    unittest.main()

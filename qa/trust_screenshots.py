#!/usr/bin/env python3
"""Screenshots of the certificate trust dialog and the insecure-TLS checkbox.

Runs a throwaway TLS listener with a fresh self-signed certificate on
127.0.0.1 only; never contacts a pool. Intended for xvfb-run.
"""
from __future__ import annotations

import socket
import ssl
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'qa'))

import tkinter as tk  # noqa: E402
from smoke_screenshots import grab_window, _pump  # noqa: E402
from flagship import tls  # noqa: E402
from flagship.app import Application  # noqa: E402
from flagship.trust_dialog import TrustDialog  # noqa: E402


def local_server(directory):
    cert, key = Path(directory) / 'xcp.pem', Path(directory) / 'xcp.key'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '3650',
                    '-keyout', str(key), '-out', str(cert), '-subj', '/C=US/O=XCP-ng test/CN=xcp-host-01',
                    '-addext', 'subjectAltName=DNS:xcp-host-01'],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert), str(key))
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(2)
    def serve():
        while True:
            try:
                raw, _ = listener.accept()
                context.wrap_socket(raw, server_side=True).close()
            except OSError:
                if listener.fileno() < 0:
                    return
    threading.Thread(target=serve, daemon=True).start()
    return listener


def main() -> int:
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'docs' / 'screenshots'
    dest.mkdir(parents=True, exist_ok=True)
    temp = tempfile.TemporaryDirectory()
    listener = local_server(temp.name)
    info = tls.fetch_certificate('127.0.0.1', listener.getsockname()[1])
    info.verify_error = 'self-signed certificate'
    root = tk.Tk()
    root.geometry('1100x720+20+20')
    app = Application(root, known=tls.KnownCerts(Path(temp.name) / 'known.json'))
    _pump(root, 0.6)
    written = []

    dialog = app.connect()
    dialog.geometry('+60+60')
    dialog.fields['Endpoint'].delete(0, 'end')
    dialog.fields['Endpoint'].insert(0, 'https://xcp-host-01.lab.example')
    dialog.insecure_check.invoke()
    _pump(root, 0.8)
    written.append(dest / 'connect-insecure-checkbox.png')
    grab_window(int(dialog.winfo_id()), written[-1])
    dialog.destroy()

    for name, kwargs in (('trust-certificate.png', {}),
                         ('trust-certificate-changed.png', {'changed': True, 'old_fingerprint': ':'.join(['5a'] * 32)})):
        trust = TrustDialog(root, info, wait=False, **kwargs)
        trust.window.geometry('+60+60')
        _pump(root, 0.8)
        written.append(dest / name)
        grab_window(int(trust.window.winfo_id()), written[-1])
        trust.window.destroy()

    app.client = Mock(tls_mode=tls.MODE_INSECURE, endpoint='https://xcp-host-01.lab.example')
    app.status.set('Connected to https://xcp-host-01.lab.example. Inventory up to date.')
    app.update_tls_indicator()
    _pump(root, 0.8)
    written.append(dest / 'status-insecure-tls.png')
    grab_window(int(root.winfo_id()), written[-1])
    app.client = None
    app.jobs.shutdown(wait=False)
    root.destroy()
    listener.close()
    temp.cleanup()
    for path in written:
        print('WROTE', path, path.stat().st_size, 'bytes')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

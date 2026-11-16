"""Certificate trust for XAPI connections: verified by default, optional pins.

Three ways to reach a host whose certificate the system does not trust
(typically the self-signed certificate an XCP-ng host makes at install):

  * Verified (default): system CA store, or only the CA PEM file you give,
    plus host name checking. Nothing changes for properly signed hosts.
  * Pinned: you looked at the certificate and chose "Connect once" or
    "Always trust this certificate". The handshake runs without CA checks,
    then the SHA-256 fingerprint of the presented certificate is compared to
    the pin BEFORE any byte (credentials, session cookie) is sent. A
    different certificate is refused; it is never accepted silently.
  * Insecure: "Ignore SSL certificate errors". No verification at all, for
    that connection only.

"Always trust" pins live in ~/.config/flagship/known_certs.json (0600, in a
0700 directory), keyed by host:port. Standard library only; the optional
python3-cryptography module gives richer certificate details when present.
"""
from __future__ import annotations

import datetime
import hashlib
import ipaddress
import json
import os
import re
import socket
import ssl
import tempfile
import threading
from pathlib import Path

MODE_VERIFY, MODE_PINNED, MODE_INSECURE = 'verified', 'pinned', 'insecure'


def host_key(host, port):
    host = (host or '').lower().rstrip('.')
    if ':' in host and not host.startswith('['):
        host = '[' + host + ']'
    return '%s:%d' % (host, int(port or 443))


def fingerprint(der):
    """Lower-case colon-separated SHA-256 of a DER certificate."""
    digest = hashlib.sha256(der).hexdigest()
    return ':'.join(digest[i:i + 2] for i in range(0, len(digest), 2))


def normalize_fingerprint(value):
    """Accept AA:BB.., aabb.. or 'sha256:' prefixed input; return canonical form."""
    text = (value or '').strip().lower()
    text = text.removeprefix('sha256:').removeprefix('sha256/')
    hexdigits = re.sub(r'[:\s-]', '', text)
    if not re.fullmatch(r'[0-9a-f]{64}', hexdigits):
        raise ValueError('A SHA-256 fingerprint has 64 hexadecimal digits')
    return ':'.join(hexdigits[i:i + 2] for i in range(0, 64, 2))


def display_fingerprint(fp):
    """Upper case in two lines of 16 bytes, easy to compare by eye."""
    parts = (fp or '').upper().split(':')
    return ':'.join(parts[:16]) + ('\n' + ':'.join(parts[16:]) if len(parts) > 16 else '')


def is_ip(host):
    try:
        ipaddress.ip_address((host or '').strip('[]'))
        return True
    except ValueError:
        return False


def name_matches(pattern, host):
    pattern, host = pattern.lower().rstrip('.'), host.lower().rstrip('.').strip('[]')
    if pattern == host:
        return True
    if is_ip(host) or is_ip(pattern):
        try:
            return ipaddress.ip_address(pattern) == ipaddress.ip_address(host)
        except ValueError:
            return False
    return pattern.startswith('*.') and '.' in host and host.split('.', 1)[1] == pattern[2:]


class CertInfo:
    """What the dialog shows about the certificate a server presented."""

    def __init__(self, host, port, der):
        self.host, self.port, self.der = host, int(port or 443), der
        self.sha256 = fingerprint(der)
        self.subject = self.issuer = self.not_before = self.not_after = ''
        self.names = []
        self.self_signed = False
        self.expired = False
        self.verify_error = ''
        _describe(self)

    @property
    def key(self):
        return host_key(self.host, self.port)

    @property
    def name_ok(self):
        return any(name_matches(n, self.host) for n in self.names)

    def problems(self):
        out = []
        if self.self_signed:
            out.append('The certificate is self-signed, so no trusted certifying authority vouches for it.')
        else:
            out.append('The certificate is not from a certifying authority this computer trusts.')
        if self.names and not self.name_ok:
            out.append('The name in the certificate (%s) does not match the host you are connecting to (%s).'
                       % (', '.join(self.names), self.host))
        if self.expired:
            out.append('The certificate has expired or is not yet valid.')
        return out


def _fmt_time(value):
    return value.astimezone().strftime('%Y-%m-%d %H:%M %Z')


def _describe(info):
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        cert = x509.load_der_x509_certificate(info.der)
    except Exception:  # module absent (it is optional) or unparsable
        _describe_stdlib(info)
        return
    info.subject = cert.subject.rfc4514_string()
    info.issuer = cert.issuer.rfc4514_string()
    info.self_signed = cert.subject == cert.issuer
    names = [a.value for a in cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)]
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        names += san.get_values_for_type(x509.DNSName)
        names += [str(ip) for ip in san.get_values_for_type(x509.IPAddress)]
    except x509.ExtensionNotFound:
        pass
    info.names = list(dict.fromkeys(str(n) for n in names))
    utc = datetime.timezone.utc
    before = getattr(cert, 'not_valid_before_utc', None) or cert.not_valid_before.replace(tzinfo=utc)
    after = getattr(cert, 'not_valid_after_utc', None) or cert.not_valid_after.replace(tzinfo=utc)
    info.expired = not before <= datetime.datetime.now(utc) <= after
    info.not_before, info.not_after = _fmt_time(before), _fmt_time(after)


def _describe_stdlib(info):
    """Fallback parser (CPython's own test decoder) when cryptography is missing."""
    decode = getattr(getattr(ssl, '_ssl', None), '_test_decode_cert', None)
    if decode is None:
        return
    fd, path = tempfile.mkstemp(suffix='.pem')
    try:
        with os.fdopen(fd, 'w') as handle:
            handle.write(ssl.DER_cert_to_PEM_cert(info.der))
        decoded = decode(path)
    except Exception:
        return
    finally:
        os.unlink(path)
    short = {'commonName': 'CN', 'organizationName': 'O', 'organizationalUnitName': 'OU',
             'countryName': 'C', 'stateOrProvinceName': 'ST', 'localityName': 'L'}
    def flat(rdns):
        return ','.join('%s=%s' % (short.get(k, k), v) for rdn in reversed(rdns) for k, v in rdn)
    subject, issuer = decoded.get('subject', ()), decoded.get('issuer', ())
    info.subject, info.issuer = flat(subject), flat(issuer)
    info.self_signed = subject == issuer
    names = [value for rdn in subject for key, value in rdn if key == 'commonName']
    names += [value for kind, value in decoded.get('subjectAltName', ()) if kind in ('DNS', 'IP Address')]
    info.names = list(dict.fromkeys(n.strip() for n in names))
    utc = datetime.timezone.utc
    try:
        before = datetime.datetime.fromtimestamp(ssl.cert_time_to_seconds(decoded['notBefore']), utc)
        after = datetime.datetime.fromtimestamp(ssl.cert_time_to_seconds(decoded['notAfter']), utc)
    except (KeyError, ValueError):
        return
    info.expired = not before <= datetime.datetime.now(utc) <= after
    info.not_before, info.not_after = _fmt_time(before), _fmt_time(after)


class CertificateError(ssl.SSLCertVerificationError):
    """Base for trust decisions the user can resolve in the trust dialog.

    Subclasses SSLCertVerificationError so callers that already treat a
    verification failure as fatal keep doing so."""

    def __init__(self, info, message):
        super().__init__(message)
        self.info = info
        self.verify_message = message

    def __str__(self):
        return self.args[0] if self.args else type(self).__name__


class CertificateUntrusted(CertificateError):
    """Verification failed (self-signed, unknown CA, name mismatch, expired)."""

    def __init__(self, info, reason=''):
        info.verify_error = reason
        super().__init__(info, 'The certificate of %s is not trusted%s' % (info.key, (': ' + reason) if reason else ''))


class CertificateChanged(CertificateError):
    """A pinned host presented a different certificate. Never accepted silently."""

    def __init__(self, info, pinned):
        super().__init__(info, 'The certificate of %s has changed since you trusted it' % info.key)
        self.pinned = pinned


def insecure_context():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def fetch_certificate(host, port=443, timeout=15):
    """Read the leaf certificate without trusting it (for display only)."""
    with socket.create_connection((host, int(port or 443)), timeout=timeout) as raw:
        with insecure_context().wrap_socket(raw, server_hostname=None if is_ip(host) else host) as tls:
            return CertInfo(host, port, tls.getpeercert(binary_form=True))


def known_certs_path():
    base = os.environ.get('XDG_CONFIG_HOME', '')
    base = Path(base) if base and Path(base).is_absolute() else Path.home() / '.config'
    return base / 'flagship' / 'known_certs.json'


class KnownCerts:
    """"Always trust this certificate" pins, host:port -> SHA-256, file mode 0600."""

    def __init__(self, path=None):
        self.path = Path(path) if path else known_certs_path()
        self.lock = threading.Lock()

    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}
        return {k: v for k, v in data.items() if isinstance(v, dict) and isinstance(v.get('sha256'), str)} \
            if isinstance(data, dict) else {}

    def get(self, host, port):
        entry = self.load().get(host_key(host, port))
        return entry['sha256'] if entry else ''

    def _save(self, data):
        directory = self.path.parent
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        payload = (json.dumps(data, indent=2, sort_keys=True) + '\n').encode('utf-8')
        fd, temp = tempfile.mkstemp(prefix='.known_certs.', dir=str(directory))
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'wb') as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self.path)
        except BaseException:
            try: os.unlink(temp)
            except OSError: pass
            raise
        os.chmod(self.path, 0o600)

    def remember(self, info):
        with self.lock:
            data = self.load()
            data[info.key] = {
                'sha256': info.sha256, 'subject': info.subject, 'issuer': info.issuer,
                'not_after': info.not_after,
                'trusted': datetime.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')}
            self._save(data)

    def forget(self, key):
        with self.lock:
            data = self.load()
            if data.pop(key, None) is not None:
                self._save(data)
                return True
            return False


class TrustPolicy:
    """Per-connection decision: which SSL context to use and what to check after the handshake."""

    def __init__(self, ca_file=None, insecure=False, pins=None, known=None):
        self.ca_file = ca_file or None
        self.insecure = bool(insecure)
        self.pins = {}  # session ("Connect once") pins, host:port -> sha256
        for key, value in (pins or {}).items():
            self.pins[key] = normalize_fingerprint(value)
        self.known = known
        self._verified = None

    def pinned(self, host, port):
        key = host_key(host, port)
        if key in self.pins:
            return self.pins[key]
        return self.known.get(host, port) if self.known is not None else ''

    def mode(self, host, port):
        if self.insecure:
            return MODE_INSECURE
        return MODE_PINNED if self.pinned(host, port) else MODE_VERIFY

    def verified_context(self):
        if self._verified is None:
            self._verified = ssl.create_default_context(cafile=self.ca_file)
        return self._verified

    def context(self, host, port):
        if self.mode(host, port) == MODE_VERIFY:
            return self.verified_context()
        # Pinned or insecure: no CA/name checks in OpenSSL; pins are checked in check().
        return insecure_context()

    def check(self, tls_socket, host, port):
        """Call right after the handshake, before sending anything."""
        if self.insecure:
            return
        pin = self.pinned(host, port)
        if not pin:
            return  # the verified context already authenticated the peer
        der = tls_socket.getpeercert(binary_form=True)
        if not der:
            raise CertificateUntrusted(CertInfo(host, port, b''), 'no certificate presented')
        if fingerprint(der) != pin:
            raise CertificateChanged(CertInfo(host, port, der), pin)

    def wrap(self, raw, host, port):
        """Wrap a connected TCP socket; raise CertificateUntrusted with details on verify failure."""
        try:
            tls = self.context(host, port).wrap_socket(raw, server_hostname=host)
        except ssl.SSLCertVerificationError as exc:
            raise untrusted_from(exc, host, port) from None
        try:
            self.check(tls, host, port)
        except Exception:
            tls.close()
            raise
        return tls

    def trust(self, info, always=False):
        """Accept the certificate in info for this session, and on disk if always."""
        self.pins[info.key] = info.sha256
        if always and self.known is not None:
            self.known.remember(info)


def untrusted_from(exc, host, port, timeout=15):
    """Turn a verification failure into CertificateUntrusted with the server's certificate."""
    reason = getattr(exc, 'verify_message', '') or str(exc)
    try:
        info = fetch_certificate(host, port, timeout)
    except OSError:
        raise exc
    return CertificateUntrusted(info, reason)

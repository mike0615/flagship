"""Bounded HTTPS XAPI transfers. Callers journal PUT intent and track server tasks.

Session cookies stay out of URLs. A PUT body is sent only after 100 Continue;
redirects are followed only before upload, to a freshly verified pool host.
"""
import re
import socket
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

BLOCK = 1024 * 1024


class TransferError(RuntimeError):
    pass


def head(reader):
    line = reader.readline(4097)
    match = re.fullmatch(rb'HTTP/1\.[01] ([0-9]{3})(?: [^\r\n]*)?\r\n', line)
    if not match: raise TransferError('Invalid transfer response status')
    total = len(line)
    headers = {}
    while True:
        line = reader.readline(4097)
        total += len(line)
        if line == b'\r\n': break
        if not line or len(line) > 4096 or total > 16384 or b':' not in line:
            raise TransferError('Invalid transfer response headers')
        key, value = line[:-2].split(b':', 1)
        if not line.endswith(b'\r\n') or not re.fullmatch(rb'[A-Za-z0-9-]+', key):
            raise TransferError('Invalid transfer response header')
        key = key.decode('ascii').lower()
        if key in headers and key in ('content-length', 'transfer-encoding', 'location'):
            raise TransferError('Ambiguous transfer response headers')
        headers[key] = value.strip().decode('latin1')
    return int(match[1]), headers


class Response:
    def __init__(self, connection):
        self.connection = connection
        self.reader = connection.makefile('rb')
        self.headers = {}

    def close(self):
        try: self.connection.shutdown(socket.SHUT_RDWR)
        except OSError: pass
        finally:
            self.reader.close()
            self.connection.close()

    def exact(self, count):
        block = self.reader.read(count)
        if len(block) != count: raise TransferError('Transfer ended before the expected data arrived')
        return block

    def chunks(self):
        encoding = self.headers.get('transfer-encoding', '').lower()
        length = self.headers.get('content-length')
        if encoding and length is not None:
            raise TransferError('Ambiguous transfer body framing')
        if self.headers.get('content-encoding', 'identity').lower() != 'identity':
            raise TransferError('Unsupported HTTP content encoding')
        if encoding:
            if encoding != 'chunked': raise TransferError('Unsupported transfer encoding')
            while True:
                line = self.reader.readline(4097)
                size = line.split(b';', 1)[0].strip()
                if len(line) > 4096 or not line.endswith(b'\r\n') or not re.fullmatch(rb'[0-9a-fA-F]{1,16}', size):
                    raise TransferError('Invalid transfer chunk size')
                remaining = int(size, 16)
                if remaining == 0:
                    total = 0
                    while True:
                        trailer = self.reader.readline(4097)
                        total += len(trailer)
                        if trailer == b'\r\n': return
                        if not trailer or len(trailer) > 4096 or total > 16384:
                            raise TransferError('Invalid transfer trailer')
                while remaining:
                    data = self.exact(min(BLOCK, remaining))
                    remaining -= len(data)
                    yield data
                if self.exact(2) != b'\r\n': raise TransferError('Invalid transfer chunk terminator')
        elif length is not None:
            if not re.fullmatch(r'[0-9]{1,19}', length): raise TransferError('Invalid transfer length')
            remaining = int(length)
            while remaining:
                data = self.exact(min(BLOCK, remaining))
                remaining -= len(data)
                yield data
        else:
            while True:
                data = self.reader.read(BLOCK)
                if not data: return
                yield data


def request(client, method, path, parameters, source=None, size=None,
            checkpoint=lambda: None, progress=lambda transferred: None, timeout=30):
    """Return a response owned by caller, who must close it and confirm its task."""
    if (method, path) not in (('GET', '/export'), ('PUT', '/import')):
        raise ValueError('Unsupported XAPI transfer operation')
    if method == 'PUT' and (source is None or not isinstance(size, int) or size <= 0):
        raise ValueError('Import requires a nonempty source with an exact byte length')
    if 'session_id' in parameters: raise ValueError('Use session cookies for authentication')
    session = client.session
    if not isinstance(session, str) or not re.fullmatch(r'[A-Za-z0-9:_-]+', session):
        raise TransferError('An authenticated session is required')
    endpoint = urlsplit(client.endpoint)
    hosts = {endpoint.hostname} | {r.get('address') for r in client.call('host.get_all_records').values()}
    query = {str(key): str(value) for key, value in parameters.items()}
    location = client.endpoint + path + '?' + urlencode(query)
    for attempt in range(4):
        checkpoint()
        target = urlsplit(location)
        allowed_port = (endpoint.port or 443) if target.hostname == endpoint.hostname else 443
        try: port = target.port or 443
        except ValueError: raise TransferError('Invalid transfer destination port') from None
        redirected_query = parse_qs(target.query, keep_blank_values=True)
        redirected_query.pop('session_id', None)  # Never forward a session in the redirected URI.
        if (target.scheme != 'https' or not target.hostname or target.hostname not in hosts or
                port != allowed_port or target.username or target.password or target.fragment or
                target.path != path or redirected_query != {k: [v] for k, v in query.items()}):
            raise TransferError('Transfer redirect is outside the selected pool operation')
        raw = socket.create_connection((target.hostname, port), timeout=timeout)
        try: connection = client.trust.wrap(raw, target.hostname, port)
        except Exception:
            raw.close()
            raise
        response = Response(connection)
        try:
            authority = '['+target.hostname+']' if ':' in target.hostname else target.hostname
            headers = (method+' '+path+'?'+urlencode(query)+' HTTP/1.1\r\nHost: '+authority+':'+str(port)+
                       '\r\nCookie: session_id='+session+'\r\nConnection: close\r\n')
            if method == 'PUT':
                headers += 'Content-Type: application/octet-stream\r\nContent-Length: '+str(size)+'\r\nExpect: 100-continue\r\n'
            connection.sendall((headers+'\r\n').encode('ascii'))
            status, fields = head(response.reader)
            if status in (301, 302, 303, 307, 308):
                if not fields.get('location') or attempt == 3:
                    raise TransferError('Transfer redirect limit exceeded')
                location = urljoin(location, fields['location'])
                response.close()
                continue
            if method == 'PUT':
                if status != 100:
                    raise TransferError('Host did not authorize the upload body')
                transferred = 0
                while transferred < size:
                    checkpoint()
                    block = source.read(min(BLOCK, size-transferred))
                    if not block or len(block) > size-transferred:
                        raise TransferError('Import source changed or ended prematurely')
                    connection.sendall(block)
                    transferred += len(block)
                    progress(transferred)
                status, fields = head(response.reader)
            if status != 200:
                raise TransferError('Host refused the transfer; inspect the associated task')
            response.headers = fields
            return response
        except Exception:
            response.close()
            raise
    raise TransferError('Transfer redirect limit exceeded')

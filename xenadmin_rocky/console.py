"""Authenticated XAPI console tunnels; no redirects, plaintext or credential URLs.

Protocol: https://xapi-project.github.io/xen-api/consoles.html
"""
import socket
import threading
from urllib.parse import parse_qs, urlsplit


class ConsoleError(RuntimeError):
    pass


class Tunnel:
    def __init__(self, connection):
        self.connection = connection
        self.reader = connection.makefile('rb')
        self.send_lock = threading.Lock()

    def read(self, size):
        if not 0 <= size <= 64 * 1024 * 1024:
            raise ConsoleError('Console message exceeds the supported size')
        result = self.reader.read(size)
        if len(result) != size:
            raise ConsoleError('Console connection closed')
        return result

    def send(self, data):
        with self.send_lock:
            self.connection.sendall(data)

    def close(self):
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        finally:
            self.reader.close()
            self.connection.close()


def console_target(client, vm_ref):
    """Resolve only a console belonging to the freshly selected VM and host."""
    vm = client.call('VM.get_record', vm_ref)
    if vm.get('power_state') not in ('Running', 'Paused'):
        raise ConsoleError('Start the VM before opening its console')
    host = client.call('host.get_record', vm['resident_on'])
    for ref in client.call('VM.get_consoles', vm_ref):
        record = client.call('console.get_record', ref)
        if record.get('VM') != vm_ref:
            raise ConsoleError('Console ownership changed; refresh the VM')
        if record.get('protocol') != 'rfb':
            continue
        location = urlsplit(record.get('location', ''))
        endpoint = urlsplit(client.endpoint)
        allowed_hosts = {endpoint.hostname, host.get('address')}
        try:
            port = location.port or 443
        except ValueError:
            raise ConsoleError('Invalid console port') from None
        allowed_port = (endpoint.port or 443) if location.hostname == endpoint.hostname else 443
        if (location.scheme != 'https' or location.hostname not in allowed_hosts or
                not location.hostname or port != allowed_port or location.username or
                location.password or location.fragment or location.path != '/console' or
                any(ord(c) < 33 or ord(c) > 126 for c in record['location'])):
            raise ConsoleError('Console URL is outside the verified pool host')
        query = parse_qs(location.query, keep_blank_values=True)
        if not (query == {'ref': [ref]} or query == {'uuid': [record.get('uuid')]}):
            raise ConsoleError('Console URL does not identify the selected console')
        return location.hostname, port, location.path + '?' + location.query
    raise ConsoleError('This VM has no graphical RFB console')


def open_console(client, vm_ref, timeout=30):
    hostname, port, target = console_target(client, vm_ref)
    session = client.session
    if not session or any(ord(c) < 33 or ord(c) > 126 or c in ';,"\\' for c in session):
        raise ConsoleError('A valid authenticated session is required')
    connection = None
    tunnel = None
    try:
        raw = socket.create_connection((hostname, port), timeout=timeout)
        try:
            connection = client.ssl_context.wrap_socket(raw, server_hostname=hostname)
        except Exception:
            raw.close()
            raise
        tunnel = Tunnel(connection)
        authority = '[' + hostname + ']' if ':' in hostname else hostname
        tunnel.send(('CONNECT ' + target + ' HTTP/1.1\r\nHost: ' + authority + ':' + str(port) +
                     '\r\nCookie: session_id=' + session + '\r\n\r\n').encode('ascii'))
        # Read through the same buffered reader that will consume RFB bytes.
        status = tunnel.reader.readline(4097)
        if len(status) > 4096 or status.split()[:2] not in ([b'HTTP/1.1', b'200'], [b'HTTP/1.0', b'200']):
            raise ConsoleError('Console tunnel was refused by the host')
        total = len(status)
        while True:
            line = tunnel.reader.readline(4097)
            total += len(line)
            if not line or len(line) > 4096 or total > 16384:
                raise ConsoleError('Invalid console tunnel response')
            if line == b'\r\n':
                return tunnel
    except Exception:
        if tunnel is not None:
            tunnel.close()
        elif connection is not None:
            connection.close()
        raise

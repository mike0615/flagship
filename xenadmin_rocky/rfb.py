"""RFB 3.3/3.8 framebuffer and input over an already authenticated TLS tunnel.

Wire format reference: https://www.rfc-editor.org/rfc/rfc6143
No clipboard synchronization or independent plaintext VNC connections.
"""
import re
import struct
from .console import ConsoleError


class RFB:
    def __init__(self, tunnel):
        self.tunnel = tunnel
        self.width = self.height = 0

    def unpack(self, fmt):
        return struct.unpack(fmt, self.tunnel.read(struct.calcsize(fmt)))

    @staticmethod
    def dimensions(width, height):
        if not (0 < width <= 4096 and 0 < height <= 4096):
            raise ConsoleError('Console resolution exceeds the supported limit')

    def handshake(self):
        banner = self.tunnel.read(12)
        if not re.fullmatch(rb'RFB 003\.\d{3}\n', banner):
            raise ConsoleError('Unsupported console protocol')
        modern = int(banner[8:11]) >= 8
        if not modern and int(banner[8:11]) < 3:
            raise ConsoleError('Unsupported console protocol version')
        self.tunnel.send(b'RFB 003.008\n' if modern else b'RFB 003.003\n')
        if modern:
            count, = self.unpack('!B')
            if not count or 1 not in self.tunnel.read(count):
                raise ConsoleError('Host console requires an unsupported authentication method')
            self.tunnel.send(b'\x01')
            status, = self.unpack('!I')
            if status:
                raise ConsoleError('Host refused console authentication')
        elif self.unpack('!I')[0] != 1:
            raise ConsoleError('Host console requires an unsupported authentication method')
        self.tunnel.send(b'\x01')  # Shared console; do not evict other operators.
        self.width, self.height = self.unpack('!HH')
        self.dimensions(self.width, self.height)
        self.tunnel.read(16)  # Replace the advertised pixel format explicitly.
        length, = self.unpack('!I')
        if length > 65536:
            raise ConsoleError('Console desktop name exceeds the supported limit')
        self.tunnel.read(length)  # Do not surface untrusted server names in logs/UI.
        # 32bpp, 24-bit depth, little endian, true colour, B G R padding bytes.
        pixel = struct.pack('!BBBBHHHBBB3x', 32, 24, 0, 1, 255, 255, 255, 16, 8, 0)
        self.tunnel.send(b'\x00\x00\x00\x00' + pixel)
        self.tunnel.send(struct.pack('!BBHiii', 2, 0, 3, 0, 1, -223))
        self.request(False)
        return self.width, self.height

    def request(self, incremental=True):
        self.tunnel.send(struct.pack('!BBHHHH', 3, bool(incremental), 0, 0, self.width, self.height))

    def rectangle(self, x, y, width, height):
        if not width or not height or x + width > self.width or y + height > self.height:
            raise ConsoleError('Console rectangle is outside the desktop')

    def events(self):
        """Yield bounded drawing events; the caller owns its framebuffer/UI thread."""
        message, = self.unpack('!B')
        if message == 0:
            resized = False
            _, count = self.unpack('!BH')
            if count > 4096:
                raise ConsoleError('Console update has too many rectangles')
            for _ in range(count):
                x, y, width, height, encoding = self.unpack('!HHHHi')
                if encoding == -223:
                    if x or y:
                        raise ConsoleError('Invalid console resize origin')
                    self.dimensions(width, height)
                    self.width, self.height = width, height
                    resized = True
                    yield ('resize', width, height)
                    continue
                self.rectangle(x, y, width, height)
                if encoding == 0:
                    pixels = self.tunnel.read(width * height * 4)
                    rgb = bytearray(width * height * 3)
                    rgb[0::3], rgb[1::3], rgb[2::3] = pixels[2::4], pixels[1::4], pixels[0::4]
                    yield ('pixels', x, y, width, height, bytes(rgb))
                elif encoding == 1:
                    source_x, source_y = self.unpack('!HH')
                    self.rectangle(source_x, source_y, width, height)
                    yield ('copy', x, y, width, height, source_x, source_y)
                else:
                    raise ConsoleError('Host used an unsupported framebuffer encoding')
            # A resize invalidates the local framebuffer, even if dimensions
            # repeat. Ask for every pixel rather than only subsequent changes.
            self.request(not resized)
        elif message == 2:
            yield ('bell',)
        elif message == 3:
            self.tunnel.read(3)
            length, = self.unpack('!I')
            if length > 1024 * 1024:
                raise ConsoleError('Console clipboard message exceeds the supported limit')
            self.tunnel.read(length)  # Intentionally no automatic clipboard sharing.
        else:
            raise ConsoleError('Host sent an unsupported framebuffer message')

    def key(self, keysym, pressed):
        if not 0 <= keysym <= 0xffffffff:
            raise ValueError('Invalid console key')
        self.tunnel.send(struct.pack('!BBHI', 4, bool(pressed), 0, keysym))

    def pointer(self, x, y, buttons):
        if not 0 <= buttons <= 255:
            raise ValueError('Invalid console pointer buttons')
        x, y = max(0, min(x, self.width - 1)), max(0, min(y, self.height - 1))
        self.tunnel.send(struct.pack('!BBHH', 5, buttons, x, y))

import io
import struct
import unittest
from xenadmin_rocky.console import ConsoleError
from xenadmin_rocky.rfb import RFB


class Wire:
    def __init__(self, data):
        self.data = io.BytesIO(data)
        self.sent = []

    def read(self, count):
        result = self.data.read(count)
        if len(result) != count: raise ConsoleError('Connection closed')
        return result

    def send(self, data): self.sent.append(data)


def greeting(modern=True, width=2, height=1):
    auth = b'RFB 003.008\n\x01\x01\x00\x00\x00\x00' if modern else b'RFB 003.003\n\x00\x00\x00\x01'
    return auth + struct.pack('!HH', width, height) + bytes(16) + struct.pack('!I', 4) + b'name'


class RFBTests(unittest.TestCase):
    def test_old_and_modern_handshake_requests_shared_truecolor_raw(self):
        for modern in (True, False):
            wire = Wire(greeting(modern)); rfb = RFB(wire)
            self.assertEqual(rfb.handshake(), (2, 1))
            self.assertIn(b'\x01', wire.sent)
            self.assertEqual(wire.sent[-1], struct.pack('!BBHHHH', 3, 0, 0, 0, 2, 1))
            self.assertEqual(len(wire.sent[-3]), 20)

    def test_framebuffer_pixels_converted_without_alpha_or_endian_error(self):
        update = b'\x00\x00\x00\x01' + struct.pack('!HHHHi', 0, 0, 2, 1, 0)
        wire = Wire(greeting() + update + b'\x00\x00\xff\x00\xff\x00\x00\x00')
        rfb = RFB(wire); rfb.handshake()
        self.assertEqual(list(rfb.events()), [('pixels', 0, 0, 2, 1, b'\xff\x00\x00\x00\x00\xff')])
        self.assertEqual(wire.sent[-1][1], 1)

    def test_resize_and_copyrect_with_validated_source(self):
        update = b'\x00\x00\x00\x02' + struct.pack('!HHHHi', 0, 0, 4, 3, -223)
        update += struct.pack('!HHHHiHH', 1, 1, 2, 1, 1, 0, 0)
        rfb = RFB(Wire(greeting() + update));rfb.handshake()
        self.assertEqual(list(rfb.events()), [('resize', 4, 3), ('copy', 1, 1, 2, 1, 0, 0)])

    def test_refuses_authentication_downgrade_and_oversized_desktop(self):
        for wire in (b'RFB 003.008\n\x01\x02', b'RFB 003.003\n\x00\x00\x00\x02',
                     greeting(width=65535), b'private text'):
            with self.assertRaises(ConsoleError): RFB(Wire(wire)).handshake()

    def test_malformed_rectangles_and_encodings_fail_closed(self):
        for rectangle in (struct.pack('!HHHHi', 1, 0, 2, 1, 0),
                          struct.pack('!HHHHi', 0, 0, 2, 1, 16),
                          struct.pack('!HHHHiHH', 0, 0, 2, 1, 1, 1, 0),
                          struct.pack('!HHHHi', 1, 0, 2, 1, -223)):
            rfb = RFB(Wire(greeting() + b'\x00\x00\x00\x01' + rectangle));rfb.handshake()
            with self.assertRaises(ConsoleError): list(rfb.events())

    def test_clipboard_is_consumed_without_exposing_or_synchronizing_content(self):
        rfb = RFB(Wire(greeting() + b'\x03\x00\x00\x00\x00\x00\x00\x06secret\x02'))
        rfb.handshake()
        self.assertEqual(list(rfb.events()), [])
        self.assertEqual(list(rfb.events()), [('bell',)])

    def test_keyboard_and_pointer_wire_events(self):
        wire = Wire(greeting());rfb=RFB(wire);rfb.handshake()
        rfb.key(0xff0d, True); rfb.key(0xff0d, False); rfb.pointer(500, -2, 1)
        self.assertEqual(wire.sent[-3], b'\x04\x01\x00\x00\x00\x00\xff\x0d')
        self.assertEqual(wire.sent[-2][1], 0)
        self.assertEqual(wire.sent[-1], struct.pack('!BBHH',5,1,1,0))


if __name__ == '__main__': unittest.main()

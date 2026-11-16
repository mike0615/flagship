import io
import ctypes.util
import socket
import threading
import unittest
from unittest.mock import Mock,patch
from flagship.console import Tunnel
from flagship.external_viewer import ExternalViewer,des_block,exact,vnc_response


class ViewerBridgeTests(unittest.TestCase):
    def setUp(self):
        self.client=Mock(session='private-xapi-session');self.process=Mock();self.process.poll.return_value=None
        self.viewer=None

    def tearDown(self):
        if self.viewer: self.viewer.close();self.viewer.worker.join(timeout=2)

    def create(self,connector):
        library=ctypes.util.find_library('crypto')
        with patch('flagship.external_viewer.ctypes.util.find_library',return_value=library), patch('flagship.external_viewer.subprocess.Popen',return_value=self.process):
            self.viewer=ExternalViewer(self.client,'vm',connector=connector,binary='/example/remote-viewer')
        config=self.process.stdin.write.call_args.args[0].decode()
        fields=dict(line.split('=',1) for line in config.splitlines() if '=' in line)
        return fields

    def test_platform_des_matches_standard_known_vector(self):
        self.assertEqual(des_block(bytes.fromhex('133457799bbcdff1'),bytes.fromhex('0123456789abcdef')).hex(),'85e813540f0ab405')

    def test_bad_one_use_password_never_opens_authenticated_host_tunnel(self):
        connector=Mock(); fields=self.create(connector)
        with socket.create_connection(('127.0.0.1',int(fields['port'])),timeout=3) as client:
            exact(client,12);client.sendall(b'RFB 003.008\n');self.assertEqual(exact(client,2),b'\x01\x02')
            client.sendall(b'\x02');exact(client,16);client.sendall(b'\0'*16)
            self.assertEqual(exact(client,4),b'\0\0\0\x01')
        self.viewer.worker.join(timeout=2);connector.assert_not_called()
        self.assertNotIn('private-xapi-session',str(self.process.stdin.write.call_args))
        self.assertEqual(fields['host'],'127.0.0.1')

    def test_authenticated_bridge_relays_init_and_pixels_and_preserves_shared_mode(self):
        upstream,server=socket.socketpair();server.settimeout(3);seen=[]
        def host():
            try:
                server.sendall(b'RFB 003.008\n');seen.append(exact(server,12))
                server.sendall(b'\x01\x01');self.assertEqual(exact(server,1),b'\x01');server.sendall(b'\0'*4)
                seen.append(exact(server,1));server.sendall(b'host-framebuffer')
                seen.append(exact(server,5));server.sendall(b'pixels')
            finally:server.close()
        worker=threading.Thread(target=host);worker.start()
        fields=self.create(lambda *_:Tunnel(upstream))
        with socket.create_connection(('127.0.0.1',int(fields['port'])),timeout=3) as client:
            exact(client,12);client.sendall(b'RFB 003.008\n');exact(client,2);client.sendall(b'\x02')
            challenge=exact(client,16);client.sendall(vnc_response(fields['password'],challenge));self.assertEqual(exact(client,4),b'\0'*4)
            client.sendall(b'\0') # Even an exclusive request must not evict existing operators.
            self.assertEqual(exact(client,16),b'host-framebuffer')
            client.sendall(b'input');self.assertEqual(exact(client,6),b'pixels')
        worker.join(timeout=3);self.assertFalse(worker.is_alive());self.assertEqual(seen[1],b'\x01');self.assertEqual(seen[2],b'input')

"""External remote-viewer through a private, one-use authenticated VNC bridge.

Only a random VNC password reaches the viewer over stdin. XAPI credentials and
session cookies stay in Flagship's verified/pinned TLS tunnel. DES is used solely
for the VNC challenge protocol, through the platform OpenSSL library.
"""
import ctypes
import ctypes.util
import hmac
import queue
import secrets
import shutil
import socket
import struct
import subprocess
import threading
from .console import open_console, ConsoleError


def des_block(key,data):
    if len(key)!=8 or len(data)!=8: raise ValueError('DES blocks require eight bytes')
    library=ctypes.util.find_library('crypto')
    if not library: raise ConsoleError('The platform crypto library is unavailable.')
    crypto=ctypes.CDLL(library)
    try:
        setup=crypto.DES_set_key_unchecked; encrypt=crypto.DES_ecb_encrypt
    except AttributeError: raise ConsoleError('This platform does not expose VNC challenge authentication.') from None
    setup.argtypes=[ctypes.c_void_p,ctypes.c_void_p]; setup.restype=None
    encrypt.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int]; encrypt.restype=None
    schedule=(ctypes.c_uint64*16)(); out=ctypes.create_string_buffer(8)
    setup(ctypes.create_string_buffer(key,8),ctypes.byref(schedule))
    encrypt(ctypes.create_string_buffer(data,8),out,ctypes.byref(schedule),1)
    return out.raw


def vnc_response(password,challenge):
    key=bytes(int('{:08b}'.format(b)[::-1],2) for b in password.encode('ascii')[:8].ljust(8,b'\0'))
    return des_block(key,challenge[:8])+des_block(key,challenge[8:])


def exact(connection,count):
    result=b''
    while len(result)<count:
        part=connection.recv(count-len(result))
        if not part: raise ConsoleError('External viewer disconnected.')
        result+=part
    return result


class ExternalViewer:
    def __init__(self,client,vm,title='Flagship console',connector=open_console,binary=None):
        self.client=client; self.vm=vm; self.connector=connector
        self.errors=queue.Queue(); self.stop=threading.Event(); self.lock=threading.Lock()
        self.tunnel=self.local=self.process=None
        self.bytes_from_host=0; self.bytes_to_host=0
        binary=binary or shutil.which('remote-viewer')
        if not binary: raise ValueError('Virt Viewer is not installed. Install the native virt-viewer package to enable this option.')
        self.password=''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789') for _ in range(8))
        # Check crypto availability before opening a listener or launching a viewer.
        vnc_response(self.password,b'\0'*16)
        self.listener=socket.socket(); self.listener.bind(('127.0.0.1',0)); self.listener.listen(1); self.listener.settimeout(20)
        port=self.listener.getsockname()[1]
        try:
            self.process=subprocess.Popen([binary,'--shared','--title',title,'-'],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            config='[virt-viewer]\ntype=vnc\nhost=127.0.0.1\nport={}\npassword={}\n'.format(port,self.password)
            self.process.stdin.write(config.encode('ascii')); self.process.stdin.close()
            self.worker=threading.Thread(target=self.serve,daemon=True); self.worker.start()
        except Exception:
            self.close(); raise

    def serve(self):
        try:
            local,_=self.listener.accept(); local.settimeout(15)
            with self.lock:
                if self.stop.is_set(): local.close(); return
                self.local=local
            self.listener.close()
            local.sendall(b'RFB 003.008\n')
            if exact(local,12)!=b'RFB 003.008\n': raise ConsoleError('The external viewer requires RFB 3.8.')
            local.sendall(b'\x01\x02')
            if exact(local,1)!=b'\x02': raise ConsoleError('External viewer refused VNC authentication.')
            challenge=secrets.token_bytes(16); local.sendall(challenge)
            if not hmac.compare_digest(exact(local,16),vnc_response(self.password,challenge)):
                local.sendall(struct.pack('!I',1)); raise ConsoleError('External viewer authentication failed.')
            self.password=None; local.sendall(struct.pack('!I',0))
            # Authenticate upstream before relaying anything. Always keep the console shared.
            tunnel=self.connector(self.client,self.vm)
            with self.lock:
                if self.stop.is_set(): tunnel.close(); return
                self.tunnel=tunnel
            banner=tunnel.read(12)
            if banner[:8]!=b'RFB 003.' or not banner[8:11].isdigit(): raise ConsoleError('Unsupported host console banner.')
            modern=int(banner[8:11])>=8
            tunnel.send(b'RFB 003.008\n' if modern else b'RFB 003.003\n')
            if modern:
                count=tunnel.read(1)[0]
                if not count or 1 not in tunnel.read(count): raise ConsoleError('Unsupported host console security.')
                tunnel.send(b'\x01')
                if tunnel.read(4)!=b'\0'*4: raise ConsoleError('Host refused console security.')
            elif tunnel.read(4)!=struct.pack('!I',1): raise ConsoleError('Unsupported host console security.')
            exact(local,1); tunnel.send(b'\x01')
            local.settimeout(None); tunnel.connection.settimeout(None)
            sender=threading.Thread(target=self.send_to_host,daemon=True); sender.start()
            while not self.stop.is_set():
                block=tunnel.reader.read1(65536)
                if not block: break
                local.sendall(block); self.bytes_from_host+=len(block)
        except Exception as exc:
            if not self.stop.is_set(): self.errors.put(exc)
        finally: self.close(terminate=False)

    def send_to_host(self):
        try:
            while not self.stop.is_set():
                block=self.local.recv(65536)
                if not block: break
                self.tunnel.send(block); self.bytes_to_host+=len(block)
        except OSError: pass
        finally: self.close(terminate=False)

    def close(self,terminate=True):
        self.stop.set(); self.password=None
        with self.lock:
            try: self.listener.close()
            except OSError: pass
            if self.local:
                try: self.local.shutdown(socket.SHUT_RDWR)
                except OSError: pass
                self.local.close(); self.local=None
            if self.tunnel: self.tunnel.close(); self.tunnel=None
        if terminate and self.process and self.process.poll() is None: self.process.terminate()

#!/usr/bin/env python3
"""Privately capture a recorded QA guest console; optional key only targets that guest."""
import argparse
import getpass
import json
import os
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
import time
from xenadmin_rocky.api import Client
from xenadmin_rocky.console import open_console
from xenadmin_rocky.rfb import RFB


def capture(c, state, guest, args):
    tunnel = None
    try:
        vm = c.call('VM.get_by_uuid', guest['uuid'])
        if not c.call('VM.get_record', vm)['name_label'].startswith(state['prefix']):
            raise ValueError('Recorded guest no longer matches the QA namespace')
        tunnel = open_console(c, vm)
        rfb = RFB(tunnel)
        width, height = rfb.handshake()
        pixels = bytearray(width*height*3)
        received = False
        click = getattr(args, 'click', None)
        if click is not None:
            if len(click) != 3 or any(not isinstance(value, int) for value in click) or not 1 <= click[2] <= 5:
                raise ValueError('Click requires x, y and a button number from 1 to 5')
            x, y, button = click
            rfb.pointer(x, y, 1 << (button-1)); rfb.pointer(x, y, 0)
            time.sleep(1.0)
        for chord in args.chord:
            keys = [int(value, 0) for value in chord.split(',')]
            for key in keys: rfb.key(key, True)
            for key in reversed(keys): rfb.key(key, False)
            time.sleep(1.0)  # Allow a guest focus/VT switch before sending text.
        for char in args.text:
            code = ord(char)
            key = {'\n': 0xff0d, '\r': 0xff0d, '\t': 0xff09}.get(char, code if code < 256 else 0x01000000 | code)
            shifted = 'A' <= char <= 'Z' or char in '~!@#$%^&*()_+{}|:"<>?'
            if shifted: rfb.key(0xffe1, True)
            rfb.key(key, True); rfb.key(key, False)
            if shifted: rfb.key(0xffe1, False)
            time.sleep(.02)
        for key in args.key:
            rfb.key(key, True); rfb.key(key, False)
        tunnel.connection.settimeout(5)
        deadline = time.monotonic()+5
        while time.monotonic() < deadline:
            try:
                for event in rfb.events():
                    if event[0] == 'resize':
                        _, width, height = event
                        pixels = bytearray(width*height*3)
                    elif event[0] in ('pixels', 'copy'):
                        kind, x, y, w, h, *data = event
                        if kind == 'pixels': tile = data[0]
                        else:
                            sx, sy = data
                            tile = b''.join(pixels[((sy+row)*width+sx)*3:((sy+row)*width+sx+w)*3] for row in range(h))
                        for row in range(h):
                            offset = ((y+row)*width+x)*3
                            pixels[offset:offset+w*3] = tile[row*w*3:(row+1)*w*3]
                        received = True
            except socket.timeout:
                break
        if not received: raise ValueError('No framebuffer pixels received')
        fd = os.open(args.output, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as output:
            output.write(('P6\n%d %d\n255\n' % (width, height)).encode()+pixels)
        print('Private framebuffer capture saved:', width, 'x', height)
    finally:
        if tunnel: tunnel.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('endpoint', 'username', 'ca-file', 'state-file'):
        p.add_argument('--'+name, required=True)
    p.add_argument('--click', type=lambda value: [int(part) for part in value.split(',')], help='Guest x,y,button; only the recorded QA VM receives input')
    p.add_argument('--output')
    p.add_argument('--interactive', action='store_true', help='Read nonsecret QA commands as JSON lines; retain only the API session in memory')
    p.add_argument('--key', type=lambda value: int(value, 0), action='append', default=[])
    p.add_argument('--chord', action='append', default=[], help='Comma-separated X11 keysyms held together, then released')
    p.add_argument('--text', default='', help='Nonsecret QA shell text only; arguments are visible to local process listings')
    args = p.parse_args()
    state = json.loads(Path(args.state_file).read_text())
    if state['endpoint'] != args.endpoint or not state['prefix'].startswith('xenadmin-qa-'):
        p.error('Expected a QA manifest for this endpoint')
    guests = [item for item in state['created'] if item['class'] == 'VM']
    if len(guests) != 1: p.error('Expected one recorded QA guest')
    c = Client(args.endpoint, args.ca_file)
    tunnel = None
    try:
        password = getpass.getpass('XAPI QA password: ')
        c.login(args.username, password)
        password = None
        if not args.interactive:
            if not args.output: p.error('--output is required without --interactive')
            capture(c, state, guests[0], args)
        else:
            print('QA console session ready. JSON commands: output basename, text, chord, key; quit to logout.', flush=True)
            for line in sys.stdin:
                if line.strip() == 'quit': break
                try:
                    command = json.loads(line)
                    name = command['output']
                    if not isinstance(name, str) or Path(name).name != name or name in ('.', '..'):
                        raise ValueError('Output must be a new basename in the private state directory')
                    operation = SimpleNamespace(output=str(Path(args.state_file).parent/name),
                        text=command.get('text', ''), chord=command.get('chord', []), key=command.get('key', []), click=command.get('click'))
                    capture(c, state, guests[0], operation)
                except Exception as exc:
                    print('QA command stopped:', type(exc).__name__, flush=True)
                print('Ready.', flush=True)
    finally:
        c.logout()


if __name__ == '__main__': main()

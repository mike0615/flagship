#!/usr/bin/env python3
"""Privately capture a recorded QA guest console; optional key only targets that guest."""
import argparse
import getpass
import json
import os
from pathlib import Path
import socket
import time
from xenadmin_rocky.api import Client
from xenadmin_rocky.console import open_console
from xenadmin_rocky.rfb import RFB


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('endpoint', 'username', 'ca-file', 'state-file', 'output'):
        p.add_argument('--'+name, required=True)
    p.add_argument('--key', type=lambda value: int(value, 0), action='append', default=[])
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
        vm = c.call('VM.get_by_uuid', guests[0]['uuid'])
        if not c.call('VM.get_record', vm)['name_label'].startswith(state['prefix']):
            raise ValueError('Recorded guest no longer matches the QA namespace')
        tunnel = open_console(c, vm)
        rfb = RFB(tunnel)
        width, height = rfb.handshake()
        pixels = bytearray(width*height*3)
        received = False
        for key in args.key:
            rfb.key(key, True); rfb.key(key, False)
        tunnel.connection.settimeout(5)
        deadline = time.monotonic()+15
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
        c.logout()


if __name__ == '__main__': main()

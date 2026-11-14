#!/usr/bin/env python3
"""Stream verified QA media directly to an ISO SR, without filling dom0 /tmp."""
import argparse
import getpass
import hashlib
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
from xenadmin_rocky.journal import save_json_private


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','destination','sha256','ssh-host','ssh-control','record'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    destination=Path(args.destination)
    if (not str(destination).startswith('/var/run/sr-mount/') or
            not re.fullmatch(r'xenadmin-qa-[A-Za-z0-9_.-]+\.iso',destination.name) or
            '..' in destination.parts):
        parser.error('Destination must be a new xenadmin-qa-*.iso in the selected ISO SR')
    if not re.fullmatch(r'[0-9a-f]{64}',args.sha256):parser.error('Expected a SHA-256 digest')
    record=Path(args.record)
    if record.exists():parser.error('Inspect the previous staging record instead of replacing it')
    source_fd=os.open(args.source,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    info=os.fstat(source_fd)
    if not stat.S_ISREG(info.st_mode) or not info.st_size:
        os.close(source_fd);parser.error('Expected a nonempty regular ISO file')
    state={'source':str(Path(args.source).absolute()),'destination':str(destination),
           'partial':str(destination)+'.part','bytes':info.st_size,'sha256':args.sha256,'status':'prepared'}
    save_json_private(record,state)
    quote=shlex.quote
    # Require a 20 GiB reserve on the actual backing filesystem, not just SR metadata.
    minimum_kib=(info.st_size+1023)//1024+20*1024*1024
    script='\n'.join([
        'set -eu',
        'destination='+quote(str(destination)),
        'partial='+quote(str(destination)+'.part'),
        'test -d '+quote(str(destination.parent)),
        'test ! -e "$destination"; test ! -L "$destination"',
        'test ! -e "$partial"; test ! -L "$partial"',
        'available=$(df -Pk '+quote(str(destination.parent))+" | awk 'NR==2 {print $4}')",
        'test "$available" -ge '+str(minimum_kib),
        'umask 077; exec 3> "$partial"',
        "printf 'QA-ISO-READY\\n' >&2",
        'cat >&3; exec 3>&-',
        'digest=$(sha256sum "$partial")',
        'test "${digest%% *}" = '+quote(args.sha256),
        'ln -- "$partial" "$destination"',  # Atomic no-overwrite publication.
        'rm -- "$partial"',
        'sync',  # Legacy XCP-ng dom0 coreutils has no per-file sync option.
        "printf 'QA-ISO-STAGED\\n'",
    ])
    # -k forces authentication. Never place a password into an upload stream that
    # might already be owned by cat because sudo reused cached authentication.
    remote=shlex.join(['sudo','-k','-S','-p','QA-ISO-PASSWORD\n','/bin/sh','-c',script])
    process=None
    transferred=0;code=None
    try:
        process=subprocess.Popen(['ssh','-S',args.ssh_control,'-o','BatchMode=yes',
            '-o','StrictHostKeyChecking=yes',args.ssh_host,remote],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if process.stderr.readline()!=b'QA-ISO-PASSWORD\n':
            raise RuntimeError('Remote authentication handshake was not confirmed; no credential was sent')
        password=getpass.getpass('QA sudo password: ')
        process.stdin.write((password+'\n').encode());process.stdin.flush()
        password=None
        if process.stderr.readline()!=b'QA-ISO-READY\n':
            raise RuntimeError('Staging was not authorized or the destination failed its preflight checks')
        state['status']='streaming';save_json_private(record,state)
        digest=hashlib.sha256();transferred=0;reported=0
        with os.fdopen(source_fd,'rb') as source:
            source_fd=None
            while True:
                block=source.read(1024*1024)
                if not block:break
                digest.update(block);process.stdin.write(block);transferred+=len(block)
                if transferred-reported>=1024**3:
                    reported=transferred;print('Staged',transferred//1024**2,'MiB',flush=True)
        process.stdin.close()
        output=process.stdout.read(1024)
        code=process.wait()
        if code or output!=b'QA-ISO-STAGED\n' or digest.hexdigest()!=args.sha256:
            raise RuntimeError('Remote staging or full-image digest confirmation failed; inspect the private record')
        state.update(status='verified_and_staged',transferred=transferred)
        save_json_private(record,state)
        print('PASS: complete ISO streamed to SR, remote checksum matched, new filename published without overwrite.')
        return 0
    except Exception as exc:
        state.update(status='interrupted_or_failed',error_type=type(exc).__name__,
                     transferred=transferred,remote_exit_code=code)
        if isinstance(exc,RuntimeError):state['reason']=str(exc)
        save_json_private(record,state)
        print('QA ISO staging stopped:',str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__,flush=True)
        return 1
    finally:
        if source_fd is not None:os.close(source_fd)
        if process and process.poll() is None:
            process.kill();process.wait()


if __name__=='__main__':raise SystemExit(main())

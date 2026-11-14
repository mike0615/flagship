#!/usr/bin/env python3
"""Build an OEMDRV seed for an isolated disposable Rocky 9 or 10 desktop QA VM."""
import argparse
import crypt
import hashlib
from pathlib import Path
import secrets
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--major', type=int, choices=(9,10), default=9)
    parser.add_argument('--airgap', type=Path, required=True)
    parser.add_argument('--output-directory', type=Path, required=True)
    args = parser.parse_args()
    for item in ('SHA256SUMS', 'install-offline.sh', 'rpms'):
        if not (args.airgap/item).exists(): parser.error('Expected an extracted airgap bundle')
    release = {}
    for line in (args.airgap/'BUILD_OS_RELEASE').read_text().splitlines():
        if '=' in line:
            key, value = line.split('=',1);release[key] = value.strip(chr(34))
    if release.get('ID') != 'rocky' or release.get('VERSION_ID','').split('.')[0] != str(args.major):
        parser.error('The bundle Rocky major must match --major')
    # The output directory must be new, keeping the generated account hash private.
    args.output_directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    staging = args.output_directory/'seed'
    staging.mkdir(mode=0o700)
    template = Path(__file__).with_name('desktop-seed.ks.in').read_text()
    if args.major == 10:
        template = template.replace('#version=RHEL9', '#version=RHEL10')
        template = template.replace('gnome-terminal\n%end', 'ptyxis\nxorg-x11-server-Xwayland\n%end')
        template = template.replace('Exec=gnome-terminal -- ', 'Exec=ptyxis --new-window -- ')
        template = template.replace('WaylandEnable=false\n', '')
    hashed = crypt.crypt(secrets.token_urlsafe(32), crypt.mksalt(crypt.METHOD_SHA512))
    config = staging/'ks.cfg'
    config.write_text(template.replace('@QA_PASSWORD_HASH@', hashed))
    config.chmod(0o600)
    if args.major == 9:
        subprocess.run(['ksvalidator', '-v', 'RHEL9', str(config)], check=True)
    else:
        subprocess.run(['podman','run','--rm','-v',str(staging.absolute())+':/seed:ro,Z',
            'quay.io/rockylinux/rockylinux:10','bash','-euc',
            'dnf --disablerepo="*" --enablerepo=baseos --enablerepo=appstream install -y pykickstart; ksvalidator -v RHEL10 /seed/ks.cfg'],check=True)
    subprocess.run(['sha256sum', '-c', 'SHA256SUMS', '--quiet'], cwd=args.airgap, check=True)
    shutil.copytree(args.airgap, staging/'airgap')
    output = args.output_directory/'xenadmin-qa-oemdrv.iso'
    subprocess.run(['xorriso', '-as', 'mkisofs', '-quiet', '-R', '-J', '-V', 'OEMDRV',
                    '-o', str(output), str(staging)], check=True)
    output.chmod(0o600)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.iso.sha256').write_text(digest+'  '+output.name+'\n')
    print('QA seed built; validate guest isolation and exact VM UUID before attachment.')


if __name__ == '__main__': main()

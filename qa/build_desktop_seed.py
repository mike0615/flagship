#!/usr/bin/env python3
"""Build an OEMDRV seed for an isolated disposable Rocky 9 desktop QA VM."""
import argparse
import crypt
import hashlib
from pathlib import Path
import secrets
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--airgap', type=Path, required=True)
    parser.add_argument('--output-directory', type=Path, required=True)
    args = parser.parse_args()
    for item in ('SHA256SUMS', 'install-offline.sh', 'rpms'):
        if not (args.airgap/item).exists(): parser.error('Expected an extracted airgap bundle')
    # The output directory must be new, keeping the generated account hash private.
    args.output_directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    staging = args.output_directory/'seed'
    staging.mkdir(mode=0o700)
    template = Path(__file__).with_name('desktop-seed.ks.in').read_text()
    hashed = crypt.crypt(secrets.token_urlsafe(32), crypt.mksalt(crypt.METHOD_SHA512))
    config = staging/'ks.cfg'
    config.write_text(template.replace('@QA_PASSWORD_HASH@', hashed))
    config.chmod(0o600)
    subprocess.run(['ksvalidator', '-v', 'RHEL9', str(config)], check=True)
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

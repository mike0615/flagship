#!/usr/bin/env python3
"""Assemble validated, uniquely named release assets from both Rocky builds."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from flagship import __version__

tag = 'v' + __version__.replace('.dev', '-dev.')
if len(sys.argv) != 2 or sys.argv[1] != tag or not re.fullmatch(r'v\d+\.\d+\.\d+-dev\.\d+', tag):
    raise SystemExit('Pass the development release tag matching flagship.__version__')
commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
release = ROOT / 'dist' / ('release-' + tag)
if release.exists():
    raise SystemExit('Release staging directory already exists; inspect it before rebuilding')
release.mkdir(parents=True)
manifest = {'tag': tag, 'version': __version__, 'source_commit': commit, 'targets': {}}
for major in (9, 10):
    build = ROOT / 'dist' / __version__ / ('el' + str(major))
    candidates = sorted(build.glob('flagship-*.noarch.rpm')) + sorted(build.glob('flagship-*.src.rpm'))
    archives = sorted(build.glob('flagship-[0-9]*.tar.gz'))
    bundles = sorted(build.glob('flagship-airgap-*.tar.gz'))
    if len(candidates) != 2 or len(archives) != 1 or len(bundles) != 1:
        raise SystemExit('Expected one application RPM, SRPM, source archive and offline bundle for el' + str(major))
    with tarfile.open(archives[0], 'r:gz') as archive:
        records = [m for m in archive.getmembers() if m.name.endswith('/SOURCE_COMMIT')]
        if len(records) != 1 or archive.extractfile(records[0]).read().decode().strip() != commit:
            raise SystemExit('Source archive commit does not match the release checkout')
    for rpm in candidates:
        identity = subprocess.check_output(['rpm', '-qp', '--qf', '%{NAME} %{VERSION}-%{RELEASE} %{ARCH}', str(rpm)], text=True)
        if not identity.startswith('flagship ') or '.el' + str(major) not in identity:
            raise SystemExit('RPM target identity mismatch')
        shutil.copy2(rpm, release / rpm.name)
    source_name = 'flagship-' + tag.removeprefix('v') + '-source-el' + str(major) + '.tar.gz'
    shutil.copy2(archives[0], release / source_name)
    shutil.copy2(bundles[0], release / bundles[0].name)
    shutil.copy2(build / 'airgap' / 'PACKAGES.tsv', release / ('PACKAGES-el' + str(major) + '.tsv'))
    manifest['targets'][str(major)] = {'source_archive': source_name, 'offline_bundle': bundles[0].name,
                                     'rpms': [p.name for p in candidates]}
for name in ('LIVE_PORTABLE_2026-11-16.md', 'WORKSPACE_QUALIFICATION.md'):
    shutil.copy2(ROOT / 'evidence' / name, release / name)
(release / 'RELEASE_SOURCE.json').write_text(json.dumps(manifest, indent=2) + '\n')
files = sorted(p for p in release.iterdir() if p.is_file())
(release / 'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n' for p in files))
print(str(release))

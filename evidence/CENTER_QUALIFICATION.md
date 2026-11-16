# Center interface candidate qualification, 2026-11-16

Application: Flagship 1.2.0.dev1. Packaged source commit:
`20e3f705bacfb8a776e5f406d592e798147e7a7b`.

| Check | Rocky 9 | Rocky 10 |
|---|---|---|
| Native noarch RPM and source RPM build | Passed | Passed |
| Minimal-container install, network disabled | Passed | Passed |
| Installed imports, help, launchers and compatibility commands | Passed | Passed |
| Installed native GUI and smoke launch, network disabled | Passed | Passed |
| Tests against installed /usr/share/flagship modules | 215 passed | 215 passed |

Base image identities report Rocky 9.8 and 10.2. Dependencies came from the
current matching-major BaseOS/AppStream repositories; exact resolved package
versions and image digests are recorded in center-provenance.json. Some package
release tags are newer than the image's /etc/os-release minor version.

`center-build-el{9,10}.txt`, `center-offline-el{9,10}.txt`, and
`center-installed-el{9,10}.txt` retain command output. `center-tests.txt` retains
the source-tree desktop regression run. The GUI checks used a test-only Rocky 9
Xvfb server over a private Unix socket. The Rocky 10 application and libraries
ran in the Rocky 10 container. Xvfb is not an application runtime dependency.
Both test clients had `--network=none`. TLS tests use local fixtures, not a
hypervisor; screenshots use synthetic inventory.

GitHub Actions run 43940380635 also passed tests and both RPM jobs for the
packaged source commit. This evidence commit does not change the packaged code.

## Artifacts

Local versioned build output is under `dist/1.2.0.dev1/el9` and `el10`:
application RPM, source RPM, source archive, SHA256SUMS, dependency-complete
binary airgap archive and its .sha256 sidecar. The airgap archive includes a
local repository, PACKAGES.tsv, checksum inventory, matching-major identity,
installer and offline documentation. Runtime needs no Wine, Windows runtime,
pip, EPEL or internet assets. Dependency SRPM archives are not included in this
iteration; the application source archive and source RPM are included.

The candidate RPM is unsigned, as the existing development packaging documents
explain. Transfer checksums detect corruption; they are not signatures.

## Remaining evidence and functionality

No new live XAPI connection or live host mutation was performed for this change.
Container success does not establish booted-desktop/Wayland/SELinux behavior,
real NFS attachment, pool-member certificate acceptance, guest input, migration,
RRD compatibility, XVA import/export or restricted-role behavior on a live pool.
These need target-host qualification. Earlier evidence applies only to its
recorded source/build, not automatically to these added workflows.

Full XCP-ng Center parity remains incomplete. See docs/CENTER_INTERFACE.md for
scope: HA, DR, WLB, updates, pool membership, vApps, snapshot schedules, advanced
network/storage/property editors, multiple simultaneous pool connections,
OVF/OVA/raw-disk imports and host/RDP console features remain unfinished.

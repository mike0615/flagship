# Flagship 1.2.0.dev2 qualification

Packaged source commit: `19568329bf4288315b6c6d80f55a2843df325ccf`.

Both Rocky major versions passed native RPM/source-RPM builds, minimal-container
offline installation, installed GUI smoke launch and 220 tests against installed
/usr/share/flagship modules with --network=none. See center-dev2-build-el{9,10}.txt,
center-dev2-offline-el{9,10}.txt, center-dev2-installed-el{9,10}.txt and
center-dev2-provenance.json for logs, package versions and artifact hashes.
The separate Xvfb display server test setup is unchanged from dev.1.

Live XCP-ng 8.3.0 read-only and disposable-workflow evidence, including the fixed
XVA roundtrip and independently verified cleanup, is in LIVE_CENTER_2026-11-16.md.
This does not establish full guest OS, multi-host, HA/DR or Windows feature parity.

Application RPMs, source RPMs, source archives, checksum manifests and separate
Rocky 9/10 offline archives are local under dist/1.2.0.dev2/el9 and el10. Each
transfer archive has a .sha256 sidecar. Older dev.1 artifacts are preserved in
their separate version directory. Runtime dependencies remain stock Rocky
Python/Tk/CA packages, with no Wine or pip fallback.

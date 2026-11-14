# Offline installation on Rocky Linux 9 and 10

## Requirements

A Rocky Linux 9 or 10 x86_64 desktop with a graphical session, trusted HTTPS access
to the XAPI pool coordinator on TCP 443, administrative install access, and the
matching-major airgap bundle. Internet access is not required by the installed
client. The matching dependency-source archive is supplied separately for offline source
access; it is not installed or needed at runtime. A desktop environment itself is a prerequisite; the bundle does not install
GNOME/KDE or turn a minimal server into a workstation.

## Transfer and install

On a connected builder follow BUILD.md. Transfer the matching archive through your
approved media procedure. Authenticate the source/release and compare SHA-256
against a separately trusted manifest. Checksums shipped beside files detect
corruption, not a malicious replacement of both files and manifest.

Extract in a staging directory, review PACKAGES.tsv and run:

```sh
tar -xzf xenadmin-rocky-airgap-el9-x86_64-dev1.tar.gz
cd airgap
sha256sum -c SHA256SUMS
sudo ./install-offline.sh
xenadmin-rocky --version
xenadmin-rocky
```

Use the el10 archive on Rocky 10. DNF is invoked with every repository disabled;
it enables only the transferred file:// repository and selects the application
and necessary dependencies. It does not force an upgrade of every bundled RPM. The candidate RPM is unsigned, so the
installer explicitly disables package signature checking for the local repository and this transaction.
Do not use that setting as a global DNF configuration. Stable release signing remains
a qualification gate. Dependency license identifiers are recorded in PACKAGES.tsv;
retain their license files installed by each package.

Expected outcome: DNF exits successfully with no external repository use, the
version prints, and the desktop opens. Open Help with external networking disabled.
Reboot and repeat launch from the application menu. Then test trusted pool login
and a read-only inventory. Record exact Rocky minor, architecture and package list.
Do not mark an installation validated if any dependency was fetched externally.

## Upgrade and remove

Retain the previous RPM and matching dependency bundle before upgrading. Install
a new authenticated bundle with its offline installer. To remove the client:

```sh
sudo dnf --disablerepo='*' remove xenadmin-rocky
```

Review DNF's transaction before confirming. Removing the client does not remove
VMs, undo host changes or cancel tasks. There is no saved credential store.

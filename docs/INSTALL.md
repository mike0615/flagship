# Offline installation on Rocky Linux 9 and 10

## Requirements

A Rocky Linux 9 or 10 x86_64 desktop with a graphical session, trusted HTTPS access
to the XAPI pool coordinator on TCP 443, administrative install access, and the
matching-major airgap bundle. Internet access is not required by the installed
client. The matching dependency-source archive is supplied separately for offline source
access; it is not installed or needed at runtime. A desktop environment itself is a prerequisite; the bundle does not install
GNOME/KDE or turn a minimal server into a workstation.

For a previously published XenAdmin Rocky candidate, use its attached documentation and original
archive names. The current source build targets Flagship 1.2.0.dev1, which is a development candidate, not a stable release.

## Transfer and install

On a connected builder follow BUILD.md. Transfer the matching archive through your
approved media procedure. Authenticate the source/release and compare SHA-256
against a separately trusted manifest. Checksums shipped beside files detect
corruption, not a malicious replacement of both files and manifest.

Use the exact archive filename for the release you transferred. This example
uses the current Flagship 1.2.0.dev1 build. Extract in a staging directory, review PACKAGES.tsv
and run:

```sh
tar -xzf flagship-airgap-el9-x86_64-1.2.0.dev1.tar.gz
cd airgap
sha256sum -c SHA256SUMS
sudo ./install-offline.sh
flagship --version
flagship
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
a new authenticated bundle with its offline installer.

Upgrading from XenAdmin Rocky: installing the Flagship package replaces
`xenadmin-rocky` (`Obsoletes:` / `Provides:`). The `xenadmin-rocky` and
`xenadmin-rocky-recovery` commands remain as symlinks. On first run Flagship
copies `~/.local/state/xenadmin-rocky` (and `~/.config/xenadmin-rocky` if
present) to the new Flagship locations and leaves the originals in place.

To remove the client:

```sh
sudo dnf --disablerepo='*' remove flagship
```

Review DNF's transaction before confirming. Removing the client does not remove
VMs, undo host changes or cancel tasks. There is no saved credential store.

## Corresponding source set for dev.2

Runtime installation needs the matching binary airgap archive only. To retain a
complete offline source set, also transfer the dev.1 dependency-source archive for
the same Rocky major and the dev.2 source-delta archive, plus the native source
archive. The delta contains the dev.2 application SRPM and changed dependency
SRPMs. Rocky 9 glibc and tzdata differ from the earlier bundle; the recorded exact
versions, rather than package names alone, determine source coverage.

`DEPENDENCY-SOURCES.json` attached to dev.2 maps every bundled binary RPM to its
exact source RPM, source SHA-256 and archive download. Baseline archive links point
to the retained dev.1 release; delta links point to dev.2. Transfer both archives
before disconnecting. Extract into separate directories and consult the map rather
than assuming a baseline source version matches a newer binary. These archives
are not needed to run the installed application.

Application upgrades/removal preserve private operation journals under the user
state directory. Retain them for recovery; see RECOVERY.md before exporting or
manually retiring them. 1.2.0.dev1 runtime packaging is under verification; use a
published candidate and its matching attached instructions for installation.

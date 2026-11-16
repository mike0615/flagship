Native Rocky Linux 9/10 desktop client. **Development prerelease; no Wine required.**

This release adds the Center-style interface, contextual menus/tabs, scoped
inventory tables, an eight-step VM wizard, host controls, NFS/private-network
creation, RRD graphs and XVA import/export. It fixes XVA import readiness and
VM-set task result compatibility found during live XCP-ng 8.3.0 testing.

### Install on a connected desktop

Rocky Linux 9:
```bash
sudo dnf install https://github.com/mike0615/flagship/releases/download/v1.2.0-dev.2/flagship-1.2.0-0.2.dev2.el9.noarch.rpm
```
Rocky Linux 10:
```bash
sudo dnf install https://github.com/mike0615/flagship/releases/download/v1.2.0-dev.2/flagship-1.2.0-0.2.dev2.el10.noarch.rpm
```
Then launch **Flagship** from the application menu or run `flagship`.
Runtime dependencies come from stock Rocky repositories; no pip or EPEL is required.

### Offline installation

Download the matching `flagship-airgap-el9-x86_64-1.2.0.dev2.tar.gz` or
`flagship-airgap-el10-x86_64-1.2.0.dev2.tar.gz`. Verify its SHA-256 against the
attached SHA256SUMS, extract it, enter `airgap/` and run
`sudo ./install-offline.sh`. Use only the bundle matching your Rocky major.
A graphical desktop is a prerequisite.

The release workflow builds each major separately, checks offline installation,
and runs the native installed GUI and regression suite with networking disabled.
Earlier live testing completed 16 disposable workflow checks including an XVA
roundtrip; test VMs, snapshots, disks and networks were removed and verified absent.

RPMs are unsigned development packages. SHA256SUMS detects corruption and is not
a signature. Application SRPMs and per-major source archives are attached;
dependency SRPM archives are not included. Full Windows feature parity, guest OS,
multi-host, migration and HA/DR qualification remain incomplete. See the attached
qualification notes and repository docs/CENTER_INTERFACE.md for details.

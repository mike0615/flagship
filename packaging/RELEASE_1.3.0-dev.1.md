**Native Rocky Linux 9/10 development prerelease — no Wine.**

- Redesigned infrastructure workspace: dark inventory navigator, resource icons,
  summary cards, readable capacities, compact contextual actions, back/forward
  navigation and preserved collapsed branches.
- Import/export OVA appliances and standalone qcow2 disks, alongside XVA.
- Docked console with undock/redock, fullscreen, fit and opt-in built-in input.
- Native Virt Viewer option through a one-use authenticated bridge. XAPI session
  credentials remain in Flagship's verified/pinned TLS tunnel.

### Install

Rocky Linux 9:
```bash
sudo dnf install https://github.com/mike0615/flagship/releases/download/v1.3.0-dev.1/flagship-1.3.0-0.1.dev1.el9.noarch.rpm
```
Rocky Linux 10:
```bash
sudo dnf install https://github.com/mike0615/flagship/releases/download/v1.3.0-dev.1/flagship-1.3.0-0.1.dev1.el10.noarch.rpm
```
Launch Flagship from the application menu or run `flagship`. Native qemu-img and
virt-viewer dependencies come from Rocky AppStream and are in the offline bundles.

For a disconnected desktop, download the matching-major airgap archive, verify
SHA256SUMS, extract it, enter airgap/ and run `sudo ./install-offline.sh`.
The graphical desktop is a prerequisite. RPMs are unsigned development packages;
SHA256SUMS checks corruption and is not a signature.

Live XCP-ng testing verified OVA and qcow2 disk-byte roundtrips, dock/undock console
continuity and real Virt Viewer access; disposable resources were removed and
verified absent. The release workflow separately checks native installed packages
on both Rocky majors with networking disabled.

OVA supports a single VM with self-contained disks. This USTAR compatibility
profile limits each converted VMDK file to under 8 GiB; use qcow2 for larger disk
files. Backing chains, split extents, OVF collections/chunking, Secure Boot-required
appliances and vTPM are unsupported. Image conversion does not install guest
storage/NIC drivers. No vCenter/ESXi deployment or installed guest OS migration
qualification is claimed. Read docs/PORTABLE_IMAGES.md and attached qualification
notes for the exact scope.

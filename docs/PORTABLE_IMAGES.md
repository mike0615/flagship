# Portable images and the infrastructure workspace

Flagship 1.3.0.dev1 runs natively on Rocky Linux 9 and 10. Its RPM now includes
native qemu-img and Virt Viewer dependencies from Rocky AppStream. Offline
bundles include those dependencies; there is no Wine or online pip fallback.

## Find and manage objects

The dark inventory navigator stays visible while the workspace changes with
selection. Resource icons and power-state labels distinguish hosts, guests,
storage and networks. Collapsed branches survive inventory refreshes. Use the
filter above the tree for names/UUIDs; Objects groups by type, Organization
Views groups by tags, Saved Searches opens the searchable inventory, and
Notifications opens alerts/tasks. Back/forward buttons revisit selected objects
within the current connection. Double-click search results to open an object.

Summary replaces the raw property dump with resource cards, human-readable
capacity values, management addresses and identity. Advanced properties still
provides the redacted record for troubleshooting. Common VM power commands sit
in a compact action bar; less frequent and destructive commands are under
Actions and the contextual menu. Host selections do not show irrelevant VM
power buttons. The status bar indicates background work.

The design follows the persistent resource navigation and object tabs in the
supplied XCP-ng Center reference, and the summary/action hierarchy shown in
VMware's vSphere Client documentation. It remains an independent native client.

## Export OVA, qcow2 or XVA

Halt the VM, select it and click Export VM (also under VM > Export).
Choose .ova, .qcow2 or .xva. Existing destination files are never overwritten.

- OVA includes CPU count, memory, BIOS/UEFI firmware, network-adapter count and
  all attached virtual disks. Disks are converted to monolithic streamOptimized
  VMDK, packaged with an OVF descriptor and SHA-256 manifest. The descriptor is
  the first tar member. This compatibility profile uses USTAR and requires each
  converted VMDK file to be smaller than 8 GiB; virtual disks may be larger if
  their compressed VMDK is below that limit. qcow2 is available for larger files.
- qcow2 exports one disk. If the VM has several disks, choose which disk to export.
  qcow2 alone does not carry the VM's CPU, memory, firmware or other disk files.
- XVA retains the existing native XAPI appliance workflow.

Export uses the server's VHD disk stream and native qemu-img conversion, with
bounded buffers and a private local staging directory. Temporary disk space may
approach the size of the VM's allocated disk data. The completed file is
published only after task success, conversion and hashing. VM exports require a
halted guest; this candidate does not take automatic snapshots for live export.

## Import an OVA or qcow2 image

Click Import VM, select the file, destination SR and network, then review the
VM name, vCPUs, memory and firmware. OVA defaults come from its descriptor;
qcow2 defaults to two vCPUs, 2048 MiB and BIOS. Choose UEFI when appropriate for
the guest disk. All imported adapters map to the selected destination network,
with new MAC addresses. The new VM remains halted for hardware review.

The importer supports one VM, up to 32 self-contained disks and eight adapters,
with virtual disk capacities up to 2 TiB each. Supported OVA disks are monolithic
sparse/streamOptimized VMDK and standalone qcow2. CPU/memory and hardware must fit
the destination host and selected template. The installer template is cloned;
its identity and disks are not modified. Disk byte capacities are preserved;
VHD conversion explicitly disables CHS geometry rounding.

Archives are parsed without tar.extract. Unsafe paths, duplicate members,
links, non-regular members, XML entities, invalid manifests and encrypted or
externally backed images are rejected. A present SHA-1/SHA-256 manifest is
checked, but is not an authenticity signature. qcow2 backing chains/external
data files, split VMDK extents, OVF collections, Secure Boot-required appliances,
vTPM/encryption/device passthrough and OVF file chunking are not supported.

Disk conversion does not install guest drivers or convert an operating system.
An appliance from VMware/KVM may need storage, NIC, bootloader or Xen guest-tool
changes before it boots correctly. No vCenter/ESXi deployment or installed-guest
migration qualification is claimed. Local parsing/conversion finishes before
creating server resources; a later server failure can leave a partial VM/disk.
Save the workflow report and inspect UUIDs/journals before retrying. There are no
automatic mutation retries or speculative deletion of server resources.

## Docked console and Virt Viewer

Select a running VM, then Console > Connect console. The authenticated native
VNC viewer opens inside the Console tab. Undock turns the same widget into a
window, and Dock returns it without reconnecting or replacing its framebuffer.
Fullscreen is available; Escape exits fullscreen. Fit scales down to integer
pixel ratios; disable Fit for 1:1 viewing and scrolling. Keyboard/mouse input is
opt-in for the built-in viewer. Switching to another VM disables input and hides
that VM's docked console until you return. An undocked console retains its label.

Open in Virt Viewer launches the native remote-viewer program. Flagship keeps
XAPI session cookies in its verified/pinned TLS tunnel. The external viewer gets
only a one-use random VNC password through stdin, connecting to an ephemeral
127.0.0.1 listener. Its challenge is authenticated before the host tunnel opens.
The viewer is shared, so it does not evict another operator. Disconnecting
Flagship closes its viewer bridges. The external viewer has its own keyboard,
mouse, scaling and fullscreen controls, and is intended for interactive access.

VMware Remote Console's VMware-specific connection protocol is not supported by
an XCP-ng XAPI host; remote-viewer supplies the native viewer alternative here.

## References

- Supplied XCP-ng Center 25.4 Interface Reference, main-window and console sections.
- VMware vSphere Client summary/configuration examples:
  https://www.vmware.com/docs/configuration-management-using-vsphere-configuration-profiles
- DMTF OVF 2.1.1: https://www.dmtf.org/sites/default/files/standards/documents/DSP0243_2.1.1.pdf
- QEMU image conversion: https://www.qemu.org/docs/master/tools/qemu-img.html
- XAPI disk endpoints: https://xapi-project.github.io/xen-api/snapshots.html
- Virt Viewer: https://gitlab.com/virt-viewer/virt-viewer/-/raw/master/man/remote-viewer.pod

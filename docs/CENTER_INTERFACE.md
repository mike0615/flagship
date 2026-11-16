# Center-style native desktop

Flagship 1.2.0.dev1 implements the main navigation model in the supplied
XCP-ng Center 25.4 Interface Reference, using Python 3.9+ and Tk 8.6.
It runs as a Linux desktop program on Rocky Linux 9 and 10. No Wine,
Windows .NET, web server, pip packages or online assets are required.

## Navigation

The nine menus are File, View, Pool, Server, VM, Storage, Templates, Tools
and Help. Commands reflect the selected object. VM lifecycle commands use
the server's allowed operations; every server change needs a review or confirmation.
Right-click a host, VM, pool or SR for its commands. F5 refreshes, F1 opens
offline help, Ctrl+N creates a VM, Ctrl+E shuts down a VM, Ctrl+R reboots it
and Ctrl+Y suspends it.

Infrastructure nests connected hosts beneath their pool and resident VMs beneath
hosts. Halted VMs without affinity appear at pool level. Non-shared SRs follow
PBD attachments. Objects groups by type, Organization Views groups by tags,
Saved Searches opens the searchable inventory, and Notifications displays
Alerts and Tasks. The current implementation provides an ad-hoc search filter;
it does not persist named searches. View can show templates, snapshots and
local storage. Tree filtering matches names and UUIDs.

Host pages: General, Memory, Storage, Networking, NICs, GPU, Console,
Performance and Search. VM pages: General, Memory, Storage, Networking,
Console, Performance, Snapshots and Search. SR pages: General, Storage, Search.
Tables sort by clicking column headings. Double-click related objects or search
results to navigate. Select a snapshot row before Revert or Delete; an empty
selection never acts on the parent VM. Delete VM record retains disks.

Inventory refreshes every ten seconds when idle, configurable in View.
This is polling, not an XAPI event subscription. Notifications show server
messages and tasks. Dismiss selected permanently removes that server message.
Submitted task summaries and operation history remain available.

## Creation and editing

New VM has eight steps: Template, Name, Installation Media, Home Server,
CPU & Memory, Storage, Networking, Finish. Review happens before Create Now.
Description, optional home-server affinity and BIOS/UEFI firmware selection
are applied only to the new VM. Template default preserves existing boot
settings; explicit firmware requires an HVM template. Secure Boot and vTPM
configuration are not implemented. The new VM receives one interface; use
Devices for more disks and adapters. Installed templates copy their disks;
installer templates receive the specified new disk.

Properties edits name and description for a VM, host, SR, network or pool.
If a later setter fails, earlier changes remain and the recovery report
identifies the affected object. Other property categories remain read-only.

New Storage Repository supports shared NFS virtual-disk storage and NFS ISO
libraries. Enter the NFS server and absolute export path. The worker uses
SR.create and checks every returned PBD attachment. Partial attachment failure
retains the created SR for inspection. No speculative destroy/forget follows.
iSCSI, SMB and local-disk formatting workflows are not implemented.

Networking > Add Network creates a private network with a validated MTU.
It does not attach a physical NIC, configure VLANs, bond NICs or change the
management address. Use Devices to manage existing VM interfaces.

Server > Enter maintenance mode requires that ordinary resident guests are
halted or migrated first. It disables host placement; it does not evacuate guests
automatically. Reboot and Shut down re-read host state, require a disabled host,
check allowed operations and refuse remaining running/suspended ordinary guests.

## Performance and consoles

Performance > Load history reads /rrd_updates from the selected/resident host
with the same verified/pinned TLS policy as RPC. Ranges: 10 minutes, one hour,
one day or one week. Choose a data source to graph. Units are the server's raw
data-source units; missing/non-finite samples are omitted, with gaps left open.
History is loaded explicitly, not fabricated or continuously refreshed. Pool
members must have trusted certificates for their management address.

Console opens the existing native TLS VNC viewer in a separate window.
Input is opt-in. Host text console, integrated RDP, fullscreen docking and
clipboard synchronization remain outside this candidate.

## XVA transfer

File > Import XVA uploads a validated local XVA archive to selected writable
storage, remaps the imported guest's interfaces to the selected network and
leaves the guest halted. VM > Export XVA exports a halted VM, template or
snapshot to a new filename. OVF, OVA and raw-disk imports are not implemented.

Transfers stream through bounded buffers, authenticate TLS before sending
session cookies and do not retry failed mutations. Uploads wait for HTTP 100
Continue. Redirects must identify a verified member of the connected pool and
preserve the operation parameters. Task success and complete tar framing are
required before a private export partial file is published. Existing files are
never overwritten. Tools > Save workflow report retains paths, task references
and SHA-256 values. Interrupted imports may leave server resources; inspect them
before retrying. Stop workflow monitoring does not roll back server changes.

## Qualification boundary

Tests exercise synthetic records and simulated XAPI responses. Container builds,
network-disabled installs and GUI construction demonstrate native packaging,
not live host compatibility or complete Windows feature parity. Advanced HA,
DR, WLB, updates, pool membership, vApps, scheduled snapshots, host consoles,
OVF/OVA and advanced network/storage editors still need implementation.

Screenshots in docs/screenshots/center-*.png use synthetic demonstration data.

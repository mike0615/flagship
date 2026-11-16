# Supplied Windows source review

Input: `/home/mike/Downloads/xenadmin-25.04`, dated April 29, 2025.
File-level SHA-256 inventory: `upstream/SHA256SUMS`.
This is a targeted architectural and workflow review, not a claim that every line
of the Windows application has been audited.

## Architecture and portability boundaries

`XenAdmin/XenAdmin.csproj` targets `net481` and `UseWindowsForms=true`.
It references `AxMSTSCLib`, `MSTSCLib`, System.Management and WinForms ReportViewer.
Its prebuild invokes Windows `aximp.exe` on `mstscax.dll`. These dependencies
prevent a direct native Rocky rebuild.

`XenModel/XenAPI` contains the generated session, VM, host, storage and network
API models. `Session.cs` logs in with username, password, API version and originator.
The native implementation uses the documented XML-RPC wire format instead of
recompiling those Windows-oriented dependencies.

`XenModel/Actions/VM` separates lifecycle, cloning, snapshots, migration, disks,
VCPU/memory configuration and import/export workflows. The native action dispatcher
maps its supported operations to XAPI methods; complex provisioning and transfer
workflows require their own validation rather than generic raw RPC access.

`XenAdmin/TabPages` defines general, storage, networks, performance, snapshots,
alerts and history views. The first native interface mirrors resource navigation
and inventory categories, with structured property displays. It does not yet
match the Windows tables, charts or wizards visually.

`XenAdmin/Wizards` includes new VM, network, SR, HA, DR, migration and import/export.
The feature matrix distinguishes these from basic API operation submission.

## Existing work discovered

`mike0615/xcp-ng-center-rocky` was private at inspection. Its documented approach
uses Wine, winetricks and Windows .NET Framework. Its own known-limitations file
identifies COM/RDP, reporting and plugins as unresolved. It is not used as evidence
of a native or offline-qualified release; it has not been modified or made public.

## Primary API references

- https://xapi-project.github.io/xen-api/wire-protocol.html
- https://xapi-project.github.io/xen-api/classes/vm.html
- https://xapi-project.github.io/xen-api/importexport.html
- https://xapi-project.github.io/xen-api/consoles.html

The VM reference specifies clone followed by provision for template creation.
Import/export and console connections have separate HTTP protocols; a VM RPC
alone does not implement those features. Feature status must reflect that distinction.

The next native creation workflow follows `CreateVMAction.cs`: copy installed
custom templates to a selected SR, remove the template provisioning `disks` entry
when explicitly creating storage, provision, and replace the new VM's inherited
VIFs with the chosen networking. Partial failures retain references instead of
attempting speculative deletion. `ChangeVCPUSettingsAction` ordering is mirrored
when reducing vCPUs (startup before maximum). The XML-RPC wire reference also
requires decimal-string integer encoding and opaque references; regression checks
cover values above XML-RPC int32 and non-OpaqueRef-shaped task references.

## Device and recovery work (dev.3)

The native device actions follow the separation in
`XenModel/Actions/VDI/{DetachVirtualDiskAction,DestroyDiskAction}.cs`: remove a
connection versus explicitly destroy its underlying disk. Unlike a cleanup in a
finally block, a rejected native unplug stops before connection removal. The
native data-delete operation additionally requires the exact disk UUID and rejects
shared/read-only/snapshot or other-associated disks. This is a deliberate safety
boundary, not a claim to implement every advanced Windows storage workflow.

`VIF.move` is used for network changes where the server supports it, preserving
adapter identity/MAC rather than deleting and recreating the VIF. Unsupported
server methods fail explicitly; there is no destructive fallback. Online growth
uses the server's advertised allowed operations rather than assuming support from
a product version alone. Required VBD/VIF/VDI constructor fields were checked
against the supplied generated classes and the primary XAPI reference.

The native operation journal records intent before mutation RPCs, returned outcomes,
observed UUIDs/task states and structural workflow progress. It does not serialize
login parameters or raw RPC arguments. A read-only inspector resolves fresh
references through get_by_uuid and verifies UUID identity; history never replays
stored operations. Task cancellation requests remain distinct from terminal task
outcomes, consistent with https://xapi-project.github.io/xen-api/classes/task.html.

## November 16 Center interface work

New input: the supplied `11-16-2026/xenadmin-development` tree and the
XCP-ng Center 25.4 Interface Reference and XenCenter PDF. Their exact hashes
are in `upstream/2026-11-16-SHA256SUMS`; original inputs were preserved.
The Word reference's main-window anatomy, object tab lists and wizard steps
informed the native shell. The PDF's navigation, VM/storage/network and
performance sections provided supporting workflow context. These references
are not redistributed as app assets.

The supplied `XenModel/Actions/SR/SrCreateAction.cs` defines SR.create argument
ordering and post-create PBD verification. `NFS_ISO.cs` specifies the
`location` and `type=nfs_iso` device config. `NetworkAction.cs` distinguishes
private network.create from physical/VLAN attachment. `CreateVMAction.cs`
sets HVM_boot_params firmware to bios/uefi. `ArchiveMaintainer.cs` specifies
RRD /rrd_updates query parameters and resident-host selection. The native
implementation follows these interfaces without porting WinForms/COM.

The existing feature/xva-transfer branch supplied httpstream.py, transfers.py,
xva.py and their tests. Integration updates use current TrustPolicy wrapping,
validate local XVA framing before uploading, persist recovery file paths,
and record imported VM UUIDs. No source-wide replacement from that older
branch was performed. See CENTER_INTERFACE.md for implemented scope and gaps.

## Live XVA import protocol correction

The live XCP-ng 8.3.0 host exposed two differences from the simulated transfer
server. XAPI's Import.handler sends HTTP 200 with a Task-Id before reading the
archive. Import completion stores a VM-reference set in the task result. The
native transport now binds early readiness to the exact task and the import
workflow decodes exactly one member. No generic HTTP 200 response grants upload
permission, and HTTP readiness never replaces successful task confirmation.
The supplied XenAPI/HTTP.cs HttpPutStream/Put implementation also treats the
initial successful response as the upload stream being ready.

Primary server source:
https://github.com/xapi-project/xen-api/blob/master/ocaml/xapi/import.ml

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

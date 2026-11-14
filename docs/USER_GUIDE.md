# XenAdmin Rocky user guide

## Start and connect

Launch XenAdmin Rocky from the desktop menu or run `xenadmin-rocky`.
Use a graphical Rocky Linux session. Click Connect and enter the HTTPS address
of the pool coordinator, such as `https://pool.example.internal`. Enter your
XAPI username and password. Passwords remain in process memory while connecting
and are not saved to disk. Use an account with the permissions needed for your task.

For an internal CA, provide its PEM file in the connection dialog or install the
trusted CA through Rocky's system trust mechanism. Certificate hostname and chain
verification are required. Use the DNS name listed in the certificate.
If a member reports HOST_IS_SLAVE, reconnect explicitly to the trusted coordinator;
the application does not forward credentials to an automatically supplied address.

Expected result: pool and host inventory appears. Missing inventory classes are
listed in the status bar; a partial inventory is not a complete health assessment.

## Navigate and inspect

Expand Pools, Hosts, Virtual machines, Templates, Snapshots, Storage or Networks.
Select an object. General shows its properties, Storage and Networking show related
devices, Snapshots shows the selected VM's snapshots. Tasks and Alerts show pool
records. Enter part of a name or UUID in the filter field to narrow the tree.
Refresh explicitly to obtain current records; there is no automatic event stream.
An empty related-device view does not prove healthy storage or networking.

## Change a VM

Select a VM and click an action. The application checks the last fetched
allowed_operations and asks for confirmation. The server makes the final permission
and state check. Refresh before acting if another administrator may have changed it.
Start/resume request a running, unpaused VM. Shutdown/reboot use guest-aware calls;
guest tools may be required. Force off can lose unsaved guest data.

Snapshot and Clone ask for a name. Clone submits a clone operation only; this is
not the complete new-VM provisioning wizard for a template. Revert snapshot can
replace the VM's current disk state. Keep an independent backup before reverting.
Migrate in pool asks for a host reference listed in the dialog; cross-pool migration
is not supported. Rename changes the label. Delete VM record removes metadata;
it deliberately leaves disks, which may need separately reviewed storage cleanup.

Expected result: submission returns and inventory refreshes. A returned task is
not proof of success. Open Tasks, refresh and inspect status, progress and error_info.
Tasks submitted by this session are checked every three seconds, and confirmed
outcomes appear in Tasks. A connection/session error pauses monitoring until a
successful refresh or reconnection. Other pool tasks require a manual refresh.
Pending tasks may outlive this application. On a disconnect, inspect task and VM
state before retrying; the client never automatically retries a mutation.

## Export and help

Export inventory writes local JSON. Selected credential/location fields are
redacted, but VM names, addresses and other infrastructure details remain sensitive.
Inspect the file before sharing. Help opens this installed guide without internet.

## Disconnect and exit

Disconnect requests session logout. Wait for the current network operation before
closing. Logout does not cancel running server tasks. If the host is unreachable,
its session may remain until the server expires it. No credentials are remembered
for the next launch. See OPERATIONS.md for recovery and INSTALL.md for removal.

## Create a virtual machine (development tree after dev.1)

Choose New VM. Select a halted template, name, vCPU count, memory in MiB, writable
storage repository, network, and optional ISO. The disk size applies to installer
templates without allocated data disks. Installed-template disks are copied to the
selected SR with their contents and existing sizes; the disk-size entry does not
resize them. The new VM receives one NIC on the selected network. Additional
NICs and disk/device editing are separate work still under development.

Review the summary before choosing Create. No server changes occur during form
entry or review. Start after creation is optional and defaults off. The workflow
waits for each asynchronous task to succeed before continuing. For offline guest
installation, select an ISO already available on the pool's ISO repository.
The client does not download operating system installation media.

If monitoring must stop, choose Tools → Stop workflow monitoring. This stops further
client workflow steps; an already submitted server task may continue. The client
does not guess whether a timed-out mutation succeeded and never replays it.
On failure, retain the recovery information and use Tools → Save workflow report.
It contains created resource/task references and must be treated as infrastructure
metadata. Inspect those objects through trusted pool administration before retrying
or deleting anything. No automatic cleanup is attempted after an uncertain result.

## Edit CPU and memory (development tree after dev.1)

Select a halted, ordinary VM and choose CPU / memory. Enter the vCPU count and
fixed memory size in MiB, then confirm. Maximum/startup vCPUs are set to the same
count; dynamic minimum/maximum memory are set to the fixed size while preserving
the server's static minimum. Running VMs, snapshots and templates are rejected.
The server remains responsible for capacity, permissions and license restrictions.
A failed sequence may have applied earlier settings: save the workflow report,
refresh and inspect the VM before deciding how to recover. Dynamic memory ranges
and live CPU changes are not yet exposed by this editor.

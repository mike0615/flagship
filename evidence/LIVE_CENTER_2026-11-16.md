# Live Center qualification, 2026-11-16

A user-authorized XCP-ng 8.3.0 host was exercised through the native Python
client over HTTPS with a session-only SHA-256 certificate pin. Credentials
were entered through an echo-disabled prompt, never saved in source, reports,
command arguments or operation journals. Host addresses, full inventory and
private run manifests are not published here.

## Read-only checks

- Native XAPI login/logout and every requested inventory class succeeded.
- Host and running-VM RRD history parsed into finite time-series samples.
- Shared authenticated VM RFB console handshake and framebuffer read succeeded;
  no input was sent to an existing guest.
- Native Tk host, VM, SR and Notifications views rendered the live inventory.

## Isolated mutation checks

The user approved disposable resources on an existing local SR with private
networks. Existing VMs, source templates, management networking, host power,
SR configuration and pool membership were not changed.

Sixteen checks completed: TLS/login; halted-VM provisioning; disk growth;
detach preserving disk identity; explicit extra-disk deletion; empty DVD
lifecycle; NIC move preserving UUID/MAC; VM start, pause, unpause and hard
shutdown; name/description editing; snapshot ownership; snapshot revert to a
halted state; complete XVA export; and XVA import to a separate halted VM with
selected networking. All mutations targeted this run's named resources.

The first import stopped before uploading its body because the client expected
HTTP 100 Continue. The server returned its XAPI early HTTP 200 readiness
response. The server task was inspected and confirmed failed with premature
EOF before a new explicit import attempt. No automatic mutation retry occurred.

The fix accepts early HTTP 200 only when its Task-Id matches the requested
transfer task, retains certificate verification, and still requires final task
success. XAPI's import task returns a singleton VM-reference set; this now has
a dedicated decoder, without loosening scalar clone/copy task result handling.
The corrected import streamed the 2,126,336-byte disposable export and completed.

Explicit cleanup resolved only recorded UUIDs, checked storage and associations,
destroyed disposable snapshots/VMs/disks/networks, and retained private journals.
A separate post-cleanup inventory found zero remaining test VMs, snapshots,
VDIs or networks by either recorded UUID or run prefix.

## Boundaries

These tests used a firmware-only disposable VM. They do not establish graceful
guest shutdown, installed-guest input, guest hotplug, real NFS/iSCSI/SMB creation,
HA/DR, migration, multiple hosts, restricted roles or full Windows feature parity.
Host maintenance/power actions were not executed on the user's running host.
Native Rocky 9/10 package checks are recorded separately.

## Reproduction

`qa/live_center_smoke.py` provides the isolated protocol/device/snapshot/XVA
workflow. It requires --execute, an explicit SR UUID and expected endpoint
certificate pin. It prompts for credentials. `qa/cleanup_protocol.py` accepts
--pin and performs scoped cleanup from the private manifest. Review both
scripts and authorize the target resources before running them on another host.

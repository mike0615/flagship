# Operations, security and recovery

## Trust and privileges

The desktop runs as the logged-in user and binds no listening ports. Installation
requires administrator privileges; ordinary use does not. Use HTTPS and least
privilege XAPI accounts. No TLS bypass is provided. Do not place passwords or
session references in commands, screenshots or support tickets. The application
does not save passwords; Python memory cannot guarantee secure secret erasure.
No telemetry, remote assets or online update checks are used by the native client.

## Troubleshooting

| Symptom | Check | Expected outcome |
|---|---|---|
| No module named tkinter | Installed python3-tkinter RPM | `python3 -c 'import tkinter'` exits 0 |
| No display | Log into graphical desktop; check DISPLAY | A local Tk window can open |
| Login fails | DNS, certificate name/chain, account, coordinator | Trusted coordinator returns inventory |
| Partial inventory | Status bar and RBAC | Account can read intended classes |
| Action unavailable | Refresh, power state, allowed_operations | Server permits intended operation |
| Task remains pending | Refresh Tasks and check host externally | Task reaches success or failure |
| Session expires | Disconnect then reconnect | New session with fresh credentials |
| Offline dependency error | Correct Rocky major/architecture bundle | DNF resolves using only local RPMs |

Network errors deliberately omit request arguments and tracebacks from dialogs.
Record the time, selected operation, application/Rocky version and sanitized server
error/task state. Use the established host management tool to inspect uncertain
outcomes; never repeatedly submit destructive actions to test connectivity.

## Recovery and rollback

The application does not modify the host until an action is confirmed. Closing or
uninstalling it does not roll back server changes. Restore guests from independently
verified backups for data recovery. Before revert/delete/force-off, record the VM
UUID, disk associations and backup location through your approved tools.

For client rollback install a previously retained RPM with DNF downgrade using
only the corresponding offline dependency set. Retain package SHA-256 manifests.
There is no application database or credential store to migrate. Server tasks are
owned by XAPI, not by the client process.

## Persistent recovery records (dev.3)

The client records operation intent before changes, observed server outcomes and
workflow transitions in a private owner-only state directory. It excludes login
parameters, raw RPC arguments and API session tokens. The files do retain sensitive
infrastructure metadata and survive client restart/uninstall. See RECOVERY.md for
paths, record semantics, retention/view limits, inspection by UUID and journal
storage-failure recovery. These records never cause automatic RPC replay.

An unavailable journal blocks further changes; read-only inventory/inspection can
still be used to investigate. Permanent disk-data deletion is distinct from detach,
requires the exact UUID and refuses shared/snapshot/read-only or other-associated
disks. A rejected unplug stops removal. Coordinate destructive operations with
other administrators and retain independent backups; client checks are not a
server-wide transaction locking every competing administrative client.

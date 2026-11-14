# Feature matrix

Implemented means code exists, not that it has passed live host qualification.
See QUALIFICATION.md for the evidence boundary.

| Windows workflow | Native candidate | Remaining qualification/work |
|---|---|---|
| Connect, TLS trust, login/logout | Implemented, one pool at a time | Live trusted TLS/login passed; restricted RBAC and pool coordinator tests remain |
| Resource tree, search | Implemented | UI/operator validation |
| General, storage, network properties | Structured inventory tabs | Rich editors and polished tables |
| VM start, shutdown, reboot | Async operation submission | Task completion and guest behavior |
| Force shutdown | Confirmed async submission | Live firmware VM start/force shutdown passed; guest OS validation remains |
| Pause/unpause/suspend/resume | Async operation submission | State transitions on host |
| Clone, snapshots, revert | Async operation submission | Disk relationships and rollback |
| Rename | Synchronous setter | Live permission/state tests |
| Same-pool migration | Async submission with host selection | Live migration and compatibility |
| Delete VM record | Confirmed async submission, disks retained | Disk lifecycle cleanup wizard |
| Tasks and alerts | Submitted-task outcomes, cancellation requests, persistent operation history | Live cancellation qualification, alert actions and advanced history/report views |
| Inventory export | Local JSON, selected credential fields redacted | Review metadata before sharing |
| New VM wizard | Template clone/copy, selected SR, disk, one NIC, optional ISO/start | Live installer-template provisioning passed; installed-template copy, additional NICs/disks and advanced installation options remain |
| CPU/memory editing | Halted VM vCPU and fixed-memory editor | Live qualification, dynamic memory and live CPU controls |
| Disk, ISO, VIF editing | Add/attach/grow/rename/detach/delete disks, DVD/ISO lifecycle, NIC add/move/connect/remove | Live cold disk/DVD/NIC checks passed; guest hotplug, advanced QoS/slots/MAC edits, specialized devices and storage migration |
| SR/network creation | Not implemented | Validated creation wizards |
| XVA/OVF import and export | Not implemented | Streaming transfer and task/error handling |
| Embedded VNC/RDP console | Development-source TLS console viewer, raw/CopyRect/resize and opt-in input; not in dev.3 RPMs | Live firmware handshake/pixels/input transmission passed; interactive guest input, installer, RDP and advanced viewer features remain |
| Performance graphs | Not implemented | RRD collection and graph UI |
| Host updates, HA, DR, WLB | Not implemented | Dedicated workflows and entitlement tests |
| Cross-pool migration | Not implemented | Transfer networks and credential boundaries |
| Windows plugins/ReportViewer | Not implemented | Linux replacement design |
| Multiple saved pool connections | Not implemented | Secure connection profiles |
| Offline help | Indexed installed chapters, including recovery; no browser/network | Booted-desktop operator verification |

A v1.0 of the full requested compatibility scope cannot be declared from this
candidate. Expand and test the missing workflows before a parity-oriented release.

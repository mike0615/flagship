# Feature matrix

Implemented means code exists, not that it has passed live host qualification.
See QUALIFICATION.md for the evidence boundary.

| Windows workflow | Native candidate | Remaining qualification/work |
|---|---|---|
| Connect, TLS trust, login/logout | Implemented, one pool at a time | Live TLS, RBAC and pool coordinator tests |
| Resource tree, search | Implemented | UI/operator validation |
| General, storage, network properties | Structured inventory tabs | Rich editors and polished tables |
| VM start, shutdown, reboot | Async operation submission | Task completion and guest behavior |
| Force shutdown | Confirmed async submission | Disposable VM validation |
| Pause/unpause/suspend/resume | Async operation submission | State transitions on host |
| Clone, snapshots, revert | Async operation submission | Disk relationships and rollback |
| Rename | Synchronous setter | Live permission/state tests |
| Same-pool migration | Async submission with host selection | Live migration and compatibility |
| Delete VM record | Confirmed async submission, disks retained | Disk lifecycle cleanup wizard |
| Tasks and alerts | Submitted-task progress/outcomes; pool inventory display | Live qualification, persistent history, cancel and alert actions |
| Inventory export | Local JSON, selected credential fields redacted | Review metadata before sharing |
| New VM wizard | Template clone/copy, selected SR, disk, one NIC, optional ISO/start | Live provisioning, additional NICs/disks and advanced installation options |
| CPU/memory editing | Halted VM vCPU and fixed-memory editor | Live qualification, dynamic memory and live CPU controls |
| Disk, ISO, VIF editing | Not implemented | Full device lifecycle |
| SR/network creation | Not implemented | Validated creation wizards |
| XVA/OVF import and export | Not implemented | Streaming transfer and task/error handling |
| Embedded VNC/RDP console | Not implemented | Authenticated console tunnel and viewer |
| Performance graphs | Not implemented | RRD collection and graph UI |
| Host updates, HA, DR, WLB | Not implemented | Dedicated workflows and entitlement tests |
| Cross-pool migration | Not implemented | Transfer networks and credential boundaries |
| Windows plugins/ReportViewer | Not implemented | Linux replacement design |
| Multiple saved pool connections | Not implemented | Secure connection profiles |
| Offline help | Included with RPM | Clean install verification |

A v1.0 of the full requested compatibility scope cannot be declared from this
candidate. Expand and test the missing workflows before a parity-oriented release.

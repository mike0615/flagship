# Qualification record

Development status. This record must be updated with evidence, not assumptions.

| Gate | Status |
|---|---|
| Targeted Windows source architectural review | Completed; SOURCE_ANALYSIS.md |
| Native implementation and feature-gap inventory | Initial implementation; FEATURE_MATRIX.md |
| Unit/security regression tests | 117 passing local checks including device states, durable journal failures/restarts, UUID inspection, real TLS and GUI; dev.3 disconnected install and installed GUI/help/recovery checks passed on both Rocky majors |
| Rocky 9 RPM build | dev.1/dev.2/dev.3 pass |
| Rocky 10 RPM build | dev.1/dev.2/dev.3 pass |
| Rocky 9 clean disconnected desktop installation | Pending |
| Rocky 10 clean disconnected desktop installation | Pending |
| Installed GUI and help in network-disabled containers | dev.3 installed New VM/device tables/indexed help/history/recovery CLI pass on both majors |
| Reboot and graphical desktop menu interaction | Pending booted VMs |
| Trusted TLS, read-only and restricted account behavior | Verified trusted TLS/native login on live XCP-ng; restricted-role qualification pending |
| Disposable guest lifecycle, snapshots, restore, migration | Live provisioning, cold devices and firmware start/pause/unpause/shutdown pass; guest OS, snapshots, restore and migration pending |
| Windows workflow comparison and independent operator | Pending |
| Offline dependency resolution | dev.1/dev.2/dev.3 pass in fresh network-disabled containers |
| Dependency license inventory and source retention | License identifiers and exact SRPM coverage recorded for all 83/el9 and 85/el10 binary RPMs; dev.2 uses baseline plus source delta |
| Stable v1.0 | Not qualified |

Container checks can establish package installation and GUI creation, but do not
replace a booted desktop, live hypervisor or independent operator journey.

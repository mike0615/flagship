# Qualification record

Development status. This record must be updated with evidence, not assumptions.

Flagship 1.1.0.dev1 is the rebrand of the XenAdmin Rocky 1.0.0.dev4 development
tree (package, commands, icon, journals and documentation). Historical rows
below keep the candidate names under which the evidence was collected. The
rename itself does not qualify a stable v1.0.

| Gate | Status |
|---|---|
| Targeted Windows source architectural review | Completed; SOURCE_ANALYSIS.md |
| Native implementation and feature-gap inventory | Initial implementation; FEATURE_MATRIX.md |
| Unit/security regression tests | Published dev.3 baseline: 117 checks; console development branch: 141 checks, including 1024x768/narrow-window layout; dev.3 disconnected container install/GUI/help/recovery passed on both Rocky majors |
| Rocky 9 RPM build | dev.1/dev.2/dev.3/dev.4 pass |
| Rocky 10 RPM build | dev.1/dev.2/dev.3/dev.4 pass |
| Rocky 9 clean disconnected desktop installation | dev.3 installed from the transferred local bundle during isolated Rocky 9.6 Workstation installation; booted GNOME, native application and indexed help observed |
| Rocky 10 clean disconnected desktop installation | Pending |
| Installed GUI and help in network-disabled containers | dev.4 installed New VM/device tables/indexed help/history/recovery CLI and console rendering/clean closure pass on both majors |
| Reboot and graphical desktop menu interaction | Rocky 9 installer reboot, subsequent clean installed-system reboot with distinct boot IDs, repeated application checks and manual desktop-search/menu launch passed; Rocky 10 pending |
| Trusted TLS, read-only and restricted account behavior | Verified trusted TLS/native login on live XCP-ng; restricted-role qualification pending |
| Disposable guest lifecycle, snapshots, restore, migration | Live provisioning, cold devices and firmware start/pause/unpause/shutdown pass; guest OS, snapshots, restore and migration pending |
| Windows workflow comparison and independent operator | Pending |
| Offline dependency resolution | dev.1/dev.2/dev.3/dev.4 pass in fresh network-disabled containers |
| Dependency license inventory and source retention | License identifiers and exact SRPM coverage recorded for all 83/el9 and 85/el10 binary RPMs; dev.2 uses baseline plus source delta |
| Stable v1.0 | Not qualified |

Container checks can establish package installation and GUI creation, but do not
replace a booted desktop, live hypervisor or independent operator journey.

Console development branch: 141 local checks pass under a 1024x768 X display.
The booted dev.3 guest exposed a small-display layout issue. Source now fits the
screen, wraps toolbar actions, reserves space for VM actions/status and cancels
pending Tk timers on destruction. These source fixes are not in dev.3 RPMs.
Public progress does not qualify Rocky 10 or a complete stable v1.0.

The dev.4 RPMs built from source commit 201a547 passed fresh disconnected container
installs and the installed GUI fixture on both Rocky majors. No booted dev.4 or
Rocky 10 desktop success is inferred from those checks.

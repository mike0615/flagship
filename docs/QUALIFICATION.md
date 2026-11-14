# Qualification record

Development status. This record must be updated with evidence, not assumptions.

| Gate | Status |
|---|---|
| Targeted Windows source architectural review | Completed; SOURCE_ANALYSIS.md |
| Native implementation and feature-gap inventory | Initial implementation; FEATURE_MATRIX.md |
| Unit/security regression tests | 51 passing local tests, including stateful provisioning simulations and real TLS/XML-RPC; see evidence/provisioning-tests.txt |
| Rocky 9 RPM build | dev.1 and dev.2 pass: separate major-specific container builds |
| Rocky 10 RPM build | dev.1 and dev.2 pass: separate major-specific container builds |
| Rocky 9 clean disconnected desktop installation | Pending |
| Rocky 10 clean disconnected desktop installation | Pending |
| Installed GUI and help in network-disabled containers | dev.2 pass on both majors: installed New VM review and built-in help under Xvfb |
| Reboot and graphical desktop menu interaction | Pending booted VMs |
| Trusted TLS, read-only and restricted account behavior | Pending live host |
| Disposable guest lifecycle, snapshots, restore, migration | Pending live host |
| Windows workflow comparison and independent operator | Pending |
| Offline dependency resolution | dev.1 and dev.2 pass on both fresh base containers, local repository only |
| Dependency license inventory and source retention | License identifiers and exact SRPM coverage recorded for all 83/el9 and 85/el10 binary RPMs; dev.2 uses baseline plus source delta |
| Stable v1.0 | Not qualified |

Container checks can establish package installation and GUI creation, but do not
replace a booted desktop, live hypervisor or independent operator journey.

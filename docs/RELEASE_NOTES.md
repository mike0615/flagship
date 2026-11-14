# Release notes

## 1.0.0.dev3 — in development

Disk/DVD/NIC management, separate detach versus permanent disk deletion, private
fsync operation journals, recovery/history after restart, UUID inspection in GUI
and headless CLI, cancellation requests, named-host migration selection, and an
indexed offline help viewer. Explicit JSON exports use private permissions.
114 local checks pass; current package builds/install checks are pending.
Full Windows parity, live pool and booted/independent-operator qualification remain
open. Journals never replay changes or guarantee automatic rollback.

## 1.0.0.dev2 — development candidate, November 14, 2026

Submitted task tracking now distinguishes server-confirmed outcomes from submission.
Monitoring pauses on connection/session errors; mutations are never replayed.
51 local API/TLS/task/provisioning/desktop checks pass. New VM review/provisioning,
selected SR/network/ISO, installed-template disk copy, recovery reports and halted
VM CPU/fixed-memory configuration are implemented. XAPI integers are encoded as
decimal strings and references are opaque. Outputs are isolated by app version.
These changes are not included in the published dev.1 RPMs. Both dev.2 RPMs
passed disconnected container installation, installed New VM review and offline
help checks. GitHub CI tests and both Rocky builds passed. Live hypervisor and
booted desktop qualification remain open.


## 1.0.0.dev1 — development candidate, November 14, 2026

Initial native Python/Tk client, HTTPS XAPI transport, mandatory certificate
verification, resource inventory, basic VM action submission, redacted JSON export,
offline help, RPM specification and airgap bundle tooling.

No stable v1.0 has been released. Full Windows feature parity, Rocky 9/10 clean
installation, disconnected dependency resolution and live guest workflows remain
release gates. Do not interpret the RPM version field 1.0.0 as a stable release:
the RPM release is explicitly `0.1.dev1`.

Known limitations and missing features are in FEATURE_MATRIX.md. This client has
no saved settings, import/export engine, embedded console, updater or Windows
plugin compatibility. The original Windows client remains a separate application.

### Candidate verification evidence

20 tests passed locally and GitHub CI passed tests and both RPM jobs. Final RPMs
installed in network-disabled Rocky 9 and 10 base containers using only the bundled
file repository; the installed GUI also opened under Xvfb on each major. Help is
application data so RPM `nodocs` settings cannot suppress it. All bundled binary
RPMs have corresponding source RPMs retained in the separate dependency-source
archives. This evidence does not qualify booted desktops or live guest workflows.

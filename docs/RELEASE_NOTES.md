# Release notes

## 1.0.0.dev4 — in development

Authenticated native RFB console window, opt-in keyboard/mouse input, full repaint
after resize, held-modifier preservation, display-aware main-window sizing and
wrapped toolbar controls. VM actions/status stay visible on small displays.
141 local checks pass, including a 1024x768 client display and narrower windows;
new RPM qualification is pending. Actual live Tk-console rendering passed.
The published dev.3 RPMs passed an isolated Rocky 9.6 Workstation install, clean
installed-system reboot, repeated application/help/recovery checks and desktop
menu launch. These guest results do not qualify dev.4 RPMs or Rocky 10.
Rocky 10 media is verified and its adapted QA seed passes syntax validation; its
booted desktop run remains pending. Full Windows scope and stable v1.0 remain open.

## 1.0.0.dev3 — development candidate, November 14, 2026

Disk/DVD/NIC management, separate detach versus permanent disk deletion, private
fsync operation journals, recovery/history after restart, UUID inspection in GUI
and headless CLI, cancellation requests, named-host migration selection, and an
indexed offline help viewer. Explicit JSON exports use private permissions.
117 local checks pass. Both RPM builds and remote CI passed; fresh disconnected
installations and installed GUI/help/recovery checks passed on Rocky 9 and 10
containers. These container checks do not qualify booted Rocky desktops.
Live XCP-ng provisioning, cold devices and firmware power-state checks now pass;
see `evidence/LIVE_PROTOCOL.md`. Full Windows parity and booted Rocky desktop /
independent-operator qualification remain open. Journals never replay changes or guarantee automatic rollback.

## 1.0.0.dev2 — development candidate, November 14, 2026

**Known provisioning defects found during subsequent live testing:** implicit XML-RPC
string task results were rejected after a successful clone; template conversion
also occurred before provisioning. A failed attempt can leave a halted partial
clone. Inspect existing tasks/resources before retrying. Both defects are corrected
in dev.3 source; dev.2 RPMs remain affected.

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

# Release notes

## Unreleased after dev.1

Submitted task tracking now distinguishes server-confirmed outcomes from submission.
Monitoring pauses on connection/session errors; mutations are never replayed.
29 local API/TLS/task/desktop checks pass. These changes are not included in the dev.1 RPMs.


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

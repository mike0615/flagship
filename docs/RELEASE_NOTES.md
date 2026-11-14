# Release notes

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

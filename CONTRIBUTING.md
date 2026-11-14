# Contributing

Review the feature matrix and qualification record before changing scope. Keep
network operations off the Tk thread, verify TLS, avoid credential persistence,
and do not automatically retry mutations. Add meaningful API/state regression
tests for management changes. Never use a production guest for destructive tests.

Run unit tests and a GUI smoke test, build for each Rocky major and record the
exact evidence boundary. Do not call task submission task completion. Keep RPMs,
dependency bundles and generated artifacts out of Git history. Retain upstream
notices and audit bundled dependencies before redistribution.

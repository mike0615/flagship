# Changelog

## 1.2.0.dev2 — 2026-11-16

- Live XCP-ng qualification found an import compatibility issue: accept the
  task-matched early HTTP 200 readiness response used by XAPI and decode
  its singleton VM-set task result. Ordinary HTTP 200 responses without the
  exact transfer task ID still cannot receive an archive.
- Disposable VM/device/snapshot and XVA roundtrip checks completed on a live
  XCP-ng 8.3.0 host; test resources were explicitly cleaned up.

## 1.2.0.dev1 — 2026-11-16

- Native Center-style navigation, contextual menus/tabs, relationship-scoped
  sortable tables, tags, search, notifications and idle inventory refresh.
- Eight-step VM wizard with description, home-server affinity and BIOS/UEFI.
- Reviewed host maintenance/power actions, identity properties, NFS SR/ISO
  creation, private networks, SR rescans/defaults and alert dismissal.
- RRD history graph and integrated task-confirmed streaming XVA transfers.
- Reuses the existing transfer branch while applying current certificate
  pinning and preserving partial-file and imported-object recovery details.
- Rocky 9/10 package and offline qualification recorded separately.


All notable changes to Flagship (formerly XenAdmin Rocky). Detailed notes are
in [docs/RELEASE_NOTES.md](docs/RELEASE_NOTES.md).

## 1.1.0.dev2 — 2026-11-15

### Added
- **Trust prompt for self-signed or unverifiable host certificates.** It shows
  the subject, issuer, validity dates and SHA-256 fingerprint, with
  **Connect once**, **Always trust this certificate** and **Cancel**
  (the default). Pins are stored per `host:port` in
  `~/.config/flagship/known_certs.json` (0600, directory 0700).
- Pinned hosts are accepted when the presented certificate's fingerprint
  matches, even when it is self-signed or the name doesn't match. The check
  runs right after the handshake, before any request, credential or console
  cookie is sent, on both the XML-RPC connection and the console TLS socket.
- **Changed-certificate warning**: a pinned host with a different certificate
  gets a red "certificate has changed" dialog showing both fingerprints and is
  asked again. It is never accepted automatically.
- **Ignore SSL certificate errors (insecure)** checkbox in the connect dialog,
  with a one-line warning and a red **Insecure TLS** status-bar marker. It
  covers RPC and console for that connection only.
- `flagship --insecure` pre-ticks the checkbox. `flagship-recovery inspect`
  adds `--pin SHA256`, `--insecure` and `--no-saved-pins` and honors GUI pins
  by default.
- **Tools ▸ Trusted certificates…** lists and removes saved pins.
- Help chapter *Self-signed XCP-ng certificates* (docs/TLS_CERTIFICATES.md) and
  an About note. Screenshots are in docs/screenshots/.
- Tests: local self-signed TLS servers on 127.0.0.1 for verify failure, pin
  accept, pin mismatch rejection (nothing sent) and insecure accept, covering
  RPC and console.

### Fixed
- The RPM now ships its own bytecode. On Rocky 10, file times are clamped to
  the changelog date, so after an upgrade Python could reuse `__pycache__`
  files left by an earlier build with the same date (for example
  `flagship --version` still reporting 1.1.0.dev1).

### Unchanged
- Certificates are verified against the system CA store (or the CA PEM file)
  with host name checks by default.

## 1.1.0.dev1 — 2026-11-15

- Renamed from XenAdmin Rocky to Flagship (package, commands, icon, state
  directory), with Obsoletes/Provides and compatibility symlinks.

# Verification evidence

`unit-tests.txt`: local Rocky 9 Python regression run.
`gui-smoke-el9.txt`: empty output with process exit 0 from GUI construction using
Xvfb on the builder; does not prove interactive behavior or real pool management.

Live test host read-only SSH probe on November 14, 2026 returned
`Permission denied (publickey,password)`. No host changes were made. Approved
access is needed for live qualification; packaging work can continue independently.

Initial Rocky 10 disconnected install using a forced transaction of every bundled
RPM failed on reverse dependencies of installed base packages. This is retained
in offline-container-el10-initial-failure.txt. A local DNF repository fixed that
resolution issue on both majors. The next checks exposed missing help when the
container's default tsflags=nodocs suppressed RPM %doc files. Help is now installed
as application data as well; rebuild and rerun are required before qualification.

Final candidate container checks passed for both majors: network namespace disabled,
only a local DNF repository enabled, version/import checks, unconditional help and
launcher files present. installed-gui-el9.txt and installed-gui-el10.txt additionally
show the installed RPM GUI creating a window under the builder's isolated Xvfb
Unix socket with the container network still disabled. These do not test reboot,
interactive desktop menus, guest management or an independent operator.

`provisioning-tests.txt` records 51 passing local checks for the dev.2 development
tree. It includes a stateful simulated pool exercising creation from installer and
installed templates, preservation of the source template, partial-failure reports,
CPU ordering, GUI review/confirmation, and real HTTPS large-integer encoding.
The simulation does not prove any live host workflow. dev.1 package evidence above
remains specific to the dev.1 release, not proof of dev.2 offline installation.

dev2-offline-el9.txt / dev2-offline-el10.txt record successful fresh network-disabled
installs of 1.0.0-0.2.dev2. dev2-installed-gui-el9.txt / el10.txt also exercise the
installed New VM review and built-in help using synthetic records and no pool
connection. The reproducible fixture is evidence/fixtures/dev2_installed_gui.py.
dev2-provenance.json compares all native modules with both RPM source archives;
dev2-source-closure.json confirms exact corresponding source coverage. dev.2
source archives combine the retained dev.1 baseline with changed/new SRPM deltas.

`device-recovery-tests.txt` records 117 passing dev.3 checks, including stateful
simulated disk/DVD/NIC operations, refused unplug/delete paths, private durable
journals, process-exit recovery, storage-write failures, UUID inspection over
verified HTTPS, cancellation requests and GUI confirmations. Live XCP-ng results and explicit limits are in `LIVE_PROTOCOL.md`. The dev.3 installed fixture also checks the standalone recovery launcher
without inherited PYTHONPATH or DISPLAY so source-tree imports cannot mask packaging
errors. Booted/independent operator qualification remains open.

`dev3-offline-el9.txt` / `dev3-offline-el10.txt` record disconnected installations;
`dev3-installed-gui-el9.txt` / `dev3-installed-gui-el10.txt` record the installed
GUI, help, durable history and independent headless launcher smoke on both majors.

`dev4-offline-el9.txt` / `dev4-offline-el10.txt` record fresh network-disabled
installs. `dev4-installed-gui-el9.txt` / `dev4-installed-gui-el10.txt` exercise
installed New VM review, disk/NIC tables, indexed help, durable history, standalone
recovery, console pixels/input default and clean child-window closure. The records
are synthetic; the fixture is `fixtures/dev4_installed_gui.py`. Booted Rocky 9
dev.3 evidence and explicit limits are in `BOOTED_ROCKY9.md`.

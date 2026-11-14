# v1.0 delivery roadmap

The active goal is the requested Rocky 9/10 application and airgap release. The
initial candidate is a foundation, not completion of that goal.

1. Native foundation: source inventory, XAPI transport, desktop navigation,
   guarded lifecycle actions, reproducible packages and offline documentation.
2. Airgap engineering: dependency closure, local DNF repository, checksums,
   licensing/signature inventory and disconnected installation tests per major.
3. Management workflows: task completion tracking, new VM provisioning,
   CPU/memory/disk/ISO/network editors, XVA transfer, authenticated VNC console,
   performance monitoring and host/pool operations. Maintain parity matrix.
4. Live qualification: approved disposable XCP-ng pool, restricted user, trusted
   certificates, lifecycle/restore/migration tests with independently verified
   outcomes. No production resources for destructive testing.
5. Operator qualification: clean booted Rocky 9 and 10 desktops, offline install,
   reboot, launcher/help, recovery and upgrade/rollback walkthrough by an
   independent operator. Record failures and tested/untested boundaries.
6. Release: stable source tag, source archive, per-major binary/SRPMs, dependency
   bundles, signed packages and verification keys, checksums, release notes and
   complete installation/user/operator/build/help documents. A GitHub prerelease
   must remain explicitly a development candidate until these gates pass.

Current external requirement: approved access to a test hypervisor and suitable
Rocky desktop VMs. The default host's SSH probe rejected current authentication.
Independent implementation and container verification continue while access is
being arranged.

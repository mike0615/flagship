# Booted Rocky 9 qualification — November 14, 2026

Candidate: published 1.0.0.dev3, RPM 1.0.0-0.3.dev3.el9.noarch.
Environment: XCP-ng 8.3 / XAPI 26.1.11, a dedicated two-vCPU / 4 GiB RAM /
24 GiB disk guest. Its newly created network has no physical uplink. Existing
workloads were not selected for mutation. Installation used the existing Rocky
9.6 DVD plus a separate OEMDRV seed carrying the transferred dev.3 airgap bundle.

Observed through the native RFB path:

- Both CDs visible in the installer; ks.cfg discovered from OEMDRV.
- Automated Workstation installation from local media; dependency/transaction
  checks succeeded, followed by package installation and post-install setup.
- Installer-to-installed-system reboot into GNOME.
- Installed native application launched; RPM/version output confirmed dev.3.
- SELinux enforcing, installed offline help and standalone recovery --help passed.
- Pointer input opened the installed indexed help, which displayed its user guide.
- A clean `sudo systemctl reboot` returned to GNOME. The new startup log and a
  direct /proc/sys/kernel/random/boot_id read confirmed a different boot ID.
- Application/help/recovery startup checks ran again after that reboot.
- Closing the application, finding XenAdmin Rocky through GNOME desktop search,
  and launching that installed menu entry opened the native application again.
- The actual source Tk ConsoleWindow also rendered live guest pixels over verified
  HTTPS, with input disabled by default. Protocol input additionally controlled
  installer VT switching and shell diagnostics.

Private manifests, boot IDs, rendered seed, install logs and framebuffer captures
remain outside Git under the local QA state directory. The initial rendered seed
SHA-256 was d883d4bc7c8a827e9ba7ff6676c18ce2fe475ed6f3637d75987987f06d7011ec.
The source QA seed template has subsequently improved fail-fast logging and its
interactive shell; do not treat the current template as byte-identical to that
first rendered seed.

A small-window layout issue in dev.3 was observed. Console-branch source now fits
the display, wraps toolbar actions, reserves action/status space and cleans up Tk
timers; 140 local checks pass at a 1024x768 client display. These changes are not
in dev.3 RPMs. The published dev.3 release notes carry the layout advisory.

Not established: installed-guest pool login/workflows, guest tools or guest-aware
shutdown, advanced devices, performance, snapshots/migration, independent operator
review, Rocky 10 desktop qualification or full Windows parity. No stable v1.0
claim follows from this single-platform qualification.

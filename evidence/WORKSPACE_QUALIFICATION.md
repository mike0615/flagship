# Flagship 1.3.0.dev1 qualification

See LIVE_PORTABLE_2026-11-16.md for eleven live disk/console checks and cleanup.
Source regression output is in workspace-tests.txt. Native qemu-img tests compare
actual disk bytes, parse OVF hardware, verify manifests and reject unsafe images.
Console tests verify widget/framebuffer continuity, input opt-in and authenticated
external viewer relaying, including rejection before opening a host tunnel.

The matching Rocky 9/10 RPMs and binary dependency bundles are built separately.
The release workflow checks offline installation and runs the installed native
GUI and regression suite with --network=none before publication. Publication is
not permitted to substitute for a failed build or test. Exact release source and
payload hashes are in the published RELEASE_SOURCE.json and SHA256SUMS.

This remains a development prerelease with the compatibility boundaries described
in docs/PORTABLE_IMAGES.md. AppStream supplies qemu-img and virt-viewer on both
Rocky majors. No Wine, pip downloads or browser-hosted UI is involved.

# Live portable images and console qualification, 2026-11-16

The user-authorized XCP-ng 8.3.0 host was used over session-pinned HTTPS. Credentials
were prompted without echo and were not saved in source or command arguments.
Endpoint details, private run manifests and complete infrastructure inventory
are excluded from this public evidence.

Eleven checks passed using a disposable 64 MiB disk containing two known nonzero
regions, a disposable VM, two imported VMs and a private network:

1. Imported a native VHD pattern into the disposable VDI.
2. Exported a complete OVA with a SHA-256 value.
3. Imported the OVA as a distinct halted VM.
4. Exported its disk again and verified byte equivalence with qemu-img compare.
5. Exported a standalone qcow2 image with a SHA-256 value.
6. Imported that qcow2 as a distinct halted VM.
7. Exported its disk again and verified byte equivalence with qemu-img compare.
8. Connected the docked native console and received a live framebuffer.
9. Undocked/redocked without replacing its framebuffer or dropping the connection.
10. Launched real remote-viewer 11 in a native Rocky 9 container using the desktop
    display. It authenticated with the one-use VNC password and received console
    bytes through Flagship's TLS bridge. No XAPI credentials entered the viewer.
11. Verified the source installer template's UUID and name remained unchanged.

The source test VM was powered off after console testing. Scoped cleanup resolved
recorded UUIDs and validated associations before deleting disposable VMs, disks
and the private network. A separate inventory check found zero remaining test VM,
VDI or network records by recorded UUID or run prefix. Existing guests and host
network/storage/pool settings were not changed.

This is disk-byte/protocol and native viewer evidence, not an installed guest OS
migration test. No guest keyboard or pointer input was sent by the harness. No
vCenter/ESXi target was tested. Multi-disk OVA parsing/import was tested separately
with real conversions and simulated XAPI. Broad appliance compatibility, guest
storage/NIC drivers, Secure Boot/vTPM, Wayland, multi-host and restricted RBAC
remain outside this live qualification.

`qa/live_portable_smoke.py` reproduces the isolated test with explicit endpoint,
SR UUID, expected TLS pin, private state directory and --execute. Credentials are
prompted. Use scoped cleanup_protocol.py afterwards and verify the inventory.

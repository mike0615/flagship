# VM console (development source)

Console support is on the development branch and is not included in dev.3 RPMs.
Select a running VM, then Console. A separate scrollable window opens in view-only
mode. Enable keyboard and mouse to send input; click inside the guest display.
Disable control or move focus away to release tracked keys and pointer buttons.
Send Ctrl+Alt+Delete is available only while control is enabled. Close console
leaves the guest running. Disconnecting the pool closes its console windows.
There is no automatic reconnect: inspect the error, close and reopen the console.

The native viewer uses the API session through HTTPS CONNECT to the selected VM's
resident host. Certificate-chain and hostname verification remain mandatory.
Trust the appropriate CA for every pool host; no plaintext or redirect fallback
exists. Member hosts must be reachable directly from the desktop. The session is
sent as an HTTP cookie, never placed in a URL or saved. Console input and pixels
are not journaled. Clipboard synchronization is disabled.

The current viewer supports RFB 3.3/3.8 with raw pixels, CopyRect and desktop resize
up to 4096 by 4096. It requests shared access rather than evicting other operators.
Compressed encodings, guest RDP, fullscreen/scaling, clipboard transfer and QEMU
extended scancodes remain future work. Raw updates may use substantial bandwidth.
A halted VM has no active graphical console: start it first. A pool permission
failure or a separate VNC authentication requirement stops the connection.

## Evidence and limits

141 local checks pass, including framebuffer pixel colours, overlapping CopyRect,
resize, input opt-in, modifier/button release, old-client isolation, TLS failure,
HTTP refusal, destination/ownership checks and bounded malformed protocol data.
A dedicated firmware-only VM on XCP-ng 8.3/XAPI 26.1.11 passed authenticated RFB
handshake, actual framebuffer receipt and input transmission. That firmware test did not prove guest response to input or a booted Rocky
desktop. A later dedicated Rocky 9.6 installer guest accepted a VT switch and
shell commands through the native RFB path; its replies were captured privately.
An installed desktop and complete interactive operator journey remain pending. The live harness is `qa/live_protocol_smoke.py --console`; it requires
explicit creation authorization and a fresh private state directory. Cleanup uses
the separately reviewed, UUID-scoped `qa/cleanup_protocol.py` harness.

Protocol references: [XAPI consoles](https://xapi-project.github.io/xen-api/consoles.html)
and [RFB specification](https://www.rfc-editor.org/rfc/rfc6143). Windows behavior was
compared with XenAdmin ConsoleView/XSVNCScreen.cs and XenModel/Network/HTTPHelper.cs.

A dedicated isolated 24 GiB / 4 GiB RAM guest also booted the Rocky 9.6 DVD.
The native framebuffer showed its boot menu and subsequent media-check screen,
including a live resolution change from 640x480 to 1024x768. Installation and
booted-desktop qualification are in progress; media-check progress alone does
not establish a completed installation or prove that transmitted keys changed
the guest. Private captures and the running guest UUID remain outside Git.

The corrected two-CD QA layout (Rocky DVD slot 1, OEMDRV seed slot 3) was
observed inside the installer with `lsblk`. `/run/install/ks.cfg` confirmed
seed discovery. The console then showed unattended Workstation installation,
partition creation on the dedicated xvda disk and local package installation.
Completion, first desktop boot and reboot remain unverified.

The isolated Rocky 9.6 Workstation installation completed and rebooted into GNOME.
The installed dev.3 application launched and its indexed offline help opened via
native RFB pointer input. SELinux remained enforcing. A 1024x768 display exposed
layout clipping, corrected in source with display-aware sizing, wrapped actions
and reserved status/action space. Second reboot, desktop-menu and pool-workflow
qualification are still open. The Rocky 10.2 DVD full SHA-256 matched its signed
checksum; it has not yet been installed.

The actual Tk ConsoleWindow (not only a protocol harness) also rendered live
guest content through verified TLS on a 1024x768 source-client display, with input
off by default. `qa/live_console_window.py` reproduces that UUID-scoped check.
The guest check log confirmed dev.3 RPM version, installed offline help and the
standalone recovery command in the booted SELinux-enforcing system.

Rocky 9 subsequently passed a clean installed-system reboot with a distinct boot
ID, repeated startup checks and manual GNOME desktop-search/menu launch. See
`evidence/BOOTED_ROCKY9.md`; guest pool workflows and Rocky 10 remain open.

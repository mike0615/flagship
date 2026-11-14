# Live qualification harnesses

These tools create or operate on explicitly recorded disposable test resources.
They are not product installation commands. Keep state directories private and
outside Git; credentials are prompted and are not accepted through arguments.
Use the tested pool's trusted CA file. Never disable TLS verification.
Run from the checkout root with `export PYTHONPATH="$PWD"` before invoking tools
that import `xenadmin_rocky`.

`live_protocol_smoke.py --execute` creates isolated networks and a firmware VM,
tests provisioning/devices/power states and retains an exact UUID manifest.
`--console` additionally checks the authenticated RFB handshake, pixels and input
transmission. `cleanup_protocol.py --execute` accepts its manifest, validates
ownership, halted VM state, storage and associations, and removes only those
recorded resources. It deliberately refuses running VMs; investigate uncertain
outcomes before changing state or retrying. A recovered clone task must appear in
the original journal. See each tool's `--help` for required parameters.

## Booted desktop qualification

`prepare_desktop.py --execute` creates one 24 GiB disk / 4 GiB RAM / two-vCPU guest
from the builtin installer template and selected ISO. Its network has no physical
uplink. Verify actual backing filesystem capacity as well as SR API capacity
before creating it; install one guest at a time when capacity is limited.

Build a separate offline seed on a connected Rocky 9 builder with Python,
pykickstart (`ksvalidator`) and xorriso:

```sh
python3 qa/build_desktop_seed.py \
  --major 9 --airgap /absolute/path/to/extracted/airgap \
  --output-directory /private/new/output-directory
```

The builder verifies the bundle checksums, generates an unpredictable guest
password hash and creates an `OEMDRV` ISO containing `ks.cfg` and the bundle.
The root account is locked. For disposable graphical testing, the `qa` guest
account has automatic graphical login and passwordless sudo. Preserve network
isolation and remove this VM after qualification; this is not a production image.
The Kickstart erases **xvda**. Attach it only to the exact recorded disposable VM.
Both rendered profiles passed their matching RHEL9/RHEL10 Kickstart validators.
Use `--major 10` with a Rocky 10 bundle; that build validates in a connected Rocky
10 Podman container. Rocky 9 uses GNOME Terminal and an Xorg QA session. Rocky 10
uses Ptyxis and retains Wayland, with XWayland installed for Tk. The Rocky 10 DVD
package metadata and Ptyxis man page confirmed those dependencies and CLI flags.
Syntax validation does not establish a completed Rocky 10 desktop installation.
See [RHEL 10 removed desktop features](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/10/html/10.0_release_notes/removed-features).

Transfer the seed with authenticated SSH to a dedicated ISO SR, compare SHA-256
before and after transfer, scan that SR, and attach it as a secondary DVD while
the QA VM is halted. The Rocky DVD must have an earlier device position than the
seed: this firmware boots only its first CD drive. Keep both CD drives inside
the emulated IDE range: original DVD slot 1 and seed slot 3, with disk slot 0.
Slot 4 was accepted by XAPI but was invisible to this installer guest. Do not
interpret server-side attachment metadata as proof of guest device visibility. XAPI HVM boot order `cd`
means hard disk then CD; `dc` means CD then hard disk. An empty disk falls through
to the Rocky DVD; after installation, it boots from its installed disk.

Select the install entry on the Rocky DVD. The installer discovers `ks.cfg` on
OEMDRV; verify acceptance through the console rather than assuming the seed ran.
The post-install step installs the application using only the transferred local
repository and configures a graphical qualification session. A later template
revision adds fail-fast desktop command logging; retain the rendered seed hash
and exact template used for each attempt.

`capture_console.py` verifies the recorded VM UUID and namespace, then saves a
private PPM framebuffer. Optional `--key` values send X11 keysyms to that guest.
With `--interactive`, the tool logs in once and accepts JSON lines such as
`{"output":"status.ppm"}`; `quit` logs out. Output names must be new basenames in
the private state directory. Optional `text`, `chord` and `key` fields operate
only on the recorded guest. Commands are for nonsecret diagnostics; terminal
input may be echoed. The password is discarded after login and no session token
is saved. Each capture revalidates the recorded VM UUID and namespace.
No received pixels, keyboard input or session cookie is written to public logs.
Captures prove only what is visible. Input transmission, installer launch,
completed installation, reboot, menu launch and real pool workflows are separate
qualification gates. Record actual evidence for each.

Seed ISO metadata/files are separate from guest disks. After guest cleanup,
verify no VBD associations remain before removing the exact recorded seed ISO
file/VDI metadata. Never clean an entire ISO SR or select existing workloads by
name. Keep manifests, cleanup plans and journals until the run is reviewed.

References: [automatic OEMDRV discovery](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/automatically_installing_rhel/starting-kickstart-installations_rhel-installer)
and [Kickstart commands](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/automatically_installing_rhel/kickstart-commands-and-options-reference_rhel-installer).

## Large ISO staging

`stage_iso.py` streams a verified image directly to a new `xenadmin-qa-*.iso`
filename inside the selected ISO SR. It does not stage large media in dom0 /tmp.
It requires an existing authenticated SSH control connection and prompts for
sudo authentication through a forced, confirmed password handshake; credentials
are never arguments or files. The remote filesystem must retain 20 GiB free.
The complete remote SHA-256 must match before atomic no-overwrite publication;
interruptions retain only the exact private `.part` file named in the private
record. Inspect that record and actual remote process/file state before retrying.

Console `text` diagnostics use the seeded US keyboard layout, explicitly send
Shift for uppercase/symbols, and pause after focus/VT changes. This is a QA typing
helper; it is not a layout-independent clipboard or QEMU scancode implementation.
The seed now holds an interactive shell after its checks; retain exact seed
revision/hash when comparing runs.

Legacy dom0 coreutils exposes only argument-free `sync`; staging uses that
portable flush. A completed upload can exist even if a later flush/status step
fails. Inspect the exact final/partial names and full remote checksum before any
retry; an existing staging record is never silently replaced.

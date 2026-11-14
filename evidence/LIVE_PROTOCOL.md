# Live XAPI protocol qualification — November 14, 2026

Target: single-host XCP-ng 8.3, XAPI 26.1.11. Login used the supplied test account,
HTTPS with verified certificate chain and IP subject alternative name. Credentials,
endpoint details, resource UUIDs and raw journals remain outside the repository.

The explicit `qa/live_protocol_smoke.py` harness created dedicated isolated networks
and a new VM from the builtin Other install media template. It passed:

- Native asynchronous provisioning to a halted VM.
- Disk growth observed through live API metadata; detach retained UUID.
- Permanent deletion of only the dedicated extra disk.
- Empty DVD drive creation and removal.
- NIC network move preserving UUID and MAC.
- VM start, pause, unpause and hard shutdown, each confirmed by server state.
- Original builtin template UUID and name unchanged.

Two earlier attempts exposed real compatibility defects: XAPI implicit string task
results and conversion out of template state before VM.provision. The decoder now
supports both XML-RPC string forms; provisioning occurs before hardware changes.
117 local regression tests pass, including those observed server semantics.

All three attempts were scoped using private UUID manifests and journals.
`qa/cleanup_protocol.py` verifies recorded ownership, halted state, expected SR,
disk associations and empty isolated networks before deletion. Cleanup outcomes
are recorded privately. No existing workload was selected for mutation.

This is protocol/device/firmware evidence. It does not establish successful Rocky
installation, guest tools, boot/reboot, guest data I/O, hotplug with guest drivers,
console access, installed-template copy or complete Windows feature parity.

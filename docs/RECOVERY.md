# Operation history and recovery

## When to use this guide

Use this after a lost connection, client/process exit, stopped workflow, failed
multi-step operation or journal-storage error. Earlier steps may have succeeded.
A request submission is not proof of success, and an error is not proof that the
server made no changes. The client never replays journal entries automatically.

## Find the records

Choose Tools → Operation history / recovery. This works without a pool connection
and opens records from previous application runs. The default directory is:

```text
~/.local/state/xenadmin-rocky/journals/
```

If XDG_STATE_HOME is an absolute path, the directory is
`$XDG_STATE_HOME/xenadmin-rocky/journals/`. Files are named
`operations-<random-id>.jsonl`. The directory is owner-only (0700), files are
owner-readable/writable (0600), and records are flushed with fsync. Use persistent
local storage for this directory. These are ordinary private files, not a
cryptographically tamper-evident audit service or a guarantee against media failure.

Authentication parameters, raw RPC arguments and the API session token are not
journalled. Object/task references, observed UUIDs, method names, pool endpoint,
timestamps, progress transitions and error codes are retained. Treat the files as
private infrastructure metadata. Explicit JSON exports also use mode 0600 and
refuse a symbolic-link destination. Inventory/object exports hide selected
credential fields, but are not a complete sanitizer for arbitrary server metadata.
Review all exports before sharing them.

## Read the states correctly

| Record/state | Meaning | Next action |
|---|---|---|
| intent without outcome | Intent was saved before the call; this does not prove the request was sent | Inspect the server before deciding whether to retry |
| unknown outcome | Communication failed; a server change may have occurred | Check recorded UUIDs/task and current server state |
| returned for Async call | Server returned a task reference | Check the task's actual status |
| pending/cancelling | The server has not reported a terminal outcome | Continue observation; do not resubmit the mutation |
| task success/failure/cancelled | Server reported this terminal task state | Inspect resulting objects, especially after a partial workflow |
| interrupted workflow | Earlier successful steps may have left resources | Review the recorded objects/tasks before cleanup or retry |
| object_identity | A stable UUID was observed for a created object | Prefer that UUID when reconnecting |

The viewer shows at most the last 3000 events across the 100 most recent files.
Warnings identify a truncated window, malformed records or an incomplete final
line. Older files remain on disk. Recovery review applies to the displayed window,
not every operation in retained archives. Preserve the originals if corruption or
an incomplete record is reported. History is evidence to investigate, not a script
to execute and not automatic rollback.

## Inspect the current object safely

1. Identify the intended pool from the workflow's endpoint and verify its TLS trust.
2. Connect to that pool with an account permitted to read the relevant objects.
3. In history choose Inspect current object by UUID. Select the recorded class and
   enter its UUID. References can expire across sessions; do not paste an old
   opaque reference as a UUID.
4. The client resolves a new reference using get_by_uuid and verifies the returned
   object's UUID before displaying it. This inspection exposes no resource-changing
   calls. Confirm current VM state, disk associations and task outcome.
5. Decide whether the remaining work should be completed, abandoned or cleaned up.
   Use the normal reviewed controls or another trusted pool administration tool.
   Never delete a disk merely because its creation workflow was interrupted.

If the response was lost before a created object's UUID could be observed, inspect
the recorded task UUID/reference and server-side records. Some cases require pool
administrator investigation. The journal does not supply server-side idempotency
or guarantee that every interrupted request can be resolved automatically.

## Headless recovery commands

These commands require no graphical display and never expose resource-changing
RPC methods. Run inspection from an interactive terminal; passwords are prompted
with getpass and are not command-line/environment options.

```sh
xenadmin-rocky-recovery history --output private-history.json
xenadmin-rocky-recovery inspect \
  --endpoint https://pool.example.internal --username readonly-admin \
  --ca-file /path/to/trusted-ca.pem --kind VM \
  --uuid 00000000-0000-4000-8000-000000000001 \
  --output private-object.json
```

Replace the example endpoint, account, CA file and UUID. Use --output to obtain a
private file rather than relying on a shell redirection's umask. Object inspection
resolves the UUID afresh and makes only get_by_uuid/get_record resource calls.
Login/logout create/close the authentication session. Use --help for class choices
and the optional history --directory/--limit parameters. API errors, TLS failures
and invalid UUIDs do not trigger a mutation retry.

## Journal storage failure

If an intent cannot be saved, the next resource-changing call is not sent. If a
result cannot be saved after a response, server work may already have completed.
Further changes are blocked by the failed journal; read-only inventory/inspection
remain available. Stop the workflow and save its available report to another
writable location if needed. Preserve the existing journal, correct disk-space,
ownership or filesystem problems, then restart the client and inspect the pool
before making further changes. Do not disable journaling to blindly repeat an
uncertain operation. Uninstalling/upgrading the RPM preserves these user records.

## Cancellation is a request, not rollback

Tools → Stop workflow monitoring stops subsequent client workflow steps. It does
not cancel a submitted server task. After monitoring stops, Tools → Request task
cancellation offers outstanding/cancellable tasks. The client re-reads the task,
checks server-advertised cancellation support and requests cancellation only while
pending. The task can still finish normally, fail or take time to cancel. Tasks
shows the actual outcome. Earlier successful workflow steps are not undone.

When running directly from the source directory instead of an installed RPM, use
`python3 -m xenadmin_rocky.recovery` in place of `xenadmin-rocky-recovery`. The RPM
launcher supplies the installed module path and works from any working directory.

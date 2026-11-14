"""Headless history and UUID inspection; no resource-changing RPCs are exposed."""
import argparse
import getpass
import json
import sys
import uuid
from .api import Client, APIError
from .journal import OperationJournal, OBJECT_CLASSES, recovery_needed, save_json_private
from .redaction import safe_record


def inspect_by_uuid(client, kind, object_uuid):
    if kind not in OBJECT_CLASSES:
        raise ValueError('Unsupported object class')
    try:
        object_uuid = str(uuid.UUID(object_uuid))
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Enter a valid object UUID, not an opaque reference') from None
    ref = client.call(kind + '.get_by_uuid', object_uuid)
    if not isinstance(ref, str) or not ref or ref == 'OpaqueRef:NULL':
        raise ValueError('The server did not return an object reference')
    record = client.call(kind + '.get_record', ref)
    try:
        matches = isinstance(record, dict) and str(uuid.UUID(record.get('uuid', ''))) == object_uuid
    except (ValueError, TypeError, AttributeError):
        matches = False
    if not matches:
        raise ValueError('Server object identity does not match the requested UUID')
    report = {'object_class': kind, 'uuid': object_uuid, 'current_reference': ref, 'record': safe_record(record)}
    endpoint = getattr(client, 'endpoint', None)
    if isinstance(endpoint, str):
        report['endpoint'] = endpoint
    return report


def main():
    parser = argparse.ArgumentParser(prog='xenadmin-rocky-recovery', description='Read-only XenAdmin Rocky recovery tools')
    commands = parser.add_subparsers(dest='command', required=True)
    history = commands.add_parser('history', help='Read local operation records without connecting to a pool')
    history.add_argument('--directory')
    history.add_argument('--limit', type=int, default=3000)
    history.add_argument('--output')
    inspect = commands.add_parser('inspect', help='Read a current pool object by UUID')
    inspect.add_argument('--endpoint', required=True)
    inspect.add_argument('--username', required=True)
    inspect.add_argument('--ca-file')
    inspect.add_argument('--kind', required=True, choices=sorted(OBJECT_CLASSES))
    inspect.add_argument('--uuid', required=True)
    inspect.add_argument('--output')
    args = parser.parse_args()
    client = None
    try:
        if args.command == 'history':
            if not 1 <= args.limit <= 10000:
                raise ValueError('History limit must be between 1 and 10000')
            records, warnings = OperationJournal(args.directory).history(args.limit)
            report = {'recovery_review': recovery_needed(records), 'warnings': warnings, 'events': records}
        else:
            # Validate the endpoint/CA before prompting. Passwords are never argv/env options.
            client = Client(args.endpoint, args.ca_file)
            client.login(args.username, getpass.getpass('XAPI password: '))
            report = inspect_by_uuid(client, args.kind, args.uuid)
        if args.output:
            save_json_private(args.output, report)
        else:
            print(json.dumps(report, indent=2))
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        message = str(exc) if isinstance(exc, (ValueError, APIError)) else type(exc).__name__
        print('Recovery command failed: ' + message, file=sys.stderr)
        return 1
    finally:
        if client:
            try:
                client.logout()
            except Exception:
                pass


if __name__ == '__main__':
    raise SystemExit(main())

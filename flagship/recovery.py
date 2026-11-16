"""Headless history and UUID inspection; no resource-changing RPCs are exposed."""
import argparse
import getpass
import json
import sys
import uuid
from .api import Client, APIError
from .journal import OperationJournal, OBJECT_CLASSES, recovery_needed, save_json_private
from .redaction import safe_record
from .tls import CertificateChanged, CertificateUntrusted, KnownCerts, host_key, normalize_fingerprint


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


def make_client(args):
    known = None if args.no_saved_pins else KnownCerts()
    client = Client(args.endpoint, args.ca_file, insecure=args.insecure, known=known)
    if args.pin:
        client.trust.pins[host_key(client.host, client.port)] = normalize_fingerprint(args.pin)
    return client


def main():
    parser = argparse.ArgumentParser(prog='flagship-recovery', description='Read-only Flagship recovery tools')
    commands = parser.add_subparsers(dest='command', required=True)
    history = commands.add_parser('history', help='Read local operation records without connecting to a pool')
    history.add_argument('--directory')
    history.add_argument('--limit', type=int, default=3000)
    history.add_argument('--output')
    inspect = commands.add_parser('inspect', help='Read a current pool object by UUID')
    inspect.add_argument('--endpoint', required=True)
    inspect.add_argument('--username', required=True)
    inspect.add_argument('--ca-file', help='Trust only this CA PEM file (for example the host\'s own self-signed certificate)')
    inspect.add_argument('--pin', metavar='SHA256',
                         help='Accept the endpoint only if its certificate has this SHA-256 fingerprint')
    inspect.add_argument('--insecure', action='store_true',
                         help='Ignore SSL certificate errors (no verification; insecure)')
    inspect.add_argument('--no-saved-pins', action='store_true',
                         help='Ignore certificates trusted in the Flagship GUI (~/.config/flagship/known_certs.json)')
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
            client = make_client(args)
            if args.insecure:
                print('WARNING: certificate checks are disabled (--insecure).', file=sys.stderr)
            client.login(args.username, getpass.getpass('XAPI password: '))
            report = inspect_by_uuid(client, args.kind, args.uuid)
        if args.output:
            save_json_private(args.output, report)
        else:
            print(json.dumps(report, indent=2))
        return 0
    except CertificateChanged as exc:
        print('Recovery command failed: WARNING: the certificate of %s HAS CHANGED.\n'
              'Presented SHA-256: %s\nTrusted SHA-256:   %s\n'
              'Nothing was sent. Confirm the change on the host before trusting the new certificate.'
              % (exc.info.key, exc.info.sha256.upper(), exc.pinned.upper()), file=sys.stderr)
        return 1
    except CertificateUntrusted as exc:
        info = exc.info
        print('Recovery command failed: the certificate of %s is not trusted (%s).\n'
              'Subject: %s\nIssuer:  %s\nValid:   %s to %s\nSHA-256: %s\n'
              'If this matches the host, rerun with --pin %s, or use --ca-file.'
              % (info.key, info.verify_error, info.subject, info.issuer, info.not_before,
                 info.not_after, info.sha256.upper(), info.sha256.upper()), file=sys.stderr)
        return 1
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

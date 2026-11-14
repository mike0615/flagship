"""Selected sensitive fields are hidden; infrastructure exports still need review."""
from datetime import date, datetime
from xmlrpc.client import DateTime


def safe_record(value):
    if isinstance(value, (DateTime, date, datetime)):
        return str(value)
    if isinstance(value, dict):
        return {key: ('[redacted]' if any(part in key.lower() for part in
                ('password', 'secret', 'session', 'token', 'location')) else safe_record(item))
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_record(item) for item in value]
    return value

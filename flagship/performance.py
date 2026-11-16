"""Bounded, TLS-authenticated RRD reads, following XenAdmin ArchiveMaintainer."""
import math
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlencode, urlsplit
from .api import TrustedHTTPSConnection

MAX_XML = 16 * 1024 * 1024


def parse_rrd(payload, kind, uuid):
    if len(payload) > MAX_XML or b'<!DOCTYPE' in payload.upper() or b'<!ENTITY' in payload.upper():
        raise ValueError('Unsupported RRD response')
    root = ET.fromstring(payload)
    legends = [entry.text or '' for entry in root.findall('./meta/legend/entry')]
    selected = {}
    for i, legend in enumerate(legends):
        parts = legend.split(':', 3)
        if len(parts) == 4 and parts[1] == kind and parts[2] == uuid:
            selected[i] = parts[3]
    series = {label: [] for label in selected.values()}
    for row in root.findall('./data/row'):
        try: timestamp = float(row.findtext('t', 'nan'))
        except ValueError: continue
        if not math.isfinite(timestamp): continue
        vals = row.findall('v')
        for i, label in selected.items():
            try: value = float(vals[i].text or 'nan')
            except (ValueError, IndexError): continue
            if math.isfinite(value): series[label].append((timestamp, value))
    return {k: sorted(v) for k, v in series.items() if v}


def fetch_rrd(client, cls, ref, seconds=600):
    if cls not in ('host', 'VM') or seconds not in (600, 3600, 86400, 604800):
        raise ValueError('Choose a host or VM and a supported time range.')
    record = client.call(cls + '.get_record', ref)
    if cls == 'VM':
        if record.get('power_state') not in ('Running', 'Paused'):
            raise ValueError('Performance history requires a resident VM.')
        host = client.call('host.get_record', record['resident_on'])
    else: host = record
    endpoint = urlsplit(client.endpoint)
    hostname = host.get('address')
    if not hostname or any(c in hostname for c in '/\\?#@ \r\n'):
        raise ValueError('Invalid host address in inventory')
    port = (endpoint.port or 443) if hostname == endpoint.hostname else 443
    interval = 5 if seconds <= 3600 else 60 if seconds <= 86400 else 3600
    query = {'session_id': client.session, 'start': int(time.time())-seconds, 'cf': 'AVERAGE', 'interval': interval}
    if cls == 'host': query['host'] = 'true'
    else: query['vm_uuid'] = record['uuid']
    conn = TrustedHTTPSConnection(hostname, port, client.trust, timeout=30)
    try:
        conn.request('GET', '/rrd_updates?' + urlencode(query), headers={'Accept': 'application/xml'})
        response = conn.getresponse()
        # Never forward session credentials through redirects.
        if response.status != 200: raise ValueError('The host refused the performance request.')
        payload = response.read(MAX_XML+1)
    finally: conn.close()
    return parse_rrd(payload, 'host' if cls == 'host' else 'vm', record['uuid'])

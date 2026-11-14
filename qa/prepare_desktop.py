#!/usr/bin/env python3
"""Create one isolated desktop qualification guest. Keep its UUID manifest for cleanup."""
import argparse
from datetime import datetime, timezone
import getpass
from pathlib import Path
import uuid
from xenadmin_rocky.api import Client
from xenadmin_rocky.journal import OperationJournal, save_json_private
from xenadmin_rocky.workflows import Provisioner, VMPlan, GiB


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('endpoint', 'username', 'ca-file', 'sr-uuid', 'iso-uuid', 'state-directory'):
        p.add_argument('--'+name, required=True)
    p.add_argument('--execute', action='store_true')
    args = p.parse_args()
    if not args.execute: p.error('--execute is required')
    directory = Path(args.state_directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    state_file = directory/'live-state.json'
    if state_file.exists(): p.error('Inspect the existing run instead of replacing its manifest')
    prefix = 'xenadmin-qa-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
    state = {'prefix': prefix, 'endpoint': args.endpoint, 'created': [], 'status': 'starting'}
    journal = OperationJournal(directory/'journals')
    c = Client(args.endpoint, args.ca_file, journal=journal)
    jobs = Provisioner(c, progress=journal.workflow, timeout=600)

    def record(kind, ref):
        data = c.call(kind+'.get_record', ref)
        state['created'].append({'class': kind, 'ref': ref, 'uuid': data['uuid'], 'label': data.get('name_label', '')})
        save_json_private(state_file, state)
        return data

    save_json_private(state_file, state)
    try:
        password = getpass.getpass('XAPI QA password: ')
        c.login(args.username, password)
        password = None
        storage = c.call('SR.get_by_uuid', args.sr_uuid)
        sr = c.call('SR.get_record', storage)
        if sr.get('content_type') != 'user' or int(sr['physical_size'])-int(sr['physical_utilisation']) < 48*GiB:
            raise ValueError('Expected user SR with at least 48 GiB free')
        iso = c.call('VDI.get_by_uuid', args.iso_uuid)
        image = c.call('VDI.get_record', iso)
        if c.call('SR.get_record', image['SR']).get('content_type') != 'iso':
            raise ValueError('Install media must be from an ISO SR')
        templates = c.call('VM.get_by_name_label', 'Other install media')
        if len(templates) != 1: raise ValueError('Expected one builtin installer template')
        journal.begin('Isolated Rocky desktop qualification', args.endpoint)
        network = c.call('network.create', {'name_label': prefix+'-isolated',
            'name_description': 'No physical uplink; desktop qualification only', 'MTU': 1500, 'other_config': {}})
        record('network', network)
        result = jobs.create(VMPlan(templates[0], prefix+'-desktop', storage, network,
                                   cpus=2, memory_mib=4096, disk_gib=24, iso=iso, start=False))
        vm = result['resources']['VM']
        data = record('VM', vm)
        for ref in data.get('VBDs', []):
            vbd = c.call('VBD.get_record', ref)
            if vbd.get('type') == 'Disk': record('VDI', vbd['VDI'])
        jobs.async_call('VM.start', vm, False, False)
        state['status'] = 'running_installer'
        state['iso_name'] = image.get('name_label')
        save_json_private(state_file, state)
        journal.finish('completed')
        print('Dedicated installer guest started; private manifest saved. Existing guests were not selected.')
    finally:
        try: c.logout()
        finally: journal.close()


if __name__ == '__main__': main()

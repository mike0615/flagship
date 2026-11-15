#!/usr/bin/env python3
"""Explicit, scoped live XAPI smoke. Credentials are prompted; no production VM is selected."""
import argparse
from datetime import datetime, timezone
import getpass
from pathlib import Path
import time
import uuid
from flagship.api import Client, APIError
from flagship.devices import DeviceManager
from flagship.journal import OperationJournal, save_json_private
from flagship.workflows import Provisioner, VMPlan, WorkflowError, GiB, NULL


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--username', required=True)
    parser.add_argument('--ca-file', required=True)
    parser.add_argument('--sr-uuid', required=True)
    parser.add_argument('--state-directory', required=True)
    parser.add_argument('--console', action='store_true', help='Also test authenticated framebuffer and input on the dedicated firmware VM')
    parser.add_argument('--execute', action='store_true', help='Explicitly create isolated, clearly named QA resources')
    args = parser.parse_args()
    if not args.execute:
        parser.error('--execute is required; this creates dedicated QA resources')
    directory = Path(args.state_directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    state_file = directory/'live-state.json'
    if state_file.exists():
        parser.error('State file already exists; inspect the previous run instead of silently replacing it')
    run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
    prefix = 'xenadmin-qa-' + run
    state = {'run': run, 'prefix': prefix, 'endpoint': args.endpoint, 'created': [], 'checks': [], 'status': 'starting'}
    journal = OperationJournal(directory/'journals')
    client = Client(args.endpoint, args.ca_file, journal=journal)
    workflow = Provisioner(client, progress=journal.workflow, timeout=300)
    stage = 'login'

    def persist():
        save_json_private(state_file, state)

    def record(kind, ref, label):
        data = client.call(kind+'.get_record', ref)
        state['created'].append({'class': kind, 'ref': ref, 'uuid': data['uuid'], 'label': label})
        persist()
        return data

    def check(label, condition):
        if not condition:
            raise AssertionError(label)
        state['checks'].append(label)
        persist()
        print('PASS:', label, flush=True)

    def own_vm(vm):
        record = client.call('VM.get_record', vm)
        if not record.get('name_label', '').startswith(prefix):
            raise ValueError('Refusing to operate on a VM outside this run')
        known = [r['uuid'] for r in state['created'] if r['class'] == 'VM']
        if record['uuid'] not in known:
            raise ValueError('VM UUID is not recorded as created by this run')
        return record

    persist()
    try:
        password = getpass.getpass('XAPI QA password: ')
        client.login(args.username, password)
        password = None
        check('verified TLS and native XAPI login', True)
        storage = client.call('SR.get_by_uuid', args.sr_uuid)
        sr = client.call('SR.get_record', storage)
        free = int(sr['physical_size']) - int(sr['physical_utilisation'])
        if sr.get('content_type') != 'user' or free < 15*GiB:
            raise ValueError('Test SR must have at least 15 GiB free user storage')
        templates = client.call('VM.get_by_name_label', 'Other install media')
        if len(templates) != 1:
            raise ValueError('Expected one builtin Other install media template')
        template = templates[0]
        before = client.call('VM.get_record', template)
        journal.begin('Live isolated QA smoke', args.endpoint)
        networks = []
        for number in (1, 2):
            stage = 'create isolated QA network'
            name = prefix+'-net'+str(number)
            ref = client.call('network.create', {'name_label': name, 'name_description': 'Disposable XenAdmin qualification network',
                                                'MTU': 1500, 'other_config': {}})
            record('network', ref, name)
            networks.append(ref)
        stage = 'native VM provisioning'
        report = workflow.create(VMPlan(template, prefix+'-protocol', storage, networks[0], cpus=1,
                                        memory_mib=512, disk_gib=1, start=False))
        vm = report['resources']['VM']
        record('VM', vm, prefix+'-protocol')
        base = own_vm(vm)
        check('native provisioning produced a halted VM', base['power_state']=='Halted')
        for ref in base.get('VBDs', []):
            vbd = client.call('VBD.get_record', ref)
            if vbd.get('type') == 'Disk' and vbd.get('VDI') not in ('', None, NULL):
                record('VDI', vbd['VDI'], 'base QA disk')
        stage = 'native add and grow disk'
        manager = DeviceManager(client, progress=journal.workflow, timeout=300)
        extra = manager.execute('add_disk', vm, sr=storage, name=prefix+'-extra', size_gib=1)
        disk = extra['resources']['VDI']
        link = extra['resources']['VBD']
        data = record('VDI', disk, prefix+'-extra')
        manager.execute('grow_disk', vm, vbd=link, size_gib=2)
        check('native disk growth is reflected by live XAPI', int(client.call('VDI.get_record', disk)['virtual_size'])==2*GiB)
        manager.execute('rename_disk', vm, vbd=link, name=prefix+'-renamed')
        stage = 'native detach and reattach'
        manager.execute('detach_disk', vm, vbd=link)
        check('detach retained the same disk UUID', client.call('VDI.get_record', disk)['uuid']==data['uuid'])
        attached = manager.execute('attach_disk', vm, vdi=disk)
        stage = 'native UUID-confirmed disk deletion'
        manager.execute('delete_disk', vm, vbd=attached['resources']['VBD'], confirmation_uuid=data['uuid'])
        try:
            client.call('VDI.get_record', disk)
        except APIError as exc:
            check('explicit deletion removed only the QA extra disk', str(exc)=='HANDLE_INVALID')
        else:
            raise AssertionError('Deleted disk still exists')
        stage = 'native DVD creation/removal'
        dvd = manager.execute('add_cd', vm)
        manager.execute('remove_cd', vm, vbd=dvd['resources']['VBD'])
        check('native empty DVD lifecycle completed', True)
        stage = 'native adapter creation/move/removal'
        nic = manager.execute('add_nic', vm, network=networks[0])['resources']['VIF']
        first = client.call('VIF.get_record', nic)
        manager.execute('move_nic', vm, vif=nic, network=networks[1])
        moved = client.call('VIF.get_record', nic)
        check('adapter network move preserved UUID and MAC', first['uuid']==moved['uuid'] and first['MAC']==moved['MAC'])
        manager.execute('remove_nic', vm, vif=nic)
        stage = 'native VM power-state transitions'
        for operation, expected, parameters in [('start', 'Running', (False, False)), ('pause', 'Paused', ()),
                                                 ('unpause', 'Running', ()), ('hard_shutdown', 'Halted', ())]:
            own_vm(vm)
            workflow.async_call('VM.'+operation, vm, *parameters)
            check('live VM '+operation+' -> '+expected, own_vm(vm)['power_state']==expected)
            if operation == 'start' and args.console:
                stage = 'verified console tunnel and framebuffer'
                from flagship.console import open_console
                from flagship.rfb import RFB
                tunnel = open_console(client, vm)
                try:
                    console = RFB(tunnel)
                    width, height = console.handshake()
                    check('live authenticated RFB handshake', width > 0 and height > 0)
                    seen = False
                    deadline = time.monotonic() + 30
                    while not seen and time.monotonic() < deadline:
                        seen = any(event[0] == 'pixels' for event in console.events())
                    check('live framebuffer pixels received', seen)
                    console.key(0xff0d, True)
                    console.key(0xff0d, False)
                    console.pointer(0, 0, 0)
                    check('live firmware input events transmitted', True)
                finally:
                    tunnel.close()
                stage = 'native VM power-state transitions'
        after = client.call('VM.get_record', template)
        check('builtin source template UUID/name unchanged', before['uuid']==after['uuid'] and before['name_label']==after['name_label'])
        state['status'] = 'passed'
        journal.finish('completed', report={'resources': {'VM': vm}, 'tasks': workflow.tasks})
        persist()
        print('Live QA smoke passed. Dedicated resources are recorded privately for explicit cleanup.', flush=True)
        return 0
    except Exception as exc:
        state['status']='failed_or_interrupted'
        state['stage']=stage
        state['error']=str(exc) if isinstance(exc,(APIError,ValueError,AssertionError)) else type(exc).__name__
        if isinstance(exc, WorkflowError):
            state['workflow']={'stage':exc.stage,'reason':exc.reason,'resources':exc.resources,'tasks':exc.tasks}
        persist()
        print('Live QA stopped at:',stage,'—',state['error'],flush=True)
        print('Partial QA resources retained; inspect the private state and journal before retrying.',flush=True)
        return 1
    finally:
        try: client.logout()
        except Exception: pass
        journal.close()


if __name__=='__main__':
    raise SystemExit(main())

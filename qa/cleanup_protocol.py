#!/usr/bin/env python3
"""Explicit cleanup of resources recorded by live_protocol_smoke; never select production VMs by name alone."""
import argparse
import getpass
import json
from pathlib import Path
from xenadmin_rocky.api import Client, APIError
from xenadmin_rocky.journal import OperationJournal, save_json_private
from xenadmin_rocky.protocol import decode_reference_result, NULL
from xenadmin_rocky.workflows import Provisioner


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--endpoint', required=True)
    p.add_argument('--username', required=True)
    p.add_argument('--ca-file', required=True)
    p.add_argument('--state-file', required=True)
    p.add_argument('--sr-uuid', required=True)
    p.add_argument('--recover-clone-task-uuid')
    p.add_argument('--execute', action='store_true')
    args=p.parse_args()
    if not args.execute: p.error('--execute is required')
    path=Path(args.state_file)
    state=json.loads(path.read_text())
    prefix=state['prefix']
    if state.get('endpoint') != args.endpoint or not prefix.startswith('xenadmin-qa-'):
        p.error('State must belong to this endpoint and the QA namespace')
    journal=OperationJournal(path.parent/'cleanup-journals')
    c=Client(args.endpoint,args.ca_file,journal=journal)
    jobs=Provisioner(c,progress=journal.workflow,timeout=300)
    def find(kind, object_uuid):
        try: return c.call(kind+'.get_by_uuid', object_uuid)
        except APIError as exc:
            if str(exc) in ('UUID_INVALID','HANDLE_INVALID'): return None
            raise
    try:
        password=getpass.getpass('XAPI QA password: ')
        c.login(args.username,password)
        password=None
        journal.begin('Explicit QA cleanup',args.endpoint)
        if args.recover_clone_task_uuid:
            events=[]
            for file in (path.parent/'journals').glob('operations-*.jsonl'):
                events.extend(json.loads(line) for line in file.read_text().splitlines())
            intents={e['op_id']:e for e in events if e.get('event')=='intent'}
            permitted=[e for e in events if e.get('event')=='task_state' and e.get('uuid')==args.recover_clone_task_uuid
                       and intents.get(e.get('op_id'),{}).get('method') in ('Async.VM.clone','Async.VM.copy')]
            if not permitted: raise ValueError('Recovery task is not in this run\'s creation journal')
            task=c.call('task.get_record',c.call('task.get_by_uuid',args.recover_clone_task_uuid))
            if task['status']!='success': raise ValueError('Creation task outcome is not confirmed successful')
            ref=decode_reference_result(task['result'])
            machine=c.call('VM.get_record',ref)
            if not machine['name_label'].startswith(prefix): raise ValueError('Recovered VM is outside the QA namespace')
            if not any(item['uuid']==machine['uuid'] for item in state['created']):
                state['created'].append({'class':'VM','ref':ref,'uuid':machine['uuid'],'label':machine['name_label']})
                save_json_private(path,state)
        machines=[]; disks={}
        storage=c.call('SR.get_by_uuid',args.sr_uuid)
        for item in state['created']:
            if item['class']!='VM': continue
            ref=find('VM',item['uuid'])
            if not ref: continue
            machine=c.call('VM.get_record',ref)
            if not machine['name_label'].startswith(prefix) or machine['power_state']!='Halted':
                raise ValueError('Cleanup only accepts recorded, halted QA VMs')
            machines.append((ref,machine))
        own_refs={ref for ref,_ in machines}
        for _, machine in machines:
            for link in machine.get('VBDs',[]):
                vbd=c.call('VBD.get_record',link)
                if vbd.get('type')!='Disk' or vbd.get('VDI') in ('',None,NULL): continue
                disk=c.call('VDI.get_record',vbd['VDI'])
                if disk['SR']!=storage or disk.get('type')!='user':
                    raise ValueError('QA disk is not on the expected test SR')
                for association in disk.get('VBDs',[]):
                    if c.call('VBD.get_record',association)['VM'] not in own_refs:
                        raise ValueError('Disk has a non-QA association; refusing cleanup')
                disks[disk['uuid']]=vbd['VDI']
        for item in state['created']:
            if item['class']=='VDI':
                ref=find('VDI',item['uuid'])
                if ref:
                    disk=c.call('VDI.get_record',ref)
                    if disk['SR']!=storage: raise ValueError('Recorded disk changed storage')
                    disks[item['uuid']]=ref
        plan={'vm_uuids':[m['uuid'] for _,m in machines],'disk_uuids':list(disks),
              'network_uuids':[i['uuid'] for i in state['created'] if i['class']=='network']}
        save_json_private(path.parent/'cleanup-plan.json',plan)
        for ref,_ in machines:
            jobs.async_call('VM.destroy',ref)
        for object_uuid in disks:
            ref=find('VDI',object_uuid)
            if not ref: continue
            disk=c.call('VDI.get_record',ref)
            if disk.get('VBDs') or disk['SR']!=storage:
                raise ValueError('Disk acquired an association; stop cleanup and inspect')
            jobs.async_call('VDI.destroy',ref)
        for item in reversed(state['created']):
            if item['class']!='network': continue
            ref=find('network',item['uuid'])
            if not ref: continue
            network=c.call('network.get_record',ref)
            if not network['name_label'].startswith(prefix) or network.get('PIFs') or network.get('VIFs'):
                raise ValueError('Network is not empty isolated QA infrastructure')
            c.call('network.destroy',ref)
        state['status']='cleaned'
        save_json_private(path,state)
        journal.finish('completed')
        print('Scoped QA cleanup completed; private plan and journal retained.')
        return 0
    except Exception as exc:
        print('QA cleanup stopped:',str(exc) if isinstance(exc,(ValueError,APIError)) else type(exc).__name__)
        return 1
    finally:
        try:c.logout()
        except Exception:pass
        journal.close()


if __name__=='__main__':raise SystemExit(main())

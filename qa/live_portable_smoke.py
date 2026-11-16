import sys,getpass,json,time,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from flagship.api import Client
from flagship.journal import OperationJournal,save_json_private
from flagship.workflows import Provisioner,VMPlan
from flagship.management import NetworkPlan
from flagship.portable import PortableTransfer
from flagship.images import Converter
from flagship.external_viewer import ExternalViewer
from flagship.workflows import WorkflowError
import argparse
from urllib.parse import urlsplit
from flagship.tls import host_key
parser=argparse.ArgumentParser(description='Disposable OVA/qcow2 and docked/external console qualification')
for name in ('endpoint','username','pin','sr-uuid','state-directory'): parser.add_argument('--'+name,required=True)
parser.add_argument('--viewer-binary',default=None)
parser.add_argument('--execute',action='store_true')
args=parser.parse_args()
if not args.execute: parser.error('--execute is required')
base=Path(args.state_directory);base.mkdir(parents=True,exist_ok=True,mode=0o700)
manifest=base/'live-state.json'
if manifest.exists(): raise SystemExit('Inspect previous run before retrying')
state={'prefix':'xenadmin-qa-portable-'+str(int(time.time())),'endpoint':args.endpoint,'created':[],'checks':[],'status':'starting'}
journal=OperationJournal(base/'journals')
endpoint=urlsplit(args.endpoint)
c=Client(state['endpoint'],journal=journal,pins={host_key(endpoint.hostname,endpoint.port or 443):args.pin})
engine=Provisioner(c,timeout=300)
def persist():save_json_private(manifest,state)
def record(kind,ref):
 r=c.call(kind+'.get_record',ref);state['created'].append({'class':kind,'ref':ref,'uuid':r['uuid'],'label':r.get('name_label','')});persist();return r
def check(label,condition):
 if not condition:raise AssertionError(label)
 state['checks'].append(label);persist();print('PASS:',label,flush=True)
persist()
try:
 password=getpass.getpass('Temporary XAPI password: ');c.login(args.username,password);password=None
 journal.begin('Disposable portable and console qualification',state['endpoint'])
 sr=c.call('SR.get_by_uuid',args.sr_uuid)
 state['sr_uuid']=args.sr_uuid;persist()
 template=c.call('VM.get_by_name_label','Other install media')
 if len(template)!=1:raise ValueError('Expected one installer template')
 template=template[0];original=copy.deepcopy(c.call('VM.get_record',template))
 network=NetworkPlan(state['prefix']+'-net','Disposable portable QA').create(c)['resources']['network'];record('network',network)
 report=engine.create(VMPlan(template,state['prefix']+'-source',sr,network,cpus=1,memory_mib=512,disk_gib=1,disk_bytes=64*1024**2))
 vm=report['resources']['VM'];record('VM',vm);disk=report['resources']['VDI'];record('VDI',disk)
 raw=base/'pattern.raw'
 with raw.open('wb') as f:f.write(b'FLAGSHIP PORTABLE CONTENT CHECK');f.seek(4*1024**2);f.write(b'NONZERO SECOND REGION');f.truncate(64*1024**2)
 vhd=Converter().convert(raw,'raw',base/'pattern.vhd','vpc');PortableTransfer(c,timeout=300).import_disk(vhd,disk)
 check('pattern uploaded into disposable VDI',True)
 for fmt in ('ova','qcow2'):
  filename=base/('export.'+fmt)
  exported=PortableTransfer(c,timeout=300).export_portable(vm,filename,fmt)
  check(fmt+' export published with SHA256',filename.exists() and bool(exported['sha256']))
  imported=PortableTransfer(c,timeout=300).import_portable(filename,sr,network,template,name=state['prefix']+'-'+fmt)
  imported_vm=imported['resources']['VM'];machine=record('VM',imported_vm)
  imported_disk=imported['resources']['VDI'];record('VDI',imported_disk)
  check(fmt+' imported as a distinct halted VM',imported_vm!=vm and machine['power_state']=='Halted')
  target=PortableTransfer(c,timeout=300).export_disk(imported_disk,base/(fmt+'-roundtrip.vhd'))
  Converter().run('compare','-f','raw','-F','vpc',raw,target)
  check(fmt+' roundtrip preserved nonzero disk bytes',True)
 engine.async_call('VM.start',vm,False,False)
 try:
  import tkinter as tk
  from flagship.app import Application
  from flagship.console_window import ConsoleWindow
  root=tk.Tk();root.withdraw();app=Application(root);app.auto_refresh.set(False);app.client=c;app.records=c.inventory()[0];app.populate();app.select_resource('VM',vm)
  view=ConsoleWindow(app,vm,parent=app.console_host);app.consoles.append(view)
  deadline=time.monotonic()+15
  while view.image is None and time.monotonic()<deadline:root.update();time.sleep(.03)
  check('live docked console received framebuffer',view.image is not None)
  image=view.image;view.toggle_dock();root.update();view.toggle_dock();root.update()
  check('live undock/redock preserved framebuffer and connection',view.image is image and not view.stop.is_set() and view.docked)
  view.close();app.client=None;app.jobs.shutdown(wait=True);app.journal.close();root.destroy()
  external=ExternalViewer(c,vm,title='Flagship disposable QA',binary=args.viewer_binary)
  deadline=time.monotonic()+20
  while external.bytes_from_host<24 and not external.stop.is_set() and time.monotonic()<deadline:time.sleep(.1)
  try:
   check('real Virt Viewer authenticated and received console bytes',external.bytes_from_host>=24)
  finally:external.close()
 finally:engine.async_call('VM.hard_shutdown',vm)
 after=c.call('VM.get_record',template)
 check('source template UUID and name unchanged',after['uuid']==original['uuid'] and after['name_label']==original['name_label'])
 state['status']='passed';persist();journal.finish('completed')
except Exception as exc:
 state['status']='failed_or_interrupted';state['error_type']=type(exc).__name__
 if isinstance(exc,WorkflowError):state['workflow']={'stage':exc.stage,'reason':exc.reason,'resources':exc.resources,'tasks':exc.tasks}
 persist();print('STOPPED',type(exc).__name__,getattr(exc,'reason',''),flush=True)
 raise
finally:c.logout();journal.close()

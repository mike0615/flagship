#!/usr/bin/env python3
"""Capture a synthetic Center-style desktop; no hypervisor or credentials."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tkinter as tk
from unittest.mock import Mock
from flagship.app import Application
from qa.smoke_screenshots import grab_window, _pump

root=tk.Tk(); app=Application(root); root.geometry('1200x760+20+20')
app.client=Mock(); app.client.endpoint='https://pool.example.test'; app.client.tls_mode='verified'
app.records={
 'pool':{'pool':{'name_label':'Development Pool','uuid':'example-pool','master':'host'}},
 'host':{'host':{'name_label':'rocky-lab-host','uuid':'example-host','enabled':True,'metrics':'hm','name_description':'XCP-ng 8.3 test infrastructure','software_version':{'product_version':'8.3'},'memory_total':str(64*1024**3)}},
 'host_metrics':{'hm':{'memory_total':str(64*1024**3),'memory_free':str(40*1024**3)}},
 'VM':{'vm':{'name_label':'Rocky Linux 10','uuid':'example-vm','name_description':'Native Linux guest','resident_on':'host','power_state':'Running','VCPUs_at_startup':'4','memory_dynamic_max':str(8*1024**3),'allowed_operations':['clean_shutdown','clean_reboot','pause','suspend','snapshot','pool_migrate']},
       'vm2':{'name_label':'Rocky Linux 9','uuid':'example-vm2','resident_on':'host','power_state':'Halted','VCPUs_at_startup':'2','memory_dynamic_max':str(4*1024**3),'allowed_operations':['start','clone','destroy']},
       'snap':{'name_label':'Before update','uuid':'example-snapshot','is_a_snapshot':True,'snapshot_of':'vm','power_state':'Halted','allowed_operations':['revert','destroy']}},
 'SR':{'sr':{'name_label':'Local storage','uuid':'example-sr','type':'ext','content_type':'user','shared':False,'physical_size':str(1024**4),'physical_utilisation':str(320*1024**3),'virtual_allocation':str(400*1024**3),'allowed_operations':['scan','vdi_create']}},
 'PBD':{'pbd':{'host':'host','SR':'sr','currently_attached':True}},
 'network':{'net':{'name_label':'Management Network','MTU':'1500','bridge':'xenbr0'}},
 'PIF':{'pif':{'host':'host','network':'net','device':'eth0','MAC':'02:00:00:00:00:01','currently_attached':True,'management':True,'IP':'192.0.2.10','VLAN':'-1'}},
 'message':{'m':{'name':'Example alert','body':'Synthetic screenshot data only','priority':'3'}},
 'task':{'t':{'name_label':'Create VM','status':'success','progress':'1'}}}
app.populate(); app.status.set('Synthetic demonstration data — no live server connection')
dest=Path(sys.argv[1]) if len(sys.argv)>1 else Path('docs/screenshots'); dest.mkdir(parents=True,exist_ok=True)
for cls,ref,tab,filename in [('host','host','General','center-host.png'),('host','host','Storage','center-storage.png'),('VM','vm','Memory','center-vm.png')]:
 item=next(i for i,k in app.items.items() if k==(cls,ref)); app.tree.selection_set(item); app.show(); app.tabs.select(app.frames[tab]); _pump(root)
 grab_window(root.winfo_id(),dest/filename)
app.open_notifications(); _pump(root); grab_window(root.winfo_id(),dest/'center-notifications.png')
app.jobs.shutdown(wait=False); app.journal.close(); root.destroy()

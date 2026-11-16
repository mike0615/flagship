"""Workspace presentation: visual hierarchy, summaries and predictable navigation."""
import json
import tkinter as tk
from tkinter import ttk
from . import __version__
from .inventory import size, ordinary
from .redaction import safe_record


class Workspace:
    def workspace_style(self):
        style=ttk.Style(self.root)
        if 'clam' in style.theme_names(): style.theme_use('clam')
        self.root.configure(background='#edf2f7')
        style.configure('.',font=('DejaVu Sans',10),background='#edf2f7',foreground='#253c53')
        style.configure('TButton',padding=(10,6),background='white',bordercolor='#d5e0ea',relief='flat')
        style.map('TButton',background=[('active','#e3eef8')])
        style.configure('Accent.TButton',background='#087db5',foreground='white',bordercolor='#087db5')
        style.map('Accent.TButton',background=[('active','#05638f')],foreground=[('disabled','#b7c7d5')])
        style.configure('Brand.TFrame',background='#102a43')
        style.configure('Brand.TLabel',background='#102a43',foreground='white',font=('DejaVu Sans',17,'bold'))
        style.configure('BrandSmall.TLabel',background='#102a43',foreground='#aec8de',font=('DejaVu Sans',9))
        style.configure('Side.TFrame',background='#18354e')
        style.configure('Side.TLabel',background='#18354e',foreground='#bbd2e5',font=('DejaVu Sans',9,'bold'))
        style.configure('Nav.TRadiobutton',background='#18354e',foreground='#e1edf7',padding=(10,8))
        style.map('Nav.TRadiobutton',background=[('selected','#245779'),('active','#20445f')],foreground=[('selected','white')])
        style.configure('Treeview',rowheight=29,background='white',fieldbackground='white',borderwidth=0,font=('DejaVu Sans',10))
        style.configure('Treeview.Heading',font=('DejaVu Sans',9,'bold'),background='#eaf1f7',padding=7,borderwidth=0)
        style.map('Treeview',background=[('selected','#d9edfa')],foreground=[('selected','#075d8e')])
        style.configure('Inventory.Treeview',background='#18354e',fieldbackground='#18354e',foreground='#e0edf6',rowheight=29)
        style.configure('Inventory.Treeview.Heading',background='#18354e',foreground='#b7cfe2')
        style.map('Inventory.Treeview',background=[('selected','#087db5')],foreground=[('selected','white')])
        style.configure('Heading.TLabel',font=('DejaVu Sans',19,'bold'),foreground='#173e5b')
        style.configure('Muted.TLabel',foreground='#637e93',font=('DejaVu Sans',9))
        style.configure('Card.TFrame',background='white',borderwidth=1,relief='solid',bordercolor='#dce5ee')
        style.configure('CardTitle.TLabel',background='white',foreground='#688298',font=('DejaVu Sans',9,'bold'))
        style.configure('CardValue.TLabel',background='white',foreground='#173e5b',font=('DejaVu Sans',19,'bold'))
        style.configure('CardHint.TLabel',background='white',foreground='#637e93',font=('DejaVu Sans',9))
        style.configure('TNotebook',background='#edf2f7',borderwidth=0)
        style.configure('TNotebook.Tab',padding=(13,9),background='#e4edf5',foreground='#47667d')
        style.map('TNotebook.Tab',background=[('selected','white')],foreground=[('selected','#087db5')])
        style.configure('Horizontal.TProgressbar',background='#10a3a3',troughcolor='#eaf1f7',borderwidth=0,thickness=5)
        self.history=[]; self.history_index=-1; self.history_client=None; self.navigating=False
        self.resource_icons={}
        for name,color in [('host','#4ca4d6'),('VM','#22c59b'),('halted','#b1c5d7'),('SR','#e8b456'),('network','#9c91e4'),('pool','#4cbcc7')]:
            icon=tk.PhotoImage(master=self.root,width=16,height=16)
            icon.put(color,to=(2,3,14,13)); icon.put('#18354e',to=(4,5,12,9))
            self.resource_icons[name]=icon

    def brand_header(self):
        header=ttk.Frame(self.root,style='Brand.TFrame',padding=(18,10)); header.pack(fill='x')
        ttk.Label(header,text='◈  FLAGSHIP',style='Brand.TLabel').pack(side='left')
        ttk.Label(header,text='INFRASTRUCTURE WORKSPACE',style='BrandSmall.TLabel').pack(side='left',padx=22)
        ttk.Label(header,text='Native Linux  /  '+__version__,style='BrandSmall.TLabel').pack(side='right')

    def make_summary(self,parent,title):
        cards=ttk.Frame(parent); cards.pack(fill='x',pady=(0,12))
        self.summary_cards[title]=[]
        for i in range(4):
            frame=ttk.Frame(cards,style='Card.TFrame',padding=(12,12)); frame.grid(row=0,column=i,sticky='nsew',padx=(0,8 if i<3 else 0))
            cards.columnconfigure(i,weight=1,uniform='summary')
            label=ttk.Label(frame,text='',style='CardTitle.TLabel'); label.pack(anchor='w')
            value=ttk.Label(frame,text='—',style='CardValue.TLabel'); value.pack(anchor='w',pady=(8,5))
            hint=ttk.Label(frame,text='',style='CardHint.TLabel'); hint.pack(anchor='w')
            gauge=ttk.Progressbar(frame,maximum=100,length=70); gauge.pack(fill='x',pady=(10,0))
            self.summary_cards[title].append((label,value,hint,gauge))

    def summary_values(self,cls,r):
        records=self.records
        if not cls:
            guests=[v for v in records.get('VM',{}).values() if ordinary(v)]
            return [('HOSTS',str(len(records.get('host',{}))),'Connected inventory',0),('VIRTUAL MACHINES',str(len(guests)),str(sum(v.get('power_state')=='Running' for v in guests))+' running',0),('STORAGE',str(len(records.get('SR',{}))),'Repositories',0),('ALERTS',str(len(records.get('message',{}))),'Open notifications',0)]
        if cls=='host':
            metrics=records.get('host_metrics',{}).get(r.get('metrics'),{})
            total=int(metrics.get('memory_total',0)); free=int(metrics.get('memory_free',0))
            cpus=r.get('cpu_info',{}).get('cpu_count') or len(r.get('host_CPUs',[])) or '—'
            return [('STATE','Enabled' if r.get('enabled') else 'Disabled','Host placement',0),('CPU',str(cpus),'Logical processors',0),('MEMORY',size(total),size(free)+' available',100*(total-free)/total if total else 0),('VERSION',r.get('software_version',{}).get('product_version','—'),'XAPI host',0)]
        if cls=='VM':
            metrics=records.get('VM_metrics',{}).get(r.get('metrics'),{})
            utilisation=metrics.get('VCPUs_utilisation',{})
            average=sum(float(v) for v in utilisation.values())/len(utilisation)*100 if utilisation else 0
            return [('POWER',r.get('power_state','—'),'Virtual machine',0),('CPU',str(r.get('VCPUs_at_startup','—')),'Configured vCPUs',average),('MEMORY',size(r.get('memory_dynamic_max')),'Configured capacity',0),('DISKS',str(len([d for d in records.get('VBD',{}).values() if d.get('VM')==self.selected()[1] and d.get('type')=='Disk'])),'Attached virtual disks',0)]
        if cls=='SR':
            total=int(r.get('physical_size',0)); used=int(r.get('physical_utilisation',0))
            return [('TYPE',r.get('type','—'),'Storage backend',0),('CAPACITY',size(total),'Physical capacity',0),('USED',size(used),size(max(0,total-used))+' available',100*used/total if total else 0),('SHARING','Shared' if r.get('shared') else 'Local','Repository scope',0)]
        return [('TYPE',cls,'Inventory resource',0),('STORAGE',str(len(records.get('SR',{}))),'Repositories',0),('NETWORKS',str(len(records.get('network',{}))),'Networks',0),('ALERTS',str(len(records.get('message',{}))),'Notifications',0)]

    def update_workspace(self,cls,ref,record):
        selected=(cls,ref) if cls else None
        if self.history_client is not self.client:
            self.history=[]; self.history_index=-1; self.history_client=self.client
        if selected and not self.navigating and (self.history_index<0 or self.history[self.history_index]!=selected):
            self.history=self.history[:self.history_index+1]+[selected]; self.history_index=len(self.history)-1
        self.back_button.configure(state='normal' if self.history_index>0 else 'disabled')
        self.forward_button.configure(state='normal' if self.history_index<len(self.history)-1 else 'disabled')
        display={'host':'Host','VM':'Virtual machine','SR':'Storage','network':'Network','pool':'Pool'}.get(cls,'Overview')
        self.breadcrumb.configure(text='WORKSPACE  /  '+display.upper())
        for title,widgets in self.summary_cards.items():
            for (label,value,hint,gauge),(a,b,c,d) in zip(widgets,self.summary_values(cls,record) if title=='General' else self.summary_values('',{})):
                label.configure(text=a); value.configure(text=b); hint.configure(text=c); gauge.configure(value=max(0,min(100,d)))
        for console in self.consoles:
            if not console.window.winfo_exists() or not console.docked: continue
            if selected==('VM',console.vm): console.window.pack(fill='both',expand=True)
            else: console.release(); console.control.set(False); console.window.pack_forget()

    def select_resource(self,cls,ref):
        if self.navigation.get() in ('Saved Searches','Notifications'): self.navigation.set('Infrastructure')
        if (cls,ref) not in self.items.values():
            self.navigation.set('Objects'); self.search.set(''); self.populate()
        for iid,key in self.items.items():
            if key==(cls,ref):
                self.tree.selection_set(iid); self.tree.see(iid); self.show(); return True
        return False

    def navigate_history(self,direction):
        index=self.history_index+direction
        if not 0<=index<len(self.history): return
        cls,ref=self.history[index]; self.navigating=True
        try:
            if self.select_resource(cls,ref): self.history_index=index
        finally: self.navigating=False
        self.back_button.configure(state='normal' if self.history_index>0 else 'disabled')
        self.forward_button.configure(state='normal' if self.history_index<len(self.history)-1 else 'disabled')

    def advanced_properties(self):
        cls,ref=self.selected() or ('','')
        self.record_details(cls,ref)

    def record_details(self,cls,ref):
        if not cls or ref not in self.records.get(cls,{}): return
        window=tk.Toplevel(self.root); window.title('Advanced '+cls+' properties'); window.geometry('850x600')
        text=tk.Text(window,wrap='word',padx=15,pady=15)
        scroll=ttk.Scrollbar(window,command=text.yview); text.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y'); text.pack(fill='both',expand=True)
        text.insert('end',json.dumps(safe_record(self.records[cls][ref]),indent=2,default=str)); text.configure(state='disabled')

    def overview_rows(self,cls,ref,r):
        rows=[('Name',r.get('name_label','')),('Description',r.get('name_description',''))]
        if cls=='VM':
            host=self.records.get('host',{}).get(r.get('resident_on') or r.get('affinity'),{})
            rows += [('Power state',r.get('power_state','')),('Home server',host.get('name_label','Automatic placement')),('Firmware',r.get('HVM_boot_params',{}).get('firmware','Template default')),('UUID',r.get('uuid',''))]
        elif cls=='host':
            ips=[p.get('IP','') for p in self.records.get('PIF',{}).values() if p.get('host')==ref and p.get('management')]
            rows += [('Management address',', '.join(ip for ip in ips if ip)),('Software',r.get('software_version',{}).get('product_brand','XAPI host')),('UUID',r.get('uuid',''))]
        else: rows += [('UUID',r.get('uuid','')),('Tags',', '.join(r.get('tags',[])))]
        return [(None,row) for row in rows]

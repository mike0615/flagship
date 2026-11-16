"""Reviewable native management forms using the application's serialized worker."""
import tkinter as tk
from tkinter import ttk, messagebox
from .management import StoragePlan, NetworkPlan, host_operation, edit_identity
from .history import HistoryDialog
from .trust_dialog import TrustedCertificatesDialog


class ManagementUI:
    def history(self):
        return HistoryDialog(self.root,self.journal,self.inspect_object)

    def trusted_certificates(self):
        return TrustedCertificatesDialog(self.root,self.known)

    def management_form(self,title,fields,review,execute):
        if not self.client or self.busy: return
        window=tk.Toplevel(self.root); window.title(title); window.transient(self.root); window.grab_set()
        frame=ttk.Frame(window,padding=18); frame.pack(fill='both',expand=True)
        variables={}
        for i,(label,default,choices) in enumerate(fields):
            ttk.Label(frame,text=label).grid(row=i,column=0,sticky='w',pady=5,padx=6)
            var=tk.StringVar(value=default); variables[label]=var
            widget=ttk.Combobox(frame,textvariable=var,values=choices,state='readonly',width=48) if choices else ttk.Entry(frame,textvariable=var,width=50)
            widget.grid(row=i,column=1,sticky='ew',pady=5)
        def apply():
            if self.busy:
                messagebox.showinfo('Operation in progress','Wait for the current operation.',parent=window); return
            try: plan,summary=review({k:v.get() for k,v in variables.items()})
            except ValueError as exc:
                messagebox.showerror('Check settings',str(exc),parent=window); return
            if not messagebox.askyesno('Review '+title,summary+'\n\nApply these changes to the connected server?',parent=window): return
            window.destroy()
            self.submit(lambda:execute(plan),lambda report:self.management_done(report),title+'…',mutation=True)
        buttons=ttk.Frame(frame); buttons.grid(row=len(fields),column=0,columnspan=2,sticky='ew',pady=(16,0))
        ttk.Button(buttons,text='Cancel',command=window.destroy).pack(side='left')
        ttk.Button(buttons,text='Review and apply',command=apply).pack(side='right')
        window.variables=variables
        return window

    def management_done(self,report):
        self.last_workflow_report=report; self.refresh()

    def properties(self):
        cls,ref=self.selected() or ('','')
        if cls not in ('host','VM','SR','network','pool'): return
        r=self.records[cls][ref]; client=self.client
        def review(v):
            if not v['Name'].strip(): raise ValueError('Name cannot be empty.')
            return v, 'Object: '+r.get('name_label',ref)+'\nName: '+v['Name']+'\nDescription: '+v['Description']
        return self.management_form('Properties', [('Name',r.get('name_label',''),None),('Description',r.get('name_description',''),None)],
            review,lambda v:edit_identity(client,cls,ref,v['Name'],v['Description']))

    def new_sr(self):
        hosts={'{} [{}]'.format(r.get('name_label',ref),i):ref for i,(ref,r) in enumerate(self.records.get('host',{}).items(),1)}
        client=self.client
        def review(v):
            plan=StoragePlan(hosts.get(v['Host'],''),v['Name'],v['Description'],v['NFS server'],v['Export path'],v['Type']=='NFS ISO library')
            plan.validate()
            return plan,'Create '+v['Type']+'\nHost: '+v['Host']+'\nName: '+v['Name']+'\nLocation: '+v['NFS server']+':'+v['Export path']+'\nShared: Yes\nPartial storage may remain if attachment fails.'
        return self.management_form('New Storage Repository',[
          ('Type','NFS virtual disk storage',['NFS virtual disk storage','NFS ISO library']),('Host',next(iter(hosts),''),list(hosts)),
          ('Name','New storage',None),('Description','',None),('NFS server','',None),('Export path','/',None)],review,lambda plan:plan.create(client))

    def new_network(self):
        client=self.client
        def review(v):
            plan=NetworkPlan(v['Name'],v['Description'],int(v['MTU'])); plan.validate()
            return plan,'Create a private network with no physical NIC attachment.\nName: '+plan.name+'\nMTU: '+str(plan.mtu)
        return self.management_form('New Private Network',[('Name','New network',None),('Description','',None),('MTU','1500',None)],review,lambda plan:plan.create(client))

    def host_action(self,action):
        cls,ref=self.selected() or ('','')
        if cls!='host' or not self.client or self.busy: return
        r=self.records['host'][ref]; client=self.client
        if not messagebox.askyesno('Confirm host operation',action+' on '+r.get('name_label',ref)+'?\nGuests must be migrated or halted before maintenance or power operations.'): return
        def done(task):
            self.tracker.add(task,action,r.get('name_label',ref)); self.refresh()
        self.submit(lambda:host_operation(client,ref,action),done,'Submitting host '+action+'…',mutation=True,completion='submitted')

    def sr_action(self,action):
        cls,ref=self.selected() or ('','')
        if cls!='SR' or action!='scan' or not self.client or self.busy: return
        r=self.records['SR'][ref]
        if action not in r.get('allowed_operations',[]): return
        if not messagebox.askyesno('Rescan storage','Rescan '+r.get('name_label',ref)+' on the server?'): return
        client=self.client
        def work():
            current=client.call('SR.get_record',ref)
            if 'scan' not in current.get('allowed_operations',[]): raise ValueError('Rescan is no longer allowed.')
            return client.call('Async.SR.scan',ref)
        def done(task):
            self.tracker.add(task,'Rescan',r.get('name_label',ref)); self.refresh()
        self.submit(work,done,'Rescanning storage…',mutation=True,completion='submitted')

    def set_default_sr(self):
        cls,ref=self.selected() or ('','')
        if cls!='SR' or not self.client or self.busy: return
        pool=next(iter(self.records.get('pool',{})),None)
        if not pool or self.records['SR'][ref].get('content_type')=='iso': return
        if not messagebox.askyesno('Default storage','Use '+self.records['SR'][ref].get('name_label',ref)+' as the pool default storage?'): return
        client=self.client
        self.submit(lambda:client.call('pool.set_default_SR',pool,ref),lambda _:self.refresh(),'Setting default storage…',mutation=True)

    def dismiss_alert(self):
        if not self.client or self.busy: return
        key=self.table_items.get('Alerts',{}).get(next(iter(self.tables['Alerts'].selection()),''))
        if not key: return
        if not messagebox.askyesno('Dismiss alert','Permanently dismiss the selected server alert?'): return
        client=self.client
        self.submit(lambda:client.call('message.destroy',key[1]),lambda _:self.refresh(),'Dismissing alert…',mutation=True)

    def load_performance(self):
        if not self.client or self.busy: return
        cls,ref=self.selected() or ('','')
        if cls not in ('host','VM'): return
        from .performance import fetch_rrd
        client=self.client; selected=(cls,ref)
        seconds={'10 minutes':600,'1 hour':3600,'1 day':86400,'1 week':604800}[self.performance_range.get()]
        def done(series):
            if self.selected()!=selected: return
            self.performance_key=selected; self.performance_series=series
            self.performance_selector.configure(values=sorted(series))
            self.performance_source.set(next(iter(sorted(series)),''))
            self.draw_performance(); self.show()
        self.submit(lambda:fetch_rrd(client,cls,ref,seconds),done,'Loading performance history…')

    def draw_performance(self):
        canvas=self.performance_canvas; canvas.delete('all')
        samples=self.performance_series.get(self.performance_source.get(),[])
        if not samples:
            canvas.create_text(20,25,anchor='nw',text='Load history to display a server data source.',fill='#54697d'); return
        width=max(200,canvas.winfo_width()); height=max(100,canvas.winfo_height())
        left,right,top,bottom=70,width-20,20,height-30
        low=min(v for _,v in samples); high=max(v for _,v in samples)
        if high==low: high=low+1
        t0,t1=samples[0][0],samples[-1][0]
        canvas.create_line(left,top,left,bottom,right,bottom,fill='#b0becb')
        canvas.create_text(left-6,top,anchor='e',text=format(high,'.4g'),fill='#54697d')
        canvas.create_text(left-6,bottom,anchor='e',text=format(low,'.4g'),fill='#54697d')
        import time
        canvas.create_text(left,bottom+16,anchor='w',text=time.strftime('%m-%d %H:%M',time.localtime(t0)))
        canvas.create_text(right,bottom+16,anchor='e',text=time.strftime('%m-%d %H:%M',time.localtime(t1)))
        points=[(left+(t-t0)/max(1,t1-t0)*(right-left),bottom-(v-low)/(high-low)*(bottom-top)) for t,v in samples]
        # Do not bridge intervals where the server had no samples.
        steps=sorted(b[0]-a[0] for a,b in zip(samples,samples[1:]) if b[0]>a[0])
        gap=steps[len(steps)//2]*2.5 if steps else 0
        for i in range(1,len(points)):
            if samples[i][0]-samples[i-1][0]<=gap: canvas.create_line(*points[i-1],*points[i],fill='#2479aa',width=2)
        if len(points)==1:
            x,y=points[0]; canvas.create_oval(x-2,y-2,x+2,y+2,fill='#2479aa')

    def export_vm(self):
        if not self.client or self.busy: return
        cls,ref=self.selected() or ('','')
        if cls!='VM': return
        from tkinter import filedialog
        path=filedialog.asksaveasfilename(parent=self.root,title='Export VM to a new XVA file',defaultextension='.xva',filetypes=[('XVA archive','*.xva')])
        if not path or not messagebox.askyesno('Export VM','Export the halted VM to '+path+'?\nExisting files will not be overwritten.'): return
        self.start_transfer('export',path,ref)

    def import_vm(self):
        if not self.client or self.busy: return
        from tkinter import filedialog
        from .dialogs import choose_resource
        path=filedialog.askopenfilename(parent=self.root,title='Import XVA archive',filetypes=[('XVA archive','*.xva')])
        if not path: return
        storage={ref:r for ref,r in self.records.get('SR',{}).items() if r.get('content_type')=='user' and 'vdi_create' in r.get('allowed_operations',[])}
        ok,sr=choose_resource(self.root,'Import storage repository',storage)
        if not ok: return
        ok,network=choose_resource(self.root,'Import network',self.records.get('network',{}))
        if not ok: return
        if not messagebox.askyesno('Review XVA import','Import '+path+'?\nStorage: '+storage[sr].get('name_label',sr)+'\nNetwork: '+self.records['network'][network].get('name_label',network)+'\nThe imported VM stays halted. Partial resources may remain on failure.'): return
        self.start_transfer('import',path,sr,network)

    def start_transfer(self,operation,path,ref,network=None):
        import threading
        from .transfers import XVATransfer
        self.workflow_stop=threading.Event(); self.workflow_label='XVA '+operation
        self.last_workflow_report=None
        transfer=XVATransfer(self.client,stop=self.workflow_stop,progress=self.publish_workflow_progress)
        def work():
            return transfer.export_vm(ref,path) if operation=='export' else transfer.import_vm(path,ref,network)
        def done(report):
            self.workflow_stop=None; self.last_workflow_report=report
            messagebox.showinfo('XVA '+operation,report['stage'])
            self.refresh()
        self.submit(work,done,'XVA '+operation+'…',mutation=True)

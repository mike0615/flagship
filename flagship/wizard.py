"""Eight-step creation wizard. No server changes before the Finish review."""
import tkinter as tk
from tkinter import ttk, messagebox
from .workflows import VMPlan


class NewVMDialog:
    steps=('Template','Name','Installation Media','Home Server','CPU & Memory','Storage','Networking','Finish')

    def __init__(self,app):
        self.app=app; self.plan=None; self.step=0; self.values={}; self.choices={}
        self.window=tk.Toplevel(app.root); self.window.title('New VM'); self.window.transient(app.root); self.window.grab_set()
        self.window.geometry('780x540')
        self.window.minsize(680,480)
        body=ttk.Frame(self.window,padding=14); body.pack(fill='both',expand=True)
        self.step_list=tk.Listbox(body,width=22,exportselection=False,activestyle='none',height=10)
        self.step_list.pack(side='left',fill='y',padx=(0,16))
        for n,title in enumerate(self.steps,1): self.step_list.insert('end',str(n)+'. '+title)
        self.form=ttk.Frame(body); self.form.pack(fill='both',expand=True)
        self.pages=[]
        for title in self.steps:
            page=ttk.Frame(self.form); self.pages.append(page)
            ttk.Label(page,text=title,font=('sans',16,'bold')).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,18))
            page.columnconfigure(1,weight=1)
        records=app.records
        self.current=self.pages[0]
        self.combo('Template',{ref:r for ref,r in records.get('VM',{}).items() if r.get('is_a_template') and not r.get('is_a_snapshot') and not r.get('is_control_domain')})
        selected=app.selected()
        if selected and selected[0]=='VM':
            for label,ref in self.choices['Template'].items():
                if ref==selected[1]: self.values['Template'].set(label)
        self.current=self.pages[1]; self.entry('Name','New virtual machine'); self.entry('Description','')
        self.current=self.pages[2]
        isos={ref:r for ref,r in records.get('VDI',{}).items() if records.get('SR',{}).get(r.get('SR'),{}).get('content_type')=='iso'}
        self.combo('Install ISO',isos,optional='No ISO — use template boot configuration')
        self.combo('Boot mode',{'':{'name_label':'Template default'},'bios':{'name_label':'BIOS'},'uefi':{'name_label':'UEFI'}})
        self.values['Boot mode'].set(next(label for label,ref in self.choices['Boot mode'].items() if ref==''))
        self.current=self.pages[3]
        self.combo('Home Server',records.get('host',{}),optional='Automatic placement')
        self.current=self.pages[4]; self.entry('vCPUs','2'); self.entry('Memory (MiB)','2048')
        self.current=self.pages[5]
        self.combo('Storage repository',{ref:r for ref,r in records.get('SR',{}).items() if r.get('content_type')!='iso' and 'vdi_create' in r.get('allowed_operations',[])})
        self.entry('New disk (GiB)','20')
        ttk.Label(self.current,text='Installer templates receive a new disk. Installed-template disks are copied with their existing sizes and contents.',wraplength=460).grid(row=10,column=0,columnspan=2,sticky='w',pady=15)
        self.current=self.pages[6]; self.combo('Network',records.get('network',{}))
        ttk.Label(self.current,text='The new VM receives one adapter on this network. Add further disks and interfaces through Devices after creation.',wraplength=460).grid(row=10,column=0,columnspan=2,sticky='w',pady=15)
        self.review_frame=self.pages[7]
        self.review_text=tk.Text(self.review_frame,width=54,height=16,wrap='word',state='disabled')
        self.review_text.grid(row=1,column=0,columnspan=2,sticky='nsew'); self.review_frame.rowconfigure(1,weight=1)
        self.start=tk.BooleanVar(value=False)
        ttk.Checkbutton(self.review_frame,text='Start VM after successful creation',variable=self.start,command=self.review).grid(row=2,column=0,columnspan=2,sticky='w',pady=10)
        buttons=ttk.Frame(self.window,padding=14); buttons.pack(fill='x')
        ttk.Button(buttons,text='Cancel',command=self.window.destroy).pack(side='left')
        self.next_button=ttk.Button(buttons,text='Next >',command=self.next); self.next_button.pack(side='right')
        self.back_button=ttk.Button(buttons,text='< Back',command=self.back); self.back_button.pack(side='right',padx=6)
        self.show_step(0)

    def entry(self,label,value):
        row=len(self.current.grid_slaves())//2+1
        ttk.Label(self.current,text=label).grid(row=row,column=0,sticky='w',padx=4,pady=6)
        var=tk.StringVar(value=value); ttk.Entry(self.current,textvariable=var,width=38).grid(row=row,column=1,sticky='ew',pady=6)
        self.values[label]=var

    def combo(self,label,records,optional=None):
        choices={optional:''} if optional else {}
        for n,(ref,r) in enumerate(sorted(records.items(),key=lambda x:x[1].get('name_label','')),1):
            choices['{} [{}]'.format(r.get('name_label') or r.get('uuid') or 'Unnamed',n)]=ref
        row=len(self.current.grid_slaves())//2+1
        var=tk.StringVar(value=next(iter(choices),''))
        ttk.Label(self.current,text=label).grid(row=row,column=0,sticky='w',padx=4,pady=6)
        ttk.Combobox(self.current,textvariable=var,values=list(choices),width=36,state='readonly').grid(row=row,column=1,sticky='ew',pady=6)
        self.values[label]=var; self.choices[label]=choices

    def selected(self,label): return self.choices[label].get(self.values[label].get(),'')

    def show_step(self,index):
        for page in self.pages: page.pack_forget()
        self.step=index; self.pages[index].pack(fill='both',expand=True)
        self.step_list.selection_clear(0,'end'); self.step_list.selection_set(index)
        self.back_button.configure(state='disabled' if index==0 else 'normal')
        self.next_button.configure(text='Create Now' if index==7 else 'Next >')

    def next(self):
        if self.step==7: self.create()
        elif self.step==6: self.review()
        else: self.show_step(self.step+1)

    def review(self):
        try:
            self.plan=VMPlan(self.selected('Template'),self.values['Name'].get().strip(),self.selected('Storage repository'),
              self.selected('Network'),int(self.values['vCPUs'].get()),int(self.values['Memory (MiB)'].get()),
              int(self.values['New disk (GiB)'].get()),self.selected('Install ISO'),self.start.get(),
              self.values['Description'].get(),self.selected('Home Server'),self.selected('Boot mode'))
            self.plan.validate()
        except ValueError as exc:
            self.plan=None; messagebox.showerror('Check VM settings',str(exc),parent=self.window); return
        lines=[k+': '+v.get() for k,v in self.values.items()]
        lines+=['Start after creation: '+('Yes' if self.plan.start else 'No'),'','This creates server resources and may copy template disks. Inherited network interfaces on the new VM are replaced by one adapter.','',
          'If interrupted, partial resources or tasks may remain. Use Tools → Save workflow report and inspect server state before retrying.']
        self.review_text.configure(state='normal'); self.review_text.delete('1.0','end'); self.review_text.insert('end','\n'.join(lines)); self.review_text.configure(state='disabled')
        self.show_step(7)

    def back(self):
        self.plan=None; self.show_step(max(0,self.step-1))

    def create(self):
        if self.app.busy:
            messagebox.showinfo('Operation in progress','Wait for the current operation, then choose Create again.',parent=self.window); return
        if self.plan:
            self.window.destroy(); self.app.start_provisioning(self.plan)

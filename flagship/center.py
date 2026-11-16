"""Native Center-style resource navigation and object-specific inventory pages."""
import json
import tkinter as tk
from tkinter import ttk
from .inventory import related, tabs_for, values, FIELDS, ordinary, size
from .redaction import safe_record

VM_ACTIONS = [('Start','start'),('Shut down','clean_shutdown'),('Reboot','clean_reboot'),
 ('Pause','pause'),('Unpause','unpause'),('Suspend','suspend'),('Resume','resume'),
 ('Snapshot','snapshot'),('Clone','clone'),('Revert snapshot','revert'),
 ('Migrate in pool','pool_migrate'),('Rename','set_name_label'),('Force off','hard_shutdown'),('Delete VM record','destroy')]


class CenterShell:
    def build_shell(self, width):
        self.navigation = tk.StringVar(value='Infrastructure')
        self.show_templates = tk.BooleanVar(value=False)
        self.show_snapshots = tk.BooleanVar(value=False)
        self.show_local = tk.BooleanVar(value=True)
        self.auto_refresh = tk.BooleanVar(value=True)
        style = ttk.Style(self.root)
        if 'clam' in style.theme_names(): style.theme_use('clam')
        style.configure('.', background='#f2f4f7', foreground='#20354a')
        style.configure('TButton', padding=(6,4))
        style.configure('Treeview', rowheight=25, background='white', fieldbackground='white')
        style.map('Treeview', background=[('selected','#245b87')], foreground=[('selected','white')])
        style.configure('Heading.TLabel', font=('sans',16,'bold'), foreground='#203b59')
        style.configure('TNotebook.Tab', padding=(10,6))
        self.make_menus()
        for key, command in (('<F1>',self.help),('<Control-n>',self.new_vm),('<Control-e>',lambda:self.action('clean_shutdown')),
                             ('<Control-r>',lambda:self.action('clean_reboot')),('<Control-y>',lambda:self.action('suspend')),('<F5>',self.refresh)):
            self.root.bind(key, lambda e,c=command:c())
        toolbar = ttk.Frame(self.root, padding=5); toolbar.pack(fill='x')
        self.buttonbar = ttk.Frame(toolbar); self.buttonbar.pack(fill='x')
        self.toolbar_buttons = []; self.toolbar_columns = None
        for label, command in [('Add New Server',self.connect),('Disconnect',self.disconnect),('Refresh',self.refresh),
          ('New VM',self.new_vm),('New Storage',self.new_sr),('CPU / memory',self.hardware),('Devices',self.manage_devices),('Console',self.open_console),('Export inventory',self.export)]:
            self.toolbar_buttons.append(ttk.Button(self.buttonbar,text=label,command=command))
        self.buttonbar.bind('<Configure>',lambda e:self.layout_toolbar(e.width)); self.layout_toolbar(width-12)
        split = ttk.Panedwindow(self.root,orient='horizontal'); split.pack(fill='both',expand=True)
        left = ttk.Frame(split,width=260); split.add(left,weight=1)
        self.search = tk.StringVar()
        ttk.Entry(left,textvariable=self.search).pack(fill='x',padx=7,pady=7)
        self.search.trace_add('write',lambda *_:self.populate())
        treeframe = ttk.Frame(left); treeframe.pack(fill='both',expand=True)
        self.tree = ttk.Treeview(treeframe,columns=('state',),selectmode='browse')
        self.tree.heading('#0',text='Resources'); self.tree.heading('state',text='State')
        self.tree.column('#0',width=190,minwidth=100); self.tree.column('state',width=65,minwidth=50)
        scroll = ttk.Scrollbar(treeframe,command=self.tree.yview); self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y'); self.tree.pack(fill='both',expand=True)
        for title in ('Infrastructure','Objects','Organization Views','Saved Searches','Notifications'):
            ttk.Radiobutton(left,text=title,value=title,variable=self.navigation,command=self.populate).pack(fill='x',padx=8,pady=3)
        right = ttk.Frame(split); split.add(right,weight=4)
        banner = ttk.Frame(right,padding=(14,10)); banner.pack(fill='x')
        self.object_title = ttk.Label(banner,text='Flagship',style='Heading.TLabel'); self.object_title.pack(side='left')
        self.object_subtitle = ttk.Label(banner,text='Native XAPI management'); self.object_subtitle.pack(side='right')
        actions = ttk.Frame(right,padding=4); actions.pack(side='bottom',fill='x')
        self.action_buttons = {}
        for i,(label,action) in enumerate(VM_ACTIONS):
            b = ttk.Button(actions,text=label,command=lambda a=action:self.action(a))
            b.grid(row=i//5,column=i%5,sticky='ew',padx=2,pady=2); actions.columnconfigure(i%5,weight=1)
            self.action_buttons[action] = b
        self.tabs = ttk.Notebook(right); self.tabs.pack(fill='both',expand=True)
        self.frames, self.views, self.tables, self.table_items = {}, {}, {}, {}
        commands = {
         'Home':[('Add New Server',self.connect),('New VM',self.new_vm),('Help',self.help)],
         'General':[('Properties',self.properties),('Refresh',self.refresh)],
         'Memory':[('Edit VM memory',self.hardware)],
         'Storage':[('New SR',self.new_sr),('Manage VM disks',self.manage_devices),('Rescan SR',lambda:self.sr_action('scan'))],
         'Networking':[('Add Network',self.new_network),('Manage VM interfaces',self.manage_devices)],
         'Performance':[('Load history',self.load_performance)],'NICs':[('Refresh',self.refresh)],'Console':[('Open native console',self.open_console)],
         'Snapshots':[('Take snapshot',lambda:self.action('snapshot')),('Revert selected',lambda:self.table_action('Snapshots','revert')),
                      ('Delete selected record',lambda:self.table_action('Snapshots','destroy'))],
         'Search':[('Export inventory',self.export)],'Tasks':[('Refresh',self.refresh),('Request cancellation',self.cancel_task)],
         'Alerts':[('Refresh',self.refresh),('Dismiss selected',self.dismiss_alert)]}
        for title in ('Home','General','Memory','Storage','Networking','NICs','GPU','Console','Performance','Snapshots','Search','Tasks','Alerts'):
            frame = ttk.Frame(self.tabs,padding=10); self.frames[title] = frame
            controls = ttk.Frame(frame); controls.pack(fill='x',pady=(0,8))
            for label,command in commands.get(title,[]): ttk.Button(controls,text=label,command=command).pack(side='left',padx=3)
            if title == 'Search':
                self.inventory_filter = tk.StringVar()
                ttk.Entry(controls,textvariable=self.inventory_filter).pack(side='right',fill='x',expand=True)
                self.inventory_filter.trace_add('write',lambda *_:self.show())
            if title == 'Performance':
                self.performance_range = tk.StringVar(value='10 minutes')
                ttk.Combobox(controls,textvariable=self.performance_range,values=['10 minutes','1 hour','1 day','1 week'],state='readonly',width=12).pack(side='left')
                self.performance_source = tk.StringVar()
                self.performance_selector = ttk.Combobox(controls,textvariable=self.performance_source,state='readonly',width=24)
                self.performance_selector.pack(side='left',padx=5)
                self.performance_selector.bind('<<ComboboxSelected>>',lambda e:self.draw_performance())
                self.performance_canvas = tk.Canvas(frame,background='white',height=190,highlightthickness=0)
                self.performance_canvas.pack(fill='x',pady=5)
                self.performance_canvas.bind('<Configure>',lambda e:self.draw_performance())
                self.performance_series = {}; self.performance_key = None
            tf = ttk.Frame(frame); tf.pack(fill='both',expand=True)
            table = ttk.Treeview(tf,show='headings',selectmode='browse',height=8)
            sy = ttk.Scrollbar(tf,command=table.yview); sx = ttk.Scrollbar(tf,orient='horizontal',command=table.xview)
            table.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
            sy.pack(side='right',fill='y'); sx.pack(side='bottom',fill='x'); table.pack(fill='both',expand=True)
            self.tables[title] = table
            table.bind('<Double-1>',lambda e,t=title:self.navigate_table(t))
            text = tk.Text(frame,height=4,wrap='word',relief='flat',background='#f5f7fa',foreground='#30465a',state='disabled')
            text.pack(fill='x',pady=(8,0)); self.views[title] = text
        self.status = tk.StringVar(value='Disconnected. Add a server to get started.')
        sb = ttk.Frame(self.root); sb.pack(side='bottom',fill='x',before=split)
        self.tls_indicator = tk.Label(sb,text='',padx=8); self.tls_indicator.pack(side='right')
        self.alert_count = ttk.Button(sb,text='Alerts: 0',command=self.open_notifications); self.alert_count.pack(side='right')
        ttk.Label(sb,textvariable=self.status,padding=6).pack(side='left',fill='x',expand=True)
        self.tree.bind('<<TreeviewSelect>>',lambda *_:self.show()); self.tree.bind('<Button-3>',self.context_menu)
        self.populate(); self.root.after(10000,self.refresh_inventory_timer)

    def make_menus(self):
        bar = tk.Menu(self.root); self.menus = {}
        for title in ('File','View','Pool','Server','VM','Storage','Templates','Tools','Help'):
            menu = tk.Menu(bar,tearoff=False); self.menus[title] = menu; bar.add_cascade(label=title,menu=menu)
        self.root.configure(menu=bar)
        self.menus['File'].add_command(label='Import XVA…',command=self.import_vm)
        self.menus['File'].add_command(label='Export inventory…',command=self.export)
        self.menus['File'].add_separator(); self.menus['File'].add_command(label='Exit',command=self.close)
        for label,var in [('Custom and system templates',self.show_templates),('Snapshots',self.show_snapshots),('Local storage',self.show_local)]:
            self.menus['View'].add_checkbutton(label=label,variable=var,command=self.populate)
        self.menus['View'].add_checkbutton(label='Refresh inventory every 10 seconds',variable=self.auto_refresh)
        self.menus['View'].add_command(label='Refresh now',accelerator='F5',command=self.refresh)
        for label,command in [('Stop workflow monitoring',self.stop_workflow),('Save workflow report',self.save_workflow_report),
          ('Operation history / recovery',self.history),('Request task cancellation…',self.cancel_task),('Trusted certificates…',self.trusted_certificates)]:
            self.menus['Tools'].add_command(label=label,command=command)
        self.menus['Help'].add_command(label='Flagship Help',command=self.help,accelerator='F1')
        self.menus['Help'].add_command(label='About Flagship',command=self.about)

    def update_commands(self):
        cls,ref = self.selected() or ('',''); r = self.records.get(cls,{}).get(ref,{})
        connected = self.client is not None and not self.busy
        def add(menu,label,command,enabled=True):
            self.menus[menu].add_command(label=label,command=command,state='normal' if enabled else 'disabled')
        for title in ('Pool','Server','VM','Storage','Templates'): self.menus[title].delete(0,'end')
        add('Pool','Properties…',self.properties,connected and cls=='pool')
        add('Server','Add New Server…',self.connect,not self.client and not self.busy)
        add('Server','Disconnect',self.disconnect,connected)
        for label,action in [('Enter maintenance mode','disable'),('Exit maintenance mode','enable'),('Reboot','reboot'),('Shut down','shutdown')]:
            add('Server',label,lambda a=action:self.host_action(a),connected and cls=='host')
        add('Server','Properties…',self.properties,connected and cls=='host')
        add('VM','New VM…',self.new_vm,connected)
        for label,action in VM_ACTIONS:
            enabled = connected and cls=='VM' and (action in r.get('allowed_operations',[]) or action=='set_name_label')
            self.action_buttons[action].configure(state='normal' if enabled else 'disabled')
            add('VM',label,lambda a=action:self.action(a),enabled)
        add('VM','Export XVA…',self.export_vm,connected and cls=='VM' and not r.get('is_control_domain') and r.get('power_state')=='Halted')
        add('VM','CPU / memory…',self.hardware,connected and cls=='VM' and ordinary(r) and r.get('power_state')=='Halted')
        add('VM','Devices…',self.manage_devices,connected and cls=='VM' and ordinary(r))
        add('VM','Properties…',self.properties,connected and cls=='VM')
        add('Storage','New Storage Repository…',self.new_sr,connected)
        add('Storage','Rescan',lambda:self.sr_action('scan'),connected and cls=='SR' and 'scan' in r.get('allowed_operations',[]))
        add('Storage','Set as default',self.set_default_sr,connected and cls=='SR' and r.get('content_type')!='iso')
        add('Storage','Properties…',self.properties,connected and cls=='SR')
        add('Templates','Create VM from selection…',self.new_vm,connected and cls=='VM' and r.get('is_a_template'))
        add('Templates','Copy',lambda:self.action('clone'),connected and cls=='VM' and r.get('is_a_template') and 'clone' in r.get('allowed_operations',[]))
        add('Templates','Properties…',self.properties,connected and cls=='VM' and r.get('is_a_template'))

    def populate(self):
        selected = self.selected(); self.tree.delete(*self.tree.get_children()); self.items = {}
        term = self.search.get().casefold(); flat = self.navigation.get()!='Infrastructure' or bool(term)
        root = self.tree.insert('','end',text='Flagship',open=True); nodes = {}; groups = {}
        def insert(parent,cls,ref,r):
            label = r.get('name_label') or r.get('uuid') or ref
            if term and term not in (label+' '+r.get('uuid','')).casefold(): return
            node = self.tree.insert(parent,'end',text=label,open=True,values=(r.get('power_state',''),))
            self.items[node]=(cls,ref); nodes[(cls,ref)]=node
            if selected==(cls,ref): self.tree.selection_set(node)
        for ref,r in self.records.get('pool',{}).items(): insert(root,'pool',ref,r)
        poolnode = next((nodes.get(('pool',r)) for r in self.records.get('pool',{})),None) or root
        for ref,r in self.records.get('host',{}).items(): insert(poolnode,'host',ref,r)
        for cls in ('VM','SR','network'):
            for ref,r in sorted(self.records.get(cls,{}).items(),key=lambda x:x[1].get('name_label','').casefold()):
                if cls=='VM':
                    if r.get('is_control_domain'): continue
                    if not flat and r.get('is_a_template') and not self.show_templates.get(): continue
                    if not flat and r.get('is_a_snapshot') and not self.show_snapshots.get(): continue
                if cls=='SR' and not r.get('shared') and not self.show_local.get(): continue
                category = ('Snapshots' if r.get('is_a_snapshot') else 'Templates' if r.get('is_a_template') else 'Virtual machines') if cls=='VM' else {'SR':'Storage','network':'Networks'}[cls]
                parent = nodes.get(('host',r.get('resident_on') or r.get('affinity'))) or poolnode
                if cls=='SR' and not r.get('shared'):
                    hosts=[p.get('host') for p in self.records.get('PBD',{}).values() if p.get('SR')==ref]
                    if hosts: parent=nodes.get(('host',hosts[0])) or poolnode
                if flat:
                    if self.navigation.get()=='Organization Views': category=', '.join(r.get('tags',[])) or 'Untagged'
                    if category not in groups: groups[category]=self.tree.insert(root,'end',text=category,open=True)
                    parent=groups[category]
                insert(parent,cls,ref,r)
        self.show()

    def open_notifications(self):
        self.navigation.set('Notifications'); self.populate()

    def fill_table(self,title,columns,rows):
        table=self.tables[title]
        old=self.table_items.get(title,{}).get(next(iter(table.selection()),''))
        table.delete(*table.get_children()); table.configure(columns=tuple(str(i) for i in range(len(columns))))
        for i,label in enumerate(columns):
            table.heading(str(i),text=label,command=lambda c=str(i),t=table:self.sort_table(t,c))
            table.column(str(i),width=160 if i==0 else 125,minwidth=65)
        self.table_items[title]={}
        for key,row in rows:
            iid=table.insert('','end',values=row); self.table_items[title][iid]=key
            if key is not None and key==old: table.selection_set(iid)

    @staticmethod
    def sort_table(table,column):
        rows=[(table.set(i,column),i) for i in table.get_children()]
        try: rows.sort(key=lambda x:float(x[0]))
        except ValueError: rows.sort(key=lambda x:x[0].casefold())
        for n,(_,iid) in enumerate(rows): table.move(iid,'',n)

    def show(self):
        cls,ref=self.selected() or ('',''); record=self.records.get(cls,{}).get(ref,{})
        self.object_title.configure(text=record.get('name_label') or 'Flagship')
        self.object_subtitle.configure(text=(cls+'  •  '+record.get('power_state','')) if cls else 'Native XAPI management')
        visible=tabs_for(cls,record)
        if self.navigation.get()=='Notifications': visible=('Alerts','Tasks')
        elif self.navigation.get()=='Saved Searches': visible=('Search',)
        current=self.tabs.select()
        for title,frame in self.frames.items():
            if title in visible: self.tabs.add(frame,text=title)
            elif str(frame) in self.tabs.tabs(): self.tabs.hide(frame)
        for index,title in enumerate(visible): self.tabs.insert(index,self.frames[title])
        self.tabs.select(current if current in [str(self.frames[t]) for t in visible] else self.frames[visible[0]])
        for title,view in self.views.items():
            kind,data=related(self.records,cls,ref,title); text=''
            if title=='General':
                self.fill_table(title,('Property','Value'),[(None,(k.replace('_',' ').capitalize(),self.describe(v))) for k,v in safe_record(record).items()])
                text=record.get('name_label','')+'\n'+record.get('name_description','')
            elif title=='Home':
                self.fill_table(title,('Resource','Count'),[(None,(label,len(self.records.get(k,{})))) for label,k in [('Servers','host'),('VMs and templates','VM'),('Storage repositories','SR'),('Networks','network')]])
                text='Welcome to Flagship\nAdd a server, then select a host, virtual machine or storage repository. Navigate by infrastructure, object type or tags; inspect tasks and alerts in Notifications.'
            elif title=='Search':
                term=self.inventory_filter.get().casefold(); rows=[]
                for c in ('host','VM','SR','network'):
                    for r,obj in self.records.get(c,{}).items():
                        if obj.get('is_control_domain'): continue
                        row=(obj.get('name_label',r),c,obj.get('power_state',''),obj.get('uuid',''))
                        if not term or term in ' '.join(row).casefold(): rows.append(((c,r),row))
                self.fill_table(title,('Name','Type','State','UUID'),rows)
                text='Filter by name, object type, power state or UUID. Double-click a row to open it.'
            elif title=='Performance':
                if self.performance_key != (cls,ref):
                    self.performance_series={}; self.performance_key=(cls,ref); self.draw_performance()
                self.fill_table(title,('Data source','Latest value'),[(None,(k,format(v[-1][1],'.5g'))) for k,v in self.performance_series.items()])
                text='Load RRD history from the selected host. Values use the server data source units; gaps are unavailable samples. TLS trust is required for the resident host.'
            elif title=='Console':
                self.fill_table(title,('Console','State'),[])
                text='Open native console uses the authenticated TLS VNC viewer in a separate window. Input is opt-in.' if cls=='VM' else 'Host text console is not yet supported by the native viewer.'
            else:
                columns=[x[0] for x in FIELDS.get(kind,(('Name','name_label'),('UUID','uuid')))]
                self.fill_table(title,columns,[((kind,r),values(self.records,kind,obj)) for r,obj in data.items()])
                if title=='Memory':
                    metrics=self.records.get('host_metrics',{}).get(record.get('metrics'),{})
                    text=('Host total: '+size(metrics.get('memory_total'))+'   Free: '+size(metrics.get('memory_free'))) if cls=='host' else 'Configured memory: '+size(record.get('memory_dynamic_max'))
                elif title=='GPU' and not data: text='No GPU records available for this server.'
                elif title=='Tasks': text=self.tracker.summary()
                else: text='{} item(s). Double-click a related object to open it.'.format(len(data))
                if title in ('Storage','Networking'): text+='\n'+', '.join(data)
            view.configure(state='normal'); view.delete('1.0','end'); view.insert('end',text); view.configure(state='disabled')
        self.alert_count.configure(text='Alerts: '+str(len(self.records.get('message',{}))))
        self.update_commands()

    @staticmethod
    def describe(value):
        if isinstance(value,bool): return 'Yes' if value else 'No'
        if isinstance(value,(dict,list)): return json.dumps(value,ensure_ascii=False,default=str)
        return str(value)

    def navigate_table(self,title):
        key=self.table_items.get(title,{}).get(next(iter(self.tables[title].selection()),''))
        if not key: return False
        if key not in self.items.values():
            self.navigation.set('Objects'); self.search.set(''); self.populate()
        for iid,value in self.items.items():
            if value==key:
                self.tree.selection_set(iid); self.tree.see(iid); self.show(); return True
        return False

    def table_action(self,title,action):
        if self.navigate_table(title): self.action(action)

    def context_menu(self,event):
        iid=self.tree.identify_row(event.y)
        if not iid: return
        self.tree.selection_set(iid); self.show()
        cls=(self.selected() or ('',''))[0]
        menu=self.menus.get({'host':'Server','VM':'VM','SR':'Storage','pool':'Pool'}.get(cls))
        if menu:
            try: menu.tk_popup(event.x_root,event.y_root)
            finally: menu.grab_release()

    def refresh_inventory_timer(self):
        if self.closing: return
        self.root.after(10000,self.refresh_inventory_timer)
        if self.auto_refresh.get() and self.client and not self.busy and not self.monitor_paused: self.refresh()

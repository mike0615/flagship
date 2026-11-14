"""Tk desktop: all network work is serialized outside the Tk main thread."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from . import __version__
from .api import Client, APIError
from .tasks import TaskTracker
from .workflows import Provisioner, WorkflowError, configure_hardware, MiB, stage_label
from .wizard import NewVMDialog


def safe_record(value):
    """Avoid exposing opaque session/console tokens in inventory exports."""
    if isinstance(value, dict):
        return {k: ('[redacted]' if any(s in k.lower() for s in
                ('password', 'secret', 'session', 'token', 'location')) else safe_record(v))
                for k, v in value.items()}
    if isinstance(value, list):
        return [safe_record(v) for v in value]
    return value


class Application:
    def __init__(self, root):
        self.root = root
        self.client = None
        self.records = {}
        self.tracker = TaskTracker()
        self.monitor_paused = False
        self.items = {}
        self.jobs = ThreadPoolExecutor(max_workers=1)
        self.results = queue.Queue()
        self.workflow_updates = queue.Queue()
        self.busy = False
        self.closing = False
        self.workflow_stop = None
        self.last_workflow_report = None
        root.title('XenAdmin Rocky — ' + __version__)
        root.geometry('1200x760')
        menu = tk.Menu(root)
        tools = tk.Menu(menu, tearoff=False)
        tools.add_command(label='Stop workflow monitoring', command=self.stop_workflow)
        tools.add_command(label='Save workflow report', command=self.save_workflow_report)
        menu.add_cascade(label='Tools', menu=tools)
        root.configure(menu=menu)
        toolbar = ttk.Frame(root, padding=6)
        toolbar.pack(fill='x')
        for label, command in [('Connect', self.connect), ('Disconnect', self.disconnect),
                               ('Refresh', self.refresh), ('New VM', self.new_vm),
                               ('CPU / memory', self.hardware), ('Export inventory', self.export),
                               ('Help', self.help)]:
            ttk.Button(toolbar, text=label, command=command).pack(side='left', padx=3)
        self.search = tk.StringVar()
        ttk.Entry(toolbar, textvariable=self.search).pack(side='right')
        ttk.Label(toolbar, text='Filter inventory:').pack(side='right')
        self.search.trace_add('write', lambda *_: self.populate())
        split = ttk.Panedwindow(root, orient='horizontal')
        split.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(split, columns=('state',), selectmode='browse')
        self.tree.heading('#0', text='Resources')
        self.tree.heading('state', text='State')
        self.tree.column('state', width=95)
        split.add(self.tree, weight=1)
        right = ttk.Frame(split)
        split.add(right, weight=3)
        self.tabs = ttk.Notebook(right)
        self.tabs.pack(fill='both', expand=True)
        self.views = {}
        for title in ('General', 'Storage', 'Networking', 'Snapshots', 'Tasks', 'Alerts'):
            frame = ttk.Frame(self.tabs)
            view = tk.Text(frame, wrap='none', state='disabled')
            scroll = ttk.Scrollbar(frame, command=view.yview)
            view.configure(yscrollcommand=scroll.set)
            view.pack(side='left', fill='both', expand=True)
            scroll.pack(side='right', fill='y')
            self.tabs.add(frame, text=title)
            self.views[title] = view
        actions = ttk.Frame(right, padding=6)
        actions.pack(fill='x')
        for index, (label, action) in enumerate([
                ('Start', 'start'), ('Shut down', 'clean_shutdown'),
                ('Reboot', 'clean_reboot'), ('Pause', 'pause'), ('Unpause', 'unpause'),
                ('Suspend', 'suspend'), ('Resume', 'resume'), ('Snapshot', 'snapshot'),
                ('Clone', 'clone'), ('Revert snapshot', 'revert'),
                ('Migrate in pool', 'pool_migrate'), ('Rename', 'set_name_label'),
                ('Force off', 'hard_shutdown'), ('Delete VM record', 'destroy')]):
            ttk.Button(actions, text=label, command=lambda a=action: self.action(a)).grid(
                row=index // 5, column=index % 5, sticky='ew', padx=2, pady=2)
        self.status = tk.StringVar(value='Disconnected. Connect to a pool coordinator using HTTPS.')
        ttk.Label(root, textvariable=self.status, padding=6).pack(fill='x')
        self.tree.bind('<<TreeviewSelect>>', lambda *_: self.show())
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)
        root.after(3000, self.poll_tasks)

    def submit(self, work, done, label):
        if self.busy or self.closing:
            messagebox.showinfo('Operation in progress', 'Wait for the current operation to finish.')
            return
        self.busy = True
        self.status.set(label)
        future = self.jobs.submit(work)
        future.add_done_callback(lambda f: self.results.put((f, done)))

    def poll(self):
        latest = None
        while True:
            try:
                latest = self.workflow_updates.get_nowait()
            except queue.Empty:
                break
        if latest:
            self.last_workflow_report = latest
            self.status.set('VM creation: ' + latest.get('label', latest['stage']))
            for task in latest['tasks']:
                self.records.setdefault('task', {})[task['task']] = {
                    'name_label': stage_label(task['method']), 'status': task['status'],
                    'progress': task.get('progress', 0)}
            self.show()
        try:
            future, done = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            try:
                value = future.result()
                done(value)
            except Exception as exc:
                # Do not display transport tracebacks, RPC arguments or session tokens.
                self.status.set('Operation failed: ' + (str(exc) if isinstance(exc, APIError) else type(exc).__name__))
                if isinstance(exc, WorkflowError):
                    self.last_workflow_report = {'stage': exc.stage, 'reason': exc.reason,
                                                 'resources': exc.resources, 'tasks': exc.tasks}
                self.workflow_stop = None
                error_message = (str(exc) if isinstance(exc, ValueError) else
                    'The server or connection rejected the operation. Check TLS trust, coordinator address, '
                    'permissions and current state. Refresh before retrying a mutation.')
                if isinstance(exc, WorkflowError):
                    error_message = (stage_label(exc.stage) + ': ' + exc.reason +
                        '\n\nPartial resources or server tasks may remain. Use Tools → Save workflow report, '
                        'then inspect the recorded objects before retrying. No automatic cleanup was attempted.')
                messagebox.showerror('Operation failed', error_message)
        self.root.after(100, self.poll)

    def connect(self):
        if self.client or self.busy:
            messagebox.showinfo('Connection', 'Disconnect the existing connection first.')
            return
        dialog = tk.Toplevel(self.root)
        dialog.title('Connect to pool coordinator')
        fields = {}
        for row, (key, default) in enumerate([('Endpoint', 'https://'), ('Username', 'root'),
                                                ('Password', ''), ('CA PEM file (optional)', '')]):
            ttk.Label(dialog, text=key).grid(row=row, column=0, padx=8, pady=5)
            entry = ttk.Entry(dialog, width=48, show='*' if key == 'Password' else '')
            entry.insert(0, default)
            entry.grid(row=row, column=1, padx=8, pady=5)
            fields[key] = entry
        def accept():
            endpoint, username, password, ca = [e.get() for e in fields.values()]
            dialog.destroy()
            def work():
                client = Client(endpoint, ca or None)
                try:
                    client.login(username, password)
                    records, errors = client.inventory()
                    if not records.get('pool') or not records.get('host'):
                        raise ValueError('Pool and host inventory required; verify permissions and coordinator address.')
                    return client, records, errors
                except Exception:
                    try:
                        client.logout()
                    except Exception:
                        pass
                    raise
            def done(result):
                self.client, self.records, errors = result
                self.populate()
                self.status.set('Connected. ' + self.warning(errors))
            self.submit(work, done, 'Connecting…')
        ttk.Button(dialog, text='Connect', command=accept).grid(row=4, column=1, pady=8)
        dialog.transient(self.root)
        dialog.grab_set()

    @staticmethod
    def warning(errors):
        return ('Unavailable inventory: ' + ', '.join(errors)) if errors else 'Inventory up to date.'

    def disconnect(self):
        if not self.client:
            return
        client = self.client
        def done(_):
            self.client = None
            self.tracker = TaskTracker()
            self.records = {}
            self.populate()
            self.show()
            self.status.set('Disconnected.')
        self.submit(client.logout, done, 'Disconnecting…')

    def refresh(self):
        if not self.client:
            return
        def done(result):
            self.records, errors = result
            self.monitor_paused = False
            self.populate()
            self.show()
            self.status.set(self.warning(errors))
        self.submit(self.client.inventory, done, 'Refreshing inventory…')

    def populate(self):
        selection = self.tree.selection()
        selected = self.items.get(selection[0]) if selection else None
        self.tree.delete(*self.tree.get_children())
        self.items = {}
        term = self.search.get().casefold()
        groups = [('Pools', 'pool'), ('Hosts', 'host'), ('Virtual machines', 'VM'),
                  ('Templates', 'VM'), ('Snapshots', 'VM'), ('Storage', 'SR'), ('Networks', 'network')]
        for label, cls in groups:
            parent = self.tree.insert('', 'end', text=label, open=True)
            for ref, record in sorted(self.records.get(cls, {}).items(),
                                      key=lambda item: item[1].get('name_label', '')):
                if cls == 'VM':
                    category = ('Snapshots' if record.get('is_a_snapshot') else
                                'Templates' if record.get('is_a_template') else 'Virtual machines')
                    if label != category or record.get('is_control_domain'):
                        continue
                name = record.get('name_label') or record.get('uuid', ref)
                if term and term not in (name + ' ' + record.get('uuid', '')).casefold():
                    continue
                item = self.tree.insert(parent, 'end', text=name,
                                        values=(record.get('power_state', ''),))
                self.items[item] = (cls, ref)
                if selected == (cls, ref):
                    self.tree.selection_set(item)

    def selected(self):
        selection = self.tree.selection()
        return self.items.get(selection[0]) if selection else None

    def show(self):
        selected = self.selected()
        cls, ref = selected or ('', '')
        record = self.records.get(cls, {}).get(ref, {})
        related = {
            'General': record,
            'Storage': {k: v for k, v in self.records.get('VBD' if cls == 'VM' else 'VDI', {}).items()
                        if (v.get('VM') == ref if cls == 'VM' else v.get('SR') == ref)},
            'Networking': {k: v for k, v in self.records.get('VIF' if cls == 'VM' else 'PIF', {}).items()
                           if (v.get('VM') == ref if cls == 'VM' else v.get('host') == ref)},
            'Snapshots': {k: v for k, v in self.records.get('VM', {}).items() if v.get('snapshot_of') == ref},
            'Tasks': self.records.get('task', {}), 'Alerts': self.records.get('message', {})}
        for title, view in self.views.items():
            view.configure(state='normal')
            view.delete('1.0', 'end')
            if title == 'Tasks' and self.tracker.tasks:
                view.insert('end', self.tracker.summary() + '\n\nPool task records:\n')
            view.insert('end', json.dumps(safe_record(related[title]), indent=2, default=str))
            view.configure(state='disabled')

    def action(self, action):
        if self.busy or not self.client:
            return
        selected = self.selected()
        if not selected or selected[0] != 'VM':
            messagebox.showinfo('Select VM', 'Select a VM, template or snapshot first.')
            return
        _, ref = selected
        record = self.records['VM'][ref]
        if action not in record.get('allowed_operations', []) and action != 'set_name_label':
            messagebox.showwarning('Unavailable action', 'The server does not allow this operation in the current state.')
            return
        args = []
        if action in ('start', 'resume'):
            args = [False, False]
        elif action in ('snapshot', 'clone', 'set_name_label'):
            name = simpledialog.askstring('Name', 'Enter a name:')
            if not name or not name.strip():
                return
            args = [name.strip()]
        elif action == 'pool_migrate':
            hosts = self.records.get('host', {})
            choices = '\n'.join(v.get('name_label', '') + ' — ' + k for k, v in hosts.items())
            target = simpledialog.askstring('Destination host', 'Enter destination host reference:\n' + choices)
            if target is None:
                return
            if target not in hosts:
                messagebox.showerror('Invalid host', 'Choose a host reference from this pool.')
                return
            args = [target, {}]
        if not messagebox.askyesno('Confirm operation',
                action + ' on ' + record.get('name_label', ref) + '?\n'
                'This changes the server. Delete VM record leaves virtual disks on storage. '
                'Force off may lose guest data.'):
            return
        client = self.client
        def done(task):
            if action.startswith('set_'):
                self.status.set('Property updated by server.')
            else:
                self.tracker.add(task, action, record.get('name_label', 'VM'))
                self.status.set('Task submitted. Completion will be monitored in Tasks.')
            self.refresh()
        self.submit(lambda: client.vm_action(ref, action, *args), done, 'Submitting ' + action + '…')

    def poll_tasks(self):
        self.root.after(3000, self.poll_tasks)
        if self.closing or self.busy or self.monitor_paused or not self.client or not self.tracker.pending:
            return
        client = self.client
        tracker = self.tracker
        def work():
            try:
                return tracker.poll(client), None
            except Exception as exc:
                return {}, str(exc) if isinstance(exc, APIError) else type(exc).__name__
        def done(result):
            if self.client is not client:
                return
            records, error = result
            self.records.setdefault('task', {}).update(records)
            self.show()
            if error:
                self.monitor_paused = True
                self.status.set('Task monitoring paused: ' + error + '. Reconnect or refresh; inspect state before retrying.')
            else:
                self.status.set(tracker.summary().split('\n')[-1])
        self.submit(work, done, 'Checking submitted task status…')

    def new_vm(self):
        if self.client and not self.busy:
            NewVMDialog(self)

    def start_provisioning(self, plan):
        if not self.client or self.busy:
            return
        self.last_workflow_report = None
        self.workflow_stop = threading.Event()
        provisioner = Provisioner(self.client, self.workflow_stop, progress=self.workflow_updates.put)
        def done(report):
            self.workflow_stop = None
            self.last_workflow_report = report
            messagebox.showinfo('Virtual machine created', plan.name + ' was created. Refresh inventory to inspect its configuration.')
            self.refresh()
        self.submit(lambda: provisioner.create(plan), done, 'Creating VM; Tools can stop monitoring without cancelling server tasks…')

    def stop_workflow(self):
        if self.workflow_stop:
            self.workflow_stop.set()
            self.status.set('Stop requested. Current server work may continue; wait for the recovery report.')

    def save_workflow_report(self):
        if not self.last_workflow_report:
            messagebox.showinfo('Workflow report', 'No creation/configuration report is available yet.')
            return
        path = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON', '*.json')])
        if path:
            try:
                Path(path).write_text(json.dumps(self.last_workflow_report, indent=2) + '\n')
            except OSError:
                messagebox.showerror('Save failed', 'Cannot write the selected report file.')

    def hardware(self):
        if self.busy or not self.client:
            return
        selected = self.selected()
        if not selected or selected[0] != 'VM':
            messagebox.showinfo('Select VM', 'Select a halted VM first.')
            return
        _, ref = selected
        record = self.records['VM'][ref]
        if (record.get('power_state') != 'Halted' or record.get('is_a_template') or
                record.get('is_a_snapshot') or record.get('is_control_domain')):
            messagebox.showwarning('Hardware settings', 'Select a halted ordinary VM for CPU/memory changes.')
            return
        cpus = simpledialog.askinteger('VM vCPUs', 'Startup and maximum vCPU count:',
            initialvalue=int(record.get('VCPUs_at_startup', 1)), minvalue=1, maxvalue=1024)
        if cpus is None:
            return
        memory = simpledialog.askinteger('VM memory', 'Fixed memory (MiB); minimum and maximum will be equal:',
            initialvalue=max(128, int(record.get('memory_dynamic_max', 2048 * MiB)) // MiB),
            minvalue=128, maxvalue=1048576)
        if memory is None or not messagebox.askyesno('Confirm hardware changes',
                'Set {} vCPUs and {} MiB fixed memory? The VM must be halted. Partial changes are reported if a step fails.'.format(cpus, memory)):
            return
        client = self.client
        def done(_):
            self.last_workflow_report = {'resources': {'VM': ref}, 'cpus': cpus, 'memory_mib': memory}
            self.refresh()
        self.last_workflow_report = None
        self.submit(lambda: configure_hardware(client, ref, cpus, memory), done, 'Updating VM hardware…')

    def export(self):
        if not self.records:
            return
        path = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON', '*.json')])
        if path:
            try:
                Path(path).write_text(json.dumps(safe_record(self.records), indent=2, default=str) + '\n')
                self.status.set('Inventory exported. Review infrastructure metadata before sharing.')
            except OSError:
                messagebox.showerror('Export failed', 'Cannot write the selected file.')

    def help(self):
        help_path = Path(__file__).resolve().parent.parent / 'docs' / 'USER_GUIDE.md'
        if not help_path.exists():
            help_path = Path('/usr/share/doc/xenadmin-rocky/USER_GUIDE.md')
        window = tk.Toplevel(self.root)
        window.title('XenAdmin Rocky Help')
        text = tk.Text(window, wrap='word', width=100, height=35)
        text.pack(fill='both', expand=True)
        text.insert('end', help_path.read_text() if help_path.exists() else 'Help files missing. Reinstall the RPM.')
        text.configure(state='disabled')

    def close(self):
        if self.busy:
            messagebox.showinfo('Operation in progress', 'Wait for the current operation before closing.')
            return
        self.closing = True
        if self.client:
            client = self.client
            self.client = None
            self.jobs.submit(client.logout)
        self.jobs.shutdown(wait=False)
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description='Native Rocky Linux XAPI desktop client')
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument('--smoke-test', action='store_true', help='Create UI, then exit; requires a display')
    args = parser.parse_args()
    root = tk.Tk()
    Application(root)
    if args.smoke_test:
        root.after(500, root.destroy)
    root.mainloop()

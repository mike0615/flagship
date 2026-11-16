"""Tk desktop: all network work is serialized outside the Tk main thread."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from . import APP_NAME, __version__
from .api import Client, APIError
from .tasks import TaskTracker, request_cancellation
from .workflows import Provisioner, WorkflowError, configure_hardware, MiB, stage_label
from .wizard import NewVMDialog
from .journal import OperationJournal, JournalError, save_json_private
from .history import HistoryDialog
from .devices import DeviceManager
from .dialogs import choose_resource
from .redaction import safe_record
from .recovery import inspect_by_uuid
from .help import AboutDialog, HelpDialog, docs_directory
from .journal import OBJECT_CLASSES
from .tls import CertificateError, CertificateChanged, KnownCerts, MODE_INSECURE, MODE_PINNED
from .trust_dialog import TrustDialog, TrustedCertificatesDialog



from .center import CenterShell
from .management_ui import ManagementUI


from .format_ui import PortableUI


class Application(CenterShell, PortableUI, ManagementUI):
    def __init__(self, root, journal=None, insecure_default=False, known=None):
        self.root = root
        self.known = known if known is not None else KnownCerts()
        self.insecure_default = insecure_default
        self.journal = journal or OperationJournal()
        self.device_panels = []
        self.consoles = []
        self.external_viewers = []
        self.workflow_label = 'Workflow'
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
        root.title(APP_NAME + ' — ' + __version__)
        self.app_icon=tk.PhotoImage(file=str(Path(__file__).parent/'icons'/'flagship.png'))
        root.iconphoto(True,self.app_icon)
        width = min(1200, max(640, root.winfo_screenwidth()-40))
        height = min(760, max(480, root.winfo_screenheight()-100))
        root.geometry(f'{width}x{height}')
        self.build_shell(width)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.bind('<Destroy>', self.cancel_timers, add='+')
        root.after(100, self.poll)
        root.after(3000, self.poll_tasks)
        root.update_idletasks()

    def cancel_timers(self, event):
        if event.widget is not self.root: return
        # Destroying a Tk window removes callback commands but leaves timers in
        # the interpreter's queue unless cancelled (also affects embedded use).
        for timer in self.root.tk.call('after', 'info'):
            try: self.root.after_cancel(timer)
            except tk.TclError: pass

    def layout_toolbar(self, width):
        requested = max(button.winfo_reqwidth()+6 for button in self.toolbar_buttons)
        columns = max(1, min(len(self.toolbar_buttons), width//requested))
        if columns == self.toolbar_columns: return
        self.toolbar_columns = columns
        for index in range(len(self.toolbar_buttons)):
            self.buttonbar.columnconfigure(index, weight=1 if index < columns else 0)
        for index, button in enumerate(self.toolbar_buttons):
            button.grid(row=index//columns, column=index%columns, padx=3, pady=2, sticky='ew')

    def submit(self, work, done, label, mutation=False, completion='completed'):
        if self.busy or self.closing:
            messagebox.showinfo('Operation in progress', 'Wait for the current operation to finish.')
            return
        self.busy = True
        self.update_commands()
        self.status.set(label)
        def run():
            if not mutation:
                return work()
            endpoint = getattr(self.client, 'endpoint', None)
            self.journal.begin(label, endpoint)
            try:
                value = work()
            except Exception as exc:
                report = ({'stage': exc.stage, 'resources': exc.resources, 'tasks': exc.tasks}
                          if isinstance(exc, WorkflowError) else None)
                try:
                    self.journal.finish('interrupted_or_failed', report=report, error=exc)
                except JournalError:
                    pass  # Preserve the original result/uncertainty and recovery references.
                raise
            try:
                self.journal.finish(completion, report=value if isinstance(value, dict) else None)
            except JournalError:
                error = JournalError('Server work returned, but its final journal record could not be saved. Inspect the pool before retrying.')
                error.report = value if isinstance(value, dict) else {'returned_reference': value}
                raise error from None
            return value
        future = self.jobs.submit(run)
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
            self.status.set(latest.get('operation', 'Workflow') + ': ' + latest.get('label', latest['stage']))
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
            self.update_commands()
            try:
                value = future.result()
                done(value)
            except Exception as exc:
                # Do not display transport tracebacks, RPC arguments or session tokens.
                self.status.set('Operation failed: ' + (str(exc) if isinstance(exc, APIError) else type(exc).__name__))
                if isinstance(exc, WorkflowError):
                    self.last_workflow_report = getattr(exc, 'report', {'stage': exc.stage, 'reason': exc.reason,
                                                 'resources': exc.resources, 'tasks': exc.tasks})
                if isinstance(exc, JournalError) and hasattr(exc, 'report'):
                    self.last_workflow_report = exc.report
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
        self.connect_dialog = dialog
        fields = {}
        for row, (key, default) in enumerate([('Endpoint', 'https://'), ('Username', 'root'),
                                                ('Password', ''), ('CA PEM file (optional)', '')]):
            ttk.Label(dialog, text=key).grid(row=row, column=0, padx=8, pady=5, sticky='w')
            entry = ttk.Entry(dialog, width=48, show='*' if key == 'Password' else '')
            entry.insert(0, default)
            entry.grid(row=row, column=1, padx=8, pady=5)
            fields[key] = entry
        insecure = tk.BooleanVar(value=self.insecure_default)
        warning = tk.Label(dialog, fg='#b00020', anchor='w',
                           text='\u26a0 Certificate checks are off: anyone on the network path could read your password.')
        def toggled():
            if insecure.get():
                warning.grid(row=5, column=0, columnspan=2, padx=8, sticky='w')
            else:
                warning.grid_remove()
        check = ttk.Checkbutton(dialog, text='Ignore SSL certificate errors (insecure)', variable=insecure, command=toggled)
        check.grid(row=4, column=1, padx=8, pady=(2, 0), sticky='w')
        toggled()
        dialog.fields, dialog.insecure, dialog.insecure_check, dialog.insecure_warning = fields, insecure, check, warning
        def accept():
            endpoint, username, password, ca = [e.get() for e in fields.values()]
            dialog.destroy()
            self.start_connect(endpoint, username, password, ca or None, insecure.get())
        ttk.Button(dialog, text='Connect', command=accept).grid(row=6, column=1, pady=8)
        dialog.transient(self.root)
        dialog.grab_set()
        return dialog

    def start_connect(self, endpoint, username, password, ca=None, insecure=False, pins=None):
        """Connect in the worker; certificate questions come back to the Tk thread."""
        def work():
            client = Client(endpoint, ca, journal=self.journal, insecure=insecure, pins=pins, known=self.known)
            try:
                client.login(username, password)
            except CertificateError as exc:
                # Raised after the handshake and before the login request was written.
                try:
                    client.logout()
                except Exception:
                    pass
                return 'certificate', exc
            try:
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
            if result[0] == 'certificate':
                exc = result[1]
                choice = self.ask_trust(exc)
                if choice is None:
                    self.status.set('Connection cancelled: the certificate of ' + exc.info.key + ' was not trusted.')
                    return
                if choice == 'always':
                    try:
                        self.known.remember(exc.info)
                    except OSError:
                        messagebox.showwarning('Trusted certificates', 'Could not save the trusted certificate; it is accepted for this connection only.')
                session_pins = dict(pins or {})
                session_pins[exc.info.key] = exc.info.sha256
                self.start_connect(endpoint, username, password, ca, insecure, session_pins)
                return
            self.client, self.records, errors = result
            self.populate()
            self.root.title(APP_NAME + ' — ' + __version__ + ' — ' + self.client.endpoint)
            self.status.set('Connected to ' + self.client.endpoint + '. ' + self.warning(errors))
            self.update_tls_indicator()
        self.submit(work, done, 'Connecting…')

    def ask_trust(self, exc):
        changed = isinstance(exc, CertificateChanged)
        return TrustDialog(self.root, exc.info, changed=changed,
                           old_fingerprint=exc.pinned if changed else '').result

    def update_tls_indicator(self):
        mode = self.client.tls_mode if self.client else None
        if mode == MODE_INSECURE:
            self.tls_indicator.configure(text='\u26a0 Insecure TLS', fg='white', bg='#b00020')
        elif mode == MODE_PINNED:
            self.tls_indicator.configure(text='Pinned certificate', fg='black', bg='#ffe08a')
        else:
            self.tls_indicator.configure(text='', bg=self.root.cget('bg'), fg='black')

    @staticmethod
    def warning(errors):
        return ('Unavailable inventory: ' + ', '.join(errors)) if errors else 'Inventory up to date.'

    def disconnect(self):
        if not self.client:
            return
        client = self.client
        for viewer in self.external_viewers: viewer.close()
        self.external_viewers=[]
        for console in self.consoles: console.close()
        self.consoles = []
        def work():
            try:
                client.logout()
                return False
            except Exception:
                return True
        def done(unconfirmed):
            self.client = None
            self.update_tls_indicator()
            self.tracker = TaskTracker()
            self.records = {}
            self.last_workflow_report = None
            self.workflow_stop = None
            self.monitor_paused = False
            self.populate()
            self.show()
            for panel in self.device_panels:
                if panel.window.winfo_exists():
                    panel.window.destroy()
            self.device_panels = []
            self.root.title(APP_NAME + ' — ' + __version__)
            self.status.set('Disconnected; remote logout was not confirmed.' if unconfirmed else 'Disconnected.')
        self.submit(work, done, 'Disconnecting…')

    def refresh(self):
        if not self.client:
            return
        def done(result):
            self.records, errors = result
            self.monitor_paused = False
            self.populate()
            self.show()
            self.status.set(self.warning(errors))
            self.device_panels = [panel for panel in self.device_panels if panel.window.winfo_exists()]
            for panel in self.device_panels:
                panel.reload()
        self.submit(self.client.inventory, done, 'Refreshing inventory…')

    def selected(self):
        selection = self.tree.selection()
        return self.items.get(selection[0]) if selection else None

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
            ok, target = choose_resource(self.root, 'Destination host', hosts)
            if not ok:
                return
            args = [target, {}]
        destination = ('Destination: ' + hosts[target].get('name_label', target) + '\n') if action == 'pool_migrate' else ''
        if not messagebox.askyesno('Confirm operation',
                action + ' on ' + record.get('name_label', ref) + '?\n' + destination +
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
        self.submit(lambda: client.vm_action(ref, action, *args), done, 'Submitting ' + action + '…', mutation=True,
                    completion='completed' if action.startswith('set_') else 'submitted')

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

    def inspect_object(self):
        if self.busy or not self.client:
            messagebox.showinfo('Connect first', 'Connect to the correct pool and wait for its current operation to finish.')
            return
        ok, kind = choose_resource(self.root, 'Recorded object type', {kind: {'name_label': kind} for kind in OBJECT_CLASSES})
        if not ok:
            return
        object_uuid = simpledialog.askstring('Recorded object UUID', 'Enter the UUID from history or the server inventory.\nDo not paste an old opaque reference:')
        if object_uuid is None:
            return
        client = self.client
        def done(report):
            window = tk.Toplevel(self.root)
            window.title('Read-only object inspection — ' + client.endpoint)
            text = tk.Text(window, width=110, height=32, wrap='word')
            text.pack(fill='both', expand=True)
            text.insert('end', json.dumps(report, indent=2))
            text.configure(state='disabled')
        self.submit(lambda: inspect_by_uuid(client, kind, object_uuid), done, 'Inspecting object by UUID…')

    def cancel_task(self):
        if not self.client:
            return
        if self.busy:
            messagebox.showinfo('Operation in progress', 'For a creation/device workflow, stop monitoring first, then request cancellation of its server task.')
            return
        candidates = {ref: task for ref, task in self.records.get('task', {}).items()
                      if task.get('status') in ('pending', 'cancelling') and 'cancel' in task.get('allowed_operations', [])}
        for ref, task in self.tracker.tasks.items():
            if task.get('status') in ('pending', 'cancelling'):
                candidates.setdefault(ref, {'name_label': task['operation'] + ' — ' + task['target']})
        if self.last_workflow_report:
            for task in self.last_workflow_report.get('tasks', []):
                if task.get('status') in ('pending', 'cancelling'):
                    candidates.setdefault(task['task'], {'name_label': stage_label(task['method'])})
        ok, ref = choose_resource(self.root, 'Task to request cancellation', candidates)
        if not ok or not messagebox.askyesno('Request cancellation',
                'Request cancellation of ' + candidates[ref].get('name_label', 'this task') + '?\n'
                'The task may finish normally or take time to cancel. This does not roll back earlier workflow steps.'):
            return
        client = self.client
        def done(report):
            self.last_workflow_report = report
            if ref not in self.tracker.tasks or self.tracker.tasks[ref]['status'] in self.tracker.terminal:
                self.tracker.add(ref, 'Cancellation requested', candidates[ref].get('name_label', 'Task'))
            self.monitor_paused = False
            self.status.set('Cancellation requested; Tasks will show the actual server outcome.')
        self.submit(lambda: request_cancellation(client, ref), done, 'Requesting task cancellation…',
                    mutation=True, completion='submitted')

    def publish_workflow_progress(self, report):
        report = dict(report, operation=self.workflow_label)
        self.journal.workflow(report)
        self.workflow_updates.put(report)

    def open_console(self):
        if self.busy or not self.client: return
        selected = self.selected()
        if not selected or selected[0] != 'VM':
            messagebox.showinfo('Select VM', 'Select a running VM to open its console.')
            return
        from .console_window import ConsoleWindow
        if self.navigation.get() in ('Saved Searches','Notifications'):
            self.navigation.set('Infrastructure'); self.show()
        self.consoles = [c for c in self.consoles if c.window.winfo_exists()]
        for console in self.consoles:
            if console.vm == selected[1] and console.client is self.client:
                console.reveal()
                return
        for console in list(self.consoles):
            if console.docked: console.close()
        self.consoles.append(ConsoleWindow(self, selected[1], parent=self.console_host))
        self.tabs.select(self.frames['Console'])

    def open_external_console(self):
        if self.busy or not self.client: return
        selected=self.selected()
        if not selected or selected[0]!='VM': return
        from .external_viewer import ExternalViewer
        try:
            viewer=ExternalViewer(self.client,selected[1],self.records['VM'][selected[1]].get('name_label','Flagship console'))
        except (ValueError,RuntimeError,OSError) as exc:
            messagebox.showerror('External console',str(exc)); return
        self.external_viewers.append(viewer)
        self.poll_external_viewer(viewer)

    def poll_external_viewer(self,viewer):
        if self.closing: viewer.close(); return
        try: error=viewer.errors.get_nowait()
        except queue.Empty: error=None
        if error:
            if isinstance(error,CertificateError):
                choice=self.ask_trust(error)
                if choice is not None:
                    self.client.trust.trust(error.info,always=choice=='always')
                    messagebox.showinfo('Certificate accepted','Open Virt Viewer again to connect with the accepted certificate.')
            else: messagebox.showerror('External console','The external console stopped: '+type(error).__name__)
        if not viewer.stop.is_set(): self.root.after(250,lambda:self.poll_external_viewer(viewer))

    def manage_devices(self):
        if self.busy or not self.client:
            return
        selected = self.selected()
        if not selected or selected[0] != 'VM':
            messagebox.showinfo('Select VM', 'Select an ordinary VM first.')
            return
        record = self.records.get('VM', {}).get(selected[1], {})
        if record.get('is_a_template') or record.get('is_a_snapshot') or record.get('is_control_domain'):
            messagebox.showwarning('Select VM', 'Choose an ordinary VM for device management.')
            return
        from .device_panel import DevicePanel
        panel = DevicePanel(self, selected[1])
        self.device_panels.append(panel)

    def start_device_operation(self, action, vm, options):
        if self.busy or not self.client:
            messagebox.showinfo('Operation in progress', 'Wait for the current operation before changing devices.')
            return
        self.workflow_label = 'Device management'
        self.workflow_stop = threading.Event()
        self.last_workflow_report = None
        manager = DeviceManager(self.client, self.workflow_stop, progress=self.publish_workflow_progress)
        def done(report):
            self.workflow_stop = None
            self.last_workflow_report = report
            self.refresh()
        self.submit(lambda: manager.execute(action, vm, **options), done, 'Updating VM devices…', mutation=True)

    def new_vm(self):
        if self.client and not self.busy:
            NewVMDialog(self)

    def start_provisioning(self, plan):
        if not self.client or self.busy:
            return
        self.last_workflow_report = None
        self.workflow_stop = threading.Event()
        self.workflow_label = 'VM creation'
        provisioner = Provisioner(self.client, self.workflow_stop, progress=self.publish_workflow_progress)
        def done(report):
            self.workflow_stop = None
            self.last_workflow_report = report
            messagebox.showinfo('Virtual machine created', plan.name + ' was created. Refresh inventory to inspect its configuration.')
            self.refresh()
        self.submit(lambda: provisioner.create(plan), done, 'Creating VM; Tools can stop monitoring without cancelling server tasks…', mutation=True)

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
                save_json_private(path, self.last_workflow_report)
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
        self.submit(lambda: configure_hardware(client, ref, cpus, memory), done, 'Updating VM hardware…', mutation=True)

    def export(self):
        if not self.records:
            return
        path = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON', '*.json')])
        if path:
            try:
                save_json_private(path, safe_record(self.records))
                self.status.set('Inventory exported. Review infrastructure metadata before sharing.')
            except OSError:
                messagebox.showerror('Export failed', 'Cannot write the selected file.')

    def help(self):
        return HelpDialog(self.root, docs_directory())

    def about(self):
        return AboutDialog(self.root)

    def close(self):
        if self.busy:
            messagebox.showinfo('Operation in progress', 'Wait for the current operation before closing.')
            return
        self.closing = True
        for viewer in self.external_viewers: viewer.close()
        self.external_viewers=[]
        for console in self.consoles: console.close()
        self.consoles = []
        if self.client:
            client = self.client
            self.client = None
            self.jobs.submit(client.logout)
        self.jobs.shutdown(wait=False)
        self.journal.close()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(prog='flagship', description='Flagship — native Rocky Linux XAPI desktop client')
    parser.add_argument('--version', action='version', version='%s %s' % (APP_NAME, __version__))
    parser.add_argument('--smoke-test', action='store_true', help='Create UI, then exit; requires a display')
    parser.add_argument('--insecure', action='store_true',
                        help='Pre-tick "Ignore SSL certificate errors (insecure)" in the connect dialog')
    args = parser.parse_args()
    from .migrate import migrate_legacy
    migrate_legacy()
    root = tk.Tk()
    Application(root, insecure_default=args.insecure)
    if args.smoke_test:
        root.after(500, root.destroy)
    root.mainloop()

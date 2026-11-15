"""Creation review dialog. No network calls or mutations before explicit Create."""
import tkinter as tk
from tkinter import ttk, messagebox
from .workflows import VMPlan


class NewVMDialog:
    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title('New virtual machine')
        self.window.transient(app.root)
        self.window.grab_set()
        self.form = ttk.Frame(self.window, padding=14)
        self.form.pack(fill='both', expand=True)
        self.values = {}
        self.choices = {}
        records = app.records
        self.entry('Name', 'New virtual machine')
        templates = {ref: r for ref, r in records.get('VM', {}).items()
                     if r.get('is_a_template') and not r.get('is_a_snapshot') and not r.get('is_control_domain')}
        self.combo('Template', templates)
        self.entry('vCPUs', '2')
        self.entry('Memory (MiB)', '2048')
        self.combo('Storage repository', {ref: r for ref, r in records.get('SR', {}).items()
                   if r.get('content_type') != 'iso' and 'vdi_create' in r.get('allowed_operations', [])})
        self.entry('New disk (GiB)', '20')
        self.combo('Network', records.get('network', {}))
        isos = {ref: r for ref, r in records.get('VDI', {}).items()
                if records.get('SR', {}).get(r.get('SR'), {}).get('content_type') == 'iso'}
        self.combo('Install ISO', isos, optional=True)
        self.start = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.form, text='Start VM after successful creation', variable=self.start).grid(
            row=len(self.values), column=0, columnspan=2, sticky='w', pady=8)
        ttk.Label(self.form, wraplength=550, text='Installer templates receive a new disk. Installed-template disks are copied '
                  'to the chosen storage with their existing sizes and contents. The new VM receives one network interface. '
                  'Guest installation requires reachable installation media; use a local ISO in an airgap.').grid(
            row=len(self.values)+1, column=0, columnspan=2, sticky='w', pady=8)
        ttk.Button(self.form, text='Review', command=self.review).grid(row=len(self.values)+2, column=1, sticky='e')
        self.review_frame = ttk.Frame(self.window, padding=14)
        self.review_text = tk.Text(self.review_frame, width=74, height=23, wrap='word', state='disabled')
        self.review_text.pack(fill='both', expand=True)
        buttons = ttk.Frame(self.review_frame)
        buttons.pack(fill='x', pady=8)
        ttk.Button(buttons, text='Back', command=self.back).pack(side='left')
        ttk.Button(buttons, text='Create', command=self.create).pack(side='right')
        self.plan = None

    def entry(self, label, value):
        row = len(self.values)
        ttk.Label(self.form, text=label).grid(row=row, column=0, sticky='w', padx=4, pady=4)
        var = tk.StringVar(value=value)
        ttk.Entry(self.form, textvariable=var, width=58).grid(row=row, column=1, sticky='ew', pady=4)
        self.values[label] = var

    def combo(self, label, records, optional=False):
        row = len(self.values)
        choices = {'No ISO — use template boot configuration': ''} if optional else {}
        for number, (ref, record) in enumerate(sorted(records.items(), key=lambda x: x[1].get('name_label', '')), 1):
            name = record.get('name_label') or record.get('uuid') or 'Unnamed'
            choices['{} [{}]'.format(name, number)] = ref
        var = tk.StringVar(value=next(iter(choices), ''))
        ttk.Label(self.form, text=label).grid(row=row, column=0, sticky='w', padx=4, pady=4)
        ttk.Combobox(self.form, textvariable=var, values=list(choices), width=56, state='readonly').grid(
            row=row, column=1, sticky='ew', pady=4)
        self.values[label] = var
        self.choices[label] = choices

    def selected(self, label):
        return self.choices[label].get(self.values[label].get(), '')

    def review(self):
        try:
            self.plan = VMPlan(self.selected('Template'), self.values['Name'].get().strip(),
                self.selected('Storage repository'), self.selected('Network'),
                int(self.values['vCPUs'].get()), int(self.values['Memory (MiB)'].get()),
                int(self.values['New disk (GiB)'].get()), self.selected('Install ISO'), self.start.get())
            self.plan.validate()
        except ValueError as exc:
            self.plan = None
            messagebox.showerror('Check VM settings', str(exc), parent=self.window)
            return
        lines = [key + ': ' + value.get() for key, value in self.values.items()]
        lines += ['Start after creation: ' + ('Yes' if self.plan.start else 'No'), '',
                  'This creates server resources and may copy template disks. Existing inherited network interfaces '
                  'on the new VM will be replaced by one interface on the selected network.', '',
                  'If interrupted, partial resources or server tasks may remain. No automatic deletion is attempted. '
                  'Use Tools → Save workflow report and inspect server state before retrying.']
        self.review_text.configure(state='normal')
        self.review_text.delete('1.0', 'end')
        self.review_text.insert('end', '\n'.join(lines))
        self.review_text.configure(state='disabled')
        self.form.pack_forget()
        self.review_frame.pack(fill='both', expand=True)

    def back(self):
        self.review_frame.pack_forget()
        self.form.pack(fill='both', expand=True)

    def create(self):
        if self.app.busy:
            messagebox.showinfo('Operation in progress', 'Wait for the current operation, then choose Create again.', parent=self.window)
            return
        if self.plan:
            self.window.destroy()
            self.app.start_provisioning(self.plan)

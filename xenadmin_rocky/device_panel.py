"""Operator-facing device tables and confirmations; all mutations run through Application."""
import math
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from .workflows import GiB
from .dialogs import choose_resource


class DevicePanel:
    def __init__(self, app, vm):
        self.app, self.vm, self.client = app, vm, app.client
        self.window = tk.Toplevel(app.root)
        self.window.geometry('1100x620')
        self.caption = tk.StringVar()
        ttk.Label(self.window, textvariable=self.caption, padding=8).pack(fill='x')
        ttk.Button(self.window, text='Refresh from server', command=app.refresh).pack(anchor='e', padx=8)
        tabs = ttk.Notebook(self.window)
        tabs.pack(fill='both', expand=True)
        self.tables = {}
        for key, title, columns in [('disk', 'Disks and DVD drives', ('device', 'type', 'name', 'size', 'storage', 'connected', 'mode')),
                                    ('nic', 'Network adapters', ('device', 'network', 'mac', 'mtu', 'connected'))]:
            frame = ttk.Frame(tabs)
            tabs.add(frame, text=title)
            table = ttk.Treeview(frame, columns=columns, show='headings', selectmode='browse')
            for column in columns:
                table.heading(column, text=column.capitalize())
                table.column(column, width=100 if column != 'name' else 220)
            table.pack(fill='both', expand=True)
            self.tables[key] = table
            buttons = ttk.Frame(frame, padding=6)
            buttons.pack(fill='x')
            actions = ([('Add disk', 'add_disk'), ('Attach existing', 'attach_disk'), ('Add DVD', 'add_cd'),
                        ('Grow disk', 'grow_disk'), ('Rename disk', 'rename_disk'), ('Detach — keep data', 'detach_disk'),
                        ('Delete disk data…', 'delete_disk'), ('Change/eject ISO', 'change_iso'), ('Remove DVD', 'remove_cd'),
                        ('Connect device', 'connect_disk'), ('Disconnect device', 'disconnect_disk')]
                       if key == 'disk' else [('Add adapter', 'add_nic'), ('Change network', 'move_nic'),
                                              ('Connect', 'connect_nic'), ('Disconnect', 'disconnect_nic'), ('Remove adapter', 'remove_nic')])
            for index, (label, action) in enumerate(actions):
                ttk.Button(buttons, text=label, command=lambda a=action: self.action(a)).grid(
                    row=index//5, column=index%5, sticky='ew', padx=3, pady=3)
        self.reload()

    def reload(self):
        records = self.app.records
        machine = records.get('VM', {}).get(self.vm, {})
        name = machine.get('name_label', 'VM unavailable; refresh or close this window')
        self.window.title('Devices — ' + name)
        self.caption.set(name + ' — ' + machine.get('power_state', 'Unknown') + '\nDisk detach retains data. '
                         'Deleting data is permanent. Adapter changes can interrupt guest network access.')
        for table in self.tables.values():
            table.delete(*table.get_children())
        for ref, vbd in records.get('VBD', {}).items():
            if vbd.get('VM') != self.vm:
                continue
            disk = records.get('VDI', {}).get(vbd.get('VDI'), {})
            storage = records.get('SR', {}).get(disk.get('SR'), {})
            size = int(disk.get('virtual_size', 0)) / GiB
            self.tables['disk'].insert('', 'end', iid=ref, values=(vbd.get('userdevice', ''), vbd.get('type', ''),
                '(empty)' if vbd.get('empty') else disk.get('name_label', '(unknown disk)'),
                '{:g} GiB'.format(size) if size else '', storage.get('name_label', ''),
                'Yes' if vbd.get('currently_attached') else 'No', vbd.get('mode', '')))
        for ref, vif in records.get('VIF', {}).items():
            if vif.get('VM') != self.vm:
                continue
            network = records.get('network', {}).get(vif.get('network'), {})
            self.tables['nic'].insert('', 'end', iid=ref, values=(vif.get('device', ''), network.get('name_label', ''),
                vif.get('MAC', ''), vif.get('MTU', ''), 'Yes' if vif.get('currently_attached') else 'No'))

    def choose(self, title, records, optional=False):
        return choose_resource(self.window, title, records, optional)

    def selected(self, kind):
        selection = self.tables[kind].selection()
        if not selection:
            messagebox.showinfo('Select device', 'Select a device in this table first.', parent=self.window)
            return None
        return selection[0]

    def action(self, action):
        if self.app.busy:
            messagebox.showinfo('Operation in progress', 'Wait for the current operation.', parent=self.window)
            return
        if self.app.client is not self.client:
            messagebox.showerror('Connection changed', 'Close this window and reconnect to the intended pool.', parent=self.window)
            return
        records = self.app.records
        options = {}
        if action == 'add_disk':
            ok, sr = self.choose('Storage repository', {r: v for r, v in records.get('SR', {}).items()
                                if v.get('content_type') != 'iso' and 'vdi_create' in v.get('allowed_operations', [])})
            if not ok:
                return
            name = simpledialog.askstring('Disk name', 'Name for the new disk:', parent=self.window)
            if not name or not name.strip():
                return
            size = simpledialog.askinteger('Disk size', 'New disk size (GiB):', minvalue=1, maxvalue=2097152, parent=self.window)
            if size is None:
                return
            options = {'sr': sr, 'name': name.strip(), 'size_gib': size}
        elif action == 'attach_disk':
            ok, ref = self.choose('Existing disk', {r: v for r, v in records.get('VDI', {}).items()
                if v.get('type') == 'user' and not v.get('is_a_snapshot') and (v.get('sharable') or not v.get('VBDs'))})
            if not ok:
                return
            options = {'vdi': ref}
        elif action in ('add_cd', 'change_iso'):
            if action == 'change_iso':
                ref = self.selected('disk')
                if not ref:
                    return
                if records.get('VBD', {}).get(ref, {}).get('type') != 'CD':
                    messagebox.showinfo('Select DVD', 'Select a DVD/CD drive first.', parent=self.window)
                    return
                options['vbd'] = ref
            ok, iso = self.choose('Installation ISO', {r: v for r, v in records.get('VDI', {}).items()
                if records.get('SR', {}).get(v.get('SR'), {}).get('content_type') == 'iso'}, optional=True)
            if not ok:
                return
            options['iso'] = iso or ''
        elif action in ('add_nic', 'move_nic'):
            if action == 'move_nic':
                ref = self.selected('nic')
                if not ref:
                    return
                options['vif'] = ref
            ok, network = self.choose('Network', records.get('network', {}))
            if not ok:
                return
            options['network'] = network
            if action == 'add_nic':
                mac = simpledialog.askstring('MAC address', 'MAC (blank for automatic assignment):', parent=self.window)
                if mac is None:
                    return
                options['mac'] = mac.strip()
        elif action.endswith('_nic'):
            ref = self.selected('nic')
            if not ref:
                return
            options['vif'] = ref
        else:
            ref = self.selected('disk')
            if not ref:
                return
            vbd = records.get('VBD', {}).get(ref, {})
            if action == 'remove_cd' and vbd.get('type') != 'CD':
                messagebox.showinfo('Select DVD', 'Select a DVD/CD drive first.', parent=self.window)
                return
            if action not in ('connect_disk', 'disconnect_disk', 'remove_cd') and vbd.get('type') != 'Disk':
                messagebox.showinfo('Select disk', 'Select a data disk first.', parent=self.window)
                return
            disk = records.get('VDI', {}).get(vbd.get('VDI'), {})
            options['vbd'] = ref
            if action == 'grow_disk':
                size = simpledialog.askinteger('Grow disk', 'New total size in GiB (guest partition/filesystem expansion is separate):',
                    initialvalue=math.ceil(int(disk.get('virtual_size', 0))/GiB)+1,
                    minvalue=1, maxvalue=2097152, parent=self.window)
                if size is None:
                    return
                options['size_gib'] = size
            elif action == 'rename_disk':
                name = simpledialog.askstring('Rename disk', 'New disk name:', initialvalue=disk.get('name_label', ''), parent=self.window)
                if not name or not name.strip():
                    return
                options['name'] = name.strip()
            elif action == 'delete_disk':
                expected = disk.get('uuid')
                if not expected:
                    messagebox.showerror('Disk identity missing', 'Refresh inventory to obtain the disk UUID before permanent deletion.', parent=self.window)
                    return
                entered = simpledialog.askstring('Permanently delete disk contents',
                    'This destroys the selected disk data. Verify your independent backup.\nType this exact disk UUID:\n' + expected,
                    parent=self.window)
                if entered != expected:
                    return
                options['confirmation_uuid'] = entered
        label = action.replace('_', ' ')
        if messagebox.askyesno('Confirm device change', label.capitalize() + '?\nThis changes the selected VM/server. '
                              'Running guests may lose device/network access. Detach keeps disk data; delete disk destroys it.', parent=self.window):
            self.app.start_device_operation(action, self.vm, options)

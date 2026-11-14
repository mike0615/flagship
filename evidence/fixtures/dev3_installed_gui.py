"""Installed RPM smoke with synthetic records; no live pool and no network required."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import tkinter as tk
from xenadmin_rocky.app import Application
from xenadmin_rocky.device_panel import DevicePanel
from xenadmin_rocky.history import HistoryDialog
from xenadmin_rocky.journal import OperationJournal
from xenadmin_rocky.wizard import NewVMDialog

with tempfile.TemporaryDirectory() as temporary:
    journal = OperationJournal(Path(temporary)/'journals')
    root = tk.Tk()
    app = Application(root, journal=journal)
    app.records = {'VM': {'template': {'name_label': 'Synthetic template', 'is_a_template': True},
                         'guest': {'name_label': 'Synthetic guest', 'power_state': 'Halted'}},
        'SR': {'sr': {'name_label': 'Synthetic storage', 'allowed_operations': ['vdi_create']}},
        'network': {'network': {'name_label': 'Synthetic network'}},
        'VDI': {'data': {'name_label': 'Synthetic disk', 'virtual_size': str(20*1024**3), 'uuid': 'disk-uuid'}},
        'VBD': {'link': {'VM': 'guest', 'VDI': 'data', 'type': 'Disk', 'userdevice': '0'}},
        'VIF': {'nic': {'VM': 'guest', 'network': 'network', 'device': '0', 'MAC': '02:11:22:33:44:55'}}}
    wizard = NewVMDialog(app)
    wizard.review()
    assert wizard.plan is not None
    wizard.window.destroy()
    panel = DevicePanel(app, 'guest')
    assert '20 GiB' in panel.tables['disk'].item('link')['values']
    assert '02:11:22:33:44:55' in panel.tables['nic'].item('nic')['values']
    help_window = app.help()
    help_window.select_chapter('RECOVERY.md')
    assert 'Operation history and recovery' in help_window.text.get('1.0', 'end')
    journal.intent('Async.VM.start')
    journal.close()
    history = HistoryDialog(root, OperationJournal(journal.directory))
    assert len(history.records) == 1
    environment = dict(os.environ)
    environment.pop('PYTHONPATH', None)
    environment.pop('DISPLAY', None)
    command = subprocess.run(['xenadmin-rocky-recovery', 'history',
                              '--directory', str(journal.directory)], env=environment, capture_output=True, text=True)
    assert command.returncode == 0, command.stderr
    assert 'no_recorded_outcome' in command.stdout
    root.update()
    app.jobs.shutdown(wait=False)
    root.destroy()
print('PASS: installed New VM review, disk/NIC tables, indexed recovery help, persisted history and headless recovery CLI; synthetic records only')

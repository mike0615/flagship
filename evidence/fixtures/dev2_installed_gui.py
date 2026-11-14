"""Run against an installed RPM with an X display; synthetic records, no network."""
import tkinter as tk
from xenadmin_rocky.app import Application
from xenadmin_rocky.wizard import NewVMDialog
root = tk.Tk()
app = Application(root)
app.records = {
    'VM': {'template': {'name_label': 'Synthetic installer template', 'is_a_template': True}},
    'SR': {'sr': {'name_label': 'Synthetic storage', 'allowed_operations': ['vdi_create']}},
    'network': {'network': {'name_label': 'Synthetic network'}}}
dialog = NewVMDialog(app)
dialog.review()
assert dialog.plan is not None
assert dialog.plan.memory_mib == 2048
assert dialog.plan.network == 'network'
app.help()
texts = [child for top in root.winfo_children() if isinstance(top, tk.Toplevel)
         for child in top.winfo_children() if isinstance(child, tk.Text)]
assert any('XenAdmin Rocky user guide' in text.get('1.0', 'end') for text in texts)
root.update()
app.jobs.shutdown(wait=False)
root.destroy()
print('PASS: installed desktop, New VM review, and built-in offline help; no server connected')

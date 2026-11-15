"""Read-only selectors use display names while retaining opaque API references."""
import tkinter as tk
from tkinter import ttk, messagebox


def choose_resource(parent, title, records, optional=False):
    choices = [(None, '(empty drive / eject media)')] if optional else []
    choices += [(ref, record.get('name_label') or record.get('uuid') or 'Unnamed')
                for ref, record in sorted(records.items(), key=lambda pair: pair[1].get('name_label', ''))]
    if not choices:
        messagebox.showinfo(title, 'No suitable resources are in the current inventory. Refresh and check permissions.', parent=parent)
        return False, None
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent)
    dialog.grab_set()
    labels = ['{} [{}]'.format(label, n+1) for n, (_, label) in enumerate(choices)]
    value = tk.StringVar(value=labels[0])
    ttk.Combobox(dialog, textvariable=value, values=labels, state='readonly', width=65).pack(padx=12, pady=12)
    selected = [False, None]
    def accept():
        selected[:] = [True, choices[labels.index(value.get())][0]]
        dialog.destroy()
    ttk.Button(dialog, text='Select', command=accept).pack(pady=8)
    parent.wait_window(dialog)
    return tuple(selected)

"""Read-only recovery/history viewer. No journal entry can trigger a server call."""
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from .journal import recovery_needed, save_json_private


class HistoryDialog:
    def __init__(self, root, journal, inspect_callback=None):
        self.window = tk.Toplevel(root)
        self.window.title('Operation history and recovery review')
        self.window.geometry('1000x650')
        records, warnings = journal.history()
        review = recovery_needed(records)
        self.records = records
        self.review = review
        self.warnings = warnings
        ttk.Label(self.window, text='{} displayed events; {} review items in this window. No operation will be replayed.'.format(
            len(records), len(review)), padding=8).pack(fill='x')
        ttk.Label(self.window, text=str(journal.directory), padding=4).pack(fill='x')
        if warnings:
            ttk.Label(self.window, text='Warnings: ' + '; '.join(warnings), wraplength=950).pack(fill='x')
        ttk.Button(self.window, text='Export displayed history…', command=self.export).pack(anchor='e', padx=8, pady=4)
        if inspect_callback:
            ttk.Button(self.window, text='Inspect current object by UUID…', command=inspect_callback).pack(anchor='e', padx=8, pady=4)
        tabs = ttk.Notebook(self.window)
        tabs.pack(fill='both', expand=True)
        recovery = tk.Text(tabs, wrap='word')
        recovery.insert('end', 'Use stable UUIDs where recorded; references may expire across sessions. Inspect the pool before retrying.\n\n' +
                        json.dumps(review, indent=2))
        recovery.configure(state='disabled')
        tabs.add(recovery, text='Recovery review')
        frame = ttk.Frame(tabs)
        tabs.add(frame, text='All events')
        self.table = ttk.Treeview(frame, columns=('time', 'event', 'method', 'status'), show='headings', height=12)
        for key in ('time', 'event', 'method', 'status'):
            self.table.heading(key, text=key.capitalize())
        self.table.pack(fill='both', expand=True)
        self.details = tk.Text(frame, wrap='word', height=14, state='disabled')
        self.details.pack(fill='both', expand=True)
        for index, record in enumerate(records):
            self.table.insert('', 'end', iid=str(index), values=(record.get('time', ''), record.get('event', ''),
                              record.get('method', record.get('label', '')), record.get('status', '')))
        self.table.bind('<<TreeviewSelect>>', self.show)

    def show(self, *_):
        selection = self.table.selection()
        if not selection:
            return
        self.details.configure(state='normal')
        self.details.delete('1.0', 'end')
        self.details.insert('end', json.dumps(self.records[int(selection[0])], indent=2))
        self.details.configure(state='disabled')

    def export(self):
        path = filedialog.asksaveasfilename(parent=self.window, defaultextension='.json',
                    initialfile='operation-history.json', filetypes=[('JSON', '*.json')])
        if path:
            try:
                save_json_private(path, {'recovery_review': self.review, 'warnings': self.warnings, 'events': self.records})
            except OSError:
                messagebox.showerror('Export failed', 'Cannot save private history to this destination. Choose a regular file you own.', parent=self.window)

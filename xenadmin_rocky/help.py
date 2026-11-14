"""Offline documentation viewer with a chapter index; no browser/network required."""
import tkinter as tk
from tkinter import ttk


class HelpDialog:
    def __init__(self, root, directory):
        self.window = tk.Toplevel(root)
        self.window.title('XenAdmin Rocky Help')
        self.window.geometry('1050x700')
        self.directory = directory
        self.pages = {}
        for path in directory.glob('*.md'):
            content = path.read_text()
            title = next((line.removeprefix('# ').strip() for line in content.splitlines() if line.startswith('# ')), path.stem)
            self.pages[path.name] = (title, content)
        split = ttk.Panedwindow(self.window, orient='horizontal')
        split.pack(fill='both', expand=True)
        index = ttk.Frame(split, padding=6)
        split.add(index, weight=1)
        self.search = tk.StringVar()
        ttk.Label(index, text='Find chapter:').pack(anchor='w')
        ttk.Entry(index, textvariable=self.search).pack(fill='x', pady=4)
        self.chapters = tk.Listbox(index, width=30, exportselection=False)
        self.chapters.pack(fill='both', expand=True)
        content = ttk.Frame(split)
        split.add(content, weight=4)
        self.text = tk.Text(content, wrap='word', state='disabled')
        scroll = ttk.Scrollbar(content, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self.chapters.bind('<<ListboxSelect>>', self.show)
        self.search.trace_add('write', lambda *_: self.populate())
        self.visible = []
        self.populate()
        self.select_chapter('USER_GUIDE.md')
        if not self.pages:
            self.text.configure(state='normal')
            self.text.insert('end', 'Help files missing. Reinstall the application RPM.')
            self.text.configure(state='disabled')

    def populate(self):
        term = self.search.get().casefold()
        self.visible = [name for name, (title, _) in sorted(self.pages.items(), key=lambda pair: pair[1][0])
                        if term in (name + ' ' + title).casefold()]
        self.chapters.delete(0, 'end')
        for name in self.visible:
            self.chapters.insert('end', self.pages[name][0])
        if self.visible:
            self.chapters.selection_set(0)
            self.show()

    def select_chapter(self, filename):
        if filename in self.visible:
            self.chapters.selection_clear(0, 'end')
            self.chapters.selection_set(self.visible.index(filename))
            self.show()

    def show(self, *_):
        selection = self.chapters.curselection()
        if selection:
            content = self.pages[self.visible[selection[0]]][1]
            self.text.configure(state='normal')
            self.text.delete('1.0', 'end')
            self.text.insert('end', content)
            self.text.configure(state='disabled')
            self.text.yview_moveto(0)

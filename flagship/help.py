"""Offline documentation viewer with a chapter index; no browser/network required.

Also provides the Help > About Flagship dialog.
"""
from pathlib import Path
import tkinter as tk
from tkinter import ttk
import webbrowser

from . import about_config as about


def docs_directory():
    """Installed or source-tree help chapters."""
    here = Path(__file__).resolve().parent.parent / 'docs'
    if here.is_dir():
        return here
    for candidate in (
        Path('/usr/share/flagship/docs'),
        Path('/usr/share/doc/flagship'),
        Path('/usr/share/doc/xenadmin-rocky'),
        Path('/usr/share/xenadmin-rocky/docs'),
    ):
        if candidate.is_dir():
            return candidate
    return here


class HelpDialog:
    def __init__(self, root, directory):
        self.window = tk.Toplevel(root)
        self.window.title('Flagship Help')
        self.window.geometry('1050x700')
        self.directory = directory
        self.pages = {}
        if directory.is_dir():
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


class AboutDialog:
    """Logo, name, version, tagline, toolset, author, links, credits and license."""

    def __init__(self, root):
        self.window = tk.Toplevel(root)
        self.window.title('About %s' % about.APP_NAME)
        self.window.resizable(False, False)
        self._logo_image = None
        frame = ttk.Frame(self.window, padding=28)
        frame.pack(fill='both', expand=True)

        logo_path = Path(about.LOGO_FILE)
        if logo_path.is_file():
            try:
                self._logo_image = tk.PhotoImage(file=str(logo_path))
                ttk.Label(frame, image=self._logo_image).pack(pady=(0, 8))
            except tk.TclError:
                self._logo_image = None

        def line(text, *, style=None, pady=1, font=None, foreground=None):
            kwargs = {}
            if font:
                kwargs['font'] = font
            if foreground:
                kwargs['foreground'] = foreground
            widget = ttk.Label(frame, text=text, wraplength=520, justify='center', **kwargs)
            if style:
                widget.configure(style=style)
            widget.pack(pady=pady)
            return widget

        line(about.APP_NAME, font=('TkDefaultFont', 18, 'bold'), pady=(4, 2))
        version = line('Version %s' % about.VERSION, foreground='#555555')
        line(about.TAGLINE, pady=(6, 2))
        line(about.TOOLSET, pady=(0, 6))
        line('Author: %s' % about.AUTHOR)
        line(about.COPYRIGHT, pady=(0, 8))

        links = ttk.Frame(frame)
        links.pack(pady=4)
        for index, (label, url) in enumerate(about.LINKS):
            if index:
                ttk.Label(links, text='  ·  ').pack(side='left')
            link = ttk.Label(links, text=label, foreground='#0b57d0', cursor='hand2')
            link.pack(side='left')
            link.bind('<Button-1>', lambda _event, target=url: webbrowser.open(target))

        line(about.CREDITS, pady=(12, 8), foreground='#333333')
        line(about.LICENSE_NOTICE, pady=(0, 12), foreground='#555555')

        ttk.Button(frame, text='Close', command=self.window.destroy).pack()
        self.window.transient(root)
        self.window.grab_set()
        self.window.protocol('WM_DELETE_WINDOW', self.window.destroy)
        self.window.update_idletasks()
        # Center over the parent when possible.
        try:
            px, py = root.winfo_rootx(), root.winfo_rooty()
            pw, ph = root.winfo_width(), root.winfo_height()
            w, h = self.window.winfo_width(), self.window.winfo_height()
            self.window.geometry('+%d+%d' % (px + max(0, (pw - w) // 2), py + max(0, (ph - h) // 2)))
        except tk.TclError:
            pass
        # Keep a reference so Tk does not drop the PhotoImage; silence unused.
        self._version_label = version

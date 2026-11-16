"""Certificate trust dialogs (modelled on Helm's mstsc-style warning).

TrustDialog result: 'once' (Connect once), 'always' (Always trust this
certificate) or None (Cancel, the default button).
"""
import tkinter as tk
from tkinter import ttk, messagebox

from .tls import display_fingerprint

RED = '#b00020'


class TrustDialog:
    def __init__(self, root, info, changed=False, old_fingerprint='', wait=True):
        self.info = info
        self.result = None
        self.window = window = tk.Toplevel(root)
        window.title('Flagship — Certificate ' + ('changed' if changed else 'not trusted'))
        window.resizable(False, False)
        body = ttk.Frame(window, padding=12)
        body.pack(fill='both', expand=True)
        wrap = 620
        if changed:
            tk.Label(body, text='WARNING: THE CERTIFICATE OF THIS HOST HAS CHANGED',
                     fg='white', bg=RED, font=('TkDefaultFont', 12, 'bold'), padx=8, pady=6,
                     anchor='w').pack(fill='x')
            tk.Label(body, wraplength=wrap, justify='left', fg=RED, anchor='w', pady=6, text=(
                '%s is presenting a different certificate from the one you chose to trust. '
                'This happens after a host is reinstalled or its certificate is regenerated, but it '
                'can also mean someone is intercepting the connection. Do not continue unless you '
                'know why it changed. Nothing has been sent to the host.' % info.key)).pack(fill='x')
        else:
            ttk.Label(body, wraplength=wrap, justify='left', font=('TkDefaultFont', 10, 'bold'), text=(
                'The identity of %s cannot be verified. Do you want to connect anyway?' % info.key)).pack(fill='x')
            ttk.Label(body, wraplength=wrap, justify='left', text=(
                'The host could not be authenticated because of problems with its security '
                'certificate. XCP-ng hosts use a self-signed certificate unless one was installed. '
                'Check the fingerprint against the host (see Help) before trusting it. '
                'Nothing has been sent to the host yet.')).pack(fill='x', pady=(4, 8))

        details = ttk.LabelFrame(body, text='Certificate', padding=8)
        details.pack(fill='x')
        rows = [('Host', info.key), ('Subject', info.subject or '(unavailable)'),
                ('Issuer', info.issuer or '(unavailable)'),
                ('Names', ', '.join(info.names) or '(none)'),
                ('Valid from', info.not_before or '(unavailable)'),
                ('Valid until', info.not_after or '(unavailable)'),
                ('SHA-256', display_fingerprint(info.sha256))]
        if changed and old_fingerprint:
            rows.append(('Previously trusted', display_fingerprint(old_fingerprint)))
        self.fields = {}
        for row, (label, value) in enumerate(rows):
            ttk.Label(details, text=label + ':').grid(row=row, column=0, sticky='nw', padx=(0, 8), pady=1)
            mono = label in ('SHA-256', 'Previously trusted')
            widget = tk.Label(details, text=value, justify='left', anchor='w', wraplength=wrap - 140,
                              font=('TkFixedFont', 9) if mono else None,
                              fg=RED if label == 'Previously trusted' else None)
            widget.grid(row=row, column=1, sticky='w', pady=1)
            self.fields[label] = widget

        problems = info.problems()
        if changed:
            problems.insert(0, 'The certificate does not match the one you trusted before.')
        if info.verify_error:
            problems.append('OpenSSL: ' + info.verify_error)
        errors = ttk.LabelFrame(body, text='Certificate errors', padding=8)
        errors.pack(fill='x', pady=8)
        for problem in problems:
            ttk.Label(errors, text='\u26a0  ' + problem, wraplength=wrap - 20, justify='left').pack(anchor='w')

        ttk.Label(body, text='Do you want to connect despite these certificate errors?').pack(anchor='w')
        buttons = ttk.Frame(body)
        buttons.pack(fill='x', pady=(10, 0))
        self.cancel_button = ttk.Button(buttons, text='Cancel', command=self.cancel, default='active')
        self.cancel_button.pack(side='right')
        self.always_button = ttk.Button(buttons, text='Always trust this certificate',
                                        command=lambda: self.choose('always'))
        self.always_button.pack(side='right', padx=6)
        self.once_button = ttk.Button(buttons, text='Connect once', command=lambda: self.choose('once'))
        self.once_button.pack(side='right')
        window.bind('<Escape>', lambda _e: self.cancel())
        window.protocol('WM_DELETE_WINDOW', self.cancel)
        window.transient(root)
        self.cancel_button.focus_set()
        if wait:
            window.wait_visibility()
            window.grab_set()
            window.wait_window()

    def choose(self, result):
        self.result = result
        self.window.destroy()

    def cancel(self):
        self.result = None
        self.window.destroy()


class TrustedCertificatesDialog:
    """Tools ▸ Trusted certificates…: list and remove "Always trust" pins."""

    def __init__(self, root, known):
        self.known = known
        self.window = tk.Toplevel(root)
        self.window.title('Flagship — Trusted certificates')
        frame = ttk.Frame(self.window, padding=10)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, wraplength=640, justify='left', text=(
            'Host certificates you chose to always trust. Stored in %s (readable only by you). '
            'Removing one makes Flagship ask again on the next connection.' % known.path)).pack(fill='x')
        self.tree = ttk.Treeview(frame, columns=('sha256', 'until', 'trusted'), height=8)
        for column, title, width in (('#0', 'Host', 170), ('sha256', 'SHA-256 (start)', 220),
                                     ('until', 'Valid until', 150), ('trusted', 'Trusted on', 150)):
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width)
        self.tree.pack(fill='both', expand=True, pady=8)
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x')
        ttk.Button(buttons, text='Close', command=self.window.destroy).pack(side='right')
        ttk.Button(buttons, text='Remove', command=self.remove).pack(side='right', padx=6)
        self.window.transient(root)
        self.reload()

    def reload(self):
        self.tree.delete(*self.tree.get_children())
        for key, entry in sorted(self.known.load().items()):
            self.tree.insert('', 'end', iid=key, text=key, values=(
                entry['sha256'][:47].upper() + '…', entry.get('not_after', ''), entry.get('trusted', '')))

    def remove(self):
        selected = self.tree.selection()
        if selected and messagebox.askyesno('Remove trusted certificate',
                                            'Stop trusting the saved certificate for ' + selected[0] + '?',
                                            parent=self.window):
            try:
                self.known.forget(selected[0])
            except OSError:
                messagebox.showerror('Remove failed', 'Cannot update ' + str(self.known.path), parent=self.window)
            self.reload()

"""Tk console viewer. Network threads never call Tk; input requires opt-in."""
import queue
import threading
import tkinter as tk
from tkinter import ttk
from .console import open_console
from .rfb import RFB
from .tls import CertificateError, MODE_INSECURE


class ConsoleWindow:
    def __init__(self, app, vm, connector=open_console, parent=None):
        self.app, self.client, self.vm = app, app.client, vm
        self.dock_parent=parent
        self.docked=parent is not None
        if self.docked:
            self.window=tk.Frame(parent,background="#101b2a")
            self.window.pack(fill='both',expand=True)
        else:
            self.window=tk.Toplevel(app.root)
            self.window.title('VM console — ' + app.records.get('VM', {}).get(vm, {}).get('name_label', 'VM'))
            self.window.geometry('1000x720')
        self.stop = threading.Event()
        self.frames = queue.Queue(maxsize=4)
        self.inputs = queue.Queue(maxsize=256)
        self.tunnel = self.rfb = self.image = None
        self.lock = threading.Lock()
        self.pressed = set()
        self.buttons = 0
        self.position = (0, 0)
        self.control = tk.BooleanVar(value=False)
        self.fit=tk.BooleanVar(value=True); self.scale_factor=1; self.display_image=None; self.render_timer=None
        toolbar = ttk.Frame(self.window)
        toolbar.pack(fill='x')
        ttk.Checkbutton(toolbar, text='Enable keyboard and mouse', variable=self.control,
                        command=self.release).pack(side='left')
        ttk.Checkbutton(toolbar,text='Fit',variable=self.fit,command=self.request_render).pack(side='left',padx=5)
        ttk.Button(toolbar, text='Send Ctrl+Alt+Delete', command=self.cad).pack(side='left')
        self.dock_button=ttk.Button(toolbar,text='Undock' if self.docked else 'Dock',command=self.toggle_dock)
        if parent is not None: self.dock_button.pack(side='right',padx=4)
        ttk.Button(toolbar,text='Fullscreen',command=self.fullscreen).pack(side='right',padx=4)
        ttk.Button(toolbar, text='Close console', command=self.close).pack(side='right')
        insecure = getattr(self.client, 'tls_mode', None) == MODE_INSECURE
        self.status = tk.StringVar(value='Connecting with certificate checks OFF (insecure TLS)…' if insecure
                                   else 'Connecting through verified TLS…')
        ttk.Label(self.window, textvariable=self.status).pack(fill='x')
        frame = ttk.Frame(self.window)
        frame.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(frame, background='black', takefocus=True)
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=self.canvas.xview)
        vertical = ttk.Scrollbar(frame, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=horizontal.set, yscrollcommand=vertical.set)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.item = self.canvas.create_image(0, 0, anchor='nw')
        self.canvas.bind('<Configure>',lambda e:self.request_render())
        self.canvas.bind('<KeyPress>', lambda event: self.key(event, True))
        self.canvas.bind('<KeyRelease>', lambda event: self.key(event, False))
        self.canvas.bind('<FocusOut>', lambda event: self.release())
        self.canvas.bind('<Motion>', self.pointer)
        for button in range(1, 6):
            self.canvas.bind('<ButtonPress-%d>' % button, lambda event, b=button: self.pointer(event, b, True))
            self.canvas.bind('<ButtonRelease-%d>' % button, lambda event, b=button: self.pointer(event, b, False))
        if not self.docked: self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.connector = connector
        self.worker = threading.Thread(target=self.receive, args=(connector,), daemon=True)
        self.window.update_idletasks()
        self.worker.start()
        self.poll_timer = self.window.after(25, self.poll)

    def toggle_dock(self):
        if self.dock_parent is None: return
        self.release(); self.control.set(False)
        if self.docked:
            # wm manage/forget changes the same frame into a toplevel and back;
            # the socket, framebuffer, widgets and input queues are preserved.
            self.window.tk.call('wm','manage',self.window)
            self.window.tk.call('wm','title',self.window,'Flagship console')
            self.window.tk.call('wm','geometry',self.window,'1000x720')
            self.window.tk.call('wm','protocol',self.window,'WM_DELETE_WINDOW',self.window.register(self.toggle_dock))
            self.docked=False; self.dock_button.configure(text='Dock')
        else:
            if hasattr(self.app,'select_resource'): self.app.select_resource('VM',self.vm)
            self.window.tk.call('wm','attributes',self.window,'-fullscreen',False)
            self.window.tk.call('wm','forget',self.window)
            self.window.pack(fill='both',expand=True)
            self.docked=True; self.dock_button.configure(text='Undock')
            if hasattr(self.app,'tabs'): self.app.tabs.select(self.app.frames['Console'])

    def fullscreen(self):
        if self.docked: self.toggle_dock()
        top=self.window
        current=bool(int(top.tk.call('wm','attributes',top,'-fullscreen')))
        top.tk.call('wm','attributes',top,'-fullscreen',not current)
        top.bind('<Escape>',lambda e:top.tk.call('wm','attributes',top,'-fullscreen',False))

    def reveal(self):
        if self.docked:
            self.app.tabs.select(self.app.frames['Console'])
        else: self.window.tk.call('wm','deiconify',self.window); self.window.lift()

    def emit(self, event):
        while not self.stop.is_set():
            try:
                self.frames.put(event, timeout=.1)
                return
            except queue.Full:
                continue

    def receive(self, connector):
        try:
            tunnel = connector(self.client, self.vm)
            with self.lock:
                if self.stop.is_set():
                    tunnel.close()
                    return
                self.tunnel = tunnel
            rfb = RFB(tunnel)
            width, height = rfb.handshake()
            # A static desktop can remain silent indefinitely; explicit close
            # interrupts the socket instead of expiring an otherwise healthy view.
            tunnel.connection.settimeout(None)
            if self.stop.is_set(): return
            self.rfb = rfb
            self.emit(('resize', width, height))
            self.emit(('connected',))
            threading.Thread(target=self.send, daemon=True).start()
            while not self.stop.is_set():
                for event in rfb.events(): self.emit(event)
        except CertificateError as exc:
            # A pool member's certificate is not trusted (or changed); ask on the Tk thread.
            self.emit(('certificate', exc))
        except Exception as exc:
            # Never show server response bodies, cookie contents or URLs.
            self.emit(('error', type(exc).__name__))
        finally:
            self.stop.set()
            with self.lock:
                if self.tunnel:
                    self.tunnel.close()
                    self.tunnel = None

    def send(self):
        while not self.stop.is_set():
            try: method, args = self.inputs.get(timeout=.1)
            except queue.Empty: continue
            try:
                getattr(self.rfb, method)(*args)
            except Exception:
                self.emit(('error', 'Input connection closed'))
                self.stop.set()
                with self.lock:
                    if self.tunnel: self.tunnel.close(); self.tunnel = None
                return

    def enqueue(self, method, *args):
        if self.stop.is_set() or not self.rfb: return
        try: self.inputs.put_nowait((method, args))
        except queue.Full:
            self.status.set('Input queue overflow; console closed. Reopen to continue.')
            self.stop.set()  # Release must not recursively enqueue into a full queue.
            self.close()

    def active(self):
        return (self.control.get() and not self.stop.is_set() and
                self.app.client is self.client and self.rfb is not None)

    def key(self, event, down):
        if not self.active(): return 'break'
        keysym = event.keysym_num
        if keysym == 0 and event.char:
            code = ord(event.char[0])
            keysym = code if code < 256 else 0x01000000 | code
        if not keysym: return 'break'
        if down: self.pressed.add(keysym)
        else: self.pressed.discard(keysym)
        self.enqueue('key', keysym, down)
        return 'break'

    def pointer(self, event, button=None, down=None):
        if not self.active(): return 'break'
        self.canvas.focus_set()
        self.position = (int(self.canvas.canvasx(event.x))*self.scale_factor, int(self.canvas.canvasy(event.y))*self.scale_factor)
        if self.image:
            self.position=(min(max(0,self.position[0]),self.image.width()-1),min(max(0,self.position[1]),self.image.height()-1))
        if button:
            mask = 1 << (button - 1)
            self.buttons = self.buttons | mask if down else self.buttons & ~mask
        self.enqueue('pointer', *self.position, self.buttons)
        return 'break'

    def release(self):
        for keysym in self.pressed: self.enqueue('key', keysym, False)
        self.pressed.clear()
        if self.buttons: self.enqueue('pointer', *self.position, 0)
        self.buttons = 0

    def cad(self):
        if not self.active(): return
        additions = [key for key in (0xffe3, 0xffe9, 0xffff) if key not in self.pressed]
        for keysym in additions: self.enqueue('key', keysym, True)
        for keysym in reversed(additions): self.enqueue('key', keysym, False)

    def request_render(self):
        if self.render_timer is None and self.window.winfo_exists(): self.render_timer=self.window.after_idle(self.render_display)

    def render_display(self):
        self.render_timer=None
        if self.image is None or not self.window.winfo_exists(): return
        import math
        self.scale_factor=max(1,math.ceil(max(self.image.width()/max(1,self.canvas.winfo_width()),self.image.height()/max(1,self.canvas.winfo_height())))) if self.fit.get() else 1
        self.display_image=self.image.subsample(self.scale_factor,self.scale_factor) if self.scale_factor>1 else self.image
        self.canvas.itemconfigure(self.item,image=self.display_image)
        self.canvas.configure(scrollregion=(0,0,self.display_image.width(),self.display_image.height()))

    def draw(self, event):
        kind, *args = event
        if kind == 'resize':
            width, height = args
            self.image = tk.PhotoImage(master=self.window, width=width, height=height)
            self.canvas.itemconfigure(self.item, image=self.image)
            self.canvas.configure(scrollregion=(0, 0, width, height))
        elif kind == 'pixels':
            x, y, width, height, rgb = args
            tile = tk.PhotoImage(master=self.window, data=('P6\n%d %d\n255\n' % (width, height)).encode() + rgb, format='PPM')
            self.image.tk.call(str(self.image), 'copy', str(tile), '-to', x, y)
        elif kind == 'copy':
            x, y, width, height, source_x, source_y = args
            tile = tk.PhotoImage(master=self.window, width=width, height=height)
            tile.tk.call(str(tile), 'copy', str(self.image), '-from', source_x, source_y, source_x+width, source_y+height)
            self.image.tk.call(str(self.image), 'copy', str(tile), '-to', x, y)
        elif kind == 'connected':
            self.status.set('Connected. Viewing only; enable keyboard and mouse to control the guest.')
        elif kind == 'certificate':
            self.trust_and_retry(args[0])
        elif kind == 'error':
            self.control.set(False)
            self.status.set('Console stopped: ' + args[0] + '. Close and reopen to reconnect.')

        if kind in ('resize','pixels','copy'): self.request_render()

    def trust_and_retry(self, exc):
        choice = self.app.ask_trust(exc)
        if choice is None or not self.window.winfo_exists() or self.app.client is not self.client:
            self.status.set('Console not opened: the certificate of ' + exc.info.key + ' was not trusted.')
            return
        try:
            self.client.trust.trust(exc.info, always=(choice == 'always'))
        except OSError:
            self.client.trust.trust(exc.info)
            self.status.set('Could not save the trusted certificate; accepted for this session only.')
        self.worker.join(timeout=2)
        self.stop = threading.Event()
        self.status.set('Connecting with the certificate you accepted…')
        self.worker = threading.Thread(target=self.receive, args=(self.connector,), daemon=True)
        self.worker.start()

    def poll(self):
        self.poll_timer = None
        if not self.window.winfo_exists(): return
        if self.app.client is not self.client:
            self.close()
            return
        for _ in range(8):
            try: self.draw(self.frames.get_nowait())
            except queue.Empty: break
        self.poll_timer = self.window.after(25, self.poll)

    def close(self):
        self.release()
        self.stop.set()
        if self.render_timer is not None:
            try: self.window.after_cancel(self.render_timer)
            except tk.TclError: pass
            self.render_timer=None
        if self.poll_timer is not None:
            try: self.window.after_cancel(self.poll_timer)
            except tk.TclError: pass
            self.poll_timer = None
        with self.lock:
            if self.tunnel: self.tunnel.close(); self.tunnel = None
        if self.window.winfo_exists(): self.window.destroy()

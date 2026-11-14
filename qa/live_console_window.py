#!/usr/bin/env python3
"""Exercise the actual Tk console window against one UUID-recorded QA guest."""
import argparse
import getpass
import json
from pathlib import Path
import tkinter as tk
from xenadmin_rocky.api import Client
from xenadmin_rocky.app import Application
from xenadmin_rocky.console_window import ConsoleWindow
from xenadmin_rocky.journal import OperationJournal


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('endpoint','username','ca-file','state-file'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    path=Path(args.state_file)
    state=json.loads(path.read_text())
    if state['endpoint']!=args.endpoint or not state['prefix'].startswith('xenadmin-qa-'):
        parser.error('Expected a QA manifest for this endpoint')
    guests=[item for item in state['created'] if item['class']=='VM']
    if len(guests)!=1:parser.error('Expected one recorded QA guest')
    client=Client(args.endpoint,args.ca_file)
    root=None;app=None;viewer=None
    journal=OperationJournal(path.parent/'gui-journals')
    passed=[]
    try:
        password=getpass.getpass('XAPI QA password: ')
        client.login(args.username,password)
        password=None
        vm=client.call('VM.get_by_uuid',guests[0]['uuid'])
        record=client.call('VM.get_record',vm)
        if not record['name_label'].startswith(state['prefix']):raise ValueError('Guest is outside QA namespace')
        root=tk.Tk()
        app=Application(root,journal=journal)
        app.client=client
        app.records={'VM':{vm:record}}
        app.populate()
        viewer=ConsoleWindow(app,vm)
        app.consoles.append(viewer)
        def check():
            try:
                if viewer.stop.is_set() or viewer.image is None:
                    raise ValueError('Live console did not remain connected with a framebuffer')
                width,height=viewer.image.width(),viewer.image.height()
                colours={viewer.image.get(x,y) for x in range(0,width,max(1,width//16))
                         for y in range(0,height,max(1,height//16))}
                if len(colours)<2:raise ValueError('Console framebuffer did not contain visible guest content')
                if viewer.control.get():raise ValueError('Console unexpectedly enabled input by default')
                print('PASS: actual Tk console rendered live guest pixels through verified TLS; input default remained off.',flush=True)
                passed.append(True)
            except Exception as exc:
                print('Live console window check stopped:',type(exc).__name__,flush=True)
            finally:root.quit()
        root.after(12000,check)
        root.mainloop()
        return 0 if passed else 1
    finally:
        if viewer:viewer.close()
        if app:app.client=None;app.jobs.shutdown(wait=True)
        if root:root.destroy()
        client.logout()
        journal.close()


if __name__=='__main__':raise SystemExit(main())

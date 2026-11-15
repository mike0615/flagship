import os
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from flagship.app import Application
from flagship.journal import OperationJournal


@unittest.skipUnless(os.environ.get('DISPLAY'), 'requires X display')
class WindowLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.root=tk.Tk()
        self.journal=OperationJournal(Path(self.temporary.name)/'journals')
        self.app=Application(self.root, journal=self.journal)
        self.root.update()

    def tearDown(self):
        self.app.jobs.shutdown(wait=True)
        self.journal.close()
        self.root.destroy()
        self.temporary.cleanup()

    def test_initial_window_fits_the_display(self):
        self.assertLessEqual(self.root.winfo_width(), self.root.winfo_screenwidth())
        self.assertLessEqual(self.root.winfo_height(), self.root.winfo_screenheight())

    def test_every_toolbar_action_stays_visible_after_narrowing(self):
        self.root.geometry('800x600')
        self.root.update()
        left=self.root.winfo_rootx();right=left+self.root.winfo_width()
        rectangles=[]
        for button in self.app.toolbar_buttons:
            self.assertTrue(button.winfo_ismapped())
            x,y=button.winfo_rootx(),button.winfo_rooty()
            w,h=button.winfo_width(),button.winfo_height()
            self.assertGreater(w,10)
            self.assertGreaterEqual(x,left)
            self.assertLessEqual(x+w,right)
            for px,py,pw,ph in rectangles:
                self.assertFalse(x<px+pw and px<x+w and y<py+ph and py<y+h)
            rectangles.append((x,y,w,h))

    def test_vm_actions_and_status_remain_visible_at_default_guest_resolution(self):
        self.root.geometry('984x668')
        self.root.update()
        bottom=self.root.winfo_rooty()+self.root.winfo_height()
        widgets=[]
        def collect(parent):
            for widget in parent.winfo_children():
                widgets.append(widget);collect(widget)
        collect(self.root)
        actions=[widget for widget in widgets if widget.winfo_class()=='TButton'
                 and widget.cget('text') in ('Start','Force off','Delete VM record')]
        self.assertEqual(len(actions),3)
        for widget in actions:
            self.assertTrue(widget.winfo_ismapped())
            self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(),bottom)



if __name__ == '__main__': unittest.main()

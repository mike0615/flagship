"""Selection, relationship and command regression checks for the native Center UI."""
import os
import tempfile
from pathlib import Path
import tkinter as tk
import unittest
from unittest.mock import Mock, patch
from flagship.app import Application
from flagship.journal import OperationJournal
from flagship.inventory import related, tabs_for


class RelationshipTests(unittest.TestCase):
    def test_host_storage_follows_pbd_and_networking_follows_pif(self):
        records={'SR':{'a':{},'b':{}},'PBD':{'p':{'host':'h','SR':'a'}},
                 'network':{'n':{},'m':{}},'PIF':{'i':{'host':'h','network':'n'}}}
        self.assertEqual(set(related(records,'host','h','Storage')[1]),{'a'})
        self.assertEqual(set(related(records,'host','h','Networking')[1]),{'n'})
        self.assertEqual(related(records,'host','other','Storage')[1],{})

    def test_vm_tabs_distinguish_templates_and_storage(self):
        self.assertIn('Snapshots',tabs_for('VM',{}))
        self.assertNotIn('Snapshots',tabs_for('VM',{'is_a_template':True}))
        self.assertNotIn('Memory',tabs_for('SR',{}))


@unittest.skipUnless(os.environ.get('DISPLAY'),'requires X display')
class CenterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=tk.Tk(); self.root.withdraw()
        self.journal=OperationJournal(Path(self.tmp.name)/'journal')
        self.app=Application(self.root,journal=self.journal); self.app.client=Mock()
        self.app.records={'pool':{'p':{'name_label':'Test Pool'}},'host':{'h':{'name_label':'Test Host'}},
          'VM':{'v':{'name_label':'Guest','power_state':'Running','resident_on':'h','allowed_operations':['clean_shutdown']},
                's':{'name_label':'Snapshot','is_a_snapshot':True,'snapshot_of':'v','allowed_operations':['revert','destroy']}}}
        self.app.populate()

    def tearDown(self):
        self.app.jobs.shutdown(wait=True); self.journal.close(); self.root.destroy(); self.tmp.cleanup()

    def select(self,key):
        iid=next(i for i,k in self.app.items.items() if k==key)
        self.app.tree.selection_set(iid); self.app.show(); return iid

    def visible_tabs(self):
        return {self.app.tabs.tab(t,'text') for t in self.app.tabs.tabs() if self.app.tabs.tab(t,'state')!='hidden'}

    def test_infrastructure_nests_running_guest_under_resident_host(self):
        guest=self.select(('VM','v')); host=next(i for i,k in self.app.items.items() if k==('host','h'))
        self.assertEqual(self.app.tree.parent(guest),host)
        self.assertEqual(str(self.app.action_buttons['start'].cget('state')),'disabled')
        self.assertEqual(str(self.app.action_buttons['clean_shutdown'].cget('state')),'normal')
        self.app.client.vm_action.assert_not_called()

    def test_host_and_vm_tabs_are_selection_specific(self):
        self.select(('host','h')); self.assertIn('NICs',self.visible_tabs()); self.assertNotIn('Snapshots',self.visible_tabs())
        self.select(('VM','v')); self.assertIn('Snapshots',self.visible_tabs()); self.assertNotIn('NICs',self.visible_tabs())

    def test_snapshot_action_selects_the_table_snapshot(self):
        self.select(('VM','v'))
        table=self.app.tables['Snapshots']; table.selection_set(table.get_children()[0])
        self.app.action=Mock(); self.app.table_action('Snapshots','revert')
        self.assertEqual(self.app.selected(),('VM','s')); self.app.action.assert_called_once_with('revert')

    def test_empty_snapshot_selection_cannot_revert_parent(self):
        self.select(('VM','v')); self.app.action=Mock(); self.app.table_action('Snapshots','revert')
        self.app.action.assert_not_called()

    def test_snapshot_visibility_does_not_require_template_visibility(self):
        self.app.records['VM']['s']['is_a_template'] = True
        self.app.show_templates.set(False); self.app.show_snapshots.set(True); self.app.populate()
        self.assertIn(('VM','s'), self.app.items.values())

    def test_halted_guest_uses_affinity_when_resident_on_is_null(self):
        self.app.records['VM']['v'].update(resident_on='OpaqueRef:NULL',affinity='h',power_state='Halted')
        self.app.populate(); guest=self.select(('VM','v'))
        self.assertEqual(self.app.items[self.app.tree.parent(guest)],('host','h'))

    def test_navigation_and_search_are_read_only(self):
        self.app.open_notifications(); self.assertEqual(self.visible_tabs(),{'Alerts','Tasks'})
        self.app.navigation.set('Saved Searches'); self.app.show(); self.assertEqual(self.visible_tabs(),{'Search'})
        self.app.inventory_filter.set('Running'); self.assertEqual(len(self.app.tables['Search'].get_children()),1)
        self.app.client.call.assert_not_called()

    @patch('flagship.management_ui.messagebox.askyesno',return_value=False)
    def test_declined_host_action_does_not_submit(self,confirm):
        self.select(('host','h')); self.app.submit=Mock(); self.app.host_action('reboot')
        confirm.assert_called_once(); self.app.submit.assert_not_called()

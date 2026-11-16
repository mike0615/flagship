import unittest
from unittest.mock import Mock
from flagship.management import StoragePlan, NetworkPlan, host_operation, edit_identity
from flagship.workflows import WorkflowError
from flagship.performance import parse_rrd


class ManagementTests(unittest.TestCase):
    def test_invalid_storage_makes_no_rpc(self):
        c=Mock()
        for server,path in (('','/share'),('nfs/share','/share'),('server','relative')):
            with self.assertRaises(ValueError): StoragePlan('h','name','',server,path).create(c)
        c.call.assert_not_called()

    def test_iso_storage_uses_upstream_nfs_iso_config(self):
        c=Mock(); c.call.side_effect=['sr',{'PBDs':['pbd']},True]
        result=StoragePlan('h','ISO','','nfs','/share',True).create(c)
        c.call.assert_any_call('SR.create','h',{'location':'nfs:/share','type':'nfs_iso'},0,'ISO','','iso','iso',True,{})
        self.assertEqual(result['resources'],{'SR':'sr'})

    def test_attachment_failure_preserves_created_storage(self):
        c=Mock(); c.call.side_effect=['sr',{'PBDs':['pbd']},False]
        with self.assertRaises(WorkflowError) as caught: StoragePlan('h','Data','','nfs','/share').create(c)
        self.assertEqual(caught.exception.resources,{'SR':'sr'})
        self.assertNotIn('SR.destroy',[call.args[0] for call in c.call.call_args_list])

    def test_invalid_mtu_does_not_create_network(self):
        c=Mock()
        with self.assertRaises(ValueError): NetworkPlan('Private',mtu=0).create(c)
        c.call.assert_not_called()

    def test_power_and_maintenance_refuse_active_guests(self):
        for action in ('disable','reboot','shutdown'):
            c=Mock(); c.call.side_effect=[{'enabled':False,'resident_VMs':['v'],'allowed_operations':['reboot','shutdown']},{'power_state':'Running'}]
            with self.assertRaises(ValueError): host_operation(c,'h',action)
            self.assertFalse(any(x.args[0].startswith('Async.') for x in c.call.call_args_list))

    def test_reboot_refuses_enabled_host(self):
        c=Mock(); c.call.return_value={'enabled':True,'allowed_operations':['reboot']}
        with self.assertRaises(ValueError): host_operation(c,'h','reboot')
        c.call.assert_called_once_with('host.get_record','h')

    def test_partial_property_failure_reports_the_object(self):
        c=Mock(); c.call.side_effect=[{},'',OSError()]
        with self.assertRaises(WorkflowError) as caught: edit_identity(c,'VM','v','Name','Desc')
        self.assertEqual(caught.exception.resources,{'VM':'v'})
        self.assertEqual(c.call.call_count,3)

    def test_rrd_filters_other_objects_and_nonfinite_samples(self):
        xml=b'<xport><meta><legend><entry>AVERAGE:vm:one:cpu0</entry><entry>AVERAGE:vm:two:cpu0</entry></legend></meta><data><row><t>2</t><v>0.2</v><v>1</v></row><row><t>1</t><v>NaN</v><v>1</v></row><row><t>3</t><v>Infinity</v><v>1</v></row></data></xport>'
        self.assertEqual(parse_rrd(xml,'vm','one'),{'cpu0':[(2.0,0.2)]})
        self.assertEqual(parse_rrd(xml,'host','one'),{})

    def test_rrd_rejects_entity_documents(self):
        with self.assertRaises(ValueError): parse_rrd(b'<!DOCTYPE x [<!ENTITY y "z">]><x/>','vm','one')

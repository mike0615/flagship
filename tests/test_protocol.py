import unittest
from flagship.protocol import decode_reference_result


class ProtocolTests(unittest.TestCase):
    def test_live_xcp_ng_26_task_result_implicit_string(self):
        self.assertEqual(decode_reference_result('<value>OpaqueRef:example-object</value>'), 'OpaqueRef:example-object')

    def test_explicit_string_and_escaped_opaque_content(self):
        self.assertEqual(decode_reference_result('<value><string>server&amp;object</string></value>'), 'server&object')

    def test_non_string_task_results_are_not_coerced_into_references(self):
        for text in ('<value><int>5</int></value>', '<value><array/></value>', '<value/>',
                     '<value><string>a</string><string>b</string></value>'):
            with self.assertRaises(ValueError):
                decode_reference_result(text)

class ImportResultTests(unittest.TestCase):
    def test_single_vm_set_accepts_implicit_and_explicit_strings(self):
        from flagship.protocol import decode_import_result
        for member in ('<value>OpaqueRef:vm</value>','<value><string>OpaqueRef:vm</string></value>'):
            self.assertEqual(decode_import_result('<value><array><data>'+member+'</data></array></value>'),'OpaqueRef:vm')

    def test_multiple_and_empty_vm_sets_never_pick_an_arbitrary_vm(self):
        from flagship.protocol import decode_import_result
        for members in ('','<value>a</value><value>b</value>','<value><int>1</int></value>'):
            with self.assertRaises(ValueError): decode_import_result('<value><array><data>'+members+'</data></array></value>')

    def test_import_result_does_not_expand_entities(self):
        from flagship.protocol import decode_import_result
        with self.assertRaises(ValueError): decode_import_result('<!DOCTYPE x [<!ENTITY y "z">]><value>&y;</value>')

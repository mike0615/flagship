import unittest
from xenadmin_rocky.protocol import decode_reference_result


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

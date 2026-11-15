"""XAPI scalar task results, including XML-RPC's implicit string representation."""
import xml.etree.ElementTree as ET

NULL = 'OpaqueRef:NULL'


def decode_reference_result(result):
    if not isinstance(result, str) or not result or result == NULL:
        raise ValueError('Task did not return an object reference')
    if not result.lstrip().startswith('<'):
        return result
    if len(result) > 65536 or '<!DOCTYPE' in result.upper() or '<!ENTITY' in result.upper():
        raise ValueError('Invalid task result XML')
    try:
        node = ET.fromstring(result.lstrip())
    except ET.ParseError:
        raise ValueError('Invalid task result XML') from None
    if node.tag != 'value':
        raise ValueError('Task did not return one object reference')
    if len(node) == 0:
        reference = node.text
    elif len(node) == 1 and node[0].tag == 'string' and len(node[0]) == 0:
        reference = node[0].text
    else:
        raise ValueError('Task did not return one string object reference')
    if not reference or reference == NULL:
        raise ValueError('Task did not return an object reference')
    return reference

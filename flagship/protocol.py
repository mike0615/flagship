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


def decode_import_result(result):
    """VM.import tasks return a VM set, unlike scalar clone/copy task results.

    The single-VM transfer workflow accepts exactly one member. Multiple-VM
    archives retain their task for inspection rather than guessing a target.
    """
    try:
        return decode_reference_result(result)
    except ValueError:
        pass
    if not isinstance(result,str) or len(result)>65536 or '<!DOCTYPE' in result.upper() or '<!ENTITY' in result.upper():
        raise ValueError('Invalid import task result')
    try: root=ET.fromstring(result.lstrip())
    except ET.ParseError: raise ValueError('Invalid import task result XML') from None
    if root.tag!='value' or len(root)!=1 or root[0].tag!='array' or len(root[0])!=1 or root[0][0].tag!='data':
        raise ValueError('Import did not return a VM reference set')
    entries=list(root[0][0])
    if len(entries)!=1 or entries[0].tag!='value':
        raise ValueError('Import returned multiple or no VMs; inspect the recorded task before changing devices')
    return decode_reference_result(ET.tostring(entries[0],encoding='unicode'))

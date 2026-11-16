"""Read-only XAPI inventory projections shared by the desktop and tests."""
def size(value):
    try: number = float(value)
    except (TypeError, ValueError): return 'Unknown'
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'):
        if abs(number) < 1024: return '{:.1f} {}'.format(number, unit)
        number /= 1024
    return '{:.1f} EiB'.format(number)


def ordinary(r):
    return not any(r.get(k) for k in ('is_a_template', 'is_a_snapshot', 'is_control_domain'))


def tabs_for(cls, r):
    if cls == 'host': return ('General', 'Memory', 'Storage', 'Networking', 'NICs', 'GPU', 'Console', 'Performance', 'Search')
    if cls == 'VM' and ordinary(r): return ('General', 'Memory', 'Storage', 'Networking', 'Console', 'Performance', 'Snapshots', 'Search')
    if cls == 'SR': return ('General', 'Storage', 'Search')
    if cls: return ('General', 'Storage', 'Networking', 'Search')
    return ('Home', 'Search')


def related(records, cls, ref, tab):
    if tab in ('Tasks', 'Alerts'):
        kind = 'task' if tab == 'Tasks' else 'message'
        return kind, records.get(kind, {})
    if tab == 'Snapshots': return 'VM', {k:v for k,v in records.get('VM', {}).items() if v.get('snapshot_of') == ref}
    if tab == 'Memory': return 'VM', {k:v for k,v in records.get('VM', {}).items() if (k == ref if cls == 'VM' else v.get('resident_on') == ref) and ordinary(v)}
    if tab in ('NICs', 'GPU'):
        kind = 'PIF' if tab == 'NICs' else 'PGPU'
        return kind, {k:v for k,v in records.get(kind, {}).items() if v.get('host') == ref}
    if tab == 'Storage':
        if cls == 'VM': return 'VBD', {k:v for k,v in records.get('VBD', {}).items() if v.get('VM') == ref}
        if cls == 'SR': return 'VDI', {k:v for k,v in records.get('VDI', {}).items() if v.get('SR') == ref}
        if cls == 'host':
            srs = {v.get('SR') for v in records.get('PBD', {}).values() if v.get('host') == ref}
            return 'SR', {k:v for k,v in records.get('SR', {}).items() if k in srs}
        return 'SR', records.get('SR', {})
    if tab == 'Networking':
        if cls == 'VM': return 'VIF', {k:v for k,v in records.get('VIF', {}).items() if v.get('VM') == ref}
        if cls == 'host':
            nets = {v.get('network') for v in records.get('PIF', {}).values() if v.get('host') == ref}
            return 'network', {k:v for k,v in records.get('network', {}).items() if k in nets}
        return 'network', records.get('network', {})
    return cls, {ref: records.get(cls, {}).get(ref, {})}


FIELDS = {
 'SR': (('Name','name_label'),('Type','type'),('Shared','shared'),('Used','physical_utilisation'),('Size','physical_size'),('Virtual allocation','virtual_allocation')),
 'VDI': (('Name','name_label'),('Size','virtual_size'),('Used','physical_utilisation'),('Type','type'),('Read only','read_only')),
 'VBD': (('Device','userdevice'),('Virtual disk','VDI'),('Type','type'),('Attached','currently_attached'),('Mode','mode')),
 'VIF': (('Device','device'),('Network','network'),('MAC','MAC'),('Attached','currently_attached'),('MTU','MTU')),
 'network': (('Name','name_label'),('Bridge','bridge'),('MTU','MTU')),
 'PIF': (('Device','device'),('Network','network'),('MAC','MAC'),('Attached','currently_attached'),('VLAN','VLAN'),('IP address','IP'),('Management','management')),
 'VM': (('Name','name_label'),('Power state','power_state'),('vCPUs','VCPUs_at_startup'),('Memory','memory_dynamic_max'),('Host','resident_on')),
 'task': (('Name','name_label'),('Status','status'),('Progress','progress'),('Error','error_info')),
 'message': (('Name','name'),('Priority','priority'),('Created','timestamp'),('Message','body')),
 'PGPU': (('Device','device_name'),('PCI','PCI'),('GPU group','GPU_group')),
}


def values(records, cls, r):
    out = []
    for label, field in FIELDS.get(cls, (('Name','name_label'),('UUID','uuid'))):
        v = r.get(field, '')
        if field in ('network', 'VDI', 'resident_on'):
            kind = 'host' if field == 'resident_on' else field
            v = records.get(kind, {}).get(v, {}).get('name_label') or v
        elif field in ('physical_utilisation', 'physical_size', 'virtual_allocation', 'virtual_size', 'memory_dynamic_max'): v = size(v)
        elif isinstance(v, bool): v = 'Yes' if v else 'No'
        elif field == 'progress':
            try: v = '{:.0%}'.format(float(v))
            except (TypeError, ValueError): v = 'Unknown'
        elif isinstance(v, list): v = ', '.join(str(x) for x in v)
        out.append(str(v))
    return out

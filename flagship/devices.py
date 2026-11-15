"""Disk, installation-media and VIF workflows; no implicit guest-data deletion."""
import re
from .api import APIError
from .workflows import Provisioner, WorkflowError, GiB, NULL


class DeviceManager(Provisioner):
    actions = frozenset(('add_disk', 'attach_disk', 'detach_disk', 'delete_disk', 'grow_disk',
                         'rename_disk', 'connect_disk', 'disconnect_disk', 'add_cd', 'remove_cd', 'change_iso', 'add_nic', 'move_nic',
                         'connect_nic', 'disconnect_nic', 'remove_nic'))

    def execute(self, action, vm, **options):
        if action not in self.actions:
            raise ValueError('Unsupported device operation')
        try:
            self.vm = vm
            self.machine = self.call('VM.get_record', vm)
            if (self.machine.get('is_a_template') or self.machine.get('is_control_domain') or
                    self.machine.get('is_a_snapshot') or self.machine.get('power_state') not in ('Halted', 'Running')):
                raise ValueError('Select a halted or running ordinary VM')
            self.resources['VM'] = vm
            getattr(self, action)(**options)
            return {'operation': action, 'status': 'completed', 'resources': self.resources, 'tasks': self.tasks}
        except Exception as exc:
            reason = str(exc) if isinstance(exc, (APIError, ValueError)) else type(exc).__name__
            raise WorkflowError(self.stage, reason, self.resources, self.tasks) from None

    def remember(self, kind, ref):
        self.resources[kind] = ref
        # Capture stable identities through Client.observe before the next mutation.
        self.call(kind + '.get_record', ref)
        return ref

    def vbd(self, ref, kind=None):
        record = self.call('VBD.get_record', ref)
        if record.get('VM') != self.vm or (kind and record.get('type') != kind):
            raise ValueError('Choose the correct disk/media connection on this VM')
        self.resources['VBD'] = ref
        return record

    def vif(self, ref):
        record = self.call('VIF.get_record', ref)
        if record.get('VM') != self.vm:
            raise ValueError('Network adapter does not belong to this VM')
        self.resources['VIF'] = ref
        return record

    def disk(self, ref):
        record = self.call('VDI.get_record', ref)
        if record.get('type') != 'user':
            raise ValueError('Choose a guest data disk, not ISO/system/metadata storage')
        self.resources['VDI'] = ref
        return record

    def other_disk_users(self, disk, own_vbd=None):
        if 'VBDs' not in disk:
            raise ValueError('Cannot verify disk associations; refresh before changing it')
        return [ref for ref in disk['VBDs'] if ref != own_vbd]

    def writable_exclusive_disk(self, ref, own_vbd=None):
        record = self.disk(ref)
        if record.get('read_only') or record.get('is_a_snapshot') or record.get('sharable'):
            raise ValueError('Shared, read-only and snapshot disks cannot be changed by this operation')
        if self.other_disk_users(record, own_vbd):
            raise ValueError('Disk is also associated with another connection; inspect its users first')
        return record

    def free_vbd_device(self, kind='Disk'):
        devices = [str(d) for d in self.call('VM.get_allowed_VBD_devices', self.vm)]
        if kind == 'CD':
            devices = [d for d in devices if d in ('0', '1', '2', '3')]
        if not devices:
            raise ValueError('No free {} device positions'.format(kind))
        return '3' if kind == 'CD' and '3' in devices else devices[0]

    def create_vbd(self, vdi, kind, device, read_only=False, owner=False):
        empty = vdi == NULL
        ref = self.async_call('VBD.create', {'VM': self.vm, 'VDI': vdi, 'userdevice': device,
            'device': '', 'bootable': False, 'mode': 'RO' if read_only or kind == 'CD' else 'RW',
            'type': kind, 'empty': empty, 'unpluggable': True, 'other_config': {'owner': 'true'} if owner else {},
            'qos_algorithm_type': '', 'qos_algorithm_params': {}}, reference=True)
        self.remember('VBD', ref)
        if self.machine['power_state'] == 'Running':
            self.async_call('VBD.plug', ref)
        return ref

    def add_disk(self, sr, name, size_gib):
        if not isinstance(name, str) or not name.strip() or len(name) > 255:
            raise ValueError('Disk name must contain 1 to 255 characters')
        if type(size_gib) is not int or not 1 <= size_gib <= 2097152:
            raise ValueError('Disk size must be between 1 and 2097152 GiB')
        storage = self.call('SR.get_record', sr)
        if storage.get('content_type') == 'iso' or 'vdi_create' not in storage.get('allowed_operations', []):
            raise ValueError('Choose writable VM storage')
        device = self.free_vbd_device()
        ref = self.async_call('VDI.create', {'name_label': name.strip(), 'name_description': '',
            'SR': sr, 'virtual_size': size_gib * GiB, 'type': 'user', 'sharable': False,
            'read_only': False, 'other_config': {}, 'xenstore_data': {}, 'sm_config': {}}, reference=True)
        self.remember('VDI', ref)
        self.create_vbd(ref, 'Disk', device, owner=True)

    def attach_disk(self, vdi):
        disk = self.disk(vdi)
        if disk.get('is_a_snapshot'):
            raise ValueError('Clone snapshot data before attaching it as an ordinary disk')
        if not disk.get('sharable') and self.other_disk_users(disk):
            raise ValueError('This non-shared disk already has a connection')
        device = self.free_vbd_device()
        self.create_vbd(vdi, 'Disk', device, read_only=bool(disk.get('read_only')))

    def detach_disk(self, vbd):
        record = self.vbd(vbd, 'Disk')
        self.resources['VDI'] = record['VDI']
        if record.get('currently_attached'):
            self.async_call('VBD.unplug', vbd)
        # If unplug fails, execution stops. Never destroy in a finally block.
        self.async_call('VBD.destroy', vbd)

    def delete_disk(self, vbd, confirmation_uuid):
        record = self.vbd(vbd, 'Disk')
        ref = record['VDI']
        disk = self.writable_exclusive_disk(ref, own_vbd=vbd)
        if not disk.get('managed') or not disk.get('uuid') or confirmation_uuid != disk['uuid']:
            raise ValueError('Permanent deletion requires the exact UUID of a managed guest disk')
        self.detach_disk(vbd)
        # Re-read after detaching; another VM may have acquired a connection.
        disk = self.writable_exclusive_disk(ref)
        if disk.get('uuid') != confirmation_uuid:
            raise ValueError('Disk identity changed; refusing deletion')
        self.async_call('VDI.destroy', ref)

    def grow_disk(self, vbd, size_gib):
        record = self.vbd(vbd, 'Disk')
        disk = self.writable_exclusive_disk(record['VDI'], own_vbd=vbd)
        if type(size_gib) is not int or not 1 <= size_gib <= 2097152 or size_gib * GiB <= int(disk['virtual_size']):
            raise ValueError('New disk size must be larger than the current size; shrinking is not supported')
        allowed = disk.get('allowed_operations', [])
        action = 'resize_online' if self.machine['power_state'] == 'Running' and 'resize_online' in allowed else 'resize'
        if action not in allowed:
            raise ValueError('The server/storage does not allow growing this disk in its current state')
        self.async_call('VDI.' + action, record['VDI'], size_gib * GiB)

    def connect_disk(self, vbd):
        record = self.vbd(vbd)
        if record.get('type') not in ('Disk', 'CD') or self.machine['power_state'] != 'Running':
            raise ValueError('Choose a disk/DVD connection on a running VM')
        if not record.get('currently_attached'):
            self.async_call('VBD.plug', vbd)

    def disconnect_disk(self, vbd):
        record = self.vbd(vbd)
        if record.get('type') not in ('Disk', 'CD'):
            raise ValueError('Choose a disk/DVD connection')
        if record.get('currently_attached'):
            self.async_call('VBD.unplug', vbd)

    def rename_disk(self, vbd, name):
        record = self.vbd(vbd, 'Disk')
        self.disk(record['VDI'])
        if not isinstance(name, str) or not name.strip() or len(name) > 255:
            raise ValueError('Disk name must contain 1 to 255 characters')
        self.call('VDI.set_name_label', record['VDI'], name.strip())

    def validate_iso(self, iso):
        if not iso:
            return NULL
        media = self.call('VDI.get_record', iso)
        storage = self.call('SR.get_record', media['SR'])
        if storage.get('content_type') != 'iso':
            raise ValueError('Select media from an ISO repository')
        return iso

    def add_cd(self, iso=''):
        media = self.validate_iso(iso)
        device = self.free_vbd_device('CD')
        self.create_vbd(media, 'CD', device, read_only=True)

    def remove_cd(self, vbd):
        record = self.vbd(vbd, 'CD')
        if record.get('currently_attached'):
            self.async_call('VBD.unplug', vbd)
        self.async_call('VBD.destroy', vbd)

    def change_iso(self, vbd, iso=''):
        record = self.vbd(vbd, 'CD')
        media = self.validate_iso(iso)
        if not record.get('empty', True):
            self.async_call('VBD.eject', vbd)
        if media != NULL:
            self.async_call('VBD.insert', vbd, media)

    def add_nic(self, network, mac=''):
        if mac and (not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', mac) or int(mac[:2], 16) & 1):
            raise ValueError('MAC must be a unicast address in aa:bb:cc:dd:ee:ff form, or blank for automatic assignment')
        net = self.call('network.get_record', network)
        devices = self.call('VM.get_allowed_VIF_devices', self.vm)
        if not devices:
            raise ValueError('No free network adapter positions')
        ref = self.async_call('VIF.create', {'VM': self.vm, 'network': network, 'device': str(devices[0]),
            'MAC': mac, 'MTU': int(net.get('MTU', 1500)), 'other_config': {}, 'qos_algorithm_type': '',
            'qos_algorithm_params': {}, 'locking_mode': 'network_default'}, reference=True)
        self.remember('VIF', ref)
        if self.machine['power_state'] == 'Running':
            self.async_call('VIF.plug', ref)

    def move_nic(self, vif, network):
        self.vif(vif)
        self.call('network.get_record', network)
        # VIF.move supports a running VM and retains the adapter identity/MAC.
        self.async_call('VIF.move', vif, network)

    def connect_nic(self, vif):
        record = self.vif(vif)
        if self.machine['power_state'] != 'Running':
            raise ValueError('Start the VM before connecting a network adapter')
        if not record.get('currently_attached'):
            self.async_call('VIF.plug', vif)

    def disconnect_nic(self, vif):
        if self.vif(vif).get('currently_attached'):
            self.async_call('VIF.unplug', vif)

    def remove_nic(self, vif):
        record = self.vif(vif)
        if record.get('currently_attached'):
            self.async_call('VIF.unplug', vif)
        self.async_call('VIF.destroy', vif)

"""Ordered XAPI workflows with explicit recovery records and no mutation replay."""
from dataclasses import dataclass
import json
import threading
import time
import xml.etree.ElementTree as ET
from .api import APIError

MiB = 1024**2
GiB = 1024**3
NULL = 'OpaqueRef:NULL'


def stage_label(stage):
    method = stage.removesuffix(' task monitoring')
    labels = {'VM.get_record': 'Reading VM configuration', 'SR.get_record': 'Checking storage',
              'network.get_record': 'Checking network', 'VDI.get_record': 'Checking installation media',
              'VBD.get_record': 'Checking virtual disk connections', 'VIF.get_record': 'Checking network adapters',
              'Async.VM.clone': 'Creating VM from template', 'VM.clone': 'Creating VM from template',
              'Async.VM.copy': 'Copying template disks', 'VM.copy': 'Copying template disks',
              'VM.set_is_a_template': 'Preparing new VM', 'VM.set_other_config': 'Applying installation settings',
              'Async.VM.provision': 'Provisioning VM', 'VM.provision': 'Provisioning VM',
              'Async.VDI.create': 'Creating virtual disk', 'VDI.create': 'Creating virtual disk',
              'Async.VBD.create': 'Connecting virtual disk or media', 'VBD.create': 'Connecting virtual disk or media',
              'Async.VIF.destroy': 'Removing network adapter', 'VIF.destroy': 'Removing network adapter',
              'Async.VIF.create': 'Adding network adapter', 'VIF.create': 'Adding network adapter',
              'Async.VBD.eject': 'Ejecting existing media', 'VBD.eject': 'Ejecting existing media',
              'Async.VBD.insert': 'Attaching installation media', 'VBD.insert': 'Attaching installation media',
              'Async.VM.start': 'Starting VM', 'VM.start': 'Starting VM',
              'Configure CPU and memory': 'Configuring CPU and memory'}
    device_labels = {'VBD.plug': 'Connecting disk/DVD device', 'VBD.unplug': 'Disconnecting disk/DVD device',
                     'VBD.destroy': 'Removing disk/DVD connection', 'VDI.destroy': 'Deleting disk data',
                     'VDI.resize': 'Growing virtual disk', 'VDI.resize_online': 'Growing virtual disk',
                     'VDI.set_name_label': 'Renaming virtual disk', 'VIF.move': 'Changing adapter network',
                     'VIF.plug': 'Connecting network adapter', 'VIF.unplug': 'Disconnecting network adapter',
                     'VM.get_allowed_VBD_devices': 'Finding free disk/DVD position',
                     'VM.get_allowed_VIF_devices': 'Finding free network adapter position'}
    labels.update(device_labels)
    return labels.get(method.removeprefix('Async.'), labels.get(method, 'Checking workflow state'))


class WorkflowError(RuntimeError):
    def __init__(self, stage, reason, resources, tasks):
        self.stage = stage
        self.reason = reason
        self.resources = dict(resources)
        self.tasks = list(tasks)
        super().__init__(stage + ': ' + reason + '\n\nRecovery information:\n' +
                         json.dumps({'resources': resources, 'tasks': tasks}, indent=2) +
                         '\nInspect these objects/tasks before retrying. No automatic rollback was attempted.')


@dataclass(frozen=True)
class VMPlan:
    template: str
    name: str
    sr: str
    network: str
    cpus: int = 2
    memory_mib: int = 2048
    disk_gib: int = 20
    iso: str = ''
    start: bool = False

    def validate(self):
        if not self.name.strip() or len(self.name) > 255:
            raise ValueError('VM name must contain 1 to 255 characters')
        for ref in (self.template, self.sr, self.network):
            if not isinstance(ref, str) or not ref or ref == NULL:
                raise ValueError('Select a template, storage repository and network')
        for value, low, high, label in ((self.cpus, 1, 1024, 'vCPUs'),
                  (self.memory_mib, 128, 1048576, 'Memory MiB'),
                  (self.disk_gib, 1, 2097152, 'Disk GiB')):
            if type(value) is not int or not low <= value <= high:
                raise ValueError('{} must be between {} and {}'.format(label, low, high))


def task_reference(result):
    if not isinstance(result, str) or not result or result == NULL:
        raise ValueError('Task did not return an object reference')
    if result.lstrip().startswith('<'):
        if len(result) > 65536 or '<!DOCTYPE' in result.upper() or '<!ENTITY' in result.upper():
            raise ValueError('Invalid task result XML')
        node = ET.fromstring(result)
        strings = list(node.iter('string'))
        if len(strings) != 1 or not strings[0].text or strings[0].text == NULL:
            raise ValueError('Task did not return one object reference')
        return strings[0].text
    return result


def configure_hardware(client, vm, cpus, memory_mib, checkpoint=lambda: None):
    if type(cpus) is not int or not 1 <= cpus <= 1024:
        raise ValueError('vCPU count must be between 1 and 1024')
    if type(memory_mib) is not int or not 128 <= memory_mib <= 1048576:
        raise ValueError('Memory must be between 128 and 1048576 MiB')
    checkpoint()
    record = client.call('VM.get_record', vm)
    if (record.get('power_state') != 'Halted' or record.get('is_control_domain') or
            record.get('is_a_snapshot') or record.get('is_a_template')):
        raise ValueError('Select a halted ordinary VM for hardware changes')
    static_min = int(record.get('memory_static_min', 0))
    memory = memory_mib * MiB
    if memory < static_min:
        raise ValueError('Memory is below the template/VM static minimum')
    stage = 'set memory limits'
    try:
        checkpoint()
        client.call('VM.set_memory_limits', vm, static_min, memory, memory, memory)
        # Lower startup first when shrinking the maximum, as in upstream's action.
        methods = ('set_VCPUs_max', 'set_VCPUs_at_startup')
        if cpus < int(record.get('VCPUs_at_startup', 1)):
            methods = methods[::-1]
        for method in methods:
            stage = method
            checkpoint()
            client.call('VM.' + method, vm, cpus)
    except Exception as exc:
        reason = str(exc) if isinstance(exc, (APIError, ValueError)) else type(exc).__name__
        raise WorkflowError(stage, reason, {'VM': vm}, []) from None


class Provisioner:
    def __init__(self, client, stop=None, timeout=1800, interval=1, clock=time.monotonic, progress=None):
        self.client = client
        self.stop = stop or threading.Event()
        self.timeout = timeout
        self.interval = interval
        self.clock = clock
        self.resources = {}
        self.tasks = []
        self.stage = 'validate'
        self.progress = progress or (lambda report: None)

    def announce(self):
        self.progress({'stage': self.stage, 'label': stage_label(self.stage), 'resources': dict(self.resources),
                       'tasks': [dict(task) for task in self.tasks]})

    def checkpoint(self):
        if self.stop.is_set():
            raise ValueError('Monitoring stopped; a submitted server task may still be running')

    def call(self, method, *args):
        self.checkpoint()
        self.stage = method
        self.announce()
        return self.client.call(method, *args)

    def async_call(self, method, *args, reference=False):
        task = self.call('Async.' + method, *args)
        if not isinstance(task, str) or not task or task == NULL:
            raise ValueError('Invalid task reference; server outcome is uncertain')
        self.tasks.append({'method': method, 'task': task, 'status': 'pending'})
        entry = self.tasks[-1]
        self.announce()
        deadline = self.clock() + self.timeout
        while True:
            self.checkpoint()
            self.stage = method + ' task monitoring'
            record = self.client.call('task.get_record', task)
            status = record.get('status')
            entry['status'] = status
            entry['progress'] = record.get('progress', 0)
            self.announce()
            if status == 'success':
                return task_reference(record.get('result', '')) if reference else None
            if status in ('failure', 'cancelled'):
                raise APIError(record.get('error_info') or [str(status).upper()])
            if status not in ('pending', 'cancelling'):
                raise ValueError('Unknown task outcome; inspect the server before retrying')
            if self.clock() >= deadline:
                raise TimeoutError('Task monitoring timed out')
            self.stop.wait(self.interval)

    def create(self, plan):
        plan.validate()
        try:
            template = self.call('VM.get_record', plan.template)
            if (not template.get('is_a_template') or template.get('is_a_snapshot') or
                    template.get('is_control_domain') or template.get('power_state') != 'Halted'):
                raise ValueError('Choose a halted VM template')
            if plan.memory_mib * MiB < int(template.get('memory_static_min', 0)):
                raise ValueError('Memory is below the template static minimum')
            sr = self.call('SR.get_record', plan.sr)
            if sr.get('content_type') == 'iso' or 'vdi_create' not in sr.get('allowed_operations', []):
                raise ValueError('Choose writable VM storage with vdi_create allowed')
            network = self.call('network.get_record', plan.network)
            if plan.iso:
                iso = self.call('VDI.get_record', plan.iso)
                iso_sr = self.call('SR.get_record', iso['SR'])
                if iso_sr.get('content_type') != 'iso':
                    raise ValueError('Install media must be from an ISO storage repository')
            vbds = [self.call('VBD.get_record', ref) for ref in template.get('VBDs', [])]
            installed = any(v.get('type') == 'Disk' and not v.get('empty') and
                            v.get('VDI') not in ('', None, NULL) for v in vbds)
            if installed:
                vm = self.async_call('VM.copy', plan.template, plan.name.strip(), plan.sr, reference=True)
            else:
                vm = self.async_call('VM.clone', plan.template, plan.name.strip(), reference=True)
            cloned = self.call('VM.get_record', vm)
            if vm == plan.template or (template.get('uuid') and cloned.get('uuid') == template['uuid']):
                raise ValueError('Server returned the source VM; refusing to change it')
            self.resources['VM'] = vm
            if cloned.get('is_a_template'):
                self.call('VM.set_is_a_template', vm, False)
            self.stage = 'Configure CPU and memory'
            self.announce()
            configure_hardware(self.client, vm, plan.cpus, plan.memory_mib, self.checkpoint)
            config = dict(cloned.get('other_config', {}))
            config.pop('disks', None)  # Explicit storage below; avoid template's default SR.
            if plan.iso:
                config['install-repository'] = 'cdrom'
            self.call('VM.set_other_config', vm, config)
            self.async_call('VM.provision', vm)
            if not installed:
                vdi = self.async_call('VDI.create', {
                    'name_label': plan.name.strip() + ' disk', 'name_description': '',
                    'SR': plan.sr, 'virtual_size': plan.disk_gib * GiB, 'type': 'user',
                    'sharable': False, 'read_only': False, 'other_config': {},
                    'xenstore_data': {}, 'sm_config': {}}, reference=True)
                self.resources['VDI'] = vdi
                self.call('VDI.get_record', vdi)
                self.add_vbd(vm, vdi, 'Disk')
            fresh = self.call('VM.get_record', vm)
            # Only the new VM's inherited VIFs are replaced, as upstream does.
            for vif in fresh.get('VIFs', []):
                if self.call('VIF.get_record', vif).get('VM') != vm:
                    raise ValueError('Network device does not belong to the new VM')
                self.async_call('VIF.destroy', vif)
            devices = self.call('VM.get_allowed_VIF_devices', vm)
            if not devices:
                raise ValueError('No free network device positions')
            vif = self.async_call('VIF.create', {
                'VM': vm, 'network': plan.network, 'device': str(devices[0]),
                'MAC': '', 'MTU': int(network.get('MTU', 1500)), 'other_config': {},
                'qos_algorithm_type': '', 'qos_algorithm_params': {},
                'locking_mode': 'network_default'}, reference=True)
            self.resources['VIF'] = vif
            if plan.iso:
                drives = [(ref, self.call('VBD.get_record', ref)) for ref in fresh.get('VBDs', [])]
                cd = next(((ref, v) for ref, v in drives if v.get('type') == 'CD'), None)
                if cd:
                    ref, record = cd
                    if not record.get('empty', True):
                        self.async_call('VBD.eject', ref)
                    self.async_call('VBD.insert', ref, plan.iso)
                    self.resources['CD'] = ref
                else:
                    self.add_vbd(vm, plan.iso, 'CD')
            if plan.start:
                self.async_call('VM.start', vm, False, False)
            return {'resources': self.resources, 'tasks': self.tasks, 'copied_template_disks': installed}
        except WorkflowError as exc:
            raise WorkflowError(exc.stage, exc.reason, self.resources, self.tasks) from None
        except Exception as exc:
            reason = str(exc) if isinstance(exc, (APIError, ValueError)) else type(exc).__name__
            raise WorkflowError(self.stage, reason, self.resources, self.tasks) from None

    def add_vbd(self, vm, vdi, kind):
        devices = self.call('VM.get_allowed_VBD_devices', vm)
        if kind == 'CD':
            devices = [d for d in devices if str(d) in ('0', '1', '2', '3')]
        if not devices:
            raise ValueError('No free {} device positions'.format(kind))
        device = '3' if kind == 'CD' and '3' in devices else str(devices[0])
        ref = self.async_call('VBD.create', {'VM': vm, 'VDI': vdi, 'userdevice': device,
            'device': '', 'bootable': kind == 'Disk', 'mode': 'RO' if kind == 'CD' else 'RW',
            'type': kind, 'empty': False, 'unpluggable': True,
            'other_config': {'owner': 'true'} if kind == 'Disk' else {},
            'qos_algorithm_type': '', 'qos_algorithm_params': {}}, reference=True)
        self.resources['VBD' if kind == 'Disk' else 'CD'] = ref

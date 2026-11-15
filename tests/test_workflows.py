"""Stateful pool simulation exercises complete creation sequences and partial failures."""
import copy
import threading
import unittest
from flagship.api import APIError, wire_value
from flagship.workflows import (VMPlan, Provisioner, WorkflowError,
                                      configure_hardware, task_reference, MiB, GiB)


class Pool:
    def __init__(self, installed=False, fail=None):
        self.calls = []
        self.fail = fail
        self.counter = 0
        self.tasks = {}
        self.vms = {'template': {'uuid': 'source-uuid', 'name_label': 'Source template',
            'is_a_template': True, 'power_state': 'Halted', 'memory_static_min': str(128 * MiB),
            'VCPUs_at_startup': '4', 'other_config': {'disks': '<dangerous-default-sr/>', 'keep': 'yes'},
            'VIFs': ['source-vif'], 'VBDs': ['source-disk'] if installed else []}}
        self.vifs = {'source-vif': {'VM': 'template', 'network': 'old-network'}}
        self.vbds = {'source-disk': {'VM': 'template', 'VDI': 'source-data', 'type': 'Disk',
                                   'empty': False, 'userdevice': '0'}} if installed else {}
        self.vdis = {'source-data': {'SR': 'old-sr', 'virtual_size': str(80 * GiB)},
                     'iso': {'SR': 'iso-sr'}}
        self.source = copy.deepcopy((self.vms['template'], self.vifs['source-vif'],
                                     self.vdis['source-data']))

    def task(self, result=''):
        self.counter += 1
        ref = 'task-' + str(self.counter)  # Deliberately no OpaqueRef prefix.
        self.tasks[ref] = {'status': 'success', 'result': '<value>' + result + '</value>' if result else ''}
        return ref

    def call(self, method, *args):
        self.calls.append((method, args))
        if method == self.fail:
            raise APIError(['INJECTED_FAILURE', 'private-details'])
        if method == 'task.get_record':
            return self.tasks[args[0]]
        if method == 'VM.get_record':
            return copy.deepcopy(self.vms[args[0]])
        if method == 'SR.get_record':
            return {'content_type': 'iso' if args[0] == 'iso-sr' else 'user',
                    'allowed_operations': ['vdi_create']}
        if method == 'network.get_record':
            return {'MTU': '1500'}
        if method == 'VDI.get_record':
            return self.vdis[args[0]]
        if method == 'VBD.get_record':
            return copy.deepcopy(self.vbds[args[0]])
        if method == 'VIF.get_record':
            return self.vifs[args[0]]
        if method in ('Async.VM.clone', 'Async.VM.copy'):
            self.vms['new-vm'] = copy.deepcopy(self.vms['template'])
            self.vms['new-vm'].update(uuid='new-uuid', is_a_template=True, name_label=args[1], VIFs=['new-vif'])
            self.vifs['new-vif'] = {'VM': 'new-vm', 'network': 'old-network'}
            if self.vms['new-vm']['VBDs']:
                self.vbds['copied-disk'] = dict(self.vbds['source-disk'], VM='new-vm', VDI='copied-data')
                self.vdis['copied-data'] = dict(self.vdis['source-data'], SR=args[2])
                self.vms['new-vm']['VBDs'] = ['copied-disk']
            return self.task('new-vm')
        if method == 'VM.set_memory_limits':
            assert int(args[1]) <= int(args[3]) <= int(args[4]) <= int(args[2])
            self.vms[args[0]]['memory_dynamic_max'] = str(args[4])
            return ''
        if method.startswith('VM.set_VCPUs_'):
            self.vms[args[0]][method.split('set_')[1]] = str(args[1])
            return ''
        if method == 'VM.set_other_config':
            self.vms[args[0]]['other_config'] = dict(args[1])
            return ''
        if method == 'Async.VM.provision':
            assert self.vms[args[0]]['is_a_template'], 'XAPI only provisions templates'
            self.vms[args[0]]['is_a_template'] = False
            assert 'disks' not in self.vms[args[0]]['other_config']
            return self.task()
        if method == 'VM.get_allowed_VBD_devices':
            used = [self.vbds[r]['userdevice'] for r in self.vms[args[0]]['VBDs']]
            return [str(i) for i in range(4) if str(i) not in used]
        if method == 'Async.VDI.create':
            self.vdis['new-data'] = dict(args[0])
            return self.task('new-data')
        if method == 'Async.VBD.create':
            ref = 'new-cd' if args[0]['type'] == 'CD' else 'new-disk'
            self.vbds[ref] = dict(args[0])
            self.vms[args[0]['VM']]['VBDs'].append(ref)
            return self.task(ref)
        if method == 'Async.VIF.destroy':
            assert self.vifs[args[0]]['VM'] == 'new-vm', 'must never modify source template'
            self.vms['new-vm']['VIFs'].remove(args[0])
            del self.vifs[args[0]]
            return self.task()
        if method == 'VM.get_allowed_VIF_devices':
            return ['0']
        if method == 'Async.VIF.create':
            self.vifs['selected-vif'] = dict(args[0])
            self.vms[args[0]['VM']]['VIFs'].append('selected-vif')
            return self.task('selected-vif')
        if method == 'Async.VM.start':
            assert self.vms[args[0]]['VBDs']
            assert self.vms[args[0]]['VIFs'] == ['selected-vif']
            self.vms[args[0]]['power_state'] = 'Running'
            return self.task()
        raise AssertionError('Unexpected API method: ' + method)

    def assert_source_unchanged(self, test):
        test.assertEqual(self.source, (self.vms['template'], self.vifs['source-vif'], self.vdis['source-data']))


class WorkflowTests(unittest.TestCase):
    def plan(self, **kwargs):
        values = dict(template='template', name='New guest', sr='selected-sr', network='selected-network')
        values.update(kwargs)
        return VMPlan(**values)

    def test_installer_template_provisions_selected_storage_network_and_iso(self):
        pool = Pool()
        report = Provisioner(pool).create(self.plan(iso='iso', start=True))
        self.assertEqual(pool.vdis['new-data']['SR'], 'selected-sr')
        self.assertEqual(pool.vdis['new-data']['virtual_size'], 20 * GiB)
        self.assertEqual(pool.vifs['selected-vif']['network'], 'selected-network')
        self.assertEqual(pool.vbds['new-cd']['VDI'], 'iso')
        self.assertEqual(pool.vbds['new-cd']['mode'], 'RO')
        self.assertEqual(pool.vms['new-vm']['power_state'], 'Running')
        self.assertEqual(pool.vms['new-vm']['other_config']['keep'], 'yes')
        self.assertEqual(report['resources']['VM'], 'new-vm')
        pool.assert_source_unchanged(self)

    def test_installed_template_uses_copy_and_retains_disk_size(self):
        pool = Pool(installed=True)
        report = Provisioner(pool).create(self.plan(disk_gib=5))
        self.assertTrue(report['copied_template_disks'])
        self.assertEqual(pool.vdis['copied-data']['virtual_size'], str(80 * GiB))
        self.assertEqual(pool.vdis['copied-data']['SR'], 'selected-sr')
        self.assertNotIn('new-data', pool.vdis)
        self.assertNotIn('Async.VM.clone', [c[0] for c in pool.calls])
        pool.assert_source_unchanged(self)

    def test_partial_failure_retains_recovery_refs_and_never_deletes_disk(self):
        pool = Pool(fail='Async.VIF.create')
        with self.assertRaises(WorkflowError) as caught:
            Provisioner(pool).create(self.plan())
        self.assertEqual(caught.exception.resources['VM'], 'new-vm')
        self.assertEqual(caught.exception.resources['VDI'], 'new-data')
        self.assertNotIn('private-details', str(caught.exception))
        self.assertEqual([c[0] for c in pool.calls].count('Async.VIF.create'), 1)
        self.assertNotIn('VDI.destroy', [c[0] for c in pool.calls])
        self.assertNotIn('VM.destroy', [c[0] for c in pool.calls])
        pool.assert_source_unchanged(self)

    def test_hardware_failure_preserves_creation_recovery_context(self):
        pool = Pool(fail='VM.set_VCPUs_max')
        with self.assertRaises(WorkflowError) as caught:
            Provisioner(pool).create(self.plan())
        self.assertEqual(caught.exception.resources, {'VM': 'new-vm'})
        self.assertEqual(caught.exception.tasks[0]['method'], 'VM.clone')
        pool.assert_source_unchanged(self)

    def test_invalid_plan_makes_no_server_calls(self):
        pool = Pool()
        with self.assertRaises(ValueError):
            Provisioner(pool).create(self.plan(memory_mib=0))
        self.assertEqual(pool.calls, [])

    def test_non_template_is_rejected_before_mutation(self):
        pool = Pool()
        pool.vms['template']['is_a_template'] = False
        with self.assertRaises(WorkflowError):
            Provisioner(pool).create(self.plan())
        self.assertEqual([c[0] for c in pool.calls], ['VM.get_record'])

    def test_stopped_monitor_does_not_submit_work(self):
        stop = threading.Event()
        stop.set()
        pool = Pool()
        with self.assertRaises(WorkflowError):
            Provisioner(pool, stop=stop).create(self.plan())
        self.assertEqual(pool.calls, [])

    def test_timeout_retains_task_and_never_resubmits(self):
        pool = Pool()
        original = pool.call
        def pending(method, *args):
            if method == 'task.get_record':
                return {'status': 'pending'}
            return original(method, *args)
        pool.call = pending
        clock = iter((0, 2))
        provisioner = Provisioner(pool, timeout=1, interval=0, clock=lambda: next(clock))
        with self.assertRaises(TimeoutError):
            provisioner.async_call('VM.clone', 'template', 'new', reference=True)
        self.assertEqual(len(provisioner.tasks), 1)
        self.assertEqual([c[0] for c in pool.calls].count('Async.VM.clone'), 1)

    def test_cpu_shrink_lowers_startup_before_max(self):
        pool = Pool()
        pool.vms['guest'] = dict(pool.vms['template'], is_a_template=False)
        configure_hardware(pool, 'guest', 2, 4096)
        setters = [c[0] for c in pool.calls if 'set_VCPU' in c[0]]
        self.assertEqual(setters, ['VM.set_VCPUs_at_startup', 'VM.set_VCPUs_max'])

    def test_running_guest_cannot_be_reconfigured(self):
        pool = Pool()
        pool.vms['guest'] = dict(pool.vms['template'], power_state='Running', is_a_template=False)
        with self.assertRaises(ValueError):
            configure_hardware(pool, 'guest', 2, 4096)
        self.assertEqual([c[0] for c in pool.calls], ['VM.get_record'])

    def test_reference_result_is_opaque(self):
        self.assertEqual(task_reference('<value><string>server-result-17</string></value>'), 'server-result-17')
        self.assertEqual(task_reference('server-result-18'), 'server-result-18')
        self.assertEqual(task_reference('<value>server-result-19</value>'), 'server-result-19')
        with self.assertRaises(ValueError):
            task_reference('<value><string>OpaqueRef:NULL</string></value>')
        with self.assertRaises(ValueError):
            task_reference('<!DOCTYPE value [<!ENTITY x "abc">]><value><string>&x;</string></value>')

    def test_large_integer_encoding_preserves_booleans(self):
        value = wire_value({'size': 40 * GiB, 'enabled': True, 'cpus': [4]})
        self.assertEqual(value, {'size': str(40 * GiB), 'enabled': True, 'cpus': ['4']})
        with self.assertRaises(ValueError):
            wire_value(2**63)

    def test_template_cannot_be_modified_by_hardware_editor(self):
        pool = Pool()
        with self.assertRaises(ValueError):
            configure_hardware(pool, 'template', 2, 4096)
        self.assertEqual([c[0] for c in pool.calls], ['VM.get_record'])
        pool.assert_source_unchanged(self)

    def test_memory_below_template_minimum_never_clones(self):
        pool = Pool()
        pool.vms['template']['memory_static_min'] = str(4096 * MiB)
        with self.assertRaises(WorkflowError):
            Provisioner(pool).create(self.plan(memory_mib=2048))
        self.assertEqual([c[0] for c in pool.calls], ['VM.get_record'])

    def test_progress_snapshots_preserve_pending_and_confirmed_outcomes(self):
        pool = Pool()
        updates = []
        Provisioner(pool, progress=updates.append).create(self.plan())
        task_states = [task['status'] for report in updates for task in report['tasks']]
        self.assertIn('pending', task_states)
        self.assertIn('success', task_states)
        self.assertTrue(any(r['resources'].get('VM') == 'new-vm' for r in updates))
        self.assertEqual(updates[0]['resources'], {})

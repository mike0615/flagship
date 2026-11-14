import copy
import unittest
from xenadmin_rocky.api import APIError
from xenadmin_rocky.devices import DeviceManager
from xenadmin_rocky.workflows import WorkflowError, GiB, NULL
from test_workflows import Pool


class DevicePool(Pool):
    handled = {'Async.VDI.create', 'Async.VBD.create', 'Async.VBD.destroy', 'Async.VBD.plug', 'Async.VBD.unplug',
               'Async.VDI.destroy', 'Async.VDI.resize', 'Async.VDI.resize_online', 'VDI.set_name_label',
               'Async.VBD.eject', 'Async.VBD.insert', 'Async.VIF.create', 'Async.VIF.destroy',
               'Async.VIF.plug', 'Async.VIF.unplug', 'Async.VIF.move', 'VM.get_allowed_VIF_devices'}

    def __init__(self, running=False, fail=None):
        super().__init__(fail=fail)
        self.vms['guest'] = dict(copy.deepcopy(self.vms['template']), uuid='guest-uuid',
            is_a_template=False, power_state='Running' if running else 'Halted',
            VBDs=['disk-link'], VIFs=['adapter'])
        self.vdis['data'] = dict(uuid='disk-uuid', type='user', SR='selected-sr', virtual_size=str(20*GiB),
            VBDs=['disk-link'], managed=True, read_only=False, sharable=False, is_a_snapshot=False,
            allowed_operations=['resize', 'destroy'])
        self.vbds['disk-link'] = dict(uuid='vbd-uuid', VM='guest', VDI='data', type='Disk', empty=False,
            userdevice='0', mode='RW', currently_attached=running)
        self.vifs['adapter'] = dict(uuid='vif-uuid', VM='guest', network='old-network', MAC='02:11:22:33:44:55',
            device='0', currently_attached=running)

    def call(self, method, *args):
        if method not in self.handled:
            return super().call(method, *args)
        self.calls.append((method, args))
        if method == self.fail:
            raise APIError(['INJECTED_FAILURE', 'private-detail'])
        if method == 'Async.VDI.create':
            self.vdis['added-data'] = dict(args[0], uuid='added-disk-uuid', VBDs=[], managed=True,
                allowed_operations=['resize', 'destroy'])
            return self.task('added-data')
        if method == 'Async.VBD.create':
            ref = 'added-vbd-' + str(self.counter)
            self.vbds[ref] = dict(args[0], uuid=ref+'-uuid', currently_attached=False)
            self.vms[args[0]['VM']]['VBDs'].append(ref)
            if args[0]['VDI'] != NULL:
                self.vdis[args[0]['VDI']].setdefault('VBDs', []).append(ref)
            return self.task(ref)
        if method == 'Async.VBD.destroy':
            record = self.vbds[args[0]]
            assert not record['currently_attached'], 'must unplug before destroying a connection'
            self.vms[record['VM']]['VBDs'].remove(args[0])
            if record['VDI'] != NULL:
                self.vdis[record['VDI']]['VBDs'].remove(args[0])
            del self.vbds[args[0]]
            return self.task()
        if method in ('Async.VBD.plug', 'Async.VBD.unplug'):
            self.vbds[args[0]]['currently_attached'] = method.endswith('.plug')
            return self.task()
        if method == 'Async.VDI.destroy':
            assert not self.vdis[args[0]]['VBDs'], 'must not destroy associated disk data'
            del self.vdis[args[0]]
            return self.task()
        if method in ('Async.VDI.resize', 'Async.VDI.resize_online'):
            assert int(args[1]) > int(self.vdis[args[0]]['virtual_size'])
            self.vdis[args[0]]['virtual_size'] = str(args[1])
            return self.task()
        if method == 'VDI.set_name_label':
            self.vdis[args[0]]['name_label'] = args[1]
            return ''
        if method == 'Async.VBD.eject':
            record = self.vbds[args[0]]
            self.vdis[record['VDI']]['VBDs'].remove(args[0])
            record.update(VDI=NULL, empty=True)
            return self.task()
        if method == 'Async.VBD.insert':
            self.vbds[args[0]].update(VDI=args[1], empty=False)
            self.vdis[args[1]].setdefault('VBDs', []).append(args[0])
            return self.task()
        if method == 'VM.get_allowed_VIF_devices':
            used = [self.vifs[ref]['device'] for ref in self.vms[args[0]]['VIFs']]
            return [str(n) for n in range(8) if str(n) not in used]
        if method == 'Async.VIF.create':
            ref = 'added-vif'
            self.vifs[ref] = dict(args[0], uuid='added-vif-uuid', currently_attached=False)
            self.vms[args[0]['VM']]['VIFs'].append(ref)
            return self.task(ref)
        if method in ('Async.VIF.plug', 'Async.VIF.unplug'):
            self.vifs[args[0]]['currently_attached'] = method.endswith('.plug')
            return self.task()
        if method == 'Async.VIF.move':
            self.vifs[args[0]]['network'] = args[1]
            return self.task()
        if method == 'Async.VIF.destroy':
            record = self.vifs[args[0]]
            assert not record['currently_attached']
            self.vms[record['VM']]['VIFs'].remove(args[0])
            del self.vifs[args[0]]
            return self.task()
        raise AssertionError(method)


class DeviceTests(unittest.TestCase):
    def run_action(self, pool, action, **options):
        result = DeviceManager(pool).execute(action, 'guest', **options)
        pool.assert_source_unchanged(self)
        return result

    def test_add_disk_to_running_guest_creates_then_plugs(self):
        pool = DevicePool(running=True)
        report = self.run_action(pool, 'add_disk', sr='selected-sr', name='Extra data', size_gib=50)
        self.assertEqual(pool.vdis['added-data']['virtual_size'], 50*GiB)
        self.assertTrue(pool.vbds[report['resources']['VBD']]['currently_attached'])
        self.assertEqual(pool.vdis['data']['virtual_size'], str(20*GiB))

    def test_detach_keeps_disk_contents_and_removes_only_connection(self):
        pool = DevicePool(running=True)
        self.run_action(pool, 'detach_disk', vbd='disk-link')
        self.assertIn('data', pool.vdis)
        self.assertEqual(pool.vdis['data']['VBDs'], [])
        self.assertNotIn('disk-link', pool.vbds)
        self.assertNotIn('Async.VDI.destroy', [m for m, _ in pool.calls])

    def test_failed_unplug_never_destroys_connection_or_data(self):
        pool = DevicePool(running=True, fail='Async.VBD.unplug')
        with self.assertRaises(WorkflowError):
            self.run_action(pool, 'detach_disk', vbd='disk-link')
        self.assertIn('disk-link', pool.vbds)
        self.assertTrue(pool.vbds['disk-link']['currently_attached'])
        self.assertNotIn('Async.VBD.destroy', [m for m, _ in pool.calls])
        self.assertIn('data', pool.vdis)

    def test_permanent_deletion_requires_matching_uuid(self):
        pool = DevicePool()
        with self.assertRaises(WorkflowError):
            self.run_action(pool, 'delete_disk', vbd='disk-link', confirmation_uuid='wrong')
        self.assertIn('disk-link', pool.vbds)
        self.assertIn('data', pool.vdis)

    def test_permanent_deletion_only_after_connection_removed(self):
        pool = DevicePool(running=True)
        self.run_action(pool, 'delete_disk', vbd='disk-link', confirmation_uuid='disk-uuid')
        self.assertNotIn('data', pool.vdis)
        methods = [m for m, _ in pool.calls]
        self.assertLess(methods.index('Async.VBD.unplug'), methods.index('Async.VBD.destroy'))
        self.assertLess(methods.index('Async.VBD.destroy'), methods.index('Async.VDI.destroy'))

    def test_shared_or_snapshot_or_readonly_disk_cannot_be_deleted(self):
        for flag in ('sharable', 'is_a_snapshot', 'read_only'):
            pool = DevicePool()
            pool.vdis['data'][flag] = True
            with self.assertRaises(WorkflowError):
                self.run_action(pool, 'delete_disk', vbd='disk-link', confirmation_uuid='disk-uuid')
            self.assertIn('disk-link', pool.vbds)
            self.assertNotIn('Async.VDI.destroy', [m for m, _ in pool.calls])

    def test_second_disk_association_prevents_delete(self):
        pool = DevicePool()
        pool.vdis['data']['VBDs'].append('another-connection')
        with self.assertRaises(WorkflowError):
            self.run_action(pool, 'delete_disk', vbd='disk-link', confirmation_uuid='disk-uuid')
        self.assertIn('disk-link', pool.vbds)

    def test_disk_shrink_is_rejected_without_mutation(self):
        pool = DevicePool()
        with self.assertRaises(WorkflowError):
            self.run_action(pool, 'grow_disk', vbd='disk-link', size_gib=10)
        self.assertFalse(any(m.startswith('Async.') for m, _ in pool.calls))

    def test_grow_uses_server_advertised_online_capability(self):
        pool = DevicePool(running=True)
        pool.vdis['data']['allowed_operations'].append('resize_online')
        self.run_action(pool, 'grow_disk', vbd='disk-link', size_gib=30)
        self.assertEqual(pool.vdis['data']['virtual_size'], str(30*GiB))
        self.assertIn('Async.VDI.resize_online', [m for m, _ in pool.calls])

    def test_existing_unassociated_disk_attaches_without_copying_or_deleting(self):
        pool = DevicePool()
        pool.vdis['extra'] = dict(pool.vdis['data'], uuid='extra-uuid', VBDs=[])
        report = self.run_action(pool, 'attach_disk', vdi='extra')
        self.assertEqual(pool.vbds[report['resources']['VBD']]['VDI'], 'extra')
        self.assertNotIn('Async.VDI.create', [m for m, _ in pool.calls])

    def test_foreign_vbd_and_vif_are_rejected_before_mutation(self):
        pool = DevicePool()
        pool.vbds['disk-link']['VM'] = 'another-guest'
        with self.assertRaises(WorkflowError):
            self.run_action(pool, 'detach_disk', vbd='disk-link')
        pool.vifs['adapter']['VM'] = 'another-guest'
        with self.assertRaises(WorkflowError):
            self.run_action(pool, 'remove_nic', vif='adapter')
        self.assertFalse(any(m.startswith('Async.') for m, _ in pool.calls))

    def test_empty_dvd_then_iso_insert_and_eject(self):
        pool = DevicePool()
        report = self.run_action(pool, 'add_cd')
        ref = report['resources']['VBD']
        self.assertTrue(pool.vbds[ref]['empty'])
        self.run_action(pool, 'change_iso', vbd=ref, iso='iso')
        self.assertEqual(pool.vbds[ref]['VDI'], 'iso')
        self.run_action(pool, 'change_iso', vbd=ref)
        self.assertTrue(pool.vbds[ref]['empty'])
        self.assertIn('iso', pool.vdis)

    def test_non_iso_media_is_rejected_before_eject(self):
        pool = DevicePool()
        report = self.run_action(pool, 'add_cd', iso='iso')
        ref = report['resources']['VBD']
        with self.assertRaises(WorkflowError):
            self.run_action(pool, 'change_iso', vbd=ref, iso='data')
        self.assertEqual(pool.vbds[ref]['VDI'], 'iso')
        self.assertNotIn('Async.VBD.eject', [m for m, _ in pool.calls])

    def test_move_adapter_keeps_mac_uuid_and_connection(self):
        pool = DevicePool(running=True)
        original = dict(pool.vifs['adapter'])
        self.run_action(pool, 'move_nic', vif='adapter', network='new-network')
        self.assertEqual(pool.vifs['adapter'], dict(original, network='new-network'))
        self.assertNotIn('Async.VIF.destroy', [m for m, _ in pool.calls])
        self.assertNotIn('Async.VIF.unplug', [m for m, _ in pool.calls])

    def test_remove_adapter_unplugs_first(self):
        pool = DevicePool(running=True)
        self.run_action(pool, 'remove_nic', vif='adapter')
        self.assertNotIn('adapter', pool.vifs)
        methods = [m for m, _ in pool.calls]
        self.assertLess(methods.index('Async.VIF.unplug'), methods.index('Async.VIF.destroy'))

    def test_failed_adapter_unplug_does_not_remove_it(self):
        pool = DevicePool(running=True, fail='Async.VIF.unplug')
        with self.assertRaises(WorkflowError):
            self.run_action(pool, 'remove_nic', vif='adapter')
        self.assertIn('adapter', pool.vifs)
        self.assertNotIn('Async.VIF.destroy', [m for m, _ in pool.calls])

    def test_new_adapter_auto_connects_on_running_guest(self):
        pool = DevicePool(running=True)
        self.run_action(pool, 'add_nic', network='new-network')
        self.assertEqual(pool.vifs['added-vif']['network'], 'new-network')
        self.assertTrue(pool.vifs['added-vif']['currently_attached'])

    def test_multicast_or_malformed_mac_is_rejected_before_create(self):
        for mac in ('01:00:00:00:00:01', 'invalid'):
            pool = DevicePool()
            with self.assertRaises(WorkflowError):
                self.run_action(pool, 'add_nic', network='new-network', mac=mac)
            self.assertNotIn('Async.VIF.create', [m for m, _ in pool.calls])

    def test_failed_async_unplug_task_never_destroys_connection(self):
        pool = DevicePool(running=True)
        original = pool.call
        def call(method, *args):
            if method == 'Async.VBD.unplug':
                pool.calls.append((method, args))
                task = pool.task()
                pool.tasks[task] = {'status': 'failure', 'error_info': ['DEVICE_DETACH_REJECTED']}
                return task
            return original(method, *args)
        pool.call = call
        with self.assertRaises(WorkflowError):
            self.run_action(pool, 'detach_disk', vbd='disk-link')
        self.assertTrue(pool.vbds['disk-link']['currently_attached'])
        self.assertNotIn('Async.VBD.destroy', [m for m, _ in pool.calls])

    def test_remove_dvd_preserves_iso_image(self):
        pool = DevicePool()
        report = self.run_action(pool, 'add_cd', iso='iso')
        ref = report['resources']['VBD']
        self.run_action(pool, 'remove_cd', vbd=ref)
        self.assertNotIn(ref, pool.vbds)
        self.assertIn('iso', pool.vdis)
        self.assertNotIn('Async.VDI.destroy', [m for m, _ in pool.calls])

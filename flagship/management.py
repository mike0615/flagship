"""Validated management operations. Never retry a mutation or erase partial resources."""
from dataclasses import dataclass
from .workflows import WorkflowError


@dataclass(frozen=True)
class StoragePlan:
    host: str
    name: str
    description: str
    server: str
    path: str
    iso: bool = False

    def validate(self):
        if not self.host or not self.name.strip(): raise ValueError('Choose a host and enter a storage name.')
        if not self.server.strip() or any(c in self.server for c in '/\\ \t\r\n'):
            raise ValueError('Enter an NFS server hostname or IP address, without a path.')
        if not self.path.startswith('/') or any(c in self.path for c in '\r\n'):
            raise ValueError('Enter an absolute NFS export path.')

    def create(self, client):
        self.validate()
        config = ({'location': self.server + ':' + self.path, 'type': 'nfs_iso'}
                  if self.iso else {'server': self.server, 'serverpath': self.path})
        ref = client.call('SR.create', self.host, config, 0, self.name.strip(), self.description,
                          'iso' if self.iso else 'nfs', 'iso' if self.iso else 'user', True, {})
        resources = {'SR': ref}
        try:
            record = client.call('SR.get_record', ref)
            for pbd in record.get('PBDs', []):
                if not client.call('PBD.get_currently_attached', pbd):
                    raise ValueError('Storage was created but a host attachment is not active.')
        except Exception:
            raise WorkflowError('SR.create', 'Storage may exist with incomplete attachments. Inspect its UUID before retrying.', resources, []) from None
        return {'resources': resources, 'status': 'created'}


@dataclass(frozen=True)
class NetworkPlan:
    name: str
    description: str = ''
    mtu: int = 1500

    def validate(self):
        if not self.name.strip(): raise ValueError('Enter a network name.')
        if not 576 <= self.mtu <= 9216: raise ValueError('MTU must be between 576 and 9216.')

    def create(self, client):
        self.validate()
        ref = client.call('network.create', {'name_label': self.name.strip(), 'name_description': self.description,
                          'MTU': self.mtu, 'other_config': {}})
        try: client.call('network.get_record', ref)
        except Exception:
            raise WorkflowError('network.create', 'The network may exist. Inspect it before retrying.', {'network': ref}, []) from None
        return {'resources': {'network': ref}, 'status': 'created'}


def host_operation(client, ref, action):
    if action not in ('disable', 'enable', 'reboot', 'shutdown'): raise ValueError('Unsupported host action')
    record = client.call('host.get_record', ref)
    if action in ('reboot', 'shutdown'):
        if record.get('enabled'): raise ValueError('Enter maintenance mode before powering off or rebooting a host.')
        if action not in record.get('allowed_operations', []): raise ValueError('The host does not allow this action.')
        residents = record.get('resident_VMs', [])
        for vm in residents:
            r = client.call('VM.get_record', vm)
            if not r.get('is_control_domain') and r.get('power_state') != 'Halted':
                raise ValueError('Shut down or migrate all resident guests first.')
    if action == 'disable':
        # Disabling placement alone is not evacuation. Do not silently call this completed maintenance.
        for vm in record.get('resident_VMs', []):
            r = client.call('VM.get_record', vm)
            if not r.get('is_control_domain') and r.get('power_state') != 'Halted':
                raise ValueError('Migrate or halt resident guests before entering maintenance mode.')
    return client.call('Async.host.' + action, ref)


def edit_identity(client, cls, ref, name, description):
    if cls not in ('host', 'VM', 'SR', 'network', 'pool'): raise ValueError('Unsupported object type')
    if not name.strip(): raise ValueError('Name cannot be empty.')
    client.call(cls + '.get_record', ref)
    resources = {cls: ref}
    try:
        client.call(cls + '.set_name_label', ref, name.strip())
        client.call(cls + '.set_name_description', ref, description)
    except Exception:
        raise WorkflowError(cls + '.set_name_description', 'Some properties may have changed. Refresh before retrying.', resources, []) from None
    return {'resources': resources, 'status': 'updated'}

"""Task-confirmed portable OVA and qcow2 transfers through native qemu-img."""
import math
import os
from pathlib import Path
import tempfile
from .images import Appliance, Converter, digest, inspect_header, read_ova, regular, write_ova
from .transfers import XVATransfer
from .workflows import VMPlan, GiB, MiB, NULL, WorkflowError


class PortableTransfer(XVATransfer):
    def disk_task(self,operation,ref):
        task=self.call('task.create','Portable disk '+operation,'Flagship portable image transfer')
        record=self.call('task.get_record',task)
        self.tasks.append({'method':'HTTP.disk_'+operation,'task':task,'uuid':record.get('uuid'),'status':'pending'})
        self.op_id=self.client.journal.intent('HTTP.disk_'+operation,self.client.affected_objects('VDI.'+operation,(ref,)))
        self.client.task_origins[task]=(self.op_id,'HTTP.disk_'+operation)
        self.deadline=self.clock()+self.timeout; self.announce()
        return task

    def export_disk(self,ref,target):
        record=self.call('VDI.get_record',ref)
        task=self.disk_task('export',ref); self.stage='Downloading portable disk'; self.announce()
        response=self.transport(self.client,'GET','/export_raw_vdi',{'vdi':ref,'format':'vhd','task_id':task},checkpoint=self.checkpoint)
        count=0
        try:
            with open(target,'xb') as out:
                os.chmod(target,0o600)
                for block in response.chunks():
                    self.checkpoint(); count+=len(block)
                    if count>int(record['virtual_size'])+GiB: raise ValueError('Disk response exceeds its declared capacity.')
                    out.write(block); self.observe_transfer(self.transferred+len(block))
                out.flush(); os.fsync(out.fileno())
            if not count: raise ValueError('The server returned an empty disk.')
            self.wait_task(task)
            self.client.journal.outcome(self.op_id,'returned')
        finally: response.close()
        return target

    def import_disk(self,path,ref):
        path=regular(path); task=self.disk_task('import',ref)
        self.stage='Uploading converted disk'; self.announce()
        response=None
        try:
            with path.open('rb') as source:
                response=self.transport(self.client,'PUT','/import_raw_vdi',{'vdi':ref,'format':'vhd','task_id':task},source=source,size=path.stat().st_size,checkpoint=self.checkpoint,progress=self.observe_transfer)
                received=0
                for block in response.chunks():
                    self.checkpoint(); received+=len(block)
                    if received>MiB: raise ValueError('Disk import response is too large.')
            self.wait_task(task)
            self.client.journal.outcome(self.op_id,'returned',result_ref=ref)
        finally:
            if response: response.close()

    def export_portable(self,vm,filename,fmt,disk_ref=None):
        self.output=Path(filename).absolute()
        try:
            if fmt not in ('ova','qcow2'): raise ValueError('Choose OVA or qcow2.')
            if self.output.exists() or self.output.is_symlink(): raise ValueError('Choose a new output filename.')
            machine=self.call('VM.get_record',vm)
            if machine.get('is_control_domain') or machine.get('power_state')!='Halted':
                raise ValueError('Shut down the VM before exporting portable images.')
            disks=[]
            for link in machine.get('VBDs',[]):
                device=self.call('VBD.get_record',link)
                if device.get('type')=='Disk' and not device.get('empty') and device.get('VDI') not in ('',None,NULL):
                    disks.append((int(device.get('userdevice',0)),device['VDI']))
            disks.sort()
            if fmt=='qcow2':
                if disk_ref:
                    if disk_ref not in [ref for _,ref in disks]: raise ValueError('Selected disk does not belong to this VM.')
                    disks=[pair for pair in disks if pair[1]==disk_ref]
                if len(disks)!=1: raise ValueError('Select one virtual disk for qcow2 export; use OVA for all disks.')
            if not disks: raise ValueError('This VM has no virtual disks.')
            self.resources['VM']=vm
            with tempfile.TemporaryDirectory(prefix='.flagship-export-',dir=self.output.parent) as work:
                work=Path(work); images=[]; converter=Converter(self.checkpoint)
                for i,(_,ref) in enumerate(disks,1):
                    record=self.call('VDI.get_record',ref); self.resources['VDI']=ref
                    source=self.export_disk(ref,work/('disk'+str(i)+'.vhd'))
                    self.stage='Converting disk '+str(i); self.deadline=None; self.announce()
                    target=work/(('disk'+str(i)+'.vmdk') if fmt=='ova' else 'disk.qcow2')
                    converter.convert(source,'vpc',target,'vmdk' if fmt=='ova' else 'qcow2')
                    images.append((target,'vmdk' if fmt=='ova' else 'qcow2',int(record['virtual_size'])))
                target=work/('appliance.ova' if fmt=='ova' else 'disk.qcow2')
                if fmt=='ova':
                    firmware=machine.get('HVM_boot_params',{}).get('firmware','bios')
                    write_ova(target,Appliance(machine.get('name_label','Virtual machine'),int(machine.get('VCPUs_at_startup',2)),max(128,int(machine.get('memory_dynamic_max',2048*MiB))//MiB),firmware,images,len(machine.get('VIFs',[]))))
                self.checkpoint(); target.chmod(0o600)
                with target.open('rb') as handle: os.fsync(handle.fileno())
                self.sha256=digest(target)
                os.link(target,self.output,follow_symlinks=False); self.sync_directory(self.output.parent)
            self.stage=fmt.upper()+' export completed'; self.announce()
            return self.report()
        except Exception as exc: raise self.failed(exc) from None

    def import_portable(self,filename,sr,network,template,name=None,cpus=None,memory_mib=None,firmware=None):
        self.source_path=regular(filename)
        try:
            self.stage='Inspecting portable image'; self.announce()
            with tempfile.TemporaryDirectory(prefix='flagship-import-') as work:
                work=Path(work); converter=Converter(self.checkpoint)
                if self.source_path.suffix.lower()=='.ova':
                    appliance=read_ova(self.source_path,work,self.checkpoint)
                elif self.source_path.suffix.lower()=='.qcow2':
                    size=inspect_header(self.source_path,'qcow2')
                    appliance=Appliance(self.source_path.stem,2,2048,'bios',[(self.source_path,'qcow2',size)])
                else: raise ValueError('Choose an OVA or qcow2 file.')
                if name: appliance.name=name.strip()
                if cpus is not None: appliance.cpus=cpus
                if memory_mib is not None: appliance.memory_mib=memory_mib
                if firmware is not None: appliance.firmware=firmware
                appliance.validate()
                # Complete all local parsing/conversion before creating server resources.
                converted=[]
                for i,(path,fmt,size) in enumerate(appliance.disks):
                    self.stage='Converting import disk '+str(i+1); self.announce()
                    target=converter.convert(path,fmt,work/('import'+str(i)+'.vhd'),'vpc')
                    converted.append((target,size))
                size=converted[0][1]
                plan=VMPlan(template,appliance.name,sr,network,appliance.cpus,appliance.memory_mib,max(1,math.ceil(size/GiB)),boot_mode=appliance.firmware,disk_bytes=size)
                self.create(plan)
                vm=self.resources['VM']; first_disk=self.resources['VDI']
                for i,(path,size) in enumerate(converted):
                    if i==0: disk=first_disk
                    else:
                        disk=self.async_call('VDI.create',{'name_label':appliance.name+' disk '+str(i+1),'name_description':'Imported portable disk','SR':sr,'virtual_size':size,'type':'user','sharable':False,'read_only':False,'other_config':{},'xenstore_data':{},'sm_config':{}},reference=True)
                        self.resources['VDI']=disk; self.call('VDI.get_record',disk); self.add_vbd(vm,disk,'Disk')
                    self.import_disk(path,disk)
                machine=self.call('VM.get_record',vm)
                if appliance.networks==0:
                    for vif in machine.get('VIFs',[]): self.async_call('VIF.destroy',vif)
                for i in range(1,appliance.networks):
                    slots=self.call('VM.get_allowed_VIF_devices',vm)
                    if not slots: raise ValueError('No network interface slots remain.')
                    self.async_call('VIF.create',{'VM':vm,'network':network,'device':str(slots[0]),'MAC':'','MTU':1500,'other_config':{},'qos_algorithm_type':'','qos_algorithm_params':{},'locking_mode':'network_default'},reference=True)
                self.sha256=digest(self.source_path)
            self.stage='Portable VM imported; review hardware before starting'; self.announce()
            return self.report()
        except Exception as exc:
            if isinstance(exc,WorkflowError):
                self.resources.update(exc.resources)
            raise self.failed(exc) from None

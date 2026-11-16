"""Portable image selection, preflight, hardware review and serialized transfers."""
import math
from pathlib import Path
import tempfile
import threading
from tkinter import filedialog, messagebox
from .dialogs import choose_resource
from .images import Appliance, inspect_header, read_ova


class PortableUI:
    def export_vm(self):
        if not self.client or self.busy: return
        cls,ref=self.selected() or ('','')
        if cls!='VM': return
        if self.records['VM'][ref].get('power_state')!='Halted':
            messagebox.showinfo('Export virtual machine','Shut down the VM before exporting.'); return
        path=filedialog.asksaveasfilename(parent=self.root,title='Export virtual machine',defaultextension='.ova',
            filetypes=[('Open Virtual Appliance','*.ova'),('QEMU disk image','*.qcow2'),('Xen virtual appliance','*.xva')])
        if not path: return
        fmt=Path(path).suffix.lower().lstrip('.')
        if fmt not in ('ova','qcow2','xva'): messagebox.showerror('Export format','Choose .ova, .qcow2 or .xva.'); return
        disk=None
        details='Exports the VM configuration and all attached disks.'
        if fmt=='qcow2':
            disks={v['VDI']:self.records.get('VDI',{}).get(v['VDI'],{'name_label':v['VDI']}) for v in self.records.get('VBD',{}).values()
                   if v.get('VM')==ref and v.get('type')=='Disk' and v.get('VDI') not in (None,'','OpaqueRef:NULL')}
            if not disks: messagebox.showinfo('Export disk','This VM has no disks.'); return
            if len(disks)==1: disk=next(iter(disks))
            else:
                ok,disk=choose_resource(self.root,'Disk to export as qcow2',disks)
                if not ok: return
            details='Exports one virtual disk: '+disks[disk].get('name_label','Disk')+'.\nChoose CPU, memory and firmware when importing this disk.'
        if not messagebox.askyesno('Review '+fmt.upper()+' export',details+'\n\nDestination: '+path+'\nExisting files will not be overwritten.'): return
        if fmt=='xva': self.start_transfer('export',path,ref)
        else: self.start_portable('export',path,ref,fmt=fmt,disk_ref=disk)

    def import_vm(self):
        if not self.client or self.busy: return
        path=filedialog.askopenfilename(parent=self.root,title='Import virtual machine or disk',
            filetypes=[('Supported images','*.ova *.qcow2 *.xva'),('Open Virtual Appliance','*.ova'),('QEMU disk image','*.qcow2'),('Xen virtual appliance','*.xva')])
        if not path: return
        fmt=Path(path).suffix.lower()
        storage={ref:r for ref,r in self.records.get('SR',{}).items() if r.get('content_type')=='user' and 'vdi_create' in r.get('allowed_operations',[])}
        ok,sr=choose_resource(self.root,'Destination storage',storage)
        if not ok: return
        ok,network=choose_resource(self.root,'Destination network',self.records.get('network',{}))
        if not ok: return
        if fmt=='.xva':
            if messagebox.askyesno('Review XVA import','Import '+path+'?\nThe imported VM stays halted. Partial resources may remain on failure.'):
                self.start_transfer('import',path,sr,network)
            return
        if fmt not in ('.ova','.qcow2'): messagebox.showerror('Image format','Choose an OVA, qcow2 or XVA file.'); return
        templates={ref:r for ref,r in self.records.get('VM',{}).items() if r.get('is_a_template') and not r.get('is_a_snapshot') and r.get('HVM_boot_policy')}
        template=next((ref for ref,r in templates.items() if r.get('name_label')=='Other install media'),None)
        if template is None:
            ok,template=choose_resource(self.root,'Import hardware template',templates)
            if not ok: return
        def inspect():
            if fmt=='.qcow2': return Appliance(Path(path).stem,2,2048,'bios',[(path,'qcow2',inspect_header(path,'qcow2'))])
            with tempfile.TemporaryDirectory(prefix='flagship-preflight-') as work: return read_ova(path,work,metadata_only=True)
        def done(appliance):
            self.review_portable_import(path,sr,network,template,appliance)
        self.submit(inspect,done,'Inspecting image hardware…')

    def review_portable_import(self,path,sr,network,template,appliance):
        def review(values):
            name=values['Name'].strip(); cpus=int(values['vCPUs']); memory=int(values['Memory (MiB)'])
            plan=Appliance(name,cpus,memory,values['Firmware'],appliance.disks,appliance.networks); plan.validate()
            return {'name':name,'cpus':cpus,'memory_mib':memory,'firmware':plan.firmware}, 'Import '+name+'\nDisks: '+str(len(plan.disks))+'\nvCPUs: '+str(cpus)+'\nMemory: '+str(memory)+' MiB\nFirmware: '+plan.firmware+'\nAll adapters use the selected destination network.\nThe VM stays halted; review guest storage/network drivers before starting.'
        # This form performs its own reviewed mutation submission.
        from .portable import PortableTransfer
        def execute(options):
            self.workflow_stop=threading.Event(); self.workflow_label='Portable import'
            transfer=PortableTransfer(self.client,stop=self.workflow_stop,progress=self.publish_workflow_progress)
            try: return transfer.import_portable(path,sr,network,template,**options)
            finally: self.workflow_stop=None
        return self.management_form('Import '+str(len(appliance.disks))+' disk(s)',[
            ('Name',appliance.name,None),('vCPUs',str(appliance.cpus),None),('Memory (MiB)',str(appliance.memory_mib),None),
            ('Firmware',appliance.firmware,['bios','uefi'])],review,execute)

    def start_portable(self,operation,path,ref,**options):
        from .portable import PortableTransfer
        self.workflow_stop=threading.Event(); self.workflow_label=options.get('fmt','Portable').upper()+' '+operation
        self.last_workflow_report=None
        transfer=PortableTransfer(self.client,stop=self.workflow_stop,progress=self.publish_workflow_progress)
        def done(report):
            self.workflow_stop=None; self.last_workflow_report=report
            messagebox.showinfo('Transfer complete',report['stage']); self.refresh()
        self.submit(lambda:transfer.export_portable(ref,path,**options),done,self.workflow_label+'…',mutation=True)

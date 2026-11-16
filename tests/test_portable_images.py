import copy
import io
import os
from pathlib import Path
import shutil
import struct
import tarfile
import tempfile
import unittest
from flagship.images import Appliance,Converter,inspect_header,read_ova,write_ova
from flagship.portable import PortableTransfer
from flagship.api import Client
from flagship.journal import OperationJournal
from test_workflows import Pool


@unittest.skipUnless(shutil.which('qemu-img'),'requires native qemu-img')
class ImageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.base=Path(self.tmp.name)
        self.raw=self.base/'source.raw'
        with self.raw.open('wb') as f:
            f.write(b'Flagship portable roundtrip fixture'); f.seek(4*1024*1024); f.write(b'second nonzero block'); f.truncate(16*1024*1024)
        self.converter=Converter()

    def tearDown(self): self.tmp.cleanup()

    def test_real_qcow2_roundtrip_matches_disk_bytes(self):
        target=self.converter.convert(self.raw,'raw',self.base/'disk.qcow2','qcow2')
        self.assertEqual(inspect_header(target,'qcow2'),16*1024**2)
        self.converter.run('compare','-f','raw','-F','qcow2',self.raw,target)

    def test_real_ova_preserves_hardware_manifest_and_disk_content(self):
        target=self.converter.convert(self.raw,'raw',self.base/'disk1.vmdk','vmdk')
        ova=self.base/'test.ova'; write_ova(ova,Appliance('Portable guest',3,1024,'uefi',[(target,'vmdk',16*1024**2)],2))
        destination=self.base/'out'; destination.mkdir()
        image=read_ova(ova,destination)
        self.assertEqual((image.name,image.cpus,image.memory_mib,image.firmware,image.networks),('Portable guest',3,1024,'uefi',2))
        self.converter.run('compare','-f','raw','-F','vmdk',self.raw,image.disks[0][0])
        with tarfile.open(ova) as archive: self.assertEqual(archive.getnames()[0],'appliance.ovf')

    def test_backing_file_qcow2_is_refused_before_qemu_reads_it(self):
        target=self.converter.convert(self.raw,'raw',self.base/'disk.qcow2','qcow2')
        with target.open('r+b') as f: f.seek(8); f.write(struct.pack('>QI',512,9))
        with self.assertRaises(ValueError): inspect_header(target,'qcow2')

    def test_external_data_qcow2_is_refused(self):
        target=self.converter.convert(self.raw,'raw',self.base/'disk.qcow2','qcow2')
        with target.open('r+b') as f: f.seek(72); f.write(struct.pack('>Q',4))
        with self.assertRaises(ValueError): inspect_header(target,'qcow2')

    def test_traversal_and_link_ova_members_never_extract(self):
        for name,kind in (('../escape',tarfile.REGTYPE),('link',tarfile.SYMTYPE)):
            ova=self.base/'bad.ova'
            with tarfile.open(ova,'w') as archive:
                member=tarfile.TarInfo(name);member.type=kind;archive.addfile(member,io.BytesIO())
            with self.assertRaises(ValueError): read_ova(ova,self.base)
            self.assertFalse((self.base.parent/'escape').exists())

    def test_manifest_mismatch_is_rejected(self):
        ova=self.base/'bad.ova'
        xml=b'<ovf:Envelope xmlns:ovf="http://schemas.dmtf.org/ovf/envelope/1"><ovf:References/><ovf:DiskSection/><ovf:VirtualSystem ovf:id="vm"/></ovf:Envelope>'
        with tarfile.open(ova,'w') as archive:
            for name,data in [('test.ovf',xml),('test.mf',b'SHA256(test.ovf)= '+b'0'*64)]:
                m=tarfile.TarInfo(name);m.size=len(data);archive.addfile(m,io.BytesIO(data))
        with self.assertRaisesRegex(ValueError,'checksum mismatch'): read_ova(ova,self.base)


class PortablePool(Pool):
    def __init__(self):
        super().__init__(); self.vms['template']['HVM_boot_policy']='BIOS order';self.unique=0

    def call(self,method,*args):
        if method=='task.create': return self.task()
        if method=='VM.set_HVM_boot_params': self.calls.append((method,args));self.vms[args[0]]['HVM_boot_params']=dict(args[1]);return ''
        if method=='Async.VDI.create':
            self.calls.append((method,args));self.unique+=1;ref='portable-disk-'+str(self.unique);self.vdis[ref]=dict(args[0],uuid=ref);return self.task(ref)
        if method=='Async.VBD.create':
            self.calls.append((method,args));self.unique+=1;ref='portable-vbd-'+str(self.unique);self.vbds[ref]=dict(args[0]);self.vms[args[0]['VM']]['VBDs'].append(ref);return self.task(ref)
        return super().call(method,*args)


class Reply:
    def __init__(self,data): self.data=data
    def chunks(self): yield self.data
    def close(self): pass


@unittest.skipUnless(shutil.which('qemu-img'),'requires native qemu-img')
class PortableWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
        self.journal=OperationJournal(self.base/'journals');self.journal.begin('Portable test')
        self.pool=PortablePool();self.client=Client('https://pool.test',journal=self.journal);self.client.session='test-session'
        self.client._rpc=lambda name,session,*args:self.pool.call(name,*args)
        self.source=self.base/'source.raw';self.source.write_bytes(b'fixture');self.source.touch()
        with self.source.open('r+b') as f:f.truncate(16*1024**2)
        self.qcow=Converter().convert(self.source,'raw',self.base/'source.qcow2','qcow2')
        self.uploads=[]

    def tearDown(self): self.journal.close();self.tmp.cleanup()

    def transport(self,client,method,path,parameters,**options):
        self.assertEqual((method,path),('PUT','/import_raw_vdi'))
        self.assertEqual(parameters['format'],'vhd')
        data=options['source'].read();self.assertEqual(len(data),options['size']);self.uploads.append(data)
        return Reply(b'')

    def test_qcow_import_creates_new_halted_vm_and_keeps_exact_virtual_capacity(self):
        original=copy.deepcopy(self.pool.vms['template'])
        engine=PortableTransfer(self.client,transport=self.transport)
        report=engine.import_portable(self.qcow,'selected-sr','selected-network','template')
        self.assertEqual(self.pool.vms[report['resources']['VM']]['power_state'],'Halted')
        self.assertEqual(self.pool.vdis[report['resources']['VDI']]['virtual_size'],16*1024**2)
        self.assertEqual(original,self.pool.vms['template']);self.assertEqual(len(self.uploads),1)
        transferred=self.base/'uploaded.vhd';transferred.write_bytes(self.uploads[0])
        import json,subprocess
        metadata=json.loads(subprocess.check_output(['qemu-img','info','-f','vpc','--output=json',str(transferred)]))
        self.assertEqual(metadata['virtual-size'],16*1024**2)
        Converter().run('compare','-f','raw','-F','vpc',self.source,transferred)

    def test_invalid_disk_does_not_create_any_server_resource(self):
        bad=self.base/'bad.qcow2';bad.write_bytes(b'invalid')
        with self.assertRaises(Exception): PortableTransfer(self.client,transport=self.transport).import_portable(bad,'sr','net','template')
        self.assertEqual(self.pool.calls,[]);self.assertFalse(self.uploads)

    def test_ova_import_preserves_two_disks_without_touching_template(self):
        disks=[]
        for i in (1,2):
            path=Converter().convert(self.source,'raw',self.base/('disk'+str(i)+'.vmdk'),'vmdk');disks.append((path,'vmdk',16*1024**2))
        ova=self.base/'source.ova';write_ova(ova,Appliance('Two disk guest',2,512,'bios',disks))
        report=PortableTransfer(self.client,transport=self.transport).import_portable(ova,'selected-sr','selected-network','template')
        vm=self.pool.vms[report['resources']['VM']]
        disk_links=[self.pool.vbds[v] for v in vm['VBDs'] if self.pool.vbds[v]['type']=='Disk']
        self.assertEqual(len(disk_links),2);self.assertEqual(len(self.uploads),2)

"""Local portable images: bounded OVF parsing and self-contained QEMU conversions."""
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import subprocess
import tarfile
import time
import xml.etree.ElementTree as ET
from urllib.parse import unquote

OVF='http://schemas.dmtf.org/ovf/envelope/1'
RASD='http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_ResourceAllocationSettingData'
VSSD='http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_VirtualSystemSettingData'
VMW='http://www.vmware.com/schema/ovf'
MAX_DISK=2*1024**4
MAX_XML=8*1024**2


def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()


def regular(path):
    path=Path(path).absolute()
    if not stat.S_ISREG(path.lstat().st_mode): raise ValueError('Choose a regular local image file, without symlinks.')
    return path


def inspect_header(path,fmt):
    path=regular(path)
    with path.open('rb') as f:
        header=f.read(512)
        if fmt=='qcow2':
            if len(header)<104 or header[:4]!=b'QFI\xfb': raise ValueError('Not a qcow2 image.')
            version=struct.unpack_from('>I',header,4)[0]
            backing,length=struct.unpack_from('>QI',header,8)
            size=struct.unpack_from('>Q',header,24)[0]
            if version not in (2,3) or backing or length: raise ValueError('Flatten qcow2 backing chains before importing.')
            if struct.unpack_from('>I',header,32)[0]: raise ValueError('Encrypted disk images are unsupported.')
            if version==3 and struct.unpack_from('>Q',header,72)[0]&0b1110:
                raise ValueError('External-data, corrupt or compressed-extension qcow2 images are unsupported.')
        elif fmt=='vmdk':
            if header[:4]!=b'KDMV' or len(header)<512: raise ValueError('Use a monolithic sparse or streamOptimized VMDK image.')
            offset,count=struct.unpack_from('<QQ',header,28)
            size=struct.unpack_from('<Q',header,12)[0]*512
            if not offset or not 0<count<=2048 or (offset+count)*512>path.stat().st_size:
                raise ValueError('Invalid embedded VMDK descriptor.')
            f.seek(offset*512); desc=f.read(count*512).decode('ascii',errors='strict').rstrip('\x00')
            if re.search(r'parentFileNameHint\s*=',desc,re.I): raise ValueError('Flatten VMDK parent chains before importing.')
            extents=re.findall(r'^\s*(?:RW|RDONLY|NOACCESS)\s+\d+\s+(\S+)\s+"([^"]+)"',desc,re.M)
            if len(extents)!=1 or extents[0][0]!='SPARSE' or extents[0][1]!=path.name:
                raise ValueError('External or split VMDK extents are unsupported; use a self-contained OVA.')
        else: raise ValueError('Unsupported portable image format.')
    if not 0<size<=MAX_DISK: raise ValueError('Disk virtual size must be positive and at most 2 TiB.')
    return size


class Converter:
    def __init__(self,checkpoint=lambda:None): self.checkpoint=checkpoint

    def run(self,*args):
        binary=shutil.which('qemu-img')
        if not binary: raise ValueError('Install the native qemu-img package to use OVA and qcow2 images.')
        # No shell, remote image protocols, backing chains or guest execution.
        with __import__('tempfile').TemporaryFile() as error:
            process=subprocess.Popen([binary,*map(str,args)],stdout=subprocess.DEVNULL,stderr=error)
            try:
                deadline=time.monotonic()+7200
                while process.poll() is None:
                    self.checkpoint()
                    if time.monotonic()>deadline: raise ValueError('Image conversion timed out.')
                    time.sleep(.1)
                if process.returncode: raise ValueError('qemu-img could not convert this image. Check format, available space and image consistency.')
            finally:
                if process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired: process.kill(); process.wait()

    def convert(self,source,fmt,target,outfmt):
        source=regular(source); target=Path(target)
        if target.exists() or target.is_symlink(): raise ValueError('Conversion target already exists.')
        options=['-o','subformat=streamOptimized,compat6'] if outfmt=='vmdk' else ['-o','force_size=on'] if outfmt=='vpc' else []
        self.run('convert','-f',fmt,'-O',outfmt,*options,source,target)
        target.chmod(0o600)
        return target


@dataclass
class Appliance:
    name: str
    cpus: int
    memory_mib: int
    firmware: str
    disks: list
    networks: int=1

    def validate(self):
        if not self.name.strip() or not 1<=self.cpus<=1024 or not 128<=self.memory_mib<=1048576:
            raise ValueError('Unsupported appliance CPU or memory configuration.')
        if self.firmware not in ('bios','uefi'): raise ValueError('Unsupported firmware.')
        if not 1<=len(self.disks)<=32: raise ValueError('Select a single-VM appliance with 1 to 32 disks.')
        if not 0<=self.networks<=8: raise ValueError('Appliance has too many network interfaces.')


def safe_member(name):
    p=PurePosixPath(name)
    if not name or p.is_absolute() or '..' in p.parts or '\\' in name or '\x00' in name or ':' in name:
        raise ValueError('OVA contains an unsafe member path.')
    return p


def read_ova(path,directory,checkpoint=lambda:None,metadata_only=False):
    """Extract only referenced regular disks; never tar.extract or follow a link."""
    path=regular(path); directory=Path(directory)
    with tarfile.open(path,'r:') as archive:
        members={}
        for member in archive:
            checkpoint(); safe_member(member.name)
            if member.name in members or not member.isfile() or member.size<0:
                raise ValueError('OVA must contain unique regular files, without links or directories.')
            if len(members)>=128: raise ValueError('OVA has too many members.')
            members[member.name]=member
        descriptors=[m for n,m in members.items() if n.lower().endswith('.ovf')]
        if len(descriptors)!=1 or descriptors[0].size>MAX_XML: raise ValueError('OVA requires one bounded OVF descriptor.')
        descriptor=descriptors[0]; xml=archive.extractfile(descriptor).read(MAX_XML+1)
        if b'<!DOCTYPE' in xml.upper() or b'<!ENTITY' in xml.upper(): raise ValueError('XML entities are unsupported.')
        try: root=ET.fromstring(xml)
        except ET.ParseError: raise ValueError('Invalid OVF descriptor.') from None
        ns={'o':OVF,'r':RASD,'v':VMW}
        systems=root.findall('.//o:VirtualSystem',ns)
        if len(systems)!=1 or root.find('.//o:VirtualSystemCollection',ns) is not None:
            raise ValueError('Import one virtual machine at a time.')
        vs=systems[0]
        name=vs.findtext('o:Name','Imported appliance',ns)
        cpu=2; memory=2048; network_count=0
        for item in vs.findall('.//o:Item',ns):
            kind=item.findtext('r:ResourceType','',ns); quantity=item.findtext('r:VirtualQuantity','0',ns)
            if kind=='3': cpu=int(quantity)
            elif kind=='4':
                units=item.findtext('r:AllocationUnits','byte * 2^20',ns).lower().replace(' ','')
                factors={'byte*2^20':1,'megabyte':1,'megabytes':1,'byte*2^30':1024,'byte':1/1048576}
                if units not in factors: raise ValueError('Unsupported OVF memory units.')
                memory=math.ceil(int(quantity)*factors[units])
            elif kind=='10': network_count+=1
        firmware='bios'
        for config in vs.findall('.//v:Config',ns):
            key=config.get('{'+VMW+'}key',config.get('key',''))
            value=config.get('{'+VMW+'}value',config.get('value',''))
            if key in ('uefi.secureBoot.enabled','secureBootEnabled') and value.lower() in ('true','1'):
                raise ValueError('This appliance requires Secure Boot, which this importer cannot configure.')
            if config.get('{'+VMW+'}key',config.get('key'))=='firmware':
                firmware=config.get('{'+VMW+'}value',config.get('value','bios')).lower().replace('efi','uefi')
                if firmware=='uuefi': firmware='uefi'
        files={f.get('{'+OVF+'}id'):f.get('{'+OVF+'}href','') for f in root.findall('o:References/o:File',ns)}
        disk_records={d.get('{'+OVF+'}diskId'):d for d in root.findall('o:DiskSection/o:Disk',ns)}
        ordered=[]
        for item in vs.findall('.//o:Item',ns):
            if item.findtext('r:ResourceType','',ns)=='17':
                resource=item.findtext('r:HostResource','',ns)
                disk_id=resource.rsplit('/',1)[-1]
                if disk_id not in disk_records: raise ValueError('OVF disk reference is missing.')
                ordered.append(disk_records[disk_id])
        if not ordered: ordered=list(disk_records.values())
        if len({d.get('{'+OVF+'}diskId') for d in ordered})!=len(ordered): raise ValueError('Duplicate disk attachments are unsupported.')
        manifests=[m for n,m in members.items() if n.lower().endswith('.mf')]
        expected={}
        for manifest in manifests:
            if manifest.size>MAX_XML: raise ValueError('OVA manifest is too large.')
            for line in archive.extractfile(manifest).read().decode('utf-8-sig').splitlines():
                if not line.strip(): continue
                match=re.fullmatch(r'(SHA1|SHA256)\((.+)\)\s*=\s*([0-9a-fA-F]+)',line.strip())
                if not match: raise ValueError('Unsupported or malformed OVA manifest.')
                algorithm,filename,checksum=match.groups(); safe_member(filename)
                if filename not in members: raise ValueError('Manifest refers to a missing member.')
                expected[filename]=(algorithm.lower(),checksum.lower())
        for filename,(algorithm,checksum) in ({} if metadata_only else expected).items():
            h=hashlib.new(algorithm)
            stream=archive.extractfile(members[filename])
            for block in iter(lambda:stream.read(1024*1024),b''): checkpoint(); h.update(block)
            if h.hexdigest()!=checksum: raise ValueError('OVA manifest checksum mismatch.')
        paths=[]
        for i,disk in enumerate(ordered):
            href=unquote(files.get(disk.get('{'+OVF+'}fileRef'),''))
            if not href: raise ValueError('Blank or external disks are unsupported.')
            member_name=str(PurePosixPath(descriptor.name).parent/safe_member(href))
            if member_name not in members or not member_name.lower().endswith(('.vmdk','.qcow2')):
                raise ValueError('OVA references a missing or unsupported disk image.')
            member=members[member_name]
            if member.size>MAX_DISK: raise ValueError('OVA disk exceeds supported size.')
            if metadata_only:
                units=disk.get('{'+OVF+'}capacityAllocationUnits','byte').lower().replace(' ','')
                factor={'byte':1,'byte*2^10':1024,'byte*2^20':1024**2,'byte*2^30':1024**3}.get(units)
                if factor is None: raise ValueError('Unsupported OVF disk capacity units.')
                size=int(disk.get('{'+OVF+'}capacity','0'))*factor
                if not 0<size<=MAX_DISK: raise ValueError('Unsupported disk capacity.')
                paths.append((member_name,'vmdk' if member_name.lower().endswith('.vmdk') else 'qcow2',size))
                continue
            # Preserve basename for self-contained VMDK extent validation, isolate every disk.
            target_dir=directory/str(i); target_dir.mkdir(mode=0o700)
            target=target_dir/PurePosixPath(member_name).name
            with target.open('xb') as out, archive.extractfile(member) as source:
                target.chmod(0o600)
                while True:
                    checkpoint(); block=source.read(1024*1024)
                    if not block: break
                    out.write(block)
            fmt='vmdk' if member_name.lower().endswith('.vmdk') else 'qcow2'
            size=inspect_header(target,fmt)
            paths.append((target,fmt,size))
        appliance=Appliance(name,cpu,memory,firmware,paths,network_count)
        appliance.validate(); return appliance


def write_ova(path,appliance):
    appliance.validate()
    if any(Path(disk).stat().st_size>0o77777777777 for disk,_,_ in appliance.disks):
        raise ValueError('This OVA compatibility profile requires each converted VMDK below 8 GiB; export the disk as qcow2 instead.')
    for prefix,uri in [('ovf',OVF),('rasd',RASD),('vssd',VSSD),('vmw',VMW)]: ET.register_namespace(prefix,uri)
    tag=lambda name:'{'+OVF+'}'+name
    attr=lambda **kw:{tag(k):str(v) for k,v in kw.items()}
    root=ET.Element(tag('Envelope')); refs=ET.SubElement(root,tag('References'))
    section=ET.SubElement(root,tag('DiskSection')); ET.SubElement(section,tag('Info')).text='Virtual disks'
    for i,(disk,_,size) in enumerate(appliance.disks,1):
        ET.SubElement(refs,tag('File'),attr(id='file'+str(i),href='disk'+str(i)+'.vmdk',size=Path(disk).stat().st_size))
        ET.SubElement(section,tag('Disk'),attr(diskId='disk'+str(i),fileRef='file'+str(i),capacity=size,capacityAllocationUnits='byte',format='http://www.vmware.com/interfaces/specifications/vmdk.html#streamOptimized'))
    networks=ET.SubElement(root,tag('NetworkSection')); ET.SubElement(networks,tag('Info')).text='Logical networks'
    network=ET.SubElement(networks,tag('Network'),attr(name='VM Network')); ET.SubElement(network,tag('Description')).text='Choose a destination network during import'
    vs=ET.SubElement(root,tag('VirtualSystem'),attr(id='virtual-machine')); ET.SubElement(vs,tag('Info')).text='Portable virtual machine'; ET.SubElement(vs,tag('Name')).text=appliance.name
    os_section=ET.SubElement(vs,tag('OperatingSystemSection'),attr(id=1)); ET.SubElement(os_section,tag('Info')).text='Guest operating system'; ET.SubElement(os_section,tag('Description')).text='Other'
    hw=ET.SubElement(vs,tag('VirtualHardwareSection')); ET.SubElement(hw,tag('Info')).text='Virtual hardware'
    system=ET.SubElement(hw,tag('System'))
    for k,v in [('ElementName','Virtual hardware'),('InstanceID','0'),('VirtualSystemIdentifier',appliance.name),('VirtualSystemType','vmx-13')]: ET.SubElement(system,'{'+VSSD+'}'+k).text=v
    def item(instance,kind,label,**fields):
        node=ET.SubElement(hw,tag('Item'))
        for k,v in dict(ElementName=label,InstanceID=instance,ResourceType=kind,**fields).items(): ET.SubElement(node,'{'+RASD+'}'+k).text=str(v)
    item('1','3','Virtual CPUs',VirtualQuantity=appliance.cpus)
    item('2','4','Memory',AllocationUnits='byte * 2^20',VirtualQuantity=appliance.memory_mib)
    item('3','6','SCSI controller',ResourceSubType='lsilogic',Address=0)
    for i in range(len(appliance.disks)): item(str(4+i),'17','Hard disk '+str(i+1),Parent=3,AddressOnParent=i,HostResource='ovf:/disk/disk'+str(i+1))
    for i in range(appliance.networks): item(str(100+i),'10','Network adapter '+str(i+1),Connection='VM Network',ResourceSubType='E1000',AutomaticAllocation='true',AddressOnParent=i)
    ET.SubElement(vs,'{'+VMW+'}Config',{tag('required'):'false','{'+VMW+'}key':'firmware','{'+VMW+'}value':'efi' if appliance.firmware=='uefi' else 'bios'})
    xml=ET.tostring(root,encoding='utf-8',xml_declaration=True)
    import io
    checks=['SHA256(appliance.ovf)= '+hashlib.sha256(xml).hexdigest()]
    checks+=['SHA256(disk%s.vmdk)= '%i+digest(d[0]) for i,d in enumerate(appliance.disks,1)]
    with tarfile.open(path,'w',format=tarfile.USTAR_FORMAT) as archive:
        for name,data in [('appliance.ovf',xml),('appliance.mf',('\n'.join(checks)+'\n').encode())]:
            member=tarfile.TarInfo(name); member.size=len(data); member.mode=0o600; archive.addfile(member,io.BytesIO(data))
        for i,(disk,_,_) in enumerate(appliance.disks,1): archive.add(disk,arcname='disk'+str(i)+'.vmdk',recursive=False)

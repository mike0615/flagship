"""Streaming tar envelope validation without extraction or unbounded metadata reads."""
import re


class XVAEnvelope:
    def __init__(self):
        self.buffer = bytearray()
        self.remaining = 0
        self.zeros = 0
        self.ended = False
        self.entries = 0

    def feed(self, data):
        pending = self.buffer + data
        self.buffer.clear()
        offset = 0
        while offset < len(pending):
            if self.ended:
                if any(pending[offset:]): raise ValueError('Unexpected data after the XVA archive end')
                return
            if self.remaining:
                count = min(self.remaining, len(pending)-offset)
                offset += count
                self.remaining -= count
                continue
            if len(pending)-offset < 512:
                self.buffer.extend(pending[offset:])
                return
            header = bytes(pending[offset:offset+512]); offset += 512
            if not any(header):
                self.zeros += 1
                self.ended = self.zeros == 2
                continue
            if self.zeros: raise ValueError('Invalid XVA archive end marker')
            checksum = header[148:156].strip(b'\x00 ')
            if not re.fullmatch(rb'[0-7]{1,8}', checksum) or int(checksum, 8) != sum(header[:148])+256+sum(header[156:]):
                raise ValueError('Invalid XVA tar header checksum')
            name = header[:100].split(b'\x00', 1)[0]
            if self.entries == 0 and name != b'ova.xml':
                raise ValueError('Export did not begin with XVA metadata')
            self.entries += 1
            size = header[124:136]
            if size[0] == 0x80:
                size = int.from_bytes(size[1:], 'big')
            else:
                size = size.strip(b'\x00 ')
                if not re.fullmatch(rb'[0-7]{1,12}', size): raise ValueError('Invalid XVA member size')
                size = int(size, 8)
            if size > 2**63-1: raise ValueError('XVA member exceeds the supported size')
            self.remaining = ((size+511)//512)*512

    def finish(self):
        if not self.entries or not self.ended or self.remaining or self.buffer:
            raise ValueError('XVA archive ended before its complete tar envelope arrived')

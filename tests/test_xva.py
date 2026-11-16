import io
import tarfile
import unittest
from flagship.xva import XVAEnvelope


class EnvelopeTests(unittest.TestCase):
    def archive(self):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode='w', format=tarfile.USTAR_FORMAT) as archive:
            info = tarfile.TarInfo('ova.xml');info.size=4
            archive.addfile(info, io.BytesIO(b'meta'))
        return output.getvalue()

    def test_arbitrary_block_boundaries_preserve_complete_envelope(self):
        data=self.archive()
        for size in (1, 7, 511, 1000, 4096):
            envelope=XVAEnvelope()
            for offset in range(0,len(data),size): envelope.feed(data[offset:offset+size])
            envelope.finish()

    def test_truncated_body_and_end_markers_do_not_pass(self):
        data=self.archive()
        for length in (1, 511, 512, 1023, 1024, 1536, 2047):
            envelope=XVAEnvelope();envelope.feed(data[:length])
            with self.assertRaises(ValueError): envelope.finish()

    def test_wrong_metadata_bad_checksum_and_data_after_end_are_refused(self):
        data=self.archive()
        for damaged in (b'not an archive'.ljust(512,b' '), bytes([data[0]^1])+data[1:], data+b'not-padding'):
            with self.assertRaises(ValueError):
                envelope=XVAEnvelope();envelope.feed(damaged);envelope.finish()


if __name__ == '__main__': unittest.main()

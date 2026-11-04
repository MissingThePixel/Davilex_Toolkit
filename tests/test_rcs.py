from pathlib import Path
import struct
import tempfile
import unittest
import zlib
from davilex.rcs import Archive, ArchiveError, Entry


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        temp_root=Path(__file__).resolve().parents[1]/'.test-work'
        temp_root.mkdir(exist_ok=True)
        self.folder=tempfile.TemporaryDirectory(dir=temp_root)
        self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name)

    def make(self,records,body):
        image=self.root/'rcs.IMG'
        image.write_bytes(body)
        index=struct.pack('<H',len(records))+b''.join(struct.pack('<20sI',name.encode(),offset) for name,offset in records)
        (self.root/'rcs.IND').write_bytes(index)
        return Archive(image)

    def test_last_entry_ends_at_archive_boundary(self):
        archive=self.make([('first',0),('last',3)],b'abcdefg')
        self.assertEqual([archive.read(e) for e in archive.entries],[b'abc',b'defg'])

    def test_offset_only_index(self):
        image=self.root/'rc.img'
        image.write_bytes(b'abcdef')
        (self.root/'rc.ind').write_bytes(struct.pack('<HII',2,0,2))
        archive=Archive(image)
        self.assertEqual(archive.index_layout,'offsets-4')
        self.assertEqual([archive.read(e) for e in archive.entries],[b'ab',b'cdef'])

    def test_zero_length_marker_and_duplicate_names_remain_distinct(self):
        archive=self.make([('rcs.img',0),('same.wav',0),('SAME.wav',2)],b'abcd')
        self.assertEqual(archive.entries[0].size,0)
        files=[archive.extract(e,self.root/'out') for e in archive.entries[1:]]
        self.assertNotEqual(files[0].name.casefold(),files[1].name.casefold())
        self.assertEqual([p.read_bytes() for p in files],[b'ab',b'cd'])

    def test_reject_decreasing_offsets(self):
        with self.assertRaises(ArchiveError):
            self.make([('first',3),('second',1)],b'abcd')

    def test_reject_offset_outside_image(self):
        with self.assertRaises(ArchiveError):
            self.make([('first',5)],b'abcd')

    def test_reject_truncated_index(self):
        archive=self.make([('file',0)],b'abc')
        archive.index.write_bytes(b'\x01\x00'+bytes(10))
        with self.assertRaises(ArchiveError):
            Archive(archive.image)

    def test_decompress_and_preserve_raw_bytes(self):
        decoded=b'hello world'*100
        packed=struct.pack('<I',len(decoded))+zlib.compress(decoded)
        archive=self.make([('compressed',0)],packed)
        self.assertEqual(archive.read(archive.entries[0]),decoded)
        self.assertEqual(archive.extract(archive.entries[0],self.root/'raw',raw=True).read_bytes(),packed)
        self.assertEqual(archive.extract(archive.entries[0],self.root/'decoded').read_bytes(),decoded)

    def test_reject_size_lie_and_trailing_stream_bytes(self):
        for packed in (struct.pack('<I',1)+zlib.compress(b'longer'),
                       struct.pack('<I',3)+zlib.compress(b'abc')+b'junk'):
            archive=self.make([('compressed',0)],packed)
            with self.assertRaises(ArchiveError):
                archive.read(archive.entries[0])

    def test_reject_decompression_bomb_before_allocating(self):
        archive=self.make([('compressed',0)],struct.pack('<I',0x7fffffff)+zlib.compress(b'a'))
        with self.assertRaises(ArchiveError):
            archive.read(archive.entries[0])

    def test_no_overwrite(self):
        archive=self.make([('file',0)],b'abc')
        path=archive.extract(archive.entries[0],self.root/'out')
        path.write_bytes(b'user data')
        with self.assertRaises(FileExistsError):
            archive.extract(archive.entries[0],self.root/'out')
        self.assertEqual(path.read_bytes(),b'user data')

    def test_riff_size_bytes_are_not_a_compression_header(self):
        data=b'RIFF\x78\x9c\x00\x00WAVE'+b'data'
        archive=self.make([('achter8.wav',0)],data)
        self.assertEqual(archive.storage(archive.entries[0])['compression'],'none')
        self.assertEqual(archive.read(archive.entries[0]),data)

    def test_reject_path_escape(self):
        for name in ('../outside','..\\outside','C:outside','/outside'):
            archive=self.make([(name,0)],b'abc')
            with self.assertRaises(ArchiveError):
                archive.extract(archive.entries[0],self.root/'out')

    def test_reject_changed_archive(self):
        archive=self.make([('file',0)],b'abc')
        archive.image.write_bytes(b'a')
        with self.assertRaises(ArchiveError):
            archive.read(archive.entries[0])

    def test_reject_foreign_entry(self):
        archive=self.make([('file',0)],b'abc')
        with self.assertRaises(ArchiveError):
            archive.read(Entry(0,'wrong',0,3))


if __name__=='__main__':
    unittest.main()

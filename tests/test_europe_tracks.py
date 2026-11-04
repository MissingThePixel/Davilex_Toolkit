import struct,sys,unittest
from pathlib import Path
from davilex.europe_tracks import expand,REFERENCES,CAPACITY,STRIDE,OLD
from davilex.geometry_fixes import saab_body,WINDOW_FACES,SAAB_PANELS,remove_faces
from davilex.rcs import Archive
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/vendor'))
import pefile


class EuropeTrackTests(unittest.TestCase):
    def test_all_operands_and_loading_cache_use_separate_bounded_storage(self):
        raw=(ROOT/'work/Europe Racer-menu-timing/Game/spel.exe').read_bytes()
        fixed=expand(raw);old=pefile.PE(data=raw);new=pefile.PE(data=fixed)
        table=new.sections[-1];base=0x400000+table.VirtualAddress
        self.assertEqual(table.Name.rstrip(b'\0'),b'.dvTrks')
        self.assertEqual(table.Misc_VirtualSize,CAPACITY*(STRIDE+13))
        self.assertGreaterEqual(table.VirtualAddress,old.OPTIONAL_HEADER.SizeOfImage)
        self.assertEqual(new.get_data(0x49bb36-0x400000,3),b'\x83\xf8\x40')
        for address,value in REFERENCES:
            self.assertEqual(struct.unpack('<I',new.get_data(address-0x400000,4))[0],base+value-OLD)
        self.assertEqual(struct.unpack('<I',new.get_data(0x49aa14-0x400000,4))[0],base+CAPACITY*STRIDE)
        # Preserve all original initialized data and adjacent globals.
        self.assertEqual(old.sections[2].get_data(),new.sections[2].get_data())
        self.assertEqual(new.sections[-1].get_data(),bytes(new.sections[-1].SizeOfRawData))
        with self.assertRaisesRegex(ValueError,'verified source'):expand(fixed)

    def test_unknown_table_reference_is_rejected(self):
        raw=bytearray((ROOT/'work/Europe Racer-menu-timing/Game/spel.exe').read_bytes())
        p=pefile.PE(data=raw);offset=p.get_offset_from_rva(REFERENCES[0][0]-0x400000)
        raw[offset]^=1
        with self.assertRaisesRegex(ValueError,'reference'):expand(bytes(raw))

    def test_saab_removes_only_reviewed_window_faces_retaining_all_vertices(self):
        a=Archive(ROOT/'analysis/baseline/Europe Racer/Game/rcs.img')
        original=a.read(next(e for e in a.entries if e.name.lower()=='saab.d3d'))
        fixed=saab_body(original);_,nv,nf=struct.unpack_from('<iII',original);start=12+49*nv
        self.assertEqual(fixed[12:start],original[12:start])
        self.assertEqual(struct.unpack_from('<I',fixed,8)[0],nf-26)
        self.assertEqual(fixed[start:],b''.join(original[start+i*9:start+(i+1)*9]
                                              for i in range(nf) if i not in WINDOW_FACES))
        with self.assertRaisesRegex(ValueError,'Unknown'):saab_body(fixed)

    def test_detachable_window_panels_keep_vertices_and_nonwindow_faces(self):
        a=Archive(ROOT/'analysis/baseline/Europe Racer/Game/rcs.img')
        for name,(_,expected,removed) in SAAB_PANELS.items():
            raw=a.read(next(e for e in a.entries if e.name.lower()==name))
            fixed=remove_faces(raw,expected,removed);_,nv,nf=struct.unpack_from('<iII',raw);start=12+49*nv
            self.assertEqual(fixed[12:start],raw[12:start])
            self.assertEqual(struct.unpack_from('<I',fixed,8)[0],nf-len(removed))
            self.assertEqual(fixed[start:],b''.join(raw[start+i*9:start+(i+1)*9]for i in range(nf)if i not in removed))


if __name__=='__main__':unittest.main()

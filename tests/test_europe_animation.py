import struct,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools/vendor'))
import pefile
from davilex.europe_animation import patch,SITE,RESUME,REGISTER
from davilex.europe_tracks import expand as tracks
from davilex.europe_car_capacity import expand as cars

class EuropeAnimationTests(unittest.TestCase):
    def test_repair_preserves_collision_construction_and_other_handlers(self):
        raw=cars(tracks((ROOT/'work/Europe Racer-menu-timing/Game/spel.exe').read_bytes()))
        fixed=patch(raw);before=pefile.PE(data=raw);after=pefile.PE(data=fixed)
        section=after.sections[-1];address=0x400000+section.VirtualAddress
        self.assertEqual(section.Name.rstrip(b'\0'),b'.dvAnim')
        self.assertEqual(section.Characteristics,0x60000020)
        # The existing collider creation and activation calls run before the hook.
        self.assertEqual(after.get_data(0x48938f-0x400000,SITE-0x48938f),before.get_data(0x48938f-0x400000,SITE-0x48938f))
        self.assertEqual(SITE+5+struct.unpack('<i',after.get_data(SITE-0x400000+1,4))[0],address)
        body=section.get_data()[:section.Misc_VirtualSize]
        self.assertEqual(body[1:6],b'\x83\x7d\x08\x0f\x75')
        self.assertEqual(7+body[6],len(body)-6) # Other types branch to POPFD.
        call=body.index(b'\xe8');self.assertEqual(address+call+5+struct.unpack_from('<i',body,call+1)[0],REGISTER)
        self.assertEqual(address+len(body)+struct.unpack_from('<i',body,len(body)-4)[0],RESUME)
        # Every pre-existing section's raw bytes are unchanged except the detour.
        for a,b in zip(before.sections,after.sections):
            expected=bytearray(a.get_data());actual=b.get_data()
            offset=SITE-0x400000-a.VirtualAddress
            if 0<=offset<len(expected):expected[offset:offset+5]=actual[offset:offset+5]
            self.assertEqual(actual,bytes(expected))
        with self.assertRaises(ValueError):patch(fixed)

    def test_unknown_constructor_is_rejected(self):
        raw=(ROOT/'work/Europe Racer-menu-timing/Game/spel.exe').read_bytes();p=pefile.PE(data=raw)
        changed=bytearray(raw);changed[p.get_offset_from_rva(SITE-0x400000)]=0x90
        with self.assertRaisesRegex(ValueError,'constructor'):patch(bytes(changed))

if __name__=='__main__':unittest.main()

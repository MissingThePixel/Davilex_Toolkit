import struct,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools/vendor'))
import pefile
from davilex.europe_menu_language import expand as language,KEYS,OLD_COUNT
from davilex.europe_car_capacity import expand as cars,REFERENCES,CAPACITY,OLD,STRIDE
from davilex.europe_tracks import expand as tracks
from davilex.legacy_car_addons import handling,modern_mesh
from davilex.mesh import decode
from davilex.rcs import Archive
from davilex.europe_tuning import usable
class ExpandedVehicleTests(unittest.TestCase):
 def test_compiled_a2ii_catalog_is_the_verified_original_table(self):
  import hashlib,json
  from davilex.a2ii_car_tables import records,configuration
  raw=(ROOT/'davilex/a2ii_car_catalog.json').read_bytes();catalog=json.loads(raw)
  self.assertEqual(hashlib.sha256(raw).hexdigest(),'fa48bf42c4d708503071c6411612c9e2839c92e04e19b8d724f674b103b3b0ff')
  original=ROOT/'analysis/baseline/A2II/spel.dat'
  self.assertEqual(catalog['records'],records(original)[:7])
  _,anims,cars=configuration(original,0);self.assertEqual(catalog['cars'],cars)
  for name,value in catalog['animations'].items():self.assertEqual(value,anims[name])
 def test_menu_retains_every_old_enum_and_expands_dynamic_language_loader(self):
  original=(ROOT/'analysis/baseline/Europe Racer/Menu/GameMenu.dat').read_bytes();fixed=language(original);p=pefile.PE(data=fixed)
  pointer=struct.unpack('<I',p.get_data(0x6a7ac,4))[0];header=p.get_data(pointer-0x400000,28)
  self.assertEqual(struct.unpack_from('<I',header,20)[0],OLD_COUNT+len(KEYS)-1)
  old=pefile.PE(data=original);old_names=old.get_data(0x6a7cc,0x46bfc2-0x46a7cc)
  self.assertEqual(p.get_data(pointer-0x400000+28,len(old_names)),old_names)
  appended=p.get_data(pointer-0x400000+28+len(old_names),sum(len(k)+1 for k in KEYS))
  self.assertEqual(appended,b''.join(bytes([len(k)])+k.encode()for k in KEYS))
  self.assertEqual(struct.unpack('<I',p.get_data(0x6c1c9,4))[0],OLD_COUNT+len(KEYS))
  self.assertTrue(any(e.rva==pointer-0x400000+24 for b in p.DIRECTORY_ENTRY_BASERELOC for e in b.entries))
 def test_dynamics_constructor_loader_and_all_readers_share_bounded_new_storage(self):
  original=tracks((ROOT/'work/Europe Racer-menu-timing/Game/spel.exe').read_bytes());fixed=cars(original);p=pefile.PE(data=fixed);base=0x400000+p.sections[-1].VirtualAddress
  self.assertEqual(p.sections[-1].Name.rstrip(b'\0'),b'.dvCars');self.assertEqual(p.sections[-1].Misc_VirtualSize,CAPACITY*STRIDE)
  for address,value in REFERENCES:
   expected=base+CAPACITY*STRIDE if address==0x454ab6 else base+value-OLD
   self.assertEqual(struct.unpack('<I',p.get_data(address-0x400000,4))[0],expected)
  self.assertEqual(struct.unpack('<I',p.get_data(0x53c18,4))[0],CAPACITY)
  # Adjacent original singleton/string storage must not be mistaken for end pointers.
  before=pefile.PE(data=original)
  for a in (0x453b38,0x453b5a):self.assertEqual(p.get_data(a-0x400000,4),before.get_data(a-0x400000,4))
  with self.assertRaises(ValueError):cars(fixed)
 def test_legacy_power_scale_survives_radius_conversion_with_native_gearbox(self):
  raw=(ROOT/'analysis/baseline/London Racer/phys0.dat').read_bytes()[:172];seed=(ROOT/'analysis/baseline/Europe Racer/Game/Vdyns/VDYNS0.DAT').read_bytes()
  a,report=handling(raw,seed,2.7);b,_=handling(raw,seed,5.4)
  self.assertEqual(struct.unpack_from('<f',a)[0],struct.unpack_from('<f',raw)[0])
  self.assertAlmostEqual(struct.unpack_from('<f',b,332)[0],2*struct.unpack_from('<f',a,332)[0],places=4)
  self.assertTrue(all(usable(a,i)for i in range(5)))
  self.assertEqual(report['levels'][0]['source_force_gears'],5)
  self.assertEqual(report['levels'][1]['source_force_gears'],6)
  self.assertEqual(a[312:332],seed[312:332]);self.assertEqual(a[452:572],seed[452:572])
 def test_mesh_conversion_preserves_geometry_uv_and_triangle_metadata(self):
  a=Archive(ROOT/'analysis/baseline/Autobahn Raser II/rcs.img');e=next(e for e in a.entries if e.name.casefold()=='trabant.d3d');raw=a.read(e);fixed=modern_mesh(raw)
  old,new=decode(raw),decode(fixed);self.assertEqual(old.triangles,new.triangles);self.assertEqual(old.face_metadata,new.face_metadata)
  self.assertEqual([(v.position,v.normal,v.uv,v.flags)for v in old.vertices],[(v.position,v.normal,v.uv,v.flags)for v in new.vertices])
if __name__=='__main__':unittest.main()

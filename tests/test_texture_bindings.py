from pathlib import Path
import struct
import tempfile
import unittest
from davilex.rcs import Archive
from davilex.texture_bindings import Resolver

ROOT=Path(__file__).resolve().parents[1]


def archive(folder,model):
    folder.mkdir()
    records=[('car.d3d',model),('wrong.tga',b'wrong'),('car.pcx',b'car')]
    index=bytearray(struct.pack('<H',len(records)));data=bytearray()
    for name,raw in records:
        index.extend(struct.pack('<20sI',name.encode(),len(data)));data.extend(raw)
    (folder/'rcs.ind').write_bytes(index);(folder/'rcs.img').write_bytes(data)
    return Archive(folder/'rcs.img')


class BindingTests(unittest.TestCase):
    def test_retained_binding_rejects_wrong_texture_or_changed_mesh(self):
        source=Archive(ROOT/'analysis/baseline/London Racer/rcs.img')
        model=source.read(next(e for e in source.entries if e.name.casefold()=='racer_1.d3d'))
        texture=source.read(next(e for e in source.entries if e.name.casefold()=='racer01.tga'))
        for raw_model,raw_texture in ((model,b'not the reviewed atlas'),(model+b'changed',texture)):
            with tempfile.TemporaryDirectory(dir=ROOT/'.test-work') as temp:
                folder=Path(temp);index=bytearray(struct.pack('<H',2));data=bytearray()
                for name,raw in [('racer_1.d3d',raw_model),('racer01.tga',raw_texture)]:
                    index.extend(struct.pack('<20sI',name.encode(),len(data)));data.extend(raw)
                (folder/'rcs.ind').write_bytes(index);(folder/'rcs.img').write_bytes(data)
                current=Archive(folder/'rcs.img')
                self.assertEqual(Resolver(current,folder).resolve(current.entries[0],related=False),[])

    def test_retained_london_and_m25_cars_use_their_local_original_atlas(self):
        for folder in (ROOT/'analysis/baseline/London Racer',ROOT/'analysis/M25 Racer'):
            with self.subTest(folder=folder):
                current=Archive(folder/'rcs.img');resolver=Resolver(current,ROOT/'analysis/baseline')
                for n in range(1,8):
                    entry=next(e for e in current.entries if e.name.casefold()==f'racer_{n}.d3d')
                    bindings=resolver.resolve(entry,related=False)
                    self.assertTrue(bindings,entry.name)
                    self.assertEqual(bindings[0].entry.name.casefold(),f'racer0{2 if n in (2,3) else 1}.tga')
                    self.assertEqual(bindings[0].archive.image,current.image)
                    self.assertFalse(bindings[0].related)
                lotus=next(e for e in current.entries if e.name.casefold()=='lotus_1.d3d')
                self.assertEqual(resolver.resolve(lotus,related=False)[0].entry.name.casefold(),'l3racer1.tga')

    def test_exact_mesh_animation_binding_overrides_track_placeholder(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.test-work') as temp:
            root=Path(temp);target=archive(root/'target',b'mesh UV data')
            source=archive(root/'source',b'mesh UV data')
            (target.image.parent/'etappe0.ini').write_text('[models]\n0=car.d3d,wrong.tga\n')
            (source.image.parent/'e00_anim.ini').write_text('[car]\n0=car.d3d,car.pcx\n')
            resolver=Resolver(target,root);bindings=resolver.resolve(target.entries[0])
            self.assertEqual(bindings[0].entry.name,'car.pcx')
            self.assertTrue(bindings[0].related)
            self.assertIn('Identical mesh',bindings[0].source)
            self.assertEqual(resolver.resolve(target.entries[0],related=False)[0].entry.name,'wrong.tga')

    def test_same_model_name_with_different_uv_bytes_is_not_a_match(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.test-work') as temp:
            root=Path(temp);target=archive(root/'target',b'mesh UV data')
            source=archive(root/'source',b'mesh XX data')
            (source.image.parent/'e00_anim.ini').write_text('[car]\n0=car.d3d,car.pcx\n')
            self.assertEqual(Resolver(target,root).resolve(target.entries[0]),[])

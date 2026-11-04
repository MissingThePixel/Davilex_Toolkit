from pathlib import Path
import struct
import tempfile
import unittest
from davilex.rcs import Archive,Entry,convert_image
from davilex.media import sprite_header,font_header,proportional_font,category,ordered_entries,load_image,texture_links
from davilex.mesh import Mesh,Vertex
from davilex.mesh_preview import render

ROOT=Path(__file__).resolve().parents[1]


class MediaTests(unittest.TestCase):
    def test_sprite_length_is_exact_and_dimensions_bounded(self):
        data=struct.pack('<4H',2,2,1,1)+bytes((0,1,2,255))
        self.assertEqual(sprite_header(data,len(data))['width'],2)
        self.assertIsNone(sprite_header(data,len(data)+1))
        self.assertIsNone(sprite_header(struct.pack('<4H',0,2,1,1),8))

    def test_bin_image_pixels_and_explicit_palette_survive_png_export(self):
        parent=ROOT/'.test-work';parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as folder:
            root=Path(folder);data=struct.pack('<4H',2,2,1,1)+bytes((0,1,2,255))
            (root/'rc.img').write_bytes(data)
            (root/'rc.ind').write_bytes(struct.pack('<HI',1,0))
            archive=Archive(root/'rc.img');entry=archive.entries[0]
            palette=[c for i in range(256) for c in (i,0,255-i)]
            self.assertEqual(category(archive,entry),'Images')
            image=load_image(archive,entry,palette)
            self.assertEqual(image.convert('RGB').getpixel((1,0)),(1,0,254))
            target=root/'sprite.png';convert_image(archive,entry,target,palette)
            from PIL import Image
            with Image.open(target) as exported:self.assertEqual(exported.tobytes(),data[8:])

    def test_numeric_sort_and_combined_category_filters(self):
        entries=[Entry(0,'z.bin',0,9),Entry(1,'a.wav',9,100),Entry(2,'b.pcx',109,20)]
        categories={0:(False,'Other'),1:(True,'Music / audio'),2:(True,'Images')}
        self.assertEqual([e.index for e in ordered_entries(entries,categories,'','size',True)],[1,2])
        self.assertEqual([e.index for e in ordered_entries(entries,categories,'.pcx')],[2])

    def test_mesh_orbit_changes_geometry_preview(self):
        vs=tuple(Vertex(p,(0,0,1),(0,0),(1,1,1,1),0) for p in ((0,0,0),(2,0,0),(0,1,1)))
        mesh=Mesh(vs,((0,1,2),),(b'\0'*3,))
        self.assertNotEqual(render(mesh,yaw=0).tobytes(),render(mesh,yaw=1).tobytes())

    def test_font_cell_order_and_truncation(self):
        data=bytes(256)+struct.pack('<4H',2,3,253,255)+b''.join(bytes([n])*6 for n in range(256))
        self.assertEqual(font_header(data,len(data))['glyphs'],256)
        self.assertIsNone(font_header(data,len(data)-1))
        class FakeArchive:
            def read(self,entry):return data
        image=load_image(FakeArchive(),Entry(0,'test.img',0,len(data)))
        self.assertEqual(image.size,(32,48))
        self.assertEqual(image.getpixel((2,0)),1)
        self.assertEqual(image.getpixel((0,3)),16)

    def test_textured_triangles_sample_source_colours(self):
        from PIL import Image
        vs=tuple(Vertex(p,(0,0,1),uv,(1,1,1,1),0) for p,uv in zip(((0,0,0),(2,0,0),(0,2,0)),((0,0),(.99,0),(0,.99))))
        mesh=Mesh(vs,((0,1,2),),(b'\0'*3,))
        image=render(mesh,texture=Image.new('RGB',(2,2),(230,80,20)),yaw=0,pitch=0)
        self.assertIn(bytes((230,80,20)),image.tobytes())

    def test_proportional_font_offsets_and_atlas_character_positions(self):
        table=bytearray(b'\xff'*2048+b'\x00'*8)
        struct.pack_into('<HHI',table,65*8,2,3,2056)
        struct.pack_into('<HHI',table,66*8,1,2,2062)
        data=bytes(table)+bytes([10])*6+bytes([20])*2
        self.assertEqual(proportional_font(data,len(data))['glyph_count'],2)
        self.assertIsNone(proportional_font(data,len(data)-1))
        broken=bytearray(data);struct.pack_into('<I',broken,66*8+4,2057)
        self.assertIsNone(proportional_font(broken,len(broken)))
        class FakeArchive:
            def read(self,entry):return data
        image=load_image(FakeArchive(),Entry(0,'test.fnt',0,len(data)))
        self.assertEqual(image.getpixel((2,12)),10)
        self.assertEqual(image.getpixel((4,12)),20)


if __name__=='__main__':unittest.main()

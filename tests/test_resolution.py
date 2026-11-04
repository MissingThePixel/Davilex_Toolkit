import hashlib
import json
from pathlib import Path
import struct
import unittest
from davilex.resolution import patch_a2iv,patch_engine,SOURCES,LEGACY,RADARS,radar_edits

ROOT = Path(__file__).resolve().parents[1]


class ResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT/'work/A2 Racer 4-menu-cycle/spel.dat').read_bytes()

    def test_matches_human_confirmed_720p_engine_exactly(self):
        changed, report = patch_a2iv(self.source,1280,720)
        # Preserve the lineage check of the previously human-confirmed image;
        # this revision adds only the declared minimap/marker correction.
        changed=bytearray(changed)
        addresses={hex(va) for va,_,_ in radar_edits('a2racer4-resolution')}
        for edit in report['edits']:
            if edit['address'] in addresses:
                pos=edit['file_offset'];before=bytes.fromhex(edit['before'])
                changed[pos:pos+len(before)]=before
        self.assertEqual(hashlib.sha256(changed).hexdigest(),
                         'f4c5b8efa1c00c064c8b50e78bf6960d4731fc20c02575a5fc5d993cbb1d180b')

    def test_different_aspects_preserve_uniform_pixels_and_centre_design_canvas(self):
        for width,height in [(640,480),(1920,1080),(1920,1200),(2560,1080),(1366,768)]:
            with self.subTest(dimensions=(width,height)):
                changed, report = patch_a2iv(self.source,width,height)
                x,y,cw,ch = report['clip_xy_width_height']
                self.assertAlmostEqual(width/cw,height/ch)
                self.assertAlmostEqual(x+cw/2,0)
                self.assertAlmostEqual(y-ch/2,0)
                self.assertAlmostEqual(report['hud_canvas'][0]/height,4/3)
                # Confirm all differences are covered by exact declared edits;
                # unchanged executable code and shared constants stay intact.
                restored = bytearray(changed)
                for edit in report['edits']:
                    pos=edit['file_offset'];after=bytes.fromhex(edit['after'])
                    self.assertEqual(changed[pos:pos+len(after)],after)
                    restored[pos:pos+len(after)]=bytes.fromhex(edit['before'])
                self.assertEqual(restored,self.source)
                mode=report['edits'][0]['file_offset']
                self.assertEqual(struct.unpack_from('<2I',changed,mode),(width,height))

    def test_rejects_unknown_builds_and_unsupported_dimensions(self):
        with self.assertRaises(ValueError):patch_a2iv(self.source+b'changed',1280,720)
        for width,height in [(0,720),(1920,0),(640,800),(10000,1080),(1280.0,720),(True,720)]:
            with self.subTest(dimensions=(width,height)),self.assertRaises(ValueError):
                patch_a2iv(self.source,width,height)

    def test_all_six_adapters_match_their_prepared_images_and_preserve_sources(self):
        from davilex.launch import verified_engine
        for profile,(folder,base,short) in SOURCES.items():
            if profile=='a2racer4-resolution':continue
            with self.subTest(profile=profile):
                original=verified_engine(ROOT/'work'/folder,base).read_bytes()
                changed,report=patch_engine(original,1920,1080,profile)
                expected=json.loads((ROOT/'tests/resolution-1920x1080-sha256.json').read_text())[profile]
                self.assertEqual(hashlib.sha256(changed).hexdigest(),expected)
                restored=bytearray(changed[:len(original)])
                for edit in report['edits']:
                    pos=edit['file_offset'];before=bytes.fromhex(edit['before'])
                    restored[pos:pos+len(before)]=before
                if profile not in LEGACY:self.assertEqual(restored,original)
                else:
                    # Undo the separately declared PE section/header additions.
                    pe=struct.unpack_from('<I',original,0x3c)[0];optional=pe+24
                    n=struct.unpack_from('<H',original,pe+6)[0]
                    table=optional+struct.unpack_from('<H',original,pe+20)[0]
                    for pos,size in [(pe+6,2),(optional+4,4),(optional+56,4),(table+n*40,40)]:
                        restored[pos:pos+size]=original[pos:pos+size]
                    self.assertEqual(restored,original)

    def test_a2ii_sky_uses_native_extent(self):
        from davilex.launch import verified_engine
        original=verified_engine(ROOT/'work/A2II-menu-cycle','a2ii-timing').read_bytes()
        _,report=patch_engine(original,1920,1080,'a2ii-resolution')
        edit=next(e for e in report['edits'] if e['address']=='0x4881a0')
        self.assertEqual(struct.unpack('<4I',bytes.fromhex(edit['after'])),(0,0,1919,1079))

    def test_radar_square_and_marker_scale_use_the_same_axis_across_aspects(self):
        import sys
        sys.path.insert(0,str(ROOT/'tools/vendor'))
        import pefile
        from davilex.launch import verified_engine
        for profile,spec in RADARS.items():
            folder,base,_=SOURCES[profile]
            original=verified_engine(ROOT/'work'/folder,base).read_bytes()
            for width,height in [(640,480),(3840,2560),(1920,1080),(2560,1080)]:
                changed,_=patch_engine(original,width,height,profile)
                pe=pefile.PE(data=changed)
                def operand(va,opcode):
                    pos=pe.get_offset_from_rva(va-pe.OPTIONAL_HEADER.ImageBase)
                    self.assertEqual(changed[pos:pos+2],opcode)
                    return struct.unpack_from('<I',changed,pos+2)[0]
                def factor(va):
                    target=operand(va,b'\xd8\x0d')
                    return struct.unpack_from('<f',changed,pe.get_offset_from_rva(target-0x400000))[0]
                self.assertEqual(operand(spec['map_x'],b'\xdb\x05'),spec['width']+4)
                self.assertEqual(operand(spec['marker_x'],b'\xdb\x05'),spec['width']+4)
                # The unmodified map height is screen height / 6. Both axes
                # and both marker dimensions must now share that pixel scale.
                self.assertAlmostEqual(height*factor(spec['span']),height/6,delta=.001)
                self.assertAlmostEqual(height*factor(spec['left']),height/16,delta=.001)
                self.assertAlmostEqual(height*factor(spec['marker_scale']),height/60,delta=.001)

    def test_a2ii_radar_scales_uniformly_at_bottom_left(self):
        from davilex.launch import verified_engine
        original=verified_engine(ROOT/'work/A2II-menu-cycle','a2ii-timing').read_bytes()
        for width,height in [(640,480),(1920,1080),(2560,1080),(1920,1200)]:
            _,report=patch_engine(original,width,height,'a2ii-resolution')
            radar=next(e for e in report['edits'] if e['address']=='0x489050')
            left,top,right,bottom=struct.unpack('<4i',bytes.fromhex(radar['after']))
            self.assertAlmostEqual(left/height,30/480,delta=1/height)
            self.assertAlmostEqual(top/height,361/480,delta=1/height)
            self.assertAlmostEqual((right-left)/(bottom-top),1,delta=.01)
            self.assertAlmostEqual((height-bottom)/height,-9/480,delta=1/height)

import unittest
from PIL import Image
from davilex.textures import prepare


class TextureTests(unittest.TestCase):
    def test_mip_sheet_samples_main_image_and_preserves_original(self):
        base=Image.new('RGB',(32,32),(20,60,100))
        sheet=Image.new('RGB',(48,32),(240,240,0))
        sheet.paste(base,(0,0));sheet.paste(base.resize((16,16)),(32,0))
        before=sheet.tobytes();sample,info=prepare(sheet)
        self.assertTrue(info['packed_mips_detected'])
        self.assertEqual(sample.size,(32,32))
        self.assertEqual(sample.getpixel((30,0)),(20,60,100,255))
        self.assertEqual(sheet.tobytes(),before)
        full,_=prepare(sheet,'Full image');self.assertEqual(full.size,(48,32))

    def test_shape_alone_does_not_crop_and_colour_key_is_optional(self):
        sheet=Image.new('RGB',(48,32),(255,0,255))
        sheet.paste((0,255,0),(32,0,48,16))
        sample,info=prepare(sheet)
        self.assertFalse(info['packed_mips_detected'])
        self.assertEqual(sample.size,(48,32))
        self.assertEqual(sample.getpixel((0,0))[3],0)
        opaque,_=prepare(sheet,colour_key=False)
        self.assertEqual(opaque.getpixel((0,0))[3],255)

    def test_unused_tga_alpha_bytes_do_not_hide_a_texture(self):
        image=Image.new('RGBA',(32,32),(10,20,30,0))
        image.info['davilex_tga_alpha_bits']=0
        sample,_=prepare(image)
        self.assertEqual(sample.getpixel((0,0))[3],255)
        image.info['davilex_tga_alpha_bits']=8
        sample,_=prepare(image)
        self.assertEqual(sample.getpixel((0,0))[3],0)

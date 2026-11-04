from pathlib import Path
from unittest import TestCase
from davilex.recognition import engine_matches,dimensions
from davilex.resolution import SOURCES,patch_engine
from davilex.menu import verify_copy
from davilex.paths import ROOT
class ExactMovedBuildTests(TestCase):
 def test_supported_previous_resolutions_match_but_modified_code_is_rejected(self):
  for profile,(folder,classic,_) in SOURCES.items():
   _,engine=verify_copy(ROOT/'work'/folder,classic);canonical=engine.read_bytes()
   for size in [(1280,720),(1920,1080)]:
    with self.subTest(profile=profile,size=size):
     current=patch_engine(canonical,*size,profile)[0]
     self.assertEqual(dimensions(current,profile),size)
     self.assertTrue(engine_matches(current,canonical,profile))
     edited=bytearray(current);edited[-1]^=1
     self.assertFalse(engine_matches(bytes(edited),canonical,profile))
 def test_untrusted_header_does_not_establish_compatibility(self):
  self.assertFalse(engine_matches(b'MZ'+bytes(100),b'canonical','europe-resolution'))

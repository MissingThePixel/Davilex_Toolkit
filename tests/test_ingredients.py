from pathlib import Path
import hashlib,json,tempfile,wave
from unittest import TestCase
from unittest.mock import patch
from davilex import ingredients
from davilex.audio import pcm_wav

class RecipeTests(TestCase):
 def test_recipe_checks_hash_and_range(self):
  recipe={'size':3,'sha256':hashlib.sha256(b'abc').hexdigest(),'changes':[[1,b'b'.hex()]]}
  self.assertEqual(ingredients.apply(b'axc',recipe),b'abc')
  with self.assertRaises(ValueError):ingredients.apply(b'axx',recipe)
  recipe['changes']=[[4,'00']]
  with self.assertRaises(ValueError):ingredients.apply(b'abc',recipe)
 def test_game_menu_is_reconstructed_in_memory_and_unknown_variant_rejected(self):
  with tempfile.TemporaryDirectory(dir=ingredients.ROOT/'work')as tmp:
   root=Path(tmp);(root/'patches').mkdir();game=root/'game';game.mkdir();binary=game/'menu.exe'
   original=b'original';canonical=b'patched!'
   restore={'size':8,'sha256':ingredients.digest(original),'changes':[[0,original.hex()]]}
   patcher={'size':8,'sha256':ingredients.digest(canonical),'changes':[[0,canonical.hex()]]}
   identity={'size':8,'sha256':ingredients.digest(original),'changes':[]}
   record={'title':'London Racer','profile':'london-resolution','relative':'menu.exe','restore':restore,'canonical':patcher,'accepted':[identity,patcher]}
   catalog={'paths':{'patches/virtual/menu.exe':{'entry':'test','kind':'canonical'}},'binaries':{'test':record}}
   (root/'patches/binary-recipes.json').write_text(json.dumps(catalog));requested=root/'patches/virtual/menu.exe'
   with patch.object(ingredients,'resources',return_value=root),ingredients.selected_install(game,'london-resolution'):
    for data in (original,canonical):
     binary.write_bytes(data);self.assertEqual(ingredients.read(requested),canonical);self.assertEqual(binary.read_bytes(),data);self.assertFalse(requested.exists())
    binary.write_bytes(b'unknown!')
    with self.assertRaises(ValueError):ingredients.read(requested)

class BuiltinAudioTests(TestCase):
 def test_pcm_preserves_native_rate_channels_and_existing_exports(self):
  with tempfile.TemporaryDirectory(dir=ingredients.ROOT/'work')as tmp:
   source=Path(tmp)/'source.wav';target=Path(tmp)/'decoded.wav';samples=bytes(range(100))*2
   with wave.open(str(source),'wb')as w:w.setparams((1,2,16000,0,'NONE','none'));w.writeframes(samples)
   pcm_wav(source,target,allow_external=False)
   with wave.open(str(target),'rb')as w:self.assertEqual((w.getnchannels(),w.getframerate(),w.getsampwidth()),(1,16000,2));self.assertEqual(w.readframes(100),samples)
   before=target.read_bytes()
   with self.assertRaises(FileExistsError):pcm_wav(source,target,allow_external=False)
   self.assertEqual(target.read_bytes(),before)

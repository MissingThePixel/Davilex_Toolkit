from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import json
from davilex import settings,installed

class PortableLocationTests(TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory(dir=installed.ROOT/'work');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
 def test_bundled_paths_saved_relative_and_follow_moved_root(self):
  old=self.root/'old';game=old/'games/London Racer';game.mkdir(parents=True)
  settings.save({'game':'London Racer','installs':{'London Racer':str(game)}},old)
  self.assertEqual(json.loads((old/'work/toolkit-settings.json').read_text())['installs']['London Racer'],'games/London Racer')
  new=self.root/'new';old.rename(new)
  self.assertEqual(settings.load(new)['installs']['London Racer'],str(new/'games/London Racer'))
 def test_old_crossover_y_path_rebases_to_games_folder(self):
  game=self.root/'games/Europe Racer';game.mkdir(parents=True);(self.root/'work').mkdir()
  (self.root/'work/toolkit-settings.json').write_text(json.dumps({'installs':{'Europe Racer':r'Y:\Downloads\Davilex Toolkit\games\Europe Racer'}}))
  self.assertEqual(settings.load(self.root)['installs']['Europe Racer'],str(game))
 def test_stale_external_path_dropped_instead_of_blocking_discovery(self):
  (self.root/'work').mkdir();(self.root/'work/toolkit-settings.json').write_text(json.dumps({'installs':{'London Racer':r'Y:\Gone\London Racer'}}))
  self.assertEqual(settings.load(self.root)['installs'],{})
 def test_relative_escape_ignored(self):
  (self.root/'work').mkdir();(self.root/'work/toolkit-settings.json').write_text(json.dumps({'installs':{'London Racer':'../../'}}))
  self.assertEqual(settings.load(self.root)['installs'],{})
 def test_existing_external_install_retained(self):
  game=self.root/'external';game.mkdir();toolkit=self.root/'app';toolkit.mkdir()
  settings.save({'installs':{'London Racer':str(game)}},toolkit)
  self.assertEqual(settings.load(toolkit)['installs']['London Racer'],str(game))
 def test_locate_validates_files_and_uses_moved_bundle(self):
  game=self.root/'games/London Racer';game.mkdir(parents=True)
  for name in ('menu.exe','spel.dat'):(game/name).write_bytes(b'fixture')
  with patch.object(installed,'ROOT',self.root),patch.object(installed,'baseline',return_value={'title':'London Racer','source':r'Y:\Gone\London Racer'}):
   self.assertEqual(installed.locate('london-resolution'),game)
   with self.assertRaises(ValueError):installed.locate('london-resolution',self.root)
 def test_transaction_discards_rollback_and_preserves_only_changed_original(self):
  game=self.root/'game';game.mkdir();(game/'spel.dat').write_bytes(b'original');(game/'rcs.img').write_bytes(b'untouched')
  with patch.object(installed,'ROOT',self.root):
   installed.commit(game,{Path('spel.dat'):b'patched'})
   journal=installed.journal_folder(game)
   self.assertFalse((journal/'rollback').exists());self.assertEqual((journal/'original/spel.dat').read_bytes(),b'original')
   self.assertFalse((journal/'original/rcs.img').exists());self.assertEqual((game/'rcs.img').read_bytes(),b'untouched')

import hashlib,tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from davilex import discovery
from davilex.paths import ROOT

class SiblingDiscoveryTests(TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=ROOT/'work');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.games={'A2 Racer II':'a2ii-resolution','London Racer':'london-resolution'}
  self.records={profile:{'files':[{'path':'spel.dat','sha256':hashlib.sha256(name.encode()).hexdigest()}]}for name,profile in self.games.items()}
 def game(self,folder,name):
  path=self.root/folder;path.mkdir();(path/'spel.dat').write_bytes(name.encode());(path/'menu.dat'if name=='A2 Racer II'else path/'menu.exe').write_bytes(b'menu');return path
 def test_locating_one_finds_other_named_or_arbitrarily_named_siblings(self):
  first=self.game('A2II','A2 Racer II');second=self.game('unusual folder','London Racer')
  with patch('davilex.toolkit.GAMES',self.games),patch('davilex.installed.baseline',side_effect=lambda profile:self.records[profile]):
   result=discovery.sibling_installs(first,{'A2 Racer II':str(first)})
  self.assertEqual(result,{'A2 Racer II':str(first),'London Racer':str(second)})
 def test_valid_explicit_location_is_retained_and_duplicate_siblings_are_not_guessed(self):
  first=self.game('A2II','A2 Racer II');one=self.game('LR one','London Racer');two=self.game('LR two','London Racer')
  with patch('davilex.toolkit.GAMES',self.games),patch('davilex.installed.baseline',side_effect=lambda profile:self.records[profile]),patch('davilex.installed.locate',side_effect=lambda profile,path:Path(path)):
   self.assertNotIn('London Racer',discovery.sibling_installs(first))
   self.assertEqual(discovery.sibling_installs(first,{'London Racer':str(one)})['London Racer'],str(one))
 def test_unrelated_menu_and_executable_names_do_not_establish_a_game_identity(self):
  first=self.game('A2II','A2 Racer II');other=self.game('not London','unrelated bytes')
  with patch('davilex.toolkit.GAMES',self.games),patch('davilex.installed.baseline',side_effect=lambda profile:self.records[profile]):
   self.assertNotIn('London Racer',discovery.sibling_installs(first))

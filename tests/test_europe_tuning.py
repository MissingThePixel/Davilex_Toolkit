import unittest
import struct
import tempfile
import subprocess
from unittest.mock import patch
from pathlib import Path
from davilex.europe_tuning import usable,tuning_changes

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'analysis/baseline/Europe Racer/Game'


class EuropeTuningTests(unittest.TestCase):
    def read(self,index):return (SOURCE/f'Vdyns/VDYNS{index}.DAT').read_bytes()

    def test_original_classic_has_unusable_upgrade_columns(self):
        for index in (2,18,30):
            raw=self.read(index)
            self.assertTrue(usable(raw,0))
            self.assertTrue(usable(raw,1))
            for level in (2,3,4):self.assertFalse(usable(raw,level))
        for level in range(5):self.assertTrue(usable(self.read(0),level))

    def test_player_and_opponent_bad_choices_repair_only_bad_levels(self):
        game=b'[PLAYER]\r\ncar=2\r\n[UPGRADES]\r\nPlayer=3\r\nRacer0=4\r\nRacer1=3\r\nRacer2=1\r\n[RACERS]\r\n0=18,0,0\r\n1=0,0,0\r\n2=30,0,0\r\n'
        changes,report=tuning_changes(game,(SOURCE/'Ini/Cars.ini').read_bytes(),self.read)
        self.assertEqual(changes,{('UPGRADES','Player'):0,('UPGRADES','Racer0'):0})
        self.assertEqual([r['car'] for r in report],[2,18])

    def test_unknown_damage_never_invents_physics(self):
        raw=bytearray(self.read(2));struct.pack_into('<f',raw,732,0)
        with self.assertRaisesRegex(ValueError,'no usable base'):
            tuning_changes(b'[PLAYER]\ncar=2\n[UPGRADES]\nPlayer=3\n',
                (SOURCE/'Ini/Cars.ini').read_bytes(),lambda _:bytes(raw))
        for level in (-1,5,99):self.assertFalse(usable(self.read(0),level))
        raw=bytearray(self.read(0));struct.pack_into('<f',raw,732,float('nan'))
        self.assertFalse(usable(raw,0))

    def test_each_original_menu_start_is_checked_after_menu_writes(self):
        from davilex.menu import cycle
        from davilex.europe_tuning import values
        with tempfile.TemporaryDirectory(dir=ROOT/'.test-work') as name:
            root=Path(name);engine=root/'Game/spel.exe';menu=root/'Menu/GameMenu.dat'
            (engine.parent/'Ini').mkdir(parents=True);(engine.parent/'Vdyns').mkdir();menu.parent.mkdir()
            (engine.parent/'Ini/Cars.ini').write_bytes((SOURCE/'Ini/Cars.ini').read_bytes())
            (engine.parent/'Vdyns/VDYNS2.DAT').write_bytes(self.read(2))
            config=engine.parent/'Ini/game.ini';signal=menu.parent/'GameMenu.ini'
            signal.write_text('[GENERAL]\nEXITCODE=255\n');menus=0;engines=0
            def runner(command,**kwargs):
                nonlocal menus,engines
                if Path(command[0])==menu:
                    menus+=1
                    config.write_bytes(b'[PLAYER]\ncar=2\n[UPGRADES]\nPlayer=3\n')
                    signal.write_text(f'[GENERAL]\nEXITCODE={40 if menus<=2 else 255}\n')
                else:
                    engines+=1
                    self.assertEqual(values(config.read_bytes())['upgrades','player'],'0')
                return subprocess.CompletedProcess(command,0)
            with patch('davilex.menu.verify_copy',return_value=(menu,engine)):
                self.assertEqual(cycle(root,profile='europe',runner=runner),0)
            self.assertEqual((menus,engines),(3,2))


if __name__=='__main__':unittest.main()

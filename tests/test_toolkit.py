from contextlib import nullcontext
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from davilex.quickrace import race_mode,restore_race,race_settings,race_catalog,update_ini
from davilex.toolkit import run_game,working_copy,ROOT,GAMES


class QuickRaceRecoveryTests(unittest.TestCase):
    def config(self):
        return b'[ETAPPE]\r\netappe=0\r\n[PLAYER]\r\ncar=0\r\ndamage=3\r\ncopland=1\r\nmotor=0\r\nbanden=0\r\nabs=0\r\nturbo=0\r\nversnellingsbak=0\r\nname=Pat\r\n'

    def test_exception_restores_selection_and_retains_unrelated_game_writes(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
            directory=Path(folder);config=directory/'game.ini';original=self.config()
            config.write_bytes(original)
            with self.assertRaises(RuntimeError):
                with race_mode(directory,6,4):
                    self.assertIn(b'etappe=6',config.read_bytes())
                    self.assertIn(b'car=4',config.read_bytes())
                    config.write_bytes(config.read_bytes().replace(b'name=Pat',b'name=New'))
                    raise RuntimeError('Simulated launch failure')
            self.assertEqual(config.read_bytes(),original.replace(b'name=Pat',b'name=New'))
            self.assertFalse((directory/'.quickrace-restore.json').exists())
            restore_race(directory)
            self.assertEqual(config.read_bytes(),original.replace(b'name=Pat',b'name=New'))

    def test_unchanged_file_has_byte_exact_rollback(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
            directory=Path(folder);config=directory/'game.ini';config.write_bytes(self.config())
            with race_mode(directory,1,3):pass
            self.assertEqual(config.read_bytes(),self.config())

    def test_invalid_selection_never_changes_settings(self):
        for pair in [(-1,0),(7,1),(0,7)]:
            with self.assertRaises(ValueError):race_settings(*pair)

    def test_nested_engine_config_recovers_from_saved_relative_path(self):
        profile='pmr-timing';catalog=race_catalog(profile)
        original=(ROOT/'work/PMR-menu-timing/data/game.ini').read_bytes()
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
            directory=Path(folder);data=directory/'data';data.mkdir()
            config=data/'game.ini';config.write_bytes(original)
            with patch('davilex.launch.verified_engine',return_value=data/'spel.dat'):
                with race_mode(directory,catalog['tracks'][0]['id'],catalog['cars'][1]['id'],profile):
                    self.assertNotEqual(config.read_bytes(),original)
                    # Recover as a subsequent launch would after interruption.
                    restore_race(directory)
                    self.assertEqual(config.read_bytes(),original)
            self.assertFalse((directory/'game.ini').exists())


class ToolkitTests(unittest.TestCase):
    def test_incomplete_copy_is_reported_without_overwriting_files(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
            root=Path(folder);directory=root/'work/A2IV-resolution-1280x720'
            directory.mkdir(parents=True);saved=directory/'settings.txt';saved.write_text('keep')
            with patch('davilex.toolkit.ROOT',root),self.assertRaisesRegex(ValueError,'Incomplete resolution copy'):
                working_copy('A2 Racer IV',1280,720)
            self.assertEqual(saved.read_text(),'keep')

    def test_failed_preparation_is_never_published_as_a_playable_copy(self):
        from tools import prepare_resolution
        import sys
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
            root=Path(folder);source=root/'work/source';source.mkdir(parents=True)
            engine=source/'spel.dat';engine.write_bytes(b'source')
            destination=root/'work/finished'
            with patch.object(prepare_resolution,'ROOT',root), \
                 patch.dict(prepare_resolution.SOURCES,{'a2racer4-resolution':('source','test','A2IV')}), \
                 patch.object(prepare_resolution,'verified_engine',return_value=engine), \
                 patch.object(prepare_resolution,'patch_engine',return_value=(b'patched',{})), \
                 patch.object(prepare_resolution,'select_resolution'), \
                 patch('davilex.hud_layout.prepare_layout',side_effect=ValueError('Simulated HUD failure')), \
                 patch.object(sys,'argv',['prepare_resolution','--width','1280','--height','720','--destination',str(destination)]):
                with self.assertRaisesRegex(ValueError,'Simulated HUD failure'):prepare_resolution.main()
            self.assertFalse(destination.exists())
            stages=list(destination.parent.glob('.resolution-stage-*'))
            self.assertEqual(len(stages),1)
            self.assertEqual((stages[0]/'spel.dat').read_bytes(),b'patched')

    def test_each_title_uses_its_own_available_track_car_ids_and_ini_schema(self):
        from davilex.launch import verified_engine
        from davilex.translate import ini_lines
        for game,profile in GAMES.items():
            with self.subTest(game=game):
                directory,classic=working_copy(game)
                engine=verified_engine(directory,classic)
                config=engine.parent/('Ini/game.ini' if profile.startswith('europe') else 'game.ini')
                original=config.read_bytes();choices=race_catalog(profile)
                track=choices['tracks'][-1]['id'];car=choices['cars'][-1]['id']
                changed=update_ini(original,race_settings(track,car,profile))
                values={(s,k):m[4].strip() for _,s,k,_,m in ini_lines(changed)}
                self.assertEqual(values['etappe','etappe'],str(track))
                self.assertEqual(values['player','car'],str(car))
                with self.assertRaises(ValueError):race_settings(999,car,profile)
                if profile.startswith('europe'):
                    self.assertEqual(values['etappe','british'],'1')
                    self.assertEqual(values['player','country'],str(choices['cars'][-1]['country']))
                if game=='A2 Racer IV':
                    self.assertFalse(any(c['id']>=10 for c in choices['cars']))
                if game=='Autobahn Raser II':
                    self.assertFalse(any(t['id'] in (6,7) for t in choices['tracks']))

    def test_classic_uses_confirmed_menu_copy(self):
        directory,profile=working_copy('A2 Racer II')
        self.assertEqual(directory,ROOT/'work/A2II-menu-cycle')
        self.assertEqual(profile,'a2ii-timing')

    def test_invalid_resolution_rejected_before_preparation(self):
        for width,height in [(100,480),(1080,1920),(9000,600),(1920,None)]:
            with self.assertRaises(ValueError):working_copy('A2 Racer II',width,height)

    def test_full_game_uses_menu_cycle_not_direct_engine(self):
        with patch('davilex.rendering.ensure_depth_precision'),patch('davilex.toolkit.check_idle'),patch('davilex.installed.installed_game',return_value=nullcontext((ROOT/'work/A2II-menu-cycle','a2ii-timing'))),patch('davilex.menu.verify_copy',return_value=(Path('menu'),Path('spel.dat'))), \
             patch('davilex.quickrace.restore_race'),patch('davilex.translate.restore'), \
             patch('davilex.controller.restore'),patch('davilex.display_guard.preserve_display',return_value=nullcontext()), \
             patch('davilex.menu.cycle',return_value=0) as cycle:
            self.assertEqual(run_game('A2 Racer II'),0)
            self.assertEqual(cycle.call_args.args[:2],(ROOT/'work/A2II-menu-cycle','a2ii-timing'))


if __name__=='__main__':unittest.main()

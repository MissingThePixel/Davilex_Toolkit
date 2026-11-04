from pathlib import Path
import subprocess
import json
import tempfile
import unittest
from unittest.mock import patch
from davilex.menu import cycle,read_menu_signal

ROOT=Path(__file__).resolve().parents[1]


class MenuTests(unittest.TestCase):
    def test_resolution_choice_is_reasserted_only_before_engine(self):
        with patch('davilex.resolution.select_resolution') as select:
            result,calls=self.run_sequence([40,0,255],profile='a2racer4-resolution')
            self.assertEqual(result,0)
            select.assert_called_once_with(Path(calls[1].args[0][0]))

    def run_sequence(self,codes,skip_intro=False,profile='a2ii-timing'):
        root=ROOT/'.test-work'
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as temp:
            folder=Path(temp)
            (folder/'menu.ini').write_bytes(b'[GENERAL]\r\nEXITCODE=40\r\n')
            sequence=iter(codes)
            def run_stage(command,**kwargs):
                code=next(sequence)
                if profile!='a2ii-timing' and Path(command[0]).name=='menu.dat':
                    (folder/'menu.ini').write_text(f'[GENERAL]\nEXITCODE={code}\n',encoding='ascii')
                    return subprocess.CompletedProcess(command,0)
                return subprocess.CompletedProcess(command,code)
            with patch('davilex.menu.prepare_media'), \
                 patch('davilex.menu.verify_copy',return_value=(folder/'menu.dat',folder/'spel.dat')), \
                 patch('davilex.menu.subprocess.run',side_effect=run_stage) as run:
                result=cycle(folder,skip_intro=skip_intro,profile=profile)
                calls=run.call_args_list
            return result,calls

    def test_start_engine_return_menu_then_quit(self):
        result,calls=self.run_sequence([40,0,0])
        self.assertEqual(result,0)
        self.assertEqual([Path(c.args[0][0]).name for c in calls],['menu.dat','spel.dat','menu.dat'])
        self.assertEqual(calls[0].args[0][1:],['\\FIRST'])
        self.assertEqual(calls[2].args[0][1:],[])
        for call in calls:
            self.assertEqual(call.kwargs['env']['NOCD'],'D')
            self.assertEqual(call.kwargs['cwd'],Path(call.args[0][0]).parent)

    def test_quitting_menu_does_not_start_engine(self):
        result,calls=self.run_sequence([0])
        self.assertEqual(len(calls),1)

    def test_observed_quit_255_is_success(self):
        result,calls=self.run_sequence([40,0,255])
        self.assertEqual(result,0)
        self.assertEqual(len(calls),3)

    def test_failed_engine_stops_cycle(self):
        result,calls=self.run_sequence([40,17])
        self.assertEqual(result,17)
        self.assertEqual(len(calls),2)

    def test_explicit_skip_intro_omits_first_argument(self):
        result,calls=self.run_sequence([0],skip_intro=True)
        self.assertEqual(calls[0].args[0][1:],[])

    def test_failed_preflight_never_runs_menu(self):
        with patch('davilex.menu.verify_copy',side_effect=ValueError('build mismatch')), \
             patch('davilex.menu.subprocess.run') as run:
            with self.assertRaises(ValueError): cycle(ROOT/'work'/'bad-copy')
            run.assert_not_called()

    def test_later_menus_use_firsttime_then_default(self):
        for profile in ('a2racer4-vram','autobahn2-timing','london-timing'):
            with self.subTest(profile=profile):
                result,calls=self.run_sequence([40,0,0],profile=profile)
                self.assertEqual(result,0)
                self.assertEqual(calls[0].args[0][1:],['/FirstTime'])
                self.assertEqual(calls[2].args[0][1:],['/Default'])

    def test_stale_ini_start_signal_is_cleared(self):
        root=ROOT/'.test-work'
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as temp:
            folder=Path(temp)
            ini=folder/'menu.ini'
            ini.write_text('[GENERAL]\nEXITCODE=40\n',encoding='ascii')
            def close_without_writing(command,**kwargs):
                self.assertEqual(read_menu_signal(ini),255)
                return subprocess.CompletedProcess(command,0)
            with patch('davilex.menu.verify_copy',return_value=(folder/'menu.exe',folder/'spel.dat')), \
                 patch('davilex.menu.subprocess.run',side_effect=close_without_writing) as run:
                self.assertEqual(cycle(folder,profile='london-timing'),0)
                run.assert_called_once()
            event=json.loads((folder/'launcher-events.jsonl').read_text())
            self.assertEqual(event['exit_code'],0)
            self.assertEqual(event['menu_signal'],255)

    def test_remaining_profiles_keep_menu_and_engine_directories_separate(self):
        root=ROOT/'.test-work'
        root.mkdir(exist_ok=True)
        for profile,menu_dir,engine_dir,signal_name,first in (
                ('holiday','','','menu.ini','/FirstTime'),
                ('pmr','data','data','menu.ini','/FirstTime'),
                ('europe','Menu','game','GameMenu.ini','/FirstTime')):
            with self.subTest(profile=profile),tempfile.TemporaryDirectory(dir=root) as temp:
                folder=Path(temp)
                menu=folder/menu_dir/'menu.exe'
                engine=folder/engine_dir/'spel.dat'
                menu.parent.mkdir(exist_ok=True)
                engine.parent.mkdir(exist_ok=True)
                signal=menu.parent/signal_name
                signal.write_text('[General]\nExitCode=40\n')
                calls=[]
                def runner(command,**kwargs):
                    calls.append((command,kwargs))
                    if Path(command[0])==menu:
                        self.assertEqual(read_menu_signal(signal),255)
                        value=40 if len(calls)==1 else 255
                        signal.write_text(f'[General]\nExitCode={value}\n')
                    return subprocess.CompletedProcess(command,0)
                with patch('davilex.menu.verify_copy',return_value=(menu,engine)) as verify,patch('davilex.menu.prepare_media'),patch('davilex.menu.ensure_pmr_true_colour',return_value={}),patch('davilex.europe_tuning.ensure_valid_tuning',return_value=[]) as tuning:
                    self.assertEqual(cycle(folder,profile=profile,runner=runner),0)
                if profile=='europe':tuning.assert_called_once_with(engine)
                else:tuning.assert_not_called()
                self.assertEqual(verify.call_count,4)
                for call in verify.call_args_list:
                    self.assertEqual(call.args,(folder.resolve(),profile))
                self.assertEqual(calls[0][0][1:],[first])
                self.assertEqual(calls[2][0][1:],['/Default'])
                self.assertEqual([c[1]['cwd'] for c in calls],[menu.parent,engine.parent,menu.parent])

    def test_pmr_colour_policy_runs_after_every_menu_selection(self):
        root=ROOT/'.test-work'
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as temp:
            folder=Path(temp)
            data=folder/'data'
            data.mkdir()
            menu=data/'menu.exe'
            engine=data/'spel.dat'
            ini=data/'menu.ini'
            renderer=data/'Raser.ini'
            ini.write_text('[GENERAL]\nEXITCODE=255\n')
            renderer.write_text('[PROGRAM]\nRESOLUTION=3\n')
            menus=0
            engines=0
            def runner(command,**kwargs):
                nonlocal menus,engines
                if Path(command[0])==menu:
                    menus+=1
                    ini.write_text(f'[GENERAL]\nEXITCODE={40 if menus<=2 else 255}\n')
                    # The legacy menu writes its default 8-bit choice each time.
                    renderer.write_text('[PROGRAM]\nRESOLUTION=1\n')
                else:
                    engines+=1
                    self.assertEqual(renderer.read_text(),'[PROGRAM]\nRESOLUTION=3\n')
                return subprocess.CompletedProcess(command,0)
            with patch('davilex.menu.verify_copy',return_value=(menu,engine)):
                self.assertEqual(cycle(folder,profile='pmr-timing',runner=runner),0)
            self.assertEqual((menus,engines),(3,2))
            events=[json.loads(line) for line in (data/'launcher-events.jsonl').read_text().splitlines()]
            for event in [e for e in events if e['stage']=='engine']:
                self.assertEqual(event['configuration_changes']['PROGRAM/RESOLUTION']['after'],3)

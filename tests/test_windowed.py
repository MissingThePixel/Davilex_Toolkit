from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from davilex.launch import ROOT
from davilex import windowed
from davilex.translate import ini_lines
from davilex.rendering import graphics_backend
import os
from contextlib import nullcontext
import subprocess


class WindowedBackendTests(unittest.TestCase):
    @staticmethod
    def locked():
        error=PermissionError('simulated DLL image lock');error.winerror=5;return error

    def test_exit_cleanup_retries_a_transient_image_lock(self):
        unlink=Path.unlink;attempts=[]
        def temporary_lock(path,*args,**kwargs):
            if path.name=='dxwrapper.dll' and len(attempts)<2:
                attempts.append(path);raise self.locked()
            return unlink(path,*args,**kwargs)
        with patch.object(Path,'unlink',temporary_lock),patch.object(windowed.time,'sleep'):
            with windowed.windowed_mode(self.game,'london-resolution',backend='dxwrapper'):pass
        self.assertEqual(len(attempts),2)
        self.assertFalse((self.game/'dxwrapper.dll').exists())
        self.assertFalse((self.root/'backups/windowed-renderer/active.json').exists())

    def test_persistent_exit_lock_keeps_journal_and_recovers_later(self):
        unlink=Path.unlink
        def locked_dll(path,*args,**kwargs):
            if path.name=='dxwrapper.dll':raise self.locked()
            return unlink(path,*args,**kwargs)
        with patch.object(Path,'unlink',locked_dll),patch.object(windowed,'RESTORE_WAIT_SECONDS',0):
            with windowed.windowed_mode(self.game,'london-resolution',backend='dxwrapper'):pass
            self.assertTrue((self.root/'backups/windowed-renderer/active.json').exists())
            with self.assertRaises(PermissionError):windowed.restore(self.game)
        self.assertTrue(windowed.restore(self.game))
        self.assertFalse((self.game/'dxwrapper.dll').exists())
        self.assertEqual(self.dll.read_bytes(),b'original renderer')

    def test_deferred_cleanup_does_not_hide_unrecognised_file_changes(self):
        with self.assertRaisesRegex(ValueError,'changed'):
            with windowed.windowed_mode(self.game,'london-resolution',backend='dxwrapper'):
                (self.game/'dxwrapper.dll').write_bytes(b'an unrelated modification')
        self.assertTrue((self.root/'backups/windowed-renderer/active.json').exists())

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'work');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.game=self.root/'game';self.game.mkdir()
        self.dll=self.game/'ddraw.dll';self.dll.write_bytes(b'original renderer')
        self.patches=[patch.object(windowed,'journal_folder',return_value=self.root/'backups'),
                      patch('davilex.menu.verify_copy',return_value=(self.game/'menu.exe',self.game/'spel.dat'))]
        for item in self.patches:item.start();self.addCleanup(item.stop)

    def test_windowed_translation_does_not_override_the_game_resolution(self):
        payload=windowed.payloads()
        values={(s,k):m[4].strip() for _,s,k,_,m in ini_lines(payload['dgVoodoo.conf'])}
        self.assertEqual(values['general','fullscreenmode'],'false')
        self.assertEqual(values['generalext','desktopbitdepth'],'32')
        self.assertEqual(values['directx','resolution'],'unforced')
        self.assertEqual(values['directx','appcontrolledscreenmode'],'false')
        self.assertEqual(values['directxext','depthbuffersbitdepth'],'forcemin24bit')
        self.assertTrue(payload['ddraw.dll'].startswith(b'MZ'))

    def test_custom_resolution_is_advertised_in_virtual_mode_list(self):
        payload=windowed.payloads(1278,718)
        values={(s,k):m[4].strip() for _,s,k,_,m in ini_lines(payload['dgVoodoo.conf'])}
        self.assertEqual(values['directxext','extraenumeratedresolutions'],'1278x718')
        self.assertEqual(values['directxext','enumeratedresolutionbitdepths'],'all')
        for dimensions in ((1280,None),('1280',720),(0,720)):
            with self.assertRaises(ValueError):windowed.payloads(*dimensions)

    def test_diagnostic_payloads_enable_api_trace_without_changing_display_settings(self):
        import hashlib
        payload=windowed.payloads(1280,720,diagnostic=True)
        for name,expected in windowed.DEBUG_HASHES.items():
            self.assertEqual(hashlib.sha256(payload[name]).hexdigest(),expected)
        values={(s,k):m[4].strip() for _,s,k,_,m in ini_lines(payload['dgVoodoo.conf'])}
        self.assertEqual(values['debug','maxtracelevel'],'1')
        self.assertEqual(values['directx','appcontrolledscreenmode'],'false')
        self.assertEqual(values['directxext','extraenumeratedresolutions'],'1280x720')
        self.assertEqual(values['debug','error'],'enable')

    def test_d3d9_translation_has_no_fps_cap_and_verifies_binary(self):
        import hashlib
        payload=windowed.dxwrapper_payloads()
        self.assertEqual(hashlib.sha256(payload['dxwrapper.dll']).hexdigest(),windowed.DXWRAPPER_HASH)
        self.assertEqual(hashlib.sha256(payload['ddraw.dll']).hexdigest(),windowed.DXWRAPPER_STUB_HASH)
        self.assertEqual(set(payload),{'ddraw.dll','dxwrapper.dll','dxwrapper.ini'})
        values={(s,k):m[4].strip() for _,s,k,_,m in ini_lines(payload['dxwrapper.ini'])}
        self.assertEqual(values['compatibility','dd7to9'],'1')
        self.assertEqual(values['compatibility','ddrawcompat'],'0')
        self.assertEqual(values['d3d9','enablewindowmode'],'1')
        self.assertEqual(values['d3d9','limitperframefps'],'0')

    def test_d3d9_backend_restores_existing_config_and_renderer_on_error(self):
        config=self.game/'dxwrapper.ini';config.write_bytes(b'Existing user configuration')
        with self.assertRaises(RuntimeError):
            with windowed.windowed_mode(self.game,'london-resolution',backend='dxwrapper'):
                self.assertNotEqual(config.read_bytes(),b'Existing user configuration')
                self.assertFalse((self.game/'D3DImm.dll').exists())
                raise RuntimeError('Test launch failure')
        self.assertEqual(config.read_bytes(),b'Existing user configuration')
        self.assertEqual(self.dll.read_bytes(),b'original renderer')

    def test_a2ii_wine_engine_stages_and_restores_colourkey_plugin(self):
        plugin=self.game/'davilex-colourkey.dll';plugin.write_bytes(b'Existing plugin')
        with patch('davilex.wine_overrides.running_under_wine',return_value=True):
            with windowed.windowed_mode(self.game,'a2ii-resolution',backend='dxwrapper'):
                self.assertTrue(plugin.read_bytes().startswith(b'MZ'))
                self.assertIn(b'davilex-colourkey.dll',(self.game/'dxwrapper.ini').read_bytes())
        self.assertEqual(plugin.read_bytes(),b'Existing plugin')

    def test_colourkey_plugin_is_not_enabled_for_menu_or_native_windows(self):
        with patch('davilex.wine_overrides.running_under_wine',return_value=True):
            for profile,executable in (('a2ii-resolution',self.game/'menu.exe'),('london-resolution',self.game/'menu.exe')):
                with windowed.windowed_mode(self.game,profile,backend='dxwrapper',executable=executable):
                    self.assertFalse((self.game/'davilex-colourkey.dll').exists())
        with patch('davilex.wine_overrides.running_under_wine',return_value=False):
            with windowed.windowed_mode(self.game,'a2ii-resolution',backend='dxwrapper'):
                self.assertFalse((self.game/'davilex-colourkey.dll').exists())

    def test_all_wine_d3d9_engine_profiles_share_the_guarded_conversion_plugin(self):
        from davilex.toolkit import GAMES
        with patch('davilex.wine_overrides.running_under_wine',return_value=True):
            for profile in GAMES.values():
                with self.subTest(profile=profile):
                    with windowed.windowed_mode(self.game,profile,backend='dxwrapper'):
                        self.assertTrue((self.game/'davilex-colourkey.dll').exists())
                    self.assertFalse((self.game/'davilex-colourkey.dll').exists())

    def test_renderer_follows_verified_menu_in_a_separate_folder(self):
        menu=self.game/'Menu/GameMenu.dat';menu.parent.mkdir();menu.write_bytes(b'menu')
        engine=self.game/'game/spel.exe';engine.parent.mkdir();engine.write_bytes(b'engine')
        with patch('davilex.menu.verify_copy',return_value=(menu,engine)):
            with windowed.windowed_mode(self.game,'europe-resolution',backend='dxwrapper',executable=menu):
                self.assertTrue((menu.parent/'dxwrapper.dll').exists())
                self.assertFalse((engine.parent/'ddraw.dll').exists())
            self.assertFalse((menu.parent/'dxwrapper.dll').exists())
            with self.assertRaisesRegex(ValueError,'verified'):
                with windowed.windowed_mode(self.game,'europe-resolution',backend='dxwrapper',executable=self.game/'other.exe'):pass

    def test_existing_renderer_is_restored_after_failure(self):
        with self.assertRaises(RuntimeError):
            with windowed.windowed_mode(self.game,'london-resolution'):
                self.assertNotEqual(self.dll.read_bytes(),b'original renderer')
                self.assertTrue((self.game/'D3DImm.dll').is_file())
                raise RuntimeError('Game failed')
        self.assertEqual(self.dll.read_bytes(),b'original renderer')
        self.assertFalse((self.game/'D3DImm.dll').exists())
        self.assertFalse((self.game/'dgVoodoo.conf').exists())

    def test_interrupted_session_can_be_recovered_before_next_patch(self):
        with windowed.windowed_mode(self.game,'london-resolution'):
            windowed.restore(self.game)
            self.assertEqual(self.dll.read_bytes(),b'original renderer')
        self.assertFalse((self.root/'backups/windowed-renderer/active.json').exists())

    def test_modified_renderer_configuration_is_preserved(self):
        with self.assertRaisesRegex(ValueError,'preserving'):
            with windowed.windowed_mode(self.game,'london-resolution'):
                (self.game/'dgVoodoo.conf').write_bytes(b'User edits')
        self.assertEqual((self.game/'dgVoodoo.conf').read_bytes(),b'User edits')
        self.assertTrue((self.root/'backups/windowed-renderer/active.json').exists())

    def test_wine_uses_both_native_directdraw_and_direct3d_wrappers(self):
        with patch.dict(os.environ,{'WINEDLLOVERRIDES':'d3d11=n;ddraw=b'}):
            with graphics_backend('dgvoodoo-windowed'):
                value=os.environ['WINEDLLOVERRIDES']
                self.assertIn('ddraw=n,b',value);self.assertIn('d3dimm=n,b',value)
                self.assertIn('d3d11=n',value)
            self.assertEqual(os.environ['WINEDLLOVERRIDES'],'d3d11=n;ddraw=b')


class WindowedMenuFlowTests(unittest.TestCase):
    def test_only_race_uses_the_windowed_backend_and_menu_gets_its_renderer_back(self):
        from davilex.installed import baseline
        from davilex.quickrace import update_ini
        from davilex.toolkit import run_game
        from davilex import wine_overrides
        from test_wine_overrides import MemoryRegistry
        import hashlib
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as temp:
            root=Path(temp);directory=root/'game';directory.mkdir()
            source=ROOT/'analysis/baseline'/baseline('london-resolution')['title']
            for path in source.iterdir():
                if path.suffix.casefold()=='.ini' or path.name.casefold() in ('menu.exe','spel.dat'):
                    (directory/path.name).write_bytes(path.read_bytes())
            normal=(ROOT/'work/London Racer-menu-cycle/ddraw.dll').read_bytes()
            registry=MemoryRegistry()
            calls=[]
            def runner(arguments,**options):
                stage=Path(arguments[0]).name.casefold();calls.append(stage)
                current=(directory/'ddraw.dll').read_bytes()
                if stage=='spel.dat':
                    self.assertEqual(registry.read(stage,'ddraw'),'native')
                    self.assertEqual(registry.read(stage,'d3dimm'),'native')
                    self.assertEqual(hashlib.sha256(current).hexdigest(),windowed.HASHES['ddraw.dll'])
                    self.assertTrue((directory/'dgVoodoo.conf').exists())
                    self.assertIn(b'1280x720',(directory/'dgVoodoo.conf').read_bytes())
                else:
                    self.assertEqual(registry.read(stage,'ddraw'),'native,builtin')
                    self.assertIsNone(registry.read(stage,'d3dimm'))
                    self.assertEqual(current,normal)
                    signal=40 if len(calls)==1 else 255
                    config=directory/'menu.ini';config.write_bytes(update_ini(config.read_bytes(),{('GENERAL','EXITCODE'):signal}))
                return subprocess.CompletedProcess(arguments,0)
            with patch.object(wine_overrides,'running_under_wine',return_value=True), \
                 patch.object(wine_overrides,'Registry',return_value=registry),patch.object(wine_overrides,'JOURNAL',root/'wine.json'), \
                 patch('davilex.toolkit.check_idle'),patch('davilex.display_guard.preserve_display',return_value=nullcontext()), \
                 patch('davilex.installed.journal_folder',return_value=root/'backups'),patch.object(windowed,'journal_folder',return_value=root/'backups'):
                result=run_game('London Racer',1280,720,renderer='dgvoodoo-windowed',install=directory,runner=runner)
            self.assertEqual(result,0);self.assertEqual(calls,['menu.exe','spel.dat','menu.exe'])
            self.assertFalse((directory/'D3DImm.dll').exists())
            self.assertEqual(registry.values,{})

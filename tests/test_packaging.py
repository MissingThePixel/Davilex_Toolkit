import os
from pathlib import Path
import sys
import tkinter as tk
import unittest
from unittest.mock import patch
from davilex.paths import command,resources
from davilex.rendering import depth_configuration,graphics_backend


class PortableTests(unittest.TestCase):
    def test_viewer_launcher_dispatch_is_case_insensitive(self):
        from davilex.entry import default_mode
        for name in ('RCS Explorer.exe','rcs explorer.exe','RCS EXPLORER.EXE'):
            self.assertEqual(default_mode(name),'--viewer')
        self.assertEqual(default_mode('Davilex Toolkit.exe'),'--launcher')
    def test_external_process_does_not_inherit_bundled_library_path(self):
        from davilex.process import external_environment
        with patch.object(sys,'_MEIPASS','C:/bundle/_internal',create=True):
            environment={'PATH':os.pathsep.join(('C:/Windows/System32','C:/bundle/_internal','C:/bundle/_internal/numpy.libs','C:/UserTools')),'OTHER':'keep'}
            cleaned=external_environment(environment)
            self.assertNotIn('_internal',cleaned['PATH'])
            self.assertIn('System32',cleaned['PATH']);self.assertIn('UserTools',cleaned['PATH'])
            self.assertEqual(cleaned['OTHER'],'keep')
    def test_frozen_dispatch_does_not_try_to_run_python_modules(self):
        with patch.object(sys,'frozen',True,create=True),patch.object(sys,'_MEIPASS','C:/bundle/_internal',create=True):
            self.assertEqual(command('toolkit','London Racer'),[sys.executable,'--toolkit','London Racer'])
            self.assertEqual(resources(),Path('C:/bundle/_internal/resources'))

    def test_depth_policy_retains_other_options_and_is_idempotent(self):
        original=b'# Player settings\r\nFrameRateLimit = off\r\nDepthFormat = 16 ; test\r\n'
        changed=depth_configuration(original)
        self.assertEqual(changed,original.replace(b'DepthFormat = 16',b'DepthFormat = 24'))
        self.assertEqual(depth_configuration(changed),changed)
        self.assertEqual(depth_configuration(b'DepthFormat = 32\n'),b'DepthFormat = 32\n')
        self.assertIn(b'DepthFormat = 24',depth_configuration(b''))

    def test_depth_policy_rejects_ambiguous_or_invalid_configuration(self):
        for data in (b'DepthFormat=16\nDepthFormat=24\n',b'DepthFormat=invalid\n'):
            with self.assertRaises(ValueError):depth_configuration(data)

    def test_wine_dll_overrides_are_local_and_restore_after_errors(self):
        original='ddraw,d3d8=n;winmm=b;other=n,b'
        with patch.dict(os.environ,{'WINEDLLOVERRIDES':original}):
            with self.assertRaises(RuntimeError):
                with graphics_backend('wine',True):
                    value=os.environ['WINEDLLOVERRIDES']
                    self.assertIn('ddraw=b',value);self.assertIn('d3d8=n',value)
                    self.assertIn('winmm=n,b',value);self.assertIn('other=n,b',value)
                    raise RuntimeError()
            self.assertEqual(os.environ['WINEDLLOVERRIDES'],original)

    def test_native_english_checkbox_locked_without_losing_optional_preference(self):
        from davilex.launcher import Launcher
        root=tk.Tk();root.withdraw()
        try:
            app=Launcher(root)
            app.game.set('A2 Racer IV');app.refresh();app.english.set(False)
            for title in ('London Racer','Holiday Racer','Europe Racer'):
                app.game.set(title);app.refresh()
                self.assertTrue(app.english.get());self.assertTrue(app.english_box.instate(['disabled']))
            app.game.set('Autobahn Raser II');app.refresh()
            self.assertFalse(app.english.get());self.assertFalse(app.english_box.instate(['disabled']))
        finally:root.destroy()

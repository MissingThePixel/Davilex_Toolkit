import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from davilex import wine_overrides as wine
from davilex.paths import ROOT


class MemoryRegistry:
    def __init__(self,values=None):self.values=dict(values or {})
    def read(self,app,name):return self.values.get((app,name))
    def write(self,app,name,value):
        if value is None:self.values.pop((app,name),None)
        else:self.values[app,name]=value


class WineOverrideTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(dir=ROOT/'work');self.addCleanup(temp.cleanup)
        self.journal=Path(temp.name)/'recovery.json'
        self.registry=MemoryRegistry({('spel.dat','ddraw'):'builtin',('spel.dat','dxgi'):'native'})

    def context(self,renderer='dgvoodoo-windowed',controller=False):
        return wine.application_overrides('spel.dat',renderer,controller,backend=self.registry,journal=self.journal)

    def test_real_registry_scope_is_game_specific(self):
        self.assertEqual(wine.key_for('spel.dat'),r'Software\Wine\AppDefaults\spel.dat\DllOverrides')
        with self.assertRaises(ValueError):wine.key_for('..\\other.exe')

    def test_strict_native_wrapper_and_original_values_restored_on_failure(self):
        before=self.registry.values.copy()
        with self.assertRaises(RuntimeError):
            with self.context():
                self.assertEqual(self.registry.read('spel.dat','ddraw'),'native')
                self.assertEqual(self.registry.read('spel.dat','d3dimm'),'native')
                self.assertEqual(self.registry.read('spel.dat','dxgi'),'native')
                self.assertTrue(self.journal.exists())
                raise RuntimeError('Game failed')
        self.assertEqual(self.registry.values,before)
        self.assertFalse(self.journal.exists())

    def test_builtin_choice_and_controller_are_scoped_together(self):
        with self.context('wine',True):
            self.assertEqual(self.registry.read('spel.dat','ddraw'),'builtin')
            self.assertEqual(self.registry.read('spel.dat','dinput'),'native,builtin')
            self.assertEqual(self.registry.read('spel.dat','winmm'),'native,builtin')
            self.assertIsNone(self.registry.read('spel.dat','d3dimm'))
        self.assertIsNone(self.registry.read('spel.dat','winmm'))

    def test_d3d9_translation_overrides_only_directdraw(self):
        with self.context('dxwrapper'):
            self.assertEqual(self.registry.read('spel.dat','ddraw'),'native')
            self.assertIsNone(self.registry.read('spel.dat','d3d9'))
            self.assertIsNone(self.registry.read('spel.dat','d3dimm'))

    def test_interrupted_override_recovery(self):
        self.journal.write_text(json.dumps([{'app':'spel.dat','name':'ddraw','before':'native,builtin','after':'builtin'}]))
        wine.restore(self.registry,self.journal)
        self.assertEqual(self.registry.read('spel.dat','ddraw'),'native,builtin')
        self.assertFalse(self.journal.exists())

    def test_user_change_is_preserved_with_recovery_record(self):
        with self.assertRaisesRegex(ValueError,'preserving'):
            with self.context():self.registry.write('spel.dat','ddraw','native,builtin')
        self.assertEqual(self.registry.read('spel.dat','ddraw'),'native,builtin')
        self.assertTrue(self.journal.exists())

    def test_native_windows_does_not_touch_registry(self):
        with patch.object(wine,'running_under_wine',return_value=False),patch.object(wine,'Registry') as registry:
            with wine.application_overrides('spel.dat','dgvoodoo-windowed',journal=self.journal):pass
            registry.assert_not_called()
        self.assertFalse(self.journal.exists())

    def test_corrupt_journal_cannot_target_unrelated_registry_values(self):
        self.journal.write_text(json.dumps([{'app':'spel.dat','name':'dxgi','before':None,'after':'native'}]))
        with self.assertRaises(ValueError):wine.restore(self.registry,self.journal)
        self.assertEqual(self.registry.read('spel.dat','dxgi'),'native')

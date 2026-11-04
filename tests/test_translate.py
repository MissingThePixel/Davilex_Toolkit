from pathlib import Path
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch
from davilex.translate import english_mode,restore,TOKEN,english_hud_value,select_english_hud

ROOT=Path(__file__).resolve().parents[1]


class TranslationTests(unittest.TestCase):
    def test_unfinished_english_hud_preserves_amounts_and_format_tokens(self):
        self.assertEqual(english_hud_value('STRAFE: DM %d'),'FINE: DM %d')
        self.assertEqual(english_hud_value('4 SEC ONKWETSBAAR'),'4 SEC INVINCIBLE')
        self.assertEqual(english_hud_value('+30% REPARATIE'),'+30% REPAIR')
        self.assertEqual(english_hud_value('SNELHEID'),'SPEED')
        self.assertEqual(english_hud_value('SPEED'),'SPEED')

    def test_menu_language_reset_is_corrected_without_touching_other_settings(self):
        with tempfile.TemporaryDirectory(prefix='translation-test-',dir=ROOT/'work') as folder:
            path=Path(folder);config=path/'language.ini'
            original=b'[SETTINGS]\nLANGUAGE=0\nTEXT_COUNT=56\n[ENGELS]\n54=SPEED\n'
            config.write_bytes(original)
            select_english_hud(path/'spel.dat')
            self.assertEqual(config.read_bytes(),original.replace(b'LANGUAGE=0',b'LANGUAGE=1'))
    def test_restore_preserves_game_written_settings_and_original_encoding(self):
        with tempfile.TemporaryDirectory(prefix='translation-test-',dir=ROOT/'work') as folder:
            directory=Path(folder);config=directory/'menu.ini'
            original=b'[MENUSTRINGS]\r\n1=Zur\xfcck\r\n[GENERAL]\r\nEXITCODE=40\r\n'
            translated=original.replace(b'Zur\xfcck',b'Back')
            config.write_bytes(original)
            edits=[{'section':'menustrings','key':'1','occurrence':0,'before':'Zurück','after':'Back'}]
            fake=[{'path':config,'original':original,'patched':translated,'edits':edits}]
            report={'title':'test'}
            with patch('davilex.translate.patches',return_value=(fake,report)):
                with english_mode(directory,'translation-test'):
                    self.assertIn(b'Back',config.read_bytes())
                    config.write_bytes(config.read_bytes().replace(b'EXITCODE=40',b'EXITCODE=255'))
            self.assertEqual(config.read_bytes(),original.replace(b'EXITCODE=40',b'EXITCODE=255'))
            self.assertFalse((directory/'.english-restore/manifest.json').exists())
        (ROOT/'analysis/english-translation-test-coverage.json').unlink(missing_ok=True)

    def test_exception_restores_exact_bytes(self):
        with tempfile.TemporaryDirectory(prefix='translation-test-',dir=ROOT/'work') as folder:
            directory=Path(folder);config=directory/'menu.ini'
            original=b'[UI]\ncaption=Hallo\n';translated=original.replace(b'Hallo',b'Hello')
            config.write_bytes(original)
            fake=[{'path':config,'original':original,'patched':translated,'edits':[]}]
            with patch('davilex.translate.patches',return_value=(fake,{})):
                with self.assertRaises(RuntimeError):
                    with english_mode(directory,'translation-test'):raise RuntimeError('Simulated launch failure')
            self.assertEqual(config.read_bytes(),original)
        (ROOT/'analysis/english-translation-test-coverage.json').unlink(missing_ok=True)


if __name__=='__main__':unittest.main()

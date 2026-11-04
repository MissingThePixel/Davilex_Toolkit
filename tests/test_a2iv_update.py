"""Run with Python 3 from the toolkit root: python tools/a2iv-update/test_extension.py"""
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from davilex import a2iv_text as patch
from davilex.menu_media import desktop_menu_bytes


ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / 'davilex/a2iv_dialogue.json').read_text(encoding='utf-8'))


class DialogueTests(unittest.TestCase):
    def setUp(self):
        self.before = (ROOT / 'analysis/baseline/A2 Racer 4/communi.ini').read_bytes()

    def test_complete_text_only_translation(self):
        after, count = patch.dialogue_patch(self.before, CATALOG)
        self.assertEqual(count, 149)
        self.assertEqual(len(CATALOG['entries']), 149)
        before_lines = self.before.splitlines(keepends=True)
        after_lines = after.splitlines(keepends=True)
        self.assertEqual(len(before_lines), len(after_lines))
        for before, translated in zip(before_lines, after_lines):
            if before != translated:
                self.assertEqual(before.split(b',', 7)[:7], translated.split(b',', 7)[:7])
                self.assertEqual(before.endswith(b'\r\n'), translated.endswith(b'\r\n'))
        self.assertEqual(patch.dialogue_patch(after, CATALOG), (after, 0))

    def test_unrecognised_text_and_metadata_are_preserved_by_rejection(self):
        for old, new in [(b'ik krijg jullie wel', b'unknown dialogue'),
                         (b'0=cwa05_00,', b'0=UNKNOWN,')]:
            with self.assertRaises(ValueError):
                patch.dialogue_patch(self.before.replace(old, new, 1), CATALOG)

    def test_missing_and_duplicate_entries_are_rejected(self):
        line = next(line for line in self.before.splitlines(keepends=True) if line.startswith(b'0=cwa05_00,'))
        for candidate in [self.before.replace(line, b''), self.before.replace(line, line + line)]:
            with self.assertRaises(ValueError):
                patch.dialogue_patch(candidate, CATALOG)

    def test_no_literal_csv_delimiters_in_translation(self):
        for entry in CATALOG['entries']:
            self.assertNotIn(',', entry['target'])
            self.assertNotIn('\n', entry['target'])
            entry['target'].encode('cp1252')


class MenuTests(unittest.TestCase):
    def test_only_two_verified_function_prologues_change(self):
        original = (ROOT / 'analysis/baseline/A2 Racer 4/menu.exe').read_bytes()
        output = desktop_menu_bytes(original)
        changed = {i for i, (a, b) in enumerate(zip(original, output)) if a != b}
        offsets = [a - 0x400000 - 0x1000 + 0x400 for a in (0x481634, 0x481588)]
        self.assertEqual(changed, {i for offset in offsets for i in range(offset, offset + 3)})
        for offset in offsets:
            self.assertEqual(output[offset:offset + 3], b'\xb0\x01\xc3')
        self.assertEqual(len(original), len(output))
        with self.assertRaises(ValueError):
            desktop_menu_bytes(output)



class StoryTests(unittest.TestCase):
    def test_biographies_and_briefings_preserve_gameplay_values(self):
        before = (ROOT / 'analysis/baseline/A2 Racer 4/static.ini').read_bytes()
        after, count = patch.static_patch(before, CATALOG)
        self.assertEqual(count, 71)
        self.assertEqual(patch.static_patch(after, CATALOG), (after, 0))
        before_lines = before.splitlines()
        after_lines = after.splitlines()
        self.assertEqual(len(before_lines), len(after_lines))
        changed = 0
        for old, new in zip(before_lines, after_lines):
            if old == new:
                continue
            changed += 1
            if b'=' not in old:
                self.assertTrue(old.startswith(b'Helaas heb ik slecht nieuws'))
                continue
            old_key, old_value = old.split(b'=', 1)
            new_key, new_value = new.split(b'=', 1)
            self.assertEqual(old_key, new_key)
            if old_key.upper().startswith(b'SPECS'):
                self.assertEqual(old_value.split(b',')[1:], new_value.split(b',')[1:])
            self.assertNotIn(old_key.lower(), [b'accell', b'speed', b'handling', b'brakes',
                b'qualifyposition', b'chasetime', b'indexingame', b'difficulty', b'charix', b'trackix'])
        self.assertEqual(changed, 71)

    def test_edited_biography_is_rejected(self):
        before = (ROOT / 'analysis/baseline/A2 Racer 4/static.ini').read_bytes()
        with self.assertRaises(ValueError):
            patch.static_patch(before.replace(b'Deze wilde, katachtige dame', b'Unknown custom biography'), CATALOG)


class SourceIntegrationTests(unittest.TestCase):
    def test_optional_english_flow_translates_and_restores_both_new_files(self):
        import tempfile
        from unittest.mock import patch as mock_patch
        from davilex import translate
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
            directory=Path(folder);(directory/'analysis').mkdir()
            originals={}
            for name in ('communi.ini','static.ini','menu.ini','menucaps.ini','language.ini'):
                data=(ROOT/'analysis/baseline/A2 Racer 4'/name).read_bytes()
                (directory/name).write_bytes(data);originals[name]=data
            with mock_patch('davilex.menu.verify_copy'),mock_patch.object(translate,'ROOT',directory),mock_patch.object(translate,'resources',return_value=ROOT):
                with translate.english_mode(directory,'a2racer4-resolution') as report:
                    self.assertEqual(report['changed_entries']['communi.ini'],149)
                    self.assertEqual(report['changed_entries']['static.ini'],71)
                    self.assertNotEqual((directory/'communi.ini').read_bytes(),originals['communi.ini'])
                    self.assertNotEqual((directory/'static.ini').read_bytes(),originals['static.ini'])
            for name,data in originals.items():self.assertEqual((directory/name).read_bytes(),data)
            self.assertFalse((directory/'.english-restore/manifest.json').exists())

    def test_old_and_desktop_menu_variants_remain_recognised(self):
        import tempfile
        from unittest.mock import patch as mock_patch
        from davilex.menu import verify_copy
        from davilex.menu_media import shell_safe_menu
        original=(ROOT/'analysis/baseline/A2 Racer 4/menu.exe').read_bytes()
        variants=[original]
        for skip in (False,True):
            safe=shell_safe_menu(original,skip)
            variants.extend([safe,desktop_menu_bytes(safe)])
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
            directory=Path(folder)
            with mock_patch('davilex.menu.verified_engine',return_value=directory/'spel.dat'):
                for data in variants:
                    (directory/'menu.exe').write_bytes(data)
                    self.assertEqual(verify_copy(directory,'a2racer4-resolution')[0],directory/'menu.exe')
                (directory/'menu.exe').write_bytes(variants[-1]+b'unknown edit')
                with self.assertRaisesRegex(ValueError,'Unsupported menu build'):
                    verify_copy(directory,'a2racer4-resolution')


if __name__ == '__main__':
    unittest.main()

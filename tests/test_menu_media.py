from pathlib import Path
import hashlib
import tempfile
import unittest
from davilex.menu_media import intro_search_path,prepare_local_intro,shell_safe_menu,HIDE_CALLS,INTRO_CALL,holiday_menu,HOLIDAY_EDITS,europe_menu,EUROPE_HIDE_CALLS,ensure_pmr_true_colour
from davilex.display_guard import preserve_display
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


class MediaTests(unittest.TestCase):
    def test_drive_scan_reconstructs_movie_location_with_spaces(self):
        absolute=r'C:\Games\A2 Racer 4\intro1.mpg'
        value=intro_search_path(absolute)
        self.assertEqual('c:\\'+value,absolute[0].lower()+absolute[1:])
        self.assertEqual(intro_search_path(r'Z:\Racer\intro1.mpg'),r'Racer\intro1.mpg')
        for bad in (r'\\server\share\intro1.mpg',r'C:intro1.mpg',r'B:\intro1.mpg',r'C:\Gāmēs\intro1.mpg'):
            with self.subTest(path=bad),self.assertRaises(ValueError):intro_search_path(bad)

    def test_media_hash_failure_never_edits_config(self):
        root=ROOT/'.test-work'
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as temp:
            folder=Path(temp)
            (folder/'intro1.mpg').write_bytes(b'wrong movie')
            original=b'[GENERAL]\r\nINTROAVI=DATA\\INTRO1.MPG\r\nEXITCODE=40\r\n'
            (folder/'menu.ini').write_bytes(original)
            with self.assertRaises(ValueError):
                prepare_local_intro(folder,[{'path':'intro1.mpg','sha256':'0'*64}])
            self.assertEqual((folder/'menu.ini').read_bytes(),original)

    def test_media_relocation_preserves_other_settings_and_backup(self):
        root=ROOT/'.test-work'
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as temp:
            folder=Path(temp)
            movie=b'verified movie'
            (folder/'intro1.mpg').write_bytes(movie)
            original=b'[GENERAL]\r\nINTROAVI=old.mpg\r\nEXITCODE=40\r\n'
            (folder/'menu.ini').write_bytes(original)
            files=[{'path':'intro1.mpg','sha256':hashlib.sha256(movie).hexdigest()}]
            for value in (r'Games\First\intro1.mpg',r'Games\Moved\intro1.mpg'):
                with patch('davilex.menu_media.intro_search_path',return_value=value):
                    prepare_local_intro(folder,files)
                self.assertEqual((folder/'menu.ini').read_bytes(),original.replace(b'old.mpg',value.encode()))
                self.assertEqual((folder/'menu-before-local-media.ini').read_bytes(),original)

    def test_shell_patch_changes_only_two_calls_and_preserves_stack_cleanup(self):
        original=(ROOT/'analysis'/'baseline'/'A2 Racer 4'/'menu.exe').read_bytes()
        result=shell_safe_menu(original)
        self.assertEqual(len(result),len(original))
        allowed={offset+i for offset,_ in HIDE_CALLS for i in range(5)}
        self.assertEqual({i for i,(a,b) in enumerate(zip(original,result)) if a!=b},allowed)
        for offset,_ in HIDE_CALLS:
            self.assertEqual(result[offset:offset+5],bytes.fromhex('83c4089090'))
        with self.assertRaises(ValueError):shell_safe_menu(result)

    def test_intro_skip_preserves_media_gate_and_menu_initialization(self):
        original=(ROOT/'analysis'/'baseline'/'A2 Racer 4'/'menu.exe').read_bytes()
        safe=shell_safe_menu(original)
        skipped=shell_safe_menu(original,skip_intro=True)
        offset,_=INTRO_CALL
        self.assertEqual(skipped[:offset],safe[:offset])
        self.assertEqual(skipped[offset:offset+5],b'\x90'*5)
        self.assertEqual(skipped[offset+5:],safe[offset+5:])

    def test_holiday_intro_uses_original_continuation_and_scoped_shell_patch(self):
        import struct
        original=(ROOT/'analysis'/'baseline'/'Holiday Racer'/'Menu.exe').read_bytes()
        result=holiday_menu(original)
        self.assertEqual(len(result),len(original))
        allowed={o+i for o,b,_ in HOLIDAY_EDITS for i in range(len(b))}
        self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(original,result)) if a!=b))
        offset,_,_=HOLIDAY_EDITS[-1]
        self.assertEqual(0x48dafb+5+struct.unpack_from('<i',result,offset+1)[0],0x48dd44)
        with self.assertRaises(ValueError):holiday_menu(result)

    def test_europe_shell_patch_changes_only_two_hide_calls(self):
        original=(ROOT/'analysis'/'baseline'/'Europe Racer'/'Menu'/'GameMenu.dat').read_bytes()
        result=europe_menu(original)
        allowed={o+i for o,_ in EUROPE_HIDE_CALLS for i in range(5)}
        self.assertEqual(len(result),len(original))
        self.assertEqual({i for i,(a,b) in enumerate(zip(original,result)) if a!=b},allowed)
        for offset,_ in EUROPE_HIDE_CALLS:self.assertEqual(result[offset:offset+5],bytes.fromhex('83c4089090'))
        with self.assertRaises(ValueError):europe_menu(result)

    def test_pmr_colour_policy_preserves_dimensions_and_unrelated_settings(self):
        root=ROOT/'.test-work'
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as temp:
            folder=Path(temp)
            (folder/'data').mkdir()
            config=folder/'data'/'Raser.ini'
            for before,after in ((0,6),(1,3),(3,3),(4,4),(6,6),(7,7),(8,8),(9,9)):
                original=f'[PROGRAM]\r\nRESOLUTION={before}\r\nFOCUS=1\r\n[Other]\r\nRESOLUTION=99\r\n'.encode()
                config.write_bytes(original)
                changes=ensure_pmr_true_colour(folder)
                self.assertEqual(config.read_bytes(),original.replace(f'RESOLUTION={before}\r\n'.encode(),f'RESOLUTION={after}\r\n'.encode(),1))
                self.assertEqual(bool(changes),before!=after)


class DisplayTests(unittest.TestCase):
    def test_display_restored_after_exception_without_saving_preferences(self):
        class Display:
            def __init__(self):
                self.mode=bytes(220)
                self.restored=[]
            def capture(self):return self.mode
            def restore(self,mode):self.restored.append(mode)
        backend=Display()
        with self.assertRaisesRegex(RuntimeError,'game failed'):
            with preserve_display(backend):
                backend.mode=bytes(172)+b'\x80\x02'+bytes(46)
                raise RuntimeError('game failed')
        self.assertEqual(backend.restored,[bytes(220)])
        backend=Display()
        with preserve_display(backend):pass
        self.assertEqual(backend.restored,[])

from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch
from davilex.hud_layout import edge_layout

ROOT=Path(__file__).resolve().parents[1]


class HudLayoutTests(unittest.TestCase):
    def test_preparation_ignores_translation_recovery_overlays(self):
        from davilex.hud_layout import prepare_layout
        from davilex.resolution import SOURCES
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
            root=Path(folder);source=root/'work/source';target=root/'work/target'
            source.mkdir(parents=True);target.mkdir()
            original=(ROOT/'work/Holiday Racer-menu-timing/overlay.ini').read_bytes()
            (source/'overlay.ini').write_bytes(original);(target/'overlay.ini').write_bytes(original)
            backup=source/'.english-restore/files';backup.mkdir(parents=True)
            (backup/'overlay.ini').write_bytes(original)
            with patch('davilex.launch.ROOT',root),patch.dict(SOURCES,{'holiday-resolution':('source','holiday-timing','Holiday')}):
                report=prepare_layout(target,'holiday-resolution',1920,1080)
                self.assertEqual([r['file'] for r in report],['overlay.ini'])
                self.assertEqual(prepare_layout(target,'holiday-resolution',1920,1080),report)
            self.assertFalse((target/'.english-restore').exists())
    def test_holiday_groups_move_without_moving_central_strip_or_arrow(self):
        original=(ROOT/'work/Holiday Racer-menu-timing/overlay.ini').read_bytes()
        changed,report=edge_layout(original,'holiday-resolution',1920,1080)
        edits={e['section']:e for e in report}
        self.assertIn('speed',edits);self.assertIn('numbers',edits)
        self.assertNotIn('portraits',edits)
        self.assertIn('ovl_place_arrow',edits)
        margin=(1920*480/1080-640)/2
        self.assertAlmostEqual(float(edits['speed']['after'].split(';')[0]),margin,places=5)
        self.assertAlmostEqual(float(edits['numbers']['after'].split(';')[0]),margin-16,places=5)
        self.assertAlmostEqual(float(edits['ovl_place_arrow']['after'].split(';')[0])+margin,320,places=5)
        self.assertNotIn('string_pauze_header',edits)
        self.assertNotIn('string_quit_text',edits)
        self.assertEqual(original.count(b'Text'),changed.count(b'Text'))

    def test_holiday_moving_outline_shares_portrait_coordinates_at_both_aspects(self):
        from davilex.translate import ini_lines
        original=(ROOT/'work/Holiday Racer-menu-timing/overlay.ini').read_bytes()
        for width,height in [(3840,2560),(1920,1080)]:
            changed,_=edge_layout(original,'holiday-resolution',width,height)
            values={(s,k):m[4].strip() for _,s,k,_,m in ini_lines(changed)}
            # Simulate the manager copying each moving player's local position.
            # A shared parent makes the resulting world-space positions equal,
            # regardless of the rightward displacement of Speed.
            self.assertEqual(values['ovl_player_outline','parent'].casefold(),'portraits')
            for player in range(6):
                parent=values[f'player_{player}','parent'].casefold()
                self.assertEqual(parent,'portraits')
                self.assertEqual(values[parent,'position'],'0;0')
            self.assertNotEqual(values['speed','position'],'0;0')

    def test_four_three_layout_is_byte_identical(self):
        for profile,path in [('holiday-resolution','Holiday Racer-menu-timing/overlay.ini'),
                             ('pmr-resolution','PMR-menu-timing/data/overlay.ini'),
                             ('europe-resolution','Europe Racer-menu-timing/game/Ini/overlay.ini')]:
            original=(ROOT/'work'/path).read_bytes()
            changed,report=edge_layout(original,profile,640,480)
            self.assertEqual(changed,original);self.assertEqual(report,[])

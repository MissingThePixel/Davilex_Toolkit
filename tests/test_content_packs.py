import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from davilex import content_packs,addons,car_addons


class ContentPackTests(unittest.TestCase):
    def test_source_packs_include_both_kinds_and_exclude_withdrawn_research(self):
        expected={'a2iv':(4,3),'london':(4,10),'autobahn2':(6,7),'pmr':(2,7),'holiday':(0,6),'a2ii':(0,5)}
        all_keys=[]
        for donor,(tracks,cars)in expected.items():
            keys=content_packs.members(donor);all_keys.extend(keys)
            self.assertEqual(sum(k in addons.TRACK_ADDONS for k in keys),tracks)
            self.assertEqual(sum(k in car_addons.CATALOG for k in keys),cars)
        self.assertNotIn('london-oxford',all_keys);self.assertNotIn('london-thames',all_keys)
        self.assertEqual(len(all_keys),len(set(all_keys)))

    def test_options_follow_available_sources_without_individual_items_or_tags(self):
        with patch.object(content_packs,'available_sources',return_value={'autobahn2':Path('ARII')}):
            options=content_packs.choices()
        self.assertEqual({v['addon']for v in options},{'pack-all','europe-classics','pack-autobahn2'})
        self.assertIn('6 tracks, 7 cars',options[-1]['label'])
        self.assertTrue(all('experimental'not in v['label'].lower()for v in options+addons.choices()+car_addons.choices()))

    def test_import_all_uses_only_available_donors_and_original_classics(self):
        actions=[]
        with patch.object(content_packs,'available_sources',return_value={'autobahn2':Path('ARII'),'holiday':Path('HR')}),patch.object(addons,'install',side_effect=lambda d,k:actions.append(k)):
            result=content_packs.install(Path('ER'),'pack-all')
        self.assertEqual(actions,['europe-classics']+content_packs.members('autobahn2')+content_packs.members('holiday'))
        self.assertEqual(result['installed'],actions)

    def test_missing_source_fails_before_import_and_errors_name_partial_progress(self):
        with patch.object(content_packs,'available_sources',return_value={}),patch.object(addons,'install')as install:
            with self.assertRaisesRegex(ValueError,'Locate source'):content_packs.install(Path('ER'),'pack-london')
            install.assert_not_called()
        with patch.object(content_packs,'available_sources',return_value={'holiday':Path('HR')}),patch.object(addons,'install',side_effect=ValueError('modified donor')):
            with self.assertRaisesRegex(ValueError,'Completed items are retained'):content_packs.install(Path('ER'),'pack-holiday')

    def test_locate_source_recognises_original_index_and_pmr_data_folder(self):
        root=Path(__file__).resolve().parents[1]
        for donor in ('autobahn2','pmr'):
            spec=addons.DONORS[donor]
            with tempfile.TemporaryDirectory(dir=root/'work')as temporary:
                folder=Path(temporary);data=folder/spec['sub'];data.mkdir(exist_ok=True)
                (data/'rcs.ind').write_bytes((root/'analysis/baseline'/spec['title']/spec['sub']/'rcs.ind').read_bytes())
                (data/'rcs.img').write_bytes(b'Archive content is verified by the installer.')
                self.assertEqual(content_packs.identify_source(data),(donor,folder.resolve()))
                (data/'rcs.ind').write_bytes(b'Unknown index')
                with self.assertRaises(ValueError):content_packs.identify_source(data)


if __name__=='__main__':unittest.main()

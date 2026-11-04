import io,struct,tempfile,unittest
from pathlib import Path
from PIL import Image
from davilex.car_addons import payload,dynamics_a4
from davilex.addons import table
from davilex.rcs import Archive
from davilex.europe_tuning import usable
ROOT=Path(__file__).resolve().parents[1]

class CarAddonTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'work');self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name);base=ROOT/'analysis/baseline/Europe Racer'
        for name in ('Game/Ini/Cars.ini','Game/Ini/damage.ini','Game/Ini/Racer.ini','Menu/GameMenu.ini','Menu/Language.ini'):
            destination=self.folder/name;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes((base/name).read_bytes())

    def test_patched_donor_ini_does_not_prevent_original_car_import(self):
        from unittest.mock import patch
        donor=self.folder/'donor';donor.mkdir()
        baseline=ROOT/'analysis/baseline/London Racer'
        import shutil
        for name in ('rcs.img','rcs.ind','phys0.dat'):shutil.copyfile(baseline/name,donor/name)
        for name in ('car_cfg.ini','L0_anim.ini'):(donor/name).write_text('User-modified runtime configuration')
        with patch('davilex.legacy_car_addons.source_folder',return_value=donor):
            files,report=payload(self.folder,'car-lr-mini')
        self.assertEqual(report['name'],'Mini');self.assertIn(Path('Game/Vdyns/VDYNS78.DAT'),files)

    def test_complete_panels_and_truecolour_textures_are_in_separate_archive(self):
        files,report=payload(self.folder,'car-a4-hotrod');self.assertEqual(report['damage_parts'],12)
        self.assertEqual(report['engine_id'],78)
        for ext in ('img','ind'):(self.folder/f'dvcar78.{ext}').write_bytes(files[Path(f'Game/dvcar78.{ext}')])
        archive=Archive(self.folder/'dvcar78.img')
        self.assertFalse(any(e.extension=='.pcx'for e in archive.entries))
        for e in archive.entries:
            self.assertLessEqual(len(Path(e.name).stem),8)
            if e.extension=='.tga':
                im=Image.open(io.BytesIO(archive.read(e)));self.assertEqual(im.mode,'RGB');self.assertIn(im.size,((128,128),(256,256)))
        cars=files[Path('Game/Ini/Cars.ini')]
        self.assertEqual(table(cars,'d78_vehicle')['count'],'12')
        self.assertEqual(table(cars,'cars')['0'],table((self.folder/'Game/Ini/Cars.ini').read_bytes(),'cars')['0'])

    def test_donor_power_gearing_and_mass_survive_upgrade_adaptation(self):
        raw=(ROOT/'analysis/baseline/A2 Racer 4/vdyns.dat').read_bytes()[12*616:13*616]
        seed=(ROOT/'analysis/baseline/Europe Racer/Game/Vdyns/VDYNS1.DAT').read_bytes();converted,report=dynamics_a4(raw,seed)
        self.assertEqual(converted[:16],raw[:16]);self.assertEqual(report['source_columns'],[0,1,1,1,1])
        self.assertEqual(converted[572:732],seed[572:732]) # Different tyre law, deliberately not reinterpreted.
        for level in range(5):
            donor=min(level,1);self.assertTrue(usable(converted,level))
            self.assertEqual(converted[332+4*level:336+4*level],raw[92+4*donor:96+4*donor])
            self.assertEqual(converted[452+24*level:476+24*level],raw[212+24*donor:236+24*donor])

    def test_bad_base_profile_does_not_become_a_playable_car(self):
        with self.assertRaisesRegex(ValueError,'complete donor'):
            dynamics_a4(bytes(616),bytes(1032))

    def test_legacy_force_ratios_do_not_replace_europe_wheel_motor_gearing(self):
        from davilex.legacy_car_addons import handling
        source=(ROOT/'analysis/baseline/London Racer/phys0.dat').read_bytes()[:172]
        seed=(ROOT/'analysis/baseline/Europe Racer/Game/Vdyns/VDYNS0.DAT').read_bytes()
        converted,report=handling(source,seed,2.70167798)
        self.assertEqual(converted[312:332],seed[312:332])
        self.assertEqual(converted[452:572],seed[452:572])
        self.assertEqual(converted[:4],source[:4])
        for level in range(5):
            self.assertTrue(usable(converted,level))
            self.assertEqual(report['levels'][level]['gearbox'],'authored Europe category profile')
            self.assertGreater(struct.unpack_from('<f',converted,332+level*4)[0],0)
        self.assertEqual(report['levels'][3]['source_force_gears'],6)
        self.assertEqual(report['levels'][3]['gears'],5)

    def test_delorean_uses_matching_london_sheets_and_positive_axle_width(self):
        files,report=payload(self.folder,'car-a4-delorean')
        for ext in ('img','ind'):(self.folder/f'dvcar78.{ext}').write_bytes(files[Path(f'Game/dvcar78.{ext}')])
        archive=Archive(self.folder/'dvcar78.img');donor=Archive(ROOT/'analysis/baseline/London Racer/rcs.img')
        cars=files[Path('Game/Ini/Cars.ini')]
        for frame,name in [('0','l1racer2.tga'),('1','cars01.tga')]:
            resource=table(cars,'d78_anim')[frame].split(',')[1]
            actual=next(e for e in archive.entries if e.name==resource)
            expected=next(e for e in donor.entries if e.name.casefold()==name)
            self.assertEqual(archive.read(actual),donor.read(expected))
        self.assertIn('London Racer',report['material_donor'])
        axle=list(map(float,table(cars,'wheel_positions')['78'].split(',')))
        self.assertEqual(axle,[6.55,0,12.919,6.19,0,-13.073])

    def test_downloaded_names_use_unused_compiled_description_keys(self):
        files,_=payload(self.folder,'car-a4-hotrod')
        menu=table(files[Path('Menu/GameMenu.ini')],'cars')
        self.assertEqual(menu['24'].split(',')[:3],['78','CT_DOWNLOADED','LT_DV_CAR78'])
        before=(self.folder/'Menu/Language.ini').read_bytes()
        language=files[Path('Menu/Language.ini')]
        self.assertEqual(table(language,'text_nl')['lt_dv_car78'],'Hot Rod (US / Sports)')
        self.assertEqual(table(language,'text_nl')['lt_inf_car00'],table(before,'text_nl')['lt_inf_car00'])
        # A user's existing menu car must never lose its description.
        from davilex.installed import edit_ini
        (self.folder/'Menu/GameMenu.ini').write_bytes(edit_ini(files[Path('Menu/GameMenu.ini')],
            {('cars','24'):menu['24'].replace('78,','2,',1)}))
        with self.assertRaisesRegex(ValueError,'description already used'):
            payload(self.folder,'car-a4-hotrod')

    def test_rebuild_keeps_slot_menu_id_and_damage_counts(self):
        first,info=payload(self.folder,'car-a4-hotrod')
        for relative,raw in first.items():
            p=self.folder/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        second,again=payload(self.folder,'car-a4-hotrod',78)
        self.assertEqual(again['engine_id'],78);self.assertEqual(again['menu_id'],info['menu_id'])
        self.assertEqual(first[Path('Game/Ini/damage.ini')],second[Path('Game/Ini/damage.ini')])
        self.assertEqual(table(second[Path('Game/Ini/Cars.ini')],'cars')['count'],'79')
        self.assertEqual(table(second[Path('Game/Ini/Racer.ini')],'img')['count'],'3')

if __name__=='__main__':unittest.main()

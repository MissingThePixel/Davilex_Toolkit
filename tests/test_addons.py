from pathlib import Path
import io,json,tempfile,unittest
from unittest.mock import patch
from PIL import Image
from davilex import addons,installed
from davilex.rcs import Archive

ROOT=Path(__file__).resolve().parents[1]

class AddonTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'work');self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)
        base=ROOT/'analysis/baseline/Europe Racer'
        for relative in ['Game/Ini/Racer.ini','Game/Ini/opponent.ini','Game/Ini/traffic.ini','Menu/GameMenu.ini']:
            destination=self.directory/relative;destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_bytes((base/relative).read_bytes())
        for stem in ('Extra','Graphics'):
            for ext in ['IMG','IND']:
                (self.directory/(f'Menu/{stem}.'+ext)).write_bytes((ROOT/'work/Europe Racer-menu-timing/Menu'/(stem+'.'+ext)).read_bytes())
        self.prague=self.directory/'Game/etappe15.rmp';self.prague.write_bytes(b'Prague must remain untouched')
        self.menu_before=(self.directory/'Menu/GameMenu.ini').read_bytes()
        self.racer_before=(self.directory/'Game/Ini/Racer.ini').read_bytes()
        token=installed.ACTIVE.set({'directory':self.directory,'profile':'europe-resolution','executables':{}})
        self.addCleanup(installed.ACTIVE.reset,token)
        mock=patch.object(installed,'journal_folder',return_value=self.directory/'backups')
        mock.start();self.addCleanup(mock.stop)
        stream=io.BytesIO();Image.new('RGB',(160,160),(50,60,70)).save(stream,format='TGA')
        portrait_mock=patch('davilex.car_portraits.portrait',return_value=stream.getvalue())
        portrait_mock.start();self.addCleanup(portrait_mock.stop)

    def test_additive_install_keeps_prague_and_recovers_all_new_assets(self):
        first=addons.install(self.directory,'a2iv-rotterdam')
        self.assertEqual(first['engine_id'],21)
        racer=(self.directory/'Game/Ini/Racer.ini').read_bytes()
        self.assertEqual(addons.table(racer,'maps')['15'],addons.table(self.racer_before,'maps')['15'])
        self.assertIn('Rotterdam',addons.table(racer,'maps')['21'])
        self.assertEqual(self.prague.read_bytes(),b'Prague must remain untouched')
        menu=addons.table((self.directory/'Menu/GameMenu.ini').read_bytes(),'tracks')
        self.assertTrue(menu['21'].startswith('TC_DOWNLOADED,'))
        archive=(self.directory/'Game/da4t21.img').read_bytes()
        second=addons.install(self.directory,'a2iv-scheveningen')
        self.assertEqual(second['engine_id'],22)
        self.assertEqual((self.directory/'Game/da4t21.img').read_bytes(),archive)
        installed.restore_install(self.directory)
        self.assertEqual((self.directory/'Menu/GameMenu.ini').read_bytes(),self.menu_before)
        self.assertEqual((self.directory/'Game/Ini/Racer.ini').read_bytes(),self.racer_before)
        self.assertFalse((self.directory/'Game/etappe21.rmp').exists())
        self.assertTrue(self.prague.exists())

    def test_reinstall_is_idempotent_and_modified_assets_are_rejected(self):
        first=addons.install(self.directory,'a2iv-rotterdam')
        self.assertEqual(addons.install(self.directory,'a2iv-rotterdam'),first)
        path=self.directory/'Game/etappe21.rmp';path.write_bytes(b'custom edit')
        with self.assertRaisesRegex(ValueError,'asset changed'):
            addons.install(self.directory,'a2iv-rotterdam')
        self.assertEqual(path.read_bytes(),b'custom edit')

    def test_preview_preserves_other_resources_and_original_dimensions(self):
        addons.install(self.directory,'a2iv-rotterdam')
        a=Archive(self.directory/'Menu/Extra.IMG');before={e.name:a.read(e) for e in a.entries}
        file=self.directory/'screenshot.png';Image.new('RGB',(320,180),(30,100,200)).save(file)
        addons.install_preview(self.directory,'a2iv-rotterdam',file)
        a=Archive(self.directory/'Menu/Extra.IMG');after={e.name:a.read(e) for e in a.entries}
        for name,data in before.items():
            if name!='trk21a.tga':self.assertEqual(after[name],data)
        im=Image.open(io.BytesIO(after['trk21a.tga']))
        self.assertEqual(im.size,(160,160));self.assertEqual(im.getpixel((0,0)),(0,0,0))
        self.assertEqual(im.getpixel((80,80)),(30,100,200))

    def test_original_classic_car_definitions_and_no_dummy_car_unlock(self):
        addons.install(self.directory,'europe-classics')
        cars=addons.table((self.directory/'Menu/GameMenu.ini').read_bytes(),'cars')
        extra=[v for v in cars.values() if 'CT_DOWNLOADED' in v]
        self.assertEqual({int(v.split(',')[0]) for v in extra},{2,18,30})
        self.assertEqual(addons.install(self.directory,'europe-classics')['added'],[])

    def test_resource_only_catalogue_does_not_require_duplicated_map_data(self):
        from davilex import quickrace
        from davilex.launch import PROFILES
        stage=ROOT/'.cache/portable-resources'
        quickrace._default_catalog.cache_clear()
        try:
            with patch('davilex.quickrace.resources',return_value=stage),patch('davilex.launch.verified_engine',return_value=stage/'work/Europe Racer-menu-timing'/PROFILES['europe-timing'][1]):
                result=quickrace.race_catalog('europe-resolution')
            self.assertEqual(len(result['tracks']),21)
            self.assertFalse((stage/'work/Europe Racer-menu-timing/game/Etappe01.pmp').exists())
        finally:quickrace._default_catalog.cache_clear()

    def test_output_collision_is_rejected_before_mutation(self):
        path=self.directory/'Game/etappe21.rmp';path.write_bytes(b'existing unrelated data')
        with self.assertRaisesRegex(ValueError,'already exists'):
            addons.install(self.directory,'a2iv-rotterdam')
        self.assertEqual((self.directory/'Menu/GameMenu.ini').read_bytes(),self.menu_before)
        self.assertEqual(path.read_bytes(),b'existing unrelated data')

    def test_donor_art_is_automatic_and_user_preview_survives_reinstall(self):
        item=addons.install(self.directory,'a2iv-frankfurt')
        self.assertIn('ttc06_00.tga',item['preview_source'])
        im=self.directory/'user.png';Image.new('RGB',(100,100),(7,8,9)).save(im)
        addons.install_preview(self.directory,'a2iv-frankfurt',im)
        addons.install(self.directory,'a2iv-frankfurt')
        a=Archive(self.directory/'Menu/Extra.IMG');e=next(e for e in a.entries if e.name=='trk21a.tga')
        self.assertEqual(Image.open(io.BytesIO(a.read(e))).getpixel((80,80)),(7,8,9))
        self.assertNotIn('preview_source',addons.registry(self.directory)['tracks']['a2iv-frankfurt'])

    def test_empty_cell_compaction_keeps_geometry_and_remaps_object_owners(self):
        import struct
        source=ROOT/'analysis/baseline/London Racer'
        before={ext:(source/('etappe1'+ext)).read_bytes() for ext in ('.rmp','.pmp','.omp')}
        rmp,pmp,omp,removed=addons.compact_empty_cells(before['.rmp'],before['.pmp'],before['.omp'])
        self.assertEqual(removed,[0]);self.assertEqual(rmp[12:],before['.rmp'][28:])
        self.assertEqual(struct.unpack_from('<I',rmp,8)[0],struct.unpack_from('<I',before['.rmp'],8)[0]-1)
        self.assertEqual(struct.unpack_from('<I',pmp)[0],struct.unpack_from('<I',before['.pmp'])[0]-1)
        for pos in range(4,len(omp),68):
            self.assertEqual(omp[pos+4:pos+68],before['.omp'][pos+4:pos+68])
            self.assertEqual(struct.unpack_from('<i',omp,pos)[0],struct.unpack_from('<i',before['.omp'],pos)[0]-1)

    def test_runtime_scene_defaults_do_not_hide_changed_object_bindings(self):
        original=b'[Objects]\r\n0=car.d3d,car.tga,0,0,Car_Anim\r\n'
        runtime=original+b'[Difficulty]\r\nLevel=2\r\n[Cops]\r\nCount=3\r\n[Fog]\r\nEnabled=0\r\n[Weather]\r\nRain=0\r\n'
        self.assertTrue(addons.scene_ini_equivalent(original,runtime))
        self.assertFalse(addons.scene_ini_equivalent(original,runtime.replace(b'car.d3d',b'other.d3d')))

    def test_known_failing_route_is_not_offered_for_installation(self):
        self.assertNotIn('london-thames',{v['addon'] for v in addons.choices()})

    def test_classic_portraits_supply_both_cars_and_preserve_custom_art(self):
        addons.install(self.directory,'europe-classics')
        a=Archive(self.directory/'Menu/Extra.IMG');images={e.name:a.read(e)for e in a.entries}
        self.assertIn('car18a.tga',images);self.assertIn('car30a.tga',images)
        images['car30a.tga']=b'user-custom-preview'
        img,ind=addons.archive_bytes(images)
        (self.directory/'Menu/Extra.IMG').write_bytes(img);(self.directory/'Menu/Extra.IND').write_bytes(ind)
        addons.install_classic_portraits(self.directory)
        a=Archive(self.directory/'Menu/Extra.IMG')
        self.assertEqual(a.read(next(e for e in a.entries if e.name=='car30a.tga')),b'user-custom-preview')

    def test_withdraw_oxford_keeps_other_ids_and_is_reversible(self):
        first=addons.install(self.directory,'a2iv-rotterdam')
        second=addons.install(self.directory,'a2iv-scheveningen')
        state=addons.registry(self.directory)
        state['tracks']['london-oxford']=state['tracks'].pop('a2iv-rotterdam')
        state['tracks']['london-oxford-road']=state['tracks'].pop('a2iv-scheveningen')
        (self.directory/addons.REGISTRY).write_text(json.dumps(state))
        path=self.directory/'Game/Ini/game.ini';path.write_bytes(b'[ETAPPE]\netappe=21\n')
        assets={p:(self.directory/p).read_bytes()for item in state['tracks'].values()for p in item['assets']}
        self.assertEqual(addons.withdraw_retired_tracks(self.directory),['london-oxford'])
        state=addons.registry(self.directory)
        self.assertNotIn('london-oxford',state['tracks'])
        self.assertIn('london-oxford',state['withdrawn_tracks'])
        self.assertEqual(state['tracks']['london-oxford-road']['engine_id'],second['engine_id'])
        races=addons.table((self.directory/'Menu/GameMenu.ini').read_bytes(),'quickrace')
        values=[v for k,v in races.items()if k.isdigit()]
        self.assertFalse(any(int(v.split(',')[0])==first['engine_id']for v in values))
        self.assertTrue(any(int(v.split(',')[0])==second['engine_id']for v in values))
        self.assertEqual(sorted(int(k)for k in races if k.isdigit()),list(range(len(values))))
        maps=addons.table((self.directory/'Game/Ini/Racer.ini').read_bytes(),'maps')
        self.assertEqual(maps[str(first['engine_id'])].split(',')[8],'empty')
        self.assertEqual(addons.table(path.read_bytes(),'etappe')['etappe'],'0')
        self.assertEqual(addons.withdraw_retired_tracks(self.directory),[])
        self.assertTrue(all((self.directory/p).read_bytes()==data for p,data in assets.items()))
        installed.restore_install(self.directory)
        self.assertEqual((self.directory/'Menu/GameMenu.ini').read_bytes(),self.menu_before)

    def test_withdrawn_oxford_is_not_offered_or_reinstallable(self):
        self.assertNotIn('london-oxford',{item['addon']for item in addons.choices()})
        self.assertIn('london-oxford-road',{item['addon']for item in addons.choices()})
        with self.assertRaisesRegex(ValueError,'Withdrawn'):addons.install(self.directory,'london-oxford')

if __name__=='__main__':unittest.main()

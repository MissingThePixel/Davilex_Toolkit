from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from davilex import installed


class InstalledPatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=installed.ROOT/'work')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.game=self.root/'game';self.game.mkdir()
        self.patcher=patch.object(installed,'ROOT',self.root)
        self.patcher.start();self.addCleanup(self.patcher.stop)

    def test_resolution_changes_reuse_install_and_original_backup(self):
        engine=self.game/'spel.dat';engine.write_bytes(b'original')
        unrelated=self.game/'music.img';unrelated.write_bytes(b'never copy this')
        installed.commit(self.game,{Path('spel.dat'):b'resolution one'})
        installed.commit(self.game,{Path('spel.dat'):b'resolution two'})
        journal=installed.journal_folder(self.game)
        self.assertEqual((journal/'original/spel.dat').read_bytes(),b'original')
        self.assertEqual(engine.read_bytes(),b'resolution two')
        self.assertFalse((journal/'original/music.img').exists())
        self.assertEqual(installed.restore_install(self.game),1)
        self.assertEqual(engine.read_bytes(),b'original')
        self.assertEqual(unrelated.read_bytes(),b'never copy this')

    def test_failed_apply_rolls_back_files_and_removes_added_files(self):
        (self.game/'one.dat').write_bytes(b'original')
        replace=installed.replace_file
        def fail(target,data):
            if target.name=='fail.dat':raise PermissionError('simulated denied write')
            replace(target,data)
        with patch.object(installed,'replace_file',side_effect=fail):
            with self.assertRaises(PermissionError):
                installed.commit(self.game,{Path('one.dat'):b'patched',Path('new.dll'):b'added',Path('fail.dat'):b'fail'})
        self.assertEqual((self.game/'one.dat').read_bytes(),b'original')
        self.assertFalse((self.game/'new.dll').exists())
        self.assertFalse((installed.journal_folder(self.game)/'pending.json').exists())

    def test_restore_retains_game_progress_and_user_changes(self):
        original=b'[OPTIONS]\r\nresolution=1\r\n[PLAYER]\r\nmoney=100\r\n'
        patched=original.replace(b'resolution=1',b'resolution=3')
        path=self.game/'game.ini';path.write_bytes(original)
        installed.commit(self.game,{Path('game.ini'):patched})
        path.write_bytes(patched.replace(b'money=100',b'money=250'))
        installed.restore_install(self.game)
        self.assertEqual(path.read_bytes(),original.replace(b'money=100',b'money=250'))

    def test_restore_does_not_overwrite_modified_binary(self):
        path=self.game/'spel.dat';path.write_bytes(b'original')
        installed.commit(self.game,{Path('spel.dat'):b'patched'})
        path.write_bytes(b'other patch')
        with self.assertRaisesRegex(ValueError,'preserving'):installed.restore_install(self.game)
        self.assertEqual(path.read_bytes(),b'other patch')

    def test_exact_active_install_required_for_external_access(self):
        self.assertFalse(installed.permitted(self.game))
        token=installed.ACTIVE.set({'directory':self.game})
        try:
            self.assertTrue(installed.permitted(self.game))
            self.assertFalse(installed.permitted(self.root))
        finally:installed.ACTIVE.reset(token)

    def relocated(self):
        (self.game/'spel.dat').write_bytes(b'original')
        (self.game/'game.ini').write_bytes(b'[OPTIONS]\r\nresolution=1\r\n')
        installed.commit(self.game,{Path('spel.dat'):b'patched',Path('game.ini'):b'[OPTIONS]\r\nresolution=3\r\n'})
        source=installed.journal_folder(self.game)
        moved=self.root/'moved'/'game'
        import shutil
        shutil.copytree(self.game,moved)
        return source,moved

    def test_moved_install_reconnects_verified_backups_and_preserves_source(self):
        source,moved=self.relocated()
        (source/'session.lock').write_bytes(b'0')
        journal=installed.journal_folder(moved)
        self.assertNotEqual(source,journal)
        self.assertTrue((source/'state.json').exists())
        self.assertFalse((journal/'session.lock').exists())
        self.assertEqual(installed.restore_install(moved),2)
        self.assertEqual((moved/'spel.dat').read_bytes(),b'original')
        self.assertEqual((self.game/'spel.dat').read_bytes(),b'patched')

    def test_relocation_rejects_modified_executable_corrupt_backup_and_pending(self):
        source,moved=self.relocated()
        target=installed._journal_path(moved)
        (moved/'spel.dat').write_bytes(b'unknown patch')
        self.assertFalse((installed.journal_folder(moved)/'state.json').exists())
        (moved/'spel.dat').write_bytes(b'patched')
        (source/'pending.json').write_text('{}')
        self.assertFalse((installed.journal_folder(moved)/'state.json').exists())
        (source/'pending.json').unlink()
        (source/'original/spel.dat').write_bytes(b'corrupt')
        self.assertEqual(installed.journal_folder(moved),target)
        self.assertFalse((target/'state.json').exists())

    def test_relocation_rejects_conflicting_valid_original_histories(self):
        source,moved=self.relocated()
        import json,shutil
        other=source.with_name('different-original')
        shutil.copytree(source,other)
        state=json.loads((other/'state.json').read_text())
        (other/'original/spel.dat').write_bytes(b'another original')
        state['files']['spel.dat']['original_sha256']=installed.digest(b'another original')
        (other/'state.json').write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError,'Multiple different'):
            installed.journal_folder(moved)
        self.assertFalse((installed._journal_path(moved)/'state.json').exists())

    def test_escape_paths_rejected(self):
        for relative in ('../elsewhere',str(self.root/'absolute')):
            with self.assertRaises(ValueError):installed.safe_target(self.game,relative)

    def test_add_missing_nocd_key_retains_existing_menu(self):
        data=b'[GENERAL]\r\nOther=keep\r\n'
        changed=installed.edit_ini(data,{('general','nocd'):1})
        self.assertIn(b'nocd=1',changed)
        self.assertIn(b'Other=keep',changed)
        self.assertEqual(installed.edit_ini(changed,{('general','nocd'):1}),changed)


class CapturedBuildTests(unittest.TestCase):
    def test_orphaned_shipped_renderer_is_recognised_without_old_journal(self):
        from davilex.windowed import dxwrapper_payloads,payloads
        profile='a2ii-resolution';actual=installed.locate(profile)
        template,_,engine_rel,_=installed.plan(actual,profile,1280,720)
        with tempfile.TemporaryDirectory(dir=installed.ROOT/'work')as folder:
            directory=Path(folder)/'install';directory.mkdir()
            baseline=installed.ROOT/'analysis/baseline'/installed.baseline(profile)['title']
            for relative in set(template)|{engine_rel.parent/'game.ini',engine_rel.parent/'raser.ini'}:
                source=baseline/relative
                if not source.exists():source=actual/relative
                if source.exists():
                    target=directory/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
            target=directory/'ddraw.dll'
            with patch.object(installed,'journal_folder',return_value=Path(folder)/'backups'):
                for data in (dxwrapper_payloads()['ddraw.dll'],payloads()['ddraw.dll'],payloads(diagnostic=True)['ddraw.dll']):
                    target.write_bytes(data)
                    replacement,*_=installed.plan(directory,profile,1280,720)
                    self.assertNotEqual(replacement[Path('ddraw.dll')],data)
                    installed.commit(directory,replacement)
                    installed.restore_install(directory)
                    self.assertEqual(target.read_bytes(),data)
                target.write_bytes(b'unknown third-party renderer')
                with self.assertRaisesRegex(ValueError,'SHA-256:'):
                    installed.plan(directory,profile,1280,720)
                self.assertEqual(target.read_bytes(),b'unknown third-party renderer')

    def test_a2iv_and_pmr_change_resolution_in_place_with_real_builds(self):
        from davilex.launch import ROOT
        from davilex.menu import verify_copy
        # Fixtures contain only files addressed by patches, never whole games.
        for profile in ('a2racer4-resolution','pmr-resolution'):
            with self.subTest(profile=profile),tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
                directory=Path(folder)/'install';directory.mkdir()
                actual=installed.locate(profile)
                payload,_,engine_rel,menu_rel=installed.plan(actual,profile,3840,2560)
                needed=set(payload)|{engine_rel.parent/'game.ini',engine_rel.parent/'raser.ini'}
                for relative in needed:
                    source=installed.ROOT/'analysis/baseline'/installed.baseline(profile)['title']/relative
                    if not source.exists():source=actual/relative
                    if source.exists():
                        target=directory/relative;target.parent.mkdir(parents=True,exist_ok=True)
                        target.write_bytes(source.read_bytes())
                # A fresh disposable install must start from the captured original,
                # not the user's current patched executable without its journal.
                title=installed.baseline(profile)['title']
                original=(installed.ROOT/'analysis/baseline'/title/engine_rel).read_bytes()
                (directory/engine_rel).write_bytes(original)
                with patch.object(installed,'journal_folder',return_value=Path(folder)/'backups'):
                    for width,height in ((3840,2560),(1920,1080),(3840,2560)):
                        with installed.installed_game(profile,width,height,directory) as (game,selected):
                            menu,engine=verify_copy(game,selected)
                            self.assertEqual(game,directory)
                            self.assertEqual(engine,directory/engine_rel)
                            self.assertEqual(menu,directory/menu_rel)
                    installed.restore_install(directory)
                    self.assertEqual((directory/engine_rel).read_bytes(),original)


if __name__=='__main__':unittest.main()

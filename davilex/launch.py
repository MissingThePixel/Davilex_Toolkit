"""Launch a verified working-copy engine with its built-in disc override."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess

from .paths import ROOT,resources
PROFILES={
    'a2ii':('A2II','spel.dat'), 'a2ii-timing':('A2II','spel.dat'),
    'a2racer4-vram':('A2 Racer 4','spel.dat'), 'a2racer4-timing':('A2 Racer 4','spel.dat'),
    'a2racer4-resolution':('A2 Racer 4','spel.dat'),
    'holiday-resolution':('Holiday Racer','spel.dat'),
    'pmr-resolution':('Paris - Marseille Racing','data/spel.dat'),
    'europe-resolution':('Europe Racer','game/spel.exe'),
    'a2ii-resolution':('A2II','spel.dat'),
    'autobahn2-resolution':('Autobahn Raser II','spel.dat'),
    'london-resolution':('London Racer','spel.dat'),
    'autobahn2':('Autobahn Raser II','spel.dat'), 'london':('London Racer','spel.dat'),
    'autobahn2-timing':('Autobahn Raser II','spel.dat'), 'london-timing':('London Racer','spel.dat'),
    'holiday':('Holiday Racer','spel.dat'), 'europe':('Europe Racer','game/spel.exe'),
    'pmr':('Paris - Marseille Racing','data/spel.dat'),
    'holiday-timing':('Holiday Racer','spel.dat'),
    'pmr-timing':('Paris - Marseille Racing','data/spel.dat'),
    'europe-timing':('Europe Racer','game/spel.exe'),
}


def verified_engine(directory,profile):
    directory=Path(directory).resolve()
    from .installed import active_engine
    active=active_engine(directory,profile)
    if active is not None:return active
    manifest=json.loads((resources(ROOT)/'analysis'/'baseline'/'manifest.json').read_text(encoding='utf-8'))
    title,engine_relative=PROFILES[profile]
    game=next(g for g in manifest if g['title']==title)
    expected=next(f['sha256'] for f in game['files'] if f['path'].replace('\\','/').lower()==engine_relative)
    if title=='A2 Racer 4':
        patch=json.loads((directory/'patch-manifest.json').read_text(encoding='utf-8'))
        if patch['source_sha256']!=expected or patch['patch_site']!='0x4bc12d':
            raise ValueError('Unsupported A2 Racer 4 patch profile.')
        expected=patch['patched_sha256']
    if profile.startswith('autobahn2'):
        patch=json.loads((directory/'patch-manifest.json').read_text(encoding='utf-8'))
        if patch['source_sha256']!=expected or patch['buffer_address']!='0x51d200':
            raise ValueError('Unsupported Autobahn II patch profile.')
        expected='756f5c09c2b8b929698c0071003974e828f145a8128677407256d4dbf1d9c80c'
        if patch['patched_sha256']!=expected:
            raise ValueError('Unsupported Autobahn II patch output.')
    if profile.endswith('-timing'):
        timing=json.loads((directory/'relative-timer-manifest.json').read_text(encoding='utf-8'))
        if timing['source_sha256']!=expected or timing['title']!=title:
            raise ValueError('Unsupported relative timer source profile.')
        expected={'A2II':'0f367445cc5e1bdb7caef28a0f9b7dab4b0ddd238673903c46d0ec1de3813703',
                  'A2 Racer 4':'7ef5f3d75c2eed1def3d7514bc4c11c7ac2130da783af4cca0dd62187b04e7e1',
                  'Autobahn Raser II':'b1f852158d9391c54574eaa4d9ce3acf1b8a6d032543a90cecaacf2398d7a613',
                  'London Racer':'a6d1340729f7946fbb153a98faded0a099c53a51dc87e8fa34a2b4ffd525eafb',
                  'Holiday Racer':'167895e194b41fa36134b68bc7b6a9aa6c1c115e8915bb1f983bff5a3c468b84',
                  'Paris - Marseille Racing':'3380c7241710922910e53025d74f837cc9baa55393f5b25a5ffa3caaa5136fee',
                  'Europe Racer':'1827f986fc733d0538182f316f869fae1888dad8c5cc1ebc18abe7118a5bf807'}[title]
        if timing['patched_sha256']!=expected:
            raise ValueError('Unsupported relative timer output profile.')
    if profile.endswith('-resolution'):
        from .resolution import patch_engine,SOURCES
        resolution=json.loads((directory/'native-resolution-manifest.json').read_text())
        # Derive the expected image from the verified canonical source, not a
        # caller-supplied output hash in the resolution manifest.
        folder,source_profile,_=SOURCES[profile]
        from .paths import patch_source
        source=verified_engine(patch_source(profile,resources(ROOT)),source_profile)
        from .ingredients import read as read_ingredient
        _,derived=patch_engine(read_ingredient(source),*resolution['dimensions'],profile)
        if resolution!=derived:
            raise ValueError('Unsupported native resolution manifest.')
        expected=derived['patched_sha256']
    engine=directory/engine_relative
    from .ingredients import read as read_ingredient
    if hashlib.sha256(read_ingredient(engine)).hexdigest()!=expected:
        raise ValueError('This launch profile does not match the engine build.')
    return engine


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--nocd',default='D')
    parser.add_argument('--profile',choices=tuple(PROFILES),default='a2ii')
    args=parser.parse_args()
    directory=args.directory.resolve()
    try:
        if not re.fullmatch('[A-Za-z]',args.nocd):
            raise ValueError('NOCD must be a single drive letter.')
        engine=verified_engine(directory,args.profile)
        env=os.environ.copy()
        env['NOCD']=args.nocd.upper()
        result=subprocess.run([str(engine)],cwd=engine.parent,env=env)
        print(f'Engine exit code: {result.returncode}')
    except (ValueError,OSError) as error:
        parser.exit(1,f'Error: {error}\n')


if __name__=='__main__':
    main()

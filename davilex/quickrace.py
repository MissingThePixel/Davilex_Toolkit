"""A2 Racer II quick-race preparation based on qrace.exe's actual writes."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from contextlib import contextmanager
from functools import lru_cache

from .paths import ROOT,resources
TRACKS=('Amsterdam start','Amsterdam - Den Haag','Den Haag','Den Haag - Rotterdam',
        'Rotterdam','Rotterdam - Amsterdam','Amsterdam finish')
CARS=('Trabant','Astra','Kever','BMW','Porsche','Mercedes','Lamborgini')


def update_ini(data,changes):
    """Edit only existing, unambiguous keys while retaining original formatting."""
    pending={(s.casefold(),k.casefold()):str(v).encode('ascii') for (s,k),v in changes.items()}
    positions={key:[] for key in pending}
    lines=data.splitlines(keepends=True)
    section=''
    for i,line in enumerate(lines):
        heading=re.match(rb'\s*\[([^\]]+)\]',line)
        if heading:
            section=heading[1].decode('cp1252').casefold()
        match=re.match(rb'([ \t]*)([^;=\r\n]+?)([ \t]*=[ \t]*)([^\r\n]*)(\r?\n)?$',line)
        if match:
            key=(section,match[2].decode('cp1252').strip().casefold())
            if key in pending:
                positions[key].append((i,match))
    for key,found in positions.items():
        if len(found)!=1:
            raise ValueError(f'Expected one existing INI key {key}, found {len(found)}.')
        i,match=found[0]
        trailing=re.search(rb'[ \t]*$',match[4])[0]
        lines[i]=match[1]+match[2]+match[3]+pending[key]+trailing+(match[5] or b'')
    return b''.join(lines)


@lru_cache(maxsize=None)
def _default_catalog(profile):
    return _read_catalog(profile)


def race_catalog(profile,directory=None):
    return _default_catalog(profile) if directory is None else _read_catalog(profile,directory)


def _read_catalog(profile,directory=None):
    """Read choices from the verified title's own tables, never another game's IDs."""
    from .resolution import SOURCES
    from .launch import verified_engine
    from .translate import ini_lines
    spec=next((v for k,v in SOURCES.items() if profile in (k,v[1])),None)
    if spec is None:raise ValueError('Unsupported Quick Race profile.')
    folder,base,_=spec
    actual_install=directory is not None
    if directory is None:
        from .paths import patch_source
        directory=patch_source(profile,resources(ROOT))
        engine=verified_engine(directory,base)
    else:
        from .launch import PROFILES
        directory=Path(directory).resolve()
        engine=directory/PROFILES[base][1]
    europe=profile.startswith('europe')
    config_dir=engine.parent/'Ini' if europe else engine.parent
    files={p.name.casefold():p for p in config_dir.iterdir() if p.is_file()}
    def table(name,section):
        if name not in files:raise ValueError('Missing game catalogue: '+str(config_dir/name))
        return {k:m[4].strip() for _,s,k,_,m in ini_lines(files[name].read_bytes()) if s==section}
    if profile.startswith('a2ii'):
        return {'tracks':[{'id':i,'label':name} for i,name in enumerate(TRACKS)],
                'cars':[{'id':i,'label':name} for i,name in enumerate(CARS)]}
    maps=table('racer.ini' if europe else 'raser.ini','maps')
    withdrawn=set()
    if europe and actual_install:
        from .addons import registry,TRACK_ADDONS
        state=registry(directory)
        withdrawn={int(item['engine_id'])for group in ('tracks','withdrawn_tracks')for key,item in state.get(group,{}).items()if TRACK_ADDONS.get(key,{}).get('withdrawn')}
    tracks=[]
    for key,value in maps.items():
        if not key.isdigit() or int(key)>=int(maps['count']):continue
        if int(key)in withdrawn:continue
        fields=[x.strip() for x in value.split(',')]
        if len(fields)<9:continue
        from .installed import baseline
        available={f['path'].replace('\\','/').casefold() for f in baseline(base)['files']}
        map_name=(engine.parent/(fields[1]+'.pmp')).relative_to(directory).as_posix().casefold()
        if actual_install:
            if not (directory/map_name).is_file():continue
        elif map_name not in available:continue
        if fields[8].casefold() in ('leer','empty'):continue
        tracks.append({'id':int(key),'label':f'{key}: {fields[8]}',
                       'name':fields[8],'british':int(fields[15]) if europe else None})
    car_table=table('cars.ini' if europe else 'car_cfg.ini','cars' if europe else 'league0')
    anim={}
    if 'l0_anim.ini' in files:
        anim={(s,k):m[4].strip() for _,s,k,_,m in ini_lines(files['l0_anim.ini'].read_bytes())}
    cars=[];converted={}
    if europe and actual_install:
        from .addons import registry
        converted={int(v['engine_id']):v for v in registry(directory).get('converted_cars',{}).values()}
    for key,value in car_table.items():
        if not key.isdigit():continue
        fields=[x.strip() for x in value.split(',')]
        if len(fields)<7:continue
        if europe:
            if fields[2].strip().casefold()=='dummy':continue
            if int(key)>=32 and int(key)not in converted:continue
            extra=converted.get(int(key));name=extra['name']if extra else fields[0].replace('_',' ')
            if extra:
                from .car_addons import COUNTRIES
                name+=f" ({extra.get('origin',COUNTRIES[extra['country']])} / {extra['category'].title()})"
        else:
            # Trailer/attached objects are not independent player vehicles.
            if not fields[0].upper().startswith('RACER_'):continue
            model=anim.get((fields[1].casefold(),'0'),'').split(',')[0]
            name=Path(model).stem if model else fields[1].replace('_',' ')
        cars.append({'id':int(key),'label':f'{key}: {name}',
                     'country':(converted[int(key)]['country']if int(key)in converted else int(key)//4) if europe else None})
    if not tracks or not cars:raise ValueError('No supported Quick Race resources found.')
    return {'tracks':sorted(tracks,key=lambda x:x['id']),'cars':sorted(cars,key=lambda x:x['id'])}


def race_settings(track,car,profile=None,directory=None):
    if profile:
        catalog=race_catalog(profile,directory=directory if profile.startswith('europe') else None)
        selected=next((x for x in catalog['tracks'] if x['id']==track),None)
        vehicle=next((x for x in catalog['cars'] if x['id']==car),None)
        if selected is None or vehicle is None:raise ValueError('Choose a listed track and car for this game.')
    else:
        selected=vehicle=None
    if not profile and (not 0 <= track < len(TRACKS) or not 0 <= car < len(CARS)):
        raise ValueError('Track and car IDs must be 0 through 6.')
    changes={('ETAPPE','etappe'):track,('PLAYER','car'):car,
             ('PLAYER','damage'):0,('PLAYER','copland'):0}
    changes.update({('PLAYER',key):1 for key in ('motor','banden','abs','turbo','versnellingsbak')})
    if profile and not profile.startswith('a2ii'):
        changes[('LEAGUE','league')]=0
        changes[('PLAYER','finished')]=0
        changes[('PLAYER','lapcount')]=0
        if not profile.startswith(('autobahn2','london')):
            changes[('PLAYER','turbo_amount')]=100
        if profile.startswith('europe'):
            changes[('ETAPPE','british')]=selected['british']
            changes[('PLAYER','country')]=vehicle['country']
    return changes


def restore_race(directory):
    """Recover only our temporary race keys, retaining unrelated game writes."""
    from .translate import ini_lines
    directory=Path(directory).resolve()
    from .installed import permitted
    if not permitted(directory):
        raise ValueError('Quick Race requires a project working copy.')
    journal=directory/'.quickrace-restore.json'
    if not journal.exists():return
    record=json.loads(journal.read_text(encoding='utf-8'))
    relative=record.get('config','game.ini')
    config=(directory/relative).resolve()
    if not config.is_relative_to(directory):raise ValueError('Invalid Quick Race recovery path.')
    original=bytes.fromhex(record['original_hex'])
    if hashlib.sha256(original).hexdigest()!=record['original_sha256']:
        raise ValueError('Quick Race recovery hash mismatch.')
    current=config.read_bytes()
    if hashlib.sha256(current).hexdigest()==record['patched_sha256']:
        config.write_bytes(original)
    else:
        changes={}
        values={(s,k):m[4].strip() for _,s,k,_,m in ini_lines(current)}
        for edit in record['edits']:
            pair=(edit['section'],edit['key'])
            if values.get(pair)==edit['after']:changes[pair]=edit['before']
        config.write_bytes(update_ini(current,changes))
    journal.replace(directory/'.quickrace-restored.json')


@contextmanager
def race_mode(directory,track,car,profile=None):
    from .translate import ini_lines
    directory=Path(directory).resolve()
    changes=race_settings(track,car,profile,directory=directory)
    restore_race(directory)
    from .launch import verified_engine
    if profile:
        engine=verified_engine(directory,profile)
        config=engine.parent/('Ini/game.ini' if profile.startswith('europe') else 'game.ini')
    else:config=directory/'game.ini'
    original=config.read_bytes();patched=update_ini(original,changes)
    values={(s,k):m[4].strip() for _,s,k,_,m in ini_lines(original)}
    record={'config':str(config.relative_to(directory)),'original_hex':original.hex(),'original_sha256':hashlib.sha256(original).hexdigest(),
            'patched_sha256':hashlib.sha256(patched).hexdigest(),
            'edits':[{'section':s.casefold(),'key':k.casefold(),
                      'before':values[s.casefold(),k.casefold()],'after':str(v)} for (s,k),v in changes.items()]}
    (directory/'.quickrace-restore.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    try:
        config.write_bytes(patched)
        yield
    finally:restore_race(directory)


def prepare(destination,track,car):
    if not 0<=track<len(TRACKS) or not 0<=car<len(CARS):
        raise ValueError('Track and car IDs must be 0 through 6.')
    baseline=ROOT/'analysis'/'baseline'/'A2II'
    manifest=json.loads((ROOT/'analysis'/'baseline'/'manifest.json').read_text(encoding='utf-8'))
    game=next(g for g in manifest if g['title']=='A2II')
    # Validate every source file before creating a playable copy.
    for item in game['files']:
        path=baseline/item['path']
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError(f'Baseline file is missing or changed: {path}')
    destination=Path(destination).resolve()
    if destination.exists():
        raise ValueError('Choose a new destination; existing game copies are never overwritten.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(baseline,destination)
    config=destination/'game.ini'
    changes=race_settings(track,car)
    config.write_bytes(update_ini(config.read_bytes(),changes))
    (destination/'quickrace-profile.json').write_text(json.dumps({'track':{'id':track,'name':TRACKS[track]},
        'car':{'id':car,'name':CARS[car]},'engine':'spel.dat','arguments':[],
        'source':'qrace.exe static analysis; gameplay validation pending',
        'changes':[{'section':s,'key':k,'value':v} for (s,k),v in changes.items()]},indent=2),encoding='utf-8')
    return destination


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--choices',action='store_true')
    parser.add_argument('--track',type=int,choices=range(7),default=0)
    parser.add_argument('--car',type=int,choices=range(7),default=0)
    parser.add_argument('--prepare',type=Path)
    parser.add_argument('--launch',action='store_true',help='Launch the prepared engine directly (experimental)')
    parser.add_argument('--nocd',default='D',help='Value of the built-in NOCD drive override')
    args=parser.parse_args()
    if args.choices:
        print(json.dumps({'tracks':dict(enumerate(TRACKS)),'cars':dict(enumerate(CARS))},indent=2))
        return
    if args.prepare is None:
        parser.error('--prepare must name a new working-copy directory')
    try:
        directory=prepare(args.prepare,args.track,args.car)
        print(directory)
        if args.launch:
            if not re.fullmatch('[A-Za-z]',args.nocd):
                raise ValueError('NOCD must be a single drive letter.')
            env=os.environ.copy()
            env['NOCD']=args.nocd.upper()
            result=subprocess.run([str(directory/'spel.dat')],cwd=directory,env=env)
            print(f'Engine exit code: {result.returncode}')
    except (ValueError,OSError) as error:
        parser.exit(1,f'Error: {error}\n')


if __name__=='__main__':
    main()

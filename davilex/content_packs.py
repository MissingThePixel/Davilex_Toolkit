"""Source-game downloads for Europe, with optional donor-folder discovery."""
from pathlib import Path
from .addons import DONORS,TRACK_ADDONS,source_folder
from .car_addons import CATALOG


def members(donor):
    return [key for key,item in TRACK_ADDONS.items()
            if item.get('donor','a2iv')==donor and not item.get('withdrawn') and not item.get('research_only')]+[
            key for key,item in CATALOG.items()if item['donor']==donor]


def available_sources():
    result={}
    for donor,spec in DONORS.items():
        try:
            folder=source_folder(donor)
            if all((folder/spec['sub']/name).is_file()for name in ('rcs.img','rcs.ind')):result[donor]=folder
        except (OSError,ValueError):continue
    return result


def choices():
    result=[{'addon':'pack-all','label':'Import all available content'},
            {'addon':'europe-classics','label':'Europe Racer: classic cars'}]
    for donor,folder in available_sources().items():
        keys=members(donor);tracks=sum(k in TRACK_ADDONS for k in keys);cars=len(keys)-tracks
        parts=[]
        if tracks:parts.append(f'{tracks} tracks')
        if cars:parts.append(f'{cars} cars')
        result.append({'addon':'pack-'+donor,'label':DONORS[donor]['title'].replace('A2II','A2 Racer II')+': '+', '.join(parts),'donor':donor})
    return result


def identify_source(folder):
    """Recognise a supplied donor using its small, original archive index."""
    from .installed import baseline,digest
    folder=Path(folder).resolve();matches=[]
    for donor,spec in DONORS.items():
        candidates=[folder]
        if spec['sub'] and folder.name.casefold()==spec['sub'].casefold():candidates.append(folder.parent)
        known={Path(f['path']).as_posix().casefold():f['sha256']for f in baseline(spec['profile'])['files']}
        expected=known.get((Path(spec['sub'])/'rcs.ind').as_posix().casefold())
        for candidate in candidates:
            archive=candidate/spec['sub'];index=archive/'rcs.ind'
            if expected and index.is_file() and (archive/'rcs.img').is_file() and digest(index.read_bytes())==expected:
                matches.append((donor,candidate));break
    if len(matches)!=1:raise ValueError('Choose a supported source-game installation containing its original RCS.IMG and RCS.IND files.')
    return matches[0]


def install(directory,key):
    from .addons import install as install_one
    sources=available_sources()
    if key=='pack-all':donors=list(sources)
    elif key.startswith('pack-') and key[5:]in DONORS:
        donors=[key[5:]]
        if donors[0]not in sources:raise ValueError('Source game not found. Use Locate source game in downloaded content first.')
    else:raise ValueError('Unknown content pack.')
    keys=[item for donor in donors for item in members(donor)]
    if key=='pack-all':keys.insert(0,'europe-classics')
    installed=[]
    for index,item in enumerate(keys,1):
        print(f'Importing {index}/{len(keys)}: {item}',flush=True)
        try:install_one(directory,item)
        except (OSError,ValueError)as error:
            raise ValueError(f'Import stopped at {item}: {error}. Completed items are retained; rerunning resumes safely.')from error
        installed.append(item)
    print(f'Import complete: {len(installed)} content items.',flush=True)
    return {'pack':key,'installed':installed}

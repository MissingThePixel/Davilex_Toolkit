"""Additive Europe Racer downloads built from verified original donor assets."""
from pathlib import Path
import hashlib,json,re,struct,sys,zlib,shutil
from .paths import ROOT,resources
from .rcs import Archive
from .translate import ini_lines
from .installed import edit_ini

def table(data,section):
    return {k:m[4].strip() for _,s,k,_,m in ini_lines(data) if s==section.casefold()}

def archive_bytes(resources):
    records=[];data=bytearray()
    for name,payload in sorted(resources.items()):
        encoded=name.encode('ascii')
        if len(encoded)>19:raise ValueError('Archive name exceeds 19 bytes')
        records.append(struct.pack('<20sI',encoded,len(data)))
        data+=struct.pack('<I',len(payload))+zlib.compress(payload)
    return bytes(data),struct.pack('<H',len(records))+b''.join(records)


def compact_empty_cells(road,centres,objects):
    """Remove unused cells that Europe's collision builder dereferences.

    Preserve every nonempty cell and all segment/path indices. OMP's owning-cell
    IDs are remapped when an unused leading/interior cell is removed. Cells
    carrying any trigger, segment, path node or object are never discarded.
    """
    version=struct.unpack_from('<i',road)[0];header=12 if version==-1 else 8
    count_offset=8 if version==-1 else 4
    count=struct.unpack_from('<I',road,count_offset)[0];pos=header;starts=[];ends=[];empty=[]
    for index in range(count):
        starts.append(pos);quads=0
        for _ in range(4):
            number=struct.unpack_from('<I',road,pos)[0];quads+=number
            pos+=4+number*(120 if version==-1 else 104)
            if pos>len(road):raise ValueError('Truncated donor road cells')
        empty.append(quads==0)
        ends.append(pos)
    if pos!=len(road):raise ValueError('Unexpected donor road tail')
    removed={i for i,e in enumerate(empty) if e}
    if not removed:return road,centres,objects,[]
    if len(removed)==count:raise ValueError('Donor road is empty')
    if struct.unpack_from('<I',centres)[0]!=count:raise ValueError('Road/centre cell counts differ')
    pos=4;centre_starts=[];centre_ends=[]
    for index in range(count):
        centre_starts.append(pos);triggers=struct.unpack_from('<2i',centres,pos+12);pos+=20;members=0
        for _ in range(3):
            n=struct.unpack_from('<I',centres,pos)[0];members+=n;pos+=4+4*n
        centre_ends.append(pos)
        if index in removed and (members or any(triggers)):
            raise ValueError('Empty road cell contains active paths/segments/triggers')
    if pos!=len(centres):raise ValueError('Unexpected donor centre tail')
    n=struct.unpack_from('<I',objects)[0]
    if len(objects)!=4+n*68:raise ValueError('Unsupported donor object record format')
    keep=[i for i in range(count) if i not in removed];mapping={old:new for new,old in enumerate(keep)}
    omp=bytearray(objects)
    for i in range(n):
        owner=struct.unpack_from('<i',objects,4+i*68)[0]
        if owner not in mapping:raise ValueError('Empty or invalid road cell still has object placements')
        struct.pack_into('<i',omp,4+i*68,mapping[owner])
    result=bytearray(road[:header]);struct.pack_into('<I',result,count_offset,len(keep))
    result+=b''.join(road[starts[i]:ends[i]] for i in keep)
    pmp=struct.pack('<I',len(keep))+b''.join(centres[centre_starts[i]:centre_ends[i]] for i in keep)
    return bytes(result),pmp,bytes(omp),sorted(removed)

def namespace_timelines(configuration,target,donor,text,anim,records):
    types=(configuration/'anmtypes.ini').read_bytes();prefix='dl_' if donor=='london' else 'da_'
    aliases={v.strip().casefold():prefix+v.strip() for _,s,k,_,m in ini_lines(types)
             if s.startswith('type') and k=='animnames' for v in m[4].split(',')}
    if any(len(v.encode('cp1252'))>=32 for v in aliases.values()):raise ValueError('Animation alias exceeds engine field')
    def rewrite(value):
        return re.sub(r'(?i)(?<![\w])('+ '|'.join(re.escape(n) for n in sorted(aliases,key=len,reverse=True))+r')(?![\w])',
                      lambda m:aliases[m[0].casefold()],value)
    text=rewrite(text);anim=rewrite(anim);data=bytearray(records)
    for n in range(struct.unpack_from('<I',records)[0]):
        at=4+n*68+32;old=data[at:at+32].split(b'\0')[0].decode('cp1252').casefold()
        if old in aliases:data[at:at+32]=aliases[old].encode('cp1252').ljust(32,b'\0')
    target_types=(target/'Game/Ini/anmtypes.ini').read_bytes();count=int(table(target_types,'general')['nranims'])
    present={m[4].strip().casefold() for _,s,k,_,m in ini_lines(target_types) if k=='animnames'};changes={}
    for n in range(int(table(types,'general')['nranims'])):
        fields=table(types,f'type{n}');name=rewrite(fields['animnames'])
        if name.casefold() in present:continue
        for k,v in fields.items():changes[f'type{count}',k]=rewrite(v) if k=='animnames' else v
        count+=1;present.add(name.casefold())
    changes['general','NrAnims']=count
    return text,anim,bytes(data),edit_ini(target_types,changes)


def build_track(source,target,stage=1,slot=21,name="Rotterdam",configuration=None,donor='a2iv',replace_owned=False):
    source=Path(source);target=Path(target);track_name=name
    configuration=Path(configuration or source)
    config=(configuration/'raser.ini').read_bytes();row=table(config,'maps')[str(stage)].split(',')
    stem=row[1].strip();a=Archive(source/'rcs.img');by={}
    for e in a.entries:by.setdefault(e.name.casefold(),[]).append(e)
    text=(configuration/(stem+'.ini')).read_text(encoding='cp1252')
    animname=table(config,'3d anims')[str(stage)]
    anim=(configuration/animname).read_text(encoding='cp1252')
    # Europe requires scripted instances in the animation registry; A2 IV's
    # map definition supplies their single authored mesh/texture directly.
    records=(source/(stem+'.omp')).read_bytes()
    timelines=None
    if donor in ('london','autobahn2'):
        text,anim,records,timelines=namespace_timelines(configuration,target,donor,text,anim,records)
    definition=table(text.encode('cp1252'),'objects')
    scripted=set();used_animations=set()
    for n in range(struct.unpack_from('<I',records)[0]):
        values=struct.unpack_from('<ii6f32si',records,4+n*68)
        used_animations.add(values[8].split(b'\0')[0].decode('cp1252').casefold())
        if values[1]==29:scripted.add(values[8].split(b'\0')[0].decode('cp1252').casefold())
    config_anim=table(anim.encode('cp1252'),'config')
    count=int(config_anim['count'])
    extra={}
    for name in sorted(scripted):
        if table(anim.encode('cp1252'),name):continue
        matches=[v.split(',') for k,v in definition.items() if k.isdigit() and len(v.split(','))>=5 and v.split(',')[4].strip().casefold()==name]
        if len(matches)!=1:raise ValueError('Ambiguous scripted object '+name)
        fields=matches[0]
        mesh=fields[0].strip().replace('\\','/').rsplit('/',1)[-1]
        texture=fields[1].strip().replace('\\','/').rsplit('/',1)[-1]
        extra['config',str(count)]=name;count+=1
        anim+='\r\n['+name+']\r\n0='+mesh+','+texture+'\r\ncount=1\r\n'
    extra['config','count']=count
    anim=edit_ini(anim.encode('cp1252'),extra).decode('cp1252')
    names={m[0].casefold() for m in re.finditer(r'[\w.-]+\.(?:d3d|tga|pcx|wav|fnt|bin)',text+'\n'+anim,re.I)}
    # Editor-only handles are not available in the shipped game archive.
    names.discard('handle.d3d')
    for field in row[2:8]:
        for ext in ('.tga','.pcx'):
            if field.strip().casefold()+ext in by:names.add(field.strip().casefold()+ext)
    waits={sec:table(config,sec)[str(stage)] for sec in ('wait_lo','wait_hi')}
    names.update(x.casefold() for x in waits.values())
    # True-colour rendering substitutes TGA for PCX in animation tables.
    names.update(Path(n).stem+'.tga' for n in list(names) if n.endswith('.pcx') and Path(n).stem+'.tga' in by)
    omitted=[]
    if donor in ('london','autobahn2'):
        active_text='\n'.join(v for k,v in definition.items() if k.isdigit() and len(v.split(','))>=5
                              and v.split(',')[4].strip().casefold() in used_animations)
        active_text+='\n'+'\n'.join(v for section in used_animations for v in table(anim.encode('cp1252'),section).values())
        active_names={m[0].casefold() for m in re.finditer(r'[\w.-]+\.(?:d3d|tga|pcx)',active_text,re.I)}
        for missing in sorted(names-set(by)):
            if missing.endswith('.wav') or missing not in active_names:
                omitted.append(missing);names.remove(missing)
    namespace='a4' if donor=='a2iv' else donor
    rename={name:'x'+hashlib.sha256((namespace+':'+Path(name).stem).encode()).hexdigest()[:7]+Path(name).suffix for name in sorted(names)}
    resources={}
    duplicate_choices={}
    for name in sorted(names):
        if name not in by:raise ValueError('Missing source dependency '+name)
        variants={a.read(e) for e in by[name]}
        if len(variants)!=1:
            if donor not in ('london','autobahn2'):raise ValueError('Ambiguous source dependency '+name)
            # London 0x49b93e-0x49b963 walks IND entries forward and exits at
            # the first matching name. Preserve that lookup order, including
            # obsolete duplicate meshes/textures retained later in the archive.
            duplicate_choices[name]=by[name][0].index
            resources[rename[name]]=a.read(by[name][0])
        else:resources[rename[name]]=variants.pop()
    def rewrite(text):
        pattern=r'(?i)(?<![\w.-])('+ '|'.join(re.escape(n) for n in sorted(rename,key=len,reverse=True))+r')(?![\w.-])'
        return re.sub(pattern,lambda m:rename[m[0].casefold()],text)
    newstem=f'etappe{slot:02d}';payload={}
    for ext in ('.rmp','.pmp','.omp','.cmp','.dmp','.pth'):
        payload[Path(newstem+ext)]=(source/(stem+ext)).read_bytes()
    rmp=payload[Path(newstem+'.rmp')];pmp=payload[Path(newstem+'.pmp')];terminal=[]
    if donor=='autobahn2':
        from .europe_navigation import trim_origin_tail
        rmp,pmp,terminal=trim_origin_tail(rmp,pmp,records,payload[Path(newstem+'.cmp')])
    rmp,pmp,omp,trimmed=compact_empty_cells(rmp,pmp,records)
    crossroads=[]
    if donor=='london' and stage==4:
        from .europe_crossroads import repair as repair_crossroads
        cmp_path=Path(newstem+'.cmp')
        # Body width/overhang needs clearance at the cut ends too. These are
        # foreign scenery boundaries, rather than this road's own curbs.
        rmp,pmp,payload[cmp_path],crossroads=repair_crossroads(rmp,pmp,payload[cmp_path],clearance=20)
    payload[Path(newstem+'.rmp')]=rmp;payload[Path(newstem+'.pmp')]=pmp
    payload[Path(newstem+'.omp')]=omp
    navigation=[]
    if donor=='autobahn2':
        from .europe_navigation import raise_buried_waypoints
        dmp=Path(newstem+'.dmp')
        payload[dmp],navigation=raise_buried_waypoints(rmp,pmp,payload[dmp])
    payload[Path('Ini')/(newstem+'.ini')]=rewrite(text).encode('cp1252')
    payload[Path('Ini')/f'xanim{slot}.ini']=rewrite(anim).encode('cp1252')
    if timelines is not None:payload[Path('Ini/anmtypes.ini')]=timelines
    opponent_source=configuration/'opponent.ini'
    source_opponents=(opponent_source if opponent_source.exists() else target/'Game/Ini/opponent.ini').read_bytes()
    opponent_stage=stage if opponent_source.exists() else 1
    opponent_changes={(sec,str(slot)):m[4].strip()
        for _,sec,key,_,m in ini_lines(source_opponents)
        if sec.startswith('racer ') and key==str(opponent_stage)}
    payload[Path('Ini/opponent.ini')]=edit_ini((target/'Game/Ini/opponent.ini').read_bytes(),opponent_changes)
    traffic=(target/'Game/Ini/traffic.ini').read_bytes()
    traffic_changes={(f'Traffic Track {slot}',key):value for key,value in table(traffic,'Traffic Track 1').items()}
    payload[Path('Ini/traffic.ini')]=edit_ini(traffic,traffic_changes)
    img,ind=archive_bytes(resources)
    archive_name=f'da4t{slot:02d}'
    payload[Path(archive_name+'.img')]=img;payload[Path(archive_name+'.ind')]=ind
    target_config=target/'Game/Ini/Racer.ini';original=target_config.read_bytes()
    maps=table(original,'maps')
    if str(slot) in maps and not replace_owned:raise ValueError('Target map ID already exists; original track preserved.')
    row[1]=newstem
    for n in range(2,8):
        old=row[n].strip().casefold()
        matches={Path(new).stem for name,new in rename.items() if Path(name).stem==old}
        if len(matches)==1:row[n]=matches.pop()
        elif matches:raise ValueError('Texture stem variants need distinct names')
    prefix=DONORS[donor]['label']
    row[8]=prefix+' - '+track_name
    # Europe adds British traffic side after the older fifteen fields.
    row=(row[:15]+['0']*(15-len(row[:15]))+[str(DONORS[donor].get('british',0))])
    changes={('MAPS',str(slot)):','.join(row),('MAPS','count'):max(int(maps['count']),slot+1),
             ('3D Anims',str(slot)):f'xanim{slot}.ini'}
    images=table(original,'img')
    if archive_name not in {v.casefold() for k,v in images.items() if k.isdigit()}:
        changes['IMG',images['count']]=archive_name;changes['IMG','count']=int(images['count'])+1
    for sec,old in waits.items():changes[sec,str(slot)]=rename[old.casefold()]
    payload[Path('Ini/Racer.ini')]=edit_ini(original,changes)
    report={'name':track_name,'source':str(source),'source_stage':stage,'target_slot':slot,'resources':len(resources),'donor':donor,
            'namespace':rename,'duplicate_first_entries':duplicate_choices,'omitted_unavailable_unused_or_audio':omitted,
            'opponents':'source per-track settings' if opponent_source.exists() else 'Europe preset; donor road navigation retained',
            'trimmed_empty_tail_cells':trimmed,'raised_buried_waypoints':navigation,
            'removed_origin_terminal_cells':terminal,
            'trimmed_crossroad_barriers':crossroads,
            'status':'experimental; original-engine validation required'}
    return {Path('Game')/p:v for p,v in payload.items()},report


DONORS={
    'a2ii':dict(title='A2II',profile='a2ii-resolution',label='A2 Racer II',sub=''),
    'holiday':dict(title='Holiday Racer',profile='holiday-resolution',label='Holiday Racer',sub=''),
    'a2iv':dict(title='A2 Racer 4',profile='a2racer4-resolution',label='A2 IV',sub=''),
    'pmr':dict(title='Paris - Marseille Racing',profile='pmr-resolution',label='PMR',sub='data'),
    'london':dict(title='London Racer',profile='london-resolution',label='London Racer',sub='',british=1),
    'autobahn2':dict(title='Autobahn Raser II',profile='autobahn2-resolution',label='AR II',sub=''),
}

TRACK_ADDONS = {
    'a2iv-rotterdam': {'stage':1, 'name':'Rotterdam', 'tested':True},
    'a2iv-scheveningen': {'stage':2, 'name':'Scheveningen', 'tested':True},
    'a2iv-frankfurt': {'stage':6, 'name':'Frankfurt', 'tested':True},
    'a2iv-bodensee': {'stage':7, 'name':'Bodensee', 'tested':True},
    'pmr-lille-paris': {'donor':'pmr','stage':0,'name':'Lille - Paris','tested':False},
    'pmr-paris-lyon': {'donor':'pmr','stage':2,'name':'Paris - Lyon','tested':False},
    'london-m25-day': {'donor':'london','stage':1,'name':'M25 South (day)','tested':False},
    'london-oxford-road': {'donor':'london','stage':3,'name':'Country route to Oxford','tested':False},
    'london-oxford': {'donor':'london','stage':4,'name':'Oxford','tested':False,
                      'withdrawn':'Withdrawn after driving tests: incomplete scenery and incompatible overlapping collision geometry.'},
    'london-london-road': {'donor':'london','stage':5,'name':'Country route to London','tested':False},
    'london-m25-night': {'donor':'london','stage':7,'name':'M25 South (night)','tested':False},
    'london-thames': {'donor':'london','stage':8,'name':'Thames','tested':False,'research_only':True},
    'ar2-munich': {'donor':'autobahn2','stage':0,'name':'Munich','tested':False},
    'ar2-hamburg': {'donor':'autobahn2','stage':2,'name':'Hamburg','tested':False},
    'ar2-dortmund': {'donor':'autobahn2','stage':3,'name':'Dortmund','tested':False},
    'ar2-frankfurt': {'donor':'autobahn2','stage':4,'name':'Frankfurt','tested':False},
    'ar2-hamburg-berlin': {'donor':'autobahn2','stage':8,'name':'Hamburg - Berlin','tested':False},
    'ar2-dortmund-frankfurt': {'donor':'autobahn2','stage':10,'name':'Dortmund - Frankfurt','tested':False},
}


def choices():
    return [{'addon':key,
             'label':'Add-on: '+DONORS[item.get('donor','a2iv')]['label']+' '+item['name']}
            for key,item in TRACK_ADDONS.items() if not item.get('research_only') and not item.get('withdrawn')]


def source_folder(donor='a2iv'):
    """Locate the donor installation without changing it or accepting unknown archives."""
    from .installed import baseline
    spec=DONORS[donor];title=spec['title']
    record=baseline(spec['profile'])
    candidates=[ROOT/'games'/title, ROOT/'analysis/baseline'/title]
    try:
        from .settings import load
        saved=load()
        from .toolkit import GAMES
        name=next(k for k,v in GAMES.items() if v==spec['profile'])
        if saved.get('installs',{}).get(name):
            candidates.append(Path(saved['installs'][name]))
    except (OSError,ValueError,TypeError):pass
    candidates.append(Path(record['source']))
    from .discovery import candidates as installed_candidates
    candidates.extend(installed_candidates(title,ROOT))
    for folder in candidates:
        if (folder/spec['sub']/'rcs.img').is_file():return folder.resolve()
    raise ValueError(title+' donor files are required for this add-on. Locate its installation in the toolkit first.')


def payload(directory, addon, slot=None, replace_owned=False):
    from .installed import baseline,digest
    if addon not in TRACK_ADDONS:raise ValueError('Unknown Europe track add-on.')
    item=TRACK_ADDONS[addon];donor=item.get('donor','a2iv');spec=DONORS[donor]
    if item.get('withdrawn'):raise ValueError(item['withdrawn'])
    source=source_folder(donor)/spec['sub']
    configuration=resources(ROOT)/'analysis/baseline'/spec['title']/spec['sub']
    maps=table((configuration/'raser.ini').read_bytes(),'maps')
    stem=maps[str(item['stage'])].split(',')[1].strip()
    expected={str(Path(f['path'])).casefold():f['sha256'] for f in baseline(spec['profile'])['files']}
    required=['rcs.img','rcs.ind']+[stem+ext for ext in ('.rmp','.pmp','.omp','.cmp','.dmp','.pth')]
    for name in required:
        path=source/name
        if not path.is_file() or digest(path.read_bytes())!=expected.get(str(Path(spec['sub'])/name).casefold()):
            raise ValueError('Unrecognised or modified donor file; preserved: '+str(path))
    if slot is None:slot=int(table((Path(directory)/'Game/Ini/Racer.ini').read_bytes(),'maps')['count'])
    from .europe_tracks import CAPACITY
    if not 0<=slot<CAPACITY:raise ValueError(f'Europe track slots are full ({CAPACITY} total).')
    return build_track(source,Path(directory),item['stage'],slot,item['name'],configuration,donor,replace_owned)



REGISTRY=Path('Game/davilex-addons.json')
CONVERTER_VERSION=7
SHARED={Path('Game/Ini/Racer.ini'),Path('Game/Ini/opponent.ini'),Path('Game/Ini/traffic.ini'),Path('Game/Ini/anmtypes.ini')}
DYNAMIC_SCENE_SECTIONS={'difficulty','cops','fog','weather'}


def registry(directory):
    path=Path(directory)/REGISTRY
    if not path.exists():return {'format':1,'tracks':{}}
    result=json.loads(path.read_text(encoding='utf-8'))
    if result.get('format')!=1 or not isinstance(result.get('tracks'),dict):
        raise ValueError('Unrecognised add-on registry; existing files preserved.')
    return result


def withdraw_retired_tracks(directory):
    """Remove retired race choices without renumbering other engine tracks.

    TRACKS is the menu's ID/name database; QUICKRACE defines selectable races.
    Retain an unused database slot and owned assets for reversible restoration.
    Mark its engine catalogue row empty, so older toolkit Quick Race views also
    omit it. Keep the withdrawn ownership record out of active track upgrades.
    """
    from .installed import ACTIVE,commit
    directory=Path(directory).resolve();active=ACTIVE.get()
    if not active or active['directory']!=directory or not active['profile'].startswith('europe'):
        raise ValueError('Track withdrawal requires an active Europe session.')
    state=registry(directory);retired={key:item for key,item in state['tracks'].items()
        if TRACK_ADDONS.get(key,{}).get('withdrawn')}
    if not retired:return []
    ids={int(item['engine_id'])for item in retired.values()}
    menu_path=Path('Menu/GameMenu.ini');raw=(directory/menu_path).read_bytes()
    entries=table(raw,'quickrace');numeric=sorted((int(k),v)for k,v in entries.items()if k.isdigit())
    kept=[(key,value)for key,value in numeric if int(value.split(',')[0])not in ids]
    lines=raw.decode('cp1252').splitlines(keepends=True)
    slots=[i for i,s,k,_,m in ini_lines(raw)if s=='quickrace' and k.isdigit()]
    for at in slots:lines[at]=''
    if slots:
        lines[min(slots)]=''.join(f'{i}={value}\r\n'for i,(old,value)in enumerate(kept))
    menu=''.join(lines).encode('cp1252')
    if 'count' in entries:menu=edit_ini(menu,{('QUICKRACE','count'):len(kept)})
    new_races={int(value.split(',')[0]):i for i,(old,value)in enumerate(kept)}
    for key,item in list(state['tracks'].items()):
        if key not in retired and int(item['engine_id'])in new_races:item['quickrace_id']=new_races[int(item['engine_id'])]
    racer_path=Path('Game/Ini/Racer.ini');racer=(directory/racer_path).read_bytes();maps=table(racer,'maps');changes={}
    for key,item in retired.items():
        row=maps[str(item['engine_id'])].split(',');row[8]='empty'
        changes['MAPS',str(item['engine_id'])]=','.join(row)
        state.setdefault('withdrawn_tracks',{})[key]=dict(item,reason=TRACK_ADDONS[key]['withdrawn'])
        del state['tracks'][key]
    files={menu_path:menu,racer_path:edit_ini(racer,changes),REGISTRY:(json.dumps(state,indent=2)+'\n').encode('utf-8')}
    game_path=Path('Game/Ini/game.ini');game=(directory/game_path).read_bytes()
    if int(table(game,'etappe').get('etappe','-1'))in ids:files[game_path]=edit_ini(game,{('ETAPPE','etappe'):0})
    commit(directory,files)
    print('Withdrawn downloaded track: '+', '.join(item['name']for item in retired.values()),flush=True)
    return list(retired)


def scene_ini_equivalent(original,current):
    """The engine appends defaults to converted scene files at race startup."""
    def stable(raw):return {(s,k,n):m[4].strip() for _,s,k,n,m in ini_lines(raw) if s not in DYNAMIC_SCENE_SECTIONS}
    return stable(original)==stable(current)


def install(directory,addon):
    """Append engine/menu records with original files journalled by installed.commit."""
    from .installed import ACTIVE,commit,digest,safe_target
    directory=Path(directory).resolve();active=ACTIVE.get()
    if not active or active['directory']!=directory or not active['profile'].startswith('europe'):
        raise ValueError('Install add-ons inside an active verified Europe session.')
    if TRACK_ADDONS.get(addon,{}).get('withdrawn'):raise ValueError(TRACK_ADDONS[addon]['withdrawn'])
    if addon.startswith('pack-'):
        from .content_packs import install as install_pack
        return install_pack(directory,addon)
    if addon=='europe-classics':return install_classics(directory)
    if addon=='europe-all-cars':
        from .car_addons import install as install_car,CATALOG
        classics=install_classics(directory)
        return {'classics':classics,'converted_cars':[install_car(directory,key)for key in CATALOG]}
    if addon.startswith('car-'):
        from .car_addons import install as install_car
        return install_car(directory,addon)
    state=registry(directory)
    if addon in state['tracks']:
        item=state['tracks'][addon]
        from .installed import journal_folder
        for relative,expected in item['assets'].items():
            path=safe_target(directory,relative)
            current=path.read_bytes() if path.is_file() else None
            snapshot=journal_folder(directory)/'patched'/expected
            compatible=(current is not None and path.suffix.casefold()=='.ini' and snapshot.is_file()
                        and scene_ini_equivalent(snapshot.read_bytes(),current))
            if current is None or (digest(current)!=expected and not compatible):
                raise ValueError('Installed add-on asset changed; preserved: '+str(path))
        if item.get('converter_version',0)<CONVERTER_VERSION:
            files,report=payload(directory,addon,item['engine_id'],replace_owned=True)
            for relative,raw in list(files.items()):
                if relative in SHARED or relative.suffix.casefold()!='.ini':continue
                path=directory/relative
                if path.exists():
                    dynamic={(s,k):m[4].strip() for _,s,k,_,m in ini_lines(path.read_bytes()) if s in DYNAMIC_SCENE_SECTIONS}
                    files[relative]=edit_ini(raw,dynamic)
            item['assets']={str(p):digest(b) for p,b in files.items() if p not in SHARED}
            item['converter_version']=CONVERTER_VERSION
            files[REGISTRY]=(json.dumps(state,indent=2)+'\n').encode('utf-8')
            commit(directory,files)
        if not item.get('preview'):install_donor_preview(directory,addon)
        return registry(directory)['tracks'][addon]
    files,report=payload(directory,addon)
    # Only shared configuration is edited. New map/archive files must be absent.
    shared=SHARED
    for relative in files:
        if relative not in shared and (directory/relative).exists():
            raise ValueError('Add-on output already exists; preserving '+str(directory/relative))
    menu=directory/'Menu/GameMenu.ini';original=menu.read_bytes()
    tracks=table(original,'tracks');quick=table(original,'quickrace')
    slot=report['target_slot']
    # The original menu reads contiguous numbered records, rather than a fixed
    # 21-item list. Refuse gaps/collisions rather than redirect an existing entry.
    if str(slot) in tracks or set(map(str,range(slot)))!={k for k in tracks if k.isdigit()}:
        raise ValueError('Menu and engine track IDs disagree; original entries preserved.')
    race_slot=max(map(int,(k for k in quick if k.isdigit())),default=-1)+1
    donor=report['donor'];title=DONORS[donor]['label']+' - '+report['name']
    changes={('TRACKS',str(slot)):f'TC_DOWNLOADED,CT_STANDARD,{title},{title},{title}',
             ('QUICKRACE',str(race_slot)):f'{slot},3,3,5,5,4,4'}
    files[Path('Menu/GameMenu.ini')]=edit_ini(original,changes)
    item={'name':report['name'],'engine_id':slot,'quickrace_id':race_slot,
            'converter_version':CONVERTER_VERSION,
            'source_game':DONORS[donor]['title'],'source_stage':report['source_stage'],
          'validation':'User confirmed driving and additive original-menu launch, 2026-11-02' if TRACK_ADDONS[addon]['tested'] else 'experimental; gameplay not yet verified',
          'assets':{str(p):digest(b) for p,b in files.items() if p not in shared and p!=Path('Menu/GameMenu.ini')}}
    state['tracks'][addon]=item
    files[REGISTRY]=(json.dumps(state,indent=2)+'\n').encode('utf-8')
    count=commit(directory,files)
    print(f'Installed {title} as downloaded track {slot} ({count} changed files). Original tracks retained.',flush=True)
    install_donor_preview(directory,addon)
    return registry(directory)['tracks'][addon]



def install_classics(directory):
    """Use the three downloaded-car definitions shipped in the official XP update."""
    from .installed import commit
    directory=Path(directory);menu=directory/'Menu/GameMenu.ini';original=menu.read_bytes()
    cars=table(original,'cars');next_id=max(map(int,(k for k in cars if k.isdigit())),default=-1)+1
    existing={int(value.split(',')[0]) for key,value in cars.items() if key.isdigit()}
    changes={};added=[]
    for engine_id,name in [(2,'Checker'),(18,'Jaguar'),(30,'Saab')]:
        if engine_id in existing:continue
        changes['CARS',str(next_id)]=f'{engine_id},CT_DOWNLOADED,LT_CD_EXTRA,20,10,30,40,60,10,40,50,70,30,80,60,80,40,90,100'
        added.append({'name':name,'engine_id':engine_id,'menu_id':next_id});next_id+=1
    if changes:
        state=registry(directory);state.setdefault('cars',[]).extend(added)
        commit(directory,{Path('Menu/GameMenu.ini'):edit_ini(original,changes),
                          REGISTRY:(json.dumps(state,indent=2)+'\n').encode('utf-8')})
    print('Original downloaded-car definitions enabled: Checker, Jaguar, Saab.',flush=True)
    install_classic_portraits(directory)
    return {'name':'Europe classic cars','added':added}


def install_preview(directory,addon,image):
    """Write the menu's trkNN a preview into its separate Extra archive."""
    return install_preview_bytes(directory,addon,Path(image).read_bytes())


def install_preview_bytes(directory,addon,image,source=None):
    from .installed import ACTIVE,commit
    import io
    from PIL import Image,ImageOps
    directory=Path(directory).resolve();active=ACTIVE.get()
    if not active or active['directory']!=directory or not active['profile'].startswith('europe'):
        raise ValueError('Preview installation requires an active Europe session.')
    state=registry(directory)
    if addon not in state['tracks']:raise ValueError('Install the track before adding its preview.')
    item=state['tracks'][addon];resource=f"trk{item['engine_id']:02d}a.tga"
    archive=Archive(directory/'Menu/Extra.IMG');images={}
    for entry in archive.entries:
        key=entry.name.casefold()
        if key in images:raise ValueError('Ambiguous Extra archive entries; original preserved.')
        images[key]=archive.read(entry)
    with Image.open(io.BytesIO(image)) as im:
        # Preserve screenshot proportions; the original menu previews are 160x160.
        thumb=ImageOps.pad(im.convert('RGB'),(160,160),method=Image.Resampling.LANCZOS,color='black')
        stream=io.BytesIO();thumb.save(stream,format='TGA');images[resource]=stream.getvalue()
    img,ind=archive_bytes(images)
    item['preview']=resource
    if source:item['preview_source']=source
    else:item.pop('preview_source',None)
    commit(directory,{Path('Menu/Extra.IMG'):img,Path('Menu/Extra.IND'):ind,
                      REGISTRY:(json.dumps(state,indent=2)+'\n').encode('utf-8')})
    print('Installed 160x160 menu preview '+resource,flush=True)


def donor_preview(addon):
    """Reuse the donor's actual route card, without replacing user screenshots."""
    item=TRACK_ADDONS[addon];donor=item.get('donor','a2iv');folder=source_folder(donor)
    if donor=='a2iv':
        name=f"ttc{item['stage']:02d}_00.tga";archive=Archive(folder/'menurcs.img')
        matches=[e for e in archive.entries if e.name.casefold()==name]
        if len(matches)!=1:raise ValueError('Donor route card is missing or ambiguous: '+name)
        return archive.read(matches[0]),'A2 Racer IV menurcs.img / '+name
    spec=DONORS[donor];folder/=spec['sub']
    rows=table((folder/'static.ini').read_bytes(),'tracks')
    matches=[v.split(',') for k,v in rows.items() if k.isdigit() and v.split(',')[0].strip()==str(item['stage'])]
    if len(matches)!=1:raise ValueError('Cannot identify donor route card')
    name=matches[0][3].strip()+'.bmp'
    return (folder/name).read_bytes(),spec['title']+' / '+name


def install_donor_preview(directory,addon):
    item=registry(Path(directory))['tracks'][addon]
    if item.get('preview'):return
    image,source=donor_preview(addon)
    install_preview_bytes(directory,addon,image,source)


def install_classic_portraits(directory):
    """Supply actual-model portraits; replace only the known incorrect donor art."""
    from .installed import commit
    from .car_portraits import portrait
    directory=Path(directory)
    extra=Archive(directory/'Menu/Extra.IMG');graphics=Archive(directory/'Menu/Graphics.IMG')
    known={e.name.casefold() for a in (extra,graphics) for e in a.entries}
    images={e.name:extra.read(e) for e in extra.entries};state=registry(directory);owned=state.setdefault('car_previews',{});changed=False
    wrong_jaguar='bd77a1098a786fc5c95cff8a4b2c3a6c8c095828955388ea4ff702758e49bc0d'
    for car in (18,30):
        name=f'car{car:02d}a.tga';existing=images.get(name)
        if name in known and not (car==18 and existing and hashlib.sha256(existing).hexdigest()==wrong_jaguar):continue
        images[name]=portrait(directory,car);changed=True
        owned[str(car)]={'resource':name,'sha256':hashlib.sha256(images[name]).hexdigest(),
                         'source':'Rendered Europe Racer vehicle, intact damage panels and wheels; static glass reflection'}
    if not changed:return
    img,ind=archive_bytes(images)
    commit(directory,{Path('Menu/Extra.IMG'):img,Path('Menu/Extra.IND'):ind,
                      REGISTRY:(json.dumps(state,indent=2)+'\n').encode('utf-8')})
    print('Installed matching Europe Jaguar/Saab model portraits.',flush=True)


def refresh_previews(directory):
    """Fill missing donor artwork on existing installs; custom previews win."""
    state=registry(Path(directory))
    for addon in state['tracks']:
        if addon not in TRACK_ADDONS or state['tracks'][addon].get('preview'):continue
        try:install_donor_preview(directory,addon)
        except (OSError,ValueError) as error:print('Optional donor preview unavailable:',error,flush=True)
    if state.get('cars'):
        try:install_classic_portraits(directory)
        except (OSError,ValueError) as error:print('Optional car portrait unavailable:',error,flush=True)

"""Verified donor vehicle assemblies adapted to Europe's vehicle controller."""
import hashlib,json,re,struct,io
from pathlib import Path
from .addons import table,archive_bytes,source_folder,REGISTRY,registry
from .installed import edit_ini
from .translate import ini_lines
from .paths import ROOT,resources

COUNTRIES=('US','JP','RU','DE','GB','FR','IT','NL')
CATEGORIES={'standard':('CT_STANDARD',3,0),'sports':('CT_SPORT',2,1),'offroad':('CT_ATV',1,3),'classic':('CT_DOWNLOADED',4,2)}
CATALOG={
 'car-a4-hotrod':dict(donor='a2iv',row=1,name='Hot Rod',country=0,category='sports'),
 'car-a4-delorean':dict(donor='a2iv',row=7,name='DeLorean DMC-12',country=0,category='sports'),
 'car-a4-humvee':dict(donor='a2iv',row=5,name='Humvee',country=0,category='offroad'),
}
for _key,_donor,_league,_row,_name,_country,_category in [
    ('lr-mini', 'london', 0, 0, 'Mini', 4, 'standard'),
    ('lr-smart', 'london', 0, 2, 'Smart City Coupe', 3, 'standard'),
    ('lr-mgf', 'london', 0, 4, 'MG F', 4, 'sports'),
    ('lr-z3', 'london', 0, 6, 'BMW Z3', 3, 'sports'),
    ('lr-jaguar', 'london', 1, 0, 'Jaguar XK8', 4, 'sports'),
    ('lr-aston', 'london', 1, 2, 'Aston Martin DB7', 4, 'sports'),
    ('lr-tvr', 'london', 1, 4, 'TVR Cerbera', 4, 'sports'),
    ('lr-rolls', 'london', 1, 6, 'Rolls-Royce', 4, 'classic'),
    ('lr-porsche', 'london', 2, 0, 'Porsche 911', 3, 'sports'),
    ('lr-megane', 'london', 2, 2, 'Renault Megane Rally', 5, 'sports'),
    ('ar2-trabant', 'autobahn2', 0, 4, 'Trabant', 3, 'classic'),
    ('ar2-aclass', 'autobahn2', 0, 6, 'Mercedes-Benz A-Class', 3, 'standard'),
    ('ar2-astra', 'autobahn2', 1, 0, 'Opel Astra', 3, 'standard'),
    ('ar2-golf', 'autobahn2', 1, 2, 'Volkswagen Golf GTI', 3, 'standard'),
    ('ar2-beetle', 'autobahn2', 1, 4, 'Volkswagen New Beetle', 3, 'standard'),
    ('ar2-tt', 'autobahn2', 2, 4, 'Audi TT', 3, 'sports'),
    ('ar2-slr', 'autobahn2', 2, 6, 'Mercedes-Benz SLR', 3, 'sports'),
    ('hr-ami', 'holiday', 0, 0, 'Citroen Ami', 5, 'classic'),
    ('hr-camper', 'holiday', 0, 1, 'Motorhome', 3, 'offroad'),
    ('hr-2cv', 'holiday', 0, 2, 'Citroen 2CV', 5, 'classic'),
    ('hr-volvo', 'holiday', 0, 3, 'Volvo Estate', 7, 'standard'),
    ('hr-jeep', 'holiday', 0, 4, 'Jeep (Holiday Racer)', 0, 'offroad'),
    ('hr-ferrari', 'holiday', 0, 5, 'Ferrari (Holiday Racer)', 6, 'sports'),
    ('pmr-fiat', 'pmr', 0, 2, 'Fiat 500', 6, 'classic'),
    ('pmr-ds', 'pmr', 0, 6, 'Citroen DS', 5, 'classic'),
    ('pmr-saxo', 'pmr', 1, 0, 'Citroen Saxo', 5, 'standard'),
    ('pmr-peugeot', 'pmr', 1, 2, 'Peugeot (PMR)', 5, 'standard'),
    ('pmr-alpine', 'pmr', 1, 6, 'Renault Alpine', 5, 'sports'),
    ('pmr-lotus', 'pmr', 2, 2, 'Lotus Esprit', 4, 'sports'),
    ('pmr-alfa', 'pmr', 0, 9, 'Alfa Romeo 155', 6, 'standard'),
]:
    CATALOG['car-'+_key]=dict(donor=_donor,league=_league,row=_row,name=_name,country=_country,category=_category)
for _row,_name,_category in [(3,'BMW 3-Series (A2 II)','sports'),(4,'Porsche 911 (A2 II)','sports'),(5,'Mercedes-Benz CLK GTR','sports'),(6,'Lamborghini Diablo','sports'),(1,'Opel Astra (A2 II)','standard')]:
    CATALOG[f'car-a2ii-{_row}']=dict(donor='a2ii',league=0,row=_row,name=_name,country=6 if _row==6 else 3,category=_category)
# The menu's extended TLanguageText enum has one bounded entry per added car.
CATALOG['car-hr-volvo']['origin']='SE'
MENU_DESCRIPTION_KEYS={i:f'LT_DV_CAR{i}'for i in range(78,128)}

def choices():
    return [{'addon':key,'label':f"Car: {item['name']} ({item.get('origin',COUNTRIES[item['country']])} / {item['category']})"}
            for key,item in CATALOG.items()]

def dynamics_a4(raw,seed):
    """Copy matching fields; retain Europe's different tyre/steering equations.

    A2 IV 0x429710 / Europe 0x4560b0 establish the shared field blocks.
    Later upgrade columns reuse the last complete donor column, rather than
    exposing uninitialised donor data. This is an explicit compatibility profile,
    not a claim of identical driving across the two engine versions.
    """
    if len(raw)!=616 or len(seed)!=1032:raise ValueError('Unsupported vehicle dynamics layout')
    valid=[i for i in range(5)if 1<=struct.unpack_from('<i',raw,72+4*i)[0]<=6 and
           all(struct.unpack_from('<f',raw,o+4*i)[0]>0 for o in (92,112,152,492,552))]
    if not valid or valid[0]!=0:raise ValueError('Missing complete donor base handling')
    result=bytearray(seed);result[:16]=raw[:16];result[24:28]=raw[24:28];result[308:312]=raw[68:72]
    columns=[]
    for n in range(5):
        source=max((v for v in valid if v<=n),default=0);columns.append(source)
        for old,new in [(o,o+240) for o in range(28,68,20)]+[(o,o+240)for o in range(72,212,20)]+[(o,o+240)for o in range(492,612,20)]:
            result[new+4*n:new+4*n+4]=raw[old+4*source:old+4*source+4]
        result[452+24*n:476+24*n]=raw[212+24*source:236+24*source]
    result[852:856]=raw[612:616]
    return bytes(result),{'source_columns':columns,'preserved':'mass, centre of mass, extra gravity, brakes, engine, gearbox, drive split, suspension, wheel radius',
                         'adapter':'Europe category tyre curve, steering response, clipping and extended controller fields'}

def verified_source():
    from .installed import baseline,digest
    folder=source_folder('a2iv');record=baseline('a2racer4-resolution')
    known={str(Path(f['path'])).casefold():f['sha256'] for f in record['files']}
    for name in ('rcs.img','rcs.ind','car_cfg.ini','L0_anim.ini','gen_anim.ini','damage.ini','vdyns.dat'):
        configuration=resources(ROOT)/'analysis/baseline/A2 Racer 4'
        path=(configuration if name.casefold().endswith('.ini')else folder)/name
        if not path.is_file() or digest(path.read_bytes())!=known.get(str(Path(name)).casefold()):
            raise ValueError('Unknown donor car file; preserved: '+str(path))
    return folder

def payload(directory,key,slot=None):
    from .rcs import Archive
    from .mesh import decode
    directory=Path(directory);item=CATALOG[key]
    if item['donor']!='a2iv':
        from .legacy_car_addons import payload as legacy_payload
        return legacy_payload(directory,key,slot)
    source=verified_source()
    configuration=resources(ROOT)/'analysis/baseline/A2 Racer 4'
    cfg=(configuration/'car_cfg.ini').read_bytes();animations=(configuration/'L0_anim.ini').read_bytes();damage=(configuration/'damage.ini').read_bytes()
    row=[x.strip()for x in table(cfg,'league0')[str(item['row'])].split(',')]
    current=(directory/'Game/Ini/Cars.ini').read_bytes();car_count=int(table(current,'cars')['count'])
    if slot is None:slot=car_count
    if not 78<=slot<128:raise ValueError('No verified unused vehicle slot below the expanded 128-record dynamics limit')
    prefix=f'd{slot}_';ref=prefix+'vehicle';animref=prefix+'anim'
    frames=table(animations,row[1]);parts={}
    source_damage=next(v.split(',')for k,v in table(damage,'damage models').items()if k.isdigit()and v.split(',')[0].strip().casefold()==row[8].casefold())
    damaged_car=source_damage[5].strip();damage_car=next(v.split(',')for k,v in table(damage,'damageable cars').items()if k.isdigit()and v.split(',')[0].strip().casefold()==damaged_car.casefold())
    phases=[s.strip()for s in damage_car[3:]if s.strip()]
    source_objects=[v for k,v in table(damage,'damageable car objects').items()if k.isdigit()and v.split(',')[0].strip().casefold()in {s.casefold()for s in phases}]
    general=(configuration/'gen_anim.ini').read_bytes()
    for value in source_objects:
        alias=value.split(',')[1].strip();binding=table(general,alias).get('0')
        if binding is None:raise ValueError('Missing intact/damage panel binding: '+alias)
        parts[str(len(parts))]=alias+','+binding
    parts['count']=str(len(parts))
    aliases={row[8].casefold():prefix+row[8],damaged_car.casefold():prefix+damaged_car}
    aliases.update({s.casefold():prefix+s for s in phases})
    for k,v in parts.items():
        if k.isdigit():aliases[v.split(',')[0].strip().casefold()]=prefix+v.split(',')[0].strip()
    archive=Archive(source/'rcs.img');by={}
    for e in archive.entries:by.setdefault(e.name.casefold(),[]).append(e)
    texture_donor=None
    if key=='car-a4-delorean':
        # A2 IV retains London's exact DeLorean meshes, but its repacked sheets
        # no longer match their UVs (the wheel samples traffic-car bodywork).
        from .installed import baseline,digest
        london=source_folder('london');known={str(Path(f['path'])).casefold():f['sha256']
                                            for f in baseline('london-resolution')['files']}
        for name in ('rcs.img','rcs.ind'):
            if digest((london/name).read_bytes())!=known[str(Path(name)).casefold()]:
                raise ValueError('Unknown matching DeLorean texture donor; preserved: '+str(london/name))
        texture_donor=Archive(london/'rcs.img')
        for name in ('delorean.d3d','delo_wie.d3d','delo_ram.d3d'):
            donor=next(e for e in texture_donor.entries if e.name.casefold()==name)
            if texture_donor.read(donor)!=archive.read(by[name][0]):
                raise ValueError('DeLorean texture donor geometry differs: '+name)
    assets={};renames={}
    def asset(name):
        name=name.replace('\\','/').split('/')[-1].strip().casefold()
        if name in renames:return renames[name]
        actual=name
        if actual not in by and name.endswith('.pcx'):actual=str(Path(name).with_suffix('.tga'))
        selected_archive=archive
        if texture_donor is not None and name in ('l1racer2.pcx','cars01.pcx'):
            actual=str(Path(name).with_suffix('.tga'));selected_archive=texture_donor
            matches=[e for e in texture_donor.entries if e.name.casefold()==actual]
        else:matches=by.get(actual,[])
        if not matches:raise ValueError('Missing donor resource: '+name)
        variants={selected_archive.read(e)for e in matches}
        if len(variants)!=1:raise ValueError('Ambiguous donor car resource: '+name)
        raw=variants.pop();extension=Path(actual).suffix
        if extension=='.pcx':
            # Europe's true-colour loader resolves even PCX references to TGA.
            from .media import load_image
            image=load_image(archive,matches[0]);stream=io.BytesIO()
            image.convert('RGB').save(stream,format='TGA');raw=stream.getvalue();extension='.tga'
        new=f'v{slot:02x}'+hashlib.sha256(actual.encode()).hexdigest()[:5]+extension
        if new in assets and assets[new]!=raw:raise ValueError('Vehicle resource namespace collision')
        if actual.endswith('.d3d'):decode(raw)
        assets[new]=raw;renames[name]=new
        return new
    def rewrite(value):
        # Replace resources and animation/damage aliases as whole tokens.
        for name in re.findall(r'(?i)[\w.\\/ -]+\.(?:d3d|pcx|tga|wav)',value):
            stripped=name.strip();value=value.replace(stripped,asset(stripped))
        for old,new in sorted(aliases.items(),key=lambda v:len(v[0]),reverse=True):
            value=re.sub(r'(?i)(?<![\w])'+re.escape(old)+r'(?![\w])',lambda _:new,value)
        return value
    changes={};kind=CATEGORIES[item['category']][1];seed_id=CATEGORIES[item['category']][2]
    for k,v in frames.items():changes[animref,k]=rewrite(v) if k.isdigit() else v
    for k,v in parts.items():changes[ref,k]=rewrite(v) if k.isdigit() else v
    for section in ('wheel_positions','light_positions'):
        value=table(cfg,section).get(row[5])
        if section=='wheel_positions' and key=='car-a4-delorean' and value is not None:
            # Retained bonus-car data reverses the rear axle's half-width.
            # Europe's player controller pairs +/- X in a fixed wheel order.
            # Restore that ordering without changing either wheel's distance.
            coordinates=[float(x)for x in value.split(',')]
            coordinates[0]=abs(coordinates[0]);coordinates[3]=abs(coordinates[3])
            value=','.join(format(x,'.9g')for x in coordinates)
        if value is not None:changes[section,str(slot)]=value
    name=ref;changes['cars',str(slot)]=','.join((name,animref,'RACER',row[3],row[4],str(slot),row[6],str(slot),aliases[row[8].casefold()],'1.0','0',str(kind)))
    changes['cars','count']=max(car_count,slot+1)
    dyn=(source/'vdyns.dat').read_bytes();index=int(row[7]);raw=dyn[index*616:(index+1)*616]
    # Always use the unmodified, authored Europe seed from the captured baseline.
    seed=resources(ROOT)/f'analysis/baseline/Europe Racer/Game/Vdyns/VDYNS{seed_id}.DAT'
    if not seed.exists():seed=directory/f'Game/Vdyns/VDYNS{seed_id}.DAT'
    from .installed import baseline,digest
    expected_seed=next(f['sha256']for f in baseline('europe-resolution')['files']
                       if str(Path(f['path'])).casefold()==str(Path(f'Game/Vdyns/VDYNS{seed_id}.DAT')).casefold())
    if digest(seed.read_bytes())!=expected_seed:raise ValueError('Unknown Europe handling seed; existing vehicle files preserved')
    converted,handling=dynamics_a4(raw,seed.read_bytes())
    target_damage=(directory/'Game/Ini/damage.ini').read_bytes();damage_changes={}
    def append(section,values):
        count=int(table(target_damage,section)['count'])
        existing=table(target_damage,section)
        for value in values:
            value=rewrite(value);fields=value.split(',');identity=fields[:2]if section=='damageable car objects'else fields[:1]
            found=[k for k,v in existing.items()if k.isdigit()and v.split(',')[:len(identity)]==identity]
            key=found[0]if len(found)==1 else str(count)
            if not found:count+=1
            damage_changes[section,key]=value
        damage_changes[section,'count']=count
    model=','.join(source_damage)+(',1.0' if len(source_damage)==7 else '')
    append('damage models',[model]);append('damageable cars',[','.join(damage_car)])
    append('damageable car objects',source_objects)
    # Named registry list: these additional assemblies are loaded alongside the
    # original [CARS] entries, with resources in a separate namespace/archive.
    racer=(directory/'Game/Ini/Racer.ini').read_bytes();images=table(racer,'img');stem=f'dvcar{slot}'
    img,ind=archive_bytes(assets)
    files={Path('Game/Ini/Cars.ini'):edit_ini(current,changes),Path('Game/Ini/damage.ini'):edit_ini(target_damage,damage_changes),
           Path('Game/Ini/Racer.ini'):edit_ini(racer,{}if stem in images.values()else{('IMG',images['count']):stem,('IMG','count'):int(images['count'])+1}),
           Path(f'Game/{stem}.img'):img,Path(f'Game/{stem}.ind'):ind,Path(f'Game/Vdyns/VDYNS{slot}.DAT'):converted}
    menu_files,menu_id=menu_registration(directory,slot,item)
    files.update(menu_files)
    return files,{**item,'engine_id':slot,'menu_id':menu_id,'internal_name':name,'handling':handling,
                  'material_donor':'London Racer: identical body/wheel/glass meshes' if texture_donor is not None else 'A2 Racer IV',
                  'rear_axle_order_corrected':key=='car-a4-delorean',
                  'source_dynamics_index':index,'resources':len(assets),'damage_parts':len(source_objects),
                  'status':'experimental compatibility conversion; driving not verified'}

def install(directory,key):
    from .installed import ACTIVE,commit,digest
    directory=Path(directory).resolve();active=ACTIVE.get()
    if not active or active['directory']!=directory or not active['profile'].startswith('europe'):
        raise ValueError('Car installation requires an active verified Europe session')
    state=registry(directory);cars=state.setdefault('converted_cars',{})
    existing=cars.get(key)
    donor=CATALOG[key]['donor']
    converter_version=12 if donor=='a2ii'else 8 if donor=='a2iv'else 9
    if existing:
        for name,expected in existing['assets'].items():
            path=directory/name
            if not path.is_file()or digest(path.read_bytes())!=expected:raise ValueError('Converted car asset changed; preserved: '+str(path))
        if existing.get('converter_version')==converter_version:
            install_portrait(directory,key)
            return registry(directory)['converted_cars'][key]
    files,report=payload(directory,key,existing['engine_id']if existing else None)
    for p in files:
        if p.suffix.casefold()in ('.img','.ind') and (directory/p).exists()and not(existing and str(p)in existing['assets']):raise ValueError('Car output collision; existing file preserved: '+str(p))
    owned={str(p):digest(b)for p,b in files.items()if p.suffix.casefold()not in ('.ini',)}
    preview={k:v for k,v in (existing or {}).items()if k in ('preview','preview_sha256','portrait_version')}
    cars[key]={**report,**preview,'converter_version':converter_version,'assets':owned};files[REGISTRY]=(json.dumps(state,indent=2)+'\n').encode('utf-8')
    commit(directory,files)
    print(f"Installed {report['name']} as additional car {report['engine_id']}",flush=True)
    install_portrait(directory,key)
    return registry(directory)['converted_cars'][key]

def install_portrait(directory,key):
    from .installed import commit,digest
    from .rcs import Archive
    from .car_portraits import portrait
    directory=Path(directory);state=registry(directory);item=state['converted_cars'][key]
    name=f"car{item['engine_id']:02d}a.tga";extra=Archive(directory/'Menu/Extra.IMG')
    images={e.name:extra.read(e)for e in extra.entries}
    old=next((n for n in images if n.casefold()==name.casefold()),None)
    version=3 # Mirrored portrait wheels retain their outward-facing triangles.
    if old:
        if item.get('portrait_version',1)==version:return
        if digest(images[old])!=item.get('preview_sha256'):return # Preserve user art.
        del images[old]
    images[name]=portrait(directory,item['engine_id']);img,ind=archive_bytes(images)
    item['preview']=name;item['preview_sha256']=digest(images[name]);item['portrait_version']=version
    commit(directory,{Path('Menu/Extra.IMG'):img,Path('Menu/Extra.IND'):ind,
                      REGISTRY:(json.dumps(state,indent=2)+'\n').encode('utf-8')})


def menu_registration(directory,slot,item):
    files={}
    menu=(directory/'Menu/GameMenu.ini').read_bytes();menu_cars=table(menu,'cars')
    present=[int(k)for k,v in menu_cars.items()if k.isdigit()and int(v.split(',')[0])==slot]
    menu_id=present[0]if present else max(int(k)for k in menu_cars if k.isdigit())+1
    label=f"{item['name']} ({item.get('origin',COUNTRIES[item['country']])} / {item['category'].title()})"
    language=(directory/'Menu/Language.ini').read_bytes()
    if slot not in MENU_DESCRIPTION_KEYS:raise ValueError('No unused compiled menu description slot; menu expansion required')
    language_key=MENU_DESCRIPTION_KEYS[slot]
    if any(v.split(',')[2].strip().casefold()==language_key.casefold() and int(v.split(',')[0])!=slot
           for k,v in menu_cars.items()if k.isdigit()):
        raise ValueError('Menu description already used by another car; preserved: '+language_key)
    sections={s for _,s,_,_,_ in ini_lines(language)if s.startswith('text_')}
    if not sections:raise ValueError('No menu language table for converted car names')
    files[Path('Menu/Language.ini')]=edit_ini(language,{(s,language_key):label for s in sections})
    # Downloaded membership is an exclusive original menu enum. Preserve the
    # true country/type separately rather than relabelling all vehicles "Extra".
    files[Path('Menu/GameMenu.ini')]=edit_ini(menu,{('CARS',str(menu_id)):f'{slot},CT_DOWNLOADED,{language_key},20,10,30,40,60,10,40,50,70,30,80,60,80,40,90,100'})
    return files,menu_id

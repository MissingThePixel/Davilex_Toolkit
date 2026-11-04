"""Old-family vehicle assemblies adapted explicitly to Europe's different controller."""
import hashlib,io,math,struct,json
from pathlib import Path
from .addons import table,archive_bytes,source_folder,DONORS
from .installed import baseline,digest,edit_ini
from .rcs import Archive
from .mesh import decode
from .paths import ROOT,resources

def modern_mesh(raw):
    mesh=decode(raw)
    if struct.unpack_from('<i',raw)[0]==-1:return raw
    return struct.pack('<iII',-1,len(mesh.vertices),len(mesh.triangles))+b''.join(
        struct.pack('<12fB',*v.position,*v.normal,*v.uv,1,1,1,1,v.flags)for v in mesh.vertices)+raw[8+33*len(mesh.vertices):]

def handling(raw,seed,wheel_radius):
    if len(raw)not in (172,240)or len(seed)!=1032:raise ValueError('Unrecognised old-family dynamics layout')
    v=struct.unpack('<'+str(len(raw)//4)+'f',raw);columns=2 if len(raw)==172 else 3
    if not all(math.isfinite(x)for x in v)or not 100<=v[0]<=10000 or not .05<=v[3]<=3:
        raise ValueError('Invalid authored old-family mass/wheel radius')
    result=bytearray(seed);struct.pack_into('<f',result,0,v[0]);struct.pack_into('<f',result,852,wheel_radius)
    seed_mass=struct.unpack_from('<f',seed)[0];reports=[]
    for level in range(5):
        c=min(level,columns-1);a,b,d=(v[9+c],v[9+columns+c],v[9+2*columns+c])
        rpm=v[9+9*columns+c]
        if not 800<rpm<=20000:raise ValueError('Invalid original maximum RPM')
        power=max(((a*r*r+b*r+d)*r*(2*math.pi/60)/745.7*(wheel_radius*.1))for r in [800+(rpm-800)*i/512 for i in range(513)])
        if not 1<=power<=3000:raise ValueError('Unusable original torque polynomial')
        ratios=[x for x in v[9+3*columns+c*6:9+3*columns+(c+1)*6]if x>0]
        if not 1<=len(ratios)<=6:raise ValueError('Unusable original gear ratios')
        gears=5 if c==0 and len(ratios)==6 else len(ratios);ratios=ratios[:gears];ratios+= [ratios[-1]]*(6-gears)
        # Old engine_force already produces wheel force (ratio * 3.07),
        # without dividing by wheel radius. The power calculation above includes
        # Europe's radius-in-metres to retain that force scale.
        # Old automatic transmission uses fixed RPM ratios independently of
        # the authored force ratios. This equivalent speed/power conversion
        # retains those inputs, but is not a transplant of the planar solver.
        automatic=(8.7,4.9,3.7,2.5,2,1.6)[gears-1]
        speed=rpm*(2*math.pi*v[3])/(60*3.07*automatic*.666)*3.6
        for off,value in [(332,power),(352,rpm),(372,800),(392,speed),(432,3.07)]:struct.pack_into('<f',result,off+4*level,value)
        # The planar engine's force multipliers are not suitable direct inputs
        # to Europe's physical wheel motors. The transplanted Mini table
        # repeatedly launches the chassis into pitch rotation. Isolated A/B
        # runs retain its mass/power/suspension and change only the gearbox:
        # Europe's authored category gearbox remains stable. Preserve its
        # complete count and six-slot table, including inactive zero slots.
        native_gears=struct.unpack_from('<i',seed,312+4*level)[0]
        native_ratios=struct.unpack_from('<6f',seed,452+24*level)
        if not 1<=native_gears<=6 or any(not math.isfinite(r)or r<=0 for r in native_ratios[:native_gears]):
            raise ValueError('Unusable Europe compatibility gearbox')
        for off in (732,772,792,832):struct.pack_into('<f',result,off+4*level,struct.unpack_from('<f',seed,off+4*level)[0]*v[0]/seed_mass)
        for off in (752,812):struct.pack_into('<f',result,off+4*level,struct.unpack_from('<f',seed,off+4*level)[0]*math.sqrt(v[0]/seed_mass))
        reports.append({'source_column':c,'peak_power_hp':power,'rpm_limit':rpm,'equivalent_speed_kmh':speed,
            'gears':native_gears,'source_force_gears':gears,'source_force_ratios':ratios[:gears],
            'gearbox':'authored Europe category profile'})
    return bytes(result),{'mass':v[0],'source_record_bytes':len(raw),'levels':reports,
        'preserved':'authored mass, torque-polynomial peak power and RPM limits; measured wheel radius; source force ratios recorded as research metadata',
        'adapter':'Europe category gearbox/tyre/steering/brakes/centre of mass; mass-scaled suspension; equivalent source speed parameter; old planar solver not imported'}

def payload(directory,key,slot=None):
    from .car_addons import CATALOG,CATEGORIES,menu_registration
    item=CATALOG[key];spec=DONORS[item['donor']];source=source_folder(item['donor'])/spec['sub'];league=item.get('league',0)
    configuration=resources(ROOT)/'analysis/baseline'/spec['title']/spec['sub']
    known={str(Path(f['path'])).casefold():f['sha256']for f in baseline(spec['profile'])['files']}
    compiled=item['donor']=='a2ii'
    required=['rcs.img','rcs.ind']if compiled else ['rcs.img','rcs.ind','car_cfg.ini',f'L{league}_anim.ini',f'phys{league}.dat']
    for name in required:
        p=(configuration if name.casefold().endswith('.ini')else source)/name
        if not p.is_file()or digest(p.read_bytes())!=known.get(str(Path(spec['sub'])/name).casefold()):raise ValueError('Unknown donor car file; preserved: '+str(p))
    if compiled:
        catalog_bytes=(resources(ROOT)/'davilex/a2ii_car_catalog.json').read_bytes()
        if digest(catalog_bytes)!='fa48bf42c4d708503071c6411612c9e2839c92e04e19b8d724f674b103b3b0ff':raise ValueError('Unknown compiled A2 II car-table ingredient')
        compiled_catalog=json.loads(catalog_bytes);animations=compiled_catalog['animations'];config=compiled_catalog['cars']
        cfg=edit_ini(b'',{(s,k):v for s,values in config.items()for k,v in values.items()})
        row=[x.strip()for x in config['league0'][str(item['row'])].split(',')]
        row[3]='hoog4';row[4]=format(compiled_catalog['records'][item['row']]['slots'][0],'.9g')
        frames=dict(animations[row[1]]);frames.update({'2':'__eu_dummy__.d3d,__eu_effect__.tga',
            '3':'__eu_front__.d3d,__eu_effect__.tga','4':'__eu_rear__.d3d,__eu_effect__.tga','count':'5'})
    else:
        cfg=(configuration/'car_cfg.ini').read_bytes();row=[x.strip()for x in table(cfg,f'league{league}')[str(item['row'])].split(',')]
        frames=table((configuration/f'L{league}_anim.ini').read_bytes(),row[1])
    archive=Archive(source/'rcs.img');by={}
    for e in archive.entries:by.setdefault(e.name.casefold(),[]).append(e)
    directory=Path(directory);cars=(directory/'Game/Ini/Cars.ini').read_bytes();count=int(table(cars,'cars')['count']);slot=count if slot is None else slot
    if not 78<=slot<128:raise ValueError('No verified unused slot below the expanded 128-car capacity')
    assets={};renames={};duplicates=[]
    def fetch(name,convert=True):
        name=Path(name.replace('\\','/')).name.casefold()
        if name.startswith('__eu_'):
            # A2 II has baked window colours, with no separate reflection frame.
            # Use Europe's original dummy/effect resources for the required slot.
            eu=Archive(directory/'Game/rcs.img');actual={'__eu_dummy__.d3d':'dummy.d3d','__eu_front__.d3d':'fr_light.d3d','__eu_rear__.d3d':'s_licht2.d3d'}.get(name,'s_sfx.tga')
            entry=next(e for e in eu.entries if e.name.casefold()==actual);raw=eu.read(entry)
            if name.endswith('.d3d'):raw=modern_mesh(raw)
            new=f'v{slot:02x}'+hashlib.sha256(name.encode()).hexdigest()[:5]+Path(actual).suffix
            assets[new]=raw;return new
        actual=str(Path(name).with_suffix('.tga'))if name.endswith('.pcx')and str(Path(name).with_suffix('.tga'))in by else name
        matches=by.get(actual,[])
        if not matches:raise ValueError('Missing original car resource: '+name)
        if len(matches)>1:duplicates.append(actual)
        raw=archive.read(matches[0]) # Observed older loader takes the first duplicate.
        if not convert:return raw
        if name in renames:return renames[name]
        ext=Path(actual).suffix
        if ext=='.d3d':raw=modern_mesh(raw)
        elif ext=='.pcx':
            from .media import load_image
            image=load_image(archive,matches[0]);stream=io.BytesIO();image.convert('RGB').save(stream,format='TGA');raw=stream.getvalue();ext='.tga'
        new=f'v{slot:02x}'+hashlib.sha256(actual.encode()).hexdigest()[:5]+ext
        if new in assets and assets[new]!=raw:raise ValueError('Vehicle resource namespace collision')
        assets[new]=raw;renames[name]=new;return new
    anim=f'd{slot}_anim';name=f'd{slot}_vehicle';changes={(name,'count'):0}
    for k,v in frames.items():
        if k.isdigit():changes[anim,k]=','.join(fetch(s.strip())for s in v.split(','))
        else:changes[anim,k]=v
    wheel_mesh=decode(fetch(frames['1'].split(',')[0],False));radius=(max(v.position[1]for v in wheel_mesh.vertices)-min(v.position[1]for v in wheel_mesh.vertices))*.5
    if compiled:
        body=decode(fetch(frames['0'].split(',')[0],False));bounds=[(min(v.position[a]for v in body.vertices),max(v.position[a]for v in body.vertices))for a in range(3)]
        half_width=max(abs(x)for x in bounds[0])*.7;height=bounds[1][0]+(bounds[1][1]-bounds[1][0])*.4
        changes['light_positions',str(slot)]=','.join(format(v,'.9g')for v in (half_width,height,bounds[2][1],half_width,height,bounds[2][0]))
    for section in ('wheel_positions','light_positions'):
        value=table(cfg,section).get(row[5])
        if value is not None:
            positions=[float(s)for s in value.split(';')[0].split(',')];positions[0]=abs(positions[0]);positions[3]=abs(positions[3]);changes[section,str(slot)]=','.join(format(v,'.9g')for v in positions)
    damage_name=f'd{slot}_damage'
    changes['cars',str(slot)]=','.join((name,anim,'RACER',row[3],row[4],str(slot),row[6],str(slot),damage_name,'1.0','0',str(CATEGORIES[item['category']][1])))
    changes['cars','count']=max(count,slot+1)
    seed_id=0 if item['category']=='classic'else CATEGORIES[item['category']][2];seedpath=resources(ROOT)/f'analysis/baseline/Europe Racer/Game/Vdyns/VDYNS{seed_id}.DAT'
    if not seedpath.exists():seedpath=directory/f'Game/Vdyns/VDYNS{seed_id}.DAT'
    expected=next(f['sha256']for f in baseline('europe-resolution')['files']if str(Path(f['path'])).casefold()==str(Path(f'Game/Vdyns/VDYNS{seed_id}.DAT')).casefold())
    seed=seedpath.read_bytes()
    if digest(seed)!=expected:raise ValueError('Unknown Europe compatibility profile')
    if compiled:
        from .a2ii_car_tables import maximum_speed
        v=compiled_catalog['records'][item['row']]['slots'];p=[0.0]*43;p[0]=v[0];p[3]=v[20]
        for c in range(2):
            p[9+c]=-v[22]/v[23]**2/(radius*.1);p[11+c]=2*v[22]/v[23]/(radius*.1)
            p[27+c]=min(v[21],1.95*v[23])
            ratios=[r for r in v[26:32]if r>0];p[15+c*6:21+c*6]=ratios+[0]*(6-len(ratios))
        converted,report=handling(struct.pack('<43f',*p),seed,radius);converted=bytearray(converted)
        for level in range(5):
            struct.pack_into('<f',converted,432+level*4,v[32]);struct.pack_into('<f',converted,392+level*4,maximum_speed(v)*3.6)
        converted=bytes(converted);report['source_record_bytes']=238;report['source']='SHA-verified A2 II compiled mass/torque/gears; alternate planar maximum-speed parameter'
        report['adapter']+='; stock compiled profile reused for upgrades; baked window colours retained'
    else:
        physical=(source/f'phys{league}.dat').read_bytes();stride=len(physical)//20
        if len(physical)not in (3440,4800):raise ValueError('Unknown original handling-table size')
        raw=physical[item['row']*stride:(item['row']+1)*stride];converted,report=handling(raw,seed,radius)
    stem=f'dvcar{slot}';racer=(directory/'Game/Ini/Racer.ini').read_bytes();images=table(racer,'img');img,ind=archive_bytes(assets)
    files={Path('Game/Ini/Cars.ini'):edit_ini(cars,changes),Path('Game/Ini/Racer.ini'):edit_ini(racer,{}if stem in images.values()else{('img',images['count']):stem,('img','count'):int(images['count'])+1}),
        Path(f'Game/{stem}.img'):img,Path(f'Game/{stem}.ind'):ind,Path(f'Game/Vdyns/VDYNS{slot}.DAT'):converted}
    damage=(directory/'Game/Ini/damage.ini').read_bytes();models=table(damage,'damage models')
    if slot>int(models['count']):raise ValueError('Damage model/car tables are not contiguous')
    original=next(v for k,v in models.items()if k.isdigit()and v.split(',')[0].casefold()=='dam_dummy')
    files[Path('Game/Ini/damage.ini')]=edit_ini(damage,{('damage models',str(slot)):damage_name+','+original.split(',',1)[1],
        ('damage models','count'):max(int(models['count']),slot+1)})
    menu,menu_id=menu_registration(directory,slot,item);files.update(menu)
    return files,{**item,'engine_id':slot,'menu_id':menu_id,'internal_name':name,'handling':report,'resources':len(assets),'damage_parts':0,
        'material_donor':spec['title'],'duplicate_first_entries':sorted(set(duplicates)),
        'status':'experimental old-family conversion; source solver/damage behaviour not imported; driving not verified'}

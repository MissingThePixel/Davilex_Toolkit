"""Verified visual-mesh repairs; retain authored glass and physical vertices."""
import hashlib,struct
from pathlib import Path
from .rcs import Archive

SAAB_SHA='ef2fa46316046b7b53791671b688eb628d8aea0cbf7b5f986e9be69a40257c29'
REAR_WINDOW_FACES=frozenset((31,32,43,44,57,58,69,70))
FRONT_WINDOW_FACES=frozenset(range(169,181))
SIDE_WINDOW_FACES=frozenset((82,83,84,92,93,94))
WINDOW_FACES=REAR_WINDOW_FACES|FRONT_WINDOW_FACES|SIDE_WINDOW_FACES
SAAB_PANELS={
    'sab_a00.d3d':('dvsaba0.d3d','10977fedb27d797929ce6603365ea739eea345c77bdf3c5d565e9689b381d8ac',frozenset((42,43,54,55,58,59,62,63))),
    'sab_a01.d3d':('dvsaba1.d3d','155dfceb0d79a27e65c0fe859e869c8ac8b5349afcc63803f9c0d91345dfa281',frozenset((8,9,10,13,14,15))),
    'sab_a02.d3d':('dvsaba2.d3d','48622265a608328e8881e323ea4685ccd8f6d34fc74d98a0e409ad96f84b5cd3',frozenset((8,9,10,13,14,15))),
}


def saab_body(raw):
    return remove_faces(raw,SAAB_SHA,WINDOW_FACES)


def remove_faces(raw,expected,removed):
    if hashlib.sha256(raw).hexdigest()!=expected:
        raise ValueError('Unknown Saab body mesh; preserving original model.')
    marker,vertices,faces=struct.unpack_from('<iII',raw)
    start=12+49*vertices
    # These opaque body triangles sample pink front/rear-window placeholders
    # and sit in front of the original SAB_RAM glass. Keep all vertex records,
    # normals, UVs, other faces and the separate reflective glass unchanged.
    return (struct.pack('<iII',marker,vertices,faces-len(removed))+
            raw[12:start]+b''.join(raw[start+i*9:start+(i+1)*9]
                                  for i in range(faces) if i not in removed))


def europe_payload(directory):
    from .addons import archive_bytes,table
    from .installed import edit_ini
    directory=Path(directory);game=directory/'Game'
    cars=(game/'Ini/Cars.ini').read_bytes();section=table(cars,'Holland_Classic_Anim')
    changes={}
    for key in ('0','5'):
        row=section[key].split(',')
        if row[0].strip().casefold() not in ('saab.d3d','dvsaab.d3d'):
            raise ValueError('Custom Saab model binding; original preserved.')
        row[0]='dvsaab.d3d';changes['Holland_Classic_Anim',key]=','.join(row)
    a=Archive(game/'rcs.img');matches=[e for e in a.entries if e.name.casefold()=='saab.d3d']
    if len(matches)!=1:raise ValueError('Missing or ambiguous original Saab mesh.')
    meshes={'dvsaab.d3d':saab_body(a.read(matches[0]))}
    panels=table(cars,'Holland_Classic')
    for key,old in (('2','sab_a00.d3d'),('3','sab_a01.d3d'),('4','sab_a02.d3d')):
        name,expected,removed=SAAB_PANELS[old];row=panels[key].split(',')
        if row[1].strip().casefold() not in (old,name):raise ValueError('Custom Saab panel binding; original preserved.')
        entry=next(e for e in a.entries if e.name.casefold()==old)
        meshes[name]=remove_faces(a.read(entry),expected,removed)
        row[1]=name;changes['Holland_Classic',key]=','.join(row)
    img,ind=archive_bytes(meshes)
    racer=(game/'Ini/Racer.ini').read_bytes();images=table(racer,'img');registration={}
    if 'dvfix' not in (v.casefold() for k,v in images.items() if k.isdigit()):
        count=int(images['count']);registration={('IMG',str(count)):'dvfix',('IMG','count'):count+1}
    return {Path('Game/dvfix.img'):img,Path('Game/dvfix.ind'):ind,
            Path('Game/Ini/Cars.ini'):edit_ini(cars,changes),
            Path('Game/Ini/Racer.ini'):edit_ini(racer,registration)}

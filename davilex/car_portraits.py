"""Menu portraits rendered from Europe's actual Classic vehicle meshes."""
from dataclasses import replace
import io,math
from pathlib import Path
from .rcs import Archive
from .mesh import decode,Mesh
from .media import load_image
from .textures import prepare
from .mesh_preview import render


def portrait(directory,car):
    from PIL import Image,ImageOps
    from .addons import table
    from .geometry_fixes import SAAB_PANELS
    game=Path(directory)/'Game';archive=Archive(game/'rcs.img')
    archives=[archive]
    for k,stem in table((game/'Ini/Racer.ini').read_bytes(),'img').items():
        if k.isdigit()and stem.casefold()!='rcs' and (game/(stem+'.img')).exists():archives.append(Archive(game/(stem+'.img')))
    by={}
    for a in archives:
        for e in a.entries:by.setdefault(e.name.casefold(),(a,e))
    cars=(game/'Ini/Cars.ini').read_bytes();row=table(cars,'cars')[str(car)].split(',')
    parts=table(cars,row[1]);positions=list(map(float,table(cars,'wheel_positions')[str(car)].split(',')))
    pieces=[]
    bindings=[(kind,*map(str.strip,parts[str(kind)].split(',')[:2]),(0,0,0)) for kind in (0,2,1)]
    damage=(game/'Ini/damage.ini').read_bytes()
    damage_ref=row[8].strip().casefold()
    model=next((v.split(',')[5].strip().casefold()for v in table(damage,'damage models').values()
                if len(v.split(','))>5 and v.split(',')[0].strip().casefold()==damage_ref),damage_ref)
    phase=next((v.split(',')[3].strip().casefold() for v in table(damage,'damageable cars').values()
               if len(v.split(','))>3 and v.split(',')[0].strip().casefold()==model),None)
    animations={v.split(',')[0].strip().casefold():v.split(',')[1:3]
                for k,v in table(cars,row[0]).items() if k.isdigit()}
    for value in table(damage,'damageable car objects').values():
        fields=[v.strip() for v in value.split(',')]
        if len(fields)>4 and fields[0].casefold()==phase and fields[1].casefold() in animations:
            model,texture=animations[fields[1].casefold()]
            bindings.append((3,model,texture,tuple(map(float,fields[2:5]))))
    for kind,model,texture,offset in bindings:
        aliases={v[0]:k for k,v in SAAB_PANELS.items()}
        model=aliases.get(model.casefold(),model)
        if model.casefold()=='dvsaab.d3d':model='saab.d3d'
        a,entry=by[model.casefold()];raw=a.read(entry)
        mesh=decode(raw)
        if kind==2:
            # The game supplies a dynamic sky reflection, not a texture-sheet UV.
            # Use a neutral blue reflection swatch for this static model portrait.
            image=Image.new('RGB',(256,256),(68,91,118))
        else:
            matches=[(a,e)for a,e in by.values() if Path(e.name).stem.casefold()==Path(texture).stem.casefold()
                     and e.extension.casefold() in ('.tga','.pcx')]
            a,entry=next(((a,e)for a,e in matches if e.extension.casefold()=='.tga'),None) or matches[0]
            image,_=prepare(load_image(a,entry),'Main square',False)
            # Opaque placeholder pixels are reflective glass/cutouts in-game.
            # Keep the authored window borders in this static illustration.
            import numpy as np
            pixels=np.array(image.convert('RGB'))
            pink=(pixels[:,:,0]>220)&(pixels[:,:,1]<40)&(pixels[:,:,2]>70)
            pixels[pink]=(35,35,35) if kind==1 else (68,91,118)
            image=Image.fromarray(pixels)
        if kind==1:
            for x,y,z in (positions[:3],positions[3:]):
                for sign in (-1,1):
                    vertices=tuple(replace(v,position=(v.position[0]*sign+x*sign,v.position[1]+y,v.position[2]+z)) for v in mesh.vertices)
                    # Reflection reverses winding; retain the wheel's outward
                    # faces when the combined portrait is back-face culled.
                    triangles=tuple((a,c,b) for a,b,c in mesh.triangles) if sign<0 else mesh.triangles
                    pieces.append((replace(mesh,vertices=vertices,triangles=triangles),image))
        else:
            vertices=tuple(replace(v,position=tuple(v.position[k]+offset[k] for k in range(3))) for v in mesh.vertices)
            pieces.append((replace(mesh,vertices=vertices),image))
    atlas=Image.new('RGB',(256,256*len(pieces)));vertices=[];faces=[];metadata=[]
    for n,(mesh,image) in enumerate(pieces):
        atlas.paste(image.convert('RGB').resize((256,256)),(0,n*256));base=len(vertices)
        vertices.extend(replace(v,uv=(max(.00001,min(.99999,v.uv[0])),
                                      (n+max(.00001,min(.99999,v.uv[1])))/len(pieces))) for v in mesh.vertices)
        faces.extend(tuple(i+base for i in f) for f in mesh.triangles);metadata.extend(mesh.face_metadata)
    # Original models have separate inward cabin surfaces; cull their backs.
    visible=[];visible_metadata=[]
    for face,meta in zip(faces,metadata):
        a,b,c=[vertices[i].position for i in face]
        u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
        nx,ny,nz=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
        facing=math.sin(.30)*ny+math.cos(.30)*(-math.sin(.65)*nx+math.cos(.65)*nz)
        if facing>0:visible.append(face);visible_metadata.append(meta)
    image=render(Mesh(tuple(vertices),tuple(visible),tuple(visible_metadata)),size=(480,400),yaw=.65,pitch=.30,zoom=1.18,texture=atlas)
    image=ImageOps.pad(image,(154,138),color=(23,29,39));frame=Image.new('RGB',(160,160),(189,185,175));frame.paste(image,(3,5))
    output=io.BytesIO();frame.save(output,format='TGA');return output.getvalue()

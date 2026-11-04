"""Repair grossly buried legacy waypoints when importing Europe's road data.

Europe 0x4f93b0/0x4573f0 uses the DMP position for grid/reset placement.
Some ARII points lie below their road deck. Keep authored small offsets and
points above the road; only raise a point more than one metre below a local
road triangle. No topology, trigger, lane, X/Z or rendered geometry changes.
"""
import math
import struct


def trim_origin_tail(road,centres,objects,collision):
    """Drop an unused terminal export cell whose geometry runs to (0,0,0).

    Europe's brush builder makes every cell's CMP walls physically active.
    ARII Hamburg-Berlin ends with an unconnected placeholder cell whose road
    quads and four walls stretch back to the origin, crossing the valid route.
    Retain all IDs in CMP/DMP/OMP: only the final unreferenced cell is removed.
    Refuse this repair if it carries gameplay data or any valid local geometry.
    """
    count_offset=8 if struct.unpack_from('<i',road)[0]==-1 else 4
    modern=count_offset==8;pos=count_offset+4;stride=120 if modern else 104
    count=struct.unpack_from('<I',road,count_offset)[0];last_start=None;quads=[]
    if count<3:return road,centres,[]
    for cell in range(count):
        if cell==count-1:last_start=pos
        for kind in range(4):
            n=struct.unpack_from('<I',road,pos)[0];pos+=4
            if pos+n*stride>len(road):raise ValueError('Truncated terminal road cell')
            if cell==count-1:
                quads.extend([[struct.unpack_from('<3f',road,pos+i*stride+v*(24 if modern else 20))
                    for v in range(4)]for i in range(n)])
            pos+=n*stride
    if pos!=len(road):raise ValueError('Unexpected terminal road tail')
    if struct.unpack_from('<I',centres)[0]!=count:raise ValueError('Terminal cell counts differ')
    pos=4;lists=[]
    for cell in range(count):
        if cell==count-1:
            centre_start=pos;centre=struct.unpack_from('<3f',centres,pos)
            triggers=struct.unpack_from('<2i',centres,pos+12)
        pos+=20;lists=[]
        for kind in range(3):
            n=struct.unpack_from('<I',centres,pos)[0];pos+=4
            lists.append(struct.unpack_from(f'<{n}I',centres,pos));pos+=n*4
    if pos!=len(centres):raise ValueError('Unexpected terminal centre tail')
    if (not quads or any(triggers)or lists[1]or lists[2]or not lists[0]
            or math.hypot(centre[0],centre[2])<5000):return road,centres,[]
    for vertices in quads:
        # The matching rail quads have origin X/Z with a ten-unit top edge.
        zero=[v[0]==0. and v[2]==0. and abs(v[1]-centre[1])<=100 for v in vertices]
        if sum(zero)<2 or not any(not z for z in zero):return road,centres,[]
        if any(math.dist(v,centre)>2000 for v,z in zip(vertices,zero)if not z):return road,centres,[]
    n=struct.unpack_from('<I',objects)[0]
    if len(objects)!=4+n*68:raise ValueError('Invalid terminal object records')
    if any(struct.unpack_from('<i',objects,4+i*68)[0]==count-1 for i in range(n)):
        return road,centres,[]
    segments=struct.unpack_from('<I',collision)[0]
    if len(collision)!=4+segments*24:raise ValueError('Invalid terminal collision records')
    for index in lists[0]:
        if index>=segments:raise ValueError('Invalid terminal collision reference')
        x,y,z,dx,dy,dz=struct.unpack_from('<6f',collision,4+index*24)
        start=(x,y,z);end=(x+dx,y+dy,z+dz)
        if math.hypot(dx,dz)<5000 or (start!=(0.,0.,0.)and end!=(0.,0.,0.)):
            return road,centres,[]
    rmp=bytearray(road[:last_start]);struct.pack_into('<I',rmp,count_offset,count-1)
    pmp=bytearray(centres[:centre_start]);struct.pack_into('<I',pmp,0,count-1)
    return bytes(rmp),bytes(pmp),[{'cell':count-1,'quads':len(quads),'unreferenced_cmp_ids':list(lists[0])}]


def raise_buried_waypoints(road, centres, waypoints):
    version=struct.unpack_from('<i',road)[0]
    modern=version==-1;pos=12 if modern else 8;stride=120 if modern else 104
    cells=struct.unpack_from('<I',road,8 if modern else 4)[0];geometry={}
    for cell in range(cells):
        for kind in range(4):
            count=struct.unpack_from('<I',road,pos)[0];pos+=4
            if pos+count*stride>len(road):raise ValueError('Truncated navigation road')
            if kind==0:
                triangles=[]
                for quad in range(count):
                    at=pos+quad*stride
                    vertices=[struct.unpack_from('<3f',road,at+v*(24 if modern else 20))for v in range(4)]
                    indices=struct.unpack_from('<6I',road,at+stride-24)
                    if any(i>3 for i in indices):raise ValueError('Invalid navigation road index')
                    triangles.extend([[vertices[i]for i in indices[start:start+3]]for start in (0,3)])
                geometry[cell]=triangles
            pos+=count*stride
    if pos!=len(road):raise ValueError('Unexpected navigation road tail')
    if struct.unpack_from('<I',centres)[0]!=cells:raise ValueError('Navigation cell counts differ')
    nodes=struct.unpack_from('<I',waypoints)[0]
    if len(waypoints)!=4+nodes*36:raise ValueError('Invalid navigation waypoint length')
    owners={};pos=4
    for cell in range(cells):
        pos+=20
        for kind in range(3):
            count=struct.unpack_from('<I',centres,pos)[0];pos+=4
            if pos+count*4>len(centres):raise ValueError('Truncated navigation centres')
            if kind:
                for node in struct.unpack_from(f'<{count}I',centres,pos):
                    if node>=nodes:raise ValueError('Invalid navigation waypoint reference')
                    owners.setdefault(node,set()).add(cell)
            pos+=count*4
    if pos!=len(centres):raise ValueError('Unexpected navigation centres tail')
    result=bytearray(waypoints);changes=[]
    for node,owned in sorted(owners.items()):
        at=4+node*36;x,y,z=struct.unpack_from('<3f',waypoints,at+8)
        if not all(math.isfinite(v)for v in (x,y,z)):raise ValueError('Nonfinite navigation waypoint')
        hits=[]
        nearby={i for cell in owned for i in range(max(0,cell-2),min(cells,cell+3))}
        for cell in sorted(nearby):
            for a,b,c in geometry.get(cell,[]):
                det=(b[2]-c[2])*(a[0]-c[0])+(c[0]-b[0])*(a[2]-c[2])
                if abs(det)<1e-8:continue
                u=((b[2]-c[2])*(x-c[0])+(c[0]-b[0])*(z-c[2]))/det
                v=((c[2]-a[2])*(x-c[0])+(a[0]-c[0])*(z-c[2]))/det
                if min(u,v,1-u-v)>=-1e-5:
                    height=u*a[1]+v*b[1]+(1-u-v)*c[1]
                    if math.isfinite(height):hits.append(height)
        if not hits:continue
        # Nearest deck preserves an existing lower route at an overpass.
        height=min(hits,key=lambda h:abs(h-y))
        if height-y<=10:continue
        struct.pack_into('<f',result,at+12,height)
        changes.append({'node':node,'old_y':y,'new_y':height})
    return bytes(result),changes

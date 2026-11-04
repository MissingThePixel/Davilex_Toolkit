"""Cut legacy scenery barriers out of a different, drivable road section.

Oxford contains scenery-only cells over an earlier stretch of its course.
Their CMP walls and vertical RMP faces become permanent colliders in Europe.
Trim walls, curbs and low paving where they overlap a distant drivable road.
Retain their outside pieces, all road cells, triggers and object placements.
"""
import math
import struct


def _interval(a,b,polygon):
    """Segment interval inside a convex X/Z polygon, independent of winding."""
    area=sum(p[0]*q[2]-q[0]*p[2] for p,q in zip(polygon,polygon[1:]+polygon[:1]))
    if abs(area)<1e-5:return None
    sign=1 if area>0 else -1;low=0.;high=1.
    for p,q in zip(polygon,polygon[1:]+polygon[:1]):
        dx=q[0]-p[0];dz=q[2]-p[2]
        value=sign*(dx*(a[2]-p[2])-dz*(a[0]-p[0]))
        delta=sign*(dx*(b[2]-a[2])-dz*(b[0]-a[0]))
        if abs(delta)<1e-9:
            if value<0:return None
        elif delta>0:low=max(low,-value/delta)
        else:high=min(high,-value/delta)
        if high-low<1e-7:return None
    return (low,high) if high>low else None


def _remaining(intervals):
    merged=[]
    for a,b in sorted(intervals):
        if merged and a<=merged[-1][1]+1e-6:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:merged.append((a,b))
    result=[];at=0.
    for a,b in merged:
        if a-at>1e-6:result.append((at,a))
        at=max(at,b)
    if 1-at>1e-6:result.append((at,1.))
    return result


def _split_polygon(vertices,p,q,sign):
    """Split a 3-D textured polygon by an X/Z half-plane."""
    inside=[];outside=[]
    def distance(v):return sign*((q[0]-p[0])*(v[2]-p[2])-(q[2]-p[2])*(v[0]-p[0]))
    for a,b in zip(vertices,vertices[1:]+vertices[:1]):
        da=distance(a);db=distance(b)
        (inside if da>=0 else outside).append(a)
        if (da<0)!=(db<0):
            t=da/(da-db);v=tuple(x+(y-x)*t for x,y in zip(a,b))
            inside.append(v);outside.append(v)
    def clean(points):
        result=[]
        for point in points:
            if not result or math.hypot(point[0]-result[-1][0],point[2]-result[-1][2])>1e-6:result.append(point)
        if len(result)>1 and math.hypot(result[0][0]-result[-1][0],result[0][2]-result[-1][2])<1e-6:result.pop()
        while len(result)>3:
            remove=next((i for i,b in enumerate(result)
                if abs((b[0]-result[i-1][0])*(result[(i+1)%len(result)][2]-b[2])-(b[2]-result[i-1][2])*(result[(i+1)%len(result)][0]-b[0]))<1e-7),None)
            if remove is None:break
            result.pop(remove)
        return result
    return clean(inside),clean(outside)


def _area(vertices):
    return abs(sum(p[0]*q[2]-q[0]*p[2]for p,q in zip(vertices,vertices[1:]+vertices[:1])))/2


def _expanded(polygon,margin):
    if not margin:return polygon
    area=sum(p[0]*q[2]-q[0]*p[2]for p,q in zip(polygon,polygon[1:]+polygon[:1]))
    if abs(area)<1e-5:return polygon
    sign=1 if area>0 else -1;lines=[]
    for p,q in zip(polygon,polygon[1:]+polygon[:1]):
        dx=q[0]-p[0];dz=q[2]-p[2];length=math.hypot(dx,dz)
        if length<1e-6:return polygon
        lines.append((p[0]+sign*dz/length*margin,p[2]-sign*dx/length*margin,dx,dz))
    result=[]
    for i,p in enumerate(polygon):
        ax,az,dx,dz=lines[i-1];bx,bz,ex,ez=lines[i];den=dx*ez-dz*ex
        if abs(den)<1e-6:return polygon
        t=((bx-ax)*ez-(bz-az)*ex)/den
        result.append((ax+t*dx,p[1],az+t*dz,*p[3:]))
    return result


def _subtract(vertices,mask):
    area=sum(p[0]*q[2]-q[0]*p[2]for p,q in zip(mask,mask[1:]+mask[:1]))
    if abs(area)<1e-5:return [vertices]
    sign=1 if area>0 else -1;pending=vertices;result=[]
    for p,q in zip(mask,mask[1:]+mask[:1]):
        if len(pending)<3:break
        pending,outside=_split_polygon(pending,p,q,sign)
        if len(outside)>=3 and _area(outside)>.05:result.append(outside)
    return result


def repair(road,centres,collision,clearance=0):
    modern=struct.unpack_from('<i',road)[0]==-1
    header=12 if modern else 8;stride=120 if modern else 104;vertex_stride=24 if modern else 20
    n=struct.unpack_from('<I',road,header-4)[0];at=header;cells=[];roads=[]
    for cell in range(n):
        groups=[]
        for kind in range(4):
            count=struct.unpack_from('<I',road,at)[0];at+=4;quads=[]
            for _ in range(count):
                raw=road[at:at+stride]
                if len(raw)!=stride:raise ValueError('Truncated crossroads quad')
                vertices=[struct.unpack_from('<5f',raw,v*vertex_stride)+(tuple(raw[v*vertex_stride+20:v*vertex_stride+24])if modern else ())for v in range(4)]
                if not all(math.isfinite(x)for v in vertices for x in v):raise ValueError('Nonfinite crossroads quad')
                quads.append((raw,vertices));at+=stride
                if kind==0:roads.append((cell,vertices))
            groups.append(quads)
        cells.append(groups)
    if at!=len(road):raise ValueError('Unexpected crossroads road tail')
    if struct.unpack_from('<I',centres)[0]!=n:raise ValueError('Crossroads cell counts differ')
    at=4;records=[]
    for cell in range(n):
        prefix=centres[at:at+20];at+=20;lists=[]
        for _ in range(3):
            count=struct.unpack_from('<I',centres,at)[0];at+=4
            lists.append(list(struct.unpack_from(f'<{count}I',centres,at)));at+=count*4
        records.append((prefix,lists))
    if at!=len(centres):raise ValueError('Unexpected crossroads centre tail')
    count=struct.unpack_from('<I',collision)[0]
    if len(collision)!=4+count*24:raise ValueError('Invalid crossroads collision records')
    segments=[collision[4+i*24:4+(i+1)*24]for i in range(count)]
    # Bounding-box grid keeps the intersection audit local, including long walls.
    grid={};size=256
    for owner,vertices in roads:
        vertices=_expanded(vertices,clearance)
        for x in range(math.floor(min(v[0]for v in vertices)/size),math.floor(max(v[0]for v in vertices)/size)+1):
            for z in range(math.floor(min(v[2]for v in vertices)/size),math.floor(max(v[2]for v in vertices)/size)+1):
                grid.setdefault((x,z),[]).append((owner,vertices))
    def cuts(cell,a,b,low,high):
        candidates={}
        for x in range(math.floor(min(a[0],b[0])/size),math.floor(max(a[0],b[0])/size)+1):
            for z in range(math.floor(min(a[2],b[2])/size),math.floor(max(a[2],b[2])/size)+1):
                for owner,v in grid.get((x,z),[]):candidates[id(v)]=(owner,v)
        result=[];owners=set()
        for owner,v in candidates.values():
            distance=abs(cell-owner)
            if min(distance,n-distance)<=8:continue
            # Keep overpasses and walls that stop below the road. A tall wall
            # must cross the deck rather than simply be somewhere above it.
            if max(p[1]for p in v)<low-5 or min(p[1]for p in v)>high+5:continue
            interval=_interval(a,b,v)
            # Float32 intersection endpoints can land a fraction of a millimetre
            # inside the neighbour. Do not create microscopic repeat cuts.
            if interval and (interval[1]-interval[0])*math.hypot(b[0]-a[0],b[2]-a[2])>.05:
                result.append(interval);owners.add(owner)
        return result,sorted(owners)
    changes=[]
    for cell,groups in enumerate(cells):
        if groups[0]:continue  # Never cut the boundaries of a drivable cell.
        prefix,lists=records[cell];new_ids=[]
        for index in lists[0]:
            if index>=count:raise ValueError('Invalid crossroads wall reference')
            x,y,z,dx,dy,dz=struct.unpack('<6f',segments[index]);cy=struct.unpack_from('<f',prefix,4)[0]
            intervals,owners=cuts(cell,(x,cy,z),(x+dx,cy+dy,z+dz),cy-25,cy+100+dy)
            if not intervals:new_ids.append(index);continue
            pieces=_remaining(intervals)
            for start,end in pieces:
                new_ids.append(len(segments))
                segments.append(struct.pack('<6f',x+dx*start,y+dy*start,z+dz*start,dx*(end-start),dy*(end-start),dz*(end-start)))
            changes.append({'cell':cell,'kind':'CMP','wall':index,'road_cells':owners,'retained_intervals':pieces})
        if len(new_ids)>12:raise ValueError('Crossroads repair exceeds CMP cell capacity')
        lists[0]=new_ids
        for kind in range(1,4):
            result=[]
            for qi,(raw,v) in enumerate(groups[kind]):
                # Scenery-only paving can also overlap the road by 0.3m.
                # Two competing ground decks/curbs can block wheels or make a
                # fast player hop over them, even after tall walls are removed.
                if max(p[1]for p in v)-min(p[1]for p in v)<=5 and _area(v)>.05:
                    pieces=[v];owners=[]
                    for owner,mask in roads:
                        distance=abs(cell-owner)
                        if min(distance,n-distance)<=8:continue
                        if min(p[1]for p in v)>max(p[1]for p in mask)+5 or max(p[1]for p in v)<min(p[1]for p in mask)-5:continue
                        if any(max(p[k]for p in v)<min(p[k]for p in mask)or min(p[k]for p in v)>max(p[k]for p in mask)for k in (0,2)):continue
                        before=sum(_area(poly)for poly in pieces)
                        candidate=[part for poly in pieces for part in _subtract(poly,mask)]
                        if before-sum(_area(poly)for poly in candidate)>.05:pieces=candidate;owners.append(owner)
                    if owners:
                        emitted=[]
                        for poly in pieces:
                            # A triangle becomes two valid triangles sharing an
                            # edge midpoint: no zero-area Ipion triangles.
                            polys=[poly]if len(poly)==4 else [[poly[0],poly[i],tuple((a+b)/2 for a,b in zip(poly[i],poly[i+1])),poly[i+1]]for i in range(1,len(poly)-1)]
                            for part in polys:
                                out=bytearray()
                                for point in part:
                                    out+=struct.pack('<5f',*point[:5])
                                    if modern:out+=bytes(max(0,min(255,round(x)))for x in point[5:9])
                                out+=struct.pack('<6I',0,1,2,0,2,3)
                                emitted.append((bytes(out),part))
                        result.extend(emitted)
                        changes.append({'cell':cell,'kind':kind,'quad':qi,'road_cells':sorted(set(owners)),'ground_overlap':True,'pieces':len(emitted)})
                        continue
                # Only vertical strip quads, with two X/Z endpoints. Preserve
                # arbitrary sloping ground, roofs, ramps and non-strip meshes.
                endpoints=[];which=[]
                for p in v:
                    hit=next((i for i,q in enumerate(endpoints)if math.hypot(p[0]-q[0],p[2]-q[2])<.001),None)
                    if hit is None:hit=len(endpoints);endpoints.append(p)
                    which.append(hit)
                if len(endpoints)!=2 or sorted(which.count(i)for i in range(2))!=[2,2]:result.append((raw,v));continue
                pairs=[[j for j in ((i-1)%4,(i+1)%4)if which[j]!=which[i]]for i in range(4)]
                if any(len(p)!=1 for p in pairs):result.append((raw,v));continue
                a,b=endpoints;low=min(p[1]for p in v);high=max(p[1]for p in v)
                if high-low<.1:result.append((raw,v));continue
                intervals,owners=cuts(cell,a,b,low,high)
                if not intervals:result.append((raw,v));continue
                pieces=_remaining(intervals)
                for start,end in pieces:
                    out=bytearray(raw)
                    for vi,p in enumerate(v):
                        other=pairs[vi][0]
                        t=start if which[vi]==0 else 1-end
                        fields=[p[k]+(v[other][k]-p[k])*t for k in range(5)]
                        struct.pack_into('<5f',out,vi*vertex_stride,*fields)
                        if modern:
                            out[vi*vertex_stride+20:vi*vertex_stride+24]=bytes(max(0,min(255,round(p[k]+(v[other][k]-p[k])*t)))for k in range(5,9))
                    result.append((bytes(out),[struct.unpack_from('<5f',out,i*vertex_stride)for i in range(4)]))
                changes.append({'cell':cell,'kind':kind,'quad':qi,'road_cells':owners,'retained_intervals':pieces})
            if len(result)>(24 if kind==1 else 12):raise ValueError(f'Crossroads repair exceeds quad cell capacity: cell {cell}, group {kind}, {len(result)} quads')
            groups[kind]=result
    if not changes:return road,centres,collision,[]
    out=bytearray(road[:header]);total=0
    for groups in cells:
        for quads in groups:
            out+=struct.pack('<I',len(quads))+b''.join(raw for raw,v in quads);total+=len(quads)
    # This header is the loader's quad-pool allocation, not a track/cell ID.
    struct.pack_into('<I',out,4 if modern else 0,total)
    pmp=bytearray(struct.pack('<I',n))
    for prefix,lists in records:
        pmp+=prefix
        for ids in lists:pmp+=struct.pack('<I',len(ids))+struct.pack(f'<{len(ids)}I',*ids)
    cmp=struct.pack('<I',len(segments))+b''.join(segments)
    return bytes(out),bytes(pmp),cmp,changes

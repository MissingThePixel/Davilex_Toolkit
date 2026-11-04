"""Orbitable geometry-only software preview for validated D3D meshes."""
import math


def render(mesh,size=(440,310),yaw=.6,pitch=-.3,zoom=1.0,wireframe=False,texture=None,flip_v=False):
    from PIL import Image,ImageDraw
    image=Image.new('RGB',size,(23,29,39));draw=ImageDraw.Draw(image)
    if not mesh.vertices or not mesh.triangles:return image
    if len(mesh.triangles)>50000:raise ValueError('Interactive preview is limited to 50,000 triangles; OBJ export remains available.')
    used={i for face in mesh.triangles for i in face}
    low=[min(mesh.vertices[i].position[a] for i in used) for a in range(3)]
    high=[max(mesh.vertices[i].position[a] for i in used) for a in range(3)]
    centre=[(a+b)/2 for a,b in zip(low,high)]
    extent=max((b-a for a,b in zip(low,high)),default=1) or 1
    scale=min(size)*.70/extent*zoom
    cy,sy,cp,sp=math.cos(yaw),math.sin(yaw),math.cos(pitch),math.sin(pitch)
    vertices=[]
    for v in mesh.vertices:
        x,y,z=[(v.position[a]-centre[a]) for a in range(3)]
        x,z=cy*x+sy*z,-sy*x+cy*z
        y,z=cp*y-sp*z,sp*y+cp*z
        vertices.append((size[0]/2+x*scale,size[1]/2-y*scale,z*scale))
    if texture is not None and not wireframe:
        return textured(image,vertices,mesh,texture,flip_v)
    faces=sorted(mesh.triangles,key=lambda face:sum(vertices[i][2] for i in face))
    for face in faces:
        a,b,c=[vertices[i] for i in face]
        u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
        normal=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
        length=math.sqrt(sum(n*n for n in normal))
        light=.35+.65*abs(sum(n*l for n,l in zip(normal,(.3,-.4,.866)))/length) if length else .35
        colour=tuple(int(c*min(1,light)) for c in (139,184,220))
        xy=[(p[0],p[1]) for p in (a,b,c)]
        draw.polygon(xy,fill=None if wireframe else colour,outline=(187,211,229) if wireframe else None)
    return image


def textured(image,vertices,mesh,texture,flip_v):
    """Orthographic barycentric UV sampling with a per-pixel depth buffer."""
    import numpy as np
    from PIL import Image
    pixels=np.array(image);height,width=pixels.shape[:2]
    depths=np.full((height,width),-np.inf)
    tex=np.array(texture.convert('RGBA'));th,tw=tex.shape[:2]
    for face in mesh.triangles:
        a,b,c=[vertices[i] for i in face]
        x0=max(0,math.floor(min(a[0],b[0],c[0])));x1=min(width-1,math.ceil(max(a[0],b[0],c[0])))
        y0=max(0,math.floor(min(a[1],b[1],c[1])));y1=min(height-1,math.ceil(max(a[1],b[1],c[1])))
        determinant=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if x0>x1 or y0>y1 or abs(determinant)<1e-8:continue
        xx,yy=np.meshgrid(np.arange(x0,x1+1)+.5,np.arange(y0,y1+1)+.5)
        p=((b[1]-c[1])*(xx-c[0])+(c[0]-b[0])*(yy-c[1]))/determinant
        q=((c[1]-a[1])*(xx-c[0])+(a[0]-c[0])*(yy-c[1]))/determinant
        r=1-p-q
        z=p*a[2]+q*b[2]+r*c[2]
        region=depths[y0:y1+1,x0:x1+1]
        mask=(p>=-1e-7)&(q>=-1e-7)&(r>=-1e-7)&(z>region)
        if not mask.any():continue
        uv=[mesh.vertices[i].uv for i in face]
        u=p*uv[0][0]+q*uv[1][0]+r*uv[2][0]
        v=p*uv[0][1]+q*uv[1][1]+r*uv[2][1]
        if flip_v:v=1-v
        tx=np.floor(np.mod(u,1)*tw).astype(int)%tw
        ty=np.floor(np.mod(v,1)*th).astype(int)%th
        colours=tex[ty,tx]
        mask &= colours[:,:,3]>=128
        pixels[y0:y1+1,x0:x1+1][mask]=colours[:,:,:3][mask]
        region[mask]=z[mask]
    return Image.fromarray(pixels)

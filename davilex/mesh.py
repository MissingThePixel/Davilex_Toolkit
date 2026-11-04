"""Strict readers for the observed 33/49-byte-vertex D3D mesh variants."""
from dataclasses import dataclass
import math
import struct
from pathlib import Path


@dataclass(frozen=True)
class Vertex:
    position: tuple
    normal: tuple
    uv: tuple
    colour: tuple
    flags: int


@dataclass(frozen=True)
class Mesh:
    vertices: tuple
    triangles: tuple
    face_metadata: tuple


def decode(data):
    if len(data) < 8:
        raise ValueError('D3D header is truncated.')
    legacy=struct.unpack_from('<i',data)[0]!=-1
    if legacy:
        nv,nf=struct.unpack_from('<II',data)
        header,stride,fmt=8,33,'<8fB'
    else:
        if len(data)<12:raise ValueError('D3D header is truncated.')
        _,nv,nf=struct.unpack_from('<iII',data)
        header,stride,fmt=12,49,'<12fB'
    if len(data) != header+stride*nv+9*nf:
        raise ValueError('Unsupported D3D variant or incorrect record counts.')
    vertices=[]
    for index in range(nv):
        fields=struct.unpack_from(fmt,data,header+stride*index)
        if not all(math.isfinite(value) for value in fields[:-1]):
            raise ValueError('D3D vertex contains a non-finite value.')
        vertices.append(Vertex(fields[:3],fields[3:6],fields[6:8],
                               (1.,1.,1.,1.) if legacy else fields[8:12],fields[-1]))
    triangles=[]
    metadata=[]
    for index in range(nf):
        start=header+stride*nv+9*index
        triangle=struct.unpack_from('<3H',data,start)
        if any(i >= nv for i in triangle):
            raise ValueError('D3D triangle references a missing vertex.')
        triangles.append(triangle)
        metadata.append(data[start+6:start+9])
    return Mesh(tuple(vertices),tuple(triangles),tuple(metadata))


def obj(mesh):
    """Geometry/UV/normal export only; retain source winding and UV values."""
    lines=['# Davilex D3D geometry; materials, colours and opaque flags are omitted.']
    for v in mesh.vertices:
        lines.append('v '+' '.join(format(x,'.9g') for x in v.position))
    for v in mesh.vertices:
        lines.append('vt '+' '.join(format(x,'.9g') for x in v.uv))
    for v in mesh.vertices:
        lines.append('vn '+' '.join(format(x,'.9g') for x in v.normal))
    for face in mesh.triangles:
        lines.append('f '+' '.join(f'{i+1}/{i+1}/{i+1}' for i in face))
    return '\n'.join(lines)+'\n'


def export_obj(data,destination):
    text=obj(decode(data))
    path=Path(destination)
    with path.open('x',encoding='utf-8') as stream:
        stream.write(text)
    return path

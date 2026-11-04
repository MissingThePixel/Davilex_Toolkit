import struct
import unittest
from davilex.mesh import decode,obj,export_obj
from pathlib import Path
import tempfile


def sample():
    vertices=b''.join(struct.pack('<12fB',x,y,0,0,0,1,x,y,1,1,1,1,0) for x,y in ((0,0),(1,0),(0,1)))
    return struct.pack('<iII',-1,3,1)+vertices+struct.pack('<3H3B',0,1,2,10,20,30)


class MeshTests(unittest.TestCase):
    def test_legacy_vertices_keep_uvs_normals_flags_and_faces(self):
        vertices=b''.join(struct.pack('<8fB',x,y,0,0,0,1,x,y,7) for x,y in ((0,0),(1,0),(0,1)))
        data=struct.pack('<II',3,1)+vertices+struct.pack('<3H3B',0,1,2,10,20,30)
        mesh=decode(data)
        self.assertEqual(mesh.vertices[1].uv,(1,0))
        self.assertEqual(mesh.vertices[1].normal,(0,0,1))
        self.assertEqual(mesh.vertices[1].flags,7)
        self.assertEqual(mesh.vertices[1].colour,(1,1,1,1))
        self.assertEqual(mesh.triangles,((0,1,2),))
        self.assertEqual(mesh.face_metadata,(bytes((10,20,30)),))
        for bad in (data[:-1],data+b'\0',data[:-9]+struct.pack('<3H3B',0,1,3,0,0,0)):
            with self.assertRaises(ValueError):decode(bad)
        bad=bytearray(data);struct.pack_into('<f',bad,8,float('nan'))
        with self.assertRaises(ValueError):decode(bad)

    def test_geometry_and_metadata_survive_decode(self):
        mesh=decode(sample())
        self.assertEqual(mesh.vertices[1].position,(1,0,0))
        self.assertEqual(mesh.triangles,((0,1,2),))
        self.assertEqual(mesh.face_metadata,(bytes((10,20,30)),))
        self.assertIn('f 1/1/1 2/2/2 3/3/3',obj(mesh))

    def test_length_and_variant_are_strict(self):
        for data in (b'',sample()[:-1],sample()+b'\0',b'\0\0\0\0'+sample()[4:]):
            with self.assertRaises(ValueError): decode(data)

    def test_invalid_index_rejected(self):
        data=bytearray(sample())
        struct.pack_into('<H',data,12+49*3,3)
        with self.assertRaises(ValueError): decode(data)

    def test_nonfinite_vertex_rejected(self):
        data=bytearray(sample())
        struct.pack_into('<f',data,12,float('nan'))
        with self.assertRaises(ValueError): decode(data)

    def test_export_does_not_overwrite(self):
        root=Path(__file__).resolve().parents[1]/'.test-work'
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as temp:
            path=Path(temp)/'mesh.obj'
            path.write_text('preserve me',encoding='utf-8')
            with self.assertRaises(FileExistsError): export_obj(sample(),path)
            self.assertEqual(path.read_text(encoding='utf-8'),'preserve me')

import struct
import unittest
from pathlib import Path
from davilex.europe_crossroads import repair


def fixture(height=0,owner_road=False,paving=False):
    def quad(vertices):
        return b''.join(struct.pack('<5fI',x,y,z,0,0,0xffffff)for x,y,z in vertices)+struct.pack('<6I',0,1,2,0,2,3)
    deck=quad([(-10,height,-10),(10,height,-10),(10,height,10),(-10,height,10)])
    wall=quad([(-20,50,0),(20,50,0),(20,0,0),(-20,0,0)])
    paving_quad=quad([(-20,3,-20),(20,3,-20),(20,3,20),(-20,3,20)])
    road=struct.pack('<3i',-1,2+int(owner_road)+int(paving),20)
    centres=struct.pack('<I',20)
    for cell in range(20):
        for kind in range(4):
            data=deck if kind==0 and (cell==0 or (cell==9 and owner_road)) else wall if cell==9 and kind==3 else paving_quad if cell==9 and kind==1 and paving else b''
            road+=struct.pack('<I',bool(data))+data
        centres+=struct.pack('<3f2i',cell*100,0,0,123,456)
        centres+=struct.pack('<2I',1,0)if cell==9 else struct.pack('<I',0)
        centres+=struct.pack('<4I',1,37,1,38)
    return road,centres,struct.pack('<I6f',1,-20,0,0,40,0,0)


class CrossroadsTests(unittest.TestCase):
    def test_crossing_is_split_not_whole_wall_deleted(self):
        road,pmp,cmp=fixture();a,b,c,changes=repair(road,pmp,cmp)
        self.assertEqual(len(changes),2)
        self.assertEqual(changes[0]['retained_intervals'],[(0.,.25),(.75,1.)])
        # Existing segment IDs stay byte-identical; new partial walls append.
        self.assertEqual(c[4:28],cmp[4:]);self.assertEqual(struct.unpack_from('<I',c)[0],3)
        self.assertEqual(struct.unpack_from('<6f',c,28),(-20,0,0,10,0,0))
        self.assertEqual(struct.unpack_from('<6f',c,52),(10,0,0,10,0,0))
        self.assertEqual(struct.unpack_from('<I',a,4)[0],3)
        self.assertEqual(repair(a,b,c),(a,b,c,[]))
        # Triggers and lane memberships survive PMP reconstruction.
        at=4
        for cell in range(20):
            self.assertEqual(struct.unpack_from('<2i',b,at+12),(123,456));at+=20
            for kind in range(3):
                count=struct.unpack_from('<I',b,at)[0];at+=4
                ids=struct.unpack_from(f'<{count}I',b,at);at+=count*4
                if kind==1:self.assertEqual(ids,(37,))
                if kind==2:self.assertEqual(ids,(38,))
        self.assertEqual(at,len(b))

    def test_grade_separation_and_drivable_owner_are_preserved(self):
        for inputs in (fixture(height=200),fixture(owner_road=True)):
            self.assertEqual(repair(*inputs),(*inputs,[]))

    def test_body_clearance_extends_vertical_cut_ends(self):
        inputs=fixture();a,b,c,changes=repair(*inputs,clearance=5)
        self.assertEqual(changes[0]['retained_intervals'],[(0.,.125),(.875,1.)])
        self.assertEqual(repair(a,b,c,clearance=5),(a,b,c,[]))

    def test_raised_overlapping_paving_is_cut_without_losing_ground_outside_road(self):
        from davilex.europe_crossroads import _area
        a,b,c,changes=repair(*fixture(paving=True))
        self.assertEqual(sum(v.get('ground_overlap',False)for v in changes),1)
        at=12;surfaces=[]
        for cell in range(20):
            for kind in range(4):
                count=struct.unpack_from('<I',a,at)[0];at+=4
                for _ in range(count):
                    points=[struct.unpack_from('<3f',a,at+i*24)for i in range(4)]
                    if cell==9 and kind==1:surfaces.append(points)
                    at+=120
        self.assertAlmostEqual(sum(_area(p)for p in surfaces),1200)
        for p in surfaces:
            for indices in ((0,1,2),(0,2,3)):self.assertGreater(_area([p[i]for i in indices]),.001)
        self.assertEqual(repair(a,b,c),(a,b,c,[]))

    def test_oxford_recorded_blockage(self):
        source=Path(__file__).resolve().parents[1]/'analysis/baseline/London Racer'
        if not source.exists():self.skipTest('Original Oxford assets unavailable')
        from davilex.addons import compact_empty_cells
        r,p,o,_=compact_empty_cells(*[(source/('etappe4'+ext)).read_bytes()for ext in ('.rmp','.pmp','.omp')])
        c=(source/'etappe4.cmp').read_bytes()
        a,b,d,changes=repair(r,p,c,clearance=20)
        self.assertEqual(len(changes),28)
        self.assertEqual(sum(v.get('ground_overlap',False)for v in changes),14)
        self.assertEqual({v['cell']for v in changes},{236,240,241,242})
        self.assertTrue(any(v.get('wall')==489 and v['road_cells']==[61]for v in changes))
        self.assertTrue(any(v['kind']==3 and v['cell']==241 and v['road_cells']==[61]for v in changes))
        self.assertEqual(repair(a,b,d,clearance=20),(a,b,d,[]))


if __name__=='__main__':unittest.main()

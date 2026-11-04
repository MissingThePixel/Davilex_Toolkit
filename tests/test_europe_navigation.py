import struct
import unittest
from pathlib import Path
from davilex.europe_navigation import raise_buried_waypoints,trim_origin_tail


def fixture(heights=(50,),point_y=-15,modern=True):
    road=struct.pack('<iii',-1,len(heights),1)if modern else struct.pack('<ii',len(heights),1)
    road+=struct.pack('<I',len(heights))
    for height in heights:
        for x,z in ((0,0),(100,0),(100,100),(0,100)):
            road+=struct.pack('<5f',x,height,z,0,0)
            if modern:road+=struct.pack('<I',0xffffff)
        road+=struct.pack('<6I',0,1,2,0,2,3)
    road+=struct.pack('<3I',0,0,0)
    centres=struct.pack('<I3f2i',1,50,0,50,0,0)+struct.pack('<4I',0,1,0,0)
    point=struct.pack('<Iii3f4i',1,1,0,50,point_y,50,-1,-1,-1,-1)
    return road,centres,point


class EuropeNavigationTests(unittest.TestCase):
    def test_buried_point_only_changes_height_bytes(self):
        for modern in (False,True):
            road,centres,original=fixture(modern=modern)
            repaired,changes=raise_buried_waypoints(road,centres,original)
            self.assertEqual(struct.unpack_from('<f',repaired,16)[0],50)
            self.assertEqual(repaired[:16],original[:16]);self.assertEqual(repaired[20:],original[20:])
            self.assertEqual(changes,[{'node':0,'old_y':-15,'new_y':50}])
            self.assertEqual(raise_buried_waypoints(road,centres,repaired),(repaired,[]))

    def test_authored_small_offsets_above_road_and_lower_decks_retained(self):
        for heights,y in (((50,),45),((50,),65),((0,50),0)):
            road,centres,original=fixture(heights,y)
            self.assertEqual(raise_buried_waypoints(road,centres,original),(original,[]))

    def test_malformed_navigation_is_rejected(self):
        road,centres,original=fixture()
        for data in ((road[:-1],centres,original),(road,centres[:-1],original),(road,centres,original[:-1])):
            with self.assertRaises((ValueError,struct.error)):raise_buried_waypoints(*data)

    def test_hamburg_berlin_bridge_regression(self):
        source=Path(__file__).resolve().parents[1]/'analysis/baseline/Autobahn Raser II'
        original=(source/'etappe8.dmp').read_bytes()
        repaired,changes=raise_buried_waypoints((source/'etappe8.rmp').read_bytes(),
            (source/'etappe8.pmp').read_bytes(),original)
        self.assertEqual(struct.unpack_from('<f',original,4+288*36+12)[0],-15)
        self.assertEqual(struct.unpack_from('<f',repaired,4+288*36+12)[0],50)
        allowed={4+row['node']*36+12+i for row in changes for i in range(4)}
        self.assertTrue(all(i in allowed for i,(a,b)in enumerate(zip(original,repaired))if a!=b))
        self.assertEqual(len(original),len(repaired))
        self.assertTrue(all(row['new_y']-row['old_y']>10 for row in changes))

    def test_hamburg_berlin_origin_cell_regression(self):
        source=Path(__file__).resolve().parents[1]/'analysis/baseline/Autobahn Raser II'
        raw={ext:(source/('etappe8'+ext)).read_bytes()for ext in ('.rmp','.pmp','.omp','.cmp')}
        rmp,pmp,removed=trim_origin_tail(*(raw[ext]for ext in ('.rmp','.pmp','.omp','.cmp')))
        self.assertEqual(removed,[{'cell':690,'quads':32,'unreferenced_cmp_ids':[2842,2843,2844,2845]}])
        self.assertEqual(struct.unpack_from('<I',rmp,8)[0],690)
        self.assertEqual(struct.unpack_from('<I',pmp)[0],690)
        self.assertEqual(rmp[12:],raw['.rmp'][12:len(rmp)])
        self.assertEqual(pmp[4:],raw['.pmp'][4:len(pmp)])
        self.assertEqual(trim_origin_tail(rmp,pmp,raw['.omp'],raw['.cmp']),(rmp,pmp,[]))
        for protected in ('trigger','waypoint','object'):
            centres=bytearray(raw['.pmp']);objects=bytearray(raw['.omp'])
            if protected=='trigger':struct.pack_into('<i',centres,len(centres)-48+12,14)
            elif protected=='waypoint':struct.pack_into('<I',centres,len(centres)-4,1);centres+=struct.pack('<I',0)
            else:
                struct.pack_into('<I',objects,0,struct.unpack_from('<I',objects)[0]+1)
                objects+=struct.pack('<ii6f32si',690,0,0,0,0,0,0,0,b'',0)
            self.assertEqual(trim_origin_tail(raw['.rmp'],bytes(centres),bytes(objects),raw['.cmp']),
                (raw['.rmp'],bytes(centres),[]))

    def test_other_ar2_terminal_cells_are_retained(self):
        source=Path(__file__).resolve().parents[1]/'analysis/baseline/Autobahn Raser II'
        for stage in (0,2,3,4,10):
            raw=[(source/(f'etappe{stage}'+ext)).read_bytes()for ext in ('.rmp','.pmp','.omp','.cmp')]
            self.assertEqual(trim_origin_tail(*raw),(raw[0],raw[1],[]))

if __name__=='__main__':unittest.main()

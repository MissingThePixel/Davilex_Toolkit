"""Reject empty Europe tuning columns before they poison the physics/camera.

The original constructor at 0x4565bd indexes five tuning columns per field.
0x4ef76c divides body mass by the selected front suspension spring. The
retained Classic-car files have empty columns 3/4; the menu can select 3.
Use the authored base column for an unusable selection, never invented values.
"""
import math
import struct
from pathlib import Path
from .translate import ini_lines
from .quickrace import update_ini
from .europe_car_capacity import CAPACITY


def values(raw):
    return {(s,k):m[4].strip() for _,s,k,_,m in ini_lines(raw)}


def usable(raw, level):
    if len(raw)!=1032 or not 0<=level<=4:return False
    def field(offset):return struct.unpack_from('<f',raw,offset+4*level)[0]
    positive=(332,352,392,432,732,792)
    nonnegative=(268,288,372,752,812)
    return (all(math.isfinite(field(o)) and field(o)>0 for o in positive)
            and all(math.isfinite(field(o)) and field(o)>=0 for o in nonnegative)
            and field(352)>field(372)
            and field(268)+field(288)>0)


def tuning_changes(game, cars, read_dynamics):
    settings=values(game);catalog=values(cars);changes={};report=[]
    selections=[('Player',settings.get(('player','car')))]
    selections.extend(('Racer'+k,v.split(',')[0].strip()) for (s,k),v in settings.items()
                      if s=='racers' and k.isdigit())
    for key,car in selections:
        requested=settings.get(('upgrades',key.casefold()))
        if requested is None or car is None:continue
        try:
            level=int(requested);engine_id=int(car)
            row=catalog['cars',str(engine_id)].split(',')
            dynamics=int(row[5].strip())
            if not 0<=dynamics<CAPACITY:raise ValueError('Dynamics index outside engine table')
        except (KeyError,IndexError,ValueError) as error:
            raise ValueError(f'Invalid Europe tuning selection for {key}: car {car}.') from error
        raw=read_dynamics(dynamics)
        if usable(raw,level):continue
        if not usable(raw,0):
            raise ValueError(f'Europe car {engine_id} has no usable base physics profile (VDYNS{dynamics}.DAT).')
        changes['UPGRADES',key]=0
        report.append({'racer':key,'car':engine_id,'dynamics':dynamics,'requested':level,'selected':0})
    return changes,report


def ensure_valid_tuning(engine):
    directory=Path(engine).parent;config=directory/'Ini/game.ini'
    original=config.read_bytes()
    changes,report=tuning_changes(original,(directory/'Ini/Cars.ini').read_bytes(),
        lambda index:(directory/f'Vdyns/VDYNS{index}.DAT').read_bytes())
    if changes:
        config.write_bytes(update_ini(original,changes))
        for item in report:
            print(f"Europe tuning: {item['racer']} car {item['car']}, empty/invalid level "
                  f"{item['requested']} -> authored base level 0.",flush=True)
    return report

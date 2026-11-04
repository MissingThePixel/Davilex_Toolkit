"""Recognise only byte-exact toolkit output, without trusting moved journals."""
import struct

def dimensions(data,profile):
 from .resolution import OVERLAYS
 try:
  if data[:2]!=b'MZ':return None
  pe=struct.unpack_from('<I',data,0x3c)[0];opt=pe+24
  if data[pe:pe+4]!=b'PE\0\0':return None
  count=struct.unpack_from('<H',data,pe+6)[0]
  if not 0<count<96:return None
  base=struct.unpack_from('<I',data,opt+28)[0];table=opt+struct.unpack_from('<H',data,pe+20)[0]
  va=0x5b37b0 if profile=='a2racer4-resolution' else OVERLAYS[profile]['table']
  rva=va+9*20-base
  for i in range(count):
   _,section,stored,pos=struct.unpack_from('<4I',data,table+i*40+8)
   if section<=rva and rva+8<=section+stored:
    width,height=struct.unpack_from('<2I',data,pos+rva-section)
    if 640<=width<=8192 and 480<=height<=8192 and width*3>=height*4:return width,height
 except (struct.error,KeyError,OverflowError):pass
 return None

def engine_matches(current,canonical,profile):
 if current==canonical:return True
 from .resolution import patch_engine
 size=dimensions(current,profile);seeds=[canonical]
 if size:
  try:seeds.append(patch_engine(canonical,*size,profile)[0])
  except ValueError:pass
 for seed in seeds:
  if current==seed:return True
  if not profile.startswith('europe'):continue
  from .europe_tracks import expand as tracks
  from .europe_car_capacity import expand as cars
  from .europe_animation import patch as animation
  variants=[seed]
  for operation in (tracks,cars,animation):
   try:seed=operation(seed)
   except (ValueError,struct.error):break
   variants.append(seed)
  if current in variants:return True
 return False

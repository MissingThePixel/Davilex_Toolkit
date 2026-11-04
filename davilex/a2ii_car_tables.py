"""Read A2 Racer II's compiled animation configuration without executing it.

Unlike the later INI files, these tables live in spel.dat. The layouts are
traced through 0x42b310 (names), 0x42b360 (bindings), 0x45d650 (frames),
0x44d320 (animations), and 0x4136c0 (wheel positions).
"""
import hashlib,struct
from pathlib import Path
HASHES={'551484bcf472407fd67ee8933c6f26b5a937d428e9e0cdf0cd72988dd003c2f9',
        '0f367445cc5e1bdb7caef28a0f9b7dab4b0ddd238673903c46d0ec1de3813703'}
class Image:
    def __init__(self,path):
        self.data=Path(path).read_bytes()
        if hashlib.sha256(self.data).hexdigest() not in HASHES:raise ValueError('Unknown A2II executable table layout')
        pe,=struct.unpack_from('<I',self.data,0x3c);sections,=struct.unpack_from('<H',self.data,pe+6);optional,=struct.unpack_from('<H',self.data,pe+20)
        self.base,=struct.unpack_from('<I',self.data,pe+24+28);self.sections=[]
        for n in range(sections):
            start=pe+24+optional+n*40;virtual_size,rva,raw_size,raw=struct.unpack_from('<4I',self.data,start+8)
            self.sections.append((self.base+rva,max(virtual_size,raw_size),raw,raw_size))
    def read(self,address,size):
        for start,length,raw,raw_size in self.sections:
            if start<=address and address+size<=start+length:
                offset=address-start;available=max(0,min(size,raw_size-offset))
                return self.data[raw+offset:raw+offset+available]+bytes(size-available)
        raise ValueError('Table address outside mapped PE sections')
    def value(self,address,fmt='<I'):return struct.unpack(fmt,self.read(address,struct.calcsize(fmt)))
    def text(self,address):
        result=bytearray()
        for n in range(256):
            byte=self.read(address+n,1)
            if byte==b'\0':return result.decode('cp1252')
            result+=byte
        raise ValueError('Unterminated PE string')

def configuration(executable,stage):
    image=Image(executable)
    meshes=[image.text(image.value(0x48d0e0+i*12)[0]) for i in range(0x165)]
    textures=[image.text(image.value(0x48e1a0+i*12)[0]) for i in range(0x5b)]
    anims={}
    for n in range(0x138):
        name=image.text(image.value(0x490430+n*4)[0]).casefold();count,pointer,flag=image.value(0x492050+n*9,'<IIB')
        if count>1024:raise ValueError('Unexpected animation frame count')
        frames={}
        for j in range(count):
            index=image.value(pointer+j*4)[0]
            if index>=0x182:raise ValueError('Invalid compiled frame index')
            _,_,mesh,texture=image.value(0x48e5e8+index*16,'<4i')
            frames[str(j)]=meshes[mesh]+','+textures[texture]
        frames['count']=str(count);anims[name]=frames
    stage_ini={'textures':{str(i):f'e{(0 if stage==6 else stage):02d}_{name}.pcx' for i,name in enumerate(('gras','weg','vang','gra2'))},'objects':{}}
    for n,(name,frames) in enumerate(anims.items()):
        if '0' in frames:stage_ini['objects'][str(n)]=frames['0']+',compiled table,0,'+name
    cars={'league0':{},'wheel_positions':{}}
    for car in range(7):
        section=f'racer_{car+1}_anim';anims[section]['1']=anims['wiel_anim']['0']
        wheels=image.value(0x486198+car*48,'<12f')
        cars['wheel_positions'][str(car)]=','.join(str(x) for x in (*wheels[:3],*wheels[6:9]))
        # Native scene exploration uses provisional mass; original old-family
        # chassis recovery is separate from these proven geometry bindings.
        cars['league0'][str(car)]=f'RACER_{car},{section},unknown,none,1000,{car},0'
    return stage_ini,anims,cars

BASE=0x484b18;STRIDE=238;COUNT=16
KNOWN={0:'mass_kg',1:'inertia_length_m',2:'inertia_width_m',3:'axle_distance_a_m',
       4:'axle_distance_b_m',5:'cg_height_m',10:'gravity',12:'drag_speed_factor',
       13:'front_tyre_B',14:'front_tyre_C',15:'front_tyre_D',16:'rear_tyre_B',
       17:'rear_tyre_C',18:'rear_tyre_D',19:'rolling_factor',20:'wheel_radius_m'}
def records(executable):
    image=Image(executable);result=[]
    for index in range(COUNT):
        address=BASE+index*STRIDE;raw=image.read(address,STRIDE)
        name=raw[:14].split(b'\0')[0].decode('ascii')
        if not name.endswith('_ANIM'):raise ValueError('Unexpected compiled car name')
        values=[struct.unpack_from('<i' if j in (24,53) else '<f',raw,22+j*4)[0] for j in range(54)]
        result.append({'index':index,'address':hex(address),'animation':name,
            'fields':{KNOWN.get(j,'slot_'+str(j)):value for j,value in enumerate(values)},
            'slots':values})
    return result
import math
def maximum_speed(v):
    # 0x40ce10 loops indices 1..7, retaining every non--1 ratio. Index 7
    # aliases the final-drive field in this layout; preserve the original read.
    ratio=next(v[25+n] for n in range(7,0,-1) if v[25+n]!=-1)
    rate=v[32]*ratio*2.653927813163482/v[20]
    linear=2*(v[22]/v[23])*rate*v[35]*v[32]*ratio/v[20]
    quadratic=-((v[22]/(v[23]*v[23]))*rate*rate*v[35]*v[32]*ratio/v[20]+v[11]*v[7]*v[6]*.5)
    discriminant=linear*linear+1200*quadratic
    if discriminant<0:return 0.
    root=math.sqrt(discriminant)
    return max((root-linear)/(2*quadratic),(-linear-root)/(2*quadratic))

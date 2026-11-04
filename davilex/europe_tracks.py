"""Relocate Europe's 30-entry track table into bounded 64-entry PE storage.

All 45 reviewed absolute table operands move together; the adjacent original
globals are retained. Raising the load guard alone would overwrite those globals.
"""
import struct

OLD=0x69f134
STRIDE=0x94
CAPACITY=64
REFERENCES=(
 (0x41d1ea,0x69f134),(0x420d3f,0x69f134),(0x421094,0x69f134),(0x421110,0x69f134),
 (0x4557fd,0x69f138),(0x4878d3,0x69f138),(0x487b3b,0x69f138),(0x487dc2,0x69f138),
 (0x495111,0x69f17e),(0x49512f,0x69f18c),(0x499423,0x69f1c4),(0x499b18,0x69f138),
 (0x49ab8a,0x69f134),(0x49bb64,0x69f138),(0x49da1a,0x69f1c0),(0x49da6a,0x69f138),
 (0x49daff,0x69f138),(0x49db9b,0x69f138),(0x49dc37,0x69f138),(0x49e17e,0x69f146),
 (0x49e1a6,0x69f146),(0x49e1c3,0x69f154),(0x49e1ed,0x69f154),(0x49e20c,0x69f170),
 (0x49e234,0x69f170),(0x49e251,0x69f162),(0x49e27b,0x69f162),(0x49e2bf,0x69f162),
 (0x49e2c5,0x69f170),(0x49e2cc,0x69f154),(0x49e2d3,0x69f146),(0x49e40f,0x69f138),
 (0x49e427,0x69f138),(0x49e5ef,0x69f1be),(0x49e5f6,0x69f1bc),(0x49e605,0x69f1ba),
 (0x4a1bb4,0x69f134),(0x4d355c,0x69f146),(0x4d35e8,0x69f154),(0x4d3674,0x69f170),
 (0x4d3700,0x69f162),(0x4d9655,0x69f138),(0x4d976b,0x69f138),(0x4d9bd8,0x69f138),
 (0x4da260,0x69f138))


def expand(original):
    pe=struct.unpack_from('<I',original,0x3c)[0];optional=pe+24
    if original[pe:pe+4]!=b'PE\0\0' or struct.unpack_from('<I',original,optional+28)[0]!=0x400000:
        raise ValueError('Unsupported Europe PE layout')
    count=struct.unpack_from('<H',original,pe+6)[0]
    table=optional+struct.unpack_from('<H',original,pe+20)[0]
    sections=[struct.unpack_from('<8sIIIIIIHHI',original,table+i*40) for i in range(count)]
    def offset(va):
        rva=va-0x400000
        for s in sections:
            if s[2]<=rva<s[2]+s[3]:return s[4]+rva-s[2]
        raise ValueError('Unmapped Europe track operand')
    if any(s[0].rstrip(b'\0')==b'.dvTrks' for s in sections):
        raise ValueError('Track-table expansion expects a verified source ingredient')
    if original[offset(0x49bb36):offset(0x49bb36)+3]!=b'\x83\xf8\x1e':
        raise ValueError('Unexpected Europe track-count guard')
    for address,value in REFERENCES:
        if struct.unpack_from('<I',original,offset(address))[0]!=value:
            raise ValueError(f'Unexpected Europe track-table reference {address:#x}')
    if struct.unpack_from('<I',original,offset(0x49aa14))[0]!=0x66a9c8:
        raise ValueError('Unexpected Europe loading-art filename cache')
    sa,fa=struct.unpack_from('<II',original,optional+32)
    align=lambda n,a:(n+a-1)//a*a
    # Earlier verified timer work reserves additional image pages beyond the
    # original section extents. Preserve that reservation and place new storage
    # after SizeOfImage; shrinking it would unmap the timer object.
    original_image_size=struct.unpack_from('<I',original,optional+56)[0]
    rva=align(max(original_image_size,max(s[2]+max(s[1],s[3]) for s in sections)),sa)
    raw=align(len(original),fa);size=CAPACITY*(STRIDE+13);stored=align(size,fa)
    header=table+count*40
    if header+40>min(s[4] for s in sections if s[3]) or any(original[header:header+40]):
        raise ValueError('No free PE section header for expanded track table')
    data=bytearray(original);data.extend(b'\0'*(raw+stored-len(data)))
    struct.pack_into('<8sIIIIIIHHI',data,header,b'.dvTrks\0',size,rva,stored,raw,0,0,0,0,0xc0000040)
    struct.pack_into('<H',data,pe+6,count+1)
    struct.pack_into('<I',data,optional+8,struct.unpack_from('<I',original,optional+8)[0]+stored)
    struct.pack_into('<I',data,optional+56,align(rva+size,sa))
    base=0x400000+rva
    for address,value in REFERENCES:struct.pack_into('<I',data,offset(address),base+value-OLD)
    # load_wait_info also writes one thirteen-byte name per track. Its old
    # cache precedes a singleton pointer; extending only MAPS corrupts it.
    struct.pack_into('<I',data,offset(0x49aa14),base+CAPACITY*STRIDE)
    data[offset(0x49bb36)+2]=CAPACITY
    return bytes(data)

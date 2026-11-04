"""Register collision-bearing static animations after their physics creation.

Europe retains the type-15 update callback but its constructor omits the
registration performed by types 12/13. Its original maps never use type 15;
AR II's Dortmund does. Preserve the existing collider and add the missing
registration, rather than disabling animation or collision.
"""
import struct
SITE=0x4894bf
RESUME=0x48967c
MANAGER=0x6c3d80
REGISTER=0x4bab60

def helper(address):
    code=bytearray(b'\x9c\x83\x7d\x08\x0f\x75\x00\x60\xb9'+struct.pack('<I',MANAGER)+b'\x53')
    code+=b'\xe8'+struct.pack('<i',REGISTER-(address+len(code)+5))
    code+=b'\xa1'+struct.pack('<I',0x6c4458)
    code+=b'\x69\xd3'+struct.pack('<I',0x158)+b'\xc7\x44\x10\x6c\x01\x00\x00\x00\x61'
    code[6]=len(code)-7
    code+=b'\x9d\xe9'+struct.pack('<i',RESUME-(address+len(code)+6))
    return bytes(code)

def patch(original):
    pe=struct.unpack_from('<I',original,0x3c)[0];opt=pe+24
    if original[pe:pe+4]!=b'PE\0\0' or struct.unpack_from('<I',original,opt+28)[0]!=0x400000:
        raise ValueError('Unsupported Europe animation PE layout')
    count=struct.unpack_from('<H',original,pe+6)[0];table=opt+struct.unpack_from('<H',original,pe+20)[0]
    sections=[struct.unpack_from('<8sIIIIIIHHI',original,table+i*40)for i in range(count)]
    def offset(address):
        for s in sections:
            if s[2]<=address-0x400000<s[2]+s[3]:return s[4]+address-0x400000-s[2]
        raise ValueError('Unmapped Europe animation code')
    if any(s[0].rstrip(b'\0')==b'.dvAnim'for s in sections):raise ValueError('Animation repair requires original constructor')
    expected=b'\xe9'+struct.pack('<i',RESUME-SITE-5)
    if original[offset(SITE):offset(SITE)+5]!=expected:raise ValueError('Unexpected Europe collision constructor exit')
    sa,fa=struct.unpack_from('<II',original,opt+32);align=lambda n,a:(n+a-1)//a*a
    rva=align(max(struct.unpack_from('<I',original,opt+56)[0],max(s[2]+max(s[1],s[3])for s in sections)),sa)
    body=helper(0x400000+rva);raw=align(len(original),fa);stored=align(len(body),fa);header=table+count*40
    if header+40>min(s[4]for s in sections if s[3])or any(original[header:header+40]):raise ValueError('No free Europe animation section header')
    data=bytearray(original);data.extend(bytes(raw+stored-len(data)));data[raw:raw+len(body)]=body
    struct.pack_into('<8sIIIIIIHHI',data,header,b'.dvAnim\0',len(body),rva,stored,raw,0,0,0,0,0x60000020)
    struct.pack_into('<H',data,pe+6,count+1)
    struct.pack_into('<I',data,opt+4,struct.unpack_from('<I',original,opt+4)[0]+stored)
    struct.pack_into('<I',data,opt+56,align(rva+len(body),sa))
    data[offset(SITE):offset(SITE)+5]=b'\xe9'+struct.pack('<i',0x400000+rva-SITE-5)
    return bytes(data)

"""Extend the verified Delphi menu's language enum and dynamic string-list load."""
import struct

KEYS=tuple(f'LT_DV_CAR{i}'for i in range(78,128))
OLD_COUNT=409

def expand(original):
    pe=struct.unpack_from('<I',original,0x3c)[0];opt=pe+24
    if original[pe:pe+4]!=b'PE\0\0' or struct.unpack_from('<I',original,opt+28)[0]!=0x400000:
        raise ValueError('Unsupported Europe menu PE layout')
    count=struct.unpack_from('<H',original,pe+6)[0];table=opt+struct.unpack_from('<H',original,pe+20)[0]
    sections=[struct.unpack_from('<8sIIIIIIHHI',original,table+i*40)for i in range(count)]
    def offset(va):
        for s in sections:
            if s[2]<=va-0x400000<s[2]+s[3]:return s[4]+va-0x400000-s[2]
        raise ValueError('Unmapped Europe menu operand')
    if any(s[0].rstrip(b'\0')==b'.dvLang'for s in sections):raise ValueError('Language expansion requires original verified ingredient')
    pointer=offset(0x46a7ac);loop=offset(0x46c1c9)
    if struct.unpack_from('<I',original,pointer)[0]!=0x46a7b0 or struct.unpack_from('<I',original,loop)[0]!=OLD_COUNT:
        raise ValueError('Unexpected Europe language table/loader')
    start=offset(0x46a7b0);end=offset(0x46bfc2);descriptor=bytearray(original[start:end])
    if descriptor[:15]!=b'\x03\x0dTLanguageText' or struct.unpack_from('<I',descriptor,20)[0]!=408:
        raise ValueError('Unexpected Europe language enum')
    struct.pack_into('<I',descriptor,20,OLD_COUNT+len(KEYS)-1)
    for name in KEYS:
        encoded=name.encode('ascii');descriptor+=bytes([len(encoded)])+encoded
    sa,fa=struct.unpack_from('<II',original,opt+32);align=lambda n,a:(n+a-1)//a*a
    # This Delphi image fills its section-header table. Extend the last resource
    # section without moving existing bytes or changing any resource directory.
    last=max(range(count),key=lambda i:sections[i][4]+sections[i][3]);section=sections[last]
    if section[0].rstrip(b'\0')!=b'.rsrc' or section[4]+section[3]!=len(original):
        raise ValueError('Unexpected Europe menu resource-section tail')
    raw=align(len(original),fa);rva=section[2]+raw-section[4]
    size=len(descriptor);stored=align(raw+size-section[4],fa);virtual=raw+size-section[4]
    result=bytearray(original);result.extend(bytes(section[4]+stored-len(result)));result[raw:raw+size]=descriptor
    struct.pack_into('<I',result,table+last*40+8,virtual)
    struct.pack_into('<I',result,table+last*40+16,stored)
    struct.pack_into('<I',result,opt+8,struct.unpack_from('<I',original,opt+8)[0]+stored-section[3])
    struct.pack_into('<I',result,opt+56,align(section[2]+virtual,sa))
    struct.pack_into('<I',result,pointer,0x400000+rva)
    struct.pack_into('<I',result,loop,OLD_COUNT+len(KEYS))
    # The relocated descriptor includes Delphi's absolute BaseType pointer.
    # Keep it valid if Wine/Windows relocates this otherwise fixed-base image.
    reloc_rva,reloc_size=struct.unpack_from('<II',original,opt+96+5*8)
    reloc_section=next(s for s in sections if s[2]<=reloc_rva<s[2]+s[3])
    reloc_end=offset(0x400000+reloc_rva)+reloc_size
    if reloc_end+12>reloc_section[4]+reloc_section[3] or any(original[reloc_end:reloc_end+12]):
        raise ValueError('No free relocation padding for menu language descriptor')
    target=rva+24
    struct.pack_into('<IIHH',result,reloc_end,target&~4095,12,0x3000|(target&4095),0)
    struct.pack_into('<I',result,opt+96+5*8+4,reloc_size+12)
    return bytes(result)

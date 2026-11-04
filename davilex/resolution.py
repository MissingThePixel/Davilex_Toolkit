"""Verified native-resolution and HUD adapters for the seven captured engines."""
import hashlib
import struct

A2IV_SOURCE_SHA256 = '3ed3c7ea468b96915fd145ce2720df8e68a0ac8bd188e6af9e72c2f92154be48'

SOURCES = {
    'a2racer4-resolution':('A2 Racer 4-menu-cycle','a2racer4-vram','A2IV'),
    'holiday-resolution':('Holiday Racer-menu-timing','holiday-timing','Holiday'),
    'pmr-resolution':('PMR-menu-timing','pmr-timing','PMR'),
    'europe-resolution':('Europe Racer-menu-timing','europe-timing','Europe'),
    'a2ii-resolution':('A2II-menu-cycle','a2ii-timing','A2II'),
    'autobahn2-resolution':('Autobahn Raser II-menu-cycle','autobahn2-timing','Autobahn2'),
    'london-resolution':('London Racer-menu-cycle','london-timing','London'),
}
LEGACY = {
    'a2ii-resolution':dict(sha='0f367445cc5e1bdb7caef28a0f9b7dab4b0ddd238673903c46d0ec1de3813703',
        width=0x49e72c,table=0x49e748,viewport=(0x45d22b,0x45d23a),clip=(0x45d26d,0x45d279),ratios=[],scale=None,
        helper='2f3ab9c939562445aa31878043138494965b56e33a3b15d14d03338355e595a7',hud=(0x41bdd0,0x41a8a0),
        background_rect=0x4881a0,minimap_rect=0x489050,
        blts=[0x46926b,0x4692f9,0x469387,0x46960b,0x4696b2,0x46975a]),
    'autobahn2-resolution':dict(sha='b1f852158d9391c54574eaa4d9ce3acf1b8a6d032543a90cecaacf2398d7a613',
        width=0x49baa0,table=0x49bab8,viewport=(0x460e07,0x460e17),clip=(0x460e4a,0x460e56),ratios=[],scale=None,
        helper='2acfe288ed2ccb12cc40f7d15741ee8fa7659746ec49fb5db54a9c21e3df3d0e',hud=(0x428b40,0x427b20),
        blts=[0x46a058,0x46a0e3,0x46a16e,0x46a3f4,0x46a498,0x46a53d]),
    'london-resolution':dict(sha='a6d1340729f7946fbb153a98faded0a099c53a51dc87e8fa34a2b4ffd525eafb',
        width=0x4c79f8,table=0x4c7a10,viewport=(0x489fbd,0x489fc3),clip=(0x48a017,0x48a02d),ratios=[],scale=None,
        helper='3dc448653b5c913f41faa4010a5e2b2a9bbc89a4c357bbae4ab42e2706c8c956',hud=(0x433d2f,0x4328fb),
        blts=[0x4988e8,0x498973,0x4989fe,0x498c84,0x498d28,0x498dcd]),
}
# Verified per-build instruction addresses, not pattern matches applied blindly.
OVERLAYS = {
    'holiday-resolution':dict(sha='167895e194b41fa36134b68bc7b6a9aa6c1c115e8915bb1f983bff5a3c468b84',
        width=0x50a978,table=0x50a990,viewport=(0x48e757,0x48e767),clip=(0x48e79a,0x48e7a6),
        ratios=[(0x45f39d,0x45f3b1,False),(0x4622b5,0x4622bb,True),(0x462994,0x4629aa,True)],
        scale=0x5639b8),
    'pmr-resolution':dict(sha='3380c7241710922910e53025d74f837cc9baa55393f5b25a5ffa3caaa5136fee',
        width=0x592728,table=0x592740,viewport=(0x4b9623,0x4b9629),clip=(0x4b967c,0x4b9692),
        ratios=[(0x475850,0x475856,False),(0x478d22,0x478d28,True),(0x47949c,0x4794a2,True)],
        scale=0x5eddf8),
    'europe-resolution':dict(sha='1827f986fc733d0538182f316f869fae1888dad8c5cc1ebc18abe7118a5bf807',
        width=0x61f0e8,table=0x61f100,viewport=(0x59fcaa,0x59fcba),clip=(0x59fced,0x59fcf9),
        ratios=[(0x4c7f38,0x4c7f4a,False),(0x4c8178,0x4c818a,False),
                (0x4cc85e,0x4cc864,True),(0x4cc933,0x4cc939,True)],scale=0x6c4270),
}
OVERLAYS.update(LEGACY)

# These radar implementations derive both marker axes from map width. Keep
# their map rectangle square and marker sizes uniform using screen height.
RADARS={
    'holiday-resolution':dict(width=0x50a978,map_x=0x42eeee,left=0x42eefc,span=0x42ef06,
        marker_x=0x42f148,marker_scale=0x42f14f,
        constants=(0x4e0604,0x4e05dc,0x4e0378,0x4e0600,0x4e0608,0x4e060c)),
    'a2racer4-resolution':dict(width=0x5b3798,map_x=0x44222e,left=0x44223c,span=0x442246,
        marker_x=0x44248c,marker_scale=0x442493,
        constants=(0x576760,0x576734,0x57675c,0x576758,0x576764,0x576768)),
}


def radar_edits(profile):
    spec=RADARS.get(profile)
    if spec is None:return []
    old_left,new_left,old_span,new_span,old_marker,new_marker=spec['constants']
    load=lambda op,address:op+struct.pack('<I',address)
    return [(spec[key],load(b'\xdb\x05',spec['width']),load(b'\xdb\x05',spec['width']+4))
            for key in ('map_x','marker_x')]+[
        (spec[key],load(b'\xd8\x0d',old),load(b'\xd8\x0d',new))
        for key,old,new in [('left',old_left,new_left),('span',old_span,new_span),
                            ('marker_scale',old_marker,new_marker)]]


def patch_engine(original, width, height, profile):
    if profile == 'a2racer4-resolution':
        return patch_a2iv(original,width,height)
    if profile not in OVERLAYS:
        raise ValueError('Unsupported resolution adapter.')
    if type(width) is not int or type(height) is not int or not (640<=width<=8192 and 480<=height<=8192) or width*3<height*4:
        raise ValueError('Use integer dimensions of at least 640x480, at most 8192 per axis, and 4:3 or wider.')
    spec=OVERLAYS[profile]
    if hashlib.sha256(original).hexdigest()!=spec['sha']:
        raise ValueError('Unsupported resolution source engine.')
    pe=struct.unpack_from('<I',original,0x3c)[0];optional=pe+24
    table=optional+struct.unpack_from('<H',original,pe+20)[0]
    count=struct.unpack_from('<H',original,pe+6)[0]
    base=struct.unpack_from('<I',original,optional+28)[0]
    def offset(address,size):
        for n in range(count):
            _,rva,stored,pos=struct.unpack_from('<4I',original,table+n*40+8)
            if rva<=address-base and address-base+size<=rva+stored:return pos+address-base-rva
        raise ValueError('Unmapped resolution patch address.')
    # Row 3 remains the immutable 640x480x8 design reference; row 9 is
    # the selected 16-bit native framebuffer. Do not change shared floats.
    design=spec['table']+3*20
    if struct.unpack_from('<5I',original,offset(design,20))!=(640,480,8,0,0):
        raise ValueError('Unexpected design mode row.')
    edits=[(spec['table']+9*20,struct.pack('<2I',640,480),struct.pack('<2I',width,height))]
    edits.extend(radar_edits(profile))
    if spec.get('background_rect'):
        edits.append((spec['background_rect'],struct.pack('<4I',0,0,639,479),struct.pack('<4I',0,0,width-1,height-1)))
    if spec.get('minimap_rect'):
        # The radar draws a separate textured TL quad, outside bitmap HUD Blts.
        # Preserve its design-space size and left/bottom margins uniformly.
        radar=(30,361,158,489)
        native=tuple(round(value*height/480) for value in radar)
        edits.append((spec['minimap_rect'],struct.pack('<4i',*radar),struct.pack('<4i',*native)))
    for first,last,inverse in [(*spec['viewport'],False),*spec['ratios']]:
        numerator=spec['width']+(0 if inverse else 4)
        denominator=spec['width']+(4 if inverse else 0)
        edits.extend([(first,b'\xdb\x05'+struct.pack('<I',numerator),b'\xdb\x05'+struct.pack('<I',design+(0 if inverse else 4))),
                      (last,b'\xda\x35'+struct.pack('<I',denominator),b'\xda\x35'+struct.pack('<I',design+(4 if inverse else 0)))])
    half_x=.75*width/height
    # MOV DWORD PTR [register+disp8], imm32 has the same seven-byte form
    # across these builds, though the base register differs in debug PMR.
    for address,field,before_value,after_value in [(spec['clip'][0],0x14,-1.,-half_x),(spec['clip'][1],0x1c,2.,2*half_x)]:
        prefix=original[offset(address,7):offset(address,7)+3]
        if prefix[0]!=0xc7 or prefix[1]&0xf8!=0x40 or prefix[2]!=field:
            raise ValueError('Unexpected clip-volume instruction.')
        edits.append((address,prefix+struct.pack('<f',before_value),prefix+struct.pack('<f',after_value)))
    changed=bytearray(original);report=[]
    for address,before,after in edits:
        pos=offset(address,len(before))
        if original[pos:pos+len(before)]!=before:raise ValueError(f'Unexpected resolution instruction at {address:#x}.')
        changed[pos:pos+len(after)]=after
        report.append({'address':hex(address),'file_offset':pos,'before':before.hex(),'after':after.hex()})
    code_section=None
    if spec.get('blts'):
        from .launch import ROOT
        from .paths import resources
        code=(resources(ROOT)/'tools/native'/('hud-'+profile.removesuffix('-resolution'))/'hud.bin').read_bytes()
        if hashlib.sha256(code).hexdigest()!=spec['helper']:raise ValueError('HUD helper build changed.')
        align=lambda n,a:(n+a-1)//a*a
        section_align,file_align=struct.unpack_from('<2I',original,optional+32)
        last=table+(count-1)*40
        vsize,rva,stored,pos=struct.unpack_from('<4I',original,last+8)
        new_rva=align(rva+max(vsize,stored),section_align)
        thunk,body=spec['hud'];wrapper_offset=align(len(code),16)
        flag=base+new_rva+0x400;wrapper_address=base+new_rva+wrapper_offset
        wrapper=(b'\xc7\x05'+struct.pack('<II',flag,1)+
                 b'\xe8'+struct.pack('<i',body-(wrapper_address+10)-5)+
                 b'\xc7\x05'+struct.pack('<II',flag,0)+b'\xc3')
        payload=code+b'\x90'*(wrapper_offset-len(code))+wrapper
        if len(payload)>=0x400:raise ValueError('HUD wrapper overlaps its state flag.')
        raw=align(len(original),file_align);raw_size=align(len(payload),file_align)
        header=table+count*40
        first_raw=min(struct.unpack_from('<I',original,table+n*40+20)[0] for n in range(count))
        if header+40>first_raw or any(original[header:header+40]):raise ValueError('No free HUD section header.')
        changed.extend(b'\0'*(raw+raw_size-len(changed)))
        changed[raw:raw+len(payload)]=payload
        struct.pack_into('<8sIIIIIIHHI',changed,header,b'.dvHUD\0\0',0x404,new_rva,raw_size,raw,0,0,0,0,0xe0000020)
        struct.pack_into('<H',changed,pe+6,count+1)
        struct.pack_into('<I',changed,optional+4,struct.unpack_from('<I',original,optional+4)[0]+raw_size)
        struct.pack_into('<I',changed,optional+56,align(new_rva+0x404,section_align))
        pos=offset(thunk,5);opcode=original[pos:pos+1]
        if opcode not in (b'\xe8',b'\xe9'):raise ValueError('Unexpected dashboard transfer opcode.')
        before=opcode+struct.pack('<i',body-thunk-5)
        if original[pos:pos+5]!=before:raise ValueError('Unexpected dashboard thunk.')
        after=opcode+struct.pack('<i',wrapper_address-thunk-5)
        changed[pos:pos+5]=after
        report.append({'address':hex(thunk),'file_offset':pos,'before':before.hex(),'after':after.hex()})
        for address in spec['blts']:
            pos=offset(address,5);before=original[pos:pos+5]
            if before[0]!=0xff or before[1] not in (0x50,0x51,0x52,0x53,0x56,0x57) or before[2:]!=b'\x14\x85\xc0':
                raise ValueError(f'Unexpected HUD Blt/TEST site {address:#x}.')
            after=b'\xe8'+struct.pack('<i',base+new_rva-address-5)
            changed[pos:pos+5]=after
            report.append({'address':hex(address),'file_offset':pos,'before':before.hex(),'after':after.hex()})
        code_section=dict(address=hex(base+new_rva),bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),helper_sha256=spec['helper'],
                          policy='Only within draw_dashboard: uniform rectangles and right panel edge anchor; original source rectangles/results; TEST EAX before RET 24.')
    result=dict(source_sha256=spec['sha'],patched_sha256=hashlib.sha256(changed).hexdigest(),
        dimensions=[width,height],depth=16,clip_xy_width_height=[-half_x,.75,2*half_x,1.5],
        hud_canvas=[640*height/480,height],hud_policy='Uniform centred 640x480 overlay design canvas.',
        camera_policy='Vertical framing retained; horizontal view expands with aspect; dynamic FOV retained.',
        hud_recording=False,edits=report)
    if code_section:
        result['code_section']=code_section
        result['hud_policy']='Uniform bitmap HUD rectangles; dashboard right panel at right edge; central prompts retained.'
    return bytes(changed),result


def patch_a2iv(original, width, height):
    """Return patched bytes and exact edits; support 4:3 and wider canvases."""
    if type(width) is not int or type(height) is not int:
        raise ValueError('Resolution dimensions must be integers.')
    if not (640 <= width <= 8192 and 480 <= height <= 8192):
        raise ValueError('Dimensions must be between 640x480 and 8192x8192.')
    if width * 3 < height * 4:
        raise ValueError('This adapter currently supports 4:3 and wider aspect ratios.')
    if hashlib.sha256(original).hexdigest() != A2IV_SOURCE_SHA256:
        raise ValueError('Unsupported A2IV engine; expected the verified VRAM-fixed build.')
    # Only this fixed PE32 build is supported; validate mappings before every edit.
    pe = struct.unpack_from('<I', original, 0x3c)[0]
    if original[pe:pe+4] != b'PE\0\0':
        raise ValueError('Invalid PE header.')
    count = struct.unpack_from('<H', original, pe+6)[0]
    optional = pe+24
    table = optional+struct.unpack_from('<H', original, pe+20)[0]
    base = struct.unpack_from('<I', original, optional+28)[0]

    def offset(address, size):
        rva = address-base
        for n in range(count):
            _, start, stored, file_offset = struct.unpack_from('<4I', original, table+n*40+8)
            if start <= rva and rva+size <= start+stored:
                return file_offset+rva-start
        raise ValueError(f'Unmapped patch address {address:#x}.')

    changed = bytearray(original)
    half_x = .75*width/height
    edits = [
        (0x5b37b0+9*20, struct.pack('<2I',640,480), struct.pack('<2I',width,height)),
        (0x4c0e47, bytes.fromhex('db059c375b00'), bytes.fromhex('d9050c6e5700')),
        (0x4c0e57, bytes.fromhex('da3598375b00'), b'\x90'*6),
        (0x4c0e8a, bytes.fromhex('c74614000080bf'), b'\xc7\x46\x14'+struct.pack('<f',-half_x)),
        (0x4c0e96, bytes.fromhex('c7461c00000040'), b'\xc7\x46\x1c'+struct.pack('<f',2*half_x)),
        (0x47cdbd, bytes.fromhex('db059c375b00'), bytes.fromhex('d9050c6e5700')),
        (0x47cdd1, bytes.fromhex('da3598375b00'), b'\x90'*6),
        (0x47fe55, bytes.fromhex('db0598375b00'), bytes.fromhex('d905086e5700')),
        (0x47fe5b, bytes.fromhex('da359c375b00'), b'\x90'*6),
        (0x480534, bytes.fromhex('db0598375b00'), bytes.fromhex('d905086e5700')),
        (0x48054a, bytes.fromhex('da359c375b00'), b'\x90'*6),
    ]
    edits.extend(radar_edits('a2racer4-resolution'))
    report = []
    for address, before, after in edits:
        pos = offset(address,len(before))
        if len(before) != len(after) or original[pos:pos+len(before)] != before:
            raise ValueError(f'Unexpected instructions/data at {address:#x}.')
        changed[pos:pos+len(after)] = after
        report.append({'address':hex(address),'file_offset':pos,'before':before.hex(),'after':after.hex()})
    return bytes(changed), {
        'source_sha256':A2IV_SOURCE_SHA256,
        'patched_sha256':hashlib.sha256(changed).hexdigest(),
        'dimensions':[width,height], 'depth':16,
        'clip_xy_width_height':[-half_x,.75,2*half_x,1.5],
        'hud_canvas':[640*height/480,height],
        'hud_policy':'Uniform 640x480 design canvas, centred; original overlay scale and positions.',
        'camera_policy':'Vertical framing retained; horizontal view expands with aspect; dynamic FOV retained.',
        'hud_recording':False, 'edits':report,
    }


def select_resolution(engine):
    """The legacy menu may select another preset; reassert the patched mode."""
    from .quickrace import update_ini
    europe=engine.name.lower()=='spel.exe'
    config = engine.parent/'Ini/game.ini' if europe else engine.parent/'raser.ini'
    config.write_bytes(update_ini(config.read_bytes(),{('OPTIONS' if europe else 'PROGRAM','RESOLUTION'):3}))

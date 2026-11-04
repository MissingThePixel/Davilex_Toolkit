"""Rebuild original toolkit helpers from an x86 MSVC Developer Command Prompt."""
from pathlib import Path
import argparse,hashlib,struct,subprocess

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind',choices=['hud','colourkey']);args=parser.parse_args()
    out=ROOT/'.cache/native-build';out.mkdir(parents=True,exist_ok=True)
    if args.kind=='colourkey':
        target=out/'davilex-colourkey.dll'
        subprocess.run(['cl','/nologo','/O2','/MT','/EHsc','/LD',str(ROOT/'native/android_colourkey.cpp'),
            '/Fe'+str(target),'/Fo'+str(out/'colourkey.obj'),'/link','/SUBSYSTEM:WINDOWS','/Brepro','user32.lib'],check=True)
        print('Built',target,'SHA-256',hashlib.sha256(target.read_bytes()).hexdigest())
        print('Runtime pins the reviewed DLL hash; review and update COLOURKEY_HASH before replacing its resource.')
        return
    for name,active,width in [('a2ii',5235712,4843308),('autobahn2',5370880,4831904),('london',5542912,5011960)]:
        obj=out/(name+'.obj')
        subprocess.run(['cl','/nologo','/c','/O2','/GS-','/W4','/WX','/DHUD_CUSTOM','/DHUD_EDGE_RIGHT',
            '/DHUD_ACTIVE_ADDRESS='+str(active),'/DHUD_WIDTH_ADDRESS='+str(width),
            '/DHUD_HEIGHT_ADDRESS='+str(width+4),str(ROOT/'native/hud_scale.cpp'),'/Fo'+str(obj)],check=True)
        data=obj.read_bytes();machine,count,_,_,_,optional,_=struct.unpack_from('<HHIIIHH',data)
        if machine!=0x14c or optional:raise ValueError('Expected x86 COFF')
        sections=[struct.unpack_from('<8sIIIIIIHHI',data,20+i*40)for i in range(count)]
        text=[s for s in sections if s[0].rstrip(b'\0').startswith(b'.text')and s[3]]
        if len(text)!=1 or text[0][7]:raise ValueError('Expected relocation-free text')
        s=text[0];code=data[s[4]:s[4]+s[3]]
        # The patched call site also replaced TEST EAX,EAX. Preserve its flags
        # before the single stdcall return, as in the original helper builder.
        end=len(code.rstrip(b'\xcc'))-3
        if code[end:end+3]!=b'\xc2\x18\x00' or code.count(b'\xc2\x18\x00')!=1:raise ValueError('Unexpected helper epilogue')
        code=code[:end]+b'\x85\xc0'+code[end:end+3]
        target=out/(name+'-hud.bin');target.write_bytes(code)
        expected=ROOT/'resources/tools/native'/('hud-'+name)/'hud.bin'
        print(name,hashlib.sha256(code).hexdigest(),'matches bundled:',code==expected.read_bytes())

if __name__=='__main__':main()

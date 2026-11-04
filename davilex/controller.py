"""Optional game-local Xidi mode, with reversible input settings."""
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import time
from .launch import ROOT
from .paths import resources
from .quickrace import update_ini
from .translate import ini_lines

LIBRARY=resources(ROOT)/'tools/third_party/Xidi-5.0.0/package/Xidi-v5.0.0/Win32'
HASHES={'dinput.dll':'055cddd3c02f3edc45abd616c613bdd8980f8499034a6c48dd3f80895e0e5947',
        'winmm.dll':'3fc06a49ad833174b4ce7a5269043c7da41af14a64068f3612f58e1d769b44fe',
        'Xidi.32.dll':'771c991cfbf7d02dc58eb1a83ca39a68b1a029446cfef1f8875150de6aca38a8'}
CONFIG='''; Game-local Xidi profile. No driver installation or system-wide changes.
[Mapper]
Type = DavilexRacing
[CustomMapper:DavilexRacing]
Template = StandardGamepad
StickLeftX = Axis(X)
StickLeftY = Null
TriggerRT = Axis(Y, -)
TriggerLT = Axis(Y, +)
[Properties]
DeadzonePercentStickLeft = 8
DeadzonePercentTriggerLT = 3
DeadzonePercentTriggerRT = 3
[Workarounds]
ActiveVirtualControllerMask = 0x01
[Log]
Enabled = no
'''


def configuration(engine,profile,*,defaults=True):
    if profile.startswith('europe'):
        changes={('InputGeneral','InputDevice'):'AnalogController',
                 ('InputKeyBinds','TurnLeft'):'JS_LEFT',('InputKeyBinds','TurnRight'):'JS_RIGHT',
                 ('InputKeyBinds','MoveForward'):'JS_UP',('InputKeyBinds','MoveBack'):'JS_DOWN',
                 ('InputKeyBinds','Turbo'):'JS_BUTTON1',('InputKeyBinds','HandBrake'):'JS_BUTTON2',
                 ('InputKeyBinds','Horn'):'JS_BUTTON3',('InputKeyBinds','Reset'):'JS_BUTTON4'}
        config=engine.parent/'Ini/game.ini'
        if defaults:
            existing={(s,k):m[4].strip() for _,s,k,_,m in ini_lines(config.read_bytes())}
            # Preserve joystick mappings chosen by the user in the menu.
            changes={key:value for key,value in changes.items() if key[0]=='InputGeneral' or
                     existing[(key[0].casefold(),key[1].casefold())].upper().startswith('KB_')}
        else:
            changes={('InputGeneral','InputDevice'):'AnalogController'}
        return config,changes
    return engine.parent/'game.ini',{('INPUT','DEVICE'):3}


def select_controller(engine,profile):
    config,changes=configuration(engine,profile,defaults=False)
    config.write_bytes(update_ini(config.read_bytes(),changes))


def restore(directory):
    directory=Path(directory).resolve()
    from .installed import permitted
    if not permitted(directory):raise ValueError('Controller mode requires a project working copy.')
    journal=directory/'.controller-restore';manifest=journal/'manifest.json'
    if not manifest.exists():return
    data=json.loads(manifest.read_text())
    config=(directory/data['config']).resolve()
    if not config.is_relative_to(directory):raise ValueError('Invalid controller recovery path.')
    changes={(e['section'].casefold(),e['key'].casefold()):e for e in data['edits']}
    current=config.read_bytes();lines=current.decode('cp1252').splitlines(keepends=True)
    for i,section,key,_,match in ini_lines(current):
        edit=changes.get((section,key))
        if edit and match[4].strip()==str(edit['after']):
            trailing=__import__('re').search(r'[ \t]*$',match[4])[0]
            lines[i]=match[1]+match[2]+match[3]+edit['before']+trailing+(match[5] or '')
    config.write_bytes(''.join(lines).encode('cp1252'))
    for item in data['created']:
        path=(directory/item['file']).resolve()
        if not path.is_relative_to(directory):raise ValueError('Invalid controller recovery path.')
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
                raise ValueError(f'Controller file changed; preserving it: {path}')
            path.unlink()
    manifest.rename(journal/f'restored-{time.time_ns()}.json')


@contextmanager
def controller_mode(directory,profile):
    from .menu import verify_copy
    directory=Path(directory).resolve();restore(directory)
    menu,engine=verify_copy(directory,profile)
    config,settings=configuration(engine,profile);original=config.read_bytes()
    existing={(s,k):m[4].strip() for _,s,k,_,m in ini_lines(original)}
    patched=update_ini(original,settings)
    payload={}
    for name,expected in HASHES.items():
        content=(LIBRARY/name).read_bytes()
        if hashlib.sha256(content).hexdigest()!=expected:raise ValueError(f'Unexpected Xidi build: {name}')
        payload[name]=content
    payload['Xidi.ini']=CONFIG.encode('ascii')
    destinations=[]
    for folder in sorted({menu.parent,engine.parent}):
        for name,content in payload.items():
            path=folder/name
            if path.exists():raise ValueError(f'Existing input wrapper/configuration is preserved; choose a clean working copy: {path}')
            destinations.append((path,content))
    journal=directory/'.controller-restore';journal.mkdir(exist_ok=True)
    (journal/'original-game.ini').write_bytes(original)
    record={'config':str(config.relative_to(directory)),
            'edits':[{'section':s,'key':k,'before':existing[(s.casefold(),k.casefold())],'after':v} for (s,k),v in settings.items()],
            'created':[{'file':str(path.relative_to(directory)),'sha256':hashlib.sha256(content).hexdigest()} for path,content in destinations]}
    (journal/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    try:
        for path,content in destinations:
            with path.open('xb') as stream:stream.write(content)
        config.write_bytes(patched)
        yield
    finally:restore(directory)

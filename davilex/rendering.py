"""Game-local renderer settings for verified compatibility copies."""
import re
import os
from contextlib import contextmanager
from .launch import ROOT


@contextmanager
def graphics_backend(renderer='ddrawcompat',controller=False):
    """Wine DLL selection applies only to this launcher and its child games."""
    if renderer not in ('ddrawcompat','wine','dgvoodoo-windowed','dgvoodoo-debug','dxwrapper'):raise ValueError('Unknown graphics backend.')
    original=os.environ.get('WINEDLLOVERRIDES')
    requested={'ddraw':'b' if renderer=='wine' else 'n,b'}
    if renderer in ('dgvoodoo-windowed','dgvoodoo-debug'):requested['d3dimm']='n,b'
    if controller:requested.update(dinput='n,b',winmm='n,b')
    entries=[]
    for entry in (original or '').split(';'):
        if '=' not in entry:
            if entry.strip():entries.append(entry)
            continue
        names,value=entry.split('=',1)
        remaining=[name.strip() for name in names.split(',') if name.strip().casefold() not in requested]
        if remaining:entries.append(','.join(remaining)+'='+value)
    entries.extend(name+'='+value for name,value in requested.items())
    os.environ['WINEDLLOVERRIDES']=';'.join(entries)
    try:yield
    finally:
        if original is None:os.environ.pop('WINEDLLOVERRIDES',None)
        else:os.environ['WINEDLLOVERRIDES']=original


def depth_configuration(original):
    """Use sufficient depth precision, retaining unrelated renderer settings."""
    lines=original.splitlines(keepends=True)
    matches=[(i,re.match(rb'([ \t]*DepthFormat[ \t]*=[ \t]*)([^;#\r\n]*)([^\r\n]*)(\r?\n)?$',line,re.I))
             for i,line in enumerate(lines)]
    matches=[(i,m) for i,m in matches if m]
    if len(matches)>1:raise ValueError('Multiple DepthFormat settings; preserving the configuration.')
    if matches:
        i,m=matches[0]
        value=m[2].strip().lower()
        if value in (b'24',b'32'):return original
        if value not in (b'app',b'16'):raise ValueError('Unknown DepthFormat; preserving the configuration.')
        trailing=re.search(rb'[ \t]*$',m[2])[0]
        lines[i]=m[1]+b'24'+trailing+m[3]+(m[4] or b'')
        changed=b''.join(lines)
    else:
        changed=original+(b'\r\n' if original and not original.endswith(b'\n') else b'')
        changed+=b'# Increase depth precision for overlapping surfaces.\r\nDepthFormat = 24\r\n'
    return changed


def ensure_depth_precision(engine,profile):
    """Apply the shared depth policy to every supported engine."""
    from .launch import PROFILES
    if profile not in PROFILES:raise ValueError('Unknown rendering profile.')
    from .installed import ACTIVE
    session=ACTIVE.get()
    if not (session and engine.resolve()==session['engine']) and not engine.resolve().is_relative_to((ROOT/'work').resolve()):
        raise ValueError('Renderer settings require a verified game session.')
    config=engine.parent/'DDrawCompat.ini'
    original=config.read_bytes() if config.exists() else b''
    changed=depth_configuration(original)
    if original==changed:return False
    backup=engine.parent/'.depth-format-original'
    if not backup.exists():backup.write_bytes(original)
    config.write_bytes(changed)
    return True

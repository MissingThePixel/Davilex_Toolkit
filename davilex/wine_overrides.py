"""Recoverable application DLL overrides for Wine's Unix-side loader.

SetEnvironmentVariableW does not change the Unix getenv() used by Wine's loader.
Use AppDefaults for each child instead, never the bottle-wide DllOverrides key.
"""
from contextlib import contextmanager
import ctypes
import json
import os
from pathlib import Path
from .paths import ROOT
from .installed import write_json

APPS={'menu.exe','menu.dat','gamemenu.dat','spel.dat','spel.exe'}
DLLS={'ddraw','d3dimm','dinput','winmm'}
JOURNAL=ROOT/'work/wine-dll-overrides.json'


def running_under_wine():
    if os.name!='nt':return False
    return hasattr(ctypes.WinDLL('ntdll'),'wine_get_version')


def key_for(app):
    if app not in APPS:raise ValueError('Unsupported Wine application override.')
    return 'Software\\Wine\\AppDefaults\\'+app+'\\DllOverrides'


class Registry:
    def __init__(self):
        import winreg
        self.api=winreg

    def read(self,app,name):
        api=self.api
        try:
            with api.OpenKey(api.HKEY_CURRENT_USER,key_for(app),0,api.KEY_READ|api.KEY_WOW64_32KEY) as key:
                value,kind=api.QueryValueEx(key,name)
        except FileNotFoundError:return None
        if kind!=api.REG_SZ:raise ValueError('Unexpected Wine override type; preserving existing value.')
        return value

    def write(self,app,name,value):
        api=self.api
        if value is None:
            try:
                with api.OpenKey(api.HKEY_CURRENT_USER,key_for(app),0,api.KEY_SET_VALUE|api.KEY_WOW64_32KEY) as key:
                    api.DeleteValue(key,name)
            except FileNotFoundError:pass
        else:
            with api.CreateKeyEx(api.HKEY_CURRENT_USER,key_for(app),0,api.KEY_SET_VALUE|api.KEY_WOW64_32KEY) as key:
                api.SetValueEx(key,name,0,api.REG_SZ,value)


def restore(backend=None,journal=None):
    journal=Path(journal or JOURNAL)
    if not journal.exists():return
    if backend is None:
        if not running_under_wine():return
        backend=Registry()
    items=json.loads(journal.read_text(encoding='utf-8'))
    for item in reversed(items):
        app,name,before,after=(item[k] for k in ('app','name','before','after'))
        key_for(app)
        if name not in DLLS or after not in ('native','native,builtin','builtin') or not (before is None or isinstance(before,str)):
            raise ValueError('Invalid Wine override recovery journal.')
        current=backend.read(app,name)
        if current==before:continue
        if current!=after:raise ValueError('Wine override changed during launch; preserving it and its recovery journal.')
        backend.write(app,name,before)
    journal.unlink()


@contextmanager
def application_overrides(executable,renderer,controller=False,backend=None,journal=None):
    if backend is None:
        if not running_under_wine():
            yield;return
        backend=Registry()
    journal=Path(journal or JOURNAL)
    app=Path(executable).name.casefold();key_for(app)
    restore(backend,journal)
    requested={'ddraw':'builtin' if renderer=='wine' else 'native,builtin'}
    if renderer in ('dgvoodoo-windowed','dgvoodoo-debug'):requested={'ddraw':'native','d3dimm':'native'}
    if renderer=='dxwrapper':requested={'ddraw':'native'}
    if controller:requested.update(dinput='native,builtin',winmm='native,builtin')
    items=[{'app':app,'name':name,'before':backend.read(app,name),'after':value} for name,value in requested.items()]
    journal.parent.mkdir(parents=True,exist_ok=True)
    write_json(journal,items)
    try:
        for item in items:backend.write(app,item['name'],item['after'])
        print('Wine application DLL overrides: '+app+'; '+', '.join(k+'='+v for k,v in requested.items()),flush=True)
        yield
    finally:restore(backend,journal)

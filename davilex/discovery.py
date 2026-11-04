"""Bounded installed-game discovery, without a persistent file-data cache."""
import os
from pathlib import Path

def candidates(title,root):
    aliases={title,'A2 Racer II' if title=='A2II' else title,'A2 Racer IV' if title=='A2 Racer 4' else title,'Paris Marseille Racing' if title=='Paris - Marseille Racing' else title}
    for name in sorted(aliases):yield root/'games'/name
    if os.name=='nt':
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
            for view in (winreg.KEY_WOW64_32KEY,winreg.KEY_WOW64_64KEY):
                try:
                    with winreg.OpenKey(hive,r'Software\Microsoft\Windows\CurrentVersion\Uninstall',0,winreg.KEY_READ|view) as key:
                        for i in range(winreg.QueryInfoKey(key)[0]):
                            try:
                                with winreg.OpenKey(key,winreg.EnumKey(key,i)) as item:
                                    name=winreg.QueryValueEx(item,'DisplayName')[0]
                                    if name.casefold() in {x.casefold() for x in aliases}:
                                        location=winreg.QueryValueEx(item,'InstallLocation')[0]
                                        if location:yield Path(location)
                            except OSError:continue
                except OSError:continue
    bases={Path(os.environ.get(name,default)) for name,default in [('ProgramFiles(x86)','C:/Program Files (x86)'),('ProgramFiles','C:/Program Files')]}
    for base in sorted(bases):
        for name in sorted(aliases):
            for publisher in ('','Davilex','Davilex Games','Xplosiv'):
                yield base/publisher/name

def game_roots():
    from .installed import locate
    from .settings import load
    from .toolkit import GAMES
    saved=load().get('installs',{});seen=set()
    for name,profile in GAMES.items():
        try:folder=locate(profile,saved.get(name))
        except (OSError,ValueError):
            try:folder=locate(profile)
            except (OSError,ValueError):continue
        if folder not in seen:seen.add(folder);yield name,folder

def identify_game(folder):
    """Identify sibling installs by known engine/index bytes, not folder names."""
    from .installed import baseline,digest
    from .toolkit import GAMES
    from .launch import PROFILES
    from .menu import MENU_PROFILES
    folder=Path(folder);claims={};hashes={}
    def fingerprint(path):
        if path not in hashes:hashes[path]=digest(path.read_bytes())if path.is_file()else None
        return hashes[path]
    for name,profile in GAMES.items():
        try:
            if not all((folder/rel).is_file()for rel in (PROFILES[profile][1],MENU_PROFILES[profile][1])):continue
            known={Path(f['path']).as_posix().casefold():f['sha256']for f in baseline(profile)['files']}
            engine=Path(PROFILES[profile][1]);index=engine.parent/'rcs.ind'
            score=2*int(fingerprint(folder/engine)==known.get(engine.as_posix().casefold()))
            expected=known.get(index.as_posix().casefold())
            if expected and fingerprint(folder/index)==expected:score+=1
            if score:claims[name]=score
        except (OSError,ValueError):continue
    if not claims:return None
    best=max(claims.values());names=[name for name,score in claims.items()if score==best]
    return names[0]if len(names)==1 else None

def sibling_installs(selected,known=None):
    """Scan one shared parent only; keep valid explicit paths and avoid ties."""
    from .installed import locate
    from .toolkit import GAMES
    selected=Path(selected).resolve();known=dict(known or {});found={}
    try:folders=sorted(p for p in selected.parent.iterdir()if p.is_dir())[:500]
    except OSError:return known
    for folder in folders:
        name=identify_game(folder)
        if name:found.setdefault(name,set()).add(folder.resolve())
    for name,folders in found.items():
        try:
            if name in known:locate(GAMES[name],known[name]);continue
        except (OSError,ValueError):pass
        if len(folders)==1:known[name]=str(next(iter(folders)))
    return known

def discover_from_known(known):
    result=dict(known);parents=set()
    for location in tuple(known.values()):
        folder=Path(location)
        if folder.is_dir()and folder.parent not in parents:
            parents.add(folder.parent);result=sibling_installs(folder,result)
    return result

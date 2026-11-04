"""Portable user settings; bundled game locations are relative to the toolkit."""
import json
from pathlib import Path,PureWindowsPath
from .paths import ROOT

def load(root=None):
    root=Path(root or ROOT)
    try:
        result=json.loads((root/'work/toolkit-settings.json').read_text(encoding='utf-8'))
        if not isinstance(result,dict):return {}
    except (OSError,ValueError):return {}
    installs=result.get('installs',{})
    result['installs']={}
    if isinstance(installs,dict):
        for game,value in installs.items():
            if not isinstance(value,str):continue
            path=Path(value)
            if not path.is_absolute() and not PureWindowsPath(value).drive:
                candidate=(root/path).resolve()
                if candidate.is_relative_to(root.resolve()) and candidate.is_dir():result['installs'][game]=str(candidate)
            elif path.is_dir():result['installs'][game]=str(path.resolve())
            else:
                # Migrate old absolute Y:\...\games\Title paths. Only rebase
                # the explicit games suffix, never guess an external folder.
                parts=PureWindowsPath(value).parts
                for i,part in enumerate(parts):
                    if part.casefold()=='games':
                        candidate=root.joinpath(*parts[i:])
                        if candidate.is_dir():result['installs'][game]=str(candidate.resolve())
                        break
    return result

def save(value,root=None):
    root=Path(root or ROOT).resolve();result=dict(value);result['installs']={}
    for game,location in value.get('installs',{}).items():
        path=Path(location).resolve()
        result['installs'][game]=path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
    destination=root/'work/toolkit-settings.json';destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_suffix('.tmp');temporary.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');temporary.replace(destination)

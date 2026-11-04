"""Separate the portable application's writable folder and bundled resources."""
from pathlib import Path
import sys

ROOT=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]


def resources(project_root=ROOT):
    if getattr(sys,'frozen',False):return Path(sys._MEIPASS)/'resources'
    packaged=Path(project_root)/'resources'
    return packaged if packaged.is_dir() else project_root


def command(mode,*arguments):
    if getattr(sys,'frozen',False):return [sys.executable,'--'+mode,*map(str,arguments)]
    return [sys.executable,'-m','davilex.'+mode,*map(str,arguments)]


def archive_root():
    return ROOT/'games' if (ROOT/'games').is_dir() else ROOT/'analysis/baseline'


def patch_source(profile,resource_root=None):
    from .resolution import SOURCES
    key=next(k for k,v in SOURCES.items() if profile in (k,v[1]))
    root=Path(resource_root) if resource_root is not None else resources(ROOT)
    compact=root/'patches'/key
    return compact if compact.is_dir() else root/'work'/SOURCES[key][0]

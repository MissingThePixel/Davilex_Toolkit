"""Single executable entry point and child-process dispatch for portable builds."""
import contextlib
import json
from pathlib import Path
import sys
import traceback
from .paths import ROOT,resources,archive_root


def self_test(output):
    from .legacy_car_addons import handling as legacy_handling
    from .car_addons import CATALOG
    from .europe_menu_language import KEYS
    from .europe_car_capacity import CAPACITY
    from .paths import resources
    import hashlib
    ingredient=resources(ROOT)/'davilex/a2ii_car_catalog.json'
    if hashlib.sha256(ingredient.read_bytes()).hexdigest()!='fa48bf42c4d708503071c6411612c9e2839c92e04e19b8d724f674b103b3b0ff':
        raise ValueError('Packaged A2 II car-table ingredient is missing or changed')
    if len(CATALOG)>CAPACITY-78 or len(KEYS)!=CAPACITY-78:raise ValueError('Vehicle catalog exceeds reserved engine/menu capacity')
    from .toolkit import GAMES
    from .installed import locate,plan
    from .quickrace import race_catalog
    from .launcher import Launcher
    from .viewer import Viewer
    import tkinter as tk
    result={'frozen':bool(getattr(sys,'frozen',False)),'root':str(ROOT),'resources':str(resources(ROOT)),'games':{}}
    from .windowed import payloads
    if (not getattr(sys,'frozen',False) and not (resources(ROOT)/'patches/binary-recipes.json').is_file()) or (resources(ROOT)/'wrappers/dgvoodoo').is_dir():
        result['windowed_backend']={name:len(data) for name,data in payloads().items()}
        result['diagnostic_backend']={name:len(data) for name,data in payloads(diagnostic=True).items()}
    from .windowed import dxwrapper_payloads
    result['d3d9_backend']={name:len(data) for name,data in dxwrapper_payloads().items()}
    gui=tk.Tk();gui.withdraw();launcher=Launcher(gui);gui.update_idletasks()
    for game in GAMES:
        launcher.game.set(game);launcher.refresh();gui.update_idletasks()
        if launcher.catalog_error:raise ValueError(launcher.catalog_error)
    gui.destroy()
    viewer=Viewer();viewer.withdraw();viewer.update_idletasks()
    result['viewer_archives']=len(viewer.presets)
    # Exercise the actual image/numerical extensions, not just the empty UI.
    from .rcs import Archive
    from .mesh import decode
    from .media import load_image
    from .texture_bindings import Resolver
    from .textures import prepare
    from .mesh_preview import render
    from PIL import ImageTk
    archive=Archive(archive_root()/'A2 Racer 4/rcs.img')
    resolver=Resolver(archive,archive_root());result['model_previews']={}
    for name in ('01vectra.d3d','08manta.d3d','08popors.d3d'):
        entry=next(e for e in archive.entries if e.name.casefold()==name)
        bindings=resolver.resolve(entry)
        if not bindings:raise ValueError('Missing test-model texture: '+name)
        binding=bindings[0]
        with load_image(binding.archive,binding.entry) as image:texture,_=prepare(image)
        preview=render(decode(archive.read(entry)),size=(180,140),texture=texture)
        tk_image=ImageTk.PhotoImage(preview,master=viewer)
        if tk_image.width()!=180:raise ValueError('Tk image extension failed.')
        destination=Path(output).with_name(Path(name).stem+'-portable-preview.png')
        preview.save(destination)
        result['model_previews'][name]={'texture':binding.entry.name,'preview':str(destination)}
    viewer.close()
    from .audio import pcm_wav
    import tempfile
    import wave
    audio=next(e for e in sorted(archive.entries,key=lambda e:e.size) if e.extension=='.wav' and e.size>128)
    with tempfile.TemporaryDirectory(prefix='audio-check-',dir=ROOT/'.cache') as folder:
        extracted=archive.extract(audio,folder)
        converted=pcm_wav(extracted,Path(folder)/'converted.wav',allow_external=False)
        with wave.open(str(converted),'rb') as decoded:
            if decoded.getsampwidth()!=2:raise ValueError('Audio conversion is not PCM16.')
            result['audio_conversion']={'entry':audio.name,'channels':decoded.getnchannels(),'frames':decoded.getnframes(),'backend':'miniaudio (external fallback disabled)'}
    for game,profile in GAMES.items():
        directory=locate(profile);payload,_,_,_=plan(directory,profile,1920,1080)
        result['games'][game]={'directory':str(directory),'patch_files':len(payload),
                              'tracks':len(race_catalog(profile)['tracks']),'cars':len(race_catalog(profile)['cars'])}
    Path(output).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')


def default_mode(executable=None):
    return '--viewer' if Path(executable or sys.executable).stem.casefold()=='rcs explorer' else '--launcher'


def main():
    from .ui import enable_dpi_awareness
    enable_dpi_awareness()
    ROOT.joinpath('work').mkdir(exist_ok=True)
    ROOT.joinpath('analysis').mkdir(exist_ok=True)
    mode=sys.argv[1] if len(sys.argv)>1 else default_mode()
    if mode=='--self-test':
        self_test(sys.argv[2]);return
    if mode in ('--toolkit','--elevated','--viewer','--launcher'):
        if len(sys.argv)>1:sys.argv.pop(1)
        if mode=='--toolkit':
            from .toolkit import main as run
        elif mode=='--elevated':
            from .elevated import main as run
        elif mode=='--viewer':
            from .viewer import main as run
        else:
            from .launcher import main as run
        if mode=='--toolkit':
            with (ROOT/'work/toolkit-last-run.log').open('w',encoding='utf-8',buffering=1) as log:
                with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):run()
        else:run()
    else:raise ValueError('Unknown executable mode: '+mode)


def guarded_main():
    try:main()
    except SystemExit:raise
    except BaseException:
        ROOT.joinpath('work').mkdir(exist_ok=True)
        details=traceback.format_exc()
        (ROOT/'work/application-error.log').write_text(details,encoding='utf-8')
        if '--self-test' not in sys.argv:
            import tkinter.messagebox
            tkinter.messagebox.showerror('Davilex Toolkit',details[-1800:])
        raise SystemExit(1)


if __name__=='__main__':guarded_main()

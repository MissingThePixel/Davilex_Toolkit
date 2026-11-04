"""Coordinate verified original menus and patched engines in isolated copies."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import re
import subprocess
from .launch import ROOT, verified_engine
from .paths import resources
from .quickrace import update_ini
from .menu_media import shell_safe_menu,prepare_local_intro,holiday_menu,europe_menu,ensure_pmr_true_colour
from .display_guard import preserve_display
from .menu_media import desktop_menu_bytes
from .menu_backdrop import black_backdrop
from contextlib import nullcontext

MENU_PROFILES={
    'a2ii-timing':('A2II','menu.dat',('\\FIRST',),(),None),
    'a2racer4-vram':('A2 Racer 4','menu.exe',('/FirstTime',),('/Default',),'menu.ini'),
    'a2racer4-resolution':('A2 Racer 4','menu.exe',('/FirstTime',),('/Default',),'menu.ini'),
    'autobahn2-timing':('Autobahn Raser II','menu.exe',('/FirstTime',),('/Default',),'menu.ini'),
    'london-timing':('London Racer','menu.exe',('/FirstTime',),('/Default',),'menu.ini'),
    'holiday':('Holiday Racer','Menu.exe',('/FirstTime',),('/Default',),'menu.ini'),
    'pmr':('Paris - Marseille Racing','data/menu.exe',('/FirstTime',),('/Default',),'menu.ini'),
    'europe':('Europe Racer','Menu/GameMenu.dat',('/FirstTime',),('/Default',),'GameMenu.ini'),
    'holiday-timing':('Holiday Racer','Menu.exe',('/FirstTime',),('/Default',),'menu.ini'),
    'pmr-timing':('Paris - Marseille Racing','data/menu.exe',('/FirstTime',),('/Default',),'menu.ini'),
    'europe-timing':('Europe Racer','Menu/GameMenu.dat',('/FirstTime',),('/Default',),'GameMenu.ini'),
}
for _name,_source in [('holiday-resolution','holiday-timing'),('pmr-resolution','pmr-timing'),('europe-resolution','europe-timing'),
                      ('a2ii-resolution','a2ii-timing'),('autobahn2-resolution','autobahn2-timing'),('london-resolution','london-timing')]:
    MENU_PROFILES[_name]=MENU_PROFILES[_source]


def read_menu_signal(path):
    section=''
    found=[]
    for line in Path(path).read_text(encoding='cp1252').splitlines():
        heading=re.match(r'\s*\[([^\]]+)\]',line)
        if heading: section=heading[1].strip().casefold()
        match=re.match(r'\s*EXITCODE\s*=\s*([+-]?\d+)\s*$',line,re.I)
        if section=='general' and match: found.append(int(match[1]))
    if len(found)!=1:
        raise ValueError('Expected one integer [GENERAL] EXITCODE in menu.ini.')
    return found[0]


def verify_copy(directory,profile):
    directory=Path(directory).resolve()
    from .installed import active_engine
    active=active_engine(directory,profile)
    if active is not None:return directory/MENU_PROFILES[profile][1],active
    if not any(directory.is_relative_to((root/'work').resolve()) for root in (ROOT,resources(ROOT))) and not directory.is_relative_to((resources(ROOT)/'patches').resolve()):
        raise ValueError('Menu experiments must use a copy inside this project work directory.')
    if profile not in MENU_PROFILES:
        raise ValueError('Unsupported menu-chain profile.')
    title,menu_relative,_,_,_=MENU_PROFILES[profile]
    engine=verified_engine(directory,profile)
    baseline=json.loads((resources(ROOT)/'analysis'/'baseline'/'manifest.json').read_text(encoding='utf-8'))
    game=next(g for g in baseline if g['title']==title)
    expected=next(f['sha256'] for f in game['files'] if f['path'].replace('\\','/').casefold()==menu_relative.casefold())
    menu=directory/menu_relative
    from .ingredients import read as read_ingredient
    contents=read_ingredient(menu)
    if hashlib.sha256(contents).hexdigest()!=expected:
        original=read_ingredient(resources(ROOT)/'analysis'/'baseline'/title/menu_relative)
        supported=(title=='A2 Racer 4' and any(contents==variant
                   for skip in (False,True)
                   for variant in (shell_safe_menu(original,skip_intro=skip),
                                   desktop_menu_bytes(shell_safe_menu(original,skip_intro=skip))))) or (title=='Holiday Racer' and contents==holiday_menu(original)) or (
                   title=='Europe Racer' and contents in (europe_menu(original),
                       __import__('davilex.europe_menu_language',fromlist=['expand']).expand(europe_menu(original))))
        if not supported:
            raise ValueError('Unsupported menu build.')
    return menu,engine


def prepare_media(directory,profile):
    if profile not in ('a2racer4-vram','a2racer4-resolution','holiday','holiday-timing','holiday-resolution'):
        return
    baseline=json.loads((resources(ROOT)/'analysis'/'baseline'/'manifest.json').read_text(encoding='utf-8'))
    title=MENU_PROFILES[profile][0]
    files=next(g['files'] for g in baseline if g['title']==title)
    prepare_local_intro(directory,files)


def cycle(directory,profile='a2ii-timing',nocd='D',skip_intro=False,runner=None,controller=False,english=False):
    backdrop = black_backdrop() if MENU_PROFILES[profile][0]=='A2 Racer 4' else nullcontext()
    with backdrop:
        return _cycle(directory,profile,nocd,skip_intro,runner,controller,english)


def _cycle(directory,profile,nocd,skip_intro,runner,controller,english):
    if not re.fullmatch('[A-Za-z]',nocd):
        raise ValueError('NOCD must be a single drive letter.')
    directory=Path(directory).resolve()
    menu,engine=verify_copy(directory,profile)
    prepare_media(menu.parent,profile)
    runner=runner or subprocess.run
    env=os.environ.copy()
    env['NOCD']=nocd.upper()
    log=menu.parent/'launcher-events.jsonl'
    _,_,first_arguments,return_arguments,result_file=MENU_PROFILES[profile]
    def execute(stage,path,arguments):
        # Recheck executable builds before every transition: a process could
        # remain open while another tool modifies a working copy.
        verify_copy(directory,profile)
        configuration_changes={}
        if stage=='engine' and profile.startswith('europe'):
            from .europe_tuning import ensure_valid_tuning
            repairs=ensure_valid_tuning(engine)
            if repairs:configuration_changes['tuning_profiles']=repairs
        if stage=='engine' and profile.endswith('-resolution'):
            from .resolution import select_resolution
            select_resolution(engine)
        if stage=='engine' and profile in ('pmr','pmr-timing'):
            configuration_changes=ensure_pmr_true_colour(directory)
        if stage=='engine' and controller:
            from .controller import select_controller
            select_controller(engine,profile)
        if stage=='engine' and english:
            from .translate import select_english_hud
            select_english_hud(engine)
        if stage=='menu' and result_file:
            signal_path=menu.parent/result_file
            # Clear an old Start signal so closing/crashing a later menu cannot
            # accidentally launch a race using a previous run's selection.
            signal_path.write_bytes(update_ini(signal_path.read_bytes(),{('GENERAL','EXITCODE'):255}))
        result=runner([str(path),*arguments],cwd=path.parent,env=env)
        event={'utc':datetime.now(timezone.utc).isoformat(),'stage':stage,
               'executable':path.name,'arguments':arguments,'exit_code':result.returncode}
        if configuration_changes:event['configuration_changes']=configuration_changes
        signal=result.returncode
        if stage=='menu':
            if result_file and result.returncode in (0,255):
                signal=read_menu_signal(menu.parent/result_file)
            event['menu_signal']=signal
            event['signal_source']=f'{result_file} [GENERAL] EXITCODE' if result_file else 'process exit code'
        with log.open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(event)+'\n')
        print(f'{stage} exit code: {result.returncode}',flush=True)
        return signal
    arguments=list(return_arguments if skip_intro else first_arguments)
    while True:
        result=execute('menu',menu,arguments)
        if result!=40:
            # The captured menu returns 255 when the user selects Quit.
            # Preserve that raw value in the log, but report a successful exit.
            return 0 if result in (0,255) else result
        result=execute('engine',engine,[])
        if result!=0:
            # Avoid restarting the menu over a crashed/failed engine and hiding
            # the failure. The original unmodified game data stays available.
            return result
        arguments=list(return_arguments)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--profile',choices=tuple(MENU_PROFILES),default='a2ii-timing')
    parser.add_argument('--nocd',default='D')
    parser.add_argument('--skip-intro',action='store_true')
    parser.add_argument('--english',action='store_true',help='Optional loose-text English pass; restore translated keys on exit.')
    parser.add_argument('--controller',action='store_true',help='Optional game-local Xidi analogue controller mode; restore original input on exit.')
    args=parser.parse_args()
    try:
        from contextlib import nullcontext
        from .translate import english_mode,restore
        from .controller import controller_mode,restore as restore_controller
        if not args.english:restore(args.directory)
        if not args.controller:restore_controller(args.directory)
        with english_mode(args.directory,args.profile) if args.english else nullcontext():
            with controller_mode(args.directory,args.profile) if args.controller else nullcontext():
                with preserve_display():
                    result=cycle(args.directory,args.profile,args.nocd,args.skip_intro,controller=args.controller,english=args.english)
        if result:
            parser.exit(1,f'Menu cycle stopped with exit code {result}. See launcher-events.jsonl in the working copy.\n')
    except (OSError,ValueError) as error:
        parser.exit(1,f'Error: {error}\n')


if __name__=='__main__':
    main()

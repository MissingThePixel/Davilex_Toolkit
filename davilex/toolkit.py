"""Shared game catalogue and verified launch path for the desktop toolkit."""
from contextlib import ExitStack
from pathlib import Path
import argparse
import csv
import io
import os
import subprocess
import sys
from .launch import ROOT
from .resolution import SOURCES
from .process import external_run

GAMES={
    'A2 Racer II':'a2ii-resolution',
    'A2 Racer IV':'a2racer4-resolution',
    'Autobahn Raser II':'autobahn2-resolution',
    'London Racer':'london-resolution',
    'Holiday Racer':'holiday-resolution',
    'Paris Marseille Racing':'pmr-resolution',
    'Europe Racer':'europe-resolution',
}
GAME_IMAGES={'spel.dat','spel.exe','menu.exe','menu.dat','gamemenu.dat'}


def check_idle():
    """Do not start another menu/engine over a running game."""
    result=external_run(['tasklist','/FO','CSV','/NH'],capture_output=True,text=True,
                          check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    active=[row[0] for row in csv.reader(io.StringIO(result.stdout))
            if row and row[0].casefold() in GAME_IMAGES]
    if active:raise ValueError('Exit the running game first: '+', '.join(active))


def working_copy(game,width=None,height=None):
    """Read-only lookup of historical experiments; the launcher does not use it."""
    profile=GAMES[game]
    folder,classic,short=SOURCES[profile]
    if width is None and height is None:return ROOT/'work'/folder,classic
    if width is None or height is None:raise ValueError('Supply both width and height.')
    # Validate dimensions before creating a directory or invoking a preparer.
    if not (640<=width<=8192 and 480<=height<=8192 and width*3>=height*4):
        raise ValueError('Use 640x480 to 8192x8192, with a 4:3 or wider aspect ratio.')
    directory=ROOT/f'work/{short}-resolution-{width}x{height}'
    if directory.exists() and not (directory/'native-resolution-manifest.json').is_file():
        raise ValueError(f'Incomplete resolution copy: {directory.name}. '
                         'Its verification manifest is missing; the existing files have been preserved.')
    if not directory.exists():
        raise ValueError('Historical resolution experiment not found. Launch the installed game through the toolkit.')
    return directory,profile


def run_game(game,width=None,height=None,english=False,controller=False,track=None,car=None,runner=None,install=None,renderer='ddrawcompat'):
    from .menu import verify_copy,cycle
    from .translate import english_mode,restore as restore_english,select_english_hud
    from .controller import controller_mode,restore as restore_controller,select_controller
    from .quickrace import race_mode,restore_race
    from .display_guard import preserve_display
    from .resolution import select_resolution
    if (track is None)!=(car is None):raise ValueError('Choose both a track and a car.')
    quick=track is not None
    from .languages import native_english
    english=english or native_english(game)
    check_idle()
    from .wine_overrides import restore as restore_wine,application_overrides
    restore_wine()
    print(f'Game: {game}; graphics backend: {renderer}; requested resolution: {width}x{height}',flush=True)
    from .installed import installed_game
    with installed_game(GAMES[game],width,height,install) as (directory,profile):
        _,engine=verify_copy(directory,profile)
        from .rendering import ensure_depth_precision
        ensure_depth_precision(engine,profile)
        restore_race(directory)
        if not english:restore_english(directory)
        if not controller:restore_controller(directory)
        child_runner=runner or external_run
        def runner(arguments,**options):
            # Wine's loader reads Unix environment, not SetEnvironmentVariableW.
            is_engine=Path(arguments[0]).resolve()==engine.resolve()
            selected='ddrawcompat' if renderer.startswith('dgvoodoo-') and not is_engine else renderer
            with application_overrides(arguments[0],selected,controller and is_engine):
                return child_runner(arguments,**options)
        if renderer in ('dgvoodoo-windowed','dgvoodoo-debug','dxwrapper'):
            original_runner=runner
            def windowed_runner(arguments,**options):
                executable=Path(arguments[0]).resolve()
                if renderer!='dxwrapper' and executable!=engine.resolve():return original_runner(arguments,**options)
                from .windowed import windowed_mode
                with windowed_mode(directory,profile,width,height,renderer=='dgvoodoo-debug',
                                   'dxwrapper' if renderer=='dxwrapper' else 'dgvoodoo',executable):
                    return original_runner(arguments,**options)
            runner=windowed_runner
        with ExitStack() as stack:
            from .rendering import graphics_backend
            stack.enter_context(graphics_backend(renderer,controller))
            if english:stack.enter_context(english_mode(directory,profile))
            if controller:stack.enter_context(controller_mode(directory,profile))
            stack.enter_context(preserve_display())
            if quick:
                stack.enter_context(race_mode(directory,track,car,profile))
                if profile.endswith('-resolution'):select_resolution(engine)
                if profile in ('pmr','pmr-timing'):
                    from .menu_media import ensure_pmr_true_colour
                    ensure_pmr_true_colour(directory)
                if english:select_english_hud(engine)
                if controller:select_controller(engine,profile)
                if profile.startswith('europe'):
                    from .europe_tuning import ensure_valid_tuning
                    ensure_valid_tuning(engine)
                env=os.environ.copy();env['NOCD']='D'
                return runner([str(engine)],cwd=engine.parent,env=env).returncode
            return cycle(directory,profile,controller=controller,english=english,runner=runner)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('game',choices=tuple(GAMES))
    parser.add_argument('--width',type=int);parser.add_argument('--height',type=int)
    parser.add_argument('--english',action='store_true');parser.add_argument('--controller',action='store_true')
    parser.add_argument('--renderer',choices=('ddrawcompat','wine','dgvoodoo-windowed','dgvoodoo-debug','dxwrapper'),default='ddrawcompat')
    parser.add_argument('--install',type=Path,help='Existing installation folder; defaults to the detected installation.')
    parser.add_argument('--restore-install',action='store_true',help='Restore original patched files, retaining unrelated INI settings.')
    parser.add_argument('--patch-only',action='store_true',help='Apply compatibility/resolution changes without starting a game.')
    parser.add_argument('--track',type=int);parser.add_argument('--car',type=int)
    parser.add_argument('--addon-image',help='Installed Europe add-on ID for a menu preview.')
    parser.add_argument('--image',type=Path,help='Screenshot to convert into the original menu preview.')
    parser.add_argument('--install-addon',help='Append an add-on to Europe Racer original Downloads menu.')
    args=parser.parse_args()
    try:
        if bool(args.addon_image)!=bool(args.image):raise ValueError('Choose both --addon-image and --image.')
        if args.restore_install or args.patch_only or args.install_addon or args.addon_image:
            from .installed import locate,restore_install,installed_game,installation_lock
            check_idle()
            if args.restore_install:
                directory=locate(GAMES[args.game],args.install)
                with installation_lock(directory):count=restore_install(directory)
                print(f'Restored {count} files in {directory}')
            else:
                with installed_game(GAMES[args.game],args.width,args.height,args.install) as (directory,_):
                    if args.install_addon:
                        if args.game!='Europe Racer':raise ValueError('This add-on adapter targets Europe Racer.')
                        from .addons import install as install_addon
                        install_addon(directory,args.install_addon)
                    if args.addon_image:
                        from .addons import install_preview
                        install_preview(directory,args.addon_image,args.image)
            return
        del args.restore_install,args.patch_only,args.install_addon,args.addon_image,args.image
        result=run_game(**vars(args))
        if result:parser.exit(1,f'Game stopped with exit code {result}.\n')
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        parser.exit(1,f'Error: {error}\n')


if __name__=='__main__':main()

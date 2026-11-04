"""Patch an existing installation; never clone a game for launch options.

Compatibility/resolution patches persist. Originals of changed files and a
write-ahead recovery journal live in the toolkit, outside the installation.
English, controller and quick-race options retain their per-run restoration.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path, PureWindowsPath
import hashlib
import json
import os
import uuid
import shutil
import threading

from .launch import ROOT, PROFILES
from .paths import resources

ACTIVE = ContextVar('installed_game', default=None)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def baseline(profile):
    title = PROFILES[profile][0]
    return next(g for g in json.loads((resources(ROOT)/'analysis/baseline/manifest.json').read_text()) if g['title']==title)


def locate(profile, selected=None):
    from .discovery import candidates
    record=baseline(profile)
    from .menu import MENU_PROFILES
    required=(PROFILES[profile][1],MENU_PROFILES[profile][1])
    locations=[Path(selected)] if selected else [*candidates(record['title'],ROOT),Path(record['source'])]
    directory=next((p.resolve() for p in locations if all((p/rel).is_file() for rel in required)),None)
    if directory is None:raise ValueError('Game installation not found. Use Locate to select its installation folder.')
    from .resolution import SOURCES
    protected={(resources(ROOT)/'work'/folder).resolve() for folder,_,_ in SOURCES.values()}
    if directory in protected or directory.is_relative_to((ROOT/'analysis').resolve()):
        raise ValueError('Choose an installed game, not the toolkit’s verified patch ingredients or captured originals.')
    for relative in (PROFILES[profile][1], MENU_PROFILES[profile][1]):
        if not (directory/relative).is_file():
            raise ValueError(f'Game installation not found at {directory}. Choose its installation folder.')
    return directory


def permitted(directory):
    directory = Path(directory).resolve()
    session = ACTIVE.get()
    return directory.is_relative_to((ROOT/'work').resolve()) or (session is not None and directory==session['directory'])


def active_engine(directory, profile):
    session = ACTIVE.get()
    if session is None or session['directory']!=Path(directory).resolve() or session['profile']!=profile:
        return None
    for path, expected in session['executables'].items():
        if digest(path.read_bytes())!=expected:
            raise ValueError(f'Installed executable changed during this session: {path}')
    return session['engine']


def _journal_path(directory):
    key=digest(str(Path(directory).resolve()).casefold().encode())[:20]
    return ROOT/'work/install-backups'/key


_RELOCATION_LOCK = threading.RLock()


def journal_folder(directory):
    """Reconnect moved installations only when backups and executable hashes agree."""
    directory = Path(directory).resolve()
    destination = _journal_path(directory)
    with _RELOCATION_LOCK:
        state_file = destination/'state.json'
        if (destination/'pending.json').exists():
            return destination
        if state_file.exists() and json.loads(state_file.read_text(encoding='utf-8')).get('files'):
            return destination
        matches = []
        for source_state in destination.parent.glob('*/state.json'):
            if source_state.parent == destination or (source_state.parent/'pending.json').exists():
                continue
            try:
                state = json.loads(source_state.read_text(encoding='utf-8'))
                if PureWindowsPath(state.get('directory','')).name.casefold() != directory.name.casefold():
                    continue
                files = state.get('files',{})
                executable_count = 0
                for relative, item in files.items():
                    target = safe_target(directory,relative)
                    original = safe_target(source_state.parent/'original',relative)
                    expected = item.get('original_sha256')
                    if expected and (not original.is_file() or digest(original.read_bytes()) != expected):
                        raise ValueError('Invalid relocation backup')
                    if target.suffix.casefold() in ('.exe','.dat'):
                        executable_count += 1
                        if not target.is_file() or digest(target.read_bytes()) not in (
                                expected,item.get('patched_sha256')):
                            raise ValueError('Executable does not match relocation history')
                    # Edited INIs are legitimate, but restoration snapshots must verify.
                    if target.suffix.casefold()=='.ini' and item.get('patched_sha256'):
                        snapshot=source_state.parent/'patched'/item['patched_sha256']
                        if not snapshot.is_file() or digest(snapshot.read_bytes())!=item['patched_sha256']:
                            raise ValueError('Invalid relocation configuration snapshot')
                if files and executable_count:
                    matches.append((source_state.parent,state))
            except (OSError,ValueError,KeyError,TypeError):
                continue
        if not matches:
            return destination
        signatures={json.dumps(state['files'],sort_keys=True) for _,state in matches}
        if len(signatures)!=1:
            raise ValueError('Multiple different relocation records match this game; originals preserved.')
        source,state=matches[0]
        staging=destination.with_name('relocation-'+uuid.uuid4().hex)
        try:
            shutil.copytree(source,staging,ignore=shutil.ignore_patterns('session.lock'))
            state['directory']=str(directory)
            write_json(staging/'state.json',state)
            if destination.exists():
                destination.rename(destination.with_name(destination.name+'.before-relocation-'+uuid.uuid4().hex))
            staging.rename(destination)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        print(f'Reconnected verified patch history for {directory.name}.',flush=True)
        return destination


def safe_target(directory, relative):
    if Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('Invalid relative patch path.')
    target=(directory/relative).resolve()
    if not target.is_relative_to(directory):
        raise ValueError('Patch path escapes the installation.')
    return target


def replace_file(target, data):
    temporary=target.with_name('.davilex-patch-'+uuid.uuid4().hex+'.tmp')
    try:
        with temporary.open('xb') as stream:stream.write(data)
        os.replace(temporary,target)
    finally:temporary.unlink(missing_ok=True)


def write_json(path, value):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    os.replace(temporary,path)


def discard_rollback(journal):
    """Keep original backups; discard completed transaction scratch files."""
    journal=Path(journal).resolve();scratch=journal/'rollback'
    if (journal/'pending.json').exists():return
    if scratch.is_dir() and scratch.resolve().is_relative_to(journal) and journal.is_relative_to((ROOT/'work').resolve()):
        shutil.rmtree(scratch)


def edit_ini(data, changes):
    """Retain formatting and add explicitly requested absent configuration keys."""
    from .translate import ini_lines
    from .quickrace import update_ini
    import re
    present={(s,k) for _,s,k,_,_ in ini_lines(data)}
    existing={p:v for p,v in changes.items() if (p[0].casefold(),p[1].casefold()) in present}
    result=update_ini(data,existing)
    for (section,key),value in changes.items():
        if (section.casefold(),key.casefold()) in present:continue
        lines=result.splitlines(keepends=True)
        heading=next((i for i,line in enumerate(lines) if re.fullmatch(
            rb'\s*\['+re.escape(section.encode('ascii'))+rb'\]\s*',line,re.I)),None)
        addition=key.encode('ascii')+b'='+str(value).encode('ascii')+b'\r\n'
        if heading is None:
            result+=b'\r\n['+section.encode('ascii')+b']\r\n'+addition
        else:
            lines.insert(heading+1,addition);result=b''.join(lines)
    return result


def commit(directory, payload):
    """Back up only modified files; journal before the first installation write.

    A failed application rolls back that application. A killed process leaves
    pending.json for recovery on the next launch, before preparing another plan.
    """
    directory=Path(directory).resolve(); journal=journal_folder(directory)
    journal.mkdir(parents=True,exist_ok=True)
    recover(directory)
    state_path=journal/'state.json'
    state=json.loads(state_path.read_text()) if state_path.exists() else {'directory':str(directory),'files':{}}
    changes=[]
    for relative, after in payload.items():
        target=safe_target(directory,relative)
        before=target.read_bytes() if target.exists() else None
        if before==after:continue
        name=str(Path(relative))
        if name not in state['files']:
            backup=journal/'original'/name
            if before is not None:
                backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(before)
            state['files'][name]={'original_sha256':digest(before) if before is not None else None}
        rollback=journal/'rollback'/name
        if before is not None:
            rollback.parent.mkdir(parents=True,exist_ok=True);rollback.write_bytes(before)
        changes.append({'file':name,'before':digest(before) if before is not None else None,'after':digest(after)})
        state['files'][name]['patched_sha256']=digest(after)
        if target.suffix.casefold()=='.ini':
            snapshot=journal/'patched'/digest(after)
            snapshot.parent.mkdir(exist_ok=True);snapshot.write_bytes(after)
    write_json(journal/'pending.json',{'directory':str(directory),'changes':changes})
    try:
        for item in changes:
            target=safe_target(directory,item['file']);target.parent.mkdir(parents=True,exist_ok=True)
            replace_file(target,payload[Path(item['file'])])
        write_json(state_path,state)
        (journal/'pending.json').unlink()
        discard_rollback(journal)
    except BaseException:
        recover(directory)
        raise
    return len(changes)


def recover(directory):
    directory=Path(directory).resolve();journal=journal_folder(directory);pending=journal/'pending.json'
    if not pending.exists():
        discard_rollback(journal);return
    record=json.loads(pending.read_text())
    if Path(record['directory']).resolve()!=directory:raise ValueError('Recovery installation mismatch.')
    for item in reversed(record['changes']):
        target=safe_target(directory,item['file'])
        current=digest(target.read_bytes()) if target.exists() else None
        if current==item['before']:continue
        if current!=item['after']:
            raise ValueError(f'File changed after interrupted patch; preserving it: {target}')
        if item['before'] is None:target.unlink()
        else:
            original=safe_target(journal/'rollback',item['file']).read_bytes()
            if digest(original)!=item['before']:raise ValueError('Recovery backup hash mismatch.')
            replace_file(target,original)
    pending.unlink()
    discard_rollback(journal)


def undo_ini(current, original, patched):
    """Undo our changed keys, retaining progress/settings subsequently written."""
    from .translate import ini_lines
    import re
    before={(s,k,n):m[4].strip() for _,s,k,n,m in ini_lines(original)}
    after={(s,k,n):m[4].strip() for _,s,k,n,m in ini_lines(patched)}
    if not before and not after:
        raise ValueError('Renderer configuration was edited; preserving it for manual restoration.')
    lines=current.decode('cp1252').splitlines(keepends=True)
    for i,s,k,n,m in ini_lines(current):
        key=(s,k,n)
        if before.get(key)==after.get(key) or m[4].strip()!=after.get(key):continue
        if key not in before:lines[i]=''
        else:
            trailing=re.search(r'[ \t]*$',m[4])[0]
            lines[i]=m[1]+m[2]+m[3]+before[key]+trailing+(m[5] or '')
    return ''.join(lines).encode('cp1252')


def restore_install(directory):
    """Restore backed-up files while retaining unrelated game-written INI keys."""
    directory=Path(directory).resolve();recover(directory)
    journal=journal_folder(directory);state_path=journal/'state.json'
    if not state_path.exists():return 0
    state=json.loads(state_path.read_text());payload={};remove=[]
    if Path(state['directory']).resolve()!=directory:raise ValueError('Backup installation mismatch.')
    # Validate the complete restoration before changing anything.
    for relative,item in state['files'].items():
        target=safe_target(directory,relative)
        current=target.read_bytes() if target.exists() else None
        current_hash=digest(current) if current is not None else None
        if current_hash==item['original_sha256']:continue
        original=None
        if item['original_sha256'] is not None:
            original=safe_target(journal/'original',relative).read_bytes()
            if digest(original)!=item['original_sha256']:raise ValueError('Original backup hash mismatch.')
        if current_hash!=item['patched_sha256']:
            if original is None or current is None or target.suffix.casefold()!='.ini':
                raise ValueError(f'File modified since patching; preserving {target}')
            patched=(journal/'patched'/item['patched_sha256']).read_bytes()
            if digest(patched)!=item['patched_sha256']:raise ValueError('Patched configuration backup hash mismatch.')
            original=undo_ini(current,original,patched)
        if original is None:remove.append(target)
        else:payload[Path(relative)]=original
    for relative,data in payload.items():replace_file(directory/relative,data)
    for target in remove:target.unlink()
    state_path.rename(journal/('restored-'+uuid.uuid4().hex+'.json'))
    return len(payload)+len(remove)


def plan(directory, profile, width=None, height=None):
    from .ingredients import selected_install
    with selected_install(directory,profile):
        return _plan(directory,profile,width,height)


def _plan(directory, profile, width=None, height=None):
    """Build a small patch payload from verified compatibility ingredients."""
    from .launch import verified_engine
    from .menu import verify_copy, MENU_PROFILES
    from .resolution import SOURCES, patch_engine
    from .hud_layout import edge_layout
    from .quickrace import update_ini
    from .translate import ini_lines
    from .menu_media import intro_search_path
    directory=Path(directory).resolve()
    from .paths import patch_source
    from .ingredients import read as read_ingredient
    folder, classic, _=SOURCES[profile]; source=patch_source(profile,resources(ROOT))
    source_menu, source_engine=verify_copy(source,classic)
    game=baseline(profile); known={Path(f['path']):f['sha256'] for f in game['files']}
    state_path=journal_folder(directory)/'state.json'
    state=json.loads(state_path.read_text())['files'] if state_path.exists() else {}
    payload={}
    from .recognition import dimensions,engine_matches
    previous_dimensions=dimensions((directory/source_engine.relative_to(source)).read_bytes(),profile)

    def add(relative, data, *, configuration=False):
        relative=Path(relative);target=safe_target(directory,relative)
        if target.exists() and not configuration:
            current=digest(target.read_bytes())
            allowed={known.get(relative),digest(data),state.get(str(relative),{}).get('patched_sha256')}
            if relative==source_menu.relative_to(source):allowed.add(digest(read_ingredient(source_menu)))
            if current not in allowed and relative==source_engine.relative_to(source):
                if engine_matches(target.read_bytes(),read_ingredient(source_engine),profile):allowed.add(current)
            if current not in allowed and relative.name.casefold().startswith('overlay') and previous_dimensions:
                template=source/relative
                if template.is_file():
                    previous,_=edge_layout(template.read_bytes(),profile,*previous_dimensions)
                    allowed.add(digest(previous))
            # An interrupted renderer cleanup can outlive a toolkit replacement
            # (and its journals). Recognise only the exact stubs we ship. commit
            # still backs up the old bytes before installing the default renderer.
            if relative.name.casefold()=='ddraw.dll':
                from .windowed import DXWRAPPER_STUB_HASH,HASHES,DEBUG_HASHES
                allowed.update((DXWRAPPER_STUB_HASH,HASHES['ddraw.dll'],DEBUG_HASHES['ddraw.dll']))
            if current not in allowed:
                raise ValueError(f'Unrecognised or modified file; preserving {target} (SHA-256: {current})')
        payload[relative]=data

    def edit(relative, changes):
        relative=Path(relative)
        data=payload.get(relative,(directory/relative).read_bytes())
        add(relative,update_ini(data,changes),configuration=True)

    engine_rel=source_engine.relative_to(source);menu_rel=source_menu.relative_to(source)
    engine_data=read_ingredient(source_engine)
    if width is not None or height is not None:
        if width is None or height is None:raise ValueError('Supply both width and height.')
        engine_data,_=patch_engine(engine_data,width,height,profile)
    if profile.startswith('europe'):
        from .europe_tracks import expand
        engine_data=expand(engine_data)
        from .europe_car_capacity import expand as expand_cars,CAPACITY as CAR_CAPACITY
        engine_data=expand_cars(engine_data)
        from .europe_animation import patch as repair_animated_collision
        engine_data=repair_animated_collision(engine_data)
        # The original dynamics loader opens every record up to its bound.
        # Populate newly reserved slots with a verified authored profile until
        # a converter installs their own record; existing add-ons are retained.
        seed=directory/'Game/Vdyns/VDYNS0.DAT'
        if digest(seed.read_bytes())!=known.get(Path('Game/Vdyns/VDYNS0.DAT')):
            raise ValueError('Unknown reserved vehicle handling seed')
        for car_id in range(100,CAR_CAPACITY):
            relative=Path(f'Game/Vdyns/VDYNS{car_id}.DAT')
            if not (directory/relative).exists():add(relative,seed.read_bytes())
    menu_data=read_ingredient(source_menu)
    if profile.startswith('europe'):
        from .europe_menu_language import expand as expand_language
        menu_data=expand_language(menu_data)
        from .europe_menu_language import KEYS
        language_rel=Path('Menu/Language.ini');language=(directory/language_rel).read_bytes()
        entries={(s,k)for _,s,k,_,_ in ini_lines(language)}
        language_sections={s for s,k in entries if s.startswith('text_')}
        add(language_rel,edit_ini(language,{(s,k):'Extra car'for s in language_sections for k in KEYS if (s,k.casefold())not in entries}),configuration=True)
    if game['title']=='A2 Racer 4':
        from .menu_media import desktop_menu_bytes
        # Transform the verified ingredient; the migration recognizer separately
        # accepts prior shell-safe versions and this desktop version.
        try:menu_data=desktop_menu_bytes(menu_data)
        except ValueError:
            from .menu_media import shell_safe_menu
            original=read_ingredient(resources(ROOT)/'analysis/baseline/A2 Racer 4/menu.exe')
            if menu_data not in [desktop_menu_bytes(shell_safe_menu(original,skip)) for skip in (False,True)]:
                raise
    add(engine_rel,engine_data);add(menu_rel,menu_data)
    common_renderer=resources(ROOT)/'wrappers/ddrawcompat/ddraw.dll'
    if common_renderer.is_file():
        for parent in {engine_rel.parent,menu_rel.parent}:add(parent/'ddraw.dll',common_renderer.read_bytes())
    # Only the renderer and its configuration are deployed, never unrelated
    # test outputs, saved races, player profiles or complete data directories.
    for parent in {source_engine.parent,source_menu.parent}:
        for path in parent.iterdir():
            if path.name.casefold()=='ddraw.dll' or (path.name.casefold().startswith('ddrawcompat') and path.suffix.lower()=='.ini'):
                if path.name.casefold()!='ddrawcompat.ini':add(path.relative_to(source),path.read_bytes())
    for path in source.rglob('overlay*.ini'):
        rel=path.relative_to(source)
        if any(part.startswith('.') for part in rel.parts):continue
        data=path.read_bytes()
        if width is not None:data,_=edge_layout(data,profile,width,height)
        add(rel,data)
    engine_dir=engine_rel.parent
    from .rendering import depth_configuration
    depth_rel=engine_dir/'DDrawCompat.ini'
    depth_path=directory/depth_rel
    original_depth=depth_path.read_bytes() if depth_path.exists() else b''
    add(depth_rel,depth_configuration(original_depth),configuration=True)
    if width is not None:
        rel=engine_dir/('Ini/game.ini' if profile.startswith('europe') else 'raser.ini')
        edit(rel,{('OPTIONS' if profile.startswith('europe') else 'PROGRAM','RESOLUTION'):3})
    # Carry only compatibility configuration, not the experimental copy's race
    # selections, volumes, controller mappings, progress, or player settings.
    config=engine_dir/('Ini/game.ini' if profile.startswith('europe') else 'game.ini')
    values={(s,k):m[4].strip() for _,s,k,_,m in ini_lines((source/config).read_bytes())}
    fixes={pair:values[pair] for pair in [('gfx options','custom_texture_memory'),('gfx options','available_texture_memory')]
           if pair in values}
    if fixes:edit(config,fixes)
    if profile.startswith(('a2racer4','holiday')):
        edit(menu_rel.parent/'menu.ini',{('GENERAL','INTROAVI'):intro_search_path(directory/menu_rel.parent/'intro1.mpg')})
    if profile.startswith('europe'):
        from .geometry_fixes import europe_payload
        for relative,data in europe_payload(directory).items():
            add(relative,data,configuration=relative.suffix.casefold()=='.ini')
        original=(directory/menu_rel.parent/'GameMenu.ini').read_bytes()
        desired={(s,k):m[4].strip() for _,s,k,_,m in ini_lines((source/menu_rel.parent/'GameMenu.ini').read_bytes())}
        changes={pair:value for pair,value in desired.items() if pair[0] in ('movies','fs_firsttime') or
                 (pair[0]=='general' and pair[1] in ('nocd','resource0','resource1','resource2','resource3','gameinterface'))}
        changes['general','leaderavi']=intro_search_path(directory/menu_rel.parent/'Media/Intro.avi')
        add(menu_rel.parent/'GameMenu.ini',edit_ini(original,changes),configuration=True)
        # The installed edition lacks these CD assets. Add only missing menu
        # resources once; existing assets are never replaced or duplicated.
        for stem in ('Graphics','Music','Voices','Extra'):
            for suffix in ('.IMG','.IND','.CHK'):
                rel=menu_rel.parent/(stem+suffix)
                if not (directory/rel).exists():
                    asset=source/rel
                    if not asset.exists():asset=ROOT/'games'/game['title']/rel
                    add(rel,asset.read_bytes())
        media_root=source
        if not (media_root/menu_rel.parent/'Media').is_dir():media_root=ROOT/'games'/game['title']
        for path in (media_root/menu_rel.parent/'Media').glob('*'):
            rel=path.relative_to(media_root)
            if path.is_file() and not (directory/rel).exists():add(rel,path.read_bytes())
    selected_profile=profile if width is not None else classic
    return payload,selected_profile,engine_rel,menu_rel


@contextmanager
def installed_game(profile,width=None,height=None,selected=None):
    directory=locate(profile,selected)
    with installation_lock(directory):
        recover(directory)
        recovery_token=ACTIVE.set({'directory':directory,'profile':None,'engine':None,'executables':{}})
        try:
            from .translate import restore as restore_english
            from .controller import restore as restore_controller
            from .quickrace import restore_race
            from .windowed import restore as restore_renderer
            restore_renderer(directory);restore_race(directory);restore_english(directory);restore_controller(directory)
        finally:ACTIVE.reset(recovery_token)
        payload,selected_profile,engine_rel,menu_rel=plan(directory,profile,width,height)
        count=commit(directory,payload)
        print(f'Patched installation: {directory} ({count} changed files; no game copy created)',flush=True)
        session={'directory':directory,'profile':selected_profile,'engine':directory/engine_rel,
                 'executables':{directory/rel:digest(payload[rel]) for rel in (engine_rel,menu_rel)}}
        token=ACTIVE.set(session)
        try:
            if profile.startswith('europe') and (directory/'Game/davilex-addons.json').exists():
                from .addons import refresh_previews,withdraw_retired_tracks
                withdraw_retired_tracks(directory)
                refresh_previews(directory)
            yield directory,selected_profile
        finally:ACTIVE.reset(token)


@contextmanager
def installation_lock(directory):
    """OS-owned lock is automatically released even if the toolkit is killed."""
    journal=journal_folder(directory);journal.mkdir(parents=True,exist_ok=True)
    with (journal/'session.lock').open('a+b') as stream:
        if os.name=='nt':
            import msvcrt
            stream.seek(0);stream.write(b'0');stream.flush();stream.seek(0)
            try:msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as error:raise ValueError('This installation already has an active toolkit session.') from error
        try:yield
        finally:
            if os.name=='nt':
                stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)

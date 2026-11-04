"""Move known 3D HUD groups to widescreen edges; keep central prompts centred."""
import re
from .quickrace import update_ini
from .translate import ini_lines


def edge_layout(original, profile, width, height):
    margin=(width*480/height-640)/2
    if margin<0:raise ValueError('Narrower HUD layouts are not supported yet.')
    rows=list(ini_lines(original))
    sections={}
    for _,section,key,_,match in rows:
        sections.setdefault(section,{})[key]=match[4].strip()
    groups={}
    if profile in ('holiday-resolution','pmr-resolution'):
        groups={'speed':1}
        if profile=='holiday-resolution':groups.update(numbers=1)
    elif profile=='a2racer4-resolution' or (profile=='europe-resolution' and 'communicator' in sections):
        groups={'speedometer':1,'communicator':-1,'portraits':-1}
    elif profile=='europe-resolution':
        groups={'speedometer':1,'timeblock':1,'lapblock':-1,'timeline':-1}
    edits={};report=[]
    for _,section,key,_,match in rows:
        if (profile=='holiday-resolution' and margin and section=='ovl_player_outline'
                and key=='parent' and match[4].strip().casefold()=='speed'):
            # The portrait manager copies its player's local position into
            # this moving outline every frame (46e168..46e18a). The two nodes
            # must share a parent; a static Position correction is overwritten.
            edits[(section,key)]='Portraits'
            report.append({'section':section,'key':key,'before':match[4].strip(),'after':'Portraits'})
        if key!='position':continue
        text=match[4].strip();parts=re.split(r'[,;]',text)
        if len(parts)<2:continue
        x=float(parts[0]);parent=sections[section].get('parent','').casefold()
        shift=groups.get(section,0)
        if section=='ovl_place_arrow' and parent=='speed':shift=-1 # counter parent movement
        if section=='ovl_player_outline' and parent=='portraits' and groups.get('portraits')==-1 and x>400:shift=2 # parent moves left
        if parent=='screen' and section not in groups:
            # Declared root HUD elements only. Pause/results, countdown and
            # turn arrows stay centred even when their initial X is zero.
            if section.startswith('ovl_portraits_'):shift=-1
            elif section in ('ovl_progress_bar',) and x>400:shift=1
            elif section in ('string_race_time_value','string_cur_lap','string_cur_pos') and x>400:shift=1
            elif profile=='pmr-resolution' and section=='string_speed':shift=-1
            elif profile=='europe-resolution' and section in ('string_damage','string_turbo','ovl_damage_background','ovl_damage_meter','ovl_turbo_background','ovl_turbo_meter'):shift=-1
        if profile=='pmr-resolution' and parent=='numbers' and x>400:shift=1
        if not shift or not margin:continue
        inset=16 if shift>0 and (section in ('numbers','timeblock') or section.startswith('string_')) else 0
        parts[0]=format(x+shift*margin-inset,'.9g')
        separator=';' if ';' in text else ','
        value=separator.join(parts)
        edits[(section,'position')]=value
        report.append({'section':section,'before':text,'after':value})
    return update_ini(original,edits),report


def prepare_layout(directory,profile,width,height):
    import hashlib
    import json
    from .resolution import SOURCES
    from .launch import ROOT
    from .paths import resources
    directory=directory.resolve()
    from .paths import patch_source
    source=patch_source(profile,resources(ROOT))
    manifest=directory/'hud-layout-manifest.json'
    previous={r['file']:r for r in json.loads(manifest.read_text())} if manifest.exists() else {}
    report=[]
    for path in source.rglob('overlay*.ini'):
        relative=path.relative_to(source)
        # Translation recovery contains historical overlay copies. They are
        # not game assets and are deliberately absent from newly staged games.
        if any(part in ('.english-restore','.controller-restore') for part in relative.parts):continue
        target=directory/relative
        original=path.read_bytes();changed,edits=edge_layout(original,profile,width,height)
        if not edits:continue
        # Re-running preparation is idempotent, but do not overwrite custom edits.
        current=target.read_bytes();old=previous.get(str(relative),{})
        recorded=(old.get('source_sha256')==hashlib.sha256(original).hexdigest() and
                  old.get('patched_sha256')==hashlib.sha256(current).hexdigest())
        if current not in (original,changed) and not recorded:
            raise ValueError(f'Custom overlay edits found; preserving {target}.')
        target.write_bytes(changed)
        report.append({'file':str(relative),'source_sha256':hashlib.sha256(original).hexdigest(),
                       'patched_sha256':hashlib.sha256(changed).hexdigest(),'edits':edits})
    manifest.write_text(json.dumps(report,indent=2)+'\n')
    return report

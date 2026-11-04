"""Optional loose-text English pass; images and executable bytes are untouched."""
from contextlib import contextmanager
from pathlib import Path
import argparse
import hashlib
import json
import re
from .launch import ROOT
from .paths import resources

TOKEN=re.compile(r'%(?:\d+\$)?[-+#0 ]*\d*(?:\.\d+)?(?:[hlL])?[diuoxXfFeEgGcs%]')
UI_SECTIONS={'menustrings','controlnames','controlkeys','ordinalwords','ordinalnumbers','errorstrings'}
HUD_ENGLISH={'GEBLITZT':'SPEED CAMERA','GETANKT':'REFUELLED','PRICE MONEY':'PRIZE MONEY',
             'EERSTE WAARSCHUWING':'FIRST WARNING','TWEEDE WAARSCHUWING':'SECOND WARNING',
             'SNELHEID':'SPEED','SCHADE':'DAMAGE'}
OVERLAY_ENGLISH={"DRUK 'SPATIE' OM VERDER TE GAAN":"PRESS SPACE TO CONTINUE",
                 'Druk een toets':'Press a key','GEARRESTEERD':'ARRESTED',
                 'JE TIJD IS OM':'TIME IS UP','Pauze':'Pause','Wilt u echt':'Really quit',
                 # Keep the actual confirmation keys; translating a label must
                 # not promise a different keyboard binding in the engine.
                 'stoppen!? (J/N)':'this race? (J/N)'}


def english_hud_value(value):
    if value in HUD_ENGLISH:return HUD_ENGLISH[value]
    if value.startswith('STRA') and value.endswith('ENWACHT'):return 'ROADSIDE ASSISTANCE'
    for old,new in [('STRAFE:', 'FINE:'),('KOSTEN:', 'COST:'),('ONKWETSBAAR','INVINCIBLE'),('REPARATIE','REPAIR')]:
        value=value.replace(old,new)
    return value


def select_english_hud(engine):
    """Menus can rewrite settings; reassert only the temporary language choice."""
    from .quickrace import update_ini
    candidates=[p for p in engine.parent.iterdir() if p.name.casefold()=='language.ini']
    ini=next((p for p in engine.parent.iterdir() if p.is_dir() and p.name.casefold()=='ini'),None)
    if ini:candidates.extend(p for p in ini.iterdir() if p.name.casefold()=='language.ini')
    for path in candidates:
        original=path.read_bytes()
        if any(s in {'engels','english'} for _,s,_,_,_ in ini_lines(original)):
            path.write_bytes(update_ini(original,{('SETTINGS','LANGUAGE'):1}))
A2_MENU={1:'Display - Advanced',2:'Download this track from the Internet.',3:'Texture detail',
    4:"Are you sure you want to delete player '%s'?",5:'A2 Racer 4 Menu',6:"The key '%s' is already in use!",
    7:'Unlock this track by qualifying for it in the Tour.',8:'Escape',9:'Welcome %s!',
    10:'Winner bonus: %d Euro',13:'Price: %s Euro.',14:'%s place',
    21:"Start the game with 'A2Racer4.exe'.",22:'General',23:'Problems'}
STORIES={
    'Autobahn Raser II':"AUTOBAHN RASER: THE STORY\nFor years, the notorious Autobahn Racers have held illegal races throughout Germany. Now they are gathering for another season of unrestricted racing.\nThe championship spans the seasons, from snowy Dortmund at night to the grand finale in Berlin in October.\nAfter a long search, you finally contact the organisation. At a meeting in a hidden garage, you are allowed to prove yourself as a newcomer in League A. Can you become champion of every class and king of the racers?\n",
    'Paris - Marseille Racing':"PARIS-MARSEILLE RACING: THE STORY\nFor years, the Paris-Marseille League has held illegal races on French motorways. These races have given you the chance to show your talent, and people have noticed.\nMore illegal races are about to take place on and around some of France's most dangerous motorways. You have been challenged to enter! Qualify through all three leagues and prove yourself: only first place counts. Do you have the courage to accept?\n"}
CREDIT_HEADINGS={
 'PRODUKTIDEE':'ORIGINAL IDEA','PROJEKTLEITER':'PROJECT LEADER','PRODUKTDESIGN':'PRODUCT DESIGN',
 'TECHNISCHE LEITUNG':'TECHNICAL LEAD','GRAFISCHE LEITUNG':'ART LEAD','SPIELPROGRAMMIERUNG':'GAME PROGRAMMING',
 'GRAFIK UND DESIGN':'ART AND DESIGN','DER STRECKEN':'OF THE TRACKS','LEVEL-EDITOR':'LEVEL EDITOR',
 'PROGRAMMIERUNG':'PROGRAMMING','DES SPIELMENÜS':'OF THE GAME MENU','GRAFIK DES':'ART FOR THE',
 'SPIELMENÜS':'GAME MENU','MUSIK UND SOUNDEFFEKTE':'MUSIC AND SOUND EFFECTS',
 'QUALITÄTSKONTROLLE':'QUALITY ASSURANCE','SPEZIELLER DANK:':'SPECIAL THANKS:',
 'CONCEPTION ET REALISATION':'DESIGN AND DEVELOPMENT','SUR UNE IDEE DE':'ORIGINAL IDEA',
 'CHEF DE PROJECT':'PROJECT LEAD','CONCEPTION':'DESIGN','RESPONSABLE TECHNIQUE':'TECHNICAL LEAD',
 'RESPONSABLE GRAPHIQUE':'ART LEAD','PROGRAMMATION':'PROGRAMMING','GRAPHISME ET CONCEPTION':'ART AND DESIGN',
 'PROGRAMMATION MENUS JEU':'GAME MENU PROGRAMMING','GRAPHISME MENUS JEU':'GAME MENU ART',
 'MUSIQUE ET EFFETS SONORES':'MUSIC AND SOUND EFFECTS','ASSURANCE QUALITlÉ':'QUALITY ASSURANCE'}


def help_text(original,reference,title):
    def blocks(text):
        matches=list(re.finditer(r'^\[([^\r\n]+)\][ \t]*\r?$',text,re.M))
        return [(m[1],text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)]) for i,m in enumerate(matches)]
    english={name.casefold():body for name,body in blocks(reference.decode('cp1252'))}
    result=[]
    for name,body in blocks(original.decode('cp1252')):
        section=name.casefold()
        if section=='helponstory':body='\r\n\r\n'+STORIES[title].replace('\n','\r\n')+'\r\n'
        elif section=='credits':
            body=''.join(CREDIT_HEADINGS.get(line.strip(),line.rstrip('\r\n'))+ ('\r\n' if line.endswith('\n') else '') for line in body.splitlines(keepends=True))
        elif section in english:body=english[section]
        result.append('['+name+']'+body)
    return ''.join(result).encode('cp1252')


def ini_lines(data):
    section='';seen={}
    for i,line in enumerate(data.decode('cp1252').splitlines(keepends=True)):
        heading=re.match(r'\s*\[([^]]+)\]',line)
        if heading:section=heading[1].strip().casefold()
        match=re.match(r'([ \t]*)([^;=\r\n]+?)([ \t]*=[ \t]*)([^\r\n]*)(\r?\n)?$',line)
        if match:
            key=match[2].strip().casefold();pair=(section,key)
            occurrence=seen.get(pair,0);seen[pair]=occurrence+1
            yield i,section,key,occurrence,match


def references(title):
    result={}
    for path in (resources(ROOT)/'analysis/baseline'/title).rglob('*.ini'):
        for _,section,key,_,match in ini_lines(path.read_bytes()):
            result[(path.name.casefold(),section,key)]=match[4].strip()
    return result


def patches(directory,profile):
    from .menu import MENU_PROFILES,verify_copy
    directory=Path(directory).resolve();verify_copy(directory,profile)
    title=MENU_PROFILES[profile][0]
    source_title='Holiday Racer' if title=='A2 Racer 4' else 'London Racer'
    reference=references(source_title)
    manual=json.loads((resources(ROOT)/'davilex/english_strings.json').read_text(encoding='utf-8'))
    result=[];unhandled=[];counts={}
    for path in directory.rglob('*'):
        if any(p in path.parts for p in ('.english-restore','.controller-restore')) or path.suffix.casefold()!='.ini':continue
        overlay=path.name.casefold().startswith('overlay')
        if title=='Europe Racer' and not overlay:continue
        if title in ('London Racer','Holiday Racer') and path.name.casefold()!='language.ini' and not overlay:continue
        original=path.read_bytes();lines=original.decode('cp1252').splitlines(keepends=True)
        if path.name.casefold()=='menuhelp.ini' and title in STORIES:
            reference_path=next(p for p in (resources(ROOT)/'analysis/baseline/London Racer').rglob('*') if p.name.casefold()=='menuhelp.ini')
            changed=help_text(original,reference_path.read_bytes(),title)
            if changed!=original:
                result.append({'path':path,'original':original,'patched':changed,'edits':[],'whole_file':True})
                counts[str(path.relative_to(directory))]='Help topics, story and credit headings'
            continue
        edits=[]
        for index,section,key,occurrence,match in ini_lines(original):
            name=path.name.casefold();old=match[4].strip();new=None;source=None
            if overlay and key=='text':
                new=OVERLAY_ENGLISH.get(old)
                source='Reviewed English overlay label; artwork and bindings preserved'
            elif name=='language.ini' and section=='settings' and key=='language':
                # All six older games ship ENGELS; Europe's engine ships ENGLISH.
                sections={s for _,s,_,_,_ in ini_lines(original)}
                if sections & {'engels','english'}:new='1';source='Bundled English language table'
            elif name=='language.ini' and section in {'engels','english'}:
                new=english_hud_value(old);source='Reviewed correction of unfinished bundled English HUD text'
                if key=='32' and 'M25' in old.upper():new=f'Unable to find {title.replace("A2II","A2 Racer II")} CD-ROM.'
            elif name=='menu.ini' and section in UI_SECTIONS and not key.startswith('*'):
                if section=='menustrings':
                    if title=='A2 Racer 4':new=A2_MENU.get(int(key)) if key.isdigit() else None
                    elif title in ('Autobahn Raser II','Paris - Marseille Racing') and key.isdigit() and int(key) not in (44,45,46,82,83,84):
                        new=reference.get((name,section,key))
                        if key=='38' and title=='Autobahn Raser II':new='Start the game using the Full Game launcher.'
                        if key=='80':new='Start the game using the Full Game launcher.'
                        if key=='27' and title=='Paris - Marseille Racing':new='%s is locked. Finish first in %s to unlock %s.'
                elif section=='errorstrings':new=manual.get(old)
                else:new=reference.get((name,section,key))
                source='English UI reference / reviewed text'
            elif name=='menucaps.ini' and key.endswith(('.caption','.hint')):
                new=manual.get(old,reference.get((name,section,key)))
                source='English UI reference / reviewed text'
            if new is None:
                if old and ((name=='menucaps.ini' and key.endswith(('.caption','.hint'))) or (name=='menu.ini' and section in UI_SECTIONS)):
                    unhandled.append({'file':str(path.relative_to(directory)),'section':section,'key':key,'text':old})
                continue
            if new==old:continue
            if TOKEN.findall(old)!=TOKEN.findall(new):
                unhandled.append({'file':str(path.relative_to(directory)),'section':section,'key':key,'text':old,'reason':'Format placeholders differ; left unchanged'})
                continue
            # Control-name records include a VK number; preserve it exactly.
            if section=='controlkeys' and old.split(',',1)[0]!=new.split(',',1)[0]:continue
            trailing=re.search(r'[ \t]*$',match[4])[0]
            lines[index]=match[1]+match[2]+match[3]+new+trailing+(match[5] or '')
            edits.append({'section':section,'key':key,'occurrence':occurrence,'before':old,'after':new,'source':source})
        if edits:
            changed=''.join(lines).encode('cp1252')
            result.append({'path':path,'original':original,'patched':changed,'edits':edits})
            counts[str(path.relative_to(directory))]=len(edits)
    if title == 'A2 Racer 4':
        from .a2iv_text import dialogue_patch, static_patch
        catalog = json.loads((resources(ROOT)/'davilex/a2iv_dialogue.json').read_text(encoding='utf-8'))
        for name, transform in [('communi.ini', dialogue_patch), ('static.ini', static_patch)]:
            path = directory/name
            original = path.read_bytes()
            changed, count = transform(original, catalog)
            if changed != original:
                result.append({'path':path, 'original':original, 'patched':changed,
                               'edits':[], 'whole_file':True})
                counts[name] = count
    report={'title':title,'directory':str(directory),'changed_entries':counts,'unhandled':unhandled,
            'scope':'Loose HUD language selector, menu labels/messages/hints, shared help topics, title-specific story and credit headings. Images, speech and hardcoded executable text are unchanged.'}
    return result,report


def restore(directory):
    directory=Path(directory).resolve()
    from .installed import permitted
    if not permitted(directory):raise ValueError('English mode requires a project working copy.')
    journal=directory/'.english-restore';manifest=journal/'manifest.json'
    if not manifest.exists():return
    items=json.loads(manifest.read_text())
    for item in items:
        target=(directory/item['file']).resolve();backup=(journal/'files'/item['file']).resolve()
        if not target.is_relative_to(directory) or not backup.is_relative_to(journal.resolve()):raise ValueError('Invalid translation backup path.')
        original=backup.read_bytes()
        if hashlib.sha256(original).hexdigest()!=item['original_sha256']:raise ValueError('English backup hash mismatch.')
        current=target.read_bytes()
        if hashlib.sha256(current).hexdigest()==item['patched_sha256']:restored=original
        else:
            if item.get('whole_file'):raise ValueError(f'Help file changed during English mode; original preserved in {backup}')
            lines=current.decode('cp1252').splitlines(keepends=True)
            edits={(e['section'],e['key'],e['occurrence']):e for e in item['edits']}
            for i,section,key,n,match in ini_lines(current):
                edit=edits.get((section,key,n))
                if edit and match[4].strip()==edit['after']:
                    trailing=re.search(r'[ \t]*$',match[4])[0]
                    lines[i]=match[1]+match[2]+match[3]+edit['before']+trailing+(match[5] or '')
            restored=''.join(lines).encode('cp1252')
        target.write_bytes(restored)
    # Keep original backups and journal for recovery; mark restoration complete.
    manifest.rename(journal/f'restored-{__import__("time").time_ns()}.json')


@contextmanager
def english_mode(directory,profile):
    directory=Path(directory).resolve()
    restore(directory)
    changes,report=patches(directory,profile)
    journal=directory/'.english-restore';journal.mkdir(exist_ok=True)
    items=[]
    for change in changes:
        relative=change['path'].relative_to(directory)
        backup=journal/'files'/relative;backup.parent.mkdir(parents=True,exist_ok=True)
        backup.write_bytes(change['original'])
        items.append({'file':str(relative),'original_sha256':hashlib.sha256(change['original']).hexdigest(),
                      'patched_sha256':hashlib.sha256(change['patched']).hexdigest(),'edits':change['edits'],
                      'whole_file':change.get('whole_file',False)})
    (journal/'manifest.json').write_text(json.dumps(items,indent=2)+'\n')
    (ROOT/'analysis'/f'english-{profile}-coverage.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    try:
        for change in changes:change['path'].write_bytes(change['patched'])
        yield report
    finally:restore(directory)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path);parser.add_argument('--profile',default='pmr-timing')
    parser.add_argument('--restore',action='store_true')
    args=parser.parse_args()
    if args.restore:restore(args.directory)
    else:
        _,report=patches(args.directory,args.profile)
        print(json.dumps(report,indent=2,ensure_ascii=True))

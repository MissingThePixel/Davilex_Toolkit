"""Build-specific IV menu preparation using verified local media."""
from pathlib import Path, PureWindowsPath
import hashlib
import json
from .quickrace import update_ini

MENU_SHA256='d56c94301a56dc6c20ac278e15abb2fdccc9a144b6e59986897c67740ba2b0f0'
HIDE_CALLS=((0xa41d5,bytes.fromhex('e8 3e 22 f6 ff')),
            (0xa41e3,bytes.fromhex('e8 30 22 f6 ff')))
INTRO_CALL=(0xa4581,bytes.fromhex('e8 ca f6 ff ff'))
HOLIDAY_SHA256='74af0a82bee128299dd8fab0d69ee89859fb50df4a0521811150f513709ca423'
HOLIDAY_EDITS=((0x8cd49,bytes.fromhex('e862a0f7ff'),bytes.fromhex('83c4089090')),
               (0x8cd5a,bytes.fromhex('e851a0f7ff'),bytes.fromhex('83c4089090')),
               (0x8cefb,bytes.fromhex('e818010000'),bytes.fromhex('e844020000')))
EUROPE_SHA256='96841959cb49e1039b59925560281a4b9e413ba31419c924d89bfe9c96331942'
EUROPE_HIDE_CALLS=((0x6bac8,bytes.fromhex('e873aff9ff')),
                   (0x6bad6,bytes.fromhex('e865aff9ff')))


def europe_menu(original):
    if hashlib.sha256(original).hexdigest()!=EUROPE_SHA256:
        raise ValueError('Unsupported Europe Racer menu build.')
    result=bytearray(original)
    for offset,before in EUROPE_HIDE_CALLS:
        if original[offset:offset+5]!=before:
            raise ValueError('Unexpected Europe shell-hide instructions.')
        result[offset:offset+5]=bytes.fromhex('83c4089090')
    return bytes(result)


def ensure_pmr_true_colour(directory):
    """Keep the menu's selected dimensions, avoiding its broken 8-bit path."""
    import re
    config=Path(directory)/'data'/'Raser.ini'
    data=config.read_bytes()
    section=''
    found=[]
    for line in data.splitlines():
        heading=re.match(rb'\s*\[([^\]]+)\]',line)
        if heading:section=heading[1].strip().lower()
        value=re.fullmatch(rb'\s*RESOLUTION\s*=\s*(\d+)\s*',line,re.I)
        if section==b'program' and value:found.append(int(value[1]))
    if len(found)!=1:raise ValueError('Expected one PMR PROGRAM/RESOLUTION value.')
    value=found[0]
    replacement={0:6,1:3}.get(value,value)
    if replacement!=value:
        config.write_bytes(update_ini(data,{('PROGRAM','RESOLUTION'):replacement}))
        return {'PROGRAM/RESOLUTION':{'before':value,'after':replacement,
                'reason':'Use the corresponding 16-bit colour mode instead of 8-bit palettized rendering.'}}
    return {}


def holiday_menu(original):
    """Keep the shell visible; use the existing post-intro continuation."""
    if hashlib.sha256(original).hexdigest()!=HOLIDAY_SHA256:
        raise ValueError('Unsupported Holiday Racer menu build.')
    result=bytearray(original)
    for offset,before,after in HOLIDAY_EDITS:
        if original[offset:offset+len(before)]!=before:
            raise ValueError('Unexpected Holiday menu instructions.')
        result[offset:offset+len(before)]=after
    return bytes(result)


def shell_safe_menu(original,skip_intro=False):
    """Skip only the two ShowWindow(SW_HIDE) calls; consume their arguments."""
    if hashlib.sha256(original).hexdigest()!=MENU_SHA256:
        raise ValueError('Unsupported A2 IV menu build for shell safety patch.')
    result=bytearray(original)
    for offset,expected in HIDE_CALLS:
        if original[offset:offset+5]!=expected:
            raise ValueError('Unexpected shell-hide instruction bytes.')
        # stdcall ShowWindow would remove its two arguments. Preserve that stack
        # effect without changing the visibility of either shell window.
        result[offset:offset+5]=bytes.fromhex('83 c4 08 90 90')
    if skip_intro:
        offset,expected=INTRO_CALL
        if original[offset:offset+5]!=expected:
            raise ValueError('Unexpected intro playback call bytes.')
        # The Delphi routine takes its string argument in EAX and returns no
        # consumed result here. Keep the caller's local-string cleanup intact.
        result[offset:offset+5]=b'\x90'*5
    return bytes(result)


def desktop_menu_bytes(data):
    """Keep the verified 800x600 form; bypass only mode selection and mode reset."""
    import struct
    result = bytearray(data)
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    section_count = struct.unpack_from('<H', data, pe + 6)[0]
    optional_size = struct.unpack_from('<H', data, pe + 20)[0]
    image_base = struct.unpack_from('<I', data, pe + 24 + 28)[0]
    section_start = pe + 24 + optional_size
    for address in (0x481634, 0x481588):
        rva = address - image_base
        offset = None
        for n in range(section_count):
            base = section_start + n * 40
            virtual_size, virtual_address, size, raw = struct.unpack_from('<IIII', data, base + 8)
            if virtual_address <= rva and rva + 3 <= virtual_address + size:
                offset = raw + rva - virtual_address
                break
        if offset is None or data[offset:offset + 3] != b'\x55\x8b\xec':
            raise ValueError(f'Unsupported A2 IV menu display routine at {address:#x}')
        # Delphi register calling convention, Boolean result in AL, no stack arguments.
        result[offset:offset + 3] = b'\xb0\x01\xc3'
    return bytes(result)

def intro_search_path(path):
    """The original menu prepends c:\\ through z:\\ to INTROAVI."""
    path=PureWindowsPath(path)
    if not path.is_absolute() or len(path.drive)!=2 or not 'C'<=path.drive[0].upper()<='Z':
        raise ValueError('A2 IV local intro must be on a drive C: through Z: (UNC paths are unsupported).')
    result=str(path.relative_to(path.anchor))
    # The current strict INI editor supports ASCII values. Fail before writing.
    try:
        result.encode('ascii')
    except UnicodeEncodeError as error:
        raise ValueError('A2 IV local intro currently requires an ASCII folder path.') from error
    return result


def prepare_local_intro(directory,baseline_files):
    directory=Path(directory).resolve()
    movie=directory/'intro1.mpg'
    expected=next(f['sha256'] for f in baseline_files if f['path'].casefold()=='intro1.mpg')
    if hashlib.sha256(movie.read_bytes()).hexdigest()!=expected:
        raise ValueError('Local intro movie does not match the captured baseline.')
    value=intro_search_path(str(movie))
    config=directory/'menu.ini'
    before=config.read_bytes()
    after=update_ini(before,{('GENERAL','INTROAVI'):value})
    backup=directory/'menu-before-local-media.ini'
    if not backup.exists():
        with backup.open('xb') as stream:
            stream.write(before)
    if after!=before:
        config.write_bytes(after)
    (directory/'menu-media-repair.json').write_text(json.dumps({
        'key':'GENERAL/INTROAVI','new_value':value,'video_sha256':expected,
        'reason':'Original startup gate searches drive roots for the configured intro movie.',
        'executable_check_unchanged':True},indent=2)+'\n',encoding='utf-8')
    return value

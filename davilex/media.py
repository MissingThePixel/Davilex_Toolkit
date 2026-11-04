"""Preview classification and indexed sprite decoding, independent of Tk."""
import io
import struct
from pathlib import Path

CATEGORIES=('Music / audio','Images','3D models','Fonts','Text','Other')


def font_header(head,length):
    if len(head)<264:return None
    width,height,a,b=struct.unpack_from('<4H',head,256)
    if 0<width<=512 and 0<height<=512 and length==264+256*width*height:
        return {'cell_width':width,'cell_height':height,'glyphs':256,'header_words':[a,b]}
    return None


def proportional_font(head,length):
    """Observed FNT: 256 <width,height,offset> slots, then eight opaque bytes."""
    if len(head)<2056:return None
    glyphs=[]
    for code in range(256):
        width,height,offset=struct.unpack_from('<HHI',head,code*8)
        if (width,height,offset)==(65535,65535,0xffffffff):continue
        if not (0<width<=512 and 0<height<=512 and 2056<=offset and offset+width*height<=length):return None
        glyphs.append({'code':code,'width':width,'height':height,'offset':offset})
    if not glyphs:return None
    end=2056
    for glyph in sorted(glyphs,key=lambda g:g['offset']):
        if glyph['offset']!=end:return None
        end+=glyph['width']*glyph['height']
    if end!=length:return None
    return {'glyph_count':len(glyphs),'cell_width':max(g['width'] for g in glyphs),
            'cell_height':max(g['height'] for g in glyphs),'glyphs':glyphs,
            'opaque_header':head[2048:2056].hex()}


def sprite_header(head,length):
    if len(head)<8:return None
    width,height,a,b=struct.unpack_from('<4H',head)
    if not (0<width<=8192 and 0<height<=8192 and width*height<=64*1024*1024):return None
    if length!=8+width*height:return None
    return {'width':width,'height':height,'anchor_words':[a,b]}


def category(archive,entry):
    if not entry.size:return 'Other'
    extension=entry.extension
    if extension in {'.wav','.mp3','.ogg','.flac'}:return 'Music / audio'
    if extension in {'.pcx','.tga','.png','.bmp','.jpg','.jpeg'}:return 'Images'
    if extension=='.bin' and sprite_header(archive.read(entry,8),archive.storage(entry)['decoded_bytes']):return 'Images'
    if extension=='.d3d':return '3D models'
    if extension in {'.img','.fnt'} and entry.size>=264:
        if font_header(archive.read(entry,264),archive.storage(entry)['decoded_bytes']):return 'Fonts'
        if extension=='.fnt' and proportional_font(archive.read(entry,2056),archive.storage(entry)['decoded_bytes']):return 'Fonts'
    if extension in {'.ini','.txt','.cfg','.csv','.xml','.json'}:return 'Text'
    return 'Other'


def load_image(archive,entry,palette=None):
    from PIL import Image
    data=archive.read(entry)
    if entry.extension in {'.img','.fnt'}:
        header=font_header(data,len(data))
        proportional=proportional_font(data,len(data)) if not header else None
        if proportional:
            w,h=proportional['cell_width'],proportional['cell_height']
            atlas=Image.new('P',(w*16,h*16),255)
            for glyph in proportional['glyphs']:
                n=glyph['code'];gw,gh=glyph['width'],glyph['height'];start=glyph['offset']
                image=Image.frombytes('P',(gw,gh),data[start:start+gw*gh])
                atlas.paste(image,(n%16*w,n//16*h))
            atlas.putpalette(palette if palette is not None else [c for i in range(256) for c in (i,i,i)])
            return atlas
        if not header:raise ValueError('Unsupported font/image record. Original export remains available.')
        w,h=header['cell_width'],header['cell_height']
        atlas=Image.new('P',(w*16,h*16),255)
        for n in range(256):
            glyph=Image.frombytes('P',(w,h),data[264+n*w*h:264+(n+1)*w*h])
            atlas.paste(glyph,(n%16*w,n//16*h))
        atlas.putpalette(palette if palette is not None else [c for i in range(256) for c in (i,i,i)])
        return atlas
    if entry.extension=='.bin':
        header=sprite_header(data,len(data))
        if not header:raise ValueError('Unsupported BIN record; indexed-image dimensions do not match its length.')
        image=Image.frombytes('P',(header['width'],header['height']),data[8:])
        image.putpalette(palette if palette is not None else [c for i in range(256) for c in (i,i,i)])
        return image
    image=Image.open(io.BytesIO(data));image.load()
    if entry.extension=='.tga' and len(data)>=18:
        image.info['davilex_tga_alpha_bits']=data[17]&15
    return image


def palette_from_file(path):
    from PIL import Image
    path=Path(path)
    if path.suffix.lower() in {'.pal','.act'}:
        data=path.read_bytes()
        if len(data)!=768:raise ValueError('Raw palettes must contain exactly 256 RGB colours (768 bytes).')
        return list(data)
    with Image.open(path) as image:
        palette=image.getpalette()
        if image.mode!='P' or palette is None:raise ValueError('Choose a palette-indexed image or a raw 768-byte RGB palette.')
        return palette[:768]


def companion_palette(archive):
    """Return a labelled candidate, not a guarantee of original sprite colours."""
    from PIL import Image
    from .rcs import Archive
    menu=archive.image.stem.lower() in {'menurc','mrcs'}
    wanted='pal.pcx' if menu else 'palet.pcx'
    wanted_archive='mrcs' if menu else 'rcs'
    for path in archive.image.parent.iterdir():
        if path.suffix.lower()!='.img' or path.stem.lower()!=wanted_archive:continue
        other=Archive(path)
        for entry in other.entries:
            if entry.name.lower()==wanted:
                with Image.open(io.BytesIO(other.read(entry))) as image:
                    palette=image.getpalette()
                    if palette:return palette[:768],f'{path.name} / {entry.name} (candidate)'
    return None,'Grayscale indices; choose a palette for original colours'


def texture_links(archive):
    """Use explicit model/texture pairs in adjacent INIs; no guessed materials."""
    import re
    links={}
    by_name={e.name.casefold():e.index for e in archive.entries if e.extension in {'.pcx','.tga','.png','.bmp'}}
    roots=[archive.image.parent]
    ini_folder=next((p for p in archive.image.parent.iterdir() if p.is_dir() and p.name.casefold()=='ini'),None)
    if ini_folder:roots.append(ini_folder)
    for root in roots:
        for path in root.iterdir():
            if path.suffix.casefold()!='.ini':continue
            for line in path.read_text(encoding='cp1252').splitlines():
                if line.lstrip().startswith(';') or '=' not in line:continue
                fields=line.split('=',1)[1].split(',')
                if len(fields)<2:continue
                model=Path(fields[0].strip().replace('\\','/')).name.casefold()
                texture=Path(fields[1].strip().replace('\\','/')).name.casefold()
                if model.endswith('.d3d') and texture in by_name:
                    links.setdefault(model,set()).add(by_name[texture])
    return {name:sorted(ids) for name,ids in links.items()}


def ordered_entries(entries,categories,query,sort_column='name',descending=False):
    result=[e for e in entries if categories[e.index][0] and query.casefold() in e.name.casefold()]
    def key(entry):
        if sort_column=='size':return (entry.size,entry.name.casefold(),entry.index)
        if sort_column=='kind':return (entry.extension,entry.name.casefold(),entry.index)
        if sort_column=='category':return (categories[entry.index][1],entry.name.casefold(),entry.index)
        return (entry.name.casefold(),entry.index)
    return sorted(result,key=key,reverse=descending)

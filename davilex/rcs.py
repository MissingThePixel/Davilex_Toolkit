"""Validated reader for the RCS IND/IMG pairs observed in seven Davilex games."""
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from collections import Counter
import io
import re
import struct
import wave
import zlib


class ArchiveError(ValueError):
    pass


@dataclass(frozen=True)
class Entry:
    index: int
    name: str
    offset: int
    size: int

    @property
    def extension(self):
        return Path(self.name).suffix.lower()


class Archive:
    def __init__(self, image, index=None):
        self.image = Path(image).resolve()
        if index is None:
            candidates = [p for p in self.image.parent.iterdir()
                          if p.stem.casefold() == self.image.stem.casefold() and p.suffix.casefold() == '.ind']
            if len(candidates) != 1:
                raise ArchiveError('Select the matching IND file: exactly one is required.')
            index = candidates[0]
        self.index = Path(index).resolve()
        data = self.index.read_bytes()
        if len(data) < 2:
            raise ArchiveError('Index is shorter than its two-byte count.')
        count = struct.unpack_from('<H', data)[0]
        if len(data) == 2+24*count:
            self.index_layout='named-24'
        elif len(data) == 2+4*count:
            self.index_layout='offsets-4'
        else:
            raise ArchiveError(f'Unsupported index layout: expected {2+24*count} named bytes or {2+4*count} offset-only bytes, found {len(data)}.')
        archive_size = self.image.stat().st_size
        records = []
        for n in range(count):
            if self.index_layout=='named-24':
                raw_name, offset = struct.unpack_from('<20sI', data, 2+24*n)
                name = raw_name.split(b'\0', 1)[0].decode('cp1252', 'replace')
            else:
                offset=struct.unpack_from('<I',data,2+4*n)[0]
                name=f'resource_{n:05d}.bin'
            if offset > archive_size:
                raise ArchiveError(f'Entry {n} starts beyond the end of the archive.')
            if records and offset < records[-1][1]:
                raise ArchiveError(f'Entry {n} has a decreasing offset; this variant is unsupported.')
            records.append((name, offset))
        self.entries = tuple(Entry(n, name, offset,
                                  (records[n+1][1] if n+1<count else archive_size)-offset)
                             for n, (name, offset) in enumerate(records))

    def _validate(self, entry):
        if not 0 <= entry.index < len(self.entries) or self.entries[entry.index] != entry:
            raise ArchiveError('Entry does not belong to this archive.')

    def read_raw(self, entry, limit=None):
        self._validate(entry)
        size = entry.size if limit is None else min(entry.size, limit)
        with self.image.open('rb') as stream:
            stream.seek(entry.offset)
            data = stream.read(size)
        if len(data) != size:
            raise ArchiveError('Archive was truncated or changed after opening.')
        return data

    def storage(self, entry):
        head = self.read_raw(entry, 12)
        if head[:4] == b'RIFF' or head[:3] == b'ID3':
            return {'compression': 'none', 'decoded_bytes': entry.size}
        if len(head) >= 6 and head[4] & 15 == 8 and head[4] >> 4 <= 7 and int.from_bytes(head[4:6], 'big') % 31 == 0:
            return {'compression': 'zlib', 'decoded_bytes': struct.unpack_from('<I', head)[0]}
        return {'compression': 'none', 'decoded_bytes': entry.size}

    def read(self, entry, limit=None):
        storage = self.storage(entry)
        if storage['compression'] == 'none':
            return self.read_raw(entry, limit)
        expected = storage['decoded_bytes']
        if expected > 256*1024*1024 or entry.size > 256*1024*1024:
            raise ArchiveError('Entry exceeds the 256 MiB decompression limit.')
        raw = self.read_raw(entry)
        decoder = zlib.decompressobj()
        try:
            decoded = decoder.decompress(raw[4:], expected+1)
        except zlib.error as error:
            raise ArchiveError(f'Invalid zlib data in {entry.name}: {error}') from error
        if len(decoded) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ArchiveError(f'Invalid decoded size or zlib stream boundary in {entry.name}.')
        return decoded if limit is None else decoded[:limit]

    @staticmethod
    def export_name(entry):
        # Flat, indexed filenames preserve duplicate/case-distinct entries on Windows.
        name = entry.name
        win = PureWindowsPath(name)
        if win.is_absolute() or win.drive or '/' in name or '\\' in name or name in {'.', '..'}:
            raise ArchiveError(f'Unsafe archive name: {name!r}')
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(' .') or 'unnamed'
        return f'{entry.index:05d}-{name}'

    def extract(self, entry, destination, raw=False):
        self._validate(entry)
        root = Path(destination).resolve()
        target = root / self.export_name(entry)
        if target == self.image or target == self.index:
            raise ArchiveError('Cannot overwrite the archive or index.')
        root.mkdir(parents=True, exist_ok=True)
        # Exclusive creation also rejects pre-existing files and symlinks.
        try:
            with self.image.open('rb') as source, target.open('xb') as output:
                if not raw and self.storage(entry)['compression'] != 'none':
                    output.write(self.read(entry))
                    return target
                source.seek(entry.offset)
                remaining = entry.size
                while remaining:
                    block = source.read(min(1024*1024, remaining))
                    if not block:
                        raise ArchiveError('Archive was truncated during extraction.')
                    output.write(block)
                    remaining -= len(block)
        except Exception:
            # Do not delete a pre-existing target if exclusive creation failed.
            if 'output' in locals():
                target.unlink(missing_ok=True)
            raise
        return target

    def describe(self, entry):
        head = self.read(entry, 128)
        info = {'index': entry.index, 'name': entry.name, 'offset': entry.offset,
                'bytes': entry.size, 'type': 'Unknown', 'signature': head[:32].hex(' ')}
        info.update(self.storage(entry))
        if entry.size == 0:
            info['type'] = 'Empty / index marker'
        elif head[:4] == b'RIFF' and head[8:12] == b'WAVE':
            info['type'] = 'WAV audio'
            # Parse format chunks directly: wave only accepts PCM and some extensible WAVs.
            with io.BytesIO(self.read(entry)) as stream:
                cursor = 12
                end = len(stream.getbuffer())
                while cursor+8 <= end:
                    stream.seek(cursor)
                    tag, length = struct.unpack('<4sI', stream.read(8))
                    if cursor+8+length > end:
                        info['warning'] = 'WAV chunk extends beyond archive entry'
                        break
                    if tag == b'fmt ' and length >= 16:
                        fmt, channels, rate, byte_rate, align, bits = struct.unpack('<HHIIHH', stream.read(16))
                        info.update(codec_tag=fmt, channels=channels, sample_rate=rate, bits=bits, byte_rate=byte_rate)
                    if tag == b'data':
                        info['audio_bytes'] = length
                    cursor += 8+length+(length & 1)
            if info.get('byte_rate') and 'audio_bytes' in info:
                info['duration_seconds'] = round(info['audio_bytes']/info['byte_rate'], 3)
        elif head[:3] == b'ID3' or (entry.extension == '.mp3' and len(head)>1 and head[0] == 255 and head[1]&0xe0 == 0xe0):
            info['type'] = 'MP3 audio'
        elif len(head) >= 128 and head[0] == 10 and head[2] == 1 and head[3] in {1,2,4,8}:
            info['type'] = 'PCX image'
        elif entry.extension == '.tga':
            info['type'] = 'TGA candidate (decode to validate)'
        elif entry.extension in {'.img','.fnt'}:
            from .media import font_header,proportional_font
            font=font_header(self.read(entry,264),info['decoded_bytes'])
            info['type']='Indexed 256-glyph font atlas' if font else 'Unknown font/image resource'
            if font:info.update(font)
            elif entry.extension=='.fnt':
                font=proportional_font(self.read(entry,2056),info['decoded_bytes'])
                if font:
                    info.update({k:v for k,v in font.items() if k!='glyphs'})
                    info['type']='Indexed proportional font atlas'
        elif entry.extension == '.d3d':
            info['type'] = 'Game model candidate (format not decoded)'
        elif entry.extension == '.bin':
            from .media import sprite_header
            sprite=sprite_header(head,info['decoded_bytes'])
            if sprite:
                info.update(type='Indexed 8-bit sprite',**sprite)
                info['palette']='Stored separately; candidate palette or grayscale indices in viewer.'
        return info

    def summary(self):
        return {'image': str(self.image), 'index': str(self.index), 'entries': len(self.entries),
                'index_layout': self.index_layout,
                'bytes': self.image.stat().st_size,
                'extensions': dict(Counter(e.extension or '(none)' for e in self.entries)),
                'empty_entries': sum(e.size == 0 for e in self.entries)}


def convert_image(archive, entry, destination, palette=None):
    from .media import load_image
    if entry.size > 128*1024*1024:
        raise ArchiveError('Image is too large for an in-memory conversion.')
    target = Path(destination).resolve()
    if target in {archive.image, archive.index}:
        raise ArchiveError('Cannot overwrite an input archive.')
    with load_image(archive,entry,palette) as image:
        image.load()
        if image.mode not in {'RGB', 'RGBA', 'L', 'LA', 'P'}:
            image = image.convert('RGBA')
        # Exclusive output prevents accidental overwrites.
        with target.open('xb') as output:
            image.save(output, format='PNG')
    return target

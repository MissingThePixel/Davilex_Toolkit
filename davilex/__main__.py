import argparse
import json
from pathlib import Path
from .rcs import Archive, ArchiveError, convert_image
from .mesh import export_obj


def main():
    parser = argparse.ArgumentParser(description='Inspect and extract Davilex RCS archives.')
    parser.add_argument('image', type=Path)
    parser.add_argument('--index', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('info')
    listing = sub.add_parser('list')
    listing.add_argument('--filter', default='')
    listing.add_argument('--details', action='store_true')
    extract = sub.add_parser('extract')
    extract.add_argument('destination', type=Path)
    extract.add_argument('--entry', type=int, action='append')
    extract.add_argument('--audio', action='store_true')
    extract.add_argument('--raw', action='store_true', help='Export stored bytes without decompression')
    convert = sub.add_parser('png')
    convert.add_argument('entry', type=int)
    convert.add_argument('destination', type=Path)
    model = sub.add_parser('obj',help='Convert a supported D3D mesh to geometry-only OBJ')
    model.add_argument('entry',type=int)
    model.add_argument('destination',type=Path)
    args = parser.parse_args()
    try:
        archive = Archive(args.image, args.index)
        if args.command == 'info':
            print(json.dumps(archive.summary(), indent=2))
        elif args.command == 'list':
            entries = [e for e in archive.entries if args.filter.casefold() in e.name.casefold()]
            print(json.dumps([archive.describe(e) if args.details else vars(e) for e in entries], indent=2))
        elif args.command == 'extract':
            entries = archive.entries if args.entry is None else [archive.entries[n] for n in args.entry if n >= 0 and n < len(archive.entries)]
            if args.entry is not None and len(entries) != len(args.entry):
                raise ArchiveError('Invalid entry index.')
            if args.audio:
                entries = [e for e in entries if e.extension in {'.wav', '.mp3'}]
            paths = [str(archive.extract(e, args.destination, raw=args.raw)) for e in entries if e.size]
            print(json.dumps({'extracted': len(paths), 'files': paths}, indent=2))
        elif args.command == 'png':
            if not 0 <= args.entry < len(archive.entries):
                raise ArchiveError('Invalid entry index.')
            print(convert_image(archive, archive.entries[args.entry], args.destination))
        elif args.command == 'obj':
            if not 0 <= args.entry < len(archive.entries):
                raise ArchiveError('Invalid entry index.')
            entry=archive.entries[args.entry]
            if entry.extension != '.d3d':
                raise ArchiveError('Select a D3D model entry.')
            print(export_obj(archive.read(entry),args.destination))
    except (ValueError, OSError, ImportError) as error:
        parser.exit(1, f'Error: {error}\n')


if __name__ == '__main__':
    main()

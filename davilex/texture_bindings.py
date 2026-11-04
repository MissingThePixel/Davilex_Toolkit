"""Resolve explicit texture bindings, with optional exact-mesh cross-archive matches."""
from dataclasses import dataclass
from pathlib import Path
import hashlib
from .rcs import Archive

# Reviewed UV/atlas associations for retained, unreferenced racer_* models.
# Pin BOTH payloads: similar filenames in another release are not evidence of
# the same material. TGA and original indexed PCX are selectable local variants.
LEGACY_CAR_MODELS={
    '1abc33e323da33def231788cb7600c6e12cf2a65b20428113c6c9b360491ec1f':'racer01',
    '645e2698cc654334964f47003e464bbc51cc7b1303eea272e63c090c4429f07a':'racer02',
    '7a02ca88b6a9f71b50e70aef3287a767b29d2a7b9d420935295d5130d51c7308':'racer02',
    '5d9d97852e110174c7f6d3b14a1c6a9a848db32ae9f19a76113468b7cf39d8fb':'racer01',
    'b1cd53fbd845709fa1c17cba2c9ae79e4a74d5a5c83d00ceefd635acdb13d0a5':'racer01',
    '32e6a19e05c60ef9b6b573bb954ce53bca71d8f1f04ce464d567ceb7921514ff':'racer01',
    'aae0be299e4a217316ba8072c6bcaef45acc4843e75dcbcdf607431c9adc7d97':'racer01',
}
LEGACY_CAR_TEXTURES={
    'racer01':{'40eee1405e98746822504674dccb8c7c1c1de23dffd55d330736df41e9f9f1f1',
               '73cec67c65c31b002c01a117d001e589f64e619decd89ecbf1b0b7ae8f2cba50'},
    'racer02':{'5920b069a161c730413fab518e76b7585936abd9079c8ad1906247c3084033ed',
               'dca266d35f53d759814dd1cf3b70dedf2dc326446bdecf0dea9a4af194b9df22'},
}


@dataclass(frozen=True)
class Binding:
    archive: object
    entry: object
    source: str
    rank: float
    related: bool=False


def references(archive):
    images={}
    for entry in archive.entries:
        if entry.extension in {'.pcx','.tga','.png','.bmp'}:
            images.setdefault(entry.name.casefold(),[]).append(entry)
    roots=[archive.image.parent]
    roots.extend(p for p in archive.image.parent.iterdir() if p.is_dir() and p.name.casefold()=='ini')
    result={}
    for root in roots:
        for path in sorted(root.iterdir()):
            if path.suffix.casefold()!='.ini':continue
            animation='anim' in path.stem.casefold()
            for number,line in enumerate(path.read_text(encoding='cp1252').splitlines(),1):
                if line.lstrip().startswith(';') or '=' not in line:continue
                fields=line.split('=',1)[1].split(',')
                if len(fields)<2:continue
                model=Path(fields[0].strip().replace('\\','/')).name.casefold()
                texture=Path(fields[1].strip().replace('\\','/')).name.casefold()
                if not model.endswith('.d3d'):continue
                candidates=list(images.get(texture,[]))
                # The paired high-colour texture is a selectable variant; retain
                # the actual INI reference as provenance rather than hiding it.
                if texture.endswith('.pcx'):candidates.extend(images.get(texture[:-4]+'.tga',[]))
                for entry in candidates:
                    rank=(0 if animation else 2)+(0 if entry.extension=='.tga' else .1)
                    result.setdefault(model,[]).append(Binding(archive,entry,f'{path.name}:{number}',rank))
    return result


class Resolver:
    def __init__(self,archive,baseline,related_roots=()):
        self.archive=archive;self.baseline=Path(baseline)
        self.related_roots=tuple(map(Path,related_roots))
        self.local=references(archive);self.related=None;self.cache={}
        self.legacy_textures={}

    def _legacy_bindings(self,digest):
        atlas=LEGACY_CAR_MODELS.get(digest.hex())
        if atlas is None:return []
        if atlas not in self.legacy_textures:
            found=[]
            for image in self.archive.entries:
                if image.extension not in {'.tga','.pcx'} or Path(image.name).stem.casefold()!=atlas:continue
                if hashlib.sha256(self.archive.read(image)).hexdigest() not in LEGACY_CAR_TEXTURES[atlas]:continue
                found.append(Binding(self.archive,image,'Reviewed retained car / original atlas (model and texture SHA-256 verified)',
                                     .5 if image.extension=='.tga' else .6))
            self.legacy_textures[atlas]=found
        return self.legacy_textures[atlas]

    def _archives(self):
        if self.related is None:
            self.related=[]
            paths=set(self.baseline.rglob('*'))
            for folder in self.related_roots:paths.update(folder.rglob('*'))
            for path in sorted(paths):
                if path.name.casefold()!='rcs.img' or path.resolve()==self.archive.image:continue
                other=Archive(path)
                if any(e.extension=='.d3d' for e in other.entries):
                    self.related.append((other,references(other)))
        return self.related

    def resolve(self,entry,related=True):
        key=(entry.index,related)
        if key in self.cache:return self.cache[key]
        result=list(self.local.get(entry.name.casefold(),[]))
        digest=hashlib.sha256(self.archive.read(entry)).digest()
        if not result:result.extend(self._legacy_bindings(digest))
        if related:
            for archive,refs in self._archives():
                for other in archive.entries:
                    if other.extension!='.d3d' or other.size!=entry.size:continue
                    if hashlib.sha256(archive.read(other)).digest()!=digest:continue
                    for binding in refs.get(other.name.casefold(),[]):
                        # Exact mesh bytes include the UVs. Original animation
                        # bindings rank ahead of another title's track placeholder.
                        rank=binding.rank+1+(0 if other.name.casefold()==entry.name.casefold() else .25)
                        result.append(Binding(binding.archive,binding.entry,
                                              f'Identical mesh {other.name}; {binding.source}',rank,True))
        unique={}
        for binding in result:
            k=(binding.archive.image,binding.entry.index)
            if k not in unique or binding.rank<unique[k].rank:unique[k]=binding
        result=sorted(unique.values(),key=lambda b:(b.rank,str(b.archive.image),b.entry.index))
        self.cache[key]=result
        return result

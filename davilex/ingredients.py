"""Read verified binary patch recipes without storing duplicate game executables."""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import hashlib,json
from .paths import ROOT,resources

_SELECTED=ContextVar('ingredient_install',default=None)

def digest(data):return hashlib.sha256(data).hexdigest()

@contextmanager
def selected_install(directory,profile):
 token=_SELECTED.set((Path(directory),profile))
 try:yield
 finally:_SELECTED.reset(token)

def apply(base,recipe):
 result=bytearray(base[:recipe['size']]);result.extend(bytes(max(0,recipe['size']-len(result))))
 for offset,hexdata in recipe['changes']:
  data=bytes.fromhex(hexdata)
  if offset<0 or offset+len(data)>len(result):raise ValueError('Invalid binary patch range')
  result[offset:offset+len(data)]=data
 result=bytes(result)
 if digest(result)!=recipe['sha256']:raise ValueError('Binary patch output hash mismatch')
 return result

def read(path):
 path=Path(path)
 if path.is_file():return path.read_bytes()
 root=resources(ROOT)
 try:key=path.relative_to(root).as_posix().casefold()
 except ValueError:raise FileNotFoundError(path)
 catalog=json.loads((root/'patches/binary-recipes.json').read_text(encoding='utf-8'))
 if key not in catalog['paths']:raise FileNotFoundError(path)
 record=catalog['binaries'][catalog['paths'][key]['entry']]
 from .installed import locate,ACTIVE
 from .launch import PROFILES
 selection=_SELECTED.get();active=ACTIVE.get()
 if selection and PROFILES[selection[1]][0]==record['title']:directory=selection[0]
 elif active and active.get('profile')in PROFILES and PROFILES[active['profile']][0]==record['title']:directory=active['directory']
 else:directory=locate(record['profile'])
 current=(directory/record['relative']).read_bytes()
 original=apply(current,record['restore'])
 canonical=apply(original,record['canonical'])
 # A whole-file match is mandatory. Restoring expected bytes alone must not
 # turn an unrecognised modified executable into an accepted build.
 if record.get('kind')=='engine':
  from .recognition import engine_matches
  accepted=current==original or engine_matches(current,canonical,record['profile'])
 else:accepted=any(current==apply(original,variant)for variant in record['accepted'])
 if not accepted:
  raise ValueError('Unsupported game binary; preserving '+str(directory/record['relative']))
 return original if catalog['paths'][key]['kind']=='original'else canonical

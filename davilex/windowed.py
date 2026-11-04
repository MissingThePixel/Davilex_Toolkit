"""Reversible DirectDraw/early Direct3D translation through D3D9 or D3D11."""
import base64
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import uuid
import zlib
import sys
import time
from .paths import resources
from .installed import journal_folder,safe_target,replace_file,write_json,permitted
from .quickrace import update_ini

HASHES={'ddraw.dll':'f68cd82bfb585c9b6676c6282b0fac713c9567eae624bc991c5bcfe5881c7bef',
        'D3DImm.dll':'85aa1d15d6880dbe927458f6a045a631264ba128528010b7296ec5c3a640e0ac'}
DEBUG_HASHES={'ddraw.dll':'b348598a1e95a2d664f516fddde6bc31786204d4f68dd3710514704a9385e30a',
              'D3DImm.dll':'bc246a5c542f565bf4bd865d24c1bde84ad32c7dd3c2ec3866799dc96cd6b396'}
DXWRAPPER_HASH='23a2889e0785a02f17f1ee764254bf22b937fc5bdc6ed6374201a9f50cc7b43d'
DXWRAPPER_STUB_HASH='b8b878e29c2931d6a8d064665c4c93edb28a0105152e7247f8f543c1603985c3'
COLOURKEY_HASH='d2fc46fac69864a268a1674c4e9e2203b30f5a42e8b33af205d602592e8c97e1'


def dxwrapper_payloads(accelerate=False):
    folder=resources()/'wrappers/dxwrapper'
    sidecar=getattr(sys,'frozen',False)or folder.is_dir()
    if sidecar:
        data=(folder/'dxwrapper.dll').read_bytes();stub=(folder/'ddraw.dll').read_bytes()
        CONFIG_TEMPLATE=(folder/'dxwrapper.ini').read_bytes()
    else:
        from ._dxwrapper_data import PAYLOAD,STUB,CONFIG_TEMPLATE
        data=zlib.decompress(base64.b85decode(PAYLOAD));stub=zlib.decompress(base64.b85decode(STUB))
    if hashlib.sha256(data).hexdigest()!=DXWRAPPER_HASH:raise ValueError('DXWrapper hash mismatch.')
    if hashlib.sha256(stub).hexdigest()!=DXWRAPPER_STUB_HASH:raise ValueError('DXWrapper stub hash mismatch.')
    config=update_ini(CONFIG_TEMPLATE,{('General','WrapperMode'):'AUTO',
        ('Compatibility','Dd7to9'):1,('d3d9','EnableWindowMode'):1,('d3d9','WindowModeBorder'):1})
    # Use the author's supported stub + main DLL layout for static imports.
    result={'ddraw.dll':stub,'dxwrapper.dll':data,'dxwrapper.ini':config}
    if accelerate:
        if sidecar:plugin=(folder/'davilex-colourkey.dll').read_bytes()
        else:
            from ._dxwrapper_data import COLOURKEY
            plugin=zlib.decompress(base64.b85decode(COLOURKEY))
        if hashlib.sha256(plugin).hexdigest()!=COLOURKEY_HASH:raise ValueError('Colour-key plugin hash mismatch.')
        result['davilex-colourkey.dll']=plugin
        result['dxwrapper.ini']=update_ini(config,{('General','LoadCustomDllPath'):'davilex-colourkey.dll'})
    return result


def payloads(width=None,height=None,diagnostic=False):
    frozen=getattr(sys,'frozen',False)or (resources()/'patches/binary-recipes.json').is_file()
    if frozen:
        folder=resources()/'wrappers'/('dgvoodoo-debug' if diagnostic else 'dgvoodoo')
        if not folder.is_dir():raise ValueError('dgVoodoo is not bundled. Select DDrawCompat or Wine compatibility (D3D9).')
        CONFIG_TEMPLATE=(folder/'dgVoodoo.conf').read_bytes()
    else:from ._dgvoodoo_data import PAYLOADS,DEBUG_PAYLOADS,CONFIG_TEMPLATE
    result={}
    for name,expected in (DEBUG_HASHES if diagnostic else HASHES).items():
        data=(folder/name).read_bytes() if frozen else zlib.decompress(base64.b85decode((DEBUG_PAYLOADS if diagnostic else PAYLOADS)[name]))
        if hashlib.sha256(data).hexdigest()!=expected:raise ValueError('Windowed backend hash mismatch: '+name)
        result[name]=data
    settings={
        ('General','OutputAPI'):'d3d11_fl10_0',('General','FullScreenMode'):'false',
        ('General','ScalingMode'):'stretched_ar',('General','KeepWindowAspectRatio'):'true',
        ('General','CenterAppWindow'):'true',('GeneralExt','DesktopBitDepth'):32,
        ('DirectX','Resolution'):'unforced',('DirectX','dgVoodooWatermark'):'true',
        ('DirectX','AppControlledScreenMode'):'false',
        ('DirectXExt','EnumeratedResolutionBitdepths'):'all',
        ('DirectXExt','DepthBuffersBitDepth'):'forcemin24bit',
        ('DirectXExt','Default3DRenderFormat'):'argb8888'}
    if width is not None or height is not None:
        if type(width) is not int or type(height) is not int or not (640<=width<=8192 and 480<=height<=8192):
            raise ValueError('Invalid windowed display dimensions.')
        settings['DirectXExt','ExtraEnumeratedResolutions']=f'{width}x{height}'
    if diagnostic:settings['Debug','MaxTraceLevel']=1
    result['dgVoodoo.conf']=update_ini(CONFIG_TEMPLATE,settings)
    return result


RESTORE_WAIT_SECONDS=2.0


def _retry_restore(operation):
    deadline=time.monotonic()+RESTORE_WAIT_SECONDS
    while True:
        try:return operation()
        except PermissionError as error:
            if getattr(error,'winerror',None)not in (5,32,33)or time.monotonic()>=deadline:raise
            time.sleep(.1)


def restore(directory,*,defer_locked=False):
    directory=Path(directory).resolve()
    if not permitted(directory):raise ValueError('Renderer recovery requires a verified game session.')
    journal=journal_folder(directory)/'windowed-renderer';manifest=journal/'active.json'
    if not manifest.exists():return True
    items=json.loads(manifest.read_text())
    for item in reversed(items):
        target=safe_target(directory,item['file'])
        def restore_item():
            current=hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
            if current==item['before']:return
            if current!=item['after']:raise ValueError(f'Renderer file changed; preserving {target}')
            if item['before'] is None:target.unlink()
            else:
                before=safe_target(journal/'original',item['file']).read_bytes()
                if hashlib.sha256(before).hexdigest()!=item['before']:raise ValueError('Renderer backup hash mismatch.')
                replace_file(target,before)
        try:_retry_restore(restore_item)
        except PermissionError as error:
            if not defer_locked or getattr(error,'winerror',None)not in (5,32,33):raise
            print(f'Renderer cleanup pending: {target.name} is still locked after game exit. '
                  'The recovery journal is retained; cleanup will retry before the next launch.',flush=True)
            return False
    manifest.rename(journal/('restored-'+uuid.uuid4().hex+'.json'))
    return True


@contextmanager
def windowed_mode(directory,profile,width=None,height=None,diagnostic=False,backend='dgvoodoo',executable=None):
    from .menu import verify_copy
    directory=Path(directory).resolve();restore(directory)
    menu,engine=verify_copy(directory,profile)
    executable=Path(executable or engine).resolve()
    if executable not in (menu.resolve(),engine.resolve()):raise ValueError('Renderer target is not a verified game executable.')
    if backend not in ('dgvoodoo','dxwrapper'):raise ValueError('Unknown windowed backend.')
    from .wine_overrides import running_under_wine
    accelerate=executable==engine.resolve() and running_under_wine()
    payload=dxwrapper_payloads(accelerate) if backend=='dxwrapper' else payloads(width,height,diagnostic)
    targets=[];items=[]
    journal=journal_folder(directory)/'windowed-renderer';journal.mkdir(parents=True,exist_ok=True)
    for folder in (executable.parent,):
        for name,data in payload.items():
            target=folder/name;relative=target.relative_to(directory)
            original=target.read_bytes() if target.exists() else None
            if original is not None:
                backup=safe_target(journal/'original',relative);backup.parent.mkdir(parents=True,exist_ok=True)
                backup.write_bytes(original)
            items.append({'file':str(relative),'before':hashlib.sha256(original).hexdigest() if original is not None else None,
                          'after':hashlib.sha256(data).hexdigest()})
            targets.append((target,data))
    write_json(journal/'active.json',items)
    try:
        for target,data in targets:replace_file(target,data)
        if backend=='dxwrapper':
            print('Windowed backend: DXWrapper v1.9.8700.25, DirectDraw/Direct3D 1-7 to D3D9, no FPS cap.',flush=True)
        else:
            if diagnostic:print('dgVoodoo diagnostic DLLs enabled; capture Wine +debugstr output.',flush=True)
            print('Windowed backend: dgVoodoo 2.87.6, D3D11, forced windowed mode, minimum D24 depth; '
                  +('extra virtual mode '+str(width)+'x'+str(height)+'.' if width is not None else 'default virtual modes.'),flush=True)
        yield
    finally:restore(directory,defer_locked=True)

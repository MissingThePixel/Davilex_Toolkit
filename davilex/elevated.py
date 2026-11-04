"""Run an installation session with Windows write permission when required."""
import contextlib
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from .launch import ROOT
from .paths import command


def requires_elevation(directory):
    if os.name!='nt' or ctypes.windll.shell32.IsUserAnAdmin():return False
    probe=Path(directory)/('.davilex-write-check-'+uuid.uuid4().hex)
    try:
        with probe.open('xb'):pass
    except PermissionError:return True
    finally:
        if probe.exists():probe.unlink()
    return False


def execute(arguments, directory):
    """Return (exit code, detail); keep the desktop GUI unelevated."""
    if not requires_elevation(directory):
        result=subprocess.run(command('toolkit',*arguments),cwd=ROOT,
                              capture_output=True,text=True,errors='replace',
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        detail=result.stdout+'\n'+result.stderr
        logfile=ROOT/'work/toolkit-last-run.log'
        if getattr(sys,'frozen',False) and logfile.exists():detail=logfile.read_text(encoding='utf-8')+detail
        logfile.write_text(detail,encoding='utf-8')
        return result.returncode,detail
    request=ROOT/'work'/('installed-run-'+uuid.uuid4().hex+'.json')
    request.write_text(json.dumps({'arguments':arguments}),encoding='utf-8')
    response=request.with_suffix('.result.json')
    class SHELLEXECUTEINFO(ctypes.Structure):
        _fields_=[('cbSize',wintypes.DWORD),('fMask',wintypes.ULONG),('hwnd',wintypes.HWND),
                  ('lpVerb',wintypes.LPCWSTR),('lpFile',wintypes.LPCWSTR),('lpParameters',wintypes.LPCWSTR),
                  ('lpDirectory',wintypes.LPCWSTR),('nShow',ctypes.c_int),('hInstApp',wintypes.HINSTANCE),
                  ('lpIDList',ctypes.c_void_p),('lpClass',wintypes.LPCWSTR),('hkeyClass',wintypes.HKEY),
                  ('dwHotKey',wintypes.DWORD),('hIcon',wintypes.HANDLE),('hProcess',wintypes.HANDLE)]
    shell=ctypes.WinDLL('shell32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    shell.ShellExecuteExW.argtypes=[ctypes.POINTER(SHELLEXECUTEINFO)]
    shell.ShellExecuteExW.restype=wintypes.BOOL
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    info=SHELLEXECUTEINFO();info.cbSize=ctypes.sizeof(info);info.fMask=0x40
    info.lpVerb='runas';info.lpFile=sys.executable
    info.lpParameters=subprocess.list2cmdline(command('elevated',str(request))[1:])
    info.lpDirectory=str(ROOT);info.nShow=0
    try:
        if not shell.ShellExecuteExW(ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:kernel.WaitForSingleObject(info.hProcess,0xffffffff)
        finally:kernel.CloseHandle(info.hProcess)
        if not response.exists():raise OSError('The installation session ended without a result. Check toolkit-last-run.log.')
        result=json.loads(response.read_text(encoding='utf-8'))
        return result['code'],(ROOT/'work/toolkit-last-run.log').read_text(encoding='utf-8')
    finally:
        request.unlink(missing_ok=True);response.unlink(missing_ok=True)


def main():
    request=Path(sys.argv[1]).resolve()
    if request.parent!=(ROOT/'work').resolve() or not request.name.startswith('installed-run-'):
        raise ValueError('Invalid toolkit launch request.')
    arguments=json.loads(request.read_text(encoding='utf-8'))['arguments']
    code=1
    with (ROOT/'work/toolkit-last-run.log').open('w',encoding='utf-8',buffering=1) as stream:
        with contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
            try:
                from .toolkit import main as launch
                sys.argv=['davilex.toolkit',*arguments]
                launch();code=0
            except SystemExit as error:code=error.code if isinstance(error.code,int) else 1
            except BaseException:
                import traceback
                traceback.print_exc()
    request.with_suffix('.result.json').write_text(json.dumps({'code':code}),encoding='utf-8')


if __name__=='__main__':main()

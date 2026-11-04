"""Start external game/audio binaries without inheriting frozen Python DLLs."""
from contextlib import contextmanager
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import threading

_spawn_lock=threading.RLock()


def external_environment(environment):
    result=dict(environment)
    internal=Path(sys._MEIPASS).resolve()
    paths=[]
    for path in result.get('PATH','').split(os.pathsep):
        try:bundled=Path(path).resolve().is_relative_to(internal)
        except OSError:bundled=False
        if not bundled:paths.append(path)
    result['PATH']=os.pathsep.join(paths)
    return result


@contextmanager
def system_dll_search():
    if os.name!='nt':
        yield;return
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.GetDllDirectoryW.argtypes=[ctypes.c_uint32,ctypes.c_wchar_p]
    api.SetDllDirectoryW.argtypes=[ctypes.c_wchar_p]
    size=api.GetDllDirectoryW(0,None)
    buffer=ctypes.create_unicode_buffer(size+1)
    if size:api.GetDllDirectoryW(len(buffer),buffer)
    original=buffer.value or None
    if not api.SetDllDirectoryW(None):raise ctypes.WinError(ctypes.get_last_error())
    try:yield
    finally:
        if not api.SetDllDirectoryW(original):raise ctypes.WinError(ctypes.get_last_error())


def external_run(arguments,*,capture_output=False,check=False,timeout=None,input=None,**kwargs):
    if not getattr(sys,'frozen',False):
        return subprocess.run(arguments,capture_output=capture_output,check=check,timeout=timeout,input=input,**kwargs)
    kwargs['env']=external_environment(kwargs.get('env') or os.environ)
    if capture_output:
        if 'stdout' in kwargs or 'stderr' in kwargs:raise ValueError('capture_output conflicts with stdout/stderr.')
        kwargs.update(stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if input is not None:kwargs['stdin']=subprocess.PIPE
    # Restore our DLL directory immediately after CreateProcess, rather than
    # leaving the GUI's imports affected while a game or conversion runs.
    with _spawn_lock,system_dll_search():process=subprocess.Popen(arguments,**kwargs)
    with process:
        try:stdout,stderr=process.communicate(input,timeout=timeout)
        except BaseException:
            process.kill();process.communicate();raise
        code=process.returncode
    if check and code:raise subprocess.CalledProcessError(code,arguments,output=stdout,stderr=stderr)
    return subprocess.CompletedProcess(arguments,code,stdout,stderr)

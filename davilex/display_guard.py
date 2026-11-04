"""Restore the current primary display mode after an isolated game process exits."""
import ctypes as C
import os
import struct
from contextlib import contextmanager


class WindowsDisplay:
    def __init__(self):
        self.api=C.WinDLL('user32',use_last_error=True)
        self.api.EnumDisplaySettingsW.argtypes=[C.c_wchar_p,C.c_uint32,C.c_void_p]
        self.api.EnumDisplaySettingsW.restype=C.c_int
        self.api.ChangeDisplaySettingsW.argtypes=[C.c_void_p,C.c_uint32]
        self.api.ChangeDisplaySettingsW.restype=C.c_long

    def capture(self):
        # DEVMODEW is 220 bytes for the Windows display API. dmSize is at 68.
        mode=C.create_string_buffer(220)
        struct.pack_into('<H',mode,68,220)
        if not self.api.EnumDisplaySettingsW(None,0xffffffff,mode):
            raise OSError('Cannot capture the current display mode; refusing to launch.')
        return mode.raw

    def restore(self,mode):
        # No CDS_UPDATEREGISTRY: preserve saved Windows display preferences.
        result=self.api.ChangeDisplaySettingsW(C.create_string_buffer(mode),0)
        if result!=0:
            raise OSError(f'Restoring the pre-game display mode failed ({result}).')


@contextmanager
def preserve_display(backend=None):
    if backend is None:
        if os.name!='nt':
            yield
            return
        backend=WindowsDisplay()
    before=backend.capture()
    try:
        yield
    finally:
        # Compare active display fields, excluding mutable driver/name metadata.
        after=backend.capture()
        if before[168:188]!=after[168:188] or before[76:92]!=after[76:92]:
            backend.restore(before)

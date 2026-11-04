"""Non-activating desktop surround for the original A2 IV menu."""
from contextlib import contextmanager
import sys
import threading

@contextmanager
def black_backdrop():
    """Non-activating black primary-display window, behind the launched menu/race."""
    if sys.platform != 'win32':
        yield
        return
    import ctypes
    from ctypes import wintypes as w
    ready = threading.Event()
    handle = []
    errors = []
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID]
    user32.CreateWindowExW.restype = w.HWND
    user32.SetWindowPos.argtypes = [w.HWND, w.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, w.UINT]
    user32.SetWindowPos.restype = w.BOOL
    user32.GetMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT]
    user32.GetMessageW.restype = ctypes.c_int
    user32.TranslateMessage.argtypes = [ctypes.POINTER(w.MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(w.MSG)]
    user32.DispatchMessageW.restype = ctypes.c_ssize_t
    user32.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
    user32.DestroyWindow.argtypes = [w.HWND]
    user32.IsWindow.argtypes = [w.HWND]

    def window_thread():
        hwnd = None
        try:
            width, height = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
            # WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW; WS_POPUP | WS_VISIBLE | SS_BLACKRECT.
            hwnd = user32.CreateWindowExW(0x08000080, 'STATIC',
                'Davilex A2 IV menu backdrop', 0x90000004,
                0, 0, width, height, None, None, None, None)
            if not hwnd:
                raise ctypes.WinError(ctypes.get_last_error())
            # HWND_TOP, SWP_NOACTIVATE: cover existing windows without taking focus.
            if not user32.SetWindowPos(hwnd, None, 0, 0, width, height, 0x10):
                raise ctypes.WinError(ctypes.get_last_error())
            handle.append(hwnd)
        except Exception as exc:
            errors.append(exc)
        finally:
            ready.set()
        if hwnd and not errors:
            message = w.MSG()
            while user32.IsWindow(hwnd):
                status = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if status <= 0:
                    break
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        if hwnd and user32.IsWindow(hwnd):
            user32.DestroyWindow(hwnd)

    thread = threading.Thread(target=window_thread, name='A2IV black backdrop', daemon=True)
    thread.start()
    if not ready.wait(10):
        raise RuntimeError('Timed out creating the A2 IV menu backdrop.')
    if errors:
        raise errors[0]
    try:
        yield
    finally:
        if handle:
            user32.PostMessageW(handle[0], 0x10, 0, 0)  # WM_CLOSE
        thread.join(3)

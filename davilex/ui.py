"""Shared crisp Tk rendering and supplied application artwork."""
import os
from .paths import resources

def enable_dpi_awareness():
    # Set before creating any HWND. System awareness is supported by Tk 8.6
    # without the mixed-monitor widget-resizing bugs of per-monitor-v2 mode.
    if os.name!='nt':return
    import ctypes
    try:ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError,OSError):
        try:ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError,OSError):pass

def configure(root):
    from tkinter import ttk
    from PIL import Image,ImageTk
    dpi=float(root.winfo_fpixels('1i'))
    root.tk.call('tk','scaling',dpi/72)
    scale=dpi/96
    style=ttk.Style(root)
    style.configure('Treeview',rowheight=round(24*scale))
    icon=resources()/'davilex/branding/icon.png'
    if icon.is_file():
        root._brand_icon=ImageTk.PhotoImage(Image.open(icon),master=root)
        root.iconphoto(True,root._brand_icon)
    return scale

def header(parent,root,width=360):
    from tkinter import ttk
    from PIL import Image,ImageTk
    path=resources()/'davilex/branding/titlebar.png'
    if not path.is_file():
        return ttk.Label(parent,text='Davilex Toolkit',font=('Segoe UI',20))
    image=Image.open(path);dpi=float(root.winfo_fpixels('1i'))/96
    target=round(width*dpi);image=image.resize((target,round(target*image.height/image.width)),Image.Resampling.LANCZOS)
    root._brand_title=ImageTk.PhotoImage(image,master=root)
    return ttk.Label(parent,image=root._brand_title)

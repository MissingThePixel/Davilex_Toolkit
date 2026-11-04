"""Desktop entry point for games, A2II Quick Race and RCS Explorer."""
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk,messagebox,filedialog
from .toolkit import ROOT,GAMES
from .quickrace import TRACKS,CARS,race_catalog
from .paths import command
from .languages import native_english
from . import settings
from .ui import enable_dpi_awareness,configure,header

SETTINGS=ROOT/'work/toolkit-settings.json'
RESOLUTIONS=('1920 x 1080','1280 x 720','2560 x 1440','3840 x 2160','Classic settings')
RENDERERS={'DDrawCompat':'ddrawcompat','Wine compatibility (D3D9)':'dxwrapper'}
LEGACY_WINE_BACKENDS={'Wine built-in DirectDraw','dgVoodoo (windowed test)',
                      'dgVoodoo (diagnostic)','DXWrapper (D3D9 test)'}


class Launcher:
    def __init__(self,root):
        self.root=root;self.running=False;self.messages=queue.Queue()
        root.title('Davilex Toolkit');scale=configure(root)
        root.minsize(min(round(590*scale),root.winfo_screenwidth()-60),min(round(480*scale),root.winfo_screenheight()-100))
        saved=settings.load()
        self.game=tk.StringVar(value=saved.get('game') if saved.get('game') in GAMES else next(iter(GAMES)))
        self.resolution=tk.StringVar(value=str(saved.get('resolution',RESOLUTIONS[0])))
        self.english=tk.BooleanVar(value=saved.get('english') is True)
        self.optional_english=self.english.get();self.previous_game=None
        self.controller=tk.BooleanVar(value=saved.get('controller') is True)
        self.installs=saved.get('installs',{}) if isinstance(saved.get('installs'),dict) else {}
        from .discovery import discover_from_known
        discovered=discover_from_known(self.installs)
        if discovered!=self.installs:
            self.installs=discovered;saved['installs']=discovered;settings.save(saved)
        self.install=tk.StringVar()
        self.track=tk.StringVar(value=TRACKS[0]);self.car=tk.StringVar(value=CARS[0])
        canvas=tk.Canvas(root,highlightthickness=0)
        scrollbar=ttk.Scrollbar(root,orient='vertical',command=canvas.yview)
        canvas.pack(side='left',fill='both',expand=True)
        self.scrollbar=scrollbar;self.canvas=canvas
        canvas.configure(yscrollcommand=scrollbar.set)
        frame=ttk.Frame(canvas,padding=round(22*scale))
        content=canvas.create_window(0,0,window=frame,anchor='nw')
        def fit_scrollbar():
            canvas.configure(scrollregion=canvas.bbox('all'))
            if frame.winfo_reqheight()>canvas.winfo_height()+1:
                if not scrollbar.winfo_manager():scrollbar.pack(side='right',fill='y',before=canvas)
            else:
                scrollbar.pack_forget();canvas.yview_moveto(0)
        frame.bind('<Configure>',lambda _:root.after_idle(fit_scrollbar))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(content,width=e.width))
        canvas.bind('<Configure>',lambda _:root.after_idle(fit_scrollbar),add='+')
        root.bind('<MouseWheel>',lambda e:canvas.yview_scroll(-int(e.delta/120),'units') if canvas.winfo_height()<frame.winfo_height() else None)
        header(frame,root).pack(anchor='center',pady=(0,10))
        ttk.Label(frame,text='Choose a game and launch options.').pack(anchor='w',pady=(2,18))
        ttk.Label(frame,text='Game').pack(anchor='w')
        self.games=ttk.Combobox(frame,textvariable=self.game,values=tuple(GAMES),state='readonly')
        self.games.pack(fill='x',pady=(3,12));self.games.bind('<<ComboboxSelected>>',self.refresh)
        ttk.Label(frame,text='Installation folder').pack(anchor='w')
        location=ttk.Frame(frame);location.pack(fill='x',pady=(3,12))
        self.location=ttk.Entry(location,textvariable=self.install,state='readonly')
        self.location.pack(side='left',fill='x',expand=True)
        self.browse=ttk.Button(location,text='Locate…',command=self.locate_install)
        self.browse.pack(side='right',padx=(8,0))
        ttk.Label(frame,text='Resolution (choose a preset or type width x height)').pack(anchor='w')
        ttk.Combobox(frame,textvariable=self.resolution,values=RESOLUTIONS).pack(fill='x',pady=(3,10))
        self.english_box=ttk.Checkbutton(frame,text='English text',variable=self.english)
        self.english_box.pack(anchor='w')
        saved_renderer=saved.get('renderer','DDrawCompat')
        if saved_renderer in LEGACY_WINE_BACKENDS:saved_renderer='Wine compatibility (D3D9)'
        self.renderer=tk.StringVar(value=saved_renderer if saved_renderer in RENDERERS else 'DDrawCompat')
        ttk.Label(frame,text='Graphics backend').pack(anchor='w',pady=(8,0))
        ttk.Combobox(frame,textvariable=self.renderer,values=tuple(RENDERERS),state='readonly').pack(fill='x',pady=(3,8))
        ttk.Checkbutton(frame,text='Controller enabler',variable=self.controller).pack(anchor='w')
        ttk.Label(frame,text='XInput controllers → legacy DirectInput / WinMM (via Xidi).').pack(anchor='w')
        ttk.Label(frame,text='Menus use keyboard/mouse. Escape opens the race pause menu.').pack(anchor='w',pady=(4,12))
        self.play=ttk.Button(frame,text='Play full game',command=lambda:self.launch(False))
        self.play.pack(fill='x')
        self.addon_button=ttk.Button(frame,text='Manage downloaded content...',command=self.manage_addons)
        self.addon_button.pack(fill='x',pady=(6,0))
        self.quick=ttk.LabelFrame(frame,text='Quick Race',padding=10)
        self.quick.pack(fill='x',pady=14)
        self.tracks=ttk.Combobox(self.quick,textvariable=self.track,values=TRACKS,state='readonly',width=28)
        self.tracks.grid(row=0,column=0,sticky='ew',padx=(0,8))
        self.cars=ttk.Combobox(self.quick,textvariable=self.car,values=CARS,state='readonly',width=18)
        self.cars.grid(row=0,column=1,sticky='ew');self.quick.columnconfigure(0,weight=1)
        self.race=ttk.Button(self.quick,text='Start selected race',command=lambda:self.launch(True))
        self.race.grid(row=1,column=0,columnspan=2,sticky='ew',pady=(8,0))
        ttk.Button(frame,text='Open RCS Explorer',command=self.viewer).pack(fill='x')
        self.status=tk.StringVar(value='Patches the selected installation. Changed-file backups are kept in work/install-backups. Windows may request write permission.')
        ttk.Label(frame,textvariable=self.status,wraplength=540).pack(anchor='w',pady=(14,0))
        self.refresh();root.protocol('WM_DELETE_WINDOW',self.close);root.after(150,self.poll)
        root.update_idletasks()
        root.geometry(f'{round(660*scale)}x{min(frame.winfo_reqheight()+4,root.winfo_screenheight()-round(100*scale))}')

    def refresh(self,event=None):
        self.play.configure(state='disabled' if self.running else 'normal')
        if not self.running:
            from .installed import baseline,locate
            if self.previous_game is not None and not native_english(self.previous_game):self.optional_english=self.english.get()
            self.english.set(True if native_english(self.game.get()) else self.optional_english)
            self.previous_game=self.game.get()
            self.english_box.configure(state='disabled' if native_english(self.game.get()) else 'normal')
            self.english_box.configure(text='English text (already English)' if native_english(self.game.get()) else 'English text')
            selected=self.installs.get(self.game.get())
            if selected and not Path(selected).is_dir():selected=None
            try:self.install.set(str(locate(GAMES[self.game.get()],selected)))
            except ValueError:
                try:self.install.set(str(locate(GAMES[self.game.get()])))
                except ValueError:self.install.set('')
            try:
                self.catalog=race_catalog(GAMES[self.game.get()],directory=Path(self.install.get()))
                for combo,value,kind in [(self.tracks,self.track,'tracks'),(self.cars,self.car,'cars')]:
                    labels=[x['label'] for x in self.catalog[kind]]
                    combo.configure(values=labels)
                    if value.get() not in labels:value.set(labels[0])
                self.catalog_error=None
            except (OSError,ValueError) as error:
                self.catalog_error=str(error)
                self.status.set('Quick Race unavailable: '+str(error))
        enabled=not self.running and not self.catalog_error
        self.race.configure(state='normal' if enabled else 'disabled')
        self.tracks.configure(state='readonly' if enabled else 'disabled')
        self.cars.configure(state='readonly' if enabled else 'disabled')
        self.addon_button.configure(state='normal' if not self.running and self.game.get()=='Europe Racer' else 'disabled')
        self.games.configure(state='disabled' if self.running else 'readonly')
        self.browse.configure(state='disabled' if self.running else 'normal')

    def locate_install(self):
        folder=filedialog.askdirectory(title='Select the existing game installation',initialdir=self.install.get(),parent=self.root)
        if not folder:return
        try:
            from .installed import locate
            directory=locate(GAMES[self.game.get()],folder)
        except (OSError,ValueError) as error:
            messagebox.showerror('Installation folder',str(error),parent=self.root);return
        self.installs[self.game.get()]=str(directory);self.install.set(str(directory));self.refresh()
        from .discovery import sibling_installs
        self.installs=sibling_installs(directory,self.installs)
        saved=settings.load();saved['installs']=self.installs;settings.save(saved)
        self.status.set(f'Ready. {len(self.installs)} game installations located.')

    def launch(self,quick,extra_arguments=None):
        if self.running:return
        import re
        arguments=[self.game.get()]
        from .installed import locate
        try:directory=locate(GAMES[self.game.get()],self.install.get())
        except (OSError,ValueError) as error:
            messagebox.showerror('Installation folder',str(error),parent=self.root);return
        arguments+=['--install',str(directory),'--renderer',RENDERERS[self.renderer.get()]]
        if extra_arguments:arguments+=extra_arguments
        resolution=self.resolution.get().strip()
        if resolution!='Classic settings':
            match=re.fullmatch(r'(\d+)\s*[xX×]\s*(\d+)',resolution)
            if not match:
                messagebox.showerror('Resolution','Enter a resolution such as 1920 x 1080.',parent=self.root);return
            width,height=map(int,match.groups())
            if not (640<=width<=8192 and 480<=height<=8192 and width*3>=height*4):
                messagebox.showerror('Resolution','Use 640x480 to 8192x8192, with a 4:3 or wider aspect ratio.',parent=self.root);return
            arguments+=['--width',str(width),'--height',str(height)]
        if self.english.get():arguments.append('--english')
        if self.controller.get():arguments.append('--controller')
        if quick:
            selected=next(x for x in self.catalog['tracks'] if x['label']==self.track.get())
            track=selected['id']
            car=next(x['id'] for x in self.catalog['cars'] if x['label']==self.car.get())
            arguments+=['--track',str(track),'--car',str(car)]
        SETTINGS.parent.mkdir(exist_ok=True)
        self.installs[self.game.get()]=str(directory)
        settings.save(dict(game=self.game.get(),resolution=resolution,
                          english=self.optional_english if native_english(self.game.get()) else self.english.get(),controller=self.controller.get(),renderer=self.renderer.get(),installs=self.installs))
        self.running=True;self.refresh();self.status.set('Updating downloaded content...' if extra_arguments else 'Running '+self.game.get()+'. Exit the game to return here.')
        def worker():
            try:
                from .elevated import execute
                code,detail=execute(arguments,directory)
                self.messages.put((code,detail.strip()))
            except OSError as error:
                detail='Launch did not complete: '+str(error)
                (ROOT/'work/toolkit-last-run.log').write_text(detail+'\n',encoding='utf-8')
                self.messages.put((1,detail))
        threading.Thread(target=worker,daemon=True).start()

    def manage_addons(self):
        from .addons import DONORS
        from .content_packs import choices,identify_source
        dialog=tk.Toplevel(self.root);dialog.title('Europe Racer downloaded content')
        dialog.transient(self.root)
        frame=ttk.Frame(dialog,padding=18);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='Import a source game’s cars and tracks into Europe Racer’s Downloads menus. Import all uses every source game found.',wraplength=470).pack(anchor='w')
        options=choices()
        selected=tk.StringVar(value=options[0]['label'])
        combo=ttk.Combobox(frame,textvariable=selected,values=[o['label'] for o in options],state='readonly',width=58)
        combo.pack(fill='x',pady=10)
        def install_selected():
            key=next(o['addon'] for o in options if o['label']==selected.get())
            dialog.destroy();self.launch(False,['--install-addon',key])
        ttk.Button(frame,text='Install selected content',command=install_selected).pack(fill='x')
        def locate_source():
            nonlocal options
            folder=filedialog.askdirectory(title='Select a source-game installation',parent=dialog)
            if not folder:return
            try:
                donor,source=identify_source(folder)
                game=next(name for name,profile in GAMES.items()if profile==DONORS[donor]['profile'])
                self.installs[game]=str(source)
                from .discovery import sibling_installs
                self.installs=sibling_installs(source,self.installs)
                try:saved=json.loads(SETTINGS.read_text(encoding='utf-8'))
                except (OSError,ValueError):saved={}
                if not isinstance(saved,dict):saved={}
                saved['installs']=self.installs;settings.save(saved)
                options=choices();combo.configure(values=[o['label']for o in options])
                selected.set(next(o['label']for o in options if o['addon']=='pack-'+donor))
            except (OSError,ValueError)as error:messagebox.showerror('Source game',str(error),parent=dialog)
        ttk.Button(frame,text='Locate source game...',command=locate_source).pack(fill='x',pady=(8,0))
        ttk.Label(frame,text='Track and car previews are imported automatically when available.',wraplength=470).pack(anchor='w',pady=(12,0))
        ttk.Label(frame,text='Only games found on this device are listed. Use Locate source game for another installation. Imported vehicles keep their names, country and type under Downloads.',wraplength=470).pack(anchor='w',pady=(12,0))

    def poll(self):
        try:
            code,detail=self.messages.get_nowait()
            self.running=False;self.refresh()
            self.status.set(('Game closed. Locked renderer cleanup will retry before the next launch.'
                             if 'Renderer cleanup pending:' in detail else 'Ready.') if code==0
                            else 'Launch failed. Details are in work/toolkit-last-run.log.')
            if code:messagebox.showerror('Game launch',detail[-1800:] or f'Exit code {code}',parent=self.root)
        except queue.Empty:pass
        self.root.after(150,self.poll)

    def viewer(self):
        subprocess.Popen(command('viewer'),cwd=ROOT,
                         creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

    def close(self):
        if self.running:
            self.status.set('Exit the game first so temporary settings and the display can be restored.');return
        self.root.destroy()


def main():
    enable_dpi_awareness()
    root=tk.Tk();Launcher(root);root.mainloop()


if __name__=='__main__':main()

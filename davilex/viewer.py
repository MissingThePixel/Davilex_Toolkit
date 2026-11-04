"""Desktop browser for Davilex RCS archives. Run: python -m davilex.viewer"""
from pathlib import Path
import io
import json
import queue
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import winsound
from .rcs import Archive, ArchiveError, convert_image
from .audio import pcm_wav
from .mesh import decode as decode_mesh, export_obj
from .media import CATEGORIES,category,ordered_entries,load_image,companion_palette,palette_from_file,texture_links
from .mesh_preview import render as render_mesh
from .textures import prepare as prepare_texture
from .texture_bindings import Resolver as TextureResolver

from .paths import ROOT,archive_root
from .ui import enable_dpi_awareness,configure


class Viewer(tk.Tk):
    def __init__(self):
        enable_dpi_awareness()
        super().__init__()
        scale=configure(self)
        self.title('Davilex RCS Explorer')
        self.geometry(f'{min(round(1220*scale),self.winfo_screenwidth()-40)}x{min(round(800*scale),self.winfo_screenheight()-100)}')
        self.minsize(min(round(960*scale),self.winfo_screenwidth()-60),min(round(620*scale),self.winfo_screenheight()-100))
        self.archive = None
        self.image_preview = None
        temp_root=ROOT/'.cache'
        temp_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='davilex-rcs-',dir=temp_root)
        self.events = queue.Queue()
        self.busy = False
        self.search = tk.StringVar()
        self.category_flags={name:tk.BooleanVar(value=True) for name in CATEGORIES}
        self.entry_categories={}
        self.sort_column='name'
        self.sort_descending=False
        self.palette=None
        self.palette_manual=False
        self.mesh=None
        self.texture=None
        self.texture_map={}
        self.texture_names={}
        self.yaw=.6;self.pitch=-.3;self.zoom=1
        self.drag=None
        self.wireframe=tk.BooleanVar()
        self.flip_v=tk.BooleanVar()
        self.colour_key=tk.BooleanVar(value=True)
        self.texture_note=tk.StringVar(value='')
        self.related_textures=tk.BooleanVar(value=True)
        self.texture_provenance={}
        self.palette_text=tk.StringVar(value='')
        self.raw = tk.BooleanVar()
        self.status = tk.StringVar(value='Open an IMG/IND pair, or choose an installed game archive.')
        self.path_text = tk.StringVar(value='No archive open')
        self.protocol('WM_DELETE_WINDOW', self.close)
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill='both', expand=True)
        top = ttk.Frame(outer)
        top.pack(fill='x')
        ttk.Label(top, text='RCS Explorer', font=('Segoe UI', 20, 'bold')).pack(side='left')
        ttk.Button(top, text='Open archive…', command=self.open_dialog).pack(side='right')
        ttk.Label(outer, textvariable=self.path_text, wraplength=1150).pack(fill='x', pady=(4,12))
        controls = ttk.Frame(outer)
        controls.pack(fill='x', pady=(0,12))
        self.presets = {}
        from .discovery import game_roots
        self.game_folders=list(game_roots())
        for name,folder in self.game_folders:
            for p in folder.rglob('*'):
                if p.suffix.casefold()=='.img' and any(q.stem.casefold()==p.stem.casefold() and q.suffix.casefold()=='.ind' for q in p.parent.iterdir()):
                    self.presets[name+' / '+str(p.relative_to(folder))]=p
        for p in (archive_root()).rglob('*'):
            if p.suffix.lower() == '.img' and any(q.stem.casefold()==p.stem.casefold() and q.suffix.lower()=='.ind' for q in p.parent.iterdir()):
                self.presets[str(p.relative_to(archive_root()))] = p
        for p in (ROOT/'analysis'/'disc-assets').rglob('*'):
            if p.suffix.lower()=='.img':
                self.presets['Disc assets / '+str(p.relative_to(ROOT/'analysis'/'disc-assets'))]=p
        for folder in (ROOT/'analysis/M25 Racer',ROOT/'reference/M25 Racer'):
            for p in folder.glob('*.img'):
                if any(q.stem.casefold()==p.stem.casefold() and q.suffix.lower()=='.ind' for q in folder.iterdir()):
                    self.presets['M25 Racer / '+p.name]=p
        self.preset = ttk.Combobox(controls, state='readonly', values=sorted(self.presets), width=42)
        self.preset.set('Choose an installed-game copy')
        self.preset.pack(side='left', padx=(0,12))
        self.preset.bind('<<ComboboxSelected>>', lambda _: self.open(self.presets[self.preset.get()]))
        ttk.Label(controls, text='Filter').pack(side='left', padx=(0,6))
        ttk.Entry(controls, textvariable=self.search).pack(side='left', fill='x', expand=True)
        self.search.trace_add('write', lambda *_: self.populate())
        categories=ttk.Frame(outer)
        categories.pack(fill='x',pady=(0,10))
        ttk.Label(categories,text='Show:').pack(side='left',padx=(0,8))
        for name,flag in self.category_flags.items():
            ttk.Checkbutton(categories,text=name,variable=flag,command=self.populate).pack(side='left',padx=(0,12))
        ttk.Button(categories,text='All',command=lambda:self.set_categories(True)).pack(side='left')
        ttk.Button(categories,text='None',command=lambda:self.set_categories(False)).pack(side='left',padx=4)
        split = ttk.Panedwindow(outer, orient='horizontal')
        split.pack(fill='both', expand=True)
        left = ttk.Frame(split)
        right = ttk.Frame(split, padding=(14,0,0,0))
        split.add(left, weight=3)
        split.add(right, weight=2)
        self.table = ttk.Treeview(left, columns=('name','kind','category','size'), show='headings', selectmode='extended')
        self.headings={'name':'Name','kind':'Extension','category':'Category','size':'Stored bytes'}
        for key, text, width in [('name','Name',230), ('kind','Extension',75),('category','Category',110), ('size','Stored bytes',105)]:
            self.table.heading(key, text=text,command=lambda column=key:self.sort_by(column))
            self.table.column(key, width=width, anchor='e' if key=='size' else 'w')
        scroll = ttk.Scrollbar(left, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.table.pack(fill='both', expand=True)
        self.table.bind('<<TreeviewSelect>>', lambda _: self.preview())
        ttk.Label(right, text='Preview & entry details', font=('Segoe UI',12,'bold')).pack(anchor='w')
        self.preview_label = ttk.Label(right, text='Select an entry to inspect it.', anchor='center')
        self.preview_label.pack(fill='both', expand=True, pady=10)
        self.preview_label.bind('<ButtonPress-1>',self.start_drag)
        self.preview_label.bind('<B1-Motion>',self.orbit)
        self.preview_label.bind('<MouseWheel>',self.zoom_mesh)
        preview_options=ttk.Frame(right)
        preview_options.pack(fill='x')
        ttk.Checkbutton(preview_options,text='Wireframe',variable=self.wireframe,command=self.draw_mesh).pack(side='left')
        ttk.Button(preview_options,text='Reset view',command=self.reset_view).pack(side='left',padx=8)
        ttk.Button(preview_options,text='Palette…',command=self.choose_palette).pack(side='right')
        ttk.Label(right,textvariable=self.palette_text,wraplength=430).pack(fill='x',pady=4)
        texture_options=ttk.Frame(right)
        texture_options.pack(fill='x',pady=(0,6))
        ttk.Label(texture_options,text='Texture:').pack(side='left')
        self.texture_choice=ttk.Combobox(texture_options,state='readonly',width=28,values=['No texture'])
        self.texture_choice.set('No texture')
        self.texture_choice.pack(side='left',fill='x',expand=True,padx=6)
        self.texture_choice.bind('<<ComboboxSelected>>',lambda _:self.guarded(self.set_texture))
        ttk.Checkbutton(texture_options,text='Flip V',variable=self.flip_v,command=self.draw_mesh).pack(side='left')
        layout_options=ttk.Frame(right);layout_options.pack(fill='x')
        ttk.Label(layout_options,text='Layout:').pack(side='left')
        self.texture_layout=ttk.Combobox(layout_options,state='readonly',width=14,values=['Auto','Full image','Main square'])
        self.texture_layout.set('Auto');self.texture_layout.pack(side='left',padx=6)
        self.texture_layout.bind('<<ComboboxSelected>>',lambda _:self.guarded(self.set_texture))
        ttk.Checkbutton(layout_options,text='Magenta colour key',variable=self.colour_key,command=lambda:self.guarded(self.set_texture)).pack(side='left')
        ttk.Label(right,textvariable=self.texture_note,wraplength=430).pack(fill='x',pady=4)
        ttk.Checkbutton(right,text='Use related archives with identical meshes',variable=self.related_textures,
                        command=lambda:self.guarded(self.preview)).pack(anchor='w')
        self.details = tk.Text(right, height=13, wrap='word', font=('Consolas',9), relief='flat', state='disabled')
        self.details.pack(fill='both')
        actions = ttk.Frame(outer)
        actions.pack(fill='x', pady=(14,8))
        for label, action in [('Export selected…', self.export_selected), ('Export filtered…', self.export_filtered),
                              ('Save PNG…', self.save_png), ('Save OBJ…', self.save_obj), ('Save PCM WAV…', self.save_wav),
                              ('Play audio', self.play), ('Stop', lambda: winsound.PlaySound(None,0))]:
            ttk.Button(actions, text=label, command=action).pack(side='left', padx=(0,6))
        ttk.Checkbutton(outer, text='Export stored bytes (skip decompression; for analysis)', variable=self.raw).pack(anchor='w')
        ttk.Label(outer, textvariable=self.status, wraplength=1150).pack(fill='x', pady=(8,0))
        self.after(100,self.poll)

    def open_dialog(self):
        path = filedialog.askopenfilename(title='Open RCS archive', filetypes=[('RCS image','*.img *.IMG'),('All files','*')])
        if path:
            self.open(path)

    def open(self,path):
        if self.busy:
            return
        try:
            archive = Archive(path)
        except (ArchiveError,OSError) as error:
            messagebox.showerror('Cannot open archive',str(error))
            return
        winsound.PlaySound(None,0)
        self.archive = archive
        self.entry_categories={e.index:category(archive,e) for e in archive.entries}
        self.texture_map=texture_links(archive)
        self.texture_names={f'{e.index:05d} · {e.name}':(archive,e) for e in archive.entries if self.entry_categories[e.index]=='Images'}
        self.base_texture_names=dict(self.texture_names)
        self.texture_resolver=TextureResolver(archive,archive_root(),[p for _,p in self.game_folders])
        self.texture_choice.configure(values=['No texture',*sorted(self.texture_names)])
        self.texture_choice.set('No texture')
        self.texture=None
        try:self.palette,label=companion_palette(archive)
        except Exception:self.palette,label=None,'Grayscale indices; choose a palette for original colours'
        self.palette_text.set(label)
        self.palette_manual=False
        self.mesh=None
        self.preview_label.configure(image='',text='Select an entry to inspect it.')
        self.path_text.set(str(archive.image))
        self.populate()

    def populate(self):
        selected=self.table.selection()
        self.table.delete(*self.table.get_children())
        if not self.archive:
            return
        categories={i:(self.category_flags[name].get(),name) for i,name in self.entry_categories.items()}
        for entry in ordered_entries(self.archive.entries,categories,self.search.get(),self.sort_column,self.sort_descending):
            self.table.insert('', 'end', iid=str(entry.index), values=(entry.name,entry.extension,self.entry_categories[entry.index],f'{entry.size:,}'))
        keep=[i for i in selected if self.table.exists(i)]
        if keep:self.table.selection_set(keep)
        else:
            self.mesh=None
            self.image_preview=None
            self.preview_label.configure(image='',text='Select an entry to inspect it.')
        for key,text in self.headings.items():
            self.table.heading(key,text=text+(' ▼' if self.sort_descending else ' ▲') if key==self.sort_column else text)
        self.status.set(f'{len(self.table.get_children()):,} of {len(self.archive.entries):,} entries. Exports preserve originals and decode zlib automatically.')

    def selected(self):
        if not self.archive:
            raise ArchiveError('Open an archive first.')
        selected = self.table.selection()
        if not selected:
            raise ArchiveError('Select at least one entry.')
        return [self.archive.entries[int(n)] for n in selected]

    def preview(self):
        if not self.archive or not self.table.selection():
            return
        entry = self.archive.entries[int(self.table.selection()[0])]
        self.image_preview = None
        self.mesh=None
        self.preview_label.configure(image='',text='No visual preview for this format.')
        try:
            info = self.archive.describe(entry)
            if self.entry_categories[entry.index] in {'Images','Fonts'} and entry.size:
                from PIL import Image,ImageTk
                palette=self.palette if entry.extension!='.img' or self.palette_manual else None
                with load_image(self.archive,entry,palette) as picture:
                    info['dimensions'] = list(picture.size)
                    picture.thumbnail((440,310))
                    self.image_preview = ImageTk.PhotoImage(picture.convert('RGBA'))
                if self.entry_categories[entry.index]=='Fonts':
                    info['palette']='IMG fonts default to grayscale; FNT uses the companion candidate. Palette selects custom colours.'
                self.preview_label.configure(image=self.image_preview,text='')
            elif info['type'] in {'WAV audio','MP3 audio'}:
                self.preview_label.configure(text='Audio available\n\nPlay here, export the original, or save a PCM WAV.')
            elif entry.extension=='.d3d':
                mesh=decode_mesh(self.archive.read(entry))
                info['type']='D3D mesh (supported binary variant)'
                info['mesh']={'vertices':len(mesh.vertices),'triangles':len(mesh.triangles),
                              'conversion':'OBJ geometry, UVs and normals; materials/colours omitted'}
                self.mesh=mesh
                self.texture_layout.set('Auto');self.flip_v.set(False)
                bindings=self.texture_resolver.resolve(entry,self.related_textures.get())
                self.texture_names=dict(self.base_texture_names);self.texture_provenance={}
                preferred=[]
                for binding in bindings:
                    name=f'{binding.entry.index:05d} · {binding.entry.name}'
                    if binding.related:
                        title=binding.archive.image.relative_to(archive_root()).parts[0]
                        name+=f' [{title}]'
                    self.texture_names[name]=(binding.archive,binding.entry)
                    self.texture_provenance[name]=binding.source
                    preferred.append(name)
                self.texture_choice.configure(values=['No texture',*dict.fromkeys(preferred+sorted(self.texture_names))])
                chosen=preferred[0] if preferred else 'No texture'
                self.texture_choice.set(chosen)
                self.set_texture(draw=False)
                self.reset_view()
                info['preview']='Drag to orbit; wheel to zoom. Texture auto-selected from INI model/texture pairs when unambiguous; manual selection available. Original materials/animation/lighting not reconstructed.'
                info['texture_candidates']=[{'image':b.entry.name,'archive':str(b.archive.image),'binding':b.source} for b in bindings]
            elif self.entry_categories[entry.index]=='Text':
                info['text']=self.archive.read(entry,16384).decode('cp1252','replace')
                self.preview_label.configure(text='Text preview in entry details below.')
            else:
                data=self.archive.read(entry,256)
                info['hex_preview']='\n'.join(f'{i:04x}  {data[i:i+16].hex(" ")}' for i in range(0,len(data),16))
        except Exception as error:
            self.mesh=None
            info = {'name':entry.name,'preview_error':str(error),'note':'Original export may still be available.'}
        self.details.configure(state='normal')
        self.details.delete('1.0','end')
        self.details.insert('1.0',json.dumps(info,indent=2))
        self.details.configure(state='disabled')

    def set_categories(self,value):
        for flag in self.category_flags.values():flag.set(value)
        self.populate()

    def sort_by(self,column):
        self.sort_descending=not self.sort_descending if self.sort_column==column else column=='size'
        self.sort_column=column
        self.populate()

    def draw_mesh(self):
        if self.mesh:
            from PIL import ImageTk
            self.image_preview=ImageTk.PhotoImage(render_mesh(self.mesh,yaw=self.yaw,pitch=self.pitch,zoom=self.zoom,wireframe=self.wireframe.get(),texture=self.texture,flip_v=self.flip_v.get()))
            self.preview_label.configure(image=self.image_preview,text='')

    def set_texture(self,draw=True):
        name=self.texture_choice.get()
        self.texture=None
        self.texture_note.set('')
        if name in self.texture_names:
            archive,entry=self.texture_names[name]
            palette=self.palette if archive.image==self.archive.image else companion_palette(archive)[0]
            with load_image(archive,entry,palette) as picture:
                self.texture,info=prepare_texture(picture,self.texture_layout.get(),self.colour_key.get())
            stored='×'.join(map(str,info['stored_size']));sampled='×'.join(map(str,info['sampled_size']))
            note=f'Sampling {sampled} from stored {stored}'
            if info['packed_mips_detected']:note+='; packed mipmaps detected'
            if name in self.texture_provenance:note+='\n'+self.texture_provenance[name]
            if archive.image!=self.archive.image:note+='\nTexture source: '+str(archive.image)
            self.texture_note.set(note)
        if draw:self.draw_mesh()

    def start_drag(self,event):self.drag=(event.x,event.y)

    def orbit(self,event):
        if self.mesh and self.drag:
            self.yaw+=(event.x-self.drag[0])*.015
            self.pitch+=(event.y-self.drag[1])*.015
            self.drag=(event.x,event.y)
            self.draw_mesh()

    def zoom_mesh(self,event):
        if self.mesh:
            self.zoom=max(.1,min(10,self.zoom*(1.1 if event.delta>0 else 1/1.1)))
            self.draw_mesh()

    def reset_view(self):
        self.yaw=.6;self.pitch=-.3;self.zoom=1
        self.draw_mesh()

    def choose_palette(self):
        path=filedialog.askopenfilename(title='Choose indexed image or 768-byte RGB palette',filetypes=[('Palette source','*.pcx *.png *.bmp *.pal *.act'),('All files','*')])
        if path:
            def action():
                self.palette=palette_from_file(path)
                self.palette_manual=True
                self.palette_text.set(str(path))
                self.preview()
            self.guarded(action)

    def job(self,worker):
        if self.busy:
            messagebox.showinfo('Operation running','Wait for the current export or conversion to finish.')
            return
        self.busy = True
        def run():
            try:
                self.events.put(('done',worker()))
            except Exception as error:
                self.events.put(('error',str(error)))
        threading.Thread(target=run,daemon=True).start()

    def poll(self):
        try:
            while True:
                kind,value = self.events.get_nowait()
                if kind in {'done','error'}:
                    self.busy = False
                self.status.set(value)
                if kind=='error':
                    messagebox.showerror('Operation failed',value)
        except queue.Empty:
            pass
        self.after(100,self.poll)

    def export(self,entries):
        if self.busy or not entries:
            return
        directory = filedialog.askdirectory(title=f'Export {len(entries)} entries into a new subfolder')
        if not directory:
            return
        # A fresh subfolder makes repeated exports safe and easy to distinguish.
        target = Path(tempfile.mkdtemp(prefix='rcs-export-',dir=directory))
        archive,raw = self.archive,self.raw.get()
        def work():
            count=0
            for i,entry in enumerate(entries):
                if entry.size:
                    archive.extract(entry,target,raw=raw)
                    count+=1
                if i%25==0:
                    self.events.put(('progress',f'Exporting {i+1}/{len(entries)}…'))
            return f'Exported {count:,} entries to {target}'
        self.job(work)

    def export_selected(self):
        self.guarded(lambda:self.export(self.selected()))

    def export_filtered(self):
        if self.archive:
            self.export([self.archive.entries[int(n)] for n in self.table.get_children()])

    def guarded(self,action):
        try:
            action()
        except Exception as error:
            messagebox.showerror('Cannot perform action',str(error))

    def save_png(self):
        def action():
            entry=self.selected()[0]
            path=filedialog.asksaveasfilename(title='Save decoded image',defaultextension='.png',initialfile=Path(entry.name).stem+'.png',filetypes=[('PNG image','*.png')])
            if path:
                archive=self.archive
                palette=self.palette if entry.extension!='.img' or self.palette_manual else None
                self.job(lambda:f'Saved {convert_image(archive,entry,path,palette)}')
        self.guarded(action)

    def audio_action(self,play=False):
        entry=self.selected()[0]
        if entry.extension not in {'.wav','.mp3'}:
            raise ArchiveError('Select a WAV or MP3 entry.')
        archive=self.archive
        destination=None if play else filedialog.asksaveasfilename(title='Save PCM WAV',defaultextension='.wav',initialfile=Path(entry.name).stem+'.wav',filetypes=[('WAV audio','*.wav')])
        if not play and not destination:
            return
        def work():
            folder=Path(tempfile.mkdtemp(dir=self.temp.name))
            source=archive.extract(entry,folder)
            target=folder/'preview.wav' if play else Path(destination)
            pcm_wav(source,target)
            if play:
                winsound.PlaySound(str(target),winsound.SND_FILENAME|winsound.SND_ASYNC)
                return f'Playing {entry.name}'
            return f'Saved {target}'
        self.job(work)

    def save_obj(self):
        def action():
            entry=self.selected()[0]
            if entry.extension!='.d3d':
                raise ArchiveError('Select a D3D model entry.')
            path=filedialog.asksaveasfilename(title='Save mesh geometry',defaultextension='.obj',
                initialfile=Path(entry.name).stem+'.obj',filetypes=[('OBJ mesh','*.obj')])
            if path:
                archive=self.archive
                self.job(lambda:f'Saved {export_obj(archive.read(entry),path)}')
        self.guarded(action)

    def play(self):
        self.guarded(lambda:self.audio_action(True))

    def save_wav(self):
        self.guarded(self.audio_action)

    def close(self):
        if self.busy:
            messagebox.showinfo('Operation running','Wait for the current operation before closing.')
            return
        winsound.PlaySound(None,0)
        self.temp.cleanup()
        self.destroy()


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',nargs='?',type=Path)
    args=parser.parse_args()
    viewer=Viewer()
    if args.archive:viewer.open(args.archive)
    viewer.mainloop()


if __name__=='__main__':main()

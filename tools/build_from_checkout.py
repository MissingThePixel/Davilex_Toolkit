"""Build the public Windows application from a self-contained source checkout."""
from pathlib import Path
import shutil,subprocess,sys

ROOT=Path(__file__).resolve().parents[1]

def main():
    resources=ROOT/'resources'
    if not (resources/'patches/binary-recipes.json').is_file():raise ValueError('Public resources directory is missing')
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean',
        '--onedir','--windowed','--noupx','--name','Davilex Toolkit',
        '--distpath',str(ROOT/'dist'),'--workpath',str(ROOT/'.cache/build'),
        '--specpath',str(ROOT/'.cache/spec'),'--paths',str(ROOT),
        '--icon',str(resources/'davilex/branding/icon.ico'),
        '--manifest',str(ROOT/'tools/packaging/toolkit.manifest'),
        '--add-data',str(resources)+';resources',
        '--hidden-import','_cffi_backend','--hidden-import','_miniaudio',
        '--exclude-module','scipy','--exclude-module','pandas','--exclude-module','matplotlib',
        '--exclude-module','pytest','--exclude-module','IPython','--exclude-module','jupyter',
        '--exclude-module','torch','--exclude-module','cv2','--exclude-module','tensorflow',
        '--exclude-module','sympy','--exclude-module','PyQt5',
        '--exclude-module','davilex._dxwrapper_data','--exclude-module','davilex._dgvoodoo_data',
        str(ROOT/'tools/portable_entry.py')],cwd=ROOT,check=True)
    app=ROOT/'dist/Davilex Toolkit'
    shutil.copyfile(app/'Davilex Toolkit.exe',app/'RCS Explorer.exe')
    for name in ('README.md','CREDITS.md','LICENSE','SECURITY-REVIEW.txt'):
        shutil.copyfile(ROOT/name,app/name)
    for name in ('assets','licenses'):shutil.copytree(ROOT/name,app/name,dirs_exist_ok=True)
    print('Built:',app)

if __name__=='__main__':main()

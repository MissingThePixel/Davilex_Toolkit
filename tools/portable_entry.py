from pathlib import Path
import sys

if not getattr(sys,'frozen',False):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from davilex.entry import guarded_main

if __name__=='__main__':guarded_main()

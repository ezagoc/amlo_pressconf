"""Explicit bounded Tiempo v5 collection; no implicit network permission."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crawler_core.tiempo_scheduler_v5 import main
if __name__=='__main__':raise SystemExit(main())

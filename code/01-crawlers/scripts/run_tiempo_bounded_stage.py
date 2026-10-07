"""Explicit one-child bounded continuation; prepare and inspect are offline."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawler_core.tiempo_bounded_stage import main
if __name__ == '__main__':
    raise SystemExit(main())

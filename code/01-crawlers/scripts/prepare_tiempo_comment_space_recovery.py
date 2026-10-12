#!/usr/bin/env python3
"""Kevin: prepare the exact stopped1517 successor without HTTP requests."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crawler_core.tiempo_comment_space_recovery import main
if __name__=='__main__':main()

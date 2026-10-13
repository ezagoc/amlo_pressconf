#!/usr/bin/env python3
"""Kevin: prepare a paused1600-media-URL successor without network calls."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crawler_core.tiempo_media_url_recovery import main
if __name__=='__main__':main()

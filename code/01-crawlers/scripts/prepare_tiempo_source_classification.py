"""Kevin: offline334 successor preparation; never starts a collector."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crawler_core.tiempo_source_classification_recovery import main
if __name__=='__main__':main()

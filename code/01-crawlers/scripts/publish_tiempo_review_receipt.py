"""Kevin: validate and exclusively publish a complete actual-AI reading receipt."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawler_core.tiempo_review_publish import main
if __name__ == '__main__':
    raise SystemExit(main())

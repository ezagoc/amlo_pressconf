"""Run or resume a <=80-URL Tiempo pilot in an isolated Dropbox pilot folder."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
CRAWLER_DIR = SCRIPT_DIR.parent
REPO_ROOT = SCRIPT_DIR.parents[2]
# Prefer the repository root project_paths module (which loads .env).
sys.path.insert(0, str(CRAWLER_DIR))
sys.path.insert(0, str(REPO_ROOT))

from project_paths import media_root  # noqa: E402
from crawler_core.tiempo_pilot import PilotError, run_pilot  # noqa: E402


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="CSV with sample_id,url,expected_year,selection_reason,expected_kind.")
    parser.add_argument("--run-dir", type=Path, required=True, help="An independent MEDIA_ROOT/data/00-newspaper_data/crawler/pilots/ subfolder containing Kevin_NOTE.md.")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--retry-errors", action="store_true", help="Retry existing errors only, after a backup. Successful URLs are skipped.")
    mode.add_argument("--export-only", action="store_true", help="Regenerate pilot exports without making requests or parsing HTML.")
    mode.add_argument("--reparse-cache", action="store_true", help="Back up and reparse complete local snapshots without network requests.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        summary = run_pilot(args.input, args.run_dir, media_root(), repo_root=REPO_ROOT,
                            pause_seconds=args.pause_seconds, timeout=args.timeout, retry_errors=args.retry_errors,
                            export_only=args.export_only, reparse_cache=args.reparse_cache)
    except (PilotError, OSError) as exc:
        print(f"Pilot stopped: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 130 if summary["interrupted"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

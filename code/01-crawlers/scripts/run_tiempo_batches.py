"""Freeze, inspect or run a bounded number of operator-gated Tiempo batches."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
CRAWLER_DIR = SCRIPT_DIR.parent
REPO_ROOT = SCRIPT_DIR.parents[2]
sys.path.insert(0, str(CRAWLER_DIR))
sys.path.insert(0, str(REPO_ROOT))

from project_paths import media_root  # noqa: E402
from crawler_core.tiempo_batches import BatchError, freeze_plan, run_batches, status, retry_queue  # noqa: E402
from crawler_core.tiempo_pilot import PilotError  # noqa: E402


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("freeze", "run", "status", "retry-queue"):
        item = sub.add_parser(command)
        item.add_argument("--run-dir", required=True, type=Path)
        if command == "freeze":
            item.add_argument("--input", required=True, type=Path)
            item.add_argument("--batch-size", type=int, default=40)
            item.add_argument("--pause-seconds", type=float, default=1.0)
            item.add_argument("--timeout", type=float, default=45.0)
            item.add_argument("--min-free-bytes", type=int, default=10 * 1024**3)
            item.add_argument("--max-consecutive-system-errors", type=int, default=3)
            item.add_argument("--max-system-error-fraction", type=float, default=0.25)
            item.add_argument("--error-fraction-min-results", type=int, default=8)
            item.add_argument("--min-reviewed-per-batch", type=int, default=3)
        elif command == "run":
            item.add_argument("--max-batches", required=True, type=int, help="1–10; no run-all mode.")
        elif command == "retry-queue":
            item.add_argument("--group", action="append", required=True, help="Explicit error group; repeat to combine.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        if args.command == "freeze":
            settings = {k: v for k, v in vars(args).items() if k not in {"command", "input", "run_dir"}}
            result = freeze_plan(args.input, args.run_dir, media_root(), repo_root=REPO_ROOT, **settings)
        elif args.command == "run":
            result = run_batches(args.run_dir, media_root(), repo_root=REPO_ROOT, max_batches=args.max_batches)
        elif args.command == "status":
            result = status(args.run_dir)
        else:
            result = {"retry_queue": str(retry_queue(args.run_dir, args.group)), "requests_made": 0}
    except (BatchError, PilotError, OSError, ValueError) as exc:
        print(f"Batch workflow stopped: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 3 if result.get("status") in {"halted", "interrupted", "awaiting_review"} else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Discover historical newspaper URLs through the GDELT DOC API."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
CRAWLER_DIR = SCRIPT_DIR.parents[0]
CODE_DIR = SCRIPT_DIR.parents[1]
REPO_ROOT = SCRIPT_DIR.parents[2]

for path in (CRAWLER_DIR, CODE_DIR, REPO_ROOT):
    sys.path.insert(0, str(path))

from crawler_core.gdelt import (  # noqa: E402
    GDELT_SOURCES,
    discover_gdelt_urls,
    load_gdelt_urls,
    write_gdelt_outputs,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Checkpointed GDELT URL discovery.")
    parser.add_argument("--source-id", action="append", choices=sorted(GDELT_SOURCES), required=True)
    parser.add_argument("--from-date", type=date.fromisoformat, required=True)
    parser.add_argument("--to-date", type=date.fromisoformat, required=True)
    parser.add_argument("--state-db", type=Path, default=REPO_ROOT / "tmp" / "gdelt" / "gdelt.sqlite")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "tmp" / "gdelt" / "discovery")
    parser.add_argument("--reports-dir", type=Path, default=REPO_ROOT / "tmp" / "gdelt" / "reports")
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--max-records", type=int, default=250)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--request-interval-seconds", type=float, default=5.2)
    parser.add_argument("--request-retries", type=int, default=3)
    parser.add_argument("--retry-backoff-seconds", type=float, default=10.0)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    discover_gdelt_urls(
        args.source_id,
        from_date=args.from_date,
        to_date=args.to_date,
        state_db=args.state_db,
        window_days=args.window_days,
        max_records=args.max_records,
        timeout=args.timeout,
        request_interval_seconds=max(5.0, args.request_interval_seconds),
        request_retries=args.request_retries,
        retry_backoff_seconds=args.retry_backoff_seconds,
        resume=args.resume,
    )
    discovered = load_gdelt_urls(args.state_db)
    outputs = write_gdelt_outputs(discovered, args.output_dir, args.reports_dir)
    for output in outputs:
        print(f"{output.source_id}: {output.rows:,} unique GDELT URLs")
        print(f"  CSV: {output.csv_path}")
        print(f"  parquet: {output.parquet_path or output.parquet_error}")
        print(f"  report: {output.report_path}")


if __name__ == "__main__":
    main()

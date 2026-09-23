"""Discover El Universal article URLs through its date-filtered public search index."""

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

from crawler_core.eluniversal import (  # noqa: E402
    discover_eluniversal_urls,
    finalize_eluniversal_checkpoints,
)
from project_paths import media_output_path  # noqa: E402


DEFAULT_DISCOVERY_PARTS = ("data", "00-newspaper_data", "crawler", "discovery", ".keep")
DEFAULT_REPORTS_PARTS = ("data", "00-newspaper_data", "crawler", "reports", ".keep")


def iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Checkpointed daily historical URL discovery for El Universal."
    )
    parser.add_argument("--from-date", type=iso_date, default=date(2010, 1, 1))
    parser.add_argument("--to-date", type=iso_date, default=date.today())
    parser.add_argument("--discovery-dir", type=Path, default=None)
    parser.add_argument("--reports-dir", type=Path, default=None)
    parser.add_argument("--checkpoint-dir", type=Path, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-pages-per-day", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    parser.add_argument("--request-retries", type=int, default=2)
    parser.add_argument("--retry-backoff-seconds", type=float, default=2.0)
    parser.add_argument("--limit-days", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    discovery_dir = args.discovery_dir or media_output_path(*DEFAULT_DISCOVERY_PARTS).parent
    reports_dir = args.reports_dir or media_output_path(*DEFAULT_REPORTS_PARTS).parent
    checkpoint_dir = args.checkpoint_dir or discovery_dir / "eluniversal_queryly_checkpoints"
    discover_eluniversal_urls(
        from_date=args.from_date,
        to_date=args.to_date,
        checkpoint_dir=checkpoint_dir,
        resume=args.resume,
        workers=args.workers,
        batch_size=args.batch_size,
        max_pages_per_day=args.max_pages_per_day,
        timeout=args.timeout,
        pause_seconds=args.pause_seconds,
        request_retries=args.request_retries,
        retry_backoff_seconds=args.retry_backoff_seconds,
        limit_days=args.limit_days,
    )
    outputs, summary = finalize_eluniversal_checkpoints(
        checkpoint_dir,
        discovery_dir,
        reports_dir,
    )
    print(f"Discovered rows: {summary.rows:,}")
    print(f"Discovered URLs: {summary.urls:,}")
    print(f"Duplicate URLs skipped: {summary.duplicates_skipped:,}")
    print(f"Error rows: {summary.errors:,}")
    print(f"Wrote CSV: {outputs.discovered_csv}")
    if outputs.discovered_parquet:
        print(f"Wrote parquet: {outputs.discovered_parquet}")
    else:
        print(f"Skipped parquet: {outputs.parquet_error}")
    print(f"Wrote report: {outputs.report_path}")


if __name__ == "__main__":
    main()

"""Discover archived Aristegui Noticias articles through checkpointed CDX windows."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
CRAWLER_DIR = SCRIPT_DIR.parents[0]
CODE_DIR = SCRIPT_DIR.parents[1]
REPO_ROOT = SCRIPT_DIR.parents[2]
for path in (CRAWLER_DIR, CODE_DIR, REPO_ROOT):
    sys.path.insert(0, str(path))

from crawler_core.aristegui_wayback import (  # noqa: E402
    discover_aristegui_wayback_urls,
    write_aristegui_wayback_outputs,
)
from project_paths import media_output_path  # noqa: E402


DEFAULT_DISCOVERY_PARTS = ("data", "00-newspaper_data", "crawler", "discovery", ".keep")
DEFAULT_REPORTS_PARTS = ("data", "00-newspaper_data", "crawler", "reports", ".keep")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Checkpointed Wayback discovery for Aristegui Noticias.")
    parser.add_argument("--discovery-dir", type=Path, default=None)
    parser.add_argument("--reports-dir", type=Path, default=None)
    parser.add_argument("--checkpoint-dir", type=Path, default=None)
    parser.add_argument("--from-year", type=int, default=2012)
    parser.add_argument("--to-year", type=int, default=2026)
    parser.add_argument("--pattern", action="append", default=None)
    parser.add_argument("--limit-per-page", type=int, default=1_000)
    parser.add_argument("--max-pages-per-query", type=int, default=100)
    parser.add_argument("--max-urls", type=int, default=400_000)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    parser.add_argument("--body-text-limit", type=int, default=80_000_000)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    discovery_dir = args.discovery_dir or media_output_path(*DEFAULT_DISCOVERY_PARTS).parent
    reports_dir = args.reports_dir or media_output_path(*DEFAULT_REPORTS_PARTS).parent
    checkpoint_dir = args.checkpoint_dir or discovery_dir / "aristeguinoticias_wayback_checkpoints"
    discovered = discover_aristegui_wayback_urls(
        from_year=args.from_year,
        to_year=args.to_year,
        patterns=args.pattern,
        limit_per_page=args.limit_per_page,
        max_pages_per_query=args.max_pages_per_query,
        max_urls=args.max_urls,
        timeout=args.timeout,
        pause_seconds=args.pause_seconds,
        body_text_limit=args.body_text_limit,
        checkpoint_dir=checkpoint_dir,
        resume=args.resume,
    )
    outputs = write_aristegui_wayback_outputs(discovered, discovery_dir, reports_dir)
    print(f"Discovered rows: {len(discovered):,}")
    print(f"Discovered archived URLs: {discovered['url'].notna().sum() if 'url' in discovered else 0:,}")
    print(f"Wrote CSV: {outputs.discovered_csv}")
    if outputs.discovered_parquet:
        print(f"Wrote parquet: {outputs.discovered_parquet}")
    else:
        print(f"Skipped parquet: {outputs.parquet_error}")
    print(f"Wrote report: {outputs.report_path}")


if __name__ == "__main__":
    main()

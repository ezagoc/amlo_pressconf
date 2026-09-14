"""Discover article URLs from RSS and Atom feeds."""

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

from crawler_core.rss import (  # noqa: E402
    build_rss_report,
    discover_rss_urls,
    load_rss_sources,
    write_rss_outputs,
)
from project_paths import media_input_path, media_output_path  # noqa: E402


DEFAULT_CAPABILITIES = media_input_path(
    "data",
    "00-newspaper_data",
    "crawler",
    "registry",
    "crawl_capabilities.csv",
)
DEFAULT_DISCOVERY_PARTS = ("data", "00-newspaper_data", "crawler", "discovery", ".keep")
DEFAULT_REPORTS_PARTS = ("data", "00-newspaper_data", "crawler", "reports", ".keep")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover article URLs from RSS/Atom feeds.")
    parser.add_argument("--capabilities", type=Path, default=DEFAULT_CAPABILITIES)
    parser.add_argument("--discovery-dir", type=Path, default=None)
    parser.add_argument("--reports-dir", type=Path, default=None)
    parser.add_argument("--source-id", action="append", default=None)
    parser.add_argument("--limit-sources", type=int, default=None)
    parser.add_argument(
        "--include-any-rss",
        action="store_true",
        help="Use every source with rss_available, not only recommended_strategy == rss.",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--pause-seconds", type=float, default=0.2)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    discovery_dir = args.discovery_dir or media_output_path(*DEFAULT_DISCOVERY_PARTS).parent
    reports_dir = args.reports_dir or media_output_path(*DEFAULT_REPORTS_PARTS).parent
    sources = load_rss_sources(args.capabilities, include_any_rss=args.include_any_rss)
    discovered = discover_rss_urls(
        sources,
        source_ids=args.source_id,
        limit_sources=args.limit_sources,
        timeout=args.timeout,
        pause_seconds=args.pause_seconds,
    )
    report = build_rss_report(discovered)
    outputs = write_rss_outputs(discovered, report, discovery_dir, reports_dir)
    print(f"RSS sources considered: {len(sources):,}")
    print(f"Discovered rows: {len(discovered):,}")
    print(f"Wrote CSV: {outputs.discovered_csv}")
    if outputs.discovered_parquet:
        print(f"Wrote parquet: {outputs.discovered_parquet}")
    else:
        print(f"Skipped parquet: {outputs.parquet_error}")
    print(f"Wrote report: {outputs.report_path}")


if __name__ == "__main__":
    main()

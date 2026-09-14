"""Discover article URLs from source sitemaps."""

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

from crawler_core.sitemaps import (  # noqa: E402
    build_sitemap_report,
    discover_sitemap_urls,
    load_sitemap_sources,
    write_sitemap_outputs,
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
    parser = argparse.ArgumentParser(description="Discover article URLs from XML sitemaps.")
    parser.add_argument("--capabilities", type=Path, default=DEFAULT_CAPABILITIES)
    parser.add_argument("--discovery-dir", type=Path, default=None)
    parser.add_argument("--reports-dir", type=Path, default=None)
    parser.add_argument("--source-id", action="append", default=None)
    parser.add_argument("--limit-sources", type=int, default=None)
    parser.add_argument(
        "--include-any-sitemap",
        action="store_true",
        help="Use every source with sitemap_available, not only recommended_strategy == sitemap.",
    )
    parser.add_argument("--max-sitemaps-per-source", type=int, default=100)
    parser.add_argument("--max-urls-per-source", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--pause-seconds", type=float, default=0.2)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    discovery_dir = args.discovery_dir or media_output_path(*DEFAULT_DISCOVERY_PARTS).parent
    reports_dir = args.reports_dir or media_output_path(*DEFAULT_REPORTS_PARTS).parent

    sources = load_sitemap_sources(
        args.capabilities,
        include_any_sitemap=args.include_any_sitemap,
    )
    discovered = discover_sitemap_urls(
        sources,
        source_ids=args.source_id,
        limit_sources=args.limit_sources,
        max_sitemaps_per_source=args.max_sitemaps_per_source,
        max_urls_per_source=args.max_urls_per_source,
        timeout=args.timeout,
        pause_seconds=args.pause_seconds,
    )
    report = build_sitemap_report(discovered)
    outputs = write_sitemap_outputs(discovered, report, discovery_dir, reports_dir)

    print(f"Sitemap sources considered: {len(sources):,}")
    print(f"Discovered rows: {len(discovered):,}")
    print(f"Wrote CSV: {outputs.discovered_csv}")
    if outputs.discovered_parquet:
        print(f"Wrote parquet: {outputs.discovered_parquet}")
    else:
        print(f"Skipped parquet: {outputs.parquet_error}")
    print(f"Wrote report: {outputs.report_path}")


if __name__ == "__main__":
    main()

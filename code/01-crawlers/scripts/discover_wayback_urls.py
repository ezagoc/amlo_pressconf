"""Discover article URLs from the Internet Archive Wayback CDX index."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
CRAWLER_DIR = SCRIPT_DIR.parents[0]
CODE_DIR = SCRIPT_DIR.parents[1]
REPO_ROOT = SCRIPT_DIR.parents[2]

for path in (CRAWLER_DIR, CODE_DIR, REPO_ROOT):
    sys.path.insert(0, str(path))

from crawler_core.wayback import (  # noqa: E402
    build_wayback_report,
    dedupe_wayback_discovery,
    discover_wayback_urls,
    load_wayback_sources,
    write_wayback_outputs,
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
    parser = argparse.ArgumentParser(
        description="Discover likely article URLs from the Internet Archive Wayback CDX index."
    )
    parser.add_argument("--capabilities", type=Path, default=DEFAULT_CAPABILITIES)
    parser.add_argument("--discovery-dir", type=Path, default=None)
    parser.add_argument("--reports-dir", type=Path, default=None)
    parser.add_argument("--source-id", action="append", default=None)
    parser.add_argument("--limit-sources", type=int, default=None)
    parser.add_argument(
        "--strategy",
        action="append",
        default=None,
        help="Optional recommended_strategy filter. Can be repeated.",
    )
    parser.add_argument("--from", dest="from_timestamp", default=None, help="Wayback start timestamp, e.g. 20180101.")
    parser.add_argument("--to", dest="to_timestamp", default=None, help="Wayback end timestamp, e.g. 20261231.")
    parser.add_argument(
        "--date-window",
        choices=["none", "year", "month"],
        default="none",
        help="Split the date range into smaller Wayback CDX queries.",
    )
    parser.add_argument(
        "--path-pattern",
        action="append",
        default=None,
        help="Article path prefix to query, e.g. juarez or nacional. Can be repeated.",
    )
    parser.add_argument(
        "--include-broad-domain",
        action="store_true",
        help="Also query the broad domain pattern. This may be slow on large sites.",
    )
    parser.add_argument("--limit-per-page", type=int, default=1_000)
    parser.add_argument("--max-pages-per-query", type=int, default=10)
    parser.add_argument("--max-urls-per-source", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    parser.add_argument("--body-text-limit", type=int, default=80_000_000)
    parser.add_argument(
        "--append-existing",
        action="store_true",
        help=(
            "Merge new rows into discovered_urls_wayback.*. When --source-id is "
            "used, previous rows for those source IDs are replaced."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    discovery_dir = args.discovery_dir or media_output_path(*DEFAULT_DISCOVERY_PARTS).parent
    reports_dir = args.reports_dir or media_output_path(*DEFAULT_REPORTS_PARTS).parent

    sources = load_wayback_sources(
        args.capabilities,
        strategies=set(args.strategy or []) or None,
    )
    discovered = discover_wayback_urls(
        sources,
        source_ids=args.source_id,
        limit_sources=args.limit_sources,
        from_timestamp=args.from_timestamp,
        to_timestamp=args.to_timestamp,
        date_window=args.date_window,
        path_patterns=args.path_pattern,
        include_broad_domain=args.include_broad_domain,
        limit_per_page=args.limit_per_page,
        max_pages_per_query=args.max_pages_per_query,
        max_urls_per_source=args.max_urls_per_source,
        timeout=args.timeout,
        pause_seconds=args.pause_seconds,
        body_text_limit=args.body_text_limit,
    )
    if args.append_existing:
        discovered = merge_existing_discovery(
            discovery_dir,
            discovered,
            replace_source_ids=set(args.source_id or []),
        )
    report = build_wayback_report(discovered)
    outputs = write_wayback_outputs(discovered, report, discovery_dir, reports_dir)

    print(f"Wayback sources considered: {len(sources):,}")
    print(f"Discovered rows: {len(discovered):,}")
    print(f"Wrote CSV: {outputs.discovered_csv}")
    if outputs.discovered_parquet:
        print(f"Wrote parquet: {outputs.discovered_parquet}")
    else:
        print(f"Skipped parquet: {outputs.parquet_error}")
    print(f"Wrote report: {outputs.report_path}")


def merge_existing_discovery(
    discovery_dir: Path,
    discovered: pd.DataFrame,
    *,
    replace_source_ids: set[str],
) -> pd.DataFrame:
    """Merge new Wayback rows with an existing discovery output."""
    parquet_path = discovery_dir / "discovered_urls_wayback.parquet"
    csv_path = discovery_dir / "discovered_urls_wayback.csv"
    existing = pd.DataFrame()
    if parquet_path.exists():
        existing = pd.read_parquet(parquet_path)
    elif csv_path.exists():
        existing = pd.read_csv(csv_path)

    if existing.empty:
        return discovered
    if replace_source_ids and "source_id" in existing.columns:
        existing = existing[~existing["source_id"].isin(replace_source_ids)].copy()
    merged = pd.concat([existing, discovered], ignore_index=True)
    return dedupe_wayback_discovery(merged)


if __name__ == "__main__":
    main()

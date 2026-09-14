"""Discover article URLs from Common Crawl CDX indexes."""

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

from crawler_core.commoncrawl import (  # noqa: E402
    build_commoncrawl_report,
    discover_commoncrawl_urls,
    load_commoncrawl_indexes,
    load_commoncrawl_sources,
    write_commoncrawl_outputs,
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
        description="Discover likely article URLs from Common Crawl CDX indexes."
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
    parser.add_argument(
        "--index-id",
        action="append",
        default=None,
        help="Common Crawl index ID, e.g. CC-MAIN-2026-34. Can be repeated.",
    )
    parser.add_argument("--year", action="append", type=int, default=None)
    parser.add_argument("--limit-indexes", type=int, default=None)
    parser.add_argument(
        "--path-pattern",
        action="append",
        default=None,
        help="Article path prefix to query, e.g. juarez or nacional. Can be repeated.",
    )
    parser.add_argument(
        "--include-broad-domain",
        action="store_true",
        help="Also query the broad domain pattern. This may be slow or return 504s on large sites.",
    )
    parser.add_argument("--limit-per-query", type=int, default=50_000)
    parser.add_argument("--max-urls-per-source", type=int, default=None)
    parser.add_argument("--page-size", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    parser.add_argument("--body-text-limit", type=int, default=80_000_000)
    parser.add_argument(
        "--append-existing",
        action="store_true",
        help=(
            "Merge new rows into discovered_urls_commoncrawl.*. When --source-id "
            "is used, previous rows for those source IDs are replaced."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    discovery_dir = args.discovery_dir or media_output_path(*DEFAULT_DISCOVERY_PARTS).parent
    reports_dir = args.reports_dir or media_output_path(*DEFAULT_REPORTS_PARTS).parent

    sources = load_commoncrawl_sources(
        args.capabilities,
        strategies=set(args.strategy or []) or None,
    )
    index_ids = load_commoncrawl_indexes(
        index_ids=args.index_id,
        years=set(args.year or []) or None,
        limit_indexes=args.limit_indexes,
        timeout=args.timeout,
    )
    print(f"Common Crawl indexes selected: {', '.join(index_ids)}")

    discovered = discover_commoncrawl_urls(
        sources,
        index_ids=index_ids,
        source_ids=args.source_id,
        limit_sources=args.limit_sources,
        path_patterns=args.path_pattern,
        include_broad_domain=args.include_broad_domain,
        limit_per_query=args.limit_per_query,
        max_urls_per_source=args.max_urls_per_source,
        page_size=args.page_size,
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
    report = build_commoncrawl_report(discovered)
    outputs = write_commoncrawl_outputs(discovered, report, discovery_dir, reports_dir)

    print(f"Common Crawl sources considered: {len(sources):,}")
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
    """Merge new Common Crawl rows with an existing discovery output."""
    parquet_path = discovery_dir / "discovered_urls_commoncrawl.parquet"
    csv_path = discovery_dir / "discovered_urls_commoncrawl.csv"
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
    if {"source_id", "url"}.issubset(merged.columns):
        url_rows = merged[merged["url"].notna()].drop_duplicates(["source_id", "url"], keep="last")
        error_rows = merged[merged["url"].isna()]
        merged = pd.concat([url_rows, error_rows], ignore_index=True)
    return merged.reset_index(drop=True)


if __name__ == "__main__":
    main()

"""Discover article URLs from category/archive listing pages."""

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

from crawler_core.category_pagination import (  # noqa: E402
    build_category_report,
    discover_category_urls,
    load_category_sources,
    write_category_outputs,
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
        description="Discover article URLs by crawling category/archive listing pages."
    )
    parser.add_argument("--capabilities", type=Path, default=DEFAULT_CAPABILITIES)
    parser.add_argument("--discovery-dir", type=Path, default=None)
    parser.add_argument("--reports-dir", type=Path, default=None)
    parser.add_argument("--source-id", action="append", default=None)
    parser.add_argument("--limit-sources", type=int, default=None)
    parser.add_argument(
        "--append-existing",
        action="store_true",
        help=(
            "Merge new rows into discovered_urls_category.*. When --source-id is "
            "used, previous rows for those source IDs are replaced."
        ),
    )
    parser.add_argument(
        "--include-custom-html",
        action="store_true",
        help="Also try sources whose current recommendation is custom_html_probe.",
    )
    parser.add_argument("--max-pages-per-category", type=int, default=25)
    parser.add_argument("--max-categories-per-source", type=int, default=None)
    parser.add_argument("--max-urls-per-source", type=int, default=None)
    parser.add_argument(
        "--pagination-style",
        choices=["auto", "path_page", "path_number", "query_page", "query_pagina", "none"],
        default="auto",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--pause-seconds", type=float, default=0.2)
    parser.add_argument(
        "--fetch-profile",
        choices=["default", "browser"],
        default="browser",
        help="HTTP request profile. Category discovery defaults to browser-like headers.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    discovery_dir = args.discovery_dir or media_output_path(*DEFAULT_DISCOVERY_PARTS).parent
    reports_dir = args.reports_dir or media_output_path(*DEFAULT_REPORTS_PARTS).parent

    sources = load_category_sources(
        args.capabilities,
        include_custom_html=args.include_custom_html,
    )
    discovered = discover_category_urls(
        sources,
        source_ids=args.source_id,
        limit_sources=args.limit_sources,
        max_pages_per_category=args.max_pages_per_category,
        max_categories_per_source=args.max_categories_per_source,
        max_urls_per_source=args.max_urls_per_source,
        pagination_style=args.pagination_style,
        timeout=args.timeout,
        pause_seconds=args.pause_seconds,
        fetch_profile=args.fetch_profile,
    )
    if args.append_existing:
        discovered = merge_existing_discovery(
            discovery_dir,
            discovered,
            replace_source_ids=set(args.source_id or []),
        )
    report = build_category_report(discovered)
    outputs = write_category_outputs(discovered, report, discovery_dir, reports_dir)

    print(f"Category sources considered: {len(sources):,}")
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
    """Merge new category rows with an existing category discovery output."""
    parquet_path = discovery_dir / "discovered_urls_category.parquet"
    csv_path = discovery_dir / "discovered_urls_category.csv"
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

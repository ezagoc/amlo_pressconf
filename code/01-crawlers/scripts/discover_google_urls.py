"""Discover newspaper article URLs with Google Programmable Search."""

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

from crawler_core.google_search import (  # noqa: E402
    build_google_report,
    dedupe_google_discovery,
    discover_google_urls,
    google_credentials,
    load_google_sources,
    parse_date,
    write_google_outputs,
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
        description="Discover article URLs via Google Programmable Search day-level date-in-URL queries."
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
    parser.add_argument("--from", dest="from_date", required=True, help="Start date, YYYY-MM-DD.")
    parser.add_argument("--to", dest="to_date", required=True, help="End date, YYYY-MM-DD.")
    parser.add_argument(
        "--section-path",
        action="append",
        default=None,
        help="Optional section/path shard, e.g. nacional or mundo. Can be repeated.",
    )
    parser.add_argument(
        "--query-mode",
        action="append",
        choices=["date-inurl", "date-range"],
        default=None,
        help=(
            "Daily Google query family. Use date-inurl for inurl:/Y/M/D/ "
            "or date-range for site:domain after/before. Can be repeated."
        ),
    )
    parser.add_argument(
        "--topic-term",
        action="append",
        default=None,
        help="Optional topic/search term shard added to each daily query. Can be repeated.",
    )
    parser.add_argument(
        "--skip-domain-query",
        action="store_true",
        help="Skip broad source/day queries and run only section-path shards.",
    )
    parser.add_argument(
        "--always-shard-sections",
        action="store_true",
        help="Run section-path shards for every day, not only near the saturation threshold.",
    )
    parser.add_argument(
        "--saturation-threshold",
        type=int,
        default=90,
        help="Run section shards when the broad day query returns at least this many URLs.",
    )
    parser.add_argument("--max-results-per-query", type=int, default=100)
    parser.add_argument("--max-urls-per-source", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    parser.add_argument("--google-api-key", default=None)
    parser.add_argument("--google-cse-id", default=None)
    parser.add_argument(
        "--append-existing",
        action="store_true",
        help=(
            "Merge new rows into discovered_urls_google.*. When --source-id is "
            "used, previous rows for those source IDs are replaced."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    discovery_dir = args.discovery_dir or media_output_path(*DEFAULT_DISCOVERY_PARTS).parent
    reports_dir = args.reports_dir or media_output_path(*DEFAULT_REPORTS_PARTS).parent
    api_key, cse_id = google_credentials(args.google_api_key, args.google_cse_id)

    sources = load_google_sources(
        args.capabilities,
        source_ids=args.source_id,
        strategies=set(args.strategy or []) or None,
    )
    discovered = discover_google_urls(
        sources,
        api_key=api_key,
        cse_id=cse_id,
        source_ids=args.source_id,
        limit_sources=args.limit_sources,
        from_date=parse_date(args.from_date),
        to_date=parse_date(args.to_date),
        section_paths=args.section_path,
        query_modes=args.query_mode,
        topic_terms=args.topic_term,
        include_domain_query=not args.skip_domain_query,
        shard_sections=bool(args.always_shard_sections or args.section_path),
        saturation_threshold=0 if args.always_shard_sections else args.saturation_threshold,
        max_results_per_query=args.max_results_per_query,
        max_urls_per_source=args.max_urls_per_source,
        timeout=args.timeout,
        pause_seconds=args.pause_seconds,
    )
    if args.append_existing:
        discovered = merge_existing_discovery(
            discovery_dir,
            discovered,
            replace_source_ids=set(args.source_id or []),
        )
    report = build_google_report(discovered)
    outputs = write_google_outputs(discovered, report, discovery_dir, reports_dir)

    print(f"Google sources considered: {len(sources):,}")
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
    """Merge new Google rows with an existing discovery output."""
    parquet_path = discovery_dir / "discovered_urls_google.parquet"
    csv_path = discovery_dir / "discovered_urls_google.csv"
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
    return dedupe_google_discovery(merged)


if __name__ == "__main__":
    main()

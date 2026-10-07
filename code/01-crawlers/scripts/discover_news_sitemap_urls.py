"""Discover Milenio, Reforma, and El Norte URLs from official sitemaps."""

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

from crawler_core.news_sitemaps import (  # noqa: E402
    SOURCE_CONFIGS,
    discover_news_sitemaps,
    write_news_sitemap_outputs,
)
from project_paths import media_output_path  # noqa: E402


DEFAULT_DISCOVERY_PARTS = ("data", "00-newspaper_data", "crawler", "discovery", ".keep")
DEFAULT_REPORTS_PARTS = ("data", "00-newspaper_data", "crawler", "reports", ".keep")
DEFAULT_STATE_DB = REPO_ROOT / "tmp" / "news_sitemap_discovery" / "news_sitemaps.sqlite"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resumably discover Milenio and Grupo Reforma official sitemap URLs."
    )
    parser.add_argument(
        "--source-id",
        action="append",
        choices=sorted(SOURCE_CONFIGS),
        default=None,
    )
    parser.add_argument("--state-db", type=Path, default=DEFAULT_STATE_DB)
    parser.add_argument("--discovery-dir", type=Path, default=None)
    parser.add_argument("--reports-dir", type=Path, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-sitemaps-per-source", type=int, default=None)
    parser.add_argument("--max-urls-per-source", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--pause-seconds", type=float, default=0.1)
    parser.add_argument("--request-retries", type=int, default=2)
    parser.add_argument("--retry-backoff-seconds", type=float, default=3.0)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument(
        "--no-final-output",
        action="store_true",
        help="Only update SQLite; do not write CSV, Parquet, or reports.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    discovery_dir = args.discovery_dir or media_output_path(*DEFAULT_DISCOVERY_PARTS).parent
    reports_dir = args.reports_dir or media_output_path(*DEFAULT_REPORTS_PARTS).parent
    source_ids = args.source_id or list(SOURCE_CONFIGS)
    summaries = discover_news_sitemaps(
        source_ids=source_ids,
        state_db_path=args.state_db,
        resume=args.resume,
        max_sitemaps_per_source=args.max_sitemaps_per_source,
        max_urls_per_source=args.max_urls_per_source,
        timeout=args.timeout,
        pause_seconds=args.pause_seconds,
        request_retries=args.request_retries,
        retry_backoff_seconds=args.retry_backoff_seconds,
        workers=args.workers,
    )
    print(f"SQLite progress DB: {args.state_db}")
    if args.no_final_output:
        print("Final discovery files skipped by --no-final-output")
        return
    for source_id in source_ids:
        outputs = write_news_sitemap_outputs(
            state_db_path=args.state_db,
            source_id=source_id,
            discovery_dir=discovery_dir,
            reports_dir=reports_dir,
        )
        state = summaries[source_id]
        print(
            f"{source_id}: urls={state['url_count']:,}, complete={state['complete']}, "
            f"stop={state['stop_reason']}"
        )
        print(f"Wrote CSV: {outputs.discovered_csv}")
        if outputs.discovered_parquet:
            print(f"Wrote parquet: {outputs.discovered_parquet}")
        else:
            print(f"Skipped parquet: {outputs.parquet_error}")
        print(f"Wrote report: {outputs.report_path}")


if __name__ == "__main__":
    main()

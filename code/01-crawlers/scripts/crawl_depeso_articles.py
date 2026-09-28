"""Complete the De Peso Cancún and Yucatán WordPress archives."""

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

from crawler_core.depeso import (  # noqa: E402
    DEPESO_SOURCES,
    crawl_depeso_sources,
    export_completed_depeso_sources,
    initialize_depeso_db,
)
from project_paths import media_output_path  # noqa: E402


DEFAULT_STATE_DB = REPO_ROOT / "tmp" / "articles_depeso" / "depeso_articles.sqlite"
DEFAULT_ARTICLES_DIR = media_output_path(
    "data", "00-newspaper_data", "crawler", "articles", ".keep"
).parent
DEFAULT_REPORTS_DIR = media_output_path(
    "data", "00-newspaper_data", "crawler", "reports", "depeso", ".keep"
).parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Crawl the complete De Peso WordPress archives in stable post-ID order. "
            "Every successful page is committed immediately to SQLite."
        )
    )
    parser.add_argument(
        "--source-id",
        action="append",
        choices=sorted(DEPESO_SOURCES),
        help="Source to crawl. Repeat for both; defaults to both sources.",
    )
    parser.add_argument("--state-db", type=Path, default=DEFAULT_STATE_DB)
    parser.add_argument("--articles-dir", type=Path, default=DEFAULT_ARTICLES_DIR)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--per-page", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--pause-seconds", type=float, default=0.15)
    parser.add_argument("--request-retries", type=int, default=3)
    parser.add_argument("--retry-backoff-seconds", type=float, default=3.0)
    parser.add_argument(
        "--fetch-profile", choices=["default", "browser"], default="browser"
    )
    parser.add_argument(
        "--max-pages-per-run",
        type=int,
        default=None,
        help="Optional run cap for testing. Omit to continue to the archive terminus.",
    )
    parser.add_argument("--progress-every-pages", type=int, default=10)
    parser.add_argument(
        "--export-on-complete",
        action="store_true",
        help="Replace final per-source Parquet files only for sources marked complete.",
    )
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Skip crawling and export already completed SQLite sources.",
    )
    parser.add_argument(
        "--allow-partial-export",
        action="store_true",
        help="Export an incomplete checkpoint for inspection without marking it complete.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_ids = args.source_id or list(DEPESO_SOURCES)
    initialize_depeso_db(args.state_db)

    if not args.export_only:
        try:
            results = crawl_depeso_sources(
                source_ids,
                state_db_path=args.state_db,
                per_page=args.per_page,
                timeout=args.timeout,
                pause_seconds=args.pause_seconds,
                request_retries=args.request_retries,
                retry_backoff_seconds=args.retry_backoff_seconds,
                fetch_profile=args.fetch_profile,
                max_pages_per_run=args.max_pages_per_run,
                progress_every_pages=args.progress_every_pages,
            )
        except KeyboardInterrupt:
            print("Interrupted by user; every completed page is already saved to SQLite.")
            return
        for result in results:
            print(
                f"{result.source_id}: rows={result.rows_saved:,}, "
                f"next_page={result.next_page:,}, complete={result.complete}, "
                f"stop_reason={result.stop_reason}"
            )

    if args.export_only or args.export_on_complete or args.allow_partial_export:
        export_completed_depeso_sources(
            args.state_db,
            source_ids,
            articles_dir=args.articles_dir,
            reports_dir=args.reports_dir,
            allow_partial=args.allow_partial_export,
        )


if __name__ == "__main__":
    main()

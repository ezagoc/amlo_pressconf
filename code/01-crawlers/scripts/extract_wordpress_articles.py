"""Extract full article text from discovered WordPress post URLs."""

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

from crawler_core.wordpress_articles import (  # noqa: E402
    build_article_extraction_report,
    extract_wordpress_articles,
    load_discovered_urls,
    load_existing_article_statuses,
    load_existing_articles,
    prepare_article_queue,
    refresh_article_term_names,
    write_article_outputs,
)
from project_paths import media_input_path, media_output_path  # noqa: E402


DEFAULT_DISCOVERY = media_input_path(
    "data",
    "00-newspaper_data",
    "crawler",
    "discovery",
    "discovered_urls_wordpress.parquet",
)
DEFAULT_ARTICLES_PARTS = ("data", "00-newspaper_data", "crawler", "articles", ".keep")
DEFAULT_REPORTS_PARTS = ("data", "00-newspaper_data", "crawler", "reports", ".keep")
DEFAULT_STATE_DB_NAME = "wordpress_articles.sqlite"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract full article text from WordPress REST API posts."
    )
    parser.add_argument(
        "--discovered",
        type=Path,
        default=DEFAULT_DISCOVERY,
        help=f"Discovered WordPress URL table. Default: {DEFAULT_DISCOVERY}",
    )
    parser.add_argument(
        "--articles-dir",
        type=Path,
        default=None,
        help="Output directory for combined and per-source article files. Default: MEDIA_ROOT/data/00-newspaper_data/crawler/articles",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=None,
        help="Output directory for wordpress_article_extraction_report.md. Default: MEDIA_ROOT/data/00-newspaper_data/crawler/reports",
    )
    parser.add_argument(
        "--source-id",
        action="append",
        default=None,
        help="Restrict extraction to one source_id. Repeat for multiple sources.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional article row limit for smoke tests.",
    )
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--pause-seconds", type=float, default=0.1)
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=100,
        help="Write checkpoint after this many processed articles.",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        help="SQLite progress DB path. Deprecated name; prefer --state-db.",
    )
    parser.add_argument(
        "--state-db",
        type=Path,
        default=None,
        help="SQLite progress DB path. Default: <articles-dir>/wordpress_articles.sqlite",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Load checkpoint/output CSV if present and skip already attempted articles.",
    )
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="With --resume, retry rows that previously ended with an error.",
    )
    parser.add_argument(
        "--no-per-source",
        action="store_true",
        help="Only write combined article files, not articles/<source_id>/articles.* files.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=100,
        help="Print rate/ETA progress after this many processed articles. Use 0 to disable.",
    )
    parser.add_argument(
        "--progress-seconds",
        type=float,
        default=60.0,
        help="Also print progress after this many seconds without output. Use 0 to disable.",
    )
    parser.add_argument(
        "--row-log",
        action="store_true",
        help="Print one terminal line for every article URL fetched.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Fetch up to this many WordPress posts per API request. Use 1 for one request per article.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of concurrent article batches to fetch. Start with 2-4 for large sources.",
    )
    parser.add_argument(
        "--no-refresh-terms",
        action="store_true",
        help="Skip source-level category/tag name lookup after article extraction.",
    )
    parser.add_argument(
        "--no-final-output",
        action="store_true",
        help="Only update the SQLite progress DB; skip final per-source parquet/report writing.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    articles_dir = args.articles_dir or media_output_path(*DEFAULT_ARTICLES_PARTS).parent
    reports_dir = args.reports_dir or media_output_path(*DEFAULT_REPORTS_PARTS).parent
    state_db_path = args.state_db or args.checkpoint or (articles_dir / DEFAULT_STATE_DB_NAME)

    discovered = load_discovered_urls(args.discovered)
    existing = None
    if args.resume:
        existing = load_existing_article_statuses(state_db_path)
        if existing is None:
            print("Resume enabled: no existing SQLite progress DB found")
        else:
            print(f"Resume enabled: loaded {len(existing):,} existing article status rows")

    queue = prepare_article_queue(
        discovered,
        source_ids=args.source_id,
        limit=args.limit,
        existing_articles=existing,
        retry_errors=args.retry_errors,
    )

    print(f"Discovered input rows: {len(discovered):,}")
    print(f"Articles queued: {len(queue):,}")
    print(f"Sources queued: {queue['source_id'].nunique() if not queue.empty else 0:,}")
    print(f"SQLite progress DB: {state_db_path}")

    extracted = extract_wordpress_articles(
        queue,
        initial_rows=None,
        checkpoint_path=state_db_path,
        checkpoint_every=args.checkpoint_every,
        timeout=args.timeout,
        pause_seconds=args.pause_seconds,
        progress_every=args.progress_every,
        progress_seconds=args.progress_seconds,
        row_log=args.row_log,
        batch_size=args.batch_size,
        workers=args.workers,
        keep_rows=not args.no_final_output,
    )
    if args.no_final_output:
        print(f"Updated SQLite progress DB: {state_db_path}")
        print("Final per-source parquet/report writing skipped by --no-final-output")
        return

    articles = load_existing_articles(state_db_path)
    if articles is None:
        articles = extracted
    if not args.no_refresh_terms:
        articles = refresh_article_term_names(
            articles,
            source_ids=args.source_id,
            timeout=args.timeout,
            batch_size=min(args.batch_size, 100),
        )
    report = build_article_extraction_report(articles)
    outputs = write_article_outputs(
        articles,
        report,
        articles_dir,
        reports_dir,
        write_per_source=not args.no_per_source,
    )

    print(f"Article rows: {len(articles):,}")
    print(f"Wrote per-source parquet outputs under: {outputs.articles_dir}")
    if outputs.parquet_error:
        print(f"Skipped parquet: {outputs.parquet_error}")
    print(f"Wrote report: {outputs.report_path}")


if __name__ == "__main__":
    main()

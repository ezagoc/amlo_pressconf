"""Extract article text from RSS-discovered URLs."""

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

from crawler_core.sitemap_articles import (  # noqa: E402
    build_sitemap_article_report,
    extract_sitemap_articles,
    load_sitemap_article_statuses,
    load_sitemap_articles_from_sqlite,
    load_sitemap_discovery,
    prepare_sitemap_article_queue,
    write_sitemap_article_outputs,
)
from project_paths import media_output_path, media_path  # noqa: E402


DEFAULT_DISCOVERY = media_path(
    "data",
    "00-newspaper_data",
    "crawler",
    "discovery",
    "discovered_urls_rss.parquet",
)
DEFAULT_ARTICLES_PARTS = ("data", "00-newspaper_data", "crawler", "articles_rss", ".keep")
DEFAULT_REPORTS_PARTS = ("data", "00-newspaper_data", "crawler", "reports", ".keep")
DEFAULT_STATE_DB_NAME = "rss_articles.sqlite"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract full article text from RSS-discovered HTML pages.")
    parser.add_argument("--discovered", type=Path, default=DEFAULT_DISCOVERY)
    parser.add_argument("--articles-dir", type=Path, default=None)
    parser.add_argument("--reports-dir", type=Path, default=None)
    parser.add_argument("--state-db", type=Path, default=None)
    parser.add_argument("--source-id", action="append", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--refresh-missing-text", action="store_true")
    parser.add_argument("--refresh-missing-date", action="store_true")
    parser.add_argument("--refresh-all-existing", action="store_true")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--pause-seconds", type=float, default=0.05)
    parser.add_argument("--checkpoint-every", type=int, default=100)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--progress-seconds", type=float, default=60.0)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument(
        "--fetch-profile",
        choices=["default", "browser"],
        default="browser",
        help="HTTP request profile. RSS extraction defaults to browser-like headers.",
    )
    parser.add_argument("--row-log", action="store_true")
    parser.add_argument(
        "--no-final-output",
        action="store_true",
        help="Only update SQLite progress DB; skip final per-source parquet/report writing.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    articles_dir = args.articles_dir or media_output_path(*DEFAULT_ARTICLES_PARTS).parent
    reports_dir = args.reports_dir or media_output_path(*DEFAULT_REPORTS_PARTS).parent
    state_db_path = args.state_db or (articles_dir / DEFAULT_STATE_DB_NAME)

    discovered = load_sitemap_discovery(args.discovered)
    existing = None
    if args.resume:
        existing = load_sitemap_article_statuses(state_db_path)
        if existing is None:
            print("Resume enabled: no existing RSS SQLite progress DB found")
        else:
            print(f"Resume enabled: loaded {len(existing):,} existing RSS article status rows")

    queue = prepare_sitemap_article_queue(
        discovered,
        source_ids=args.source_id,
        limit=args.limit,
        existing_articles=existing,
        retry_errors=args.retry_errors,
        refresh_missing_text=args.refresh_missing_text,
        refresh_missing_date=args.refresh_missing_date,
        refresh_all_existing=args.refresh_all_existing,
    )

    print(f"Discovered input rows: {len(discovered):,}")
    print(f"Articles queued: {len(queue):,}")
    print(f"Sources queued: {queue['source_id'].nunique() if not queue.empty else 0:,}")
    print(f"SQLite progress DB: {state_db_path}")

    extracted = extract_sitemap_articles(
        queue,
        state_db_path=state_db_path,
        checkpoint_every=args.checkpoint_every,
        timeout=args.timeout,
        pause_seconds=args.pause_seconds,
        progress_every=args.progress_every,
        progress_seconds=args.progress_seconds,
        workers=args.workers,
        row_log=args.row_log,
        keep_rows=not args.no_final_output,
        fetch_profile=args.fetch_profile,
    )

    if args.no_final_output:
        print(f"Updated SQLite progress DB: {state_db_path}")
        print("Final per-source parquet/report writing skipped by --no-final-output")
        return

    articles = load_sitemap_articles_from_sqlite(state_db_path)
    if articles.empty:
        articles = extracted
    report = build_sitemap_article_report(articles)
    outputs = write_sitemap_article_outputs(articles, report, articles_dir, reports_dir)

    print(f"Article rows: {len(articles):,}")
    print(f"Wrote per-source parquet outputs under: {outputs.articles_dir}")
    if outputs.parquet_error:
        print(f"Skipped parquet: {outputs.parquet_error}")
    print(f"Wrote report: {outputs.report_path}")


if __name__ == "__main__":
    main()

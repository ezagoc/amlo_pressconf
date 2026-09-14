"""Refresh WordPress category/tag names for already extracted article rows."""

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
    load_existing_articles,
    refresh_article_term_names,
    write_article_outputs,
)
from project_paths import media_input_path, media_output_path  # noqa: E402


DEFAULT_ARTICLES = media_input_path(
    "data",
    "00-newspaper_data",
    "crawler",
    "articles",
    "wordpress_articles.parquet",
)
DEFAULT_ARTICLES_PARTS = ("data", "00-newspaper_data", "crawler", "articles", ".keep")
DEFAULT_REPORTS_PARTS = ("data", "00-newspaper_data", "crawler", "reports", ".keep")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fill WordPress category/tag names from stored category_ids/tag_ids."
    )
    parser.add_argument(
        "--articles",
        type=Path,
        default=DEFAULT_ARTICLES,
        help=f"Existing article table to refresh. Default: {DEFAULT_ARTICLES}",
    )
    parser.add_argument(
        "--articles-dir",
        type=Path,
        default=None,
        help="Output directory for refreshed combined and per-source files.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=None,
        help="Output directory for refreshed report.",
    )
    parser.add_argument(
        "--source-id",
        action="append",
        default=None,
        help="Restrict refresh to one source_id. Repeat for multiple sources.",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument(
        "--no-per-source",
        action="store_true",
        help="Only write combined article files, not articles/<source_id>/articles.* files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    articles_dir = args.articles_dir or media_output_path(*DEFAULT_ARTICLES_PARTS).parent
    reports_dir = args.reports_dir or media_output_path(*DEFAULT_REPORTS_PARTS).parent

    articles = load_existing_articles(args.articles)
    if articles is None:
        raise FileNotFoundError(f"Article file not found: {args.articles}")

    print(f"Loaded rows: {len(articles):,}")
    refreshed = refresh_article_term_names(
        articles,
        source_ids=args.source_id,
        timeout=args.timeout,
        batch_size=args.batch_size,
    )
    report = build_article_extraction_report(refreshed)
    outputs = write_article_outputs(
        refreshed,
        report,
        articles_dir,
        reports_dir,
        write_per_source=not args.no_per_source,
    )

    print(f"Refreshed rows: {len(refreshed):,}")
    print(f"Wrote CSV: {outputs.articles_csv}")
    if outputs.articles_parquet:
        print(f"Wrote parquet: {outputs.articles_parquet}")
    else:
        print(f"Skipped parquet: {outputs.parquet_error}")
    print(f"Wrote report: {outputs.report_path}")


if __name__ == "__main__":
    main()

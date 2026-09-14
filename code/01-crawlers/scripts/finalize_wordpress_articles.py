"""Finalize WordPress article progress into per-source parquet outputs."""

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
    ARTICLE_KEY_COLUMNS,
    build_article_extraction_report,
    load_existing_articles,
    write_article_outputs,
)
from project_paths import media_input_path, media_output_path  # noqa: E402


DEFAULT_CHECKPOINT = media_input_path(
    "data",
    "00-newspaper_data",
    "crawler",
    "articles",
    "wordpress_articles.sqlite",
)
DEFAULT_ARTICLES_PARTS = ("data", "00-newspaper_data", "crawler", "articles", ".keep")
DEFAULT_REPORTS_PARTS = ("data", "00-newspaper_data", "crawler", "reports", ".keep")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Finalize WordPress article progress into per-source parquet.gzip files."
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=DEFAULT_CHECKPOINT,
        help="SQLite progress DB or legacy CSV/parquet checkpoint.",
    )
    parser.add_argument("--articles-dir", type=Path, default=None)
    parser.add_argument("--reports-dir", type=Path, default=None)
    parser.add_argument(
        "--no-per-source",
        action="store_true",
        help="Only write report; skip per-source parquet outputs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    articles_dir = args.articles_dir or media_output_path(*DEFAULT_ARTICLES_PARTS).parent
    reports_dir = args.reports_dir or media_output_path(*DEFAULT_REPORTS_PARTS).parent

    print(f"Reading article progress: {args.checkpoint}")
    articles = load_existing_articles(args.checkpoint)
    if articles is None:
        raise FileNotFoundError(f"Checkpoint not found: {args.checkpoint}")
    print(f"Loaded rows: {len(articles):,}")

    if not articles.empty:
        before = len(articles)
        articles = articles.drop_duplicates(ARTICLE_KEY_COLUMNS, keep="last").reset_index(drop=True)
        print(f"Deduped rows: {len(articles):,} (removed {before - len(articles):,})")
        print(f"Sources: {articles['source_id'].nunique():,}")
        print(f"Errors: {articles['error'].notna().sum():,}")
        print(
            "Missing main_text: "
            f"{articles['main_text'].fillna('').astype(str).str.strip().eq('').sum():,}"
        )

    report = build_article_extraction_report(articles)
    outputs = write_article_outputs(
        articles,
        report,
        articles_dir,
        reports_dir,
        write_per_source=not args.no_per_source,
    )

    print(f"Wrote per-source parquet outputs under: {outputs.articles_dir}")
    if outputs.parquet_error:
        print(f"Skipped parquet: {outputs.parquet_error}")
    print(f"Wrote report: {outputs.report_path}")


if __name__ == "__main__":
    main()

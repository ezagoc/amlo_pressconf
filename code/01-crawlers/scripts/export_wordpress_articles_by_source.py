"""Export article progress into per-source parquet.gzip part files."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
CRAWLER_DIR = SCRIPT_DIR.parents[0]
CODE_DIR = SCRIPT_DIR.parents[1]
REPO_ROOT = SCRIPT_DIR.parents[2]

for path in (CRAWLER_DIR, CODE_DIR, REPO_ROOT):
    sys.path.insert(0, str(path))

from crawler_core.wordpress_articles import (  # noqa: E402
    is_parquet_path,
    is_sqlite_path,
    normalize_articles_for_output,
    quote_sqlite_identifier,
)
from project_paths import media_input_path, media_output_path  # noqa: E402


DEFAULT_INPUT = media_output_path(
    "data",
    "00-newspaper_data",
    "crawler",
    "articles",
    "wordpress_articles.sqlite",
)
DEFAULT_ARTICLES_PARTS = ("data", "00-newspaper_data", "crawler", "articles", ".keep")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write per-source parquet.gzip part files from SQLite, CSV, or parquet article rows."
    )
    parser.add_argument("--articles", type=Path, default=DEFAULT_INPUT)
    parser.add_argument(
        "--articles-dir",
        type=Path,
        default=None,
        help="Output root. Default: MEDIA_ROOT/data/00-newspaper_data/crawler/articles",
    )
    parser.add_argument(
        "--source-id",
        action="append",
        default=None,
        help="Restrict export to one source_id. Repeat for multiple sources.",
    )
    parser.add_argument("--chunksize", type=int, default=50_000)
    parser.add_argument(
        "--list-sources",
        action="store_true",
        help="Only print source row counts; do not write parquet files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    articles_dir = args.articles_dir or media_output_path(*DEFAULT_ARTICLES_PARTS).parent
    source_filter = set(args.source_id or [])

    if args.list_sources:
        list_sources(args.articles, source_filter or None, args.chunksize)
        return

    part_counts: defaultdict[str, int] = defaultdict(int)
    row_counts: defaultdict[str, int] = defaultdict(int)
    for chunk_number, chunk in enumerate(iter_article_chunks(args.articles, args.chunksize), start=1):
        if source_filter:
            chunk = chunk[chunk["source_id"].isin(source_filter)].copy()
        if chunk.empty:
            continue
        chunk = normalize_articles_for_output(chunk)
        for source_id, source_rows in chunk.groupby("source_id", dropna=True):
            source_text = str(source_id)
            source_dir = articles_dir / source_text
            source_dir.mkdir(parents=True, exist_ok=True)
            part_counts[source_text] += 1
            row_counts[source_text] += len(source_rows)
            part_path = source_dir / f"articles_part_{part_counts[source_text]:06d}.parquet.gzip"
            source_rows.to_parquet(part_path, index=False, compression="gzip")
        print(
            f"Processed chunk {chunk_number:,}: rows={len(chunk):,}, "
            f"sources={chunk['source_id'].nunique():,}"
        )

    for source_id in sorted(row_counts):
        print(
            f"Exported {source_id}: rows={row_counts[source_id]:,}, "
            f"parts={part_counts[source_id]:,}, folder={articles_dir / source_id}"
        )


def iter_article_chunks(path: Path, chunksize: int):
    """Yield article chunks from SQLite, CSV, or parquet."""
    if is_sqlite_path(path):
        import sqlite3

        with sqlite3.connect(path) as conn:
            source_sql = ""
            for chunk in pd.read_sql_query(
                "SELECT * FROM articles" + source_sql,
                conn,
                chunksize=chunksize,
            ):
                yield chunk
    elif is_parquet_path(path):
        yield pd.read_parquet(path)
    else:
        yield from pd.read_csv(path, chunksize=chunksize, low_memory=False)


def list_sources(path: Path, source_filter: set[str] | None, chunksize: int) -> None:
    """Print source row counts from an article store."""
    if is_sqlite_path(path):
        import sqlite3

        with sqlite3.connect(path) as conn:
            where = ""
            params: list[str] = []
            if source_filter:
                placeholders = ", ".join("?" for _ in source_filter)
                where = f" WHERE source_id IN ({placeholders})"
                params = sorted(source_filter)
            sql = (
                "SELECT source_id, COUNT(*) AS rows "
                "FROM articles"
                f"{where} GROUP BY source_id ORDER BY rows DESC"
            )
            for source_id, rows in conn.execute(sql, params):
                print(f"{source_id}\t{rows:,}")
        return

    counts: defaultdict[str, int] = defaultdict(int)
    for chunk in iter_article_chunks(path, chunksize):
        if source_filter:
            chunk = chunk[chunk["source_id"].isin(source_filter)]
        for source_id, rows in chunk.groupby("source_id", dropna=True).size().items():
            counts[str(source_id)] += int(rows)
    for source_id, rows in sorted(counts.items(), key=lambda item: item[1], reverse=True):
        print(f"{source_id}\t{rows:,}")


if __name__ == "__main__":
    main()

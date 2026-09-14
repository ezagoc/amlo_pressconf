"""Export source-API article rows into per-source parquet.gzip files."""

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

from crawler_core.wordpress_articles import normalize_articles_for_output  # noqa: E402
from project_paths import media_output_path  # noqa: E402


DEFAULT_ARTICLES_PARTS = ("data", "00-newspaper_data", "crawler", "articles_source_api", ".keep")
DEFAULT_STATE_DB_PARTS = (
    "data",
    "00-newspaper_data",
    "crawler",
    "articles_source_api",
    "source_api_articles.sqlite",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write per-source source-API article parquet.gzip part files from SQLite."
    )
    parser.add_argument("--state-db", type=Path, default=None)
    parser.add_argument("--articles-dir", type=Path, default=None)
    parser.add_argument("--source-id", action="append", default=None)
    parser.add_argument("--chunksize", type=int, default=50_000)
    parser.add_argument("--list-sources", action="store_true")
    parser.add_argument("--include-errors", action="store_true")
    parser.add_argument("--require-date", action="store_true")
    parser.add_argument("--min-text-chars", type=int, default=0)
    parser.add_argument("--replace-existing", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    articles_dir = args.articles_dir or media_output_path(*DEFAULT_ARTICLES_PARTS).parent
    state_db = args.state_db or media_output_path(*DEFAULT_STATE_DB_PARTS)
    source_filter = set(args.source_id or [])

    if args.list_sources:
        list_sources(state_db, source_filter or None)
        return

    part_counts: defaultdict[str, int] = defaultdict(int)
    row_counts: defaultdict[str, int] = defaultdict(int)
    if args.replace_existing:
        clear_existing_parts(articles_dir, source_filter)
    for chunk_number, chunk in enumerate(iter_sqlite_chunks(state_db, args.chunksize), start=1):
        if not args.include_errors and "error" in chunk.columns:
            chunk = chunk[chunk["error"].isna() | chunk["error"].eq("")].copy()
        if args.require_date:
            date_columns = [column for column in ["date_published", "date", "lastmod"] if column in chunk.columns]
            if date_columns:
                date_text = chunk[date_columns].fillna("").astype(str).agg("".join, axis=1).str.strip()
                chunk = chunk[date_text.ne("")].copy()
            else:
                chunk = chunk.iloc[0:0].copy()
        if args.min_text_chars:
            text_length = chunk.get("main_text", pd.Series(index=chunk.index, dtype=object))
            text_length = text_length.fillna("").astype(str).str.strip().str.len()
            chunk = chunk[text_length.ge(args.min_text_chars)].copy()
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


def clear_existing_parts(articles_dir: Path, source_filter: set[str]) -> None:
    """Remove old parquet parts for selected sources before writing replacements."""
    if not source_filter:
        raise ValueError("--replace-existing requires at least one --source-id")
    for source_id in sorted(source_filter):
        source_dir = articles_dir / source_id
        if not source_dir.exists():
            continue
        for path in source_dir.glob("articles_part_*.parquet.gzip"):
            path.unlink()


def iter_sqlite_chunks(db_path: Path, chunksize: int):
    """Yield chunks from the source API article SQLite table."""
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        for chunk in pd.read_sql_query("SELECT * FROM sitemap_articles", conn, chunksize=chunksize):
            yield chunk


def list_sources(db_path: Path, source_filter: set[str] | None) -> None:
    """Print source row counts from the source API article SQLite table."""
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        where = ""
        params: list[str] = []
        if source_filter:
            placeholders = ", ".join("?" for _ in source_filter)
            where = f" WHERE source_id IN ({placeholders})"
            params = sorted(source_filter)
        sql = (
            "SELECT source_id, COUNT(*) AS rows "
            "FROM sitemap_articles"
            f"{where} GROUP BY source_id ORDER BY rows DESC"
        )
        for source_id, rows in conn.execute(sql, params):
            print(f"{source_id}\t{rows:,}")


if __name__ == "__main__":
    main()

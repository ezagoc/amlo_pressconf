"""Migrate a legacy WordPress article CSV checkpoint into SQLite progress DB."""

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

from crawler_core.wordpress_articles import save_articles_to_sqlite  # noqa: E402
from project_paths import media_input_path, media_output_path  # noqa: E402


DEFAULT_CSV = media_input_path(
    "data",
    "00-newspaper_data",
    "crawler",
    "articles",
    "wordpress_articles.checkpoint.csv",
)
DEFAULT_DB_PARTS = (
    "data",
    "00-newspaper_data",
    "crawler",
    "articles",
    "wordpress_articles.sqlite",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stream a legacy wordpress_articles.checkpoint.csv into SQLite."
    )
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--state-db", type=Path, default=media_output_path(*DEFAULT_DB_PARTS))
    parser.add_argument("--chunksize", type=int, default=50_000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(f"Reading CSV checkpoint: {args.csv}")
    print(f"Writing SQLite progress DB: {args.state_db}")
    total = 0
    for chunk_number, chunk in enumerate(
        pd.read_csv(args.csv, chunksize=args.chunksize, low_memory=False),
        start=1,
    ):
        before = len(chunk)
        chunk = chunk.drop_duplicates(["source_id", "wp_post_id"], keep="last")
        save_articles_to_sqlite(chunk, args.state_db)
        total += before
        print(
            f"Migrated chunk {chunk_number:,}: "
            f"read={before:,}, upserted={len(chunk):,}, total_read={total:,}"
        )
    print("Done.")


if __name__ == "__main__":
    main()

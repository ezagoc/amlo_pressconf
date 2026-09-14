"""Finalize a large WordPress discovery checkpoint into parquet and reports.

This avoids rewriting the multi-GB checkpoint CSV unless explicitly requested.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
CRAWLER_DIR = SCRIPT_DIR.parents[0]
CODE_DIR = SCRIPT_DIR.parents[1]
REPO_ROOT = SCRIPT_DIR.parents[2]

for path in (CRAWLER_DIR, CODE_DIR, REPO_ROOT):
    sys.path.insert(0, str(path))

from crawler_core.wordpress import build_wordpress_discovery_report  # noqa: E402
from project_paths import media_input_path, media_output_path  # noqa: E402


DEFAULT_CHECKPOINT = media_input_path(
    "data",
    "00-newspaper_data",
    "crawler",
    "discovery",
    "discovered_urls_wordpress.checkpoint.csv",
)
DEFAULT_DISCOVERY_PARTS = ("data", "00-newspaper_data", "crawler", "discovery", ".keep")
DEFAULT_REPORTS_PARTS = ("data", "00-newspaper_data", "crawler", "reports", ".keep")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Finalize discovered_urls_wordpress.checkpoint.csv into parquet/report."
    )
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--discovery-dir", type=Path, default=None)
    parser.add_argument("--reports-dir", type=Path, default=None)
    parser.add_argument(
        "--promote-csv",
        action="store_true",
        help="Also copy the checkpoint CSV to discovered_urls_wordpress.csv.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    discovery_dir = args.discovery_dir or media_output_path(*DEFAULT_DISCOVERY_PARTS).parent
    reports_dir = args.reports_dir or media_output_path(*DEFAULT_REPORTS_PARTS).parent
    discovery_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    parquet_path = discovery_dir / "discovered_urls_wordpress.parquet"
    csv_path = discovery_dir / "discovered_urls_wordpress.csv"
    report_path = reports_dir / "wordpress_discovery_report.md"

    print(f"Reading checkpoint: {args.checkpoint}")
    discovered = pd.read_csv(args.checkpoint, low_memory=False)
    print(f"Loaded rows: {len(discovered):,}")

    before = len(discovered)
    discovered = discovered.drop_duplicates(["source_id", "url"], keep="last").reset_index(drop=True)
    print(f"Deduped rows: {len(discovered):,} (removed {before - len(discovered):,})")
    print(f"Sources: {discovered['source_id'].nunique():,}")
    print(f"Usable URLs: {discovered['url'].notna().sum():,}")
    print(f"Errors: {discovered['error'].notna().sum():,}")

    print(f"Writing parquet: {parquet_path}")
    discovered.to_parquet(parquet_path, index=False)

    print(f"Writing report: {report_path}")
    report_path.write_text(build_wordpress_discovery_report(discovered), encoding="utf-8")

    if args.promote_csv:
        print(f"Copying checkpoint CSV to: {csv_path}")
        shutil.copyfile(args.checkpoint, csv_path)
    else:
        print("CSV promotion skipped. Use --promote-csv if you need the final CSV path updated.")

    print("Done.")


if __name__ == "__main__":
    main()

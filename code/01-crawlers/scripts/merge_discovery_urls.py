"""Merge multiple URL discovery outputs into canonical per-source files."""

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

from crawler_core.discovery_merge import (  # noqa: E402
    expand_discovery_inputs,
    merge_discoveries,
    read_discovery,
    write_merged_discoveries,
)
from project_paths import media_output_path  # noqa: E402


DEFAULT_DISCOVERY_PARTS = ("data", "00-newspaper_data", "crawler", "discovery", ".keep")
DEFAULT_REPORTS_PARTS = ("data", "00-newspaper_data", "crawler", "reports", ".keep")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge URL discovery files by source and URL.")
    parser.add_argument("--input", action="append", type=Path, required=True)
    parser.add_argument("--source-id", action="append", default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--reports-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir or media_output_path(*DEFAULT_DISCOVERY_PARTS).parent
    reports_dir = args.reports_dir or media_output_path(*DEFAULT_REPORTS_PARTS).parent
    input_paths = expand_discovery_inputs(args.input)
    frames = [read_discovery(path) for path in input_paths]
    print(f"Discovery inputs loaded: {len(input_paths):,}")
    merged = merge_discoveries(frames, source_ids=set(args.source_id or []) or None)
    outputs = write_merged_discoveries(merged, output_dir, reports_dir)
    for output in outputs:
        print(f"{output.source_id}: {output.rows:,} unique URLs")
        print(f"  CSV: {output.csv_path}")
        if output.parquet_path:
            print(f"  parquet: {output.parquet_path}")
        else:
            print(f"  skipped parquet: {output.parquet_error}")
        print(f"  report: {output.report_path}")


if __name__ == "__main__":
    main()

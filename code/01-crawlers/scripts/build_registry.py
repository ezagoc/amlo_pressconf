"""Build the Mexican newspaper crawler registry from the metadata workbook."""

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

from crawler_core.registry import (  # noqa: E402
    build_audit_report,
    build_registry,
    read_workbook,
    write_registry_outputs,
)
from project_paths import media_input_path, media_output_path  # noqa: E402


DEFAULT_WORKBOOK = media_input_path(
    "data",
    "00-newspaper_data",
    "mexican_newspapers.xlsx",
)
DEFAULT_REGISTRY_PARTS = ("data", "00-newspaper_data", "crawler", "registry", ".keep")
DEFAULT_REPORTS_PARTS = ("data", "00-newspaper_data", "crawler", "reports", ".keep")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build normalized crawler registry files from mexican_newspapers.xlsx."
    )
    parser.add_argument(
        "--workbook",
        type=Path,
        default=DEFAULT_WORKBOOK,
        help=f"Workbook path. Default: {DEFAULT_WORKBOOK}",
    )
    parser.add_argument(
        "--registry-dir",
        type=Path,
        default=None,
        help="Output directory for sources.csv/parquet. Default: MEDIA_ROOT/data/00-newspaper_data/crawler/registry",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=None,
        help="Output directory for metadata_audit.md. Default: MEDIA_ROOT/data/00-newspaper_data/crawler/reports",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    registry_dir = args.registry_dir or media_output_path(*DEFAULT_REGISTRY_PARTS).parent
    reports_dir = args.reports_dir or media_output_path(*DEFAULT_REPORTS_PARTS).parent
    periodicos, estados = read_workbook(args.workbook)
    registry = build_registry(periodicos, estados)
    audit_report = build_audit_report(registry, periodicos, estados, args.workbook)
    outputs = write_registry_outputs(
        registry=registry,
        audit_report=audit_report,
        registry_dir=registry_dir,
        reports_dir=reports_dir,
    )

    print(f"Registry rows: {len(registry):,}")
    print(f"Crawl candidates: {registry['crawl_candidate'].sum():,}")
    print(f"Wrote CSV: {outputs.sources_csv}")
    if outputs.sources_parquet:
        print(f"Wrote parquet: {outputs.sources_parquet}")
    else:
        print(f"Skipped parquet: {outputs.parquet_error}")
    print(f"Wrote audit report: {outputs.audit_report}")


if __name__ == "__main__":
    main()

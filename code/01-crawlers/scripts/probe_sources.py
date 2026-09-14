"""Probe newspaper source URLs for crawl capabilities."""

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

from crawler_core.capabilities import (  # noqa: E402
    build_capability_report,
    load_sources,
    probe_sources,
    write_probe_outputs,
)
from project_paths import media_input_path, media_output_path  # noqa: E402


DEFAULT_SOURCES = media_input_path(
    "data",
    "00-newspaper_data",
    "crawler",
    "registry",
    "sources.csv",
)
DEFAULT_CAPABILITIES_PARTS = ("data", "00-newspaper_data", "crawler", "registry", ".keep")
DEFAULT_REPORTS_PARTS = ("data", "00-newspaper_data", "crawler", "reports", ".keep")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run shallow crawl capability probes for newspaper sources."
    )
    parser.add_argument(
        "--sources",
        type=Path,
        default=DEFAULT_SOURCES,
        help=f"Registry CSV path. Default: {DEFAULT_SOURCES}",
    )
    parser.add_argument(
        "--capabilities-dir",
        type=Path,
        default=None,
        help="Output directory for capability CSV/parquet. Default: MEDIA_ROOT/data/00-newspaper_data/crawler/registry",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=None,
        help="Output directory for capability_report.md. Default: MEDIA_ROOT/data/00-newspaper_data/crawler/reports",
    )
    parser.add_argument(
        "--all-sources",
        action="store_true",
        help="Probe all registry rows instead of only first-wave crawl candidates.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional row limit for smoke tests.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Per-request timeout in seconds.",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=0.5,
        help="Pause between source probes.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    capabilities_dir = args.capabilities_dir or media_output_path(*DEFAULT_CAPABILITIES_PARTS).parent
    reports_dir = args.reports_dir or media_output_path(*DEFAULT_REPORTS_PARTS).parent
    sources = load_sources(args.sources, candidates_only=not args.all_sources)
    capabilities = probe_sources(
        sources,
        limit=args.limit,
        timeout=args.timeout,
        pause_seconds=args.pause_seconds,
    )
    report = build_capability_report(capabilities)
    outputs = write_probe_outputs(
        capabilities=capabilities,
        report=report,
        capabilities_dir=capabilities_dir,
        reports_dir=reports_dir,
    )

    print(f"Probed sources: {len(capabilities):,}")
    print(f"Wrote CSV: {outputs.capabilities_csv}")
    if outputs.capabilities_parquet:
        print(f"Wrote parquet: {outputs.capabilities_parquet}")
    else:
        print(f"Skipped parquet: {outputs.parquet_error}")
    print(f"Wrote report: {outputs.report_path}")


if __name__ == "__main__":
    main()

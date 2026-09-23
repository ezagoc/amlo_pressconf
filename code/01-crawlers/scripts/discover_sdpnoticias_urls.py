"""Discover SDPNoticias URLs from Arc sitemap offset feeds."""

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

from crawler_core.sdpnoticias import (  # noqa: E402
    CATEGORIES,
    build_sdp_report,
    discover_sdp_urls,
    write_sdp_outputs,
)
from project_paths import media_output_path  # noqa: E402


DEFAULT_DISCOVERY_PARTS = ("data", "00-newspaper_data", "crawler", "discovery", ".keep")
DEFAULT_REPORTS_PARTS = ("data", "00-newspaper_data", "crawler", "reports", ".keep")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover SDPNoticias article URLs from Arc sitemap offsets."
    )
    parser.add_argument("--discovery-dir", type=Path, default=None)
    parser.add_argument("--reports-dir", type=Path, default=None)
    parser.add_argument("--max-offset", type=int, default=10_000)
    parser.add_argument("--offset-step", type=int, default=100)
    parser.add_argument("--category", action="append", default=None, help="Restrict to one category. Repeat for multiple.")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--pause-seconds", type=float, default=0.05)
    parser.add_argument(
        "--expand-nested-categories",
        action="store_true",
        help="After the main/category sitemap pass, infer two-level category paths from discovered URLs and crawl those category sitemap offsets too.",
    )
    parser.add_argument("--max-nested-rounds", type=int, default=2)
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=5_000,
        help="Write discovered_urls_sdpnoticias_checkpoint.csv every N rows. Use 0 to disable.",
    )
    parser.add_argument("--checkpoint-path", type=Path, default=None)
    parser.add_argument(
        "--ignore-checkpoint",
        action="store_true",
        help="Ignore an existing checkpoint and start discovery from scratch.",
    )
    parser.add_argument(
        "--list-default-categories",
        action="store_true",
        help="Print the default categories and exit.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.list_default_categories:
        for category in CATEGORIES:
            print(category)
        return

    discovery_dir = args.discovery_dir or media_output_path(*DEFAULT_DISCOVERY_PARTS).parent
    reports_dir = args.reports_dir or media_output_path(*DEFAULT_REPORTS_PARTS).parent
    checkpoint_path = args.checkpoint_path
    if checkpoint_path is None and args.checkpoint_every > 0:
        checkpoint_path = discovery_dir / "discovered_urls_sdpnoticias_checkpoint.csv"

    discovered = discover_sdp_urls(
        max_offset=args.max_offset,
        offset_step=args.offset_step,
        categories=args.category,
        timeout=args.timeout,
        pause_seconds=args.pause_seconds,
        checkpoint_path=checkpoint_path,
        checkpoint_every=args.checkpoint_every,
        resume_checkpoint=not args.ignore_checkpoint,
        expand_nested_categories=args.expand_nested_categories,
        max_nested_rounds=args.max_nested_rounds,
    )
    report = build_sdp_report(discovered)
    outputs = write_sdp_outputs(discovered, report, discovery_dir, reports_dir)
    print(f"Discovered rows: {len(discovered):,}")
    print(f"Discovered URLs: {discovered['url'].notna().sum() if 'url' in discovered else 0:,}")
    print(f"Wrote CSV: {outputs.discovered_csv}")
    if outputs.discovered_parquet:
        print(f"Wrote parquet: {outputs.discovered_parquet}")
    else:
        print(f"Skipped parquet: {outputs.parquet_error}")
    print(f"Wrote report: {outputs.report_path}")


if __name__ == "__main__":
    main()

"""Discover Aristegui Noticias URLs from its hidden editorial sitemap index."""

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

from crawler_core.aristegui import (  # noqa: E402
    build_aristegui_report,
    discover_aristegui_urls,
    write_aristegui_outputs,
)
from project_paths import media_output_path  # noqa: E402


DEFAULT_DISCOVERY_PARTS = ("data", "00-newspaper_data", "crawler", "discovery", ".keep")
DEFAULT_REPORTS_PARTS = ("data", "00-newspaper_data", "crawler", "reports", ".keep")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover historical Aristegui Noticias URLs from the editorial sitemap index."
    )
    parser.add_argument("--discovery-dir", type=Path, default=None)
    parser.add_argument("--reports-dir", type=Path, default=None)
    parser.add_argument("--max-sitemaps", type=int, default=350)
    parser.add_argument("--max-urls", type=int, default=400_000)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--pause-seconds", type=float, default=0.05)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--heartbeat-seconds", type=float, default=15.0)
    parser.add_argument("--checkpoint-every", type=int, default=5_000)
    parser.add_argument("--checkpoint-path", type=Path, default=None)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    discovery_dir = args.discovery_dir or media_output_path(*DEFAULT_DISCOVERY_PARTS).parent
    reports_dir = args.reports_dir or media_output_path(*DEFAULT_REPORTS_PARTS).parent
    checkpoint_path = args.checkpoint_path
    if checkpoint_path is None and args.checkpoint_every > 0:
        checkpoint_path = discovery_dir / "discovered_urls_aristeguinoticias_checkpoint.csv"

    discovered = discover_aristegui_urls(
        max_sitemaps=args.max_sitemaps,
        max_urls=args.max_urls,
        timeout=args.timeout,
        pause_seconds=args.pause_seconds,
        workers=args.workers,
        retries=args.retries,
        heartbeat_seconds=args.heartbeat_seconds,
        checkpoint_path=checkpoint_path,
        checkpoint_every=args.checkpoint_every,
        resume=args.resume,
    )
    report = build_aristegui_report(discovered)
    outputs = write_aristegui_outputs(discovered, report, discovery_dir, reports_dir)
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

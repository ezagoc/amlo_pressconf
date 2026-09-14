"""Discover MVS Noticias article URLs through section and topic archives."""

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

from crawler_core.mvs import build_mvs_report, discover_mvs_urls, write_mvs_outputs  # noqa: E402
from project_paths import media_output_path  # noqa: E402


DEFAULT_DISCOVERY_PARTS = ("data", "00-newspaper_data", "crawler", "discovery", ".keep")
DEFAULT_REPORTS_PARTS = ("data", "00-newspaper_data", "crawler", "reports", ".keep")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover MVS Noticias article URLs beyond shallow category pagination."
    )
    parser.add_argument("--discovery-dir", type=Path, default=None)
    parser.add_argument("--reports-dir", type=Path, default=None)
    parser.add_argument("--max-section-pages", type=int, default=10)
    parser.add_argument("--max-topic-pages", type=int, default=50)
    parser.add_argument("--max-article-pages-to-probe", type=int, default=500)
    parser.add_argument("--max-topics", type=int, default=None)
    parser.add_argument("--max-urls", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--pause-seconds", type=float, default=0.1)
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel article-page probes. Sections and topic pagination remain sequential.",
    )
    parser.add_argument(
        "--fetch-profile",
        choices=["default", "browser"],
        default="browser",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    discovery_dir = args.discovery_dir or media_output_path(*DEFAULT_DISCOVERY_PARTS).parent
    reports_dir = args.reports_dir or media_output_path(*DEFAULT_REPORTS_PARTS).parent
    discovered = discover_mvs_urls(
        max_section_pages=args.max_section_pages,
        max_topic_pages=args.max_topic_pages,
        max_article_pages_to_probe=args.max_article_pages_to_probe,
        max_topics=args.max_topics,
        max_urls=args.max_urls,
        timeout=args.timeout,
        pause_seconds=args.pause_seconds,
        fetch_profile=args.fetch_profile,
        workers=args.workers,
    )
    report = build_mvs_report(discovered)
    outputs = write_mvs_outputs(discovered, report, discovery_dir, reports_dir)
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

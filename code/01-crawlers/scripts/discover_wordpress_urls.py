"""Discover article URLs from WordPress REST API sources."""

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

from crawler_core.wordpress import (  # noqa: E402
    build_wordpress_discovery_report,
    discover_wordpress_urls,
    load_wordpress_sources,
    write_discovery_outputs,
)
from project_paths import media_input_path, media_output_path  # noqa: E402


DEFAULT_SOURCES = media_input_path(
    "data",
    "00-newspaper_data",
    "crawler",
    "registry",
    "sources.csv",
)
DEFAULT_CAPABILITIES = media_input_path(
    "data",
    "00-newspaper_data",
    "crawler",
    "registry",
    "crawl_capabilities.csv",
)
DEFAULT_DISCOVERY_PARTS = ("data", "00-newspaper_data", "crawler", "discovery", ".keep")
DEFAULT_REPORTS_PARTS = ("data", "00-newspaper_data", "crawler", "reports", ".keep")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover article URLs from sources with WordPress REST APIs."
    )
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--capabilities", type=Path, default=DEFAULT_CAPABILITIES)
    parser.add_argument(
        "--discovery-dir",
        type=Path,
        default=None,
        help="Output directory for discovered URL CSV/parquet. Default: MEDIA_ROOT/data/00-newspaper_data/crawler/discovery",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=None,
        help="Output directory for wordpress_discovery_report.md. Default: MEDIA_ROOT/data/00-newspaper_data/crawler/reports",
    )
    parser.add_argument(
        "--include-blocked",
        action="store_true",
        help="Include all sources where the WordPress API is available, even if the homepage was blocked/paywall-like.",
    )
    parser.add_argument(
        "--source-id",
        action="append",
        default=None,
        help="Restrict discovery to one source_id. Repeat for multiple sources.",
    )
    parser.add_argument("--limit-sources", type=int, default=None)
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Maximum WordPress API pages per source. Default is 5 for safe pilot runs.",
    )
    parser.add_argument(
        "--all-pages",
        action="store_true",
        help="Ignore --max-pages and page each WordPress API until it returns no more posts.",
    )
    parser.add_argument("--per-page", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--pause-seconds", type=float, default=0.5)
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        help="Checkpoint CSV path. Default: <discovery-dir>/discovered_urls_wordpress.checkpoint.csv",
    )
    parser.add_argument(
        "--no-checkpoint",
        action="store_true",
        help="Disable per-source checkpoint writes.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Load the checkpoint/output CSV if present and skip source_ids already present.",
    )
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="With --resume, retry sources that only have error rows and no discovered URLs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    discovery_dir = args.discovery_dir or media_output_path(*DEFAULT_DISCOVERY_PARTS).parent
    reports_dir = args.reports_dir or media_output_path(*DEFAULT_REPORTS_PARTS).parent
    output_csv = discovery_dir / "discovered_urls_wordpress.csv"
    checkpoint_path = args.checkpoint or (discovery_dir / "discovered_urls_wordpress.checkpoint.csv")

    sources = load_wordpress_sources(
        args.sources,
        args.capabilities,
        include_blocked=args.include_blocked,
    )
    if args.source_id:
        sources = sources[sources["source_id"].isin(args.source_id)].reset_index(drop=True)
        missing = sorted(set(args.source_id) - set(sources["source_id"]))
        if missing:
            raise ValueError("Requested source_id not found in selected WordPress sources: " + ", ".join(missing))

    max_pages = None if args.all_pages else args.max_pages
    initial_rows = load_existing_discovery_rows(
        checkpoint_path=checkpoint_path,
        output_csv=output_csv,
        resume=args.resume,
    )
    if args.resume and initial_rows is not None and not initial_rows.empty:
        completed_sources = completed_source_ids(
            initial_rows,
            retry_errors=args.retry_errors,
            all_pages=args.all_pages,
            pilot_page_cap=args.max_pages,
        )
        before = len(sources)
        sources = sources[~sources["source_id"].isin(completed_sources)].reset_index(drop=True)
        print(
            f"Resume enabled: loaded {len(initial_rows):,} existing rows; "
            f"skipping {before - len(sources):,} completed sources"
        )

    discovered = discover_wordpress_urls(
        sources,
        limit_sources=args.limit_sources,
        max_pages=max_pages,
        per_page=args.per_page,
        timeout=args.timeout,
        pause_seconds=args.pause_seconds,
        checkpoint_path=None if args.no_checkpoint else checkpoint_path,
        initial_rows=initial_rows,
    )
    report = build_wordpress_discovery_report(discovered)
    outputs = write_discovery_outputs(discovered, report, discovery_dir, reports_dir)

    print(f"WordPress sources considered: {len(sources):,}")
    print(f"Page mode: {'all pages' if args.all_pages else f'max {args.max_pages} pages'}")
    if not args.no_checkpoint:
        print(f"Checkpoint path: {checkpoint_path}")
    print(f"Discovered rows: {len(discovered):,}")
    print(f"Wrote CSV: {outputs.discovered_csv}")
    if outputs.discovered_parquet:
        print(f"Wrote parquet: {outputs.discovered_parquet}")
    else:
        print(f"Skipped parquet: {outputs.parquet_error}")
    print(f"Wrote report: {outputs.report_path}")


def load_existing_discovery_rows(
    *,
    checkpoint_path: Path,
    output_csv: Path,
    resume: bool,
) -> pd.DataFrame | None:
    """Load prior discovery rows when resuming a long run."""
    if not resume:
        return None
    existing_path = checkpoint_path if checkpoint_path.exists() else output_csv
    if not existing_path.exists():
        print("Resume enabled: no existing checkpoint/output CSV found")
        return None
    return pd.read_csv(existing_path)


def completed_source_ids(
    existing_rows: pd.DataFrame,
    *,
    retry_errors: bool,
    all_pages: bool,
    pilot_page_cap: int,
) -> set[str]:
    """Infer which sources can be skipped in a resumed discovery run."""
    if "source_complete" in existing_rows.columns:
        source_summary = existing_rows.groupby("source_id", dropna=True).agg(
            has_url=("url", lambda values: values.notna().any()),
            has_error=("error", lambda values: values.notna().any()),
            complete=("source_complete", lambda values: values.astype(str).str.lower().isin({"true", "1"}).any()),
        )
        skip = source_summary["complete"]
        if not retry_errors:
            skip = skip | (source_summary["has_error"] & ~source_summary["has_url"])
        return set(source_summary[skip].index)

    source_summary = existing_rows.groupby("source_id", dropna=True).agg(
        has_url=("url", lambda values: values.notna().any()),
        has_error=("error", lambda values: values.notna().any()),
        max_page=("discovery_page", "max"),
    )

    if all_pages:
        # Legacy pilot outputs did not store whether the archive was exhausted.
        # A source that reached the pilot cap may have more pages, so rerun it.
        skip = source_summary["has_url"] & (source_summary["max_page"] < pilot_page_cap)
    else:
        skip = source_summary["has_url"]

    if not retry_errors:
        skip = skip | (source_summary["has_error"] & ~source_summary["has_url"])
    return set(source_summary[skip].index)


if __name__ == "__main__":
    main()

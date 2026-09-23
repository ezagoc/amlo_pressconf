"""Discover Grupo Healy / El Imparcial article URLs from daily Arc sitemaps."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
CRAWLER_DIR = SCRIPT_DIR.parents[0]
CODE_DIR = SCRIPT_DIR.parents[1]
REPO_ROOT = SCRIPT_DIR.parents[2]

for path in (CRAWLER_DIR, CODE_DIR, REPO_ROOT):
    sys.path.insert(0, str(path))

from crawler_core.grupo_healy import (  # noqa: E402
    build_grupo_healy_report,
    discover_grupo_healy_urls,
    parse_date,
    write_grupo_healy_outputs,
)
from project_paths import media_input_path, media_output_path  # noqa: E402


DEFAULT_SOURCES = media_input_path(
    "data",
    "00-newspaper_data",
    "crawler",
    "registry",
    "sources.csv",
)
DEFAULT_DISCOVERY_PARTS = ("data", "00-newspaper_data", "crawler", "discovery", ".keep")
DEFAULT_REPORTS_PARTS = ("data", "00-newspaper_data", "crawler", "reports", ".keep")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover El Imparcial / Grupo Healy URLs from daily Arc sitemap feeds."
    )
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--discovery-dir", type=Path, default=None)
    parser.add_argument("--reports-dir", type=Path, default=None)
    parser.add_argument("--source-id", action="append", default=None)
    parser.add_argument("--from", dest="from_date", required=True, help="Start date, YYYY-MM-DD.")
    parser.add_argument("--to", dest="to_date", default=date.today().isoformat(), help="End date, YYYY-MM-DD.")
    parser.add_argument("--max-urls", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--pause-seconds", type=float, default=0.05)
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=5_000,
        help="Write a checkpoint every N rows. Use 0 to disable.",
    )
    parser.add_argument("--checkpoint-path", type=Path, default=None)
    parser.add_argument(
        "--ignore-checkpoint",
        action="store_true",
        help="Ignore an existing checkpoint and start discovery from scratch.",
    )
    parser.add_argument(
        "--include-shared-paths",
        action="store_true",
        help="Also assign shared sitewide sections such as /mexico/, /mundo/, /dinero/, /deporte/, and /espectaculos/ to selected source IDs.",
    )
    parser.add_argument(
        "--output-stem",
        default=None,
        help="Output filename stem. Defaults to discovered_urls_<source_id> for one source, otherwise discovered_urls_grupo_healy_elimparcial.",
    )
    return parser.parse_args()


def main() -> None:
    import pandas as pd

    args = parse_args()
    discovery_dir = args.discovery_dir or media_output_path(*DEFAULT_DISCOVERY_PARTS).parent
    reports_dir = args.reports_dir or media_output_path(*DEFAULT_REPORTS_PARTS).parent
    output_stem = args.output_stem or default_output_stem(args.source_id)
    checkpoint_path = args.checkpoint_path
    if checkpoint_path is None and args.checkpoint_every > 0:
        checkpoint_path = discovery_dir / f"{output_stem}_checkpoint.csv"

    sources = pd.read_csv(args.sources)
    discovered = discover_grupo_healy_urls(
        sources,
        from_date=parse_date(args.from_date),
        to_date=parse_date(args.to_date),
        source_ids=args.source_id,
        max_urls=args.max_urls,
        timeout=args.timeout,
        pause_seconds=args.pause_seconds,
        checkpoint_path=checkpoint_path,
        checkpoint_every=args.checkpoint_every,
        resume_checkpoint=not args.ignore_checkpoint,
        include_shared_paths=args.include_shared_paths,
    )
    report = build_grupo_healy_report(discovered)
    outputs = write_grupo_healy_outputs(
        discovered,
        report,
        discovery_dir,
        reports_dir,
        output_stem=output_stem,
    )
    print(f"Discovered rows: {len(discovered):,}")
    print(f"Discovered URLs: {discovered['url'].notna().sum() if 'url' in discovered else 0:,}")
    print(f"Wrote CSV: {outputs.discovered_csv}")
    if outputs.discovered_parquet:
        print(f"Wrote parquet: {outputs.discovered_parquet}")
    else:
        print(f"Skipped parquet: {outputs.parquet_error}")
    print(f"Wrote report: {outputs.report_path}")


def default_output_stem(source_ids: list[str] | None) -> str:
    """Choose a stable discovery output filename stem."""
    if source_ids and len(source_ids) == 1:
        return f"discovered_urls_{source_ids[0]}"
    return "discovered_urls_grupo_healy_elimparcial"


if __name__ == "__main__":
    main()

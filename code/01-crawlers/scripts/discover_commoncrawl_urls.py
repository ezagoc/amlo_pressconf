"""Discover article URLs from Common Crawl CDX indexes."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
CRAWLER_DIR = SCRIPT_DIR.parents[0]
CODE_DIR = SCRIPT_DIR.parents[1]
REPO_ROOT = SCRIPT_DIR.parents[2]

for path in (CRAWLER_DIR, CODE_DIR, REPO_ROOT):
    sys.path.insert(0, str(path))

from crawler_core.commoncrawl import (  # noqa: E402
    build_commoncrawl_report,
    discover_commoncrawl_urls,
    likely_commoncrawl_article_url,
    load_commoncrawl_indexes,
    load_commoncrawl_sources,
    write_commoncrawl_outputs,
)
from project_paths import media_input_path, media_output_path  # noqa: E402


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
        description="Discover likely article URLs from Common Crawl CDX indexes."
    )
    parser.add_argument("--capabilities", type=Path, default=DEFAULT_CAPABILITIES)
    parser.add_argument("--discovery-dir", type=Path, default=None)
    parser.add_argument("--reports-dir", type=Path, default=None)
    parser.add_argument("--source-id", action="append", default=None)
    parser.add_argument("--limit-sources", type=int, default=None)
    parser.add_argument(
        "--strategy",
        action="append",
        default=None,
        help="Optional recommended_strategy filter. Can be repeated.",
    )
    parser.add_argument(
        "--index-id",
        action="append",
        default=None,
        help="Common Crawl index ID, e.g. CC-MAIN-2026-34. Can be repeated.",
    )
    parser.add_argument("--year", action="append", type=int, default=None)
    parser.add_argument("--limit-indexes", type=int, default=None)
    parser.add_argument(
        "--indexes-per-year",
        type=int,
        default=None,
        help="Keep an evenly spaced sample of Common Crawl indexes in each selected year.",
    )
    parser.add_argument(
        "--path-pattern",
        action="append",
        default=None,
        help="Article path prefix to query, e.g. juarez or nacional. Can be repeated.",
    )
    parser.add_argument(
        "--include-broad-domain",
        action="store_true",
        help="Also query the broad domain pattern. This may be slow or return 504s on large sites.",
    )
    parser.add_argument("--limit-per-query", type=int, default=50_000)
    parser.add_argument("--max-urls-per-source", type=int, default=None)
    parser.add_argument("--page-size", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    parser.add_argument("--body-text-limit", type=int, default=80_000_000)
    parser.add_argument(
        "--checkpoint-per-index",
        action="store_true",
        help="Save each completed index and reuse it when rerunning the same discovery settings.",
    )
    parser.add_argument(
        "--append-existing",
        action="store_true",
        help=(
            "Merge new rows into discovered_urls_commoncrawl.*. When --source-id "
            "is used, previous rows for those source IDs are replaced."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    discovery_dir = args.discovery_dir or media_output_path(*DEFAULT_DISCOVERY_PARTS).parent
    reports_dir = args.reports_dir or media_output_path(*DEFAULT_REPORTS_PARTS).parent

    sources = load_commoncrawl_sources(
        args.capabilities,
        strategies=set(args.strategy or []) or None,
    )
    index_ids = load_commoncrawl_indexes(
        index_ids=args.index_id,
        years=set(args.year or []) or None,
        limit_indexes=args.limit_indexes,
        timeout=args.timeout,
    )
    if args.indexes_per_year is not None:
        index_ids = select_indexes_per_year(index_ids, args.indexes_per_year)
    print(f"Common Crawl indexes selected: {', '.join(index_ids)}")

    def discover_indexes(selected_indexes: list[str]) -> pd.DataFrame:
        return discover_commoncrawl_urls(
            sources,
            index_ids=selected_indexes,
            source_ids=args.source_id,
            limit_sources=args.limit_sources,
            path_patterns=args.path_pattern,
            include_broad_domain=args.include_broad_domain,
            limit_per_query=args.limit_per_query,
            max_urls_per_source=args.max_urls_per_source,
            page_size=args.page_size,
            timeout=args.timeout,
            pause_seconds=args.pause_seconds,
            body_text_limit=args.body_text_limit,
        )

    if args.checkpoint_per_index:
        settings = {
            "checkpoint_schema_version": 2,
            "capabilities": str(args.capabilities.resolve()),
            "source_id": args.source_id,
            "limit_sources": args.limit_sources,
            "indexes_per_year": args.indexes_per_year,
            "strategy": args.strategy,
            "path_pattern": args.path_pattern,
            "include_broad_domain": args.include_broad_domain,
            "limit_per_query": args.limit_per_query,
            "max_urls_per_source": args.max_urls_per_source,
            "page_size": args.page_size,
            "body_text_limit": args.body_text_limit,
        }
        run_key = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:12]
        checkpoint_dir = discovery_dir / "commoncrawl_index_checkpoints" / run_key
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        discovered, failed_indexes = discover_with_index_checkpoints(
            index_ids, checkpoint_dir, discover_indexes
        )
    else:
        discovered = discover_indexes(index_ids)
        failed_indexes = []
    if not discovered.empty and {"source_id", "url"}.issubset(discovered.columns):
        keep = [
            pd.isna(url) or likely_commoncrawl_article_url(url, source_id=source_id)
            for source_id, url in zip(discovered["source_id"], discovered["url"])
        ]
        discovered = discovered.loc[keep].reset_index(drop=True)
    if discovered.empty and failed_indexes:
        reports_dir.mkdir(parents=True, exist_ok=True)
        failed_path = reports_dir / "commoncrawl_failed_indexes.csv"
        pd.DataFrame(failed_indexes).to_csv(failed_path, index=False, encoding="utf-8")
        print(f"No URLs saved; {len(failed_indexes)} indexes failed. Rerun the same command.")
        raise SystemExit(2)
    if args.append_existing:
        discovered = merge_existing_discovery(
            discovery_dir,
            discovered,
            replace_source_ids=set(args.source_id or []),
        )
    report = build_commoncrawl_report(discovered)
    outputs = write_commoncrawl_outputs(discovered, report, discovery_dir, reports_dir)

    print(f"Common Crawl sources considered: {len(sources):,}")
    print(f"Discovered rows: {len(discovered):,}")
    print(f"Wrote CSV: {outputs.discovered_csv}")
    if outputs.discovered_parquet:
        print(f"Wrote parquet: {outputs.discovered_parquet}")
    else:
        print(f"Skipped parquet: {outputs.parquet_error}")
    print(f"Wrote report: {outputs.report_path}")
    if args.checkpoint_per_index:
        reports_dir.mkdir(parents=True, exist_ok=True)
        failed_path = reports_dir / "commoncrawl_failed_indexes.csv"
        pd.DataFrame(failed_indexes, columns=["index_id", "error", "urls"]).to_csv(
            failed_path, index=False, encoding="utf-8"
        )
        if failed_indexes:
            print(f"Incomplete: {len(failed_indexes)} indexes failed; details: {failed_path}")
            print("Rerun the same command to retry only failed indexes.")
            raise SystemExit(2)


def discover_with_index_checkpoints(
    index_ids: list[str], checkpoint_dir: Path, discover_indexes
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    """Keep completed indexes and partial URLs while retrying failed indexes later."""
    frames: list[pd.DataFrame] = []
    failed_indexes: list[dict[str, object]] = []
    for index_id in index_ids:
        checkpoint_path = checkpoint_dir / f"{index_id}.csv"
        partial_path = checkpoint_dir / f"{index_id}.partial.csv"
        if checkpoint_path.exists():
            print(f"Reusing completed index: {checkpoint_path}")
            frames.append(pd.read_csv(checkpoint_path, low_memory=False))
            continue
        previous = pd.read_csv(partial_path, low_memory=False) if partial_path.exists() else pd.DataFrame()
        try:
            current = discover_indexes([index_id])
        except Exception as exc:
            current = pd.DataFrame()
            failure = f"{type(exc).__name__}: {exc}"
        else:
            errors = current.get("error", pd.Series(dtype=object)).dropna().astype(str)
            failures = errors[errors != "no_likely_article_urls_found"]
            failure = str(failures.iloc[0]) if not failures.empty else None
        previous_urls = previous[previous["url"].notna()] if "url" in previous else pd.DataFrame()
        frame = dedupe_discovery_rows(pd.concat([previous_urls, current], ignore_index=True))
        if failure:
            if not frame.empty:
                write_index_checkpoint(frame, partial_path)
                frames.append(frame)
            urls = int(frame["url"].notna().sum()) if "url" in frame else 0
            failed_indexes.append({"index_id": index_id, "error": failure, "urls": urls})
            print(f"Incomplete index {index_id}: {failure}; saved_urls={urls:,}")
            continue
        write_index_checkpoint(frame, checkpoint_path)
        print(f"Checkpointed index: {checkpoint_path}")
        frames.append(frame)
    discovered = dedupe_discovery_rows(pd.concat(frames, ignore_index=True)) if frames else pd.DataFrame()
    return discovered, failed_indexes


def select_indexes_per_year(index_ids: list[str], count: int) -> list[str]:
    """Select evenly spaced snapshots while preserving year and index order."""
    count = max(1, int(count))
    grouped: dict[str, list[str]] = {}
    ungrouped: list[str] = []
    for index_id in index_ids:
        match = re.search(r"CC-MAIN-(\d{4})-", index_id)
        if match:
            grouped.setdefault(match.group(1), []).append(index_id)
        else:
            ungrouped.append(index_id)

    selected: list[str] = []
    for indexes in grouped.values():
        if len(indexes) <= count:
            selected.extend(indexes)
            continue
        positions = {
            round(position * (len(indexes) - 1) / (count - 1))
            for position in range(count)
        } if count > 1 else {0}
        selected.extend(indexes[position] for position in sorted(positions))
    selected.extend(ungrouped)
    return selected


def dedupe_discovery_rows(discovered: pd.DataFrame) -> pd.DataFrame:
    if {"source_id", "url"}.issubset(discovered.columns):
        url_rows = discovered[discovered["url"].notna()].drop_duplicates(
            ["source_id", "url"], keep="last"
        )
        error_rows = discovered[discovered["url"].isna()]
        return pd.concat([url_rows, error_rows], ignore_index=True)
    return discovered


def write_index_checkpoint(frame: pd.DataFrame, path: Path) -> None:
    pending_path = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(pending_path, index=False, encoding="utf-8")
    pending_path.replace(path)


def merge_existing_discovery(
    discovery_dir: Path,
    discovered: pd.DataFrame,
    *,
    replace_source_ids: set[str],
) -> pd.DataFrame:
    """Merge new Common Crawl rows with an existing discovery output."""
    parquet_path = discovery_dir / "discovered_urls_commoncrawl.parquet"
    csv_path = discovery_dir / "discovered_urls_commoncrawl.csv"
    existing = pd.DataFrame()
    if parquet_path.exists():
        existing = pd.read_parquet(parquet_path)
    elif csv_path.exists():
        existing = pd.read_csv(csv_path)

    if existing.empty:
        return discovered
    if replace_source_ids and "source_id" in existing.columns:
        existing = existing[~existing["source_id"].isin(replace_source_ids)].copy()
    merged = pd.concat([existing, discovered], ignore_index=True)
    if {"source_id", "url"}.issubset(merged.columns):
        url_rows = merged[merged["url"].notna()].drop_duplicates(["source_id", "url"], keep="last")
        error_rows = merged[merged["url"].isna()]
        merged = pd.concat([url_rows, error_rows], ignore_index=True)
    return merged.reset_index(drop=True)


if __name__ == "__main__":
    main()

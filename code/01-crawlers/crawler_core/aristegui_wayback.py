"""Checkpointed Wayback discovery for Aristegui Noticias."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from crawler_core.wayback import (
    build_wayback_report,
    dedupe_wayback_discovery,
    discover_wayback_query,
)


SOURCE_ID = "aristeguinoticias"
SOURCE_NAME = "Aristegui Noticias"
SOURCE_URL = "https://aristeguinoticias.com/"
HOSTS = (
    "aristeguinoticias.com",
    "www.aristeguinoticias.com",
    "editorial.aristeguinoticias.com",
)
CHECKPOINT_COLUMNS = (
    "source_id",
    "source_name",
    "source_url",
    "url",
    "canonical_url",
    "original_url",
    "wayback_url",
    "date_published",
    "lastmod",
    "topic",
    "discovery_strategy",
    "wayback_query",
    "wayback_urlkey",
    "wayback_timestamp",
    "wayback_mimetype",
    "wayback_statuscode",
    "wayback_digest",
    "wayback_length",
    "status",
    "page_number",
    "error",
    "discovered_at",
)


@dataclass(frozen=True)
class AristeguiWaybackOutputs:
    discovered_csv: Path
    discovered_parquet: Path | None
    report_path: Path
    parquet_error: str | None = None


def discover_aristegui_wayback_urls(
    *,
    from_year: int = 2012,
    to_year: int = 2026,
    patterns: list[str] | None = None,
    limit_per_page: int = 1_000,
    max_pages_per_query: int = 100,
    max_urls: int | None = 400_000,
    timeout: float = 120.0,
    pause_seconds: float = 1.0,
    body_text_limit: int = 80_000_000,
    checkpoint_dir: Path,
    resume: bool = False,
) -> pd.DataFrame:
    """Query broad Aristegui CDX patterns year by year with per-window checkpoints."""
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    selected_patterns = patterns or default_sharded_patterns()
    source = pd.Series(
        {
            "source_id": SOURCE_ID,
            "source_name": SOURCE_NAME,
            "canonical_url": SOURCE_URL,
        }
    )
    existing_frames = load_checkpoint_frames(checkpoint_dir) if resume else []
    seen_originals = set()
    for frame in existing_frames:
        if "original_url" in frame.columns:
            seen_originals.update(frame["original_url"].dropna().astype(str))
    print(
        f"Wayback resume: checkpoints={len(existing_frames):,}, "
        f"unique originals={len(seen_originals):,}"
    )

    total_windows = len(selected_patterns)
    completed_windows = 0
    for pattern in selected_patterns:
        completed_windows += 1
        pattern_label = pattern.replace(".", "_").replace("/", "_").replace("*", "star")
        checkpoint_path = checkpoint_dir / f"{pattern_label}.csv"
        done_path = checkpoint_path.with_suffix(".done")
        if resume and done_path.exists() and checkpoint_path.exists():
            print(
                f"  shard {completed_windows}/{total_windows}: {pattern} already checkpointed"
            )
            continue
        if max_urls is not None and len(seen_originals) >= max_urls:
            print(f"Reached max_urls={max_urls:,}; stopping Wayback discovery")
            return combine_checkpoint_frames(checkpoint_dir)

        print(
            f"  shard {completed_windows}/{total_windows}: {pattern} "
            f"starting with {len(seen_originals):,} URLs"
        )
        rows = discover_wayback_query(
            source,
            url_pattern=pattern,
            seen_source_originals=seen_originals,
            from_timestamp=f"{from_year}0101",
            to_timestamp=f"{to_year}1231",
            limit_per_page=limit_per_page,
            max_pages=max_pages_per_query,
            max_urls_per_source=max_urls,
            timeout=timeout,
            pause_seconds=pause_seconds,
            body_text_limit=body_text_limit,
        )
        frame = pd.DataFrame(rows)
        if frame.empty:
            frame = pd.DataFrame(columns=CHECKPOINT_COLUMNS)
        frame["wayback_window_from"] = f"{from_year}0101"
        frame["wayback_window_to"] = f"{to_year}1231"
        frame["wayback_pattern"] = pattern
        write_frame_atomic(frame, checkpoint_path)
        errors = int(frame["error"].notna().sum()) if "error" in frame.columns else 0
        urls = int(frame["url"].notna().sum()) if "url" in frame.columns else 0
        print(
            f"  checkpointed {checkpoint_path.name}: rows={len(frame):,}, "
            f"urls={urls:,}, errors={errors:,}, total={len(seen_originals):,}"
        )
        if errors == 0:
            done_path.write_text("complete\n", encoding="ascii")
        if pause_seconds:
            time.sleep(pause_seconds)

    return combine_checkpoint_frames(checkpoint_dir)


def default_sharded_patterns() -> list[str]:
    """Shard Aristegui's DDMM article paths by the leading day digits."""
    return [f"{host}/{day:02d}*" for host in HOSTS for day in range(1, 32)]


def load_checkpoint_frames(checkpoint_dir: Path) -> list[pd.DataFrame]:
    frames = []
    for path in sorted(checkpoint_dir.glob("*.csv")):
        try:
            frames.append(pd.read_csv(path, low_memory=False))
        except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
            print(f"  ignored unreadable checkpoint {path.name}: {type(exc).__name__}: {exc}")
    return frames


def combine_checkpoint_frames(checkpoint_dir: Path) -> pd.DataFrame:
    frames = load_checkpoint_frames(checkpoint_dir)
    if not frames:
        return pd.DataFrame(columns=CHECKPOINT_COLUMNS)
    return dedupe_wayback_discovery(pd.concat(frames, ignore_index=True))


def write_frame_atomic(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_name(f"{path.stem}.tmp-{os.getpid()}-{time.time_ns()}{path.suffix}")
    frame.to_csv(temporary, index=False, encoding="utf-8")
    last_error = None
    for attempt in range(1, 11):
        try:
            os.replace(temporary, path)
            return
        except PermissionError as exc:
            last_error = exc
            if attempt < 10:
                time.sleep(min(5.0, attempt * 0.25))
        except OSError as exc:
            last_error = exc
            break
    raise OSError(f"Could not save Wayback checkpoint {path}; recovery file: {temporary}") from last_error


def write_aristegui_wayback_outputs(
    discovered: pd.DataFrame,
    discovery_dir: Path,
    reports_dir: Path,
) -> AristeguiWaybackOutputs:
    discovery_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    csv_path = discovery_dir / "discovered_urls_aristeguinoticias_wayback.csv"
    parquet_path = discovery_dir / "discovered_urls_aristeguinoticias_wayback.parquet"
    report_path = reports_dir / "aristeguinoticias_wayback_discovery_report.md"
    discovered.to_csv(csv_path, index=False, encoding="utf-8")
    parquet_error = None
    try:
        discovered.to_parquet(parquet_path, index=False)
    except Exception as exc:
        parquet_error = f"{type(exc).__name__}: {exc}"
        parquet_path = None
    report_path.write_text(build_wayback_report(discovered), encoding="utf-8")
    return AristeguiWaybackOutputs(csv_path, parquet_path, report_path, parquet_error)

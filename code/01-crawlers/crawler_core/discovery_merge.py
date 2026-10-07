"""Merge URL discovery outputs while retaining provenance."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pandas as pd


GRUPO_REFORMA_IDS = {"reforma", "elnorte"}
STRATEGY_PRIORITY = {
    "official_sitemap": 0,
    "sitemap": 0,
    "source_api": 1,
    "commoncrawl": 2,
    "wayback": 3,
}


@dataclass(frozen=True)
class MergedDiscoveryOutput:
    source_id: str
    csv_path: Path
    parquet_path: Path | None
    report_path: Path
    rows: int
    parquet_error: str | None = None


def read_discovery(path: Path) -> pd.DataFrame:
    """Read one CSV or parquet discovery output."""
    if path.suffix.lower() in {".parquet", ".gzip"}:
        return pd.read_parquet(path)
    return pd.read_csv(path, low_memory=False)


def canonical_discovery_url(source_id: object, url: object) -> object:
    """Normalize a URL for stable cross-strategy deduplication."""
    if pd.isna(url):
        return pd.NA
    parsed = urlparse(str(url).strip())
    if not parsed.netloc:
        return pd.NA
    if str(source_id) in GRUPO_REFORMA_IDS:
        root = str(source_id) + ".com"
        if re.search(r"/(?:ar|op)\d+/?$", parsed.path, flags=re.I):
            return urlunparse(("https", f"www.{root}", parsed.path.rstrip("/"), "", "", ""))
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, "", parsed.query, ""))


def merge_discoveries(
    frames: list[pd.DataFrame], *, source_ids: set[str] | None = None
) -> pd.DataFrame:
    """Merge discoveries by source and canonical URL, preserving provenance."""
    usable = [frame.copy() for frame in frames if not frame.empty]
    if not usable:
        return pd.DataFrame()
    discovered = pd.concat(usable, ignore_index=True, sort=False)
    discovered = discovered.drop(
        columns=[
            "discovery_strategies",
            "archive_first_capture",
            "archive_last_capture",
            "commoncrawl_index_count",
        ],
        errors="ignore",
    )
    if source_ids:
        discovered = discovered[discovered["source_id"].astype(str).isin(source_ids)].copy()
    discovered = discovered[discovered["url"].notna()].copy()
    discovered["url"] = [
        canonical_discovery_url(source_id, url)
        for source_id, url in zip(discovered["source_id"], discovered["url"])
    ]
    discovered = discovered[discovered["url"].notna()].copy()
    discovered["canonical_url"] = discovered["url"]
    strategy = discovered.get("discovery_strategy", pd.Series("unknown", index=discovered.index))
    discovered["discovery_strategy"] = strategy.fillna("unknown").astype(str)
    discovered["_priority"] = discovered["discovery_strategy"].map(STRATEGY_PRIORITY).fillna(9)

    keys = ["source_id", "url"]
    discovered = discovered.sort_values(keys + ["_priority"], kind="stable")
    base = discovered.drop_duplicates(keys, keep="first").copy()

    provenance = (
        discovered.groupby(keys, sort=False)["discovery_strategy"]
        .agg(lambda values: ";".join(dict.fromkeys(values.astype(str))))
        .rename("discovery_strategies")
        .reset_index()
    )
    base = base.merge(provenance, on=keys, how="left")

    if "commoncrawl_timestamp" in discovered:
        timestamp_text = (
            pd.to_numeric(discovered["commoncrawl_timestamp"], errors="coerce")
            .round()
            .astype("Int64")
            .astype("string")
        )
        captures = pd.to_datetime(
            timestamp_text,
            format="%Y%m%d%H%M%S",
            errors="coerce",
            utc=True,
        )
        discovered["_archive_capture"] = captures
        capture_summary = (
            discovered.groupby(keys, sort=False)["_archive_capture"]
            .agg(archive_first_capture="min", archive_last_capture="max")
            .reset_index()
        )
        for column in ("archive_first_capture", "archive_last_capture"):
            capture_summary[column] = capture_summary[column].dt.strftime("%Y-%m-%d")
        base = base.merge(capture_summary, on=keys, how="left")

    if "commoncrawl_index" in discovered:
        index_counts = (
            discovered.groupby(keys, sort=False)["commoncrawl_index"]
            .nunique(dropna=True)
            .rename("commoncrawl_index_count")
            .reset_index()
        )
        base = base.merge(index_counts, on=keys, how="left")

    return base.drop(columns=["_priority"], errors="ignore").sort_values(keys).reset_index(drop=True)


def expand_discovery_inputs(paths: list[Path]) -> list[Path]:
    """Expand discovery files and Common Crawl checkpoint directories."""
    expanded: list[Path] = []
    for path in paths:
        if path.is_dir():
            expanded.extend(
                candidate
                for candidate in sorted(path.rglob("CC-MAIN-*.csv"))
                if not candidate.name.endswith(".partial.csv")
            )
        else:
            expanded.append(path)
    return expanded


def build_merged_discovery_report(source_id: str, discovered: pd.DataFrame) -> str:
    """Create a concise provenance and coverage report."""
    lines = [
        f"# {source_id} merged discovery report",
        "",
        f"- Unique URLs: {len(discovered):,}",
    ]
    if "discovery_strategies" in discovered:
        counts = discovered["discovery_strategies"].value_counts(dropna=False)
        lines.extend(["", "## Discovery provenance", ""])
        lines.extend(f"- {label}: {count:,}" for label, count in counts.items())
    suffix = discovered["url"].astype(str).str.extract(r"/(ar|op)\d+/?$")[0]
    suffix_counts = suffix.value_counts()
    if not suffix_counts.empty:
        lines.extend(["", "## URL identifier families", ""])
        lines.extend(f"- {label}: {count:,}" for label, count in suffix_counts.items())
    if "archive_first_capture" in discovered:
        years = discovered["archive_first_capture"].astype("string").str[:4].value_counts().sort_index()
        if not years.empty:
            lines.extend(["", "## First Common Crawl capture year", ""])
            lines.extend(f"- {year}: {count:,}" for year, count in years.items() if year != "<NA>")
    return "\n".join(lines) + "\n"


def write_merged_discoveries(
    discovered: pd.DataFrame, output_dir: Path, reports_dir: Path
) -> list[MergedDiscoveryOutput]:
    """Write one merged CSV, parquet, and report per source."""
    output_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[MergedDiscoveryOutput] = []
    for source_id, frame in discovered.groupby("source_id", sort=True):
        source_id = str(source_id)
        frame = frame.reset_index(drop=True)
        csv_path = output_dir / f"discovered_urls_{source_id}.csv"
        parquet_path = output_dir / f"discovered_urls_{source_id}.parquet"
        report_path = reports_dir / f"{source_id}_discovery_report.md"
        frame.to_csv(csv_path, index=False, encoding="utf-8")
        parquet_error = None
        try:
            frame.to_parquet(parquet_path, index=False)
        except Exception as exc:
            parquet_error = str(exc)
            parquet_path = None
        report_path.write_text(
            build_merged_discovery_report(source_id, frame), encoding="utf-8"
        )
        outputs.append(
            MergedDiscoveryOutput(
                source_id=source_id,
                csv_path=csv_path,
                parquet_path=parquet_path,
                report_path=report_path,
                rows=len(frame),
                parquet_error=parquet_error,
            )
        )
    return outputs

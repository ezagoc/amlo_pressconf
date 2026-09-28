"""Tests for cross-strategy URL discovery merging."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crawler_core.discovery_merge import (  # noqa: E402
    canonical_discovery_url,
    expand_discovery_inputs,
    merge_discoveries,
)


def test_grupo_reforma_url_canonicalization_drops_variant_query() -> None:
    assert canonical_discovery_url(
        "reforma", "http://reforma.com/story/ar123456?v=3#fragment"
    ) == "https://www.reforma.com/story/ar123456"


def test_merge_prefers_official_row_and_retains_archive_provenance() -> None:
    official = pd.DataFrame(
        [
            {
                "source_id": "reforma",
                "url": "https://www.reforma.com/story/ar123456",
                "lastmod": "2026-01-02",
                "discovery_strategy": "official_sitemap",
            }
        ]
    )
    archive = pd.DataFrame(
        [
            {
                "source_id": "reforma",
                "url": "http://reforma.com/story/ar123456?v=3",
                "discovery_strategy": "commoncrawl",
                "commoncrawl_index": "CC-MAIN-2025-01",
                "commoncrawl_timestamp": "20250103040506",
            }
        ]
    )
    merged = merge_discoveries([archive, official])
    assert len(merged) == 1
    assert merged.iloc[0]["lastmod"] == "2026-01-02"
    assert merged.iloc[0]["discovery_strategy"] == "official_sitemap"
    assert merged.iloc[0]["discovery_strategies"] == "official_sitemap;commoncrawl"
    assert merged.iloc[0]["archive_first_capture"] == "2025-01-03"
    assert merged.iloc[0]["commoncrawl_index_count"] == 1


def test_expand_inputs_uses_completed_checkpoints_only(tmp_path: Path) -> None:
    (tmp_path / "CC-MAIN-2020-50.csv").write_text("source_id,url\n", encoding="utf-8")
    (tmp_path / "CC-MAIN-2020-45.partial.csv").write_text("source_id,url\n", encoding="utf-8")
    assert expand_discovery_inputs([tmp_path]) == [tmp_path / "CC-MAIN-2020-50.csv"]

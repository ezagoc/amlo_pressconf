"""Tests for GDELT URL discovery."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crawler_core.gdelt import canonical_gdelt_url, gdelt_article_row, weekly_windows  # noqa: E402


def test_weekly_windows_are_inclusive() -> None:
    assert weekly_windows(date(2024, 1, 1), date(2024, 1, 10), 7) == [
        (date(2024, 1, 1), date(2024, 1, 7)),
        (date(2024, 1, 8), date(2024, 1, 10)),
    ]


def test_canonical_gdelt_url_rejects_other_domains() -> None:
    assert canonical_gdelt_url(
        "http://reforma.com/story/ar123?v=3", "reforma.com"
    ) == "https://www.reforma.com/story/ar123"
    assert str(canonical_gdelt_url("https://example.com/story/ar123", "reforma.com")) == "<NA>"


def test_gdelt_article_row_keeps_only_article_ids() -> None:
    source = {"source_name": "Reforma", "source_url": "https://www.reforma.com/", "domain": "reforma.com"}
    article = {
        "url": "https://www.reforma.com/story/ar123456",
        "title": "Story",
        "seendate": "20240101T120000Z",
    }
    row = gdelt_article_row("reforma", source, article)
    assert row["url"] == article["url"]
    assert row["gdelt_seen_at"].startswith("2024-01-01")

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd


CRAWLER_DIR = Path(__file__).resolve().parents[1]
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

from crawler_core.commoncrawl import (  # noqa: E402
    augment_sources_from_registry,
    commoncrawl_url_patterns,
    likely_commoncrawl_article_url,
)
from crawler_core.news_sitemaps import (  # noqa: E402
    discover_news_sitemaps,
    is_source_article_url,
    load_source_state,
)
from crawler_core.sitemap_articles import extract_one_sitemap_article  # noqa: E402
from crawler_core.wayback import likely_wayback_article_url, wayback_url_patterns  # noqa: E402


def sitemap_index(*urls: str) -> str:
    children = "".join(f"<sitemap><loc>{url}</loc></sitemap>" for url in urls)
    return f'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{children}</sitemapindex>'


def urlset(*urls: str) -> str:
    children = "".join(
        f"<url><loc>{url}</loc><lastmod>2019-01-02T03:04:05Z</lastmod></url>"
        for url in urls
    )
    return f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{children}</urlset>'


def test_source_filters_keep_articles_and_reject_sections() -> None:
    assert is_source_article_url(
        "https://www.reforma.com/example-title/ar1234567", "reforma"
    )
    assert not is_source_article_url("https://www.reforma.com/nacional/", "reforma")
    assert is_source_article_url(
        "https://www.milenio.com/politica/example-title", "milenio"
    )
    assert not is_source_article_url(
        "https://www.milenio.com/autores/example-author", "milenio"
    )


def test_page_cap_resumes_at_next_unfinished_sitemap(tmp_path: Path) -> None:
    db_path = tmp_path / "news.sqlite"
    root = "https://www.milenio.com/sitemap/sitemap-articles-index.xml"
    child_1 = "https://www.milenio.com/sitemap/articles/2019-01.xml"
    child_2 = "https://www.milenio.com/sitemap/articles/2019-02.xml"
    responses = {
        root: sitemap_index(child_1, child_2),
        child_1: urlset("https://www.milenio.com/politica/story-one"),
        child_2: urlset("https://www.milenio.com/politica/story-two"),
    }
    requested: list[str] = []

    def fake_fetch(url: str, timeout: float, **kwargs: object) -> dict[str, object]:
        requested.append(url)
        return {
            "status": 200,
            "final_url": url,
            "content_type": "application/xml",
            "text": responses[url],
            "error": pd.NA,
        }

    with patch("crawler_core.news_sitemaps.fetch", side_effect=fake_fetch):
        for _ in range(2):
            discover_news_sitemaps(
                source_ids=["milenio"],
                state_db_path=db_path,
                resume=True,
                max_sitemaps_per_source=1,
                max_urls_per_source=None,
                timeout=1,
                pause_seconds=0,
                request_retries=0,
                retry_backoff_seconds=0,
                workers=1,
            )

    assert requested == [root, child_1, root, child_2]
    assert load_source_state(db_path, "milenio")["url_count"] == 2
    with sqlite3.connect(db_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM sitemap_state WHERE completed=1"
        ).fetchone()[0] == 2


def test_url_cap_resumes_inside_same_sitemap_without_replaying_duplicates(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "news.sqlite"
    root = "https://www.milenio.com/sitemap/sitemap-articles-index.xml"
    child = "https://www.milenio.com/sitemap/articles/2019-01.xml"
    responses = {
        root: sitemap_index(child),
        child: urlset(
            "https://www.milenio.com/politica/story-one",
            "https://www.milenio.com/politica/story-two",
        ),
    }

    def fake_fetch(url: str, timeout: float, **kwargs: object) -> dict[str, object]:
        return {
            "status": 200,
            "final_url": url,
            "content_type": "application/xml",
            "text": responses[url],
            "error": pd.NA,
        }

    with patch("crawler_core.news_sitemaps.fetch", side_effect=fake_fetch):
        first = discover_news_sitemaps(
            source_ids=["milenio"],
            state_db_path=db_path,
            resume=True,
            max_sitemaps_per_source=None,
            max_urls_per_source=1,
            timeout=1,
            pause_seconds=0,
            request_retries=0,
            retry_backoff_seconds=0,
            workers=1,
        )
        second = discover_news_sitemaps(
            source_ids=["milenio"],
            state_db_path=db_path,
            resume=True,
            max_sitemaps_per_source=None,
            max_urls_per_source=2,
            timeout=1,
            pause_seconds=0,
            request_retries=0,
            retry_backoff_seconds=0,
            workers=1,
        )

    assert first["milenio"]["url_count"] == 1
    assert first["milenio"]["complete"] is False
    assert second["milenio"]["url_count"] == 2
    assert second["milenio"]["complete"] is True


def test_archive_filters_recognize_grupo_reforma_article_ids() -> None:
    article = "https://www.elnorte.com/example-title/ar1234567"
    section = "https://www.elnorte.com/nacional/"
    assert likely_commoncrawl_article_url(article, source_id="elnorte")
    assert likely_wayback_article_url(article, "elnorte")
    assert not likely_commoncrawl_article_url(section, source_id="elnorte")
    assert not likely_wayback_article_url(section, "elnorte")
    opinion = "https://www.reforma.com/example-column-2019-01-01/op123456"
    assert likely_commoncrawl_article_url(opinion, source_id="reforma")
    assert likely_wayback_article_url(opinion, "reforma")
    assert likely_article_url_for_source("reforma", opinion)


def test_grupo_reforma_broad_archive_queries_do_not_fan_out_by_section() -> None:
    source = pd.Series(
        {"source_id": "reforma", "canonical_url": "https://www.reforma.com/"}
    )
    expected = ["www.reforma.com/*"]
    assert commoncrawl_url_patterns(source, include_broad_domain=True) == expected
    assert wayback_url_patterns(source, include_broad_domain=True) == expected


def test_explicit_archive_source_is_loaded_from_registry(tmp_path: Path) -> None:
    registry_path = tmp_path / "sources.csv"
    pd.DataFrame(
        [
            {
                "source_id": "reforma",
                "source_name": "Reforma",
                "canonical_url": "https://www.reforma.com/",
            }
        ]
    ).to_csv(registry_path, index=False)
    sources = augment_sources_from_registry(
        pd.DataFrame(columns=["source_id", "source_name", "canonical_url"]),
        registry_path=registry_path,
        requested_source_ids=["reforma"],
    )
    assert sources["source_id"].tolist() == ["reforma"]


def test_grupo_reforma_premium_body_is_labeled_as_teaser() -> None:
    html = """
    <html lang="es"><head>
      <meta name="cXenseParse:ref-premium" content="true">
      <script type="application/ld+json">
      {"@type":"NewsArticle","headline":"Premium story","datePublished":"2020-01-02T03:04:05Z",
       "articleBody":"This is the public teaser for a subscriber-only article.",
       "author":{"name":"Reporter"}}
      </script>
    </head><body></body></html>
    """
    response = {
        "status": 200,
        "final_url": "https://www.reforma.com/premium-story/ar1234567",
        "content_type": "text/html",
        "text": html,
        "error": pd.NA,
    }
    item = pd.Series(
        {
            "source_id": "reforma",
            "source_name": "Reforma",
            "source_url": "https://www.reforma.com/",
            "url": "https://www.reforma.com/premium-story/ar1234567",
            "canonical_url": "https://www.reforma.com/premium-story/ar1234567",
            "discovery_strategy": "official_sitemap",
        }
    )
    with patch("crawler_core.sitemap_articles.fetch", return_value=response):
        row = extract_one_sitemap_article(item, timeout=1, fetch_profile="browser")
    assert row["access_type"] == "premium"
    assert row["error"] == "subscription_teaser_only"
    assert row["body_character_count"] == len(row["main_text"])

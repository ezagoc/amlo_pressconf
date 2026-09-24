"""Tests for ABC Noticias sitemap discovery and extraction support."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


CRAWLER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CRAWLER_DIR))

from crawler_core.abcnoticias import (  # noqa: E402
    fetch_abc,
    fetch_abc_sitemap,
    is_abc_article_url,
)
from crawler_core.sitemap_articles import article_fields_from_html  # noqa: E402


class AbcNoticiasTests(unittest.TestCase):
    def test_historical_article_url_is_recognized(self) -> None:
        self.assertTrue(
            is_abc_article_url(
                "https://abcnoticias.mx/global/2012/1/31/"
                "entregan-escrituras-ratifican-firmas-541.html"
            )
        )
        self.assertFalse(is_abc_article_url("https://abcnoticias.mx/global"))
        self.assertFalse(
            is_abc_article_url(
                "https://example.com/global/2012/1/31/example-541.html"
            )
        )

    def test_monthly_sitemap_rows_include_date_topic_and_id(self) -> None:
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url>
            <loc>https://abcnoticias.mx/global/2012/1/31/example-title-541.html</loc>
            <lastmod>2026-05-28T20:58:56.085Z</lastmod>
          </url>
          <url><loc>https://abcnoticias.mx/global</loc></url>
        </urlset>"""
        response = {
            "status": 200,
            "final_url": "https://abcnoticias.mx/sitemaps/articles/2012-01.xml",
            "content_type": "application/xml",
            "text": xml,
            "error": pd.NA,
        }
        with patch("crawler_core.abcnoticias.fetch_abc", return_value=response):
            rows = fetch_abc_sitemap(
                "https://abcnoticias.mx/sitemaps/articles/2012-01.xml",
                timeout=1,
                retries=1,
            )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.iloc[0]["date_published"], "2012-01-31")
        self.assertEqual(rows.iloc[0]["topic"], "global")
        self.assertEqual(str(rows.iloc[0]["article_id"]), "541")

    def test_tls_failure_uses_node_fallback(self) -> None:
        failed = {
            "status": 0,
            "final_url": pd.NA,
            "content_type": pd.NA,
            "text": "",
            "error": "curl: schannel AcquireCredentialsHandle failed",
        }
        recovered = {
            "status": 200,
            "final_url": "https://abcnoticias.mx/robots.txt",
            "content_type": "text/plain",
            "text": "Allow: /",
            "error": pd.NA,
        }
        with patch("crawler_core.abcnoticias.fetch", return_value=failed), patch(
            "crawler_core.abcnoticias.fetch_abc_with_node", return_value=recovered
        ) as fallback:
            result = fetch_abc("https://abcnoticias.mx/robots.txt", 1)
        self.assertEqual(result["status"], 200)
        fallback.assert_called_once()

    def test_article_json_ld_extracts_required_fields(self) -> None:
        html = """
        <html><head>
          <script type="application/ld+json">{
            "@type":"NewsArticle",
            "headline":"Example ABC headline",
            "description":"Example summary",
            "datePublished":"2012-01-31T17:07:00-06:00",
            "author":{"@type":"Person","name":"Example Reporter"},
            "articleBody":"First paragraph. Second paragraph with more article text."
          }</script>
        </head><body><article><p>First paragraph.</p><p>Second paragraph with more article text.</p></article></body></html>
        """
        fields = article_fields_from_html(
            html,
            url="https://abcnoticias.mx/global/2012/1/31/example-title-541.html",
            source_id="abcnoticias",
        )
        self.assertEqual(fields["title"], "Example ABC headline")
        self.assertEqual(fields["authors"], "Example Reporter")
        self.assertEqual(fields["date_published"], "2012-01-31T17:07:00-06:00")
        self.assertIn("Second paragraph", fields["main_text"])


if __name__ == "__main__":
    unittest.main()

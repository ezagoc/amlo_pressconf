"""Tests for El Universal daily search discovery."""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse


CRAWLER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CRAWLER_DIR))

from crawler_core.eluniversal import (  # noqa: E402
    DISCOVERY_COLUMNS,
    build_queryly_url,
    error_row,
    finalize_eluniversal_checkpoints,
    is_eluniversal_article_url,
    normalize_eluniversal_url,
    parse_queryly_payload,
    queryly_item_row,
)
from crawler_core.sitemap_articles import (  # noqa: E402
    article_fields_from_html,
    likely_article_url_for_source,
    prepare_sitemap_article_queue,
)
import pandas as pd  # noqa: E402


class ElUniversalTests(unittest.TestCase):
    def test_modern_and_legacy_article_urls_are_kept(self) -> None:
        modern = "https://www.eluniversal.com.mx/nacion/example-article-title/"
        legacy = "https://www.eluniversal.com.mx/articulo/mundo/2016/01/15/example-title/"
        archive = "https://archivo.eluniversal.com.mx/notas/732124.html"
        self.assertTrue(is_eluniversal_article_url(modern))
        self.assertTrue(is_eluniversal_article_url(legacy))
        self.assertTrue(is_eluniversal_article_url(archive))
        self.assertTrue(likely_article_url_for_source("eluniversal", legacy))

    def test_non_article_urls_are_rejected(self) -> None:
        self.assertFalse(is_eluniversal_article_url("https://www.eluniversal.com.mx/buscador/"))
        self.assertFalse(is_eluniversal_article_url("https://www.eluniversal.com.mx/nacion/"))

    def test_relative_result_link_is_normalized(self) -> None:
        self.assertEqual(
            normalize_eluniversal_url("/nacion/example-article-title/?output=1"),
            "https://www.eluniversal.com.mx/nacion/example-article-title/",
        )

    def test_query_uses_wildcard_and_single_day_range(self) -> None:
        url = build_queryly_url(date(2020, 1, 15), offset=100, batch_size=500)
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query["query"], ["*"])
        self.assertEqual(query["daterange"], ["1/15/2020,1/15/2020"])
        self.assertEqual(query["endindex"], ["100"])
        self.assertEqual(query["batchsize"], ["100"])

    def test_jsonp_payload_is_supported(self) -> None:
        payload = parse_queryly_payload('callback({"metadata":{"total":0},"items":[]});')
        self.assertEqual(payload["metadata"]["total"], 0)

    def test_http_error_row_preserves_status_code(self) -> None:
        row = error_row(date(2020, 1, 15), "https://example.test", 1, "http_status_403")
        self.assertEqual(row["status"], 403)

    def test_archive_layout_extracts_article_metadata_and_body(self) -> None:
        html = """
        <html><head><title>El Universal - El Mundo</title></head><body>
        <script>name=eluniversal.mundo.mxm.noticia.example</script>
        <div id="noteContent">
          <h1 id="titleNote">Archive headline</h1>
          <span id="descriptionNote">Archive summary</span>
          <div class="noteText">
            <span class="noteInfo">Martes 21 de diciembre de 2010</span>
            <span id="authorNote" class="noteInfo">AP | El Universal</span>
            <span id="contentNote"><p>First archive paragraph.</p><p>Second paragraph.</p></span>
          </div>
        </div>
        </body></html>
        """
        fields = article_fields_from_html(
            html,
            url="https://archivo.eluniversal.com.mx/notas/732124.html",
            source_id="eluniversal",
        )
        self.assertEqual(fields["title"], "Archive headline")
        self.assertEqual(fields["date_published"], "2010-12-21")
        self.assertEqual(fields["authors"], "AP | El Universal")
        self.assertEqual(fields["topic"], "mundo")
        self.assertIn("Second paragraph", fields["main_text"])

    def test_queryly_item_becomes_discovery_row(self) -> None:
        row = queryly_item_row(
            {
                "link": "/nacion/example-article-title/",
                "pubdate": "Jan 15, 2020",
                "title": "Example",
                "creator": "Reporter",
            },
            date(2020, 1, 15),
            "https://api.queryly.com/example",
            1,
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["date_published"], "2020-01-15")
        self.assertEqual(row["topic"], "nacion")

    def test_finalizer_removes_cross_day_duplicate_urls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkpoints = root / "checkpoints"
            checkpoints.mkdir()
            article_url = "https://www.eluniversal.com.mx/nacion/example-article-title/"
            for day in ("2020-01-15", "2020-01-16"):
                row = {column: "" for column in DISCOVERY_COLUMNS}
                row.update(
                    {
                        "source_id": "eluniversal",
                        "url": article_url,
                        "date_published": day,
                        "topic": "nacion",
                    }
                )
                with (checkpoints / f"{day}.csv").open("w", newline="", encoding="utf-8") as output:
                    writer = csv.DictWriter(output, fieldnames=DISCOVERY_COLUMNS)
                    writer.writeheader()
                    writer.writerow(row)

            outputs, summary = finalize_eluniversal_checkpoints(
                checkpoints,
                root / "discovery",
                root / "reports",
            )

            with outputs.discovered_csv.open(newline="", encoding="utf-8") as source:
                output_rows = list(csv.DictReader(source))
            self.assertEqual(len(output_rows), 1)
            self.assertEqual(summary.urls, 1)
            self.assertEqual(summary.duplicates_skipped, 1)

    def test_extraction_queue_collapses_eluniversal_url_variants(self) -> None:
        base = "https://www.eluniversal.com.mx/nacion/example-article-title"
        discovered = pd.DataFrame(
            [
                {
                    "source_id": "eluniversal",
                    "url": base + "/?outputType=amp",
                    "canonical_url": base + "/?outputType=amp",
                    "discovery_strategy": "commoncrawl",
                    "error": pd.NA,
                },
                {
                    "source_id": "eluniversal",
                    "url": base + "/",
                    "canonical_url": base + "/",
                    "discovery_strategy": "commoncrawl",
                    "error": pd.NA,
                },
                {
                    "source_id": "eluniversal",
                    "url": "http://www.eluniversal.com.mx/nacion/example-article-title",
                    "canonical_url": "http://www.eluniversal.com.mx/nacion/example-article-title",
                    "discovery_strategy": "commoncrawl",
                    "error": pd.NA,
                },
            ]
        )

        queued = prepare_sitemap_article_queue(discovered)

        self.assertEqual(len(queued), 1)
        self.assertEqual(queued.iloc[0]["url"], base + "/")


if __name__ == "__main__":
    unittest.main()

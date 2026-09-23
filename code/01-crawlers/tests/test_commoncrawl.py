"""Regression tests for Common Crawl discovery failures."""

from __future__ import annotations

import contextlib
import gzip
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crawler_core.commoncrawl import (  # noqa: E402
    commoncrawl_url_patterns,
    discover_commoncrawl_query,
    discover_commoncrawl_urls,
    likely_commoncrawl_article_url,
    write_commoncrawl_outputs,
)
from crawler_core.commoncrawl_archive import (  # noqa: E402
    fetch_sdp_archive_query,
    load_sdp_archive_records,
    read_range,
)
from crawler_core.sitemap_articles import likely_article_url_for_source  # noqa: E402

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "discover_commoncrawl_urls.py"
SCRIPT_SPEC = importlib.util.spec_from_file_location("discover_commoncrawl_script", SCRIPT_PATH)
assert SCRIPT_SPEC is not None and SCRIPT_SPEC.loader is not None
SCRIPT_MODULE = importlib.util.module_from_spec(SCRIPT_SPEC)
SCRIPT_SPEC.loader.exec_module(SCRIPT_MODULE)


class CommonCrawlFailureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = pd.Series(
            {"source_id": "sdpnoticias", "canonical_url": "https://www.sdpnoticias.com/"}
        )
        self.failure = {
            "status": pd.NA,
            "text": "",
            "error": "requests_commoncrawl: connection closed",
        }

    def test_missing_status_is_recorded_as_transport_error(self) -> None:
        with patch("crawler_core.commoncrawl.fetch_commoncrawl", return_value=self.failure):
            rows = discover_commoncrawl_query(
                self.source,
                index_id="CC-MAIN-2026-39",
                url_pattern="www.sdpnoticias.com/mexico/*",
                seen_source_urls=set(),
                limit_per_query=10,
                page_size=None,
                timeout=1,
                body_text_limit=1000,
            )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["error"], self.failure["error"])

    def test_repeated_transport_errors_stop_empty_discovery(self) -> None:
        sources = pd.DataFrame([self.source])
        with patch("crawler_core.commoncrawl.fetch_commoncrawl", return_value=self.failure):
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, "connection failed for 3 consecutive queries"):
                    discover_commoncrawl_urls(
                        sources,
                        index_ids=["CC-MAIN-2026-39", "CC-MAIN-2026-34"],
                        path_patterns=["mexico"],
                        pause_seconds=0,
                    )

    def test_broad_sdp_pattern_covers_historical_sections(self) -> None:
        patterns = commoncrawl_url_patterns(self.source, include_broad_domain=True)
        self.assertEqual(
            patterns,
            ["www.sdpnoticias.com/*", "sdpnoticias.com/*"],
        )

    def test_sdp_article_filters_exclude_profile_and_topic_pages(self) -> None:
        for path in ["autor/fabiana-estrada-tena", "coberturas/copa-por-mexico", "page/listado-3-cine.html"]:
            url = f"https://www.sdpnoticias.com/{path}/"
            self.assertFalse(likely_commoncrawl_article_url(url, source_id="sdpnoticias"))
            self.assertFalse(likely_article_url_for_source("sdpnoticias", url))
        article = "https://www.sdpnoticias.com/historico/secretaria-de-marina-tomara-control-de-puertos/"
        self.assertTrue(likely_commoncrawl_article_url(article, source_id="sdpnoticias"))
        self.assertTrue(likely_article_url_for_source("sdpnoticias", article))

    def test_eluniversal_filter_keeps_modern_and_legacy_articles(self) -> None:
        modern = "https://www.eluniversal.com.mx/nacion/example-article-title/"
        legacy = "https://www.eluniversal.com.mx/articulo/mundo/2016/01/15/example-title/"
        section = "https://www.eluniversal.com.mx/nacion/"
        self.assertTrue(likely_commoncrawl_article_url(modern, source_id="eluniversal"))
        self.assertTrue(likely_commoncrawl_article_url(legacy, source_id="eluniversal"))
        self.assertFalse(likely_commoncrawl_article_url(section, source_id="eluniversal"))

    def test_eluniversal_default_patterns_cover_modern_and_legacy_paths(self) -> None:
        source = pd.Series(
            {"source_id": "eluniversal", "canonical_url": "https://www.eluniversal.com.mx/"}
        )
        patterns = commoncrawl_url_patterns(source)
        self.assertIn("www.eluniversal.com.mx/articulo/*", patterns)
        self.assertIn("www.eluniversal.com.mx/nacion/*", patterns)
        self.assertIn("www.eluniversal.com.mx/tendencias/*", patterns)
        self.assertIn("archivo.eluniversal.com.mx/notas/*", patterns)

    def test_indexes_per_year_are_evenly_sampled(self) -> None:
        indexes = [f"CC-MAIN-2025-{week:02d}" for week in (50, 40, 30, 20, 10)]
        self.assertEqual(
            SCRIPT_MODULE.select_indexes_per_year(indexes, 3),
            ["CC-MAIN-2025-50", "CC-MAIN-2025-30", "CC-MAIN-2025-10"],
        )

    def test_archive_query_filters_to_requested_host_and_path(self) -> None:
        records = (
            {"url": "https://www.sdpnoticias.com/nacional/historical-story/"},
            {"url": "https://www.sdpnoticias.com/deportes/another-story/"},
            {"url": "https://sdpnoticias.com/nacional/bare-host-story/"},
        )
        url = "https://index.commoncrawl.org/CC-MAIN-2020-50-index?url=www.sdpnoticias.com%2Fnacional%2F&limit=10"
        with patch("crawler_core.commoncrawl_archive.load_sdp_archive_records", return_value=records):
            response = fetch_sdp_archive_query(url, 1, body_text_limit=1000)
        self.assertEqual(response["status"], 200)
        self.assertIn("historical-story", response["text"])
        self.assertNotIn("another-story", response["text"])
        self.assertNotIn("bare-host-story", response["text"])

    def test_archive_range_retry_uses_alternate_host(self) -> None:
        class Response:
            status_code = 206
            content = b"ok"

            def raise_for_status(self) -> None:
                pass

        session = Mock()
        session.get.side_effect = [requests.exceptions.ChunkedEncodingError("partial"), Response()]
        url = "https://data.commoncrawl.org/cc-index/collections/test/cluster.idx"
        with patch("crawler_core.commoncrawl_archive.time.sleep"):
            self.assertEqual(read_range(session, url, 0, 1, 1), b"ok")
        self.assertIn("ds5q9oxwqwsfj.cloudfront.net", session.get.call_args_list[1].args[0])

    def test_archive_records_keep_capture_timestamp(self) -> None:
        record = {
            "url": "https://www.sdpnoticias.com/nacional/old-story/",
            "mime": "text/html",
            "status": "200",
        }
        line = b"com,sdpnoticias)/nacional/old-story 20201101020304 " + json.dumps(record).encode()
        compressed = gzip.compress(line + b"\n")
        load_sdp_archive_records.cache_clear()
        with patch("crawler_core.commoncrawl_archive.head_content_length", return_value=100):
            with patch(
                "crawler_core.commoncrawl_archive.find_sdp_blocks",
                return_value=[("cdx-00001.gz", 0, len(compressed))],
            ):
                with patch("crawler_core.commoncrawl_archive.read_range", return_value=compressed):
                    records = load_sdp_archive_records("CC-MAIN-2020-50", 1)
        self.assertEqual(records[0]["timestamp"], "20201101020304")
        load_sdp_archive_records.cache_clear()

    def test_output_normalizes_mixed_checkpoint_metadata(self) -> None:
        rows = pd.DataFrame(
            {
                "source_id": ["sdpnoticias", "sdpnoticias"],
                "url": [
                    "https://www.sdpnoticias.com/nacional/one-story/",
                    "https://www.sdpnoticias.com/nacional/two-story/",
                ],
                "commoncrawl_status": [200, "200"],
                "commoncrawl_timestamp": [20201101000000, "20231201000000"],
                "status": [200, 200],
                "error": [pd.NA, pd.NA],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outputs = write_commoncrawl_outputs(rows, "report", root / "data", root / "reports")
            self.assertTrue(outputs.discovered_csv.exists())
            self.assertIsNone(outputs.parquet_error)
            self.assertTrue(outputs.discovered_parquet.exists())

    def test_failed_index_continues_and_retries_without_losing_partial_urls(self) -> None:
        def row(url: object, error: object = pd.NA) -> dict[str, object]:
            return {"source_id": "sdpnoticias", "url": url, "error": error}

        initial = {
            "A": pd.DataFrame([row("https://example.com/a")]),
            "B": pd.DataFrame(
                [row("https://example.com/b-old"), row(pd.NA, "archive_fallback: 503")]
            ),
            "C": pd.DataFrame([row("https://example.com/c")]),
        }
        with tempfile.TemporaryDirectory() as directory:
            checkpoint_dir = Path(directory)
            first_calls = []

            def first_discover(index_ids: list[str]) -> pd.DataFrame:
                first_calls.extend(index_ids)
                return initial[index_ids[0]]

            with contextlib.redirect_stdout(io.StringIO()):
                first, failures = SCRIPT_MODULE.discover_with_index_checkpoints(
                    ["A", "B", "C"], checkpoint_dir, first_discover
                )
            self.assertEqual(first_calls, ["A", "B", "C"])
            self.assertEqual(len(failures), 1)
            self.assertEqual(first["url"].notna().sum(), 3)
            self.assertTrue((checkpoint_dir / "B.partial.csv").exists())

            retry_calls = []

            def retry_discover(index_ids: list[str]) -> pd.DataFrame:
                retry_calls.extend(index_ids)
                return pd.DataFrame([row("https://example.com/b-new")])

            with contextlib.redirect_stdout(io.StringIO()):
                second, failures = SCRIPT_MODULE.discover_with_index_checkpoints(
                    ["A", "B", "C"], checkpoint_dir, retry_discover
                )
            self.assertEqual(retry_calls, ["B"])
            self.assertEqual(failures, [])
            self.assertEqual(second["url"].notna().sum(), 4)
            self.assertTrue((checkpoint_dir / "B.csv").exists())


if __name__ == "__main__":
    unittest.main()

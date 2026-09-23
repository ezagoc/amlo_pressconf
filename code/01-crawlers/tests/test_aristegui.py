"""Tests for Aristegui Noticias sitemap URL normalization."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


CRAWLER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CRAWLER_DIR))

from crawler_core.aristegui import (  # noqa: E402
    is_aristegui_article_url,
    public_article_url,
    sitemap_sort_key,
    successful_checkpoint_sitemaps,
    load_checkpoint,
)
from crawler_core.sitemap_articles import (  # noqa: E402
    infer_aristegui_wayback_date,
    is_transient_fetch_error,
    likely_article_url_for_source,
    prepare_sitemap_article_queue,
)


class AristeguiUrlTests(unittest.TestCase):
    def test_editorial_article_url_is_recognized(self) -> None:
        url = "https://editorial.aristeguinoticias.com/1104/lomasdestacado/example-article/"
        self.assertTrue(is_aristegui_article_url(url))

    def test_media_and_taxonomy_urls_are_rejected(self) -> None:
        self.assertFalse(
            is_aristegui_article_url(
                "https://editorial.aristeguinoticias.com/wp-content/uploads/example.jpg"
            )
        )
        self.assertFalse(
            is_aristegui_article_url("https://editorial.aristeguinoticias.com/category/mexico/")
        )

    def test_backend_url_becomes_public_url(self) -> None:
        backend = "https://editorial.aristeguinoticias.com/2209/mexico/example-article/"
        self.assertEqual(
            public_article_url(backend),
            "https://aristeguinoticias.com/2209/mexico/example-article/",
        )

    def test_post_sitemap_numeric_order(self) -> None:
        urls = [
            "https://editorial.aristeguinoticias.com/post-sitemap10.xml",
            "https://editorial.aristeguinoticias.com/post-sitemap.xml",
            "https://editorial.aristeguinoticias.com/post-sitemap2.xml",
        ]
        self.assertEqual(sorted(urls, key=sitemap_sort_key), [urls[1], urls[2], urls[0]])

    def test_extraction_queue_keeps_nonstandard_aristegui_sections(self) -> None:
        url = "https://aristeguinoticias.com/1104/lomasdestacado/example-article/"
        self.assertTrue(likely_article_url_for_source("aristeguinoticias", url))

    def test_extraction_queue_rejects_polluted_aristegui_suffix(self) -> None:
        url = (
            "https://aristeguinoticias.com/1104/mexico/example-article/"
            "aristeguinoticias.com"
        )
        self.assertFalse(likely_article_url_for_source("aristeguinoticias", url))

    def test_wayback_queue_collapses_host_aliases_and_prefers_larger_capture(self) -> None:
        import pandas as pd

        path = "/1104/mexico/example-article/"
        rows = pd.DataFrame(
            [
                {
                    "source_id": "aristeguinoticias",
                    "url": f"https://web.archive.org/web/20130101id_/http://aristeguinoticias.com:80{path}",
                    "original_url": f"http://aristeguinoticias.com:80{path}",
                    "discovery_strategy": "wayback",
                    "wayback_timestamp": "20130101000000",
                    "wayback_length": 1000,
                    "error": pd.NA,
                },
                {
                    "source_id": "aristeguinoticias",
                    "url": f"https://web.archive.org/web/20140101id_/https://aristeguinoticias.com{path}",
                    "original_url": f"https://aristeguinoticias.com{path}",
                    "discovery_strategy": "wayback",
                    "wayback_timestamp": "20140101000000",
                    "wayback_length": 5000,
                    "error": pd.NA,
                },
            ]
        )
        queue = prepare_sitemap_article_queue(rows)
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue.iloc[0]["wayback_length"], 5000)

    def test_wayback_connection_failure_is_transient(self) -> None:
        self.assertTrue(
            is_transient_fetch_error(
                {"status": 0, "error": "curl: (7) Could not connect to server"}
            )
        )

    def test_missing_article_text_is_not_a_transient_request_failure(self) -> None:
        self.assertFalse(
            is_transient_fetch_error({"status": 200, "error": "missing_main_text"})
        )

    def test_wayback_date_uses_ddmm_path_and_capture_year(self) -> None:
        inferred = infer_aristegui_wayback_date(
            source_id="aristeguinoticias",
            discovery_strategy="wayback",
            original_url="https://aristeguinoticias.com/2308/mexico/example-article/",
            wayback_timestamp="20120828065358",
        )
        self.assertEqual(inferred, "2012-08-23")

    def test_wayback_january_capture_assigns_december_article_to_prior_year(self) -> None:
        inferred = infer_aristegui_wayback_date(
            source_id="aristeguinoticias",
            discovery_strategy="wayback",
            original_url="https://aristeguinoticias.com/3112/mexico/example-article/",
            wayback_timestamp="20130102065358",
        )
        self.assertEqual(inferred, "2012-12-31")

    def test_resume_keeps_confirmed_empty_sitemaps_completed(self) -> None:
        import pandas as pd

        checkpoint = pd.DataFrame(
            [
                {"sitemap_url": "good.xml", "url": "https://example.com/article", "error": pd.NA},
                {"sitemap_url": "empty.xml", "url": pd.NA, "error": "no_article_urls_found"},
            ]
        )
        self.assertEqual(successful_checkpoint_sitemaps(checkpoint), {"good.xml", "empty.xml"})

    def test_resume_retries_network_errors(self) -> None:
        import pandas as pd

        checkpoint = pd.DataFrame(
            [
                {"sitemap_url": "failed.xml", "url": pd.NA, "error": "curl_exit_28"},
            ]
        )
        self.assertEqual(successful_checkpoint_sitemaps(checkpoint), set())

    def test_load_checkpoint_prefers_more_complete_temporary_file(self) -> None:
        import pandas as pd

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.csv"
            pd.DataFrame(
                [{"sitemap_url": "one.xml", "url": "https://example.com/one"}]
            ).to_csv(path, index=False)
            pd.DataFrame(
                [
                    {"sitemap_url": "one.xml", "url": "https://example.com/one"},
                    {"sitemap_url": "two.xml", "url": "https://example.com/two"},
                ]
            ).to_csv(path.with_name("checkpoint.tmp.csv"), index=False)
            loaded = load_checkpoint(path)
            self.assertEqual(len(loaded), 2)


if __name__ == "__main__":
    unittest.main()

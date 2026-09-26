"""Independent regression cases from the offline task-2 boundary review."""
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawler_core.capabilities import fetch
from crawler_core.sitemap_articles import extract_one_sitemap_article
from crawler_core.tiempo_html import tiempo_fields
from test_tiempo_html import page, URL


class ReauditParserTests(unittest.TestCase):
    def extract(self, html, content_type="text/html", final_url=URL, source_id="tiempo"):
        response = {"status": 200, "final_url": final_url, "content_type": content_type, "text": html, "error": None}
        with patch("crawler_core.sitemap_articles.fetch", return_value=response):
            return extract_one_sitemap_article(pd.Series({"source_id": source_id, "url": URL}), timeout=1)

    def test_standard_entrypoint_rejects_non_html_before_parsing(self):
        for content_type in ("application/json", "text/plain", None, pd.NA):
            with self.subTest(content_type=content_type):
                result = self.extract(page(), content_type)
                self.assertEqual(result["error"], "non_html_response")
                self.assertTrue(pd.isna(result["main_text"]))

    def test_standard_entrypoint_resolves_canonical_against_final_url(self):
        html = page().replace(f'href="{URL}"', 'href="../resolved/"')
        result = self.extract(html, final_url="https://www.tiempo.com.mx/local/redirected/")
        self.assertEqual(result["url"], URL)
        self.assertEqual(result["canonical_url"], "https://www.tiempo.com.mx/local/resolved/")
        self.assertTrue(pd.isna(result["error"]))

    def test_graph_and_type_array_dates_participate_in_conflict_check(self):
        for payload in ({"@graph": [{"@type": "NewsArticle", "datePublished": "2023-06-01T12:01:00"}]},
                        {"@type": ["NewsArticle", "Article"], "datePublished": "2023-06-01T12:01:00"}):
            with self.subTest(payload=payload):
                result = tiempo_fields(page(ld=payload), url=URL)
                self.assertEqual(result["source_specific_error"], "conflicting_publication_dates")
                self.assertIsNone(result["date_published"])

    def test_other_article_in_graph_does_not_create_false_conflict(self):
        payload = {"@graph": [
            {"@type": "NewsArticle", "url": "https://www.tiempo.com.mx/local/other/", "datePublished": "2020-01-01"},
            {"@type": ["NewsArticle"], "mainEntityOfPage": {"@id": URL}, "datePublished": "2024-06-01T12:01:23"}]}
        result = tiempo_fields(page(ld=payload), url=URL)
        self.assertIsNone(result["source_specific_error"])
        self.assertEqual(result["date_published"], "2024-06-01T12:01:23")
        self.assertEqual(result["jsonld_article_selection"], "matched_current_url")

    def test_webpage_main_entity_disambiguates_same_page_fragment_ids(self):
        payload = {"@graph": [
            {"@type": "WebPage", "@id": URL, "mainEntity": {"@id": "#main"}},
            {"@type": "NewsArticle", "@id": "#related", "datePublished": "2020-01-01"},
            {"@type": "NewsArticle", "@id": "#main", "datePublished": "2024-06-01T12:01:23"}]}
        result = tiempo_fields(page(ld=payload), url=URL)
        self.assertIsNone(result["source_specific_error"])
        self.assertEqual(result["date_published"], "2024-06-01T12:01:23")

    def test_nested_recommendations_are_not_current_publication_evidence(self):
        payload = {"@type": "NewsArticle", "url": URL, "datePublished": "2024-06-01T12:01:23",
                   "isRelatedTo": {"@type": "NewsArticle", "datePublished": "2020-01-01"}}
        result = tiempo_fields(page(ld=payload), url=URL)
        self.assertIsNone(result["source_specific_error"])
        self.assertEqual(len(json.loads(result["publication_date_evidence"])), 2)

    def test_multiple_unscoped_articles_are_quarantined_not_guessed(self):
        payload = [{"@type": "NewsArticle", "datePublished": "2024-06-01"},
                   {"@type": "NewsArticle", "datePublished": "2020-01-01"}]
        result = tiempo_fields(page(ld=payload), url=URL)
        self.assertEqual(result["source_specific_error"], "ambiguous_jsonld_article")
        self.assertEqual(result["jsonld_article_selection"], "ambiguous_unscoped_articles")

    def test_two_precise_metadata_seconds_disagree_but_minute_byline_does_not(self):
        result = tiempo_fields(page(ld={"@type": "NewsArticle", "datePublished": "2024-06-01T12:01:10"},
                                   meta='<meta property="article:published_time" content="2024-06-01T12:01:55">'), url=URL)
        self.assertEqual(result["source_specific_error"], "conflicting_publication_dates")
        accepted = tiempo_fields(page(ld={"@type": "NewsArticle", "datePublished": "2024-06-01T12:01:55"},
                                     meta='<meta property="article:published_time" content="2024-06-01T12:01">'), url=URL)
        self.assertIsNone(accepted["source_specific_error"])

    def test_meta_seconds_are_kept_when_visible_byline_has_only_minutes(self):
        result = tiempo_fields(page(meta='<meta property="article:published_time" content="2024-06-01T12:01:55">'), url=URL)
        self.assertEqual(result["date_published"], "2024-06-01T12:01:55")
        self.assertEqual(result["publication_date_source"], "article:published_time")

    def test_bare_slug_identifier_does_not_invent_wrong_relative_url(self):
        payload = {"@type": "NewsArticle", "mainEntityOfPage": {"@id": "test-article"},
                   "datePublished": "2024-06-01T12:01:23"}
        result = tiempo_fields(page(ld=payload), url=URL)
        self.assertEqual(result["date_published"], "2024-06-01T12:01:23")
        self.assertEqual(result["jsonld_article_selection"], "single_unscoped_article")

    def test_wrapped_and_direct_text_leads_preserve_prose(self):
        for lead in ('<div><p>Entrada breve.</p></div>', 'Entrada breve. '):
            with self.subTest(lead=lead):
                html = page().replace('<p>Entrada breve.</p>', lead)
                result = tiempo_fields(html, url=URL)
                self.assertEqual(result["summary"], "Entrada breve.")
                self.assertTrue(result["main_text"].startswith("Entrada breve.\n"))
                self.assertNotIn("Por:", result["main_text"])

    def test_no_date_byline_is_not_added_to_prose(self):
        result = tiempo_fields(page(byline='Por: <a class="m-r-sm">María Pérez</a>'), url=URL)
        self.assertEqual(result["summary"], "Entrada breve.")
        self.assertNotIn("Por:", result["main_text"])
        self.assertIsNone(result["date_published"])

    def test_table_and_definition_list_boundaries_do_not_join_words(self):
        body = '<table><tr><th>Ciudad</th><th>Total</th></tr><tr><td>Juárez</td><td>20</td></tr></table><dl><dt>Unidad</dt><dd>Pesos</dd></dl>'
        result = tiempo_fields(page(body=body), url=URL)
        self.assertEqual(result["main_text"], "Entrada breve.\nCiudad\nTotal\nJuárez\n20\nUnidad\nPesos")

    def test_explicit_json_author_list_is_preserved_without_publisher_guess(self):
        payload = {"@type": "NewsArticle", "datePublished": "2024-06-01", "author": [{"@type": "Person", "name": "Ana López"}, {"name": "Luis Pérez"}]}
        result = tiempo_fields(page(byline="", ld=payload), url=URL)
        self.assertEqual(result["authors"], "Ana López; Luis Pérez")
        self.assertEqual(result["author_source"], "jsonld.author")


class ReauditEncodingTests(unittest.TestCase):
    def response(self, body, content_type):
        def fake_run(url, body_path, timeout, **kwargs):
            body_path.write_bytes(body)
            return subprocess.CompletedProcess(["offline-fixture"], 0, f"200\t{URL}\t{content_type}", "")
        with patch("crawler_core.capabilities.run_curl", side_effect=fake_run):
            return fetch(URL, 1)

    def test_declared_html_meta_without_http_charset(self):
        for declaration in ('<meta charset="windows-1252">', '<meta http-equiv="Content-Type" content="text/html; charset=windows-1252">'):
            text = f"<html><head>{declaration}</head><body>México — información</body></html>"
            result = self.response(text.encode("windows-1252"), "text/html")
            self.assertEqual(result["text"], text)
            self.assertEqual(result["body_encoding_source"], "html_meta_charset")
            self.assertTrue(pd.isna(result["error"]))

    def test_xml_declaration_and_bom_without_http_charset(self):
        xml = '<?xml version="1.0" encoding="ISO-8859-1"?><urlset><loc>México</loc></urlset>'
        result = self.response(xml.encode("iso-8859-1"), "application/xml")
        self.assertEqual(result["text"], xml)
        self.assertEqual(result["body_encoding_source"], "xml_declaration")
        text = "<html>México</html>"
        result = self.response(text.encode("utf-16"), "text/html")
        self.assertEqual(result["text"], text)
        self.assertEqual(result["body_encoding_source"], "byte_order_mark")

    def test_comment_and_script_text_are_not_encoding_declarations(self):
        text = '<html><head><!-- <meta charset="windows-1252"> --><script>var x = \'<meta charset="windows-1252">\';</script></head><body>México</body></html>'
        result = self.response(text.encode(), "text/html")
        self.assertEqual(result["text"], text)
        self.assertEqual(result["body_encoding_source"], "default_utf8")

    def test_explicit_http_charset_is_not_silently_overridden(self):
        text = '<html><meta charset="windows-1252"><p>México</p></html>'
        result = self.response(text.encode(), "text/html; charset=utf-8")
        self.assertEqual(result["text"], text)
        self.assertEqual(result["body_encoding_source"], "http_charset")

    def test_unknown_html_declared_charset_is_error_without_guessing(self):
        result = self.response(b'<html><meta charset="not-an-encoding"><p>Text</p></html>', "text/html")
        self.assertEqual(result["text"], "")
        self.assertIn("LookupError", result["error"])


if __name__ == "__main__":
    unittest.main()

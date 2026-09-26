"""Independent offline checks for Tiempo extraction boundaries and routing."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawler_core.sitemap_articles import article_fields_from_html, extract_one_sitemap_article
from crawler_core.tiempo_html import tiempo_fields


URL = "https://www.tiempo.com.mx/local/independent-fixture/"


def fixture(*, byline="Por: <a class='m-r-sm'>Ana López</a> 01 Junio 2024 12:01", meta="", ld=None,
            lead="Un resumen real.", body="<p>Inicio <em>con énfasis</em> y final.</p>"):
    script = "<script type='application/ld+json'>" + json.dumps(ld, ensure_ascii=False) + "</script>" if ld else ""
    return (f"<html lang='es'><head><link rel='canonical' href='{URL}'>{meta}{script}</head><body>"
            "<nav>MENÚ EXTERNO</nav><article id='article-post'><header><h1>La noticia</h1></header>"
            f"<blockquote><p>{lead}</p>{byline}</blockquote><div class='complementos-container'>{body}</div>"
            "<aside>NOTICIA AJENA</aside></article></body></html>")


def extract(html, *, source_id="tiempo", lastmod="2026-09-01"):
    response = {"status": 200, "final_url": URL, "content_type": "text/html", "text": html, "error": None}
    with patch("crawler_core.sitemap_articles.fetch", return_value=response):
        return extract_one_sitemap_article(pd.Series({"source_id": source_id, "url": URL, "lastmod": lastmod}), timeout=1)


class IndependentTiempoHTMLTests(unittest.TestCase):
    def test_date_only_metadata_agrees_with_precise_visible_date(self):
        result = tiempo_fields(fixture(ld={"@type": "NewsArticle", "datePublished": "2024-06-01"}), url=URL)
        self.assertIsNone(result["source_specific_error"])
        self.assertEqual(result["date_published"], "2024-06-01T12:01:00")

    def test_date_only_visible_date_does_not_invent_midnight(self):
        result = tiempo_fields(fixture(byline="Por: Ana López 01 Junio 2024"), url=URL)
        self.assertEqual(result["date_published"], "2024-06-01")

    def test_date_only_metadata_does_not_invent_midnight(self):
        result = tiempo_fields(fixture(byline="", meta="<meta property='article:published_time' content='2024-06-01'>"), url=URL)
        self.assertEqual(result["date_published"], "2024-06-01")

    def test_equivalent_aware_metadata_is_not_a_conflict(self):
        result = tiempo_fields(fixture(byline="", ld={"@type": "NewsArticle", "datePublished": "2024-06-02T00:30:00+02:00"},
                                       meta="<meta property='article:published_time' content='2024-06-01T22:30:00Z'>"), url=URL)
        self.assertIsNone(result["source_specific_error"])
        self.assertEqual(result["date_published"], "2024-06-02T00:30:00+02:00")

    def test_precise_metadata_disagreement_is_quarantined_without_byline(self):
        result = tiempo_fields(fixture(byline="", ld={"@type": "NewsArticle", "datePublished": "2024-06-01T12:01:00"},
                                       meta="<meta property='article:published_time' content='2024-06-01T13:01:00'>"), url=URL)
        self.assertEqual(result["source_specific_error"], "conflicting_publication_dates")
        self.assertIsNone(result["date_published"])

    def test_wrapped_byline_does_not_become_summary_or_prose(self):
        result = tiempo_fields(fixture(byline="<p>Por: <a class='m-r-sm'>Ana López</a> 01 Junio 2024 12:01</p>"), url=URL)
        self.assertEqual(result["summary"], "Un resumen real.")
        self.assertEqual(result["main_text"], "Un resumen real.\nInicio con énfasis y final.")
        self.assertEqual(result["authors"], "Ana López")

    def test_missing_author_is_null_but_true_published_article_succeeds(self):
        result = extract(fixture(byline="", meta="<meta property='article:published_time' content='2024-06-01'>"))
        self.assertTrue(pd.isna(result["authors"]))
        self.assertTrue(pd.isna(result["error"]))

    def test_missing_date_remains_missing_despite_modified_lastmod_and_url(self):
        result = extract(fixture(byline="<a class='m-r-sm'>Ana López</a>",
                                 ld={"@type": "NewsArticle", "dateModified": "2024-06-01T12:01:00"}))
        self.assertEqual(result["error"], "missing_date")
        self.assertTrue(pd.isna(result["date_published"]))
        self.assertTrue(pd.isna(result["date"]))
        self.assertEqual(result["authors"], "Ana López")

    def test_invalid_canonical_cannot_be_success(self):
        html = fixture().replace(f"href='{URL}'", "href='https://example.test/local/copied/'")
        result = extract(html)
        self.assertEqual(result["error"], "invalid_article_canonical")

    def test_source_error_page_wins_even_with_large_poll_text_and_date(self):
        html = fixture(body="<p>" + "Encuesta y resultados. " * 100 + "</p>").replace("La noticia", "Ocurrió un error al procesar la noticia")
        result = extract(html)
        self.assertEqual(result["error"], "soft_error_page")
        self.assertTrue(pd.isna(result["main_text"]))
        self.assertTrue(pd.isna(result["date_published"]))

    def test_missing_tiempo_body_layout_is_not_accepted_as_lead_only(self):
        result = extract(fixture().replace("class='complementos-container'", "class='unknown-layout'"))
        self.assertEqual(result["error"], "unrecognized_tiempo_body")

    def test_empty_summary_and_body_report_missing_text(self):
        result = extract(fixture(lead="", body="<script>not prose</script><div class='ad'>advert</div>"))
        self.assertEqual(result["error"], "missing_main_text")

    def test_literal_newline_json_and_repeated_prose_preserved(self):
        html = fixture(ld={"@type": "NewsArticle", "datePublished": "2024-06-01T12:01:25", "description": "uno\ndos"},
                       body="<p>Texto repetido.</p><p>Texto repetido.</p>").replace("uno\\ndos", "uno\ndos")
        result = tiempo_fields(html, url=URL)
        self.assertEqual(result["date_published"], "2024-06-01T12:01:25")
        self.assertEqual(result["main_text"], "Un resumen real.\nTexto repetido.\nTexto repetido.")

    def test_unknown_layout_does_not_use_full_page_as_body(self):
        result = extract("<html><h1>Generic title</h1><main>" + "Poll and sidebar. " * 100 + "</main></html>")
        self.assertEqual(result["error"], "unrecognized_tiempo_layout")
        self.assertTrue(pd.isna(result["main_text"]))

    def test_non_tiempo_parser_still_uses_generic_json_article(self):
        payload = {"@type": "NewsArticle", "headline": "Generic article", "datePublished": "2020-01-02",
                   "author": {"@type": "Person", "name": "Generic author"}, "articleBody": "Genuine paragraph. " * 40}
        html = "<html><script type='application/ld+json'>" + json.dumps(payload) + "</script><h1>Other heading</h1></html>"
        fields = article_fields_from_html(html, url="https://example.test/article", source_id="independent_generic")
        self.assertEqual(fields["title"], "Generic article")
        self.assertEqual(fields["date_published"], "2020-01-02")
        self.assertEqual(fields["authors"], "Generic author")
        self.assertIn("Genuine paragraph.", fields["main_text"])
        self.assertNotIn("source_specific_error", fields)

    def test_non_tiempo_entrypoint_retains_existing_lastmod_fallback(self):
        html = "<html><h1>Other newspaper</h1><article><p>" + "A genuine body paragraph. " * 40 + "</p></article></html>"
        fields = extract(html, source_id="independent_generic", lastmod="2020-01-02")
        self.assertEqual(fields["date_published"], "2020-01-02")
        self.assertTrue(pd.isna(fields["error"]))


if __name__ == "__main__":
    unittest.main()

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawler_core.tiempo_html import tiempo_fields
from crawler_core.sitemap_articles import extract_one_sitemap_article

URL = 'https://www.tiempo.com.mx/cultura/test-article/'


def page(byline='Por: <a class="m-r-sm">María Pérez</a> 01 Junio 2024 12:01', meta='', ld=None, body='<p>Primera <strong>frase</strong> completa.</p><ul><li>Uno</li><li>Dos</li></ul>'):
    script = '<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False) + '</script>' if ld else ''
    return f'''<html lang="es"><head><link rel="canonical" href="{URL}">{meta}{script}</head>
    <body><article id="article-post"><header><h1>Título real</h1><ol class="breadcrumb"><li class="active"><a>Cultura</a></li></ol></header>
    <blockquote><p>Entrada breve.</p>{byline}</blockquote>
    <div class="complementos-container">{body}<div class="ad">PUBLICIDAD</div></div>
    <footer>Las Más Leídas. Basura ajena.</footer></article></body></html>'''


class TiempoHTMLTests(unittest.TestCase):
    def test_complete_prose_no_byline_or_menu(self):
        f = tiempo_fields(page(), url=URL)
        self.assertEqual(f['main_text'], 'Entrada breve.\nPrimera frase completa.\nUno\nDos')
        self.assertEqual(f['summary'], 'Entrada breve.')
        self.assertEqual(f['authors'], 'María Pérez')
        self.assertEqual(f['date_published'], '2024-06-01T12:01:00')

    def test_modified_and_url_dates_never_become_published(self):
        f = tiempo_fields(page(byline='', meta='<meta property="article:modified_time" content="2025-01-01T10:00:00">'), url=URL + '2023-06-01')
        self.assertIsNone(f['date_published'])
        self.assertIsNone(f['date'])
        self.assertIsNone(f['authors'])
        self.assertEqual(f['date_modified'], '2025-01-01T10:00:00')

    def test_published_meta_not_modified_in_dom_order(self):
        f = tiempo_fields(page(byline='', meta='<meta property="article:modified_time" content="2025-01-01"><meta property="og:article:published_time" content="2024-06-01T12:01:33">'), url=URL)
        self.assertEqual(f['date_published'], '2024-06-01T12:01:33')

    def test_conflict_quarantined(self):
        f = tiempo_fields(page(ld={'@type':'NewsArticle','datePublished':'2024-06-02T12:01:00'}), url=URL)
        self.assertIsNone(f['date_published'])
        self.assertEqual(f['source_specific_error'], 'conflicting_publication_dates')

    def test_literal_json_newline_supported(self):
        html = page(ld={'@type':'NewsArticle','datePublished':'2024-06-01T12:01:33','description':'first\nsecond'}).replace('first\\nsecond', 'first\nsecond')
        self.assertEqual(tiempo_fields(html,url=URL)['publication_date_source'], 'jsonld.datePublished')

    def test_short_video_news_kept_without_fabricated_transcript(self):
        f = tiempo_fields(page(body='<iframe src="https://example.test/video"></iframe>'),url=URL)
        self.assertEqual(f['main_text'],'Entrada breve.')
        self.assertEqual(json.loads(f['media_embeds']),['https://example.test/video'])

    def test_author_missing_is_not_publisher(self):
        f = tiempo_fields(page(byline='', meta='<meta name="author" content="Tiempo Publisher">'),url=URL)
        self.assertIsNone(f['authors'])

    def test_social_embed_without_iframe_is_recorded(self):
        f = tiempo_fields(page(body='<blockquote class="tiktok-embed" cite="https://www.tiktok.com/@example/video/123">Visible video caption</blockquote><blockquote class="twitter-tweet"><a href="https://x.com/example/status/456">Date</a></blockquote>'),url=URL)
        self.assertEqual(json.loads(f['media_embeds']), ['https://www.tiktok.com/@example/video/123','https://x.com/example/status/456'])
        self.assertIn('Visible video caption',f['main_text'])

    def test_soft_200_page_has_no_fake_article(self):
        f = tiempo_fields(page().replace('Título real','Ocurrió un error al procesar la noticia'),url=URL)
        self.assertEqual(f['source_specific_error'],'soft_error_page')
        self.assertIsNone(f['main_text'])
        self.assertIsNone(f['canonical_url'])

    def test_calendar_date_invalid(self):
        f = tiempo_fields(page(byline='Por: Redacción 31 Febrero 2024 12:00'),url=URL)
        self.assertIsNone(f['date_published'])
        self.assertEqual(f['source_specific_error'],'invalid_publication_date')

    def test_repeated_actual_paragraph_retained(self):
        f = tiempo_fields(page(body='<p>Refrán.</p><p>Refrán.</p>'),url=URL)
        self.assertEqual(f['main_text'].count('Refrán.'),2)

    def test_existing_entrypoint_does_not_fallback_lastmod(self):
        response={'text':page(byline=''), 'status':200,'final_url':URL,'content_type':'text/html','error':None}
        with patch('crawler_core.sitemap_articles.fetch',return_value=response):
            f=extract_one_sitemap_article(pd.Series({'source_id':'tiempo','url':URL,'lastmod':'2025-01-01'}),timeout=1)
        self.assertEqual(f['error'],'missing_date')
        self.assertTrue(pd.isna(f['date_published']))
        self.assertTrue(pd.isna(f['date']))

    def test_partial_http200_is_transport_error(self):
        response={'text':page(),'status':200,'final_url':URL,'content_type':'text/html','error':'curl: timeout'}
        with patch('crawler_core.sitemap_articles.fetch',return_value=response):
            f=extract_one_sitemap_article(pd.Series({'source_id':'tiempo','url':URL}),timeout=1)
        self.assertEqual(f['error'],'curl: timeout')
        self.assertTrue(pd.isna(f['main_text']))


if __name__ == '__main__':
    unittest.main()

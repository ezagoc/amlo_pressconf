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

    def test_instagram_ui_removed_caption_and_link_retained(self):
        link = 'https://www.instagram.com/p/ABC123/?utm_source=ig_embed'
        embed = f'''<blockquote class="instagram-media" data-instgrm-permalink="{link}">
        <div style="padding-top: 8px"><div style="color: #3897f0; font-family: Arial,sans-serif">Ver esta publicación en Instagram</div></div>
        <p>Texto real de la publicación.</p><p>El autor dijo “Ver esta publicación en Instagram”.</p>
        <p style="color: #c9c8cd; text-overflow: ellipsis"><a href="{link}">Una publicación compartida por alguien (@persona)</a></p></blockquote>'''
        f = tiempo_fields(page(body='<p>Noticia antes.</p>' + embed + '<p>Noticia después.</p>'), url=URL)
        self.assertEqual(f['main_text'], 'Entrada breve.\nNoticia antes.\nTexto real de la publicación.\nEl autor dijo “Ver esta publicación en Instagram”.\nNoticia después.')
        self.assertEqual(json.loads(f['media_embeds']), [link])
        self.assertEqual([row['reason'] for row in json.loads(f['removed_body_elements'])], ['instagram_view_post_ui', 'instagram_shared_post_ui'])

    def test_instagram_words_outside_template_not_removed(self):
        text = '<p>Ver esta publicación en Instagram</p><p>Una publicación compartida por alguien (@persona)</p>'
        for body in [text, '<blockquote class="instagram-media" data-instgrm-permalink="https://www.instagram.com/p/ABC/">' + text + '</blockquote>']:
            with self.subTest(body=body):
                f = tiempo_fields(page(body=body), url=URL)
                self.assertIn('Ver esta publicación en Instagram', f['main_text'])
                self.assertIn('Una publicación compartida por alguien (@persona)', f['main_text'])
                self.assertEqual(json.loads(f['removed_body_elements']), [])

    def test_terminal_recommendation_removed_with_audit_video_kept(self):
        rec = '<p><strong><a href="https://puentelibre.mx/noticia/example/">Podría interesarte: Otra nota</a></strong></p>'
        f = tiempo_fields(page(body='<p>Texto real.</p>' + rec + '<p><iframe src="https://example.test/video"></iframe></p>'), url=URL)
        self.assertEqual(f['main_text'], 'Entrada breve.\nTexto real.')
        self.assertEqual(json.loads(f['related_links']), [{'url': 'https://puentelibre.mx/noticia/example/', 'text': 'Podría interesarte: Otra nota'}])
        self.assertEqual(json.loads(f['media_embeds']), ['https://example.test/video'])

    def test_recommendation_words_with_body_or_middle_link_retained(self):
        cases = ['<p>El reportero dijo: Podría interesarte: esta historia.</p>',
                 '<p>Texto importante <a href="https://example.test">Podría interesarte: noticia</a></p>',
                 '<p><a href="https://example.test">Podría interesarte: noticia</a></p><p>Más noticia real.</p>',
                 '<p><a href="https://example.test">Referencia del artículo</a></p>']
        for body in cases:
            with self.subTest(body=body):
                f = tiempo_fields(page(body=body), url=URL)
                self.assertEqual(json.loads(f['removed_body_elements']), [])

    def test_malformed_nested_recommendation_does_not_remove_parent_body(self):
        f = tiempo_fields(page(body='<p>Texto real previo.<p><strong><a href="https://example.test">Podría interesarte: noticia</a></strong></p></p>'), url=URL)
        self.assertIn('Texto real previo.', f['main_text'])
        self.assertNotIn('Podría interesarte', f['main_text'])

    def test_confirmed_source_empty_requires_narrow_evidence(self):
        html = page(meta='<title> </title><meta name="title" content="/"><meta property="og:title" content=""><meta name="twitter:title" content="">', ld={'@type': 'NewsArticle', 'headline': ' '}).replace('<h1>Título real</h1>', '<h1> </h1>')
        f = tiempo_fields(html, url=URL)
        self.assertIsNone(f['title'])
        self.assertIsNone(f['source_specific_error'])
        self.assertEqual(f['source_title_status'], 'confirmed_source_empty')
        evidence = json.loads(f['source_title_evidence'])
        self.assertTrue(evidence['recognized_empty_h1'])
        self.assertTrue(evidence['all_title_channels_empty'])
        self.assertTrue(any(row['status'] == 'observed_meta_title_placeholder' for row in evidence['channels']))
        response = {'text': html, 'status': 200, 'final_url': URL, 'content_type': 'text/html', 'error': None}
        with patch('crawler_core.sitemap_articles.fetch', return_value=response):
            row = extract_one_sitemap_article(pd.Series({'source_id': 'tiempo', 'url': URL}), timeout=1)
        self.assertEqual(row['error'], 'missing_title')

    def test_any_current_title_channel_information_blocks_source_empty(self):
        for meta, ld in [('<title>Actual title</title>', None), ('<meta name="title" content="Actual">', None),
                         ('<meta property="og:title" content="Actual">', None), ('<meta name="twitter:title" content="Actual">', None),
                         ('', {'@type': 'NewsArticle', 'headline': 'Actual'}), ('', {'@type': 'NewsArticle', 'name': 'Actual'}),
                         ('<meta property="og:title" content="/"></meta>', None),
                         ('<meta name="title" content="/"><meta name="title" content="Actual">', None)]:
            with self.subTest(meta=meta, ld=ld):
                f = tiempo_fields(page(meta=meta, ld=ld).replace('<h1>Título real</h1>', '<h1> </h1>'), url=URL)
                self.assertNotEqual(f['source_title_status'], 'confirmed_source_empty')
                self.assertFalse(json.loads(f['source_title_evidence'])['all_title_channels_empty'])

    def test_new_heading_layout_or_nonempty_h1_never_confirmed_empty(self):
        for heading in ['', '<h2>Different layout</h2>', '<h1> </h1><h2>Other heading</h2>', '<h1>/</h1>',
                        '<h1> </h1><span itemprop="headline" content="Actual"></span>', '<h1> </h1><span data-headline="Actual"></span>']:
            with self.subTest(heading=heading):
                f = tiempo_fields(page().replace('<h1>Título real</h1>', heading), url=URL)
                self.assertNotEqual(f['source_title_status'], 'confirmed_source_empty')

    def test_missing_title_other_errors_and_unparseable_ld_not_confirmed(self):
        empty = page().replace('<h1>Título real</h1>', '<h1> </h1>')
        cases = [empty.replace('class="complementos-container"', 'class="unknown"'),
                 empty.replace(f'<link rel="canonical" href="{URL}">', ''),
                 empty.replace('01 Junio 2024', '31 Febrero 2024'),
                 empty.replace('</head>', '<script type="application/ld+json">{bad</script></head>'),
                 empty.replace('01 Junio 2024 12:01', '')]
        for html in cases:
            with self.subTest(html=html):
                self.assertNotEqual(tiempo_fields(html, url=URL)['source_title_status'], 'confirmed_source_empty')

    def test_other_article_headline_not_used_to_mask_current_source_empty(self):
        ld = [{'@type': 'NewsArticle', 'url': URL, 'headline': ''},
              {'@type': 'NewsArticle', 'url': 'https://www.tiempo.com.mx/local/other/', 'headline': 'Related headline'}]
        f = tiempo_fields(page(ld=ld).replace('<h1>Título real</h1>', '<h1> </h1>'), url=URL)
        self.assertEqual(f['source_title_status'], 'confirmed_source_empty')
        self.assertNotIn('Related headline', f['source_title_evidence'])

    def test_alternative_headline_blocks_source_empty_without_filling_title(self):
        f = tiempo_fields(page(ld={'@type': 'NewsArticle', 'headline': '', 'alternativeHeadline': 'Another real title'}).replace('<h1>Título real</h1>', '<h1> </h1>'), url=URL)
        self.assertIsNone(f['title'])
        self.assertEqual(f['source_title_status'], 'unconfirmed_missing')
        self.assertFalse(json.loads(f['source_title_evidence'])['all_title_channels_empty'])


if __name__ == '__main__':
    unittest.main()

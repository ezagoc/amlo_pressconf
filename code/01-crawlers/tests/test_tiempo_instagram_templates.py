"""Narrow Instagram UI removal; preserve unsupported shapes and real captions."""
import json
import unittest
from crawler_core import tiempo_html as CANDIDATE

URL = 'https://www.tiempo.com.mx/espectaculos/prueba/'
POST = 'https://www.instagram.com/p/BvhS1asDWU0/?utm_source=ig_embed&utm_medium=loading'
STYLE = 'color: #c9c8cd; font-family: Arial,sans-serif; font-size: 14px; line-height: 17px; text-overflow: ellipsis; white-space: nowrap;'
TIME = '<time datetime="2019-03-27T17:31:17+00:00">27 Mar, 2019 a las 10:31 PDT</time>'


def footer(profile=False, word='de', post=POST):
    if profile:
        inside = f'Una publicación compartida {word} <a href="https://www.instagram.com/juanpgil/?utm_source=ig_embed">Juan Pablo Gil</a> (@juanpgil) el {TIME}'
    else:
        inside = f'<a href="{post}">Una publicación compartida {word} Juan Pablo Gil (@juanpgil)</a> el {TIME}'
    return f'<p style="{STYLE}">{inside}</p>'


def article(body):
    return f'''<html><head><link rel="canonical" href="{URL}"></head><body>
    <article id="article-post"><header><h1>Título</h1></header>
    <blockquote><p>Entrada.</p>Por: <a class="m-r-sm">Redacción</a> 31 Marzo 2019 10:28</blockquote>
    <div class="complementos-container">{body}</div></article></body></html>'''


def embed(content, post=POST):
    return f'<blockquote class="instagram-media" data-instgrm-permalink="{post}">{content}</blockquote>'


class TimedFooterTests(unittest.TestCase):
    def test_exact_link_and_profile_variants_por_de(self):
        for profile in [False, True]:
            for word in ['por', 'de']:
                with self.subTest(profile=profile, word=word):
                    f = CANDIDATE.tiempo_fields(article('<p>Antes.</p>'+embed('<p>Caption real.</p>'+footer(profile, word))+'<p>Después.</p>'), url=URL)
                    self.assertEqual(f['main_text'], 'Entrada.\nAntes.\nCaption real.\nDespués.')
                    self.assertEqual(json.loads(f['media_embeds']), [POST])
                    self.assertEqual(json.loads(f['removed_body_elements'])[0]['reason'], 'instagram_timed_shared_post_ui')
                    self.assertIn('27 Mar, 2019', json.loads(f['removed_body_elements'])[0]['text'])
                    self.assertEqual(f['date_published'], '2019-03-31T10:28:00')

    def test_observed_de_mar_and_tv_permalink(self):
        tv = 'https://www.instagram.com/tv/BvmRJGhHnJu/?utm_source=ig_embed&utm_medium=loading'
        p = footer(True, 'por').replace('Juan Pablo Gil', 'Un Nuevo Día').replace('juanpgil', 'unnuevodia').replace('27 Mar, 2019 a las 10:31 PDT', '29 de Mar de 2019 a las 8:54 PDT').replace('2019-03-27T17:31:17+00:00', '2019-03-29T15:54:50+00:00')
        f = CANDIDATE.tiempo_fields(article(embed('<p>Entrevista real.</p>'+p, tv)), url=URL)
        self.assertEqual(f['main_text'], 'Entrada.\nEntrevista real.')
        self.assertEqual(json.loads(f['media_embeds']), [tv])

    def test_news_links_and_caption_wording_are_preserved(self):
        wording = 'Una publicación compartida de Juan Pablo Gil (@juanpgil) el 27 Mar, 2019 a las 10:31 PDT'
        prose = '<p>El reportero cita <a href="https://example.test">una fuente</a> y explica.</p>'
        caption = f'<p style="color:#000;word-wrap:break-word"><a href="{POST}">{wording}</a></p>'
        f = CANDIDATE.tiempo_fields(article(prose+embed(caption+footer())+prose), url=URL)
        self.assertEqual(f['main_text'].count('El reportero cita'), 2)
        self.assertIn(wording, f['main_text'])
        self.assertEqual(len(json.loads(f['removed_body_elements'])), 1)

    def test_non_template_and_unrecognized_shapes_remain(self):
        original = footer(True)
        cases = {
            'outside_embed': original,
            'no_permalink': '<blockquote class="instagram-media">'+original+'</blockquote>',
            'wrong_embed_host': embed(original, 'https://example.test/p/ABC/'),
            'no_style': embed(original.replace(STYLE, '')),
            'black_caption': embed(original.replace('#c9c8cd', '#000')),
            'wrong_color_suffix': embed(original.replace('#c9c8cd', '#c9c8cd00')),
            'no_ellipsis': embed(original.replace('text-overflow: ellipsis;', '')),
            'no_nowrap': embed(original.replace('white-space: nowrap;', '')),
            'different_profile': embed(original.replace('/juanpgil/', '/another/')),
            'profile_external_host': embed(original.replace('www.instagram.com/juanpgil', 'www.example.test/juanpgil')),
            'profile_path_is_post': embed(original.replace('/juanpgil/', '/p/juanpgil/')),
            'different_post': embed(footer(False, post='https://www.instagram.com/p/OTHER/')),
            'extra_news_before': embed(original.replace('Una publicación', 'La noticia analiza: Una publicación')),
            'extra_news_after': embed(original.replace('</time>', '</time> y confirmó la noticia.')),
            'extra_link': embed(original.replace('</p>', '<a href="https://example.test">Cita</a></p>')),
            'nested_time': embed(original.replace(TIME, '<span>'+TIME+'</span>')),
            'no_time': embed(original.replace(TIME, '27 Mar, 2019 a las 10:31 PDT')),
            'invalid_iso': embed(original.replace('2019-03-27T17:31:17+00:00', '2019-02-30T17:31:17+00:00')),
            'missing_timezone': embed(original.replace('2019-03-27T17:31:17+00:00', '2019-03-27T17:31:17')),
            'invalid_visible_date': embed(original.replace('27 Mar,', '32 Mar,')),
            'unknown_visible_month': embed(original.replace('27 Mar,', '27 Nope,')),
            'unrecognized_display': embed(original.replace('27 Mar, 2019 a las 10:31 PDT', 'Yesterday in the news')),
            'nested_news': embed(original.replace('</p>', '<span>News continues.</span></p>')),
        }
        for name, body in cases.items():
            with self.subTest(name=name):
                f = CANDIDATE.tiempo_fields(article(body), url=URL)
                self.assertIn('Una publicación', f['main_text'])
                self.assertEqual(json.loads(f['removed_body_elements']), [])

    def test_malformed_paragraph_repair_keeps_following_news(self):
        body = embed(footer(True).replace('</p>', '<div>News continues.</div></p>'))
        f = CANDIDATE.tiempo_fields(article(body), url=URL)
        self.assertEqual(f['main_text'], 'Entrada.\nNews continues.')
        self.assertEqual(len(json.loads(f['removed_body_elements'])), 1)


if __name__ == "__main__":
    unittest.main()

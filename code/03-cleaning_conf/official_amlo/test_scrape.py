import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from bs4 import BeautifulSoup
from scrape import archive_page, blocks, dates_in_title, parse_page


class ParserTests(unittest.TestCase):
    def test_archive_accepts_both_date_attributes_and_caches(self):
        for attribute in ('date', 'datetime'):
            text = (f'<article><time {attribute}="2018-12-03 07:00:00">Fecha</time>'
                    '<h2>Conferencia de prensa del presidente</h2>'
                    '<a href="/amlo/prensa/ejemplo?idiom=es">Leer</a></article>'
                    '<a href="?page=215">215</a>')
            response = SimpleNamespace(content=text.encode(), text=text, url='https://www.gob.mx/amlo/archivo/prensa?page=2')
            with TemporaryDirectory() as tmp, patch('scrape.fetch', return_value=response) as fetch, patch('scrape.time.sleep'):
                entries, last = archive_page(Path(tmp), 'prensa', 2)
                self.assertEqual(entries[0]['published_date'], '2018-12-03')
                self.assertEqual(last, 215)
                self.assertEqual(archive_page(Path(tmp), 'prensa', 2)[0], entries)
                self.assertEqual(fetch.call_count, 1)

    def test_inline_fragments_and_multiple_speakers_are_preserved(self):
        filler = 'Palabra de contexto. ' * 40
        page = ('<h1>Conferencia de prensa 3 de diciembre 2018</h1><div class="article-body">'
                '<p><strong>-PRESIDENTE ANDRÉS MANUEL LÓPEZ OBRADOR:</strong> Hola.</p>'
                '<p>PREGUNTA: Soy Ana, de Ca<em>nal</em> 11.<br>PRESIDENTE: Gracias.</p>'
                f'<p>{filler}</p></div>').encode()
        rows, audit = parse_page(page, {'published_date': '2018-12-03'},
                                 {'url': 'test', 'raw_path': 'test', 'sha256': 'test'})
        self.assertEqual(rows[1]['text'], 'Soy Ana, de Canal 11.')
        self.assertEqual(rows[2]['participant'], 'PRESIDENTE')
        self.assertEqual(rows[-1]['text'], filler.strip())
        self.assertEqual(audit['date_basis'], 'title')

    def test_early_date_formats_and_date_mismatch_flag(self):
        self.assertEqual(dates_in_title('17 de diciembre, 2018'), ['2018-12-17'])
        self.assertEqual(dates_in_title('3 de diciembre 2018'), ['2018-12-03'])
        page = ('<h1>Conferencia de prensa 3 de diciembre de 2018</h1>'
                '<div class="article-body"><p>Documento previo</p>'
                '<p>PRESIDENTE: Hola.</p><p>PREGUNTA: Buenos días.</p><p>'
                + 'Contexto. ' * 110 + '</p></div>').encode()
        rows, audit = parse_page(page, {'published_date': '2018-12-04'},
                                 {'url': 'test', 'raw_path': 'test', 'sha256': 'test'})
        self.assertTrue(audit['publication_date_differs'])
        self.assertEqual(rows[0]['row_kind'], 'unlabeled_opening')
        self.assertEqual(rows[0]['text'], 'Documento previo')

    def test_loose_text_and_nested_lists_are_not_dropped_or_duplicated(self):
        body = BeautifulSoup('<div class="article-body">Suelto<p>Uno <b>dos</b>.</p>'
                             '<ul><li>Tres<p>Cuatro</p>Cinco</li></ul></div>', 'html.parser').div
        self.assertEqual(blocks(body), ['Suelto', 'Uno dos.', 'Tres', 'Cuatro', 'Cinco'])


if __name__ == '__main__': unittest.main()

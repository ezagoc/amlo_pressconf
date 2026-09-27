import json
import sqlite3
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crawler_core.tiempo_discovery import freeze, parse_index, parse_urlset, run_discovery, summary

INDEX='<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{}</sitemapindex>'
CHILD='https://www.tiempo.com.mx/sitemaps/sitemap_500.xml'
BODY='''<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9"><url><loc>https://www.tiempo.com.mx/noticia/test/</loc><lastmod>2026-01-01</lastmod><news:news><news:publication_date>2024-05-28T09:00:00</news:publication_date><news:title>Test &amp; Title</news:title></news:news></url></urlset>'''

class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(); self.root=Path(self.t.name); self.run=self.root/'run'
        self.index=self.root/'index.xml';self.index.write_text(INDEX.format(f'<sitemap><loc>{CHILD}</loc></sitemap>'))
    def tearDown(self):self.t.cleanup()
    def test_news_date_separate_from_lastmod(self):
        row=parse_urlset(BODY)[0]
        self.assertEqual(row['discovery_day'],'2024-05-28');self.assertEqual(row['sitemap_lastmod'],'2026-01-01')
        self.assertEqual(row['discovery_title'],'Test & Title')
    def test_unrecognized_url_and_missing_news_date_retained(self):
        b=BODY.replace('https://www.tiempo.com.mx/noticia/test/','https://other.example/a/b/').replace('<news:publication_date>2024-05-28T09:00:00</news:publication_date>','')
        row=parse_urlset(b)[0];self.assertIsNone(row['discovery_day']);self.assertFalse(row['candidate_article'])
        self.assertEqual(len(parse_urlset(b)),1)
    def test_index_rejects_external_and_html(self):
        for body in ('<html/>',INDEX.format('<sitemap><loc>https://elsewhere/sitemap_1.xml</loc></sitemap>')):
            with self.assertRaises(ValueError):parse_index(body)
    def test_legacy_http_index_preserved(self):
        body=INDEX.format('<sitemap><loc>http://tiempo.com.mx/sitemaps/sitemap_1.xml</loc></sitemap>')
        self.assertEqual(parse_index(body),['http://tiempo.com.mx/sitemaps/sitemap_1.xml'])
    def test_invalid_full_time_not_silently_truncated(self):
        for value in ('2024-05-28garbage','2024-05-28T99:00:00'):
            row=parse_urlset(BODY.replace('2024-05-28T09:00:00',value))[0]
            self.assertIsNone(row['discovery_day']);self.assertEqual(row['discovery_issue'],'invalid_news_publication_date')
    def test_number_identity_corruption_blocks_before_fetch(self):
        freeze(self.index,self.run)
        with sqlite3.connect(self.run/'discovery.sqlite') as c:c.execute('UPDATE maps SET number=2')
        with self.assertRaises(ValueError):run_discovery(self.run,fetcher=lambda *a:self.fail('must reject mismatched map'),min_free_bytes=0)
    @patch('crawler_core.tiempo_discovery.time.sleep')
    def test_same_count_entry_corruption_blocks(self,_):
        freeze(self.index,self.run)
        run_discovery(self.run,fetcher=lambda *a:{'status':200,'error':None,'text':BODY},min_free_bytes=0)
        with sqlite3.connect(self.run/'discovery.sqlite') as c:c.execute("UPDATE entries SET discovery_day='1999-01-01'")
        with self.assertRaises(ValueError):run_discovery(self.run,fetcher=lambda *a:self.fail('corrupt entry'),min_free_bytes=0)
    @patch('crawler_core.tiempo_discovery.time.sleep')
    def test_resume_no_fetch_and_frozen_evidence(self,_):
        freeze(self.index,self.run)
        response={'status':200,'error':None,'text':BODY}
        result=run_discovery(self.run,fetcher=lambda *a:response,min_free_bytes=0)
        self.assertEqual(result['unique_urls'],1)
        run_discovery(self.run,fetcher=lambda *a:self.fail('duplicate fetch'),min_free_bytes=0)
        with sqlite3.connect(self.run/'discovery.sqlite') as c:self.assertEqual(c.execute('select count(*) from attempts').fetchone()[0],1)
        (self.run/'index.xml').write_text('<html/>')
        with self.assertRaises(ValueError):run_discovery(self.run,fetcher=lambda *a:self.fail('fetch after corrupt index'),min_free_bytes=0)
    @patch('crawler_core.tiempo_discovery.time.sleep')
    def test_failed_response_retained_then_explicit_retry(self,_):
        freeze(self.index,self.run)
        r=run_discovery(self.run,fetcher=lambda *a:{'status':503,'error':None,'text':'temporary'},min_free_bytes=0)
        self.assertEqual(r['map_states'],{'failed':1});self.assertFalse(r['index_entrances_processed'])
        run_discovery(self.run,fetcher=lambda *a:self.fail('unrequested retry'),min_free_bytes=0)
        r=run_discovery(self.run,fetcher=lambda *a:{'status':200,'error':None,'text':BODY},retry_failed=True,min_free_bytes=0)
        self.assertEqual(r['map_states'],{'complete':1})
        self.assertEqual(len(list((self.run/'snapshots').glob('*.xml'))),2)
    @patch('crawler_core.tiempo_discovery.time.sleep')
    def test_complete_snapshot_survives_uncommitted_parse(self,_):
        freeze(self.index,self.run)
        with patch('crawler_core.tiempo_discovery.parse_urlset',side_effect=RuntimeError('simulated abrupt stop')):
            with self.assertRaises(RuntimeError):run_discovery(self.run,fetcher=lambda *a:{'status':200,'error':None,'text':BODY},min_free_bytes=0)
        result=run_discovery(self.run,fetcher=lambda *a:self.fail('should recover complete saved response'),min_free_bytes=0)
        self.assertTrue(result['index_entrances_processed'])

    def test_literal_title_controls_repaired_and_valid_rows_unchanged(self):
        normal_item = BODY[BODY.index('<url>'):BODY.index('</url>') + len('</url>')]
        dirty_item = normal_item.replace('/noticia/test/', '/noticia/dirty/').replace('Test &amp; Title', '\x10Test &amp;\x08 Title\x10')
        mixed = BODY.replace(normal_item, normal_item + dirty_item + normal_item.replace('/noticia/test/', '/noticia/third/'))
        before = mixed.encode('utf-8')
        rows = parse_urlset(mixed)
        expected_first = parse_urlset(BODY)[0]
        self.assertEqual(rows[0], expected_first)
        expected_third = parse_urlset(BODY.replace('/noticia/test/', '/noticia/third/'))[0]
        expected_third['ordinal'] = 2
        self.assertEqual(rows[2], expected_third)
        self.assertEqual(rows[1]['discovery_title'], 'Test & Title')
        self.assertTrue(rows[1]['candidate_article'])
        self.assertEqual(rows[1]['discovery_day'], '2024-05-28')
        self.assertEqual(rows[1]['discovery_issue'], 'illegal_xml_controls_removed_from_news_title:U+0008=1,U+0010=2')
        self.assertEqual(mixed.encode('utf-8'), before)

    def test_title_cdata_and_namespace_alias_are_strictly_supported(self):
        body = BODY.replace('news:', 'n:').replace('xmlns:news', 'xmlns:n')
        body = body.replace('Test &amp; Title', '<![CDATA[\x00News & Title\x1f]]>')
        row = parse_urlset(body)[0]
        self.assertEqual(row['discovery_title'], 'News & Title')
        self.assertIn('U+0000=1,U+001F=1', row['discovery_issue'])

    def test_non_title_controls_and_other_xml_errors_are_not_recovered(self):
        modifications = [
            BODY.replace('/noticia/test/', '/noticia/te\x10st/'),
            BODY.replace('2024-05-28T09:00:00', '2024-05-\x0828T09:00:00'),
            BODY.replace('2026-01-01', '2026-01-\x1001'),
            BODY.replace('<news:title>', '<news:title extra="\x10">'),
            BODY.replace('</news:title>', '</news:title>\x10'),
            BODY.replace('<url>', '<url><!--\x10-->'),
            BODY.replace('<url>', '<url><?test \x10?>'),
            BODY.replace('Test &amp; Title', 'Bad &#x10; title'),
            BODY.replace('Test &amp; Title', '\x10Bad &broken; title'),
            BODY.replace('Test &amp; Title', '\x10Bad <b>bold</news:title>'),
            BODY.replace('xmlns:news="http://www.google.com/schemas/sitemap-news/0.9"', 'xmlns:news="https://other.example/news"').replace('Test &amp; Title', '\x10Wrong namespace'),
            '<!DOCTYPE urlset [<!ENTITY bad "\x10">]>' + BODY.replace('Test &amp; Title', '&bad;'),
        ]
        for text in modifications:
            with self.subTest(text=repr(text)):
                with self.assertRaises((ValueError, ET.ParseError)):
                    parse_urlset(text)

    def test_all_controls_must_be_in_title_not_just_first_error(self):
        mixed = BODY.replace('Test &amp; Title', '\x10Test &amp; Title').replace('2024-05-28T09:00:00', '2024-05-28T\x0809:00:00')
        with self.assertRaises(ValueError):
            parse_urlset(mixed)

    def test_title_repair_retains_existing_discovery_issue(self):
        row = parse_urlset(BODY.replace('Test &amp; Title', '\x10Title').replace('2024-05-28T09:00:00', 'invalid'))[0]
        self.assertEqual(row['discovery_issue'], 'invalid_news_publication_date;illegal_xml_controls_removed_from_news_title:U+0010=1')
        self.assertIsNone(row['discovery_day'])
        row = parse_urlset(BODY.replace('Test &amp; Title', '\x10Title').replace('https://www.tiempo.com.mx/noticia/test/', 'https://other.example/a/b/'))[0]
        self.assertFalse(row['candidate_article'])
        self.assertIn('unrecognized_article_url;', row['discovery_issue'])

    @patch('crawler_core.tiempo_discovery.time.sleep')
    def test_control_title_raw_snapshot_retained_and_revalidated_offline(self,_):
        freeze(self.index,self.run)
        raw = BODY.replace('Test &amp; Title', '\x10Test &amp; Title')
        result = run_discovery(self.run, fetcher=lambda *a: {'status':200,'error':None,'text':raw}, min_free_bytes=0)
        self.assertEqual(result['map_states'], {'complete':1})
        snapshot = next((self.run/'snapshots').glob('*.xml'))
        self.assertEqual(snapshot.read_bytes(), raw.encode('utf-8'))
        run_discovery(self.run, fetcher=lambda *a:self.fail('no live refetch'), min_free_bytes=0)
        with sqlite3.connect(self.run/'discovery.sqlite') as c:
            row=c.execute('SELECT candidate_article,discovery_title,discovery_issue FROM entries').fetchone()
        self.assertEqual(row, (1, 'Test & Title', 'illegal_xml_controls_removed_from_news_title:U+0010=1'))

    def test_cached_source_capture_time_and_xml_bytes_preserved(self):
        from crawler_core.tiempo_pilot import digest
        for mode, fields, expected in (
            ('captured', {'captured_at':'2026-09-20T01:02:03+00:00', 'started_at':'2026-09-19T01:02:03+00:00'}, '2026-09-20T01:02:03+00:00'),
            ('started', {'started_at':'2026-09-19T01:02:03+00:00'}, '2026-09-19T01:02:03+00:00'),
            ('unknown', {}, None),
        ):
            with self.subTest(mode=mode):
                run = self.root / mode
                cache = self.root / ('cache-' + mode)
                cache.mkdir()
                raw = BODY.replace('<url>', '<url>\r\n').replace('Test &amp; Title', '\x10Test &amp; Title').encode('utf-8')
                (cache/'cached.xml').write_bytes(raw)
                record = {'url':CHILD, 'status':200, 'error':None, 'snapshot':'cached.xml', 'snapshot_sha256':digest(raw), **fields}
                (cache/'requests.jsonl').write_text(json.dumps(record)+'\n')
                freeze(self.index,run)
                run_discovery(run, recon_dir=cache, fetcher=lambda *a:self.fail('cache must not fetch'), min_free_bytes=0)
                snapshot = next((run/'snapshots').glob('*.xml'))
                metadata = json.loads(snapshot.with_suffix('.json').read_text())
                self.assertEqual(snapshot.read_bytes(), raw)
                self.assertEqual(metadata['captured_at'], expected)
                self.assertEqual(metadata['source_capture']['captured_at'], expected)
                self.assertEqual(metadata['source_capture']['snapshot_sha256'], digest(raw))
                self.assertTrue(metadata['processed_at'])
                self.assertTrue(metadata['reused_recon'])
                self.assertIsNone(metadata['network_request_id'])
                self.assertEqual(metadata['cache_snapshot'], str(cache/'cached.xml'))
                with sqlite3.connect(run/'discovery.sqlite') as c:
                    self.assertEqual(c.execute('SELECT captured_at FROM attempts').fetchone()[0], expected)

    def test_summary_missing_path_never_creates_database(self):
        with self.assertRaises(ValueError):
            summary(self.root / 'does-not-exist')
        self.assertFalse((self.root / 'does-not-exist').exists())
        empty = self.root / 'empty'
        empty.mkdir()
        with self.assertRaises(ValueError):
            summary(empty)
        self.assertFalse((empty / 'discovery.sqlite').exists())
        freeze(self.index, self.run)
        original = (self.run / 'discovery.sqlite').read_bytes()
        self.assertEqual(summary(self.run)['map_states'], {'pending':1})
        self.assertEqual((self.run / 'discovery.sqlite').read_bytes(), original)

if __name__=='__main__':unittest.main()

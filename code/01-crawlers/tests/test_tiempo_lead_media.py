"""Offline lead-media correction and independent omission detection; no HTTP."""
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawler_core.tiempo_html import tiempo_fields
from crawler_core import tiempo_continuous_source as source

URL = 'https://www.tiempo.com.mx/local/unseen-lead-media-fixture/'
VIDEO = 'https://www.youtube.com/embed/unseenClip123'
DONOR = Path('/Users/kevinfu/Library/CloudStorage/Dropbox/Media/data/00-newspaper_data/crawler/pilots/Kevin/Continuations/Remaining_Source_Encoding_Recovery_20261012')


def page(lead='', body='', *, after='', byline='Por: <a class="m-r-sm">Ana</a> 01 Junio 2024 12:01'):
    return (f'<html><head><meta charset="utf-8"><link rel="canonical" href="{URL}"></head><body>'
            '<article id="article-post"><header><h1>Article fixture</h1></header>'
            f'<blockquote><p>{lead}</p>{byline}</blockquote>'
            f'<div class="complementos-container">{body}</div>{after}</article></body></html>')


def frame(url=VIDEO, attrs=''):
    return f'<iframe src="{url}" {attrs}></iframe>'


class LeadMediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def parsed_check(self, html, **changes):
        row = tiempo_fields(html, url=URL)
        raw = html.encode('utf-8')
        (self.root / 'source.html').write_bytes(raw)
        row.update(sample_id='UNSEEN', url=URL, final_url=URL, status=200,
                   snapshot_path='source.html', snapshot_sha256=hashlib.sha256(raw).hexdigest(),
                   qa_status='success' if row['main_text'] else 'error',
                   error=None if row['main_text'] else 'missing_body', sample_metadata_json='{}')
        row.update(changes)
        return row, source.diagnose(row, self.root)

    def test_lead_only_video_keeps_missing_text_and_independent_evidence(self):
        row, check = self.parsed_check(page(frame()))
        self.assertEqual(json.loads(row['media_embeds']), [VIDEO])
        self.assertEqual(row['article_kind'], 'video_only')
        self.assertIsNone(row['summary'])
        self.assertIsNone(row['main_text'])
        self.assertEqual(row['error'], 'missing_body')
        self.assertTrue(check['recognized_video_only'])
        self.assertEqual(check['independent_video_evidence'][0]['url'], VIDEO)

    def test_versioned_body_only_native_video_contract_is_unchanged(self):
        row = tiempo_fields(page(body='<video src="/assets/clip.mp4"><source src="../alt.webm" type="video/webm"></video>'), url=URL)
        self.assertEqual(json.loads(row['media_embeds']), ['https://www.tiempo.com.mx/assets/clip.mp4', 'https://www.tiempo.com.mx/local/alt.webm'])
        self.assertEqual(json.loads(row['media_evidence']), [
            {'source':'native_video.src','raw_url':'/assets/clip.mp4','url':'https://www.tiempo.com.mx/assets/clip.mp4','media_kind':'video'},
            {'source':'native_video.source.src','raw_url':'../alt.webm','url':'https://www.tiempo.com.mx/local/alt.webm','media_kind':'video'}])
        self.assertEqual(row['classification_rule_version'], 'tiempo_media_v2_lead_and_body')

    def test_lead_body_order_deduplication_and_text_unchanged(self):
        row, check = self.parsed_check(page('Lead prose.' + frame(), '<p>Body prose.</p>' + frame() + '<video src="/clip.mp4"></video>'))
        self.assertEqual(json.loads(row['media_embeds']), [VIDEO, 'https://www.tiempo.com.mx/clip.mp4'])
        self.assertEqual(row['main_text'], 'Lead prose.\nBody prose.')
        self.assertEqual(row['summary'], 'Lead prose.')
        self.assertEqual(row['authors'], 'Ana')
        self.assertEqual(row['date_published'], '2024-06-01T12:01:00')
        self.assertEqual(row['article_kind'], 'article_with_video')
        self.assertNotIn('source_vs_output_media_difference', check['automatic_flags'])

    def test_removed_or_substituted_lead_link_is_detected_independently(self):
        for links in ('[]', '["https://www.youtube.com/embed/wrong"]'):
            with self.subTest(links=links):
                _, check = self.parsed_check(page(frame(), '<p>Body.</p>'), media_embeds=links)
                self.assertIn('source_vs_output_media_difference', check['automatic_flags'])

    def test_header_sidebar_and_after_byline_are_not_lead_media(self):
        html = page('', '<p>Body.</p>', after='<aside>'+frame()+'</aside>',
                    byline='Por: <a class="m-r-sm">Ana'+frame()+'</a> 01 Junio 2024 12:01'+frame())
        html = html.replace('</header>', frame()+'</header>')
        row, check = self.parsed_check(html)
        self.assertEqual(json.loads(row['media_embeds']), [])
        self.assertEqual(row['article_kind'], 'article')
        self.assertEqual(check['independent_video_evidence'], [])

    def test_lead_ad_and_navigation_scopes_excluded(self):
        wrappers = ['<div class="ad">{}</div>', '<div class="publicidad-content">{}</div>',
                    '<nav>{}</nav>', '<aside>{}</aside>', '<footer>{}</footer>', '<form>{}</form>',
                    '<button>{}</button>', '<div class="share-buttons">{}</div>',
                    '<div id="sidebar">{}</div>', '<noscript>{}</noscript>']
        for wrapper in wrappers:
            with self.subTest(wrapper=wrapper):
                row, check = self.parsed_check(page(wrapper.format(frame()), '<p>Body.</p>'))
                self.assertEqual(json.loads(row['media_embeds']), [])
                self.assertEqual(check['independent_video_evidence'], [])
        row, _ = self.parsed_check(page(frame(attrs='class="ad"'), '<p>Body.</p>'))
        self.assertEqual(json.loads(row['media_embeds']), [])

    def test_iframe_fallback_is_not_additional_media(self):
        html = page(f'<iframe src="{VIDEO}"><video src="/fallback.mp4"></video><script>unknownFallback()</script></iframe>')
        row, check = self.parsed_check(html)
        self.assertEqual(json.loads(row['media_embeds']), [VIDEO])
        self.assertEqual([x['url'] for x in check['independent_video_evidence']], [VIDEO])

    def test_unknown_lead_urls_retained_but_require_review(self):
        for link in ('https://unknown.example/player', 'https://www.youtube.com.evil.test/embed/x',
                     'https://user@www.youtube.com/embed/x', 'https://[invalid/video', 'javascript:unknown()'):
            with self.subTest(link=link):
                row, check = self.parsed_check(page(frame(link), '<p>Body.</p>'))
                self.assertEqual(json.loads(row['media_embeds']), [link])
                self.assertEqual(json.loads(row['media_evidence']), [])
                self.assertEqual(row['article_kind'], 'article')
                self.assertIn('unrecognized_lead_media_requires_review', check['automatic_flags'])

    def test_unknown_dynamic_markup_is_not_video_exemption(self):
        variants = ['<span onclick="loadMedia()">'+frame()+'</span>',
                    frame()+'<script>loadUnknown()</script>',
                    '<iframe data-src="'+VIDEO+'"></iframe>',
                    '<object data="/unknown.swf"></object>',
                    frame(attrs='onload="loadUnknown()"'), frame(attrs='srcdoc="unknown"'),
                    '<iframe></iframe>', '<iframe data-embed="https://unknown.example/player"></iframe>',
                    '<video controls></video>', '<source src="https://media.example/clip.mp4">',
                    '<video src="javascript:bad()"></video>',
                    '<span style="background-image:url(https://unknown.example/image)">'+frame()+'</span>']
        for lead in variants:
            with self.subTest(lead=lead):
                row, check = self.parsed_check(page(lead, '<p>Body.</p>'))
                self.assertEqual(row['source_specific_error'], 'unrecognized_lead_dynamic_media')
                self.assertEqual(json.loads(row['media_evidence']), [])
                self.assertIn('unrecognized_lead_dynamic_media', check['automatic_flags'])
                self.assertEqual(check['independent_video_evidence'], [])

    def test_multiple_leads_are_ambiguous_not_merged(self):
        row, check = self.parsed_check(page(frame(), '<p>Body.</p>', after='<blockquote>'+frame()+'</blockquote>'))
        self.assertEqual(row['source_specific_error'], 'ambiguous_article_media_lead')
        self.assertEqual(json.loads(row['media_embeds']), [])
        self.assertIn('ambiguous_article_body_or_lead_containers', check['automatic_flags'])

    def test_missing_byline_boundary_fails_closed_only_when_media_present(self):
        row, check = self.parsed_check(page(frame(), '<p>Body.</p>', byline='Unknown attribution'))
        self.assertEqual(row['source_specific_error'], 'unrecognized_article_media_byline_boundary')
        self.assertIn('unrecognized_article_media_byline_boundary', check['automatic_flags'])
        plain = tiempo_fields(page('Lead.', '<p>Body.</p>', byline=''), url=URL)
        self.assertIsNone(plain['source_specific_error'])

    def test_known_facebook_link_keeps_existing_classification_limit(self):
        link = 'https://www.facebook.com/plugins/video.php?href=https%3A%2F%2Fwww.facebook.com%2Fa%2Fvideos%2F123'
        row, check = self.parsed_check(page(frame(link), '<p>Body.</p>'))
        self.assertEqual(json.loads(row['media_embeds']), [link])
        self.assertEqual(row['article_kind'], 'article')
        self.assertEqual(check['independent_video_evidence'], [])
        self.assertNotIn('unrecognized_lead_media_requires_review', check['automatic_flags'])

    def test_saved_actual436991_only_media_fields_change_and_old_omission_detected(self):
        selection = DONOR / 'reviews/plan_000065/checkpoint_00000800/selection_00000800.json'
        self.assertTrue(selection.is_file(), 'Bound saved production source is required for this offline regression')
        x = next(r for r in json.loads(selection.read_text())['selected_records'] if r['sample_id']=='TC5_436991')
        raw = Path(x['snapshot_path']).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), x['snapshot_sha256'])
        batch = Path(x['row_check']['path']).parent.parent / 'batches' / x['batch_id']
        with sqlite3.connect((batch/'pilot.sqlite').as_uri()+'?mode=ro', uri=True) as db:
            payload = db.execute('SELECT payload_json FROM articles WHERE sample_id=?', (x['sample_id'],)).fetchone()[0]
        self.assertEqual(hashlib.sha256(payload.encode()).hexdigest(), x['payload_sha256'])
        old = json.loads(payload)
        parsed = tiempo_fields(raw.decode('utf-8'), url=old['url'])
        for key in ('title','summary','main_text','authors','date_published','canonical_url'):
            self.assertEqual(parsed[key], old[key], key)
        youtube = 'https://www.youtube.com/embed/R8NeB10INDo'
        self.assertEqual(json.loads(parsed['media_embeds']), [youtube])
        self.assertEqual(parsed['article_kind'], 'article_with_video')
        self.assertIn('source_vs_output_media_difference', source.diagnose(old,batch)['automatic_flags'])
        corrected = dict(old, **{k:parsed[k] for k in ('media_embeds','media_evidence','article_kind','classification_rule_version')})
        check = source.diagnose(corrected,batch)
        self.assertNotIn('source_vs_output_media_difference', check['automatic_flags'])
        self.assertEqual(check['independent_video_evidence'][0]['url'],youtube)
        self.assertIn('18 de agosto de 2018',corrected['main_text'])
        self.assertEqual(corrected['date_published'],'2018-07-23T12:26:43')
        self.assertEqual(hashlib.sha256(Path(x['snapshot_path']).read_bytes()).hexdigest(),x['snapshot_sha256'])


if __name__ == '__main__':
    unittest.main()

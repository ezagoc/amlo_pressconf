"""Independent, offline source expectations; never use the article parser as oracle."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawler_core import tiempo_continuous_source as source

URL = 'https://www.tiempo.com.mx/local/source-fixture/'
SUMMARY = 'Resumen conservado.'
PROSE = 'La noticia conserva todas sus palabras y cifras originales. ' * 6
BYLINE = 'Por: <a class="m-r-sm">Ana</a> 01 Junio 2024 12:01'
RELATED = '<p><strong><a href="https://puentelibre.mx/noticia/related/">Podría interesarte: Otra noticia</a></strong></p>'


def page(body=None, *, head='', byline=BYLINE, after='', title='Noticia'):
    if body is None:
        body = '<p>' + PROSE + '</p>'
    return ('<html><head><link rel="canonical" href="' + URL + '">' + head + '</head><body>'
            '<article id="article-post"><header><h1>' + title + '</h1></header>'
            '<blockquote><p>' + SUMMARY + '</p>' + byline + '</blockquote>'
            '<div class="complementos-container">' + body + '</div>' + after + '</article></body></html>')


class Priority2SourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def check(self, html, **values):
        path = self.root / 'snapshot.html'
        path.write_text(html)
        payload = {
            'sample_id': 'SOURCE_TEST', 'url': URL, 'final_url': URL,
            'canonical_url': URL, 'status': 200, 'content_type': 'text/html',
            'snapshot_path': path.name, 'snapshot_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'qa_status': 'success', 'error': None, 'title': 'Noticia', 'summary': SUMMARY,
            'main_text': SUMMARY + '\n' + PROSE, 'authors': 'Ana',
            'date_published': '2024-06-01T12:01:00', 'publication_date_source': 'visible_byline',
            'media_embeds': '[]', 'sample_metadata_json': '{}',
        }
        payload.update(values)
        return source.diagnose(payload, self.root)

    def test_control_has_no_flags(self):
        self.assertEqual(self.check(page())['automatic_flags'], [])

    def test_nested_body_article_preserves_markup_warning_without_ambiguity(self):
        body = '<article data-testid="conversation-turn-1"><div data-message-author-role="assistant"><p>' + PROSE + '</p></div></article>'
        result = self.check(page(body))
        self.assertEqual(result['automatic_flags'], [])
        self.assertEqual(result['source_markup_warnings'], ['nested_article_markup_inside_body', 'source_embedded_conversation_markup'])
        self.assertTrue(result['source_markup_evidence'])
        self.assertEqual(result['manual_review_status'], 'not_reviewed')

    def test_nested_body_article_does_not_hide_dropped_prose(self):
        body = '<article><p>' + PROSE + '</p><p>Extra news fact 42.</p></article>'
        self.assertIn('raw_visible_body_difference_requires_reading', self.check(page(body))['automatic_flags'])

    def test_second_primary_outside_article_or_body_remains_ambiguous(self):
        cases = [page(after='<article>Other story.</article>'),
                 page().replace('</body>', '<article>Other story.</article></body>'),
                 page('<article id="article-post"><p>' + PROSE + '</p></article>'),
                 page(after='<div class="complementos-container"><p>Other story.</p></div>'),
                 page(after='<blockquote>Second lead.</blockquote>')]
        for html in cases:
            with self.subTest(html=html):
                self.assertIn('ambiguous_article_body_or_lead_containers', self.check(html)['automatic_flags'])

    def test_terminal_recommendation_before_iframe_is_contractual_exclusion(self):
        body = '<p>' + PROSE + '</p>' + RELATED + '<iframe src="https://www.youtube.com/embed/123"></iframe>'
        result = self.check(page(body), media_embeds='["https://www.youtube.com/embed/123"]')
        self.assertEqual(result['automatic_flags'], [])
        self.assertEqual(result['independently_recognized_template_ui'], [{
            'reason': 'terminal_related_article_link', 'text': 'Podría interesarte: Otra noticia',
            'href': 'https://puentelibre.mx/noticia/related/'}])

    def test_related_mid_article_or_mixed_prose_cannot_be_dropped(self):
        cases = [RELATED + '<p>' + PROSE + '</p>',
                 '<p>' + PROSE + '</p>' + RELATED.replace('</strong>', '</strong> Extra reported fact.'),
                 '<p>' + PROSE + '</p>' + RELATED.replace('Podría interesarte:', 'Puedes leer:'),
                 '<p>' + PROSE + '</p><p><div>Real prose</div>' + RELATED + '</p>']
        for body in cases:
            with self.subTest(body=body):
                self.assertIn('raw_visible_body_difference_requires_reading', self.check(page(body))['automatic_flags'])

    def test_retained_terminal_recommendation_is_detected_as_extra_output(self):
        result = self.check(page('<p>' + PROSE + '</p>' + RELATED), main_text=SUMMARY + PROSE + 'Podría interesarte: Otra noticia')
        self.assertIn('raw_visible_body_difference_requires_reading', result['automatic_flags'])

    def test_equivalent_date_precision_and_offsets(self):
        equivalent = [
            ('2024-06-01T12:01:00Z', '2024-06-01T12:01:00+00:00'),
            ('2024-06-01T07:01:00-05:00', '2024-06-01T12:01:00Z'),
            ('2024-06-01T12:01', '2024-06-01T12:01:59'),
            ('2024-06-01', '2024-06-01T23:59:59-06:00'),
            ('2024-06-01T12:01:00.12Z', '2024-06-01T12:01:00.123Z'),
            ('2024-06-01T12:01:00', '2024-06-01T12:01:00-06:00'),
        ]
        for left, right in equivalent:
            with self.subTest(left=left, right=right):
                self.assertTrue(source.publication_dates_agree(left, right))
                self.assertTrue(source.publication_dates_agree(right, left))

    def test_real_date_conflicts_or_invalid_values_not_equal(self):
        conflicts = [
            ('2024-06-01', '2024-06-02T00:00:00'),
            ('2024-06-01T12:01:00', '2024-06-01T12:01:01'),
            ('2024-06-01T12:01:00Z', '2024-06-01T12:01:00-06:00'),
            ('2024-06-01T12:01:00.12Z', '2024-06-01T12:01:00.13Z'),
            ('2024-06-01T12:01', '2024-06-01T12:02'),
            (None, '2024-06-01'), ({'unexpected': 1}, '2024-06-01'),
            ('2024-02-30', '2024-03-01'),
        ]
        for left, right in conflicts:
            with self.subTest(left=left, right=right):
                self.assertFalse(source.publication_dates_agree(left, right))

    def test_equivalent_json_and_og_dates_do_not_flag(self):
        for raw in ['2024-06-01', '2024-06-01T12:01', '2024-06-01T12:01:00Z', '2024-06-01T07:01:00-05:00']:
            ld = '<script type="application/ld+json">' + json.dumps({'@type': 'NewsArticle', 'datePublished': raw}) + '</script>'
            head = ld + '<meta property="article:published_time" content="' + raw + '">'
            result = self.check(page(head=head), date_published='2024-06-01T12:01:00+00:00')
            with self.subTest(raw=raw):
                self.assertNotIn('article_vs_jsonld_date_difference', result['automatic_flags'])
                self.assertNotIn('article_vs_og_date_difference', result['automatic_flags'])

    def test_jsonld_without_publication_is_not_conflicting_evidence(self):
        for value in [{'@type': 'NewsArticle', 'headline': 'Noticia'},
                      {'@type': 'NewsArticle', 'dateModified': '2025-01-01T00:00:00'}]:
            self.assertEqual(self.check(page(head='<script type="application/ld+json">' + json.dumps(value) + '</script>'))['automatic_flags'], [])

    def test_real_conflicting_json_and_og_still_flag(self):
        head = '<script type="application/ld+json">{"@type":"NewsArticle","datePublished":"2024-06-02"}</script><meta property="article:published_time" content="2024-06-02">'
        flags = self.check(page(head=head))['automatic_flags']
        self.assertIn('article_vs_jsonld_date_difference', flags)
        self.assertIn('article_vs_og_date_difference', flags)

    def test_visible_date_only_does_not_invent_midnight_or_conflict(self):
        result = self.check(page(byline=BYLINE.replace(' 12:01', '')))
        self.assertNotIn('unrecognized_visible_byline_date', result['automatic_flags'])
        self.assertNotIn('visible_byline_date_difference', result['automatic_flags'])
        wrong = self.check(page(byline=BYLINE.replace('01 Junio', '02 Junio')))
        self.assertIn('visible_byline_date_difference', wrong['automatic_flags'])

    def test_plain_and_formatted_byline_author_needs_no_hyperlink(self):
        for byline in ['Por: Ana 01 Junio 2024 12:01',
                       'Por: <span><strong>Ana</strong></span> 01 Junio 2024 12:01',
                       'Por: Ana 01 Junio 2024']:
            with self.subTest(byline=byline):
                self.assertNotIn('visible_author_difference', self.check(page(byline=byline))['automatic_flags'])
                self.assertIn('visible_author_difference', self.check(page(byline=byline), authors='Different Author')['automatic_flags'])

    def test_missing_author_is_not_invented(self):
        html = page(byline='Por: 01 Junio 2024 12:01')
        self.assertNotIn('visible_author_difference', self.check(html, authors=None)['automatic_flags'])
        self.assertIn('visible_author_difference', self.check(html, authors='Ana')['automatic_flags'])

    def test_twitter_video_and_statuses_media_links_match_and_missing_link_fails(self):
        for css in ['twitter-tweet', 'twitter-video']:
            for route in ['status', 'statuses']:
                link = 'https://x.com/example/' + route + '/123'
                body = '<p>' + PROSE + '</p><blockquote class="' + css + '"><a href="' + link + '">Video</a></blockquote>'
                with self.subTest(css=css, route=route):
                    result = self.check(page(body), main_text=SUMMARY + PROSE + 'Video', media_embeds=json.dumps([link]))
                    self.assertNotIn('source_vs_output_media_difference', result['automatic_flags'])
                    self.assertIn('source_vs_output_media_difference', self.check(page(body), main_text=SUMMARY + PROSE + 'Video')['automatic_flags'])

    def test_native_video_relative_urls_and_dedup(self):
        body = '<p>' + PROSE + '</p><video src="/video/main.mp4"><source src="//static.tiempo.com.mx/v.webm"><source src="/video/main.mp4"></video>'
        media = ['https://www.tiempo.com.mx/video/main.mp4', 'https://static.tiempo.com.mx/v.webm']
        self.assertNotIn('source_vs_output_media_difference', self.check(page(body), media_embeds=json.dumps(media))['automatic_flags'])
        self.assertIn('source_vs_output_media_difference', self.check(page(body), media_embeds=json.dumps(media[:1]))['automatic_flags'])

    def test_native_video_unusable_or_ad_resources_not_expected(self):
        body = '<p>' + PROSE + '</p><video src="javascript:bad"><source src="https://user:pass@example.com/x"><source src="https://x.com:bad/x"><source src=" "></video><aside><video src="/ad.mp4"></video></aside><picture><source src="/image.webp"></picture>'
        self.assertNotIn('source_vs_output_media_difference', self.check(page(body))['automatic_flags'])

    def test_native_relative_resource_uses_final_response_not_request_or_canonical(self):
        body = '<p>' + PROSE + '</p><video src="clip.mp4"></video>'
        final = 'https://www.tiempo.com.mx/videos/redirect-target/'
        result = self.check(page(body), final_url=final, media_embeds=json.dumps([final + 'clip.mp4']))
        self.assertNotIn('source_vs_output_media_difference', result['automatic_flags'])
        wrong = self.check(page(body), final_url=final, media_embeds=json.dumps([URL + 'clip.mp4']))
        self.assertIn('source_vs_output_media_difference', wrong['automatic_flags'])

    def test_snapshot_hash_binding_still_enforced(self):
        with self.assertRaisesRegex(ValueError, 'Snapshot corruption'):
            self.check(page(), snapshot_sha256='0' * 64)

    def check_video_only(self, body, *, source_change=None, **values):
        html = page(body).replace('<p>' + SUMMARY + '</p>', '<p></p>')
        if source_change:
            html = source_change(html)
        return self.check(html, **dict({'qa_status': 'error', 'error': 'missing_body',
                         'summary': None, 'main_text': None, **values}))

    def test_genuine_zero_prose_video_is_source_warning_not_technical_error(self):
        cases = [('<video src="/clip.mp4"></video>', ['https://www.tiempo.com.mx/clip.mp4']),
                 ('<iframe src="https://www.youtube.com/embed/abc"></iframe>', ['https://www.youtube.com/embed/abc']),
                 ('<iframe src="//player.vimeo.com/video/123"></iframe>', ['//player.vimeo.com/video/123']),
                 ('<blockquote class="twitter-video"><a href="https://x.com/a/statuses/123"></a></blockquote>', ['https://x.com/a/statuses/123'])]
        for body, media in cases:
            with self.subTest(body=body):
                result = self.check_video_only(body, media_embeds=json.dumps(media), article_kind='untrusted_label')
                self.assertTrue(result['recognized_video_only'])
                self.assertEqual(result['source_content_warnings'], ['source_video_without_text'])
                self.assertEqual(result['automatic_flags'], ['suspicious_very_short_body_review_only'])
                self.assertEqual(result['qa_status'], 'error')
                self.assertEqual(result['error'], 'missing_body')
                self.assertEqual(result['manual_review_status'], 'not_reviewed')

    def test_arbitrary_empty_embeds_or_ad_video_cannot_claim_video_exception(self):
        cases = [('', []), ('<script src="https://www.youtube.com/embed/abc"></script>', []),
                 ('<iframe src="https://example.test/embed/abc"></iframe>', ['https://example.test/embed/abc']),
                 ('<iframe src="https://www.youtube.com.evil.test/embed/abc"></iframe>', ['https://www.youtube.com.evil.test/embed/abc']),
                 ('<div class="ad"><video src="/clip.mp4"></video></div>', []),
                 ('<iframe class="ad" src="https://www.youtube.com/embed/abc"></iframe>', ['https://www.youtube.com/embed/abc']),
                 ('<a href="https://www.youtube.com/embed/abc"></a>', []),
                 ('<blockquote class="twitter-tweet"><a href="https://x.com/a/status/123"></a></blockquote>', ['https://x.com/a/status/123'])]
        for body, media in cases:
            with self.subTest(body=body):
                result = self.check_video_only(body, media_embeds=json.dumps(media), article_kind='video_only')
                self.assertFalse(result['recognized_video_only'])
                self.assertIn('missing_body', result['automatic_flags'])
                self.assertIn('unexplained_result_error', result['automatic_flags'])

    def test_zero_prose_video_exception_requires_all_other_source_checks(self):
        body = '<video src="/clip.mp4"></video>'
        media = '["https://www.tiempo.com.mx/clip.mp4"]'
        cases = [{'media_embeds': '[]'}, {'date_published': None}, {'title': None},
                 {'publication_date_source': 'lastmod'}, {'authors': 'Wrong'},
                 {'canonical_url': 'https://www.tiempo.com.mx/local/wrong/'},
                 {'source_specific_error': 'unknown_error'}, {'date_conflict': 'conflict'},
                 {'source_change': lambda h: h.replace('<h1>Noticia</h1>', '<h1></h1>'), 'title': None},
                 {'source_change': lambda h: h.replace('01 Junio', '02 Junio')},
                 {'source_change': lambda h: h.replace('</head>', '<meta property="og:title" content="Different"></head>')},
                 {'source_change': lambda h: h.replace('</head>', '<meta property="article:published_time" content="2025-01-01"></head>')}]
        for changes in cases:
            with self.subTest(changes=changes):
                result = self.check_video_only(body, **{'media_embeds': media, **changes})
                self.assertFalse(result['recognized_video_only'])
                self.assertIn('missing_body', result['automatic_flags'])
                self.assertIn('unexplained_result_error', result['automatic_flags'])

    def test_zero_prose_video_label_never_hides_dropped_source_prose(self):
        result = self.check_video_only('<video src="/clip.mp4"></video><p>Omitted news fact.</p>',
                                       media_embeds='["https://www.tiempo.com.mx/clip.mp4"]', article_kind='video_only')
        self.assertFalse(result['recognized_video_only'])
        self.assertIn('raw_visible_body_difference_requires_reading', result['automatic_flags'])
        self.assertIn('unexplained_result_error', result['automatic_flags'])


if __name__ == '__main__':
    unittest.main()

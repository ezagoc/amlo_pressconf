"""Kevin: isolated, no-network regressions for the corroborated byline comment."""
import copy
import hashlib
import json
import sqlite3
import sys
import unittest
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup, Comment

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawler_core import tiempo_empty_shell as rule
from test_tiempo_empty_shell import qualifying_case, rebind


DONOR = Path('/Users/kevinfu/Library/CloudStorage/Dropbox/Media/data/00-newspaper_data/crawler/pilots/Kevin/Continuations/Remaining_Lead_Media_Supplement_20261012')


def footer_comment(author='Test Author ', published='2021-05-06T11:12:13'):
    d = datetime.fromisoformat(published)
    return (
        '<footer style="background-color: transparent;"><i class="fa fa-user text-muted" style="color: #444"></i> Por: '
        f'<a href="" class="m-r-sm"><strong>{author}</strong></a><br/></footer> '
        '<footer style="background-color: transparent;"><i class="fa fa-calendar text-muted" style="color: #444"></i> '
        f'{d.day:02d} {rule._MONTHS[d.month-1]} {d.year}<br/></footer> '
        '<footer style="background-color: transparent;"><i class="fa fa-clock-o text-muted" style="color: #444"></i> '
        f'{d.hour:02d} {d.minute:02d}<br/></footer>')


def with_comment(text=None, destination='p.lead blockquote'):
    case = qualifying_case(slug='unseen-comment-space-source')
    soup = BeautifulSoup(case[1].decode(), 'html.parser')
    soup.select_one(destination).append(Comment(footer_comment() if text is None else text))
    return rebind(case, str(soup).encode())


class CommentAuthorSpaceTests(unittest.TestCase):
    def assert_source_gap(self, case):
        before = copy.deepcopy(case)
        result = rule.classify_empty_article_shell(*case)
        self.assertTrue(result['matched'], result)
        self.assertEqual(result['classification'], 'source_unavailable_body_in_saved_response')
        self.assertFalse(result['evidence']['article_acceptance'])
        self.assertFalse(result['evidence']['human_approval'])
        self.assertFalse(result['evidence']['article_media_confirmed'])
        self.assertEqual(result['evidence']['research_status'], 'NEEDS_JOAQUIN_REVIEW')
        self.assertEqual(case, before)
        self.assertEqual(case[0]['qa_status'], 'error')
        self.assertEqual(case[0]['error'], 'missing_body')
        self.assertEqual(case[3]['manual_review_status'], 'not_reviewed')
        return result

    def test_original_exact_comment_and_new_boundary_whitespace(self):
        for author in ('Test Author', 'Test Author ', ' Test Author', '\tTest Author\n', '\u00a0Test Author\u00a0'):
            with self.subTest(author=repr(author)):
                self.assert_source_gap(with_comment(footer_comment(author)))

    def test_wrong_author_case_order_and_internal_spelling_reject(self):
        for author in ('Different Author ', 'test Author ', 'Author Test ', 'Test Auth or ', 'Test Author Extra '):
            with self.subTest(author=author):
                result = rule.classify_empty_article_shell(*with_comment(footer_comment(author)))
                self.assertFalse(result['matched'])
                self.assertIn('unrecognized_comment_content', result['rejection_reasons'])

    def test_wrong_comment_date_time_and_exact_markup_reject(self):
        base = footer_comment()
        bad_comments = [
            base.replace('06 Mayo 2021', '07 Mayo 2021'),
            base.replace('11 12', '11 13'),
            base.replace('<footer style=', '<footer data-hidden="body" style=', 1),
            base.replace('<strong>Test Author </strong>', '<strong><span>Test Author </span></strong>'),
            base + '<p>Hidden article prose was omitted.</p>',
            base + '<iframe src="https://unknown.example/media"></iframe>',
            base.replace('Por:', 'By:'),
        ]
        for text in bad_comments:
            with self.subTest(text=text):
                result = rule.classify_empty_article_shell(*with_comment(text))
                self.assertFalse(result['matched'])
                self.assertIn('unrecognized_comment_content', result['rejection_reasons'])

    def test_new_whitespace_exception_requires_actual_lead_context(self):
        for location in ('head', 'body', 'article#article-post', '.complementos-container'):
            with self.subTest(location=location):
                result = rule.classify_empty_article_shell(*with_comment(destination=location))
                self.assertFalse(result['matched'])
                self.assertIn('unrecognized_comment_content', result['rejection_reasons'])
        self.assertFalse(rule._known_comment(footer_comment(), 'Test Author', '2021-05-06T11:12:13'))
        # Existing exact-template acceptance is intentionally unchanged.
        self.assertTrue(rule._known_comment(footer_comment('Test Author'), 'Test Author', '2021-05-06T11:12:13'))

    def test_visible_prose_unknown_script_and_media_still_reject(self):
        case = with_comment()
        for html in ('<p>Real article prose must not disappear.</p>',
                     '<script>loadUnknownArticleMedia()</script>',
                     '<iframe src="https://unknown.example/player"></iframe>',
                     '<video data-src="https://unknown.example/movie.mp4"></video>'):
            with self.subTest(html=html):
                soup = BeautifulSoup(case[1].decode(), 'html.parser')
                soup.select_one('.complementos-container').append(BeautifulSoup(html, 'html.parser'))
                self.assertFalse(rule.classify_empty_article_shell(*rebind(case, str(soup).encode()))['matched'])

    def test_visible_jsonld_identity_and_publication_conflicts_reject(self):
        case = with_comment()
        for kind in ('visible_author', 'jsonld_author', 'jsonld_identity', 'canonical', 'headline', 'published'):
            soup = BeautifulSoup(case[1].decode(), 'html.parser')
            if kind == 'visible_author':
                soup.select_one('blockquote a strong').string = 'Someone Else'
            elif kind == 'canonical':
                soup.select_one('link[rel="canonical"]')['href'] = 'https://www.tiempo.com.mx/local/wrong/'
            elif kind == 'headline':
                soup.select_one('h1').string = 'A different headline'
            else:
                node = soup.select_one('script[type="application/ld+json"]'); data = json.loads(node.string)
                if kind == 'jsonld_author': data['author']['name'] = 'Someone Else'
                elif kind == 'jsonld_identity': data['mainEntityOfPage']['@id'] = 'wrong-identity'
                else: data['datePublished'] = '2021-05-07T11:12:13'
                node.string = json.dumps(data)
            with self.subTest(kind=kind):
                self.assertFalse(rule.classify_empty_article_shell(*rebind(case, str(soup).encode()))['matched'])

    def test_incomplete_transport_and_source_binding_reject(self):
        case = with_comment()
        for change in ({'error': 'connection_failed'}, {'curl_exit_code': 28},
                       {'body_text_limit_exceeded': True}, {'status': 503},
                       {'final_url': 'https://wrong.example/'}, {'body_encoding': 'latin-1'}):
            bad = copy.deepcopy(case); bad[2].update(change)
            with self.subTest(change=change):
                self.assertFalse(rule.classify_empty_article_shell(*bad)['matched'])
        self.assertFalse(rule.classify_empty_article_shell(*rebind(case, case[1].replace(b'</html>', b'')))['matched'])
        bad = copy.deepcopy(case); bad[0]['snapshot_sha256'] = '0' * 64
        self.assertFalse(rule.classify_empty_article_shell(*bad)['matched'])
        bad = copy.deepcopy(case); bad[3]['sample_id'] = 'WRONG'
        self.assertFalse(rule.classify_empty_article_shell(*bad)['matched'])

    def test_actual_stopped130743_and_prior_saved_empty_sources(self):
        selection = json.loads((DONOR/'reviews/plan_000065/checkpoint_00001200/selection_00001200.json').read_text())
        rows = {r['sample_id']: r for r in selection['snapshot']['rows']}
        child = DONOR/'Media/data/00-newspaper_data/crawler/pilots/Kevin/tiempo_continuous_v5/remaining_plan_000065'
        bindings = []
        for sid in ('TC5_130743', 'TC5_130744', 'TC5_130747', 'TC5_130629'):
            batch = child/'batches'/('batch_000019' if sid == 'TC5_130743' else rows[sid]['batch_id'])
            dbpath = batch/'pilot.sqlite'; checkpath = child/'row_checks'/f'{sid}.json'
            with sqlite3.connect(dbpath.as_uri()+'?mode=ro', uri=True) as db:
                payload = db.execute('SELECT payload_json FROM articles WHERE sample_id=?', (sid,)).fetchone()[0]
                row = json.loads(payload)
                response, completed = db.execute('SELECT response_json, completed_at FROM fetch_attempts WHERE attempt_id=?', (row['attempt_id'],)).fetchone()
            self.assertTrue(completed)
            rawpath = batch/row['snapshot_path']; raw = rawpath.read_bytes()
            check = json.loads(checkpath.read_text())['record']
            self.assertEqual(hashlib.sha256(raw).hexdigest(), row['snapshot_sha256'])
            originals = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (dbpath, rawpath, checkpath)}
            with self.subTest(sample_id=sid):
                result = self.assert_source_gap((row, raw, json.loads(response), check))
                self.assertEqual(result['rule_version'], 'tiempo-verified-static-source-gap-v8')
                self.assertEqual(originals, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in originals})
            bindings.append({'sample_id': sid, 'snapshot_sha256': row['snapshot_sha256'],
                             'payload_sha256': hashlib.sha256(payload.encode()).hexdigest(),
                             'row_check_sha256': originals[checkpath]})
        print('ACTUAL_SAVED_CASE_BINDINGS=' + json.dumps(bindings, sort_keys=True))


if __name__ == '__main__':
    unittest.main(verbosity=2)

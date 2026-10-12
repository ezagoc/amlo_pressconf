"""Focused no-network tests; real saved cases are opt-in, bound external files."""
import copy
import hashlib
import html
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawler_core import tiempo_empty_shell as rule


def qualifying_case(title='A synthetic headline', slug='synthetic-empty-shell',
                    published='2021-05-06T11:12:13', author='Test Author', sample_id='SYNTHETIC'):
    """Return row, raw bytes, response and source-check for isolated integration."""
    d = datetime.fromisoformat(published)
    url = f'https://www.tiempo.com.mx/noticia/{slug}/'
    canonical = f'https://www.tiempo.com.mx/local/{slug}/'
    article = (Path(__file__).parent/'fixtures/tiempo_empty_shell_article.html').read_text()
    for before, after in {'TITLE_SLOT':html.escape(title),'SLUG_SLOT':slug,'AUTHOR_SLOT':html.escape(author),
            'DATE_SLOT':f'{d.day:02d} {rule._MONTHS[d.month-1]} {d.year}',
            'TIME_SLOT':f'{d.hour:02d}:{d.minute:02d}'}.items():
        article = article.replace(before, after)
    a = BeautifulSoup(article, 'html.parser')
    for tag in a.select('.share-buttons a'):
        for key in list(tag.attrs):
            if key not in {'href','title','target','onclick','data-link','data-text','class'}:
                del tag[key]
    publisher = {'@type':'NewsMediaOrganization','name':'Tiempo La Noticia Digital',
        'url':'https://www.tiempo.com.mx','sameAs':['https://www.facebook.com/tiempo','https://www.twitter.com/tiempo_mx','https://www.instagram.com/tiempo.com.mx','https://www.youtube.com/@tiempotv'],
        'logo':{'@type':'ImageObject','url':'https://static.tiempo.com.mx/uploads/configuracion_periodico/imagen/1/logo-tiempo.png','height':110,'width':330}}
    ld = {'@context':'https://schema.org','@type':'NewsArticle','headline':title,'datePublished':published,
        'dateModified':published,'description':'','keywords':'','articleSection':'','articleBody':' ',
        'isAccessibleForFree':True,'publisher':publisher,'mainEntityOfPage':{'@type':'WebPage','@id':slug},
        'author':{'@type':'Person','name':author},'image':{'@type':'ImageObject',
            'url':'https://static.tiempo.com.mx/uploads/imagen/imagen/0/principal_','width':770,'height':423}}
    head = f'<title>{html.escape(title)}</title><link rel="canonical" href="{canonical}"><meta property="og:url" content="{canonical}"><meta property="og:title" content="{html.escape(title)}"><meta property="og:article:published_time" content="{published}">'
    scripts = '<script type="application/ld+json">'+json.dumps(ld,ensure_ascii=False)+'</script>'
    scripts += ''.join('<script>'+v+'</script>' for v in rule.FEATURES['known_inline_scripts'].values())
    scripts += ''.join('<script src="'+v+'"></script>' for v in sorted(rule._EXTERNAL))
    raw = ('<html><head>'+head+scripts+'</head><body><div id="main" class="article">'+str(a)+'</div></body></html>').encode()
    row = {'sample_id':sample_id,'url':url,'final_url':url,'canonical_url':canonical,'title':title,
        'authors':author,'date_published':published,'date_modified':published,'summary':None,'main_text':None,
        'error':'missing_body','qa_status':'error','status':200,'content_type':'text/html; charset=utf-8',
        'publication_date_source':'jsonld.datePublished','date_conflict':None,'source_specific_error':None,
        'media_embeds':'[]','media_evidence':'[]','article_kind':'article','snapshot_sha256':hashlib.sha256(raw).hexdigest()}
    response = {'status':200,'final_url':url,'error':None,'curl_exit_code':0,'body_text_limit_exceeded':False,
        'body_encoding':'utf-8','content_type':'text/html; charset=utf-8'}
    check = {'sample_id':sample_id,'url':url,'snapshot_sha256':row['snapshot_sha256'],
        'automatic_flags':['missing_body','unexplained_result_error','suspicious_very_short_body_review_only'],
        'critical_flags':[],'manual_review_status':'not_reviewed','source_markup_warnings':[],
        'outside_body_scope_evidence':[],'independent_video_evidence':[],'recognized_video_only':False}
    return row, raw, response, check


def rebind(case, raw):
    row, _, response, check = copy.deepcopy(case)
    row['snapshot_sha256'] = check['snapshot_sha256'] = hashlib.sha256(raw).hexdigest()
    return row, raw, response, check


def sidebar_poll(value='55.8', poll_id='12345'):
    """Minimal source-derived sidebar UI; no article text or original tokens."""
    return (f'<div id="sidebar"><div id="aplicacion-encuesta{poll_id}-container" class="encuesta">'
        '<div id="result" class="bs-chart-container collapse" style="width: 88%;padding: 15px 0;">'
        '<div class="progress" style="height:20px;">'
        f'<div class="progress-bar" role="progressbar" aria-valuenow="{value}" aria-valuemin="0" '
        f'style="width: {value}%; height:20px; background-color: #439646;">'
        f'<!-- span class="value">{value}% </span --><span class="">{value}% </span>'
        '</div></div></div></div></div>')


class EmptyShellTests(unittest.TestCase):
    def setUp(self):
        self.case = qualifying_case()

    def reject_html(self, transform):
        raw = transform(self.case[1].decode()).encode()
        result = rule.classify_empty_article_shell(*rebind(self.case,raw))
        self.assertFalse(result['matched'], result)
        self.assertTrue(result['rejection_reasons'])

    def test_positive_unlisted_slug_year_and_immutable_inputs(self):
        for year in [2018,2020,2024,2025]:
            case = qualifying_case(slug=f'new-unlisted-{year}',published=f'{year}-03-02T04:05:06')
            before=copy.deepcopy(case); result=rule.classify_empty_article_shell(*case)
            self.assertTrue(result['matched'], result)
            self.assertEqual(case,before)
            self.assertIsNone(case[0]['main_text']);self.assertEqual(case[0]['error'],'missing_body')
            self.assertFalse(result['evidence']['article_acceptance'])

    def test_actual_body_or_lead_prose(self):
        for transform in [lambda s:s.replace('<p> </p>','<p>Actual omitted article prose.</p>'),
                lambda s:s.replace('<blockquote style="padding: 0px">','<blockquote style="padding: 0px">An omitted lead.')]:
            with self.subTest(transform=transform):self.reject_html(transform)

    def test_outside_article_and_body_prose_or_table(self):
        for markup in ['<p>Actual omitted article prose.</p>','<table><tr><td>Count 37</td></tr></table>',
                '<figure><figcaption>Real fact omitted</figcaption></figure>']:
            with self.subTest(markup=markup):
                self.reject_html(lambda s:s.replace('</article>',markup+'</article>'))
                self.reject_html(lambda s:s.replace('</article>','</article>'+markup))
        for attrs in ['itemprop="articleBody"','class="article-content"','id="article-body"']:
            with self.subTest(attrs=attrs):
                self.reject_html(lambda s:s.replace('</body>',f'<div {attrs}>Actual source body.</div></body>'))

    def test_jsonld_prose_or_unknown_nested_content(self):
        for a,b in [('"articleBody": " "','"articleBody": "Actual news fact"'),
                    ('"keywords": ""','"keywords": "Unexplained source content"'),
                    ('"isAccessibleForFree": true','"isAccessibleForFree": false'),
                    ('"height": 110','"articleBody": "hidden prose", "height": 110')]:
            with self.subTest(a=a):self.reject_html(lambda s:s.replace(a,b))

    def test_unknown_embeds_media_and_images(self):
        for markup in ['<iframe src="https://example.org/story"></iframe>',
                '<video src="https://example.org/video.mp4"></video>',
                '<img src="https://static.tiempo.com.mx/uploads/imagen/news.jpg">',
                '<script>fetch("/article-data")</script>','<div data-src="/article-data"></div>',
                '<template><p>Hidden prose</p></template>','<div id="my-video"></div>']:
            with self.subTest(markup=markup):self.reject_html(lambda s:s.replace('</article>',markup+'</article>'))

    def test_unknown_ordinary_attributes_and_structure(self):
        for a,b in [('class="complementos-container','id="dynamic-loader" class="complementos-container'),
                    ('class="complementos-container','data-story="123" class="complementos-container'),
                    ('max-height: 600px','max-height: 601px')]:
            with self.subTest(a=a,b=b):self.reject_html(lambda s:s.replace(a,b))

    def test_unknown_comments_cannot_hide_prose_or_embeds(self):
        for markup in ['<!--<p>Real omitted prose.</p>-->','<!--<iframe src="/clip"></iframe>-->',
                       '<!--unrecognized source content-->']:
            with self.subTest(markup=markup):self.reject_html(lambda s:s.replace('</article>',markup+'</article>'))

    def test_unknown_script_and_dynamic_document_behavior(self):
        for markup in ['<script src="https://example.org/loader.js"></script>',
                '<script>document.querySelector("article").innerHTML="";</script>',
                '<meta http-equiv="refresh" content="0;url=/other">','<base href="https://example.org/">',
                '<div hx-get="/article"></div>']:
            with self.subTest(markup=markup):self.reject_html(lambda s:s.replace('</head>',markup+'</head>'))

    def test_metadata_prose_media_and_main_scope(self):
        for key in ['og:description','description','twitter:description','articleBody','transcript']:
            with self.subTest(key=key):
                self.reject_html(lambda s:s.replace('</head>',f'<meta name="{key}" content="An omitted article fact"></head>'))
        for key in ['og:image','twitter:image','twitter:player','image','thumbnailUrl','og:video:url']:
            with self.subTest(key=key):
                self.reject_html(lambda s:s.replace('</head>',f'<meta property="{key}" content="https://example.org/article-media"></head>'))
        for transform in [lambda s:s.replace('id="main"','id="unknown"'),
                lambda s:s.replace('id="main"','id="main" style="background-image:url(/article.png)"'),
                lambda s:s.replace('</head>','<link rel="image_src" href="/article.png"></head>')]:
            self.reject_html(transform)

    def test_imported_feature_binding_rejects_disk_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            changed=Path(tmp)/'features.json'; changed.write_bytes(rule._FEATURE_BYTES+b'\n')
            with patch.object(rule,'FEATURE_PATH',changed):
                result=rule.classify_empty_article_shell(*self.case)
                self.assertFalse(result['matched'])
                self.assertIn('feature_file_changed_since_import',result['rejection_reasons'])
                self.assertEqual(result['evidence']['feature_sha256'],rule.FEATURE_SHA256)

    def test_poll_comment_accepts_only_bound_percentage_slot(self):
        for value in ['0','11.0','55.8','15.3','2.3','15.6','100']:
            raw=self.case[1].decode().replace('</body>',sidebar_poll(value)+'</body>').encode()
            with self.subTest(value=value):
                result=rule.classify_empty_article_shell(*rebind(self.case,raw))
                self.assertTrue(result['matched'],result)
        # IDs vary freely; no URL, record, poll-ID or numeric-value whitelist.
        raw=self.case[1].decode().replace('</body>',sidebar_poll('42.72','87654321')+'</body>').encode()
        self.assertTrue(rule.classify_empty_article_shell(*rebind(self.case,raw))['matched'])

    def test_poll_comment_disagreement_scope_prose_media_reject(self):
        for markup in [sidebar_poll('101'),sidebar_poll('-1'),
                sidebar_poll().replace('aria-valuenow="55.8"','aria-valuenow="55.7"'),
                sidebar_poll().replace('width: 55.8%','width: 55.7%'),
                sidebar_poll().replace('<span class="">55.8%','<span class="">55.7%'),
                sidebar_poll().replace('id="sidebar"','id="main-other"'),
                sidebar_poll().replace('class="encuesta"','class="article-loader"'),
                sidebar_poll().replace('55.8% </span -->','55.8% article prose </span -->'),
                sidebar_poll().replace('55.8% </span -->','55.8% <iframe src="/clip"></iframe> </span -->'),
                sidebar_poll().replace('<span class="">','<img src="/hidden-media"><span class="">')]:
            with self.subTest(markup=markup):
                self.reject_html(lambda s:s.replace('</body>',markup+'</body>'))
        # A previously fingerprinted value must not evade contextual validation.
        self.reject_html(lambda s:s.replace('</article>','<!-- span class="value">11.0% </span --></article>'))
        self.reject_html(lambda s:s.replace('</article>',sidebar_poll()+'</article>'))

    def test_status_transport_truncation_and_binding(self):
        for key,value in [('status',403),('error','blocked'),('curl_exit_code',28),
                          ('body_text_limit_exceeded',True),('body_encoding','unknown')]:
            case=copy.deepcopy(self.case);case[2][key]=value
            with self.subTest(key=key):self.assertFalse(rule.classify_empty_article_shell(*case)['matched'])
        self.reject_html(lambda s:s.replace('</html>',''))
        self.reject_html(lambda s:s.replace('</article>','Access denied</article>'))
        case=copy.deepcopy(self.case);case[0]['snapshot_sha256']='0'*64
        self.assertFalse(rule.classify_empty_article_shell(*case)['matched'])

    def test_identity_and_actual_publication_conflicts(self):
        for a,b in [('<title>A synthetic headline','<title>Different article'),
                ('"@id": "synthetic-empty-shell"','"@id": "another-story"'),
                ('content="2021-05-06T11:12:13"','content="2021-05-07T11:12:13"')]:
            with self.subTest(a=a):self.reject_html(lambda s:s.replace(a,b))
        for key,value in [('canonical_url','https://www.tiempo.com.mx/local/different/'),('date_conflict','conflict')]:
            case=copy.deepcopy(self.case);case[0][key]=value
            with self.subTest(key=key):self.assertFalse(rule.classify_empty_article_shell(*case)['matched'])

    def test_author_only_whitespace_equivalence_and_immutable_inputs(self):
        for name in ['Test  Author',' Test\tAuthor ','Test\nAuthor','Test\u00a0Author']:
            raw=self.case[1].decode().replace('"name": "Test Author"','"name": '+json.dumps(name)).encode()
            case=rebind(self.case,raw); before=copy.deepcopy(case)
            with self.subTest(name=name):
                result=rule.classify_empty_article_shell(*case)
                self.assertTrue(result['matched'],result)
                self.assertEqual(case,before)
                self.assertEqual(case[0]['authors'],'Test Author')

    def test_author_identity_object_and_entity_are_not_relaxed(self):
        for old,new in [('"name": "Test Author"','"name": "Other Author"'),
                ('"name": "Test Author"','"name": "test Author"'),
                ('"name": "Test Author"','"name": "Author Test"'),
                ('"name": "Test Author"','"name": ["Test Author"]'),
                ('"name": "Test Author"','"name": "Test Author", "extra": "hidden source content"'),
                ('"@type": "Person"','"@type": "Organization"'),
                ('"@id": "synthetic-empty-shell"','"@id": "different-article"')]:
            with self.subTest(new=new):self.reject_html(lambda s:s.replace(old,new))

    def test_unhandled_research_or_technical_flag_is_not_waived(self):
        for flag in ['article_vs_discovery_day_difference','raw_visible_body_difference_requires_reading','non_html_response']:
            case=copy.deepcopy(self.case);case[3]['automatic_flags'].append(flag)
            with self.subTest(flag=flag):self.assertFalse(rule.classify_empty_article_shell(*case)['matched'])

    def test_normal_short_video_and_soft_error_not_relabelled(self):
        for fields in [{'main_text':'A real short item.','summary':'A real short item.','error':None,'qa_status':'success'},
                       {'main_text':'Full article. '*100,'error':None,'qa_status':'success'},
                       {'media_embeds':'["https://www.youtube.com/embed/123"]','article_kind':'video'},
                       {'source_specific_error':'soft_error_page','error':'soft_error_page'}]:
            case=copy.deepcopy(self.case);case[0].update(fields);before=copy.deepcopy(case)
            with self.subTest(fields=fields):self.assertFalse(rule.classify_empty_article_shell(*case)['matched']);self.assertEqual(case,before)


@unittest.skipUnless(os.environ.get('TIEMPO_EMPTY_SHELL_REAL_BATCH'), 'Set the bound local batch explicitly; no online fixture retrieval.')
class SavedSourceTests(unittest.TestCase):
    def test_five_actual_saved_responses(self):
        batch=Path(os.environ['TIEMPO_EMPTY_SHELL_REAL_BATCH']);child=batch.parent.parent
        with sqlite3.connect((batch/'pilot.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True) as db:
            for sid in ['TC5_476522','TC5_501081','TC5_552341','TC5_560498','TC5_514287']:
                row=json.loads(db.execute('SELECT payload_json FROM articles WHERE sample_id=?',(sid,)).fetchone()[0])
                response=json.loads(db.execute('SELECT response_json FROM fetch_attempts WHERE sample_id=?',(sid,)).fetchone()[0])
                raw=(batch/row['snapshot_path']).read_bytes();check=json.loads((child/'row_checks'/f'{sid}.json').read_text())['record']
                with self.subTest(sample_id=sid):
                    self.assertEqual(hashlib.sha256(raw).hexdigest(),row['snapshot_sha256'])
                    result=rule.classify_empty_article_shell(row,raw,response,check)
                    self.assertTrue(result['matched'],result)


if __name__=='__main__':unittest.main()

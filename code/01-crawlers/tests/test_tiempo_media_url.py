"""Kevin: targeted media-URL quarantine; no source requests or native edits."""
import copy
import hashlib
import html
import json
import sqlite3
import unittest
from pathlib import Path
from test_tiempo_lead_media_supplement import LeadMediaSupplementTests,html_page,URL,VIDEO
from crawler_core import tiempo_lead_media as media
from crawler_core import tiempo_effective_media_html as extractor
from crawler_core import tiempo_effective_media_source as independent

DONOR=Path('/Users/kevinfu/Library/CloudStorage/Dropbox/Media/data/00-newspaper_data/crawler/pilots/Kevin/Continuations/Remaining_Comment_Space_Recovery_20261012')
INERT='<blockquote class="instagram-media" data-instgrm-permalink="https:/www.instagram.com/p/UnseenID/"><div style="padding:16px"><p>A preserved attribute caption.</p></div></blockquote><script async src="/www.instagram.com/embed.js"></script>'

def markup_target(raw=INERT,sibling=''):
    return '<video><source src="'+html.escape(raw,quote=True)+'"></video>'+sibling

def article(raw=INERT,sibling=''):
    return html_page('A genuine short lead.').replace('</div></article>',markup_target(raw,sibling)+'</div></article>')

class MediaURLTests(unittest.TestCase):
    def setUp(self):
        self.fx=LeadMediaSupplementTests('runTest');self.fx.setUp();self.addCleanup(self.fx.doCleanups)

    def test_url_syntax_keeps_real_resources_without_html_or_repairs(self):
        for value in ('https://cdn.example/movie.mp4?x=1&y=2','//cdn.example/a.mp4','/media/a.mp4','clip%20one.mp4',VIDEO):
            with self.subTest(valid=value):
                self.assertEqual(extractor._media_http_url(value,URL),independent.valid_media_resource(value,URL))
                self.assertIsNotNone(independent.valid_media_resource(value,URL))
        for value in (INERT,'https:/www.instagram.com/p/X/','javascript:alert(1)','data:video/mp4;base64,AA','https://u:p@example.com/v','https://cdn.example/a b.mp4','a\n.mp4','https://[bad','https://example.com:bad/v'):
            with self.subTest(invalid=value):
                self.assertIsNone(extractor._media_http_url(value,URL));self.assertIsNone(independent.valid_media_resource(value,URL))

    def test_only_source_bound_invalid_target_removed_no_guess_or_caption(self):
        args=self.fx.fixture(article());frozen=copy.deepcopy(args)
        result=media.compute(*args)
        self.assertEqual(result['status'],'effective_media_correction')
        self.assertEqual(result['effective']['media_embeds'],'[]');self.assertEqual(result['effective']['media_evidence'],'[]')
        self.assertEqual(result['effective']['article_kind'],'article')
        self.assertEqual(result['quarantined_source_targets'][0]['raw_value'],INERT)
        self.assertNotIn('attribute caption',args[0]['main_text'])
        self.assertEqual(args,frozen);self.assertEqual(len(result['removed_references']),1)

    def test_valid_body_and_lead_siblings_survive(self):
        for sibling in ('<video src="https://cdn.example/real.mp4"></video>',f'<iframe src="{VIDEO}"></iframe>'):
            args=self.fx.fixture(article(sibling=sibling));r=media.compute(*args)
            self.assertEqual(r['status'],'effective_media_correction');self.assertEqual(r['effective']['article_kind'],'article_with_video')
            refs=json.loads(r['effective']['media_embeds']);self.assertEqual(len(refs),1)
            self.assertNotIn('<',refs[0]);self.assertEqual(len(json.loads(r['effective']['media_evidence'])),1)
        both=article().replace('A genuine short lead.',f'<iframe src="{VIDEO}"></iframe>')
        r=media.compute(*self.fx.fixture(both));self.assertEqual(r['status'],'effective_media_correction');self.assertIn(VIDEO,json.loads(r['effective']['media_embeds']))

    def test_unknown_or_incomplete_attribute_cannot_receive_quarantine(self):
        extra=['<iframe src="https://unknown.example/player"></iframe>','<video src="x"></video>',
               '<object data="x"></object>','<custom-player data-video="x"></custom-player>',
               '<div data-player="x"></div>','<div onload="run()"></div>',
               '<div style="behavior:expression(run())"></div>','<script>run()</script>']
        cases=[INERT.replace('</blockquote>',e+'</blockquote>') for e in extra]
        cases += [INERT[:-9],INERT+'unexplained text','<div>Unknown HTML</div>',INERT.replace('embed.js','other.js')]
        for raw in cases:
            with self.subTest(raw=raw):
                self.assertFalse(media._inert_instagram_attribute(raw))
                self.assertEqual(media.compute(*self.fx.fixture(article(raw)))['status'],'blocked_effective_media_review')

    def test_omitted_prose_wrong_identity_and_empty_article_still_block(self):
        for key,value in [('main_text','Omitted actual source prose'),('canonical_url','https://wrong.example/'),('title','Wrong title')]:
            args=list(self.fx.fixture(article()));args[0][key]=value;args[3]['fields_sha256']=media.w.fields_digest(args[0])
            self.assertEqual(media.compute(*args)['status'],'blocked_effective_media_review')
        page=html_page('').replace('<p>'+('All reported words remain in the body. '*8)+'</p>',markup_target())
        self.assertEqual(media.compute(*self.fx.fixture(page))['status'],'blocked_effective_media_review')
        # Invalid iframe/unknown malformed target must not slip through no-lead path.
        page=html_page('Lead.').replace('</div></article>','<iframe src="&lt;unknown&gt;"></iframe></div></article>')
        self.assertEqual(media.compute(*self.fx.fixture(page))['status'],'blocked_effective_media_review')

    def test_effective_save_readback_repetition_and_native_preservation(self):
        row,raw,response,record=self.fx.fixture(article());db=self.fx.persist(row,response,record)
        before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (db,self.fx.batch/'source.html',self.fx.root/'row_checks/SYNTHETIC.json')}
        policy=media.bound(self.fx.policy);plan={**self.fx.plan,'row_count':1,'batches':[{'sample_ids':['SYNTHETIC']}]}
        binding=media.assess(self.fx.root,plan,self.fx.batch,row,record,policy)
        self.assertEqual(binding,media.assess(self.fx.root,plan,self.fx.batch,row,record,policy))
        self.assertEqual(media.verify(binding)['result']['quarantined_source_targets'][0]['raw_value'],INERT)
        summary=media.summary(self.fx.root,plan,[record],policy)
        self.assertEqual(media.verify_summary(self.fx.root,plan,summary,policy)['correction_count'],1)
        self.assertEqual({p:hashlib.sha256(p.read_bytes()).hexdigest() for p in before},before)

    def test_actual_bound368888_only_four_fields_and_source_warning(self):
        selection=json.loads((DONOR/'reviews/plan_000065/checkpoint_00001600/selection_00001600.json').read_text())
        item=next(r for r in selection['selected_records'] if r['sample_id']=='TC5_368888')
        batch=Path(item['row_check']['path']).parent.parent/'batches'/item['batch_id']
        with sqlite3.connect((batch/'pilot.sqlite').as_uri()+'?mode=ro',uri=True) as db:
            payload=db.execute('SELECT payload_json FROM articles WHERE sample_id=?',('TC5_368888',)).fetchone()[0]
            row=json.loads(payload);response=json.loads(db.execute('SELECT response_json FROM fetch_attempts WHERE attempt_id=?',(row['attempt_id'],)).fetchone()[0])
        raw=Path(item['snapshot_path']).read_bytes();record=json.loads(Path(item['row_check']['path']).read_text())['record'];before=copy.deepcopy((row,response,record))
        result=media.compute(row,raw,response,record)
        self.assertEqual(result['status'],'effective_media_correction');self.assertEqual(set(result['changed_fields']),set(media.MEDIA_FIELDS))
        self.assertEqual(result['effective']['media_embeds'],'[]');self.assertEqual(result['effective']['media_evidence'],'[]')
        self.assertEqual(result['effective']['article_kind'],'article');self.assertEqual(result['source_media_warnings'],['source_html_in_media_url_attribute'])
        self.assertEqual(len(result['quarantined_source_targets'][0]['raw_value']),7141)
        self.assertEqual((row,response,record),before);self.assertEqual(hashlib.sha256(payload.encode()).hexdigest(),item['payload_sha256'])

if __name__=='__main__':unittest.main()

"""Bound effective-media evidence tests; native data are never rewritten."""
import copy
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawler_core import tiempo_lead_media as media
from crawler_core import tiempo_html as native
from crawler_core import tiempo_continuous_source as native_source

URL='https://www.tiempo.com.mx/local/unseen-supplement/'
VIDEO='https://www.youtube.com/embed/unseenVideo'
DONOR=Path('/Users/kevinfu/Library/CloudStorage/Dropbox/Media/data/00-newspaper_data/crawler/pilots/Kevin/Continuations/Remaining_Source_Encoding_Recovery_20261012')


def html_page(lead=None):
    if lead is None:lead=f'<iframe src="{VIDEO}"></iframe>'
    return ('<html><head><meta charset="utf-8"><link rel="canonical" href="'+URL+'"></head><body>'
            '<article id="article-post"><header><h1>Complete source headline</h1></header>'
            '<blockquote><p>'+lead+'</p>Por: <a class="m-r-sm">Ana</a> 01 Junio 2024 12:01</blockquote>'
            '<div class="complementos-container"><p>'+('All reported words remain in the body. '*8)+'</p></div></article></body></html>')


class LeadMediaSupplementTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'child';self.batch=self.root/'batches/batch_000001'
        self.batch.mkdir(parents=True);(self.root/'row_checks').mkdir()
        self.policy=self.root/'policy.json';self.policy.write_text('{"test_policy":true}\n')
        self.plan={'plan_sha256':'synthetic-plan'}

    def fixture(self,html=None):
        html=html if html is not None else html_page();raw=html.encode('utf-8')
        path=self.batch/'source.html';path.write_bytes(raw)
        row=native.tiempo_fields(html,url=URL)
        row.update(sample_id='SYNTHETIC',url=URL,final_url=URL,status=200,content_type='text/html; charset=utf-8',
                   snapshot_path='source.html',snapshot_sha256=hashlib.sha256(raw).hexdigest(),attempt_id='attempt-1',
                   qa_status='success',error=None,sample_metadata_json='{}')
        response={'status':200,'curl_exit_code':0,'error':None,'body_text_limit_exceeded':False,
                  'body_encoding':'utf-8','body_encoding_source':'http_charset','content_type':row['content_type'],'final_url':URL}
        record=native_source.diagnose(row,self.batch);record['critical_flags']=[]
        return row,raw,response,record

    def persist(self,row,response,record):
        dbpath=self.batch/'pilot.sqlite'
        with sqlite3.connect(dbpath) as db:
            db.execute('CREATE TABLE articles(sample_id TEXT PRIMARY KEY,payload_json TEXT)')
            db.execute('CREATE TABLE fetch_attempts(attempt_id TEXT PRIMARY KEY,sample_id TEXT,url TEXT,completed_at TEXT,response_json TEXT)')
            db.execute('INSERT INTO articles VALUES (?,?)',(row['sample_id'],json.dumps(row)))
            db.execute('INSERT INTO fetch_attempts VALUES (?,?,?,?,?)',(row['attempt_id'],row['sample_id'],row['url'],'2026-10-12T00:00:00Z',json.dumps(response)))
        (self.root/'row_checks'/(row['sample_id']+'.json')).write_text(json.dumps({'record':record}))
        return dbpath

    def test_actual436991_and_alias_only_four_media_fields_corrected(self):
        selection=json.loads((DONOR/'reviews/plan_000065/checkpoint_00000800/selection_00000800.json').read_text())
        for sid in ('TC5_436991','TC5_177742'):
            x=next(r for r in selection['snapshot']['rows'] if r['sample_id']==sid)
            batch=Path(x['row_check']['path']).parent.parent/'batches'/x['batch_id']
            with sqlite3.connect((batch/'pilot.sqlite').as_uri()+'?mode=ro',uri=True) as db:
                payload=db.execute('SELECT payload_json FROM articles WHERE sample_id=?',(sid,)).fetchone()[0]
                row=json.loads(payload);response=json.loads(db.execute('SELECT response_json FROM fetch_attempts WHERE attempt_id=?',(row['attempt_id'],)).fetchone()[0])
            raw=Path(x['snapshot_path']).read_bytes();record=json.loads(Path(x['row_check']['path']).read_text())['record']
            frozen=copy.deepcopy((row,response,record))
            result=media.compute(row,raw,response,record)
            self.assertEqual(result['status'],'effective_media_correction')
            self.assertEqual(result['added_references'],['https://www.youtube.com/embed/R8NeB10INDo'])
            self.assertEqual(set(result['changed_fields']),set(media.MEDIA_FIELDS))
            self.assertEqual(result['effective']['article_kind'],'article_with_video')
            self.assertEqual((row,response,record),frozen)
            self.assertEqual(hashlib.sha256(payload.encode()).hexdigest(),x['payload_sha256'])

    def test_no_lead_media_retains_every_native_media_field(self):
        row,raw,response,record=self.fixture(html_page('A short lead.'))
        result=media.compute(row,raw,response,record)
        self.assertEqual(result['status'],'no_effective_media_change')
        self.assertEqual(result['effective'],{k:row[k] for k in media.MEDIA_FIELDS})

    def test_unknown_dynamic_reference_and_missing_target_are_blockers(self):
        for lead in ('<iframe src="https://unknown.example/player"></iframe>',
                     '<iframe></iframe>',f'<iframe src="{VIDEO}" data-player="unknown"></iframe>',
                     f'<iframe src="{VIDEO}" onload="unknown()"></iframe>',
                     '<video src="javascript:unknown()"></video>', '<object data="unknown"></object>'):
            with self.subTest(lead=lead):
                args=self.fixture(html_page(lead));result=media.compute(*args)
                self.assertEqual(result['status'],'blocked_effective_media_review')
                self.assertTrue(result['technical_blockers'])

    def test_wrong_native_media_reference_is_not_silently_replaced(self):
        row,raw,response,record=self.fixture();row['media_embeds']='["https://www.youtube.com/embed/wrong"]'
        record['fields_sha256']=native_source.fields_digest(row)
        self.assertIn('effective_media_independent_reference_mismatch',media.compute(row,raw,response,record)['technical_blockers'])

    def test_wrong_identity_title_date_and_omitted_prose_remain_blocked(self):
        for key,value in [('canonical_url','https://www.tiempo.com.mx/local/wrong/'),('title','Wrong headline'),
                          ('date_published','2024-06-02T12:01:00'),('main_text','Dropped actual prose.')]:
            row,raw,response,record=self.fixture();row[key]=value
            record['fields_sha256']=native_source.fields_digest(row)
            with self.subTest(key=key):
                result=media.compute(row,raw,response,record)
                self.assertEqual(result['status'],'blocked_effective_media_review')
                self.assertTrue(any(reason.startswith('effective_media_would_change_nonmedia_fields:') for reason in result['technical_blockers']))

    def test_raw_response_decode_and_partial_transport_binding(self):
        row,raw,response,record=self.fixture()
        self.assertTrue(media.compute(row,raw+b' ',response,record)['technical_blockers'])
        for changes in ({'curl_exit_code':28},{'body_text_limit_exceeded':True},{'final_url':'https://wrong.example/'},
                        {'body_encoding':'unknown_codec'},{'body_encoding':None}):
            with self.subTest(changes=changes):
                self.assertTrue(media.compute(row,raw,{**response,**changes},record)['technical_blockers'])

    def test_inconsistent_response_error_charset_and_record_bindings_block(self):
        row,raw,response,record=self.fixture()
        for changes in ({'error':'timeout'},{'content_type':'text/html; charset=windows-1252'},
                        {'body_encoding_source':'guessed'}):
            with self.subTest(changes=changes):
                self.assertTrue(media.compute(row,raw,{**response,**changes},record)['technical_blockers'])
        for changes in ({'sample_id':'OTHER'},{'snapshot_sha256':'wrong'},{'fields_sha256':'wrong'}):
            with self.subTest(changes=changes):
                self.assertTrue(media.compute(row,raw,response,{**record,**changes})['technical_blockers'])

    def test_native_critical_failure_never_gets_media_exemption(self):
        row,raw,response,record=self.fixture();record['critical_flags']=['identity_mismatch']
        self.assertIn('effective_media_cannot_correct_native_critical_failure',media.compute(row,raw,response,record)['technical_blockers'])

    def test_assess_verify_repeat_and_summary_readback_preserve_native(self):
        row,raw,response,record=self.fixture();dbpath=self.persist(row,response,record)
        before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (dbpath,self.batch/'source.html',self.root/'row_checks/SYNTHETIC.json')}
        binding=media.assess(self.root,self.plan,self.batch,row,record,media.bound(self.policy))
        self.assertEqual(media.assess(self.root,self.plan,self.batch,row,record,media.bound(self.policy)),binding)
        doc=media.verify(binding)
        self.assertFalse(doc['native_rows_modified']);self.assertFalse(doc['human_approval']);self.assertFalse(doc['article_acceptance'])
        self.assertEqual(doc['manual_review_status'],'not_reviewed')
        summary=media.summary(self.root,self.plan,[record],media.bound(self.policy))
        saved=json.loads(Path(summary['path']).read_text());self.assertEqual(saved['correction_count'],1)
        export=json.loads(Path(saved['effective_media_export']['path']).read_text());self.assertEqual(len(export['corrections']),1)
        self.assertEqual({p:hashlib.sha256(p.read_bytes()).hexdigest() for p in before},before)

    def test_verify_rejects_tampered_effective_field_and_human_approval(self):
        row,raw,response,record=self.fixture();self.persist(row,response,record)
        binding=media.assess(self.root,self.plan,self.batch,row,record,media.bound(self.policy));path=Path(binding['path'])
        original=json.loads(path.read_text())
        for mutation in ('effective','human'):
            doc=copy.deepcopy(original)
            if mutation=='effective':doc['result']['effective']['media_embeds']='[]'
            else:doc['human_approval']=True
            path.write_text(json.dumps(doc))
            with self.assertRaises(ValueError):media.verify(media.bound(path))
        path.write_text(json.dumps(original))

    def test_verify_rejects_unfinished_attempt_native_payload_or_policy_change(self):
        row,raw,response,record=self.fixture();dbpath=self.persist(row,response,record)
        binding=media.assess(self.root,self.plan,self.batch,row,record,media.bound(self.policy))
        with sqlite3.connect(dbpath) as db:db.execute('UPDATE fetch_attempts SET completed_at=NULL')
        with self.assertRaises(ValueError):media.verify(binding)
        with sqlite3.connect(dbpath) as db:db.execute('UPDATE fetch_attempts SET completed_at=?',('2026-10-12T00:00:00Z',))
        self.policy.write_text('{"test_policy":false}')
        with self.assertRaises(ValueError):media.verify(binding)


if __name__=='__main__':unittest.main()

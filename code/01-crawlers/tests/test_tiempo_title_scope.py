"""Kevin: focused offline title-role tests; synthetic readings are not production."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

from bs4 import BeautifulSoup
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crawler_core import tiempo_title_scope as title
from crawler_core import tiempo_html as native
from crawler_core import tiempo_continuous_source as source
from crawler_core import tiempo_source_classification_policy as policy
from crawler_core import tiempo_continuous_v5 as w

DONOR=Path('/Users/kevinfu/Library/CloudStorage/Dropbox/Media/data/00-newspaper_data/crawler/pilots/Kevin/Continuations/Remaining_Media_URL_Recovery_20261013')
NOTES=DONOR/'diagnostics/Stopped107_Source_Notes.json'


def actual_case(index=0):
    note=json.loads(NOTES.read_text())['records'][index]
    with sqlite3.connect(Path(note['database_path']).as_uri()+'?mode=ro',uri=True) as db:
        payload=db.execute('SELECT payload_json FROM articles WHERE sample_id=?',(note['sample_id'],)).fetchone()[0]
        row=json.loads(payload)
        response=json.loads(db.execute('SELECT response_json FROM fetch_attempts WHERE attempt_id=?',(row['attempt_id'],)).fetchone()[0])
    return row,Path(note['raw_path']).read_bytes(),response,json.loads(Path(note['row_check_path']).read_text())['record'],note,payload


class TitleScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'child';self.batch=self.root/'batches/batch_000001'
        self.batch.mkdir(parents=True);(self.root/'row_checks').mkdir()

    def fixture(self,mutate=lambda s:s):
        old,raw,response,_,note,_=actual_case()
        text=mutate(raw.decode());raw=text.encode();(self.batch/'response.html').write_bytes(raw)
        row={**old,**native.tiempo_fields(text,url=old['final_url'])}
        row.update(snapshot_path='response.html',snapshot_sha256=hashlib.sha256(raw).hexdigest())
        row.update(qa_status='error' if not row['title'] else 'success',error='missing_title' if not row['title'] else None)
        record=source.diagnose(row,self.batch);record.update(critical_flags=[],collection_outcome='article_candidate',
            unexplained_flags=[x for x in record['automatic_flags'] if x not in title.encoding.RESEARCH_FLAGS],unexplained_families=['other_unexplained'])
        check=self.root/'row_checks'/(row['sample_id']+'.json');check.write_text(json.dumps({'record':record}))
        payload=json.dumps(row);note={**note,'request_url':row['url'],'raw_sha256':row['snapshot_sha256'],
            'payload_sha256':hashlib.sha256(payload.encode()).hexdigest(),'row_check_sha256':title._binding(check)['sha256'],
            'body_h1_count':len(BeautifulSoup(text,'html.parser').select('.complementos-container h1')),
            'actual_ai_read_note':'SYNTHETIC TEST ONLY: crafted paragraph-role fixture; not an actual production source reading.'}
        evidence={'schema':'tiempo-focused-stopped-source-reading-v1','author':'Kevin','synthetic_fixture':True,
            'actual_ai_read':True,'human_approval':False,'native_review_state_changed':False,'records':[note]}
        path=self.root/'synthetic_reading.json';path.write_text(json.dumps(evidence))
        return row,raw,response,record,note,payload,title._binding(path)

    def decide(self,args):
        row,raw,response,record,note,payload,binding=args
        return title.classify(row,raw,response,record,self.batch,role_evidence=binding,
            payload_sha256=hashlib.sha256(payload.encode()).hexdigest(),row_check_sha256=note['row_check_sha256'])

    def test_three_bound_real_cases_reuse_prior_roles_native_unchanged(self):
        for index in range(3):
            row,raw,response,record,note,payload=actual_case(index);before=copy.deepcopy((row,response,record))
            got=title.classify(row,raw,response,record,Path(note['database_path']).parent,role_evidence=title._binding(NOTES),
                payload_sha256=note['payload_sha256'],row_check_sha256=note['row_check_sha256'])
            self.assertTrue(got['matched'],got['rejection_reasons'])
            self.assertEqual(got['evidence']['explained_title_flags'],['unexplained_result_error'])
            self.assertEqual(len(got['evidence']['removed_body_h1_channels']),note['body_h1_count'])
            self.assertEqual(before,(row,response,record));self.assertIsNone(row['title'])

    def test_structure_and_jsonld_never_replace_actual_role_evidence(self):
        args=list(self.fixture());args[-1]=None
        got=self.decide(args);self.assertFalse(got['matched']);self.assertIn('no_matching_actual_source_role_reading',got['rejection_reasons'])

    def test_only_body_h1_headline_stays_candidate(self):
        args=self.fixture(lambda s:s.replace('<h1 dir="ltr">','<h1 itemprop="headline">',1))
        got=self.decide(args);self.assertFalse(got['matched'])
        self.assertTrue(got['evidence']['roles']['explicit_headline_nodes'])
        soup=BeautifulSoup('<article id="article-post"><div class="complementos-container"><h1>Only real title</h1><p>Body.</p></div></article>','html.parser')
        self.assertEqual(title.title_roles(soup)['unresolved_or_title_h1'][0]['text'],'Only real title')

    def test_real_header_and_prose_roles_coexist(self):
        args=self.fixture(lambda s:__import__('re').sub(r'(<header>.*?<h1[^>]*>)\s*(</h1>)',r'\1Actual headline\2',s,count=1,flags=__import__('re').S))
        self.assertEqual(args[0]['title'],'Actual headline')
        roles=title.title_roles(BeautifulSoup(args[1].decode(),'html.parser'),reviewed=args[4])
        self.assertEqual([r['text'] for r in roles['unresolved_or_title_h1']],['Actual headline'])
        self.assertEqual(len(roles['reviewed_body_h1_indices']),5)
        self.assertFalse(self.decide(args)['matched'])

    def test_title_metadata_conflict_still_warns(self):
        def change(s):
            import re
            s=re.sub(r'(<header>.*?<h1[^>]*>)\s*(</h1>)',r'\1Actual headline\2',s,count=1,flags=re.S)
            return s.replace('property="og:title" content=""','property="og:title" content="Conflicting headline"',1)
        args=self.fixture(change)
        self.assertIn('source_title_metadata_disagreement',args[3]['automatic_flags'])
        self.assertFalse(self.decide(args)['matched'])

    def test_unknown_roles_dynamic_partial_omission_identity_and_evidence_reject(self):
        for mutate in (lambda s:s.replace('<h1 dir="ltr">','<h1 dir="ltr" role="heading">',1),
                       lambda s:s.replace('<h1 dir="ltr">','<h1 dir="ltr" class="headline">',1),
                       lambda s:s.replace('<h1 dir="ltr">','<h1 dir="ltr" data-title="unknown">',1),
                       lambda s:s.replace('<h1 dir="ltr">','<h1 dir="ltr"><custom-player></custom-player>',1),
                       lambda s:s.rstrip()[:-7]):
            self.assertFalse(self.decide(self.fixture(mutate))['matched'])
        for key,val in [('main_text','Dropped source paragraphs.'),('canonical_url','https://www.tiempo.com.mx/local/wrong/'),
                        ('date_published','2020-01-01T00:00:00')]:
            args=list(self.fixture());args[0][key]=val;args[3]['fields_sha256']=source.fields_digest(args[0])
            self.assertFalse(self.decide(args)['matched'])
        args=list(self.fixture());args[2]['curl_exit_code']=7;self.assertFalse(self.decide(args)['matched'])
        args=list(self.fixture());args[4]['row_check_sha256']='wrong';self.assertFalse(self.decide(args)['matched'])

    def test_policy_save_readback_reuse_keeps_native_and_distinguishes_correction(self):
        args=self.fixture();row,raw,response,record,note,payload,binding=args
        dbpath=self.batch/'pilot.sqlite'
        with sqlite3.connect(dbpath) as db:
            db.execute('CREATE TABLE articles(sample_id TEXT PRIMARY KEY,payload_json TEXT)')
            db.execute('CREATE TABLE fetch_attempts(attempt_id TEXT PRIMARY KEY,sample_id TEXT,url TEXT,completed_at TEXT,response_json TEXT)')
            db.execute('INSERT INTO articles VALUES (?,?)',(row['sample_id'],payload))
            db.execute('INSERT INTO fetch_attempts VALUES (?,?,?,?,?)',(row['attempt_id'],row['sample_id'],row['url'],'closed',json.dumps(response)))
        frozen=title._binding(dbpath);pb=policy.create_policy(self.root,[66],True,title_role_evidence=binding)
        plan={'plan_sha256':'synthetic-test','program_sha256':w.program_hashes()}
        saved=policy.assess(self.root,plan,self.batch,row,record,pb)
        proof=policy.verify_decision(saved,record,pb)
        self.assertEqual(proof['correction_kind'],title.CLASSIFICATION)
        self.assertEqual(proof['effective_outcome'],'article_candidate');self.assertIsNone(proof['source_gap_kind'])
        self.assertEqual(saved,policy.assess(self.root,plan,self.batch,row,record,pb))
        self.assertEqual(frozen,title._binding(dbpath))
        self.assertEqual(policy.trigger([record],{row['sample_id']:saved},pb,row,{}),None)
        doc=json.loads(Path(saved['path']).read_text());doc['effective_explained_flags']=[]
        Path(saved['path']).write_text(json.dumps(doc))
        with self.assertRaises(ValueError):policy.verify_decision(title._binding(saved['path']),record,pb)

if __name__=='__main__':unittest.main()

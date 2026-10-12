"""Offline, isolated tests; saved cases are opt-in local inputs, never downloads."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crawler_core import tiempo_source_encoding as encoding
from crawler_core import tiempo_source_classification_policy as policy
from crawler_core import tiempo_continuous_source as source
from crawler_core import tiempo_continuous_v5 as w

DONOR = Path('/Users/kevinfu/Library/CloudStorage/Dropbox/Media/data/00-newspaper_data/crawler/pilots/Kevin/Continuations/Remaining_Source_Image_Reference_20261012')
CHILD = DONOR/'Media/data/00-newspaper_data/crawler/pilots/Kevin/tiempo_continuous_v5/remaining_plan_000065'


def saved_case(position=659):
    batch=CHILD/'batches'/f'batch_{(position-1)//80+1:06d}'
    if not (batch/'pilot.sqlite').is_file():raise unittest.SkipTest('Bound local saved-source fixture unavailable')
    with sqlite3.connect((batch/'pilot.sqlite').as_uri()+'?mode=ro',uri=True) as db:
        row=json.loads(db.execute('SELECT payload_json FROM articles ORDER BY ordinal').fetchall()[(position-1)%80][0])
        response=json.loads(db.execute('SELECT response_json FROM fetch_attempts WHERE attempt_id=?',(row['attempt_id'],)).fetchone()[0])
    raw=(batch/row['snapshot_path']).read_bytes()
    check=w.load(CHILD/'row_checks'/(row['sample_id']+'.json'))['record']
    return row,raw,response,check,batch


def encoding_response(url,timeout,**kwargs):
    """Natural byte-detector mismatch at an unseen URL; no injected flags/HTTP.

    The unchanged saved sports HTML is read only into memory, with its article
    slug and publication slots replaced. Embedded quotations retain their own
    original dates; no permanent raw fixture file is created by this function.
    """
    row,raw,response,_,_=saved_case()
    old_slug=row['url'].rstrip('/').split('/')[-1];slug=url.rstrip('/').split('/')[-1]
    text=raw.decode('utf-8').replace(old_slug,slug)
    text=text.replace('2018-08-15T16:01:29','2024-06-01T12:01:33')
    text=text.replace('15 Agosto 2018','01 Junio 2024').replace('16:01','12:01').replace('16 01','12 01')
    return {**response,'final_url':url,'text':text}


class EncodingCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.batch=self.root/'batches'/'batch_000001';self.batch.mkdir(parents=True)
        self.row,self.raw,self.response,self.original_check,_=saved_case()

    def materialize(self,raw=None,row=None,response=None):
        row=copy.deepcopy(self.row if row is None else row)
        raw=self.raw if raw is None else raw
        response=copy.deepcopy(self.response if response is None else response)
        row['snapshot_path']='response.html';row['snapshot_sha256']=hashlib.sha256(raw).hexdigest()
        (self.batch/'response.html').write_bytes(raw)
        check=source.diagnose(row,self.batch)
        check.update(critical_flags=[],collection_outcome='article_candidate',
                     unexplained_flags=sorted(set(check['automatic_flags'])-encoding.RESEARCH_FLAGS),
                     unexplained_families=['body_or_media'],duplicate_relations=[])
        return row,raw,response,check

    def decide(self,*args):
        return encoding.classify_encoding_disagreement(*args,self.batch)

    def test_three_actual_saved_positives_no_global_patch_or_mutation(self):
        original_soup=source.BeautifulSoup
        for position in [595,629,659]:
            row,raw,response,check,batch=saved_case(position);before=copy.deepcopy((row,response,check))
            decision=encoding.classify_encoding_disagreement(row,raw,response,check,batch)
            self.assertTrue(decision['matched'],(position,decision))
            self.assertEqual(decision['evidence']['utf8_automatic_flags'],[])
            self.assertFalse(decision['evidence']['image_pixels_reviewed'])
            self.assertEqual(before,(row,response,check));self.assertIs(source.BeautifulSoup,original_soup)

    def test_transport_charset_completeness_and_bindings_reject(self):
        base=self.materialize()
        mutations=[{'status':500},{'error':'timeout'},{'curl_exit_code':7},
                   {'body_text_limit_exceeded':True},{'body_encoding':'latin1'},
                   {'body_encoding_source':'guessed'},{'content_type':'text/html; charset=latin1'},
                   {'final_url':'https://www.tiempo.com.mx/noticia/wrong/'}]
        for delta in mutations:
            response={**base[2],**delta};self.assertFalse(self.decide(base[0],base[1],response,base[3])['matched'],delta)
        bad=copy.deepcopy(base[3]);bad['fields_sha256']='changed';self.assertFalse(self.decide(*base[:3],bad)['matched'])
        for raw in [self.raw.rstrip()[:-7],self.raw.replace(b'<meta charset="utf-8">',b'<meta charset="latin1">'),
                    self.raw.replace(b'<meta charset="utf-8">',b''),self.raw+b'\xff']:
            if raw.endswith(b'\xff'):
                # Strict source diagnosis cannot even parse invalid input as a correction.
                check=copy.deepcopy(base[3]);row=copy.deepcopy(base[0]);row['snapshot_sha256']=hashlib.sha256(raw).hexdigest();check['snapshot_sha256']=row['snapshot_sha256'];check['fields_sha256']=source.fields_digest(row)
                self.assertFalse(self.decide(row,raw,base[2],check)['matched'])
            else:self.assertFalse(self.decide(*self.materialize(raw))['matched'])

    def test_omission_identity_date_title_and_media_fail_closed(self):
        for key,value in [('main_text','An omitted article body'),('summary','Wrong summary'),
                          ('authors','Wrong Author'),('title','Wrong headline'),
                          ('canonical_url','https://www.tiempo.com.mx/deportes/wrong/'),
                          ('date_published','2018-08-16T16:01:29'),('media_embeds','[]')]:
            row={**self.row,key:value};self.assertFalse(self.decide(*self.materialize(row=row))['matched'],key)
        raw=self.raw.replace(b'"@id": "atletico_de_madrid_supercampeon_supercopa_de_europa_derroto_real_madrid_42_videos_goles_diego_costa"',b'"@id": "wrong_identity"')
        self.assertNotEqual(raw,self.raw);self.assertFalse(self.decide(*self.materialize(raw))['matched'])
        raw=self.raw.replace('"name": "Redacción"'.encode(),b'"name": "Wrong Author"')
        self.assertNotEqual(raw,self.raw);self.assertFalse(self.decide(*self.materialize(raw))['matched'])

    def test_unknown_dynamic_structures_even_when_native_output_matches(self):
        inserts=['<iframe src="https://unknown.invalid/media"></iframe>',
                 '<object data="unknown"></object>','<embed src="unknown">',
                 '<script>loadUnknownNews()</script>','<div data-src="unknown"></div>',
                 '<canvas></canvas>','<news-widget></news-widget>',
                 '<div onclick="loadUnknownArticleMedia()"></div>',
                 '<div style="background-image:url(unknown)"></div>']
        for fragment in inserts:
            for marker in [b'<p class="lead">',b'<div class="complementos-container img-responsive complemento-img">']:
                raw=self.raw.replace(marker,fragment.encode()+marker,1)
                self.assertNotEqual(raw,self.raw);self.assertFalse(self.decide(*self.materialize(raw))['matched'],fragment)
        for old,new in [(b'<head>',b'<head><meta http-equiv="refresh" content="0;url=https://unknown.invalid">'),
                        (b'src="https://platform.twitter.com/widgets.js"',b'onload="unknownLoad()" src="https://platform.twitter.com/widgets.js"')]:
            raw=self.raw.replace(old,new,1);self.assertNotEqual(raw,self.raw);self.assertFalse(self.decide(*self.materialize(raw))['matched'])

    def test_literal_dom_entity_disagreement_not_double_decoded(self):
        raw=self.raw.replace('content="¡Supercampeones!'.encode(),'content="&amp;#161;Supercampeones!'.encode(),1)
        self.assertNotEqual(raw,self.raw);self.assertFalse(self.decide(*self.materialize(raw))['matched'])

    def test_unknown_native_flag_and_critical_status_remain_blocked(self):
        base=self.materialize()
        for key in ['automatic_flags','unexplained_flags','critical_flags']:
            check=copy.deepcopy(base[3]);check[key]=[*check.get(key,[]),'unknown_actual_problem']
            self.assertFalse(self.decide(*base[:3],check)['matched'],key)

    def persist(self,args):
        row,raw,response,record=args
        checks=self.root/'row_checks';checks.mkdir(exist_ok=True)
        w.write(checks,row['sample_id']+'.json',{'record':record})
        with sqlite3.connect(self.batch/'pilot.sqlite') as db:
            db.execute('CREATE TABLE articles(sample_id TEXT,payload_json TEXT)')
            db.execute('CREATE TABLE fetch_attempts(attempt_id TEXT,sample_id TEXT,url TEXT,completed_at TEXT,response_json TEXT)')
            db.execute('INSERT INTO articles VALUES (?,?)',(row['sample_id'],json.dumps(row)))
            db.execute('INSERT INTO fetch_attempts VALUES (?,?,?,?,?)',(row['attempt_id'],row['sample_id'],row['url'],'closed',json.dumps(response)))
        binding=policy.create_policy(self.root,[2],True)
        plan={'plan_sha256':'isolated-test-plan'}
        decision=policy.assess(self.root,plan,self.batch,row,record,binding)
        return row,record,binding,plan,decision

    def test_policy_persists_reads_and_counts_correction_as_article_candidate(self):
        row,record,binding,plan,decision=self.persist(self.materialize())
        before=copy.deepcopy(record);doc=policy.verify_decision(decision,record,binding)
        self.assertTrue(doc['decision']['matched']);self.assertTrue(doc['article_candidate'])
        self.assertIsNone(doc['source_gap_kind']);self.assertEqual(doc['correction_kind'],encoding.CLASSIFICATION)
        self.assertEqual(doc['effective_outcome'],'article_candidate');self.assertFalse(doc['article_acceptance'])
        self.assertEqual(policy.assess(self.root,plan,self.batch,row,record,binding),decision)
        self.assertIsNone(policy.trigger([record],{row['sample_id']:decision},binding,row,{}))
        self.assertEqual(record,before)
        sb=policy.summary(self.root,plan,{row['sample_id']:decision},[record],binding);summary=w.load(sb['path'])
        self.assertEqual(summary['classified_source_gap_count'],0);self.assertEqual(summary['classified_encoding_correction_count'],1)
        for key,value in [('correction_kind','wrong'),('source_gap_kind','source_unavailable_body_in_saved_response'),('effective_outcome','source_unavailable')]:
            modified={**doc,key:value};candidate=self.root/f'tampered_{key}.json';w.write(self.root,candidate.name,modified)
            with self.assertRaisesRegex(ValueError,'outcome/status'):
                policy.verify_decision(policy._binding(candidate),record,binding)

    def test_correction_does_not_clear_other_history_and_actual_gate_is_separate(self):
        row,record,binding,_,decision=self.persist(self.materialize())
        def unknown(sid):return {'sample_id':sid,'automatic_flags':['unknown'], 'unexplained_flags':['unknown'],
            'unexplained_families':['other_unexplained'],'critical_flags':[]}
        a,b,c=unknown('one'),unknown('two'),unknown('three')
        self.assertEqual(policy.trigger([a,record,b,c],{row['sample_id']:decision},binding,{},{}),'three_unexplained_rows_in_rolling80')
        self.assertFalse(any(p.name.startswith('selection') or p.name=='reviewer_odd.json' for p in self.root.rglob('*')))
        critical=unknown('critical');critical['critical_flags']=['identity_error']
        self.assertEqual(policy.trigger([record,critical],{row['sample_id']:decision},binding,{},{}),'critical_source_or_access_failure')


if __name__=='__main__':unittest.main()

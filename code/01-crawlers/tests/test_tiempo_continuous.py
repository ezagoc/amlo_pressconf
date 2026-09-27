"""Offline tests with synthetic articles, real pilot storage and independent checks."""
import contextlib,csv,io,json,sqlite3,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import pandas as pd
from bs4 import BeautifulSoup
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crawler_core import tiempo_continuous as c,tiempo_continuous_source as source,tiempo_pilot as pilot
from crawler_core.tiempo_review import fields_digest


def page(url,*,title='Article',body_extra='',date='2024-06-01T12:01:33'):
    slug=url.rstrip('/').split('/')[-1];body=('Report '+slug+' describes the public event with all details preserved. ')*5
    ld={'@type':'NewsArticle','headline':title,'datePublished':date}
    return f'''<html><head><title>{title}</title><link rel="canonical" href="{url}"><meta property="og:title" content="{title}"><script type="application/ld+json">{json.dumps(ld)}</script></head><body><article id="article-post"><header><h1>{title}</h1></header><blockquote><p>Summary {slug}.</p>Por: <a class="m-r-sm">Kevin Fixture</a> 01 Junio 2024 12:01</blockquote><div class="complementos-container"><p>{body}</p>{body_extra}</div></article></body></html>'''
def response(url,timeout,**kwargs):return {'status':200,'final_url':url,'content_type':'text/html','error':None,'text':page(url)}
def writecsv(p,rows):p.write_bytes(c.csvbytes(list(rows[0]),rows))
def candidate(i):
    url=f'https://www.tiempo.com.mx/local/new-{i}/'
    return {'sample_id':f'TC_TEST_{i:06d}','url':url,'url_key':c.normalize_url(url),'expected_year':'2024','selection_reason':'Offline synthetic fixture','expected_kind':'article_candidate','identity_class':'new_urls','discovery_scope':'target_2018_2025','queue_class':'new_urls','discovery_date_status':'consistent','baseline_protected':'0','discovery_day':'2024-06-01','discovery_days_json':'["2024-06-01"]','discovery_dates_json':'["2024-06-01T12:01:33"]'}
class Clock:
    def __init__(self):self.t=100.;self.waits=[]
    def now(self):return self.t
    def sleep(self,seconds):self.waits.append(seconds);self.t+=seconds

IG_POST='https://www.instagram.com/p/Bvmpt-kANgB/'
IG_STYLE='color: #c9c8cd; font-family: Arial,sans-serif; font-size: 14px; line-height: 17px; text-overflow: ellipsis; white-space: nowrap;'
def timed_instagram(*,profile=True,word='de'):
    label='Una publicación compartida '+word+' Suelta la Sopa (@sueltalasopatv)'
    attribution=('Una publicación compartida '+word+' <a href="https://www.instagram.com/sueltalasopatv/">Suelta la Sopa</a> (@sueltalasopatv)') if profile else ('<a href="'+IG_POST+'">'+label+'</a>')
    footer='<p style="'+IG_STYLE+'">'+attribution+' el <time datetime="2019-03-29T19:28:04+00:00">29 Mar, 2019 a las 12:28 PDT</time></p>'
    return '<blockquote class="instagram-media" data-instgrm-permalink="'+IG_POST+'"><p>REAL CAPTION stays.</p>'+footer+'</blockquote>'

class IndependentInstagramUiTests(unittest.TestCase):
    def test_only_recognized_timed_ui_removed_caption_stays(self):
        for profile in [False,True]:
            for word in ['por','de']:
                doc=BeautifulSoup(timed_instagram(profile=profile,word=word),'html.parser')
                removed=source.remove_known_instagram_ui(doc)
                self.assertEqual([x['reason'] for x in removed],['instagram_timed_shared_post_ui'])
                self.assertEqual(doc.get_text(' ',strip=True),'REAL CAPTION stays.')
                self.assertEqual(doc.blockquote['data-instgrm-permalink'],IG_POST)
    def test_old_12hour_clock_without_meridiem_is_ui_only(self):
        for stamp,display in [('2019-03-30T01:28:04+00:00','29 Mar, 2019 a las 6:28 PDT'),
                              ('2019-03-30T07:28:04+00:00','30 Mar, 2019 a las 12:28 PDT')]:
            raw=timed_instagram().replace('2019-03-29T19:28:04+00:00',stamp).replace('29 Mar, 2019 a las 12:28 PDT',display)
            doc=BeautifulSoup(raw,'html.parser');self.assertEqual(len(source.remove_known_instagram_ui(doc)),1)
            wrong=BeautifulSoup(raw.replace('Mar, 2019','Mar, 2020'),'html.parser')
            self.assertEqual(source.remove_known_instagram_ui(wrong),[])
    def test_wrong_link_extra_prose_date_or_style_stays_visible(self):
        cases=[timed_instagram().replace('/sueltalasopatv/','/unrelated/'),
               timed_instagram(profile=False).replace('href="'+IG_POST,'href="https://www.instagram.com/p/OTHER/'),
               timed_instagram().replace('</time>','</time> Additional news statement.'),
               timed_instagram().replace('12:28 PDT','12:29 PDT'),
               timed_instagram().replace('2019-03-29T19:28:04+00:00','invalid'),
               timed_instagram().replace('font-size: 14px','font-size: 16px'),
               timed_instagram().replace('color: #c9c8cd','color: #000'),
               timed_instagram().replace('color: #c9c8cd','color: #c9c8cd00'),
               timed_instagram().replace('/sueltalasopatv/','/sueltalasopatv/#news'),
               timed_instagram().replace('<time ','<span><time ').replace('</time>','</time></span>')]
        for raw in cases:
            with self.subTest(raw=raw):
                doc=BeautifulSoup(raw,'html.parser');before=doc.get_text(' ',strip=True)
                self.assertEqual(source.remove_known_instagram_ui(doc),[])
                self.assertEqual(doc.get_text(' ',strip=True),before)
    def test_matching_words_outside_instagram_not_removed(self):
        doc=BeautifulSoup(timed_instagram().replace('class="instagram-media"','class="news-quote"'),'html.parser')
        self.assertEqual(source.remove_known_instagram_ui(doc),[])
        self.assertIn('Una publicación compartida',doc.get_text())
    def test_existing_same_post_and_view_ui_are_explicit(self):
        doc=BeautifulSoup('<blockquote class="instagram-media" data-instgrm-permalink="'+IG_POST+'"><p>REAL CAPTION stays.</p><div style="padding-top:8px"><div style="color:#3897f0;font-family:Arial">Ver esta publicación en Instagram</div></div><p style="'+IG_STYLE+'"><a href="'+IG_POST+'">Una publicación compartida de Name (@name)</a></p></blockquote>','html.parser')
        self.assertEqual([r['reason'] for r in source.remove_known_instagram_ui(doc)],['instagram_view_post_ui','instagram_shared_post_ui'])
        self.assertEqual(doc.get_text(' ',strip=True),'REAL CAPTION stays.')

class ContinuousTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name);self.media=self.base/'Media';self.root=self.media/'data/00-newspaper_data/crawler/pilots/Kevin/tiempo_continuous/testplan';self.clock=Clock()
        self.example=self.media/'data/00-newspaper_data/crawler/pilots/fixture_review';self.example.mkdir(parents=True);(self.example/'Kevin_NOTE.md').write_text('# Kevin synthetic offline review fixture\n')
        self.seedinput=self.base/'seed.csv';seed=[candidate(99901),candidate(99902)];seed[0]['sample_id']='SEED1';seed[1]['sample_id']='UNREVIEWED';writecsv(self.seedinput,seed)
        with contextlib.redirect_stdout(io.StringIO()):pilot.run_pilot(self.seedinput,self.example,self.media,pause_seconds=0,fetcher=response)
        with sqlite3.connect((self.example/'pilot.sqlite').as_uri()+'?mode=ro',uri=True) as db:self.seedrows=[json.loads(x[0]) for x in db.execute('SELECT payload_json FROM articles ORDER BY ordinal')]
        row=self.seedrows[0];ann={'sample_id':row['sample_id'],'snapshot_sha256':row['snapshot_sha256'],'fields_sha256':fields_digest(row),'reviewer':'Kevin','reviewed_at':'2026-09-26T12:00:00-04:00','review_result':'PASS','source_quality_issue':None,'review_note':'Synthetic fixture expected text and fields checked in offline test.'};(self.example/'review_annotations.json').write_text(json.dumps({'format_version':1,'annotations':[ann]}))
        self.registry_path=self.base/'registry.json';self.registry=source.build_registry([self.example],self.registry_path);self.exclusions=[]
        for role,n in c.REQUIRED_EXCLUSIONS.items():
            p=self.base/(role+'.csv');writecsv(p,[{'sample_id':f'E_{role}_{i}','url':f'https://www.tiempo.com.mx/local/excluded-{role}-{i}/'} for i in range(n)]);self.exclusions.append({'role':role,'path':str(p),'sha256':c.sha_file(p)})
    def freeze(self,n=2,budget=None,**kwargs):
        self.input=self.base/'queue.csv';rows=[candidate(i) for i in range(n)];writecsv(self.input,rows)
        self.queue_db=self.base/('original_'+self.root.name+'.sqlite')
        if not self.queue_db.exists():
            with sqlite3.connect(self.queue_db) as db:
                columns=[k for k in rows[0] if k not in {'sample_id','selection_reason','expected_year','expected_kind'}]
                db.execute('CREATE TABLE candidates ('+', '.join(k+' TEXT' for k in columns)+')')
                db.executemany('INSERT INTO candidates VALUES ('+','.join('?' for _ in columns)+')',[[r[k] for k in columns] for r in rows])
        self.plan=c.freeze(self.input,self.root,self.media,self.registry_path,c.sha_file(self.registry_path),self.exclusions,start='2024-06-01',end='2024-06-02',max_fetch_calls=budget or n,queue_db_path=self.queue_db,queue_db_sha256=c.sha_file(self.queue_db),min_free_bytes=1,**kwargs);return self.plan
    def run(self,*args,**kwargs):
        if args or 'result' in kwargs:return super().run(*args,**kwargs)
        options={'max_batches':10,'fetcher':Mock(side_effect=response),'clock':self.clock.now,'sleep':self.clock.sleep};options.update(kwargs)
        with contextlib.redirect_stdout(io.StringIO()):return c.run(self.root,self.media,**options)
    def test_registry_only_real_bound_review_and_no_unread(self):
        self.assertEqual([r['sample_id'] for r in self.registry['exemplars']],['SEED1']);self.assertEqual(self.registry['skipped']['not_current_passing_review'],1)
        p=self.example/'review_annotations.json';j=json.loads(p.read_text());j['annotations'][0]['fields_sha256']='0'*64;p.write_text(json.dumps(j))
        with self.assertRaises(ValueError):source.load_registry(self.registry_path,c.sha_file(self.registry_path))
    def test_no_network_flag_by_default(self):
        self.freeze()
        with self.assertRaisesRegex(ValueError,'network execution'):c.run(self.root,self.media,max_batches=1)
    def test_finite_collection_keeps_not_reviewed_no_approvals(self):
        self.freeze();fetch=Mock(side_effect=response);state=self.run(fetcher=fetch);self.assertEqual(state['status'],c.PENDING);self.assertTrue(state['collection_inputs_finished']);self.assertEqual(fetch.call_count,2)
        self.assertFalse(list(self.root.rglob('approvals')));self.assertFalse(list(self.root.rglob('review_annotations.json')));summary=c.load(self.root/'checkpoint_00000002/summary.json');self.assertEqual(summary['actual_manual_reviews'],0);self.assertFalse(summary['article_acceptance'])
        f=pd.read_parquet(self.root/'batches/batch_000001/articles.parquet');self.assertTrue(f.manual_review_status.eq('not_reviewed').all());self.assertTrue(f.manual_review_result.isna().all());self.assertTrue(all(t>=1 for t in self.clock.waits))
    def test_completed_resume_requests_zero(self):
        self.freeze();self.run();fetch=Mock(side_effect=AssertionError('must not request'));state=self.run(fetcher=fetch);self.assertEqual(state['status'],c.PENDING);fetch.assert_not_called()
    def test_unknown_joint_type_is_novel_not_approved(self):
        self.freeze();fetch=Mock(side_effect=lambda u,t,**k:{**response(u,t,**k),'text':page(u,body_extra='<ul><li>New layout</li></ul>')});state=self.run(fetcher=fetch);self.assertEqual(state['status'],c.PENDING);self.assertEqual(fetch.call_count,2);self.assertFalse((self.root/'safety_halt.json').exists());self.assertTrue(all(c.load(p)['record']['novel_type'] for p in (self.root/'row_checks').glob('*.json')));self.assertEqual(c.load(self.root/'checkpoint_00000002/summary.json')['actual_manual_reviews'],0)
    def test_http_and_transport_all_stop_after_durable_result(self):
        for status,error in [(403,None),(429,None),(500,None),(503,None),(None,'timeout')]:
            with self.subTest(status=status,error=error):
                self.root=self.root.with_name('test'+str(status)+str(bool(error)));self.freeze();fetch=Mock(side_effect=lambda u,t,**k:{**response(u,t,**k),'status':status,'error':error});state=self.run(fetcher=fetch);self.assertEqual(state['status'],'halted_no_automatic_resume');self.assertEqual(fetch.call_count,1)
                with sqlite3.connect((self.root/'batches/batch_000001/pilot.sqlite').as_uri()+'?mode=ro',uri=True) as db:self.assertEqual(db.execute('SELECT count(*) FROM articles').fetchone()[0],1)
    def test_two_body_differences_stop_before_third(self):
        self.freeze(3);fetch=Mock(side_effect=lambda u,t,**k:{**response(u,t,**k),'text':page(u,body_extra='<div class="ad">Unexplained visible text</div>')});state=self.run(fetcher=fetch);self.assertEqual(state['status'],'halted_no_automatic_resume');self.assertEqual(fetch.call_count,2)
    def test_budget_reservation_and_low_disk(self):
        self.freeze(3,budget=1);fetch=Mock(side_effect=response);state=self.run(fetcher=fetch);self.assertEqual(fetch.call_count,1);self.assertEqual(c.load(self.root/'safety_halt.json')['reason'],'request_budget_exhausted')
        self.root=self.root.with_name('lowdisk');self.freeze();fetch=Mock();state=self.run(fetcher=fetch,disk_free=lambda p:0);fetch.assert_not_called();self.assertEqual(c.load(self.root/'safety_halt.json')['reason'],'low_disk_space')
    def test_snapshot_before_commit_resumes_without_refetch(self):
        self.freeze();fetch=Mock(side_effect=response)
        with patch.object(pilot,'commit_result',side_effect=KeyboardInterrupt):state=self.run(fetcher=fetch)
        self.assertEqual(fetch.call_count,1);self.assertEqual(state['status'],'interrupted_requires_explicit_invocation');state=self.run(fetcher=fetch);self.assertEqual(fetch.call_count,2);self.assertEqual(state['status'],c.PENDING)
    def test_commit_before_callback_replays_risk_counter(self):
        self.freeze(3);fetch=Mock(side_effect=lambda u,t,**k:{**response(u,t,**k),'text':page(u,body_extra='<div class="ad">Unexplained visible text</div>')})
        with patch.object(c,'_risk',side_effect=KeyboardInterrupt):state=self.run(fetcher=fetch)
        self.assertEqual(fetch.call_count,1);state=self.run(fetcher=fetch);self.assertEqual(fetch.call_count,2);self.assertEqual(state['status'],'halted_no_automatic_resume')
    def test_received_but_unsaved_response_never_silent_refetch(self):
        self.freeze();fetch=Mock(side_effect=response)
        with patch.object(pilot,'save_snapshot',side_effect=KeyboardInterrupt):self.run(fetcher=fetch)
        state=self.run(fetcher=fetch);self.assertEqual(fetch.call_count,1);self.assertEqual(c.load(self.root/'safety_halt.json')['reason'],'transport_state_requires_reconciliation')
    def test_queue_mutation_and_existing_namespace_rejected(self):
        self.freeze();p=self.root/self.plan['batches'][0]['input_path'];p.write_text(p.read_text()+'\n');fetch=Mock()
        with self.assertRaises(ValueError):self.run(fetcher=fetch)
        fetch.assert_not_called()
        with self.assertRaises(ValueError):self.freeze()
    def test_missing_original_exclusion_protocol_rejected(self):
        self.exclusions.pop()
        with self.assertRaisesRegex(ValueError,'four original'):self.freeze()
    def test_400_checkpoint_is_pending_and_batch81_has_clock_gap(self):
        self.freeze(400);fetch=Mock(side_effect=response);state=self.run(fetcher=fetch);self.assertEqual(fetch.call_count,400);self.assertEqual(state['status'],c.PENDING);j=c.load(self.root/'checkpoint_00000400/summary.json');self.assertEqual(j['actual_manual_reviews'],0);self.assertEqual(j['pending_source_review_sample_count'],22);self.assertFalse(j['article_acceptance']);self.assertEqual(len(self.clock.waits),399)
    def test_durable_budget_rejects_deleted_or_valid_prefix_ledger(self):
        for kind in ['delete','truncate','state_delete','state_rollback']:
            with self.subTest(kind=kind):
                self.root=self.root.with_name('budget_'+kind);self.freeze(3,budget=2);fetch=Mock(side_effect=response);risk=c._risk;counter=[0];earlier={}
                def interrupt(*args,**kwargs):
                    counter[0]+=1
                    if counter[0]==1:earlier['state']=(self.root/'transport_state.json').read_bytes()
                    if counter[0]==2:raise KeyboardInterrupt()
                    return risk(*args,**kwargs)
                with patch.object(c,'_risk',side_effect=interrupt):first=self.run(fetcher=fetch)
                self.assertEqual(fetch.call_count,2);self.assertEqual(first['status'],'interrupted_requires_explicit_invocation')
                path=self.root/'transport_calls.jsonl'
                if kind=='delete':path.unlink()
                elif kind=='truncate':path.write_text('\n'.join(path.read_text().split('\n')[:2])+'\n')
                elif kind=='state_delete':(self.root/'transport_state.json').unlink()
                else:
                    path.write_text('\n'.join(path.read_text().split('\n')[:2])+'\n');(self.root/'transport_state.json').write_bytes(earlier['state'])
                result=self.run(fetcher=fetch);self.assertEqual(fetch.call_count,2);self.assertEqual(result['status'],'halted_no_automatic_resume')
    def test_first_clock_must_be_finite_before_any_fetch(self):
        for value in [float('nan'),float('inf'),-float('inf')]:
            self.root=self.root.with_name('clock_'+str(len(list(self.root.parent.glob('clock_*')))));self.freeze();fetch=Mock(side_effect=response)
            state=self.run(fetcher=fetch,clock=lambda:value);fetch.assert_not_called();self.assertEqual(state['status'],'halted_no_automatic_resume')
    def test_empty_discovery_and_wrong_scope_rejected(self):
        for changes in [{'discovery_dates_json':'[]'},{'discovery_dates_json':'[""]'},{'discovery_scope':'outside_target'},{'identity_class':'old_errors'}]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):c._validate_rows([{**candidate(0),**changes}],'2024-06-01','2024-06-02')
    def test_original_queue_membership_and_all_columns_verified(self):
        self.freeze();rows=c.readcsv(self.root/'queue.csv');rows[0]['discovery_dates_json']='["2024-06-01T13:01:33"]'
        with self.assertRaisesRegex(ValueError,'differs'):c._queue_binding(rows,self.queue_db,c.sha_file(self.queue_db))
        rows[0]=candidate(444)
        with self.assertRaisesRegex(ValueError,'absent'):c._queue_binding(rows,self.queue_db,c.sha_file(self.queue_db))
    def test_maximum_plan_size_is_explicit(self):
        with self.assertRaisesRegex(ValueError,'2000'):c._validate_rows([candidate(i) for i in range(2001)],'2024-06-01','2024-06-02')
    def test_damaged_subset_or_evidence_stops_resume(self):
        for filename in ['core_fields_complete.csv','failed_or_incomplete_urls.csv','check.json']:
            self.root=self.root.with_name('damage_'+filename.replace('.','_'));self.freeze();self.run();folder=next((self.root/'automatic_checks/batch_000001').iterdir());p=folder/filename
            if filename.endswith('.csv'):
                f=pd.read_csv(p,dtype=str,keep_default_na=False)
                if f.empty:f=pd.read_csv(folder/'all_results.csv',dtype=str,keep_default_na=False).iloc[:1]
                else:f.loc[0,'main_text']='FAKE'
                f.to_csv(p,index=False)
            else:j=c.load(p);j['manual_reviews']=999;p.write_text(json.dumps(j))
            fetch=Mock();result=self.run(fetcher=fetch);fetch.assert_not_called();self.assertEqual(result['status'],'halted_no_automatic_resume');self.assertEqual(c.load(self.root/'safety_halt.json')['reason'],'batch_readback_failed')
    def test_ambiguous_or_unexplained_article_structure_stops(self):
        additions=['<div class="complementos-container"><p>Extra missed news body.</p></div>','<p>Extra missed prose sibling.</p>','<blockquote><p>Another lead.</p></blockquote>']
        for i,extra in enumerate(additions):
            self.root=self.root.with_name('structure'+str(i));self.freeze(3);fetch=Mock(side_effect=lambda u,t,**k:{**response(u,t,**k),'text':page(u).replace('</article>',extra+'</article>')});result=self.run(fetcher=fetch);self.assertEqual(fetch.call_count,2);self.assertEqual(result['status'],'halted_no_automatic_resume')
    def test_external_redirect_and_canonical_stops_before_second(self):
        for channel in ['final_url','canonical_url']:
            self.root=self.root.with_name('host_'+channel);self.freeze()
            def external(u,t,**kw):
                result=response(u,t,**kw)
                if channel=='final_url':result['final_url']='https://outside.example/local/redirect/'
                else:result['text']=result['text'].replace('rel="canonical" href="'+u,'rel="canonical" href="https://outside.example/local/redirect/')
                return result
            fetch=Mock(side_effect=external);state=self.run(fetcher=fetch);self.assertEqual(fetch.call_count,1);self.assertEqual(state['status'],'halted_no_automatic_resume');self.assertIn(channel+'_outside_tiempo_scope',c.load(self.root/'safety_halt.json')['risks'])
    def test_new_nested_tag_path_only_marks_novelty(self):
        self.freeze();fetch=Mock(side_effect=lambda u,t,**k:{**response(u,t,**k),'text':page(u,body_extra='<section><p>Additional news details with valid source text.</p></section>')});state=self.run(fetcher=fetch);self.assertEqual(fetch.call_count,2);self.assertEqual(state['status'],c.PENDING);self.assertTrue(all(c.load(p)['record']['novel_type'] for p in (self.root/'row_checks').glob('*.json')))
    def test_early_sleep_return_cannot_shorten_gap(self):
        self.freeze();fetch=Mock(side_effect=response);state=self.run(fetcher=fetch,sleep=lambda seconds:None);self.assertEqual(fetch.call_count,1);self.assertEqual(state['status'],'halted_no_automatic_resume');self.assertEqual(c.load(self.root/'safety_halt.json')['reason'],'transport_pause_not_satisfied')
    def test_unknown_disk_measurement_cannot_start_fetch(self):
        self.freeze();fetch=Mock();state=self.run(fetcher=fetch,disk_free=lambda p:float('nan'));fetch.assert_not_called();self.assertEqual(state['status'],'halted_no_automatic_resume')
    def test_one_body_difference_is_quarantined_then_normal_continues(self):
        self.freeze(3)
        def altered(u,t,**k):
            extra='<div class="ad">Unexplained visible text</div>' if u.endswith('new-0/') else ''
            return {**response(u,t,**k),'text':page(u,body_extra=extra)}
        fetch=Mock(side_effect=altered);result=self.run(fetcher=fetch);self.assertEqual(fetch.call_count,3);self.assertEqual(result['status'],c.PENDING)
        summary=c.load(self.root/'checkpoint_00000003/summary.json');self.assertEqual(summary['quarantined_rows'],1);self.assertEqual(summary['usable_candidates'],2);self.assertEqual(summary['actual_manual_reviews'],0)
        folder=next((self.root/'automatic_checks/batch_000001').iterdir());q=pd.read_csv(folder/'quarantined_results.csv');self.assertEqual(q.sample_id.tolist(),['TC_TEST_000000']);self.assertTrue(q.manual_review_status.eq('not_reviewed').all())
    def test_window_rules_exact_boundary_and_row_count(self):
        def record(families=()):
            return {'critical_flags':[],'unexplained_flags':['difference'] if families else [],'unexplained_families':list(families)}
        history=[]
        for i in range(80):
            history.append(record(['body_or_media','article_structure'] if i in {0,39,79} else []))
        self.assertEqual(c._window_trigger(history),'three_unexplained_rows_in_rolling80')
        history=[record(['body_or_media']) if i in {0,39,80} else record() for i in range(81)]
        self.assertIsNone(c._window_trigger(history))
        self.assertIsNone(c._window_trigger([record(['publication_date']),record(['body_or_media'])]))
        self.assertIsNone(c._window_trigger([record(['body_or_media']),record(),record(['body_or_media'])]))
        self.assertEqual(c._window_trigger([record(['body_or_media']),record(['body_or_media'])]),'two_consecutive_same_family_anomalies')
    def test_consecutive_anomalies_across_batch_boundary_stop(self):
        self.freeze(82)
        def altered(u,t,**k):
            i=int(u.rstrip('/').rsplit('-',1)[-1]);extra='<div class="ad">Unexplained source text</div>' if i in {79,80} else ''
            return {**response(u,t,**k),'text':page(u,body_extra=extra)}
        fetch=Mock(side_effect=altered);state=self.run(fetcher=fetch);self.assertEqual(fetch.call_count,81);self.assertEqual(state['status'],'halted_no_automatic_resume');self.assertEqual(c.load(self.root/'safety_halt.json')['reason'],'two_consecutive_same_family_anomalies')
        self.assertTrue(state['partial_check']);self.assertFalse(state['partial_check']['batch_input_complete'])
    def test_row_assessment_tamper_prevents_new_request(self):
        self.freeze(3);fetch=Mock(side_effect=response);risk=c._risk;counter=[0]
        def interrupt(*a,**k):
            counter[0]+=1
            if counter[0]==2:raise KeyboardInterrupt()
            return risk(*a,**k)
        with patch.object(c,'_risk',side_effect=interrupt):self.run(fetcher=fetch)
        p=self.root/'row_checks/TC_TEST_000000.json';record=c.load(p);record['record']['novel_type']=not record['record']['novel_type'];p.write_text(json.dumps(record))
        calls=fetch.call_count;state=self.run(fetcher=fetch);self.assertEqual(fetch.call_count,calls);self.assertEqual(state['status'],'halted_no_automatic_resume')
    def test_quarantine_subset_tamper_stops_resume(self):
        self.freeze(2)
        def altered(u,t,**k):
            return {**response(u,t,**k),'text':page(u,body_extra='<div class="ad">Extra source text</div>' if u.endswith('new-0/') else '')}
        self.run(fetcher=Mock(side_effect=altered));folder=next((self.root/'automatic_checks/batch_000001').iterdir());path=folder/'quarantined_results.csv';frame=pd.read_csv(path);frame['sample_id']='FAKE';frame.to_csv(path,index=False);fetch=Mock();state=self.run(fetcher=fetch);fetch.assert_not_called();self.assertEqual(state['status'],'halted_no_automatic_resume')
    def test_rolling80_threshold_replayed_before_any_new_request(self):
        self.freeze(82);calls=[0];risk=c._risk
        def altered(u,t,**k):
            index=int(u.rstrip('/').rsplit('-',1)[-1]);extra='<div class="ad">Unexplained source text</div>' if index in {0,39,79} else ''
            return {**response(u,t,**k),'text':page(u,body_extra=extra)}
        def interrupted(*a,**k):
            calls[0]+=1
            if calls[0]==80:raise KeyboardInterrupt()
            return risk(*a,**k)
        fetch=Mock(side_effect=altered)
        with patch.object(c,'_risk',side_effect=interrupted):self.run(fetcher=fetch)
        self.assertEqual(fetch.call_count,80);state=self.run(fetcher=fetch);self.assertEqual(fetch.call_count,80);self.assertEqual(state['status'],'halted_no_automatic_resume');self.assertEqual(c.load(self.root/'safety_halt.json')['reason'],'three_unexplained_rows_in_rolling80')
    def test_oldest_anomaly_expires_at_row81_in_actual_runner(self):
        self.freeze(82)
        def altered(u,t,**k):
            index=int(u.rstrip('/').rsplit('-',1)[-1]);extra='<div class="ad">Unexplained source text</div>' if index in {0,39,80} else ''
            return {**response(u,t,**k),'text':page(u,body_extra=extra)}
        fetch=Mock(side_effect=altered);state=self.run(fetcher=fetch);self.assertEqual(fetch.call_count,82);self.assertEqual(state['status'],c.PENDING);self.assertEqual(c.load(self.root/'checkpoint_00000082/summary.json')['quarantined_rows'],3)
    def test_nonstandard_final_origin_is_critical(self):
        self.freeze();fetch=Mock(side_effect=lambda u,t,**k:{**response(u,t,**k),'final_url':'https://www.tiempo.com.mx:4444/local/article/'})
        state=self.run(fetcher=fetch);self.assertEqual(fetch.call_count,1);self.assertEqual(state['status'],'halted_no_automatic_resume');self.assertIn('final_url_identity_invalid',c.load(self.root/'safety_halt.json')['risks'])
    def test_relative_canonical_same_identity_is_not_conflict(self):
        self.freeze();fetch=Mock(side_effect=lambda u,t,**k:{**response(u,t,**k),'text':page(u).replace('href="'+u+'"','href="'+u.split('.mx',1)[1]+'"')});state=self.run(fetcher=fetch);self.assertEqual(fetch.call_count,2);self.assertEqual(state['status'],c.PENDING)
    def test_missing_canonical_evidence_is_quarantined_not_identity_halt(self):
        self.freeze()
        def altered(u,t,**k):
            html=page(u)
            if u.endswith('new-0/'):html=html.replace('<link rel="canonical" href="'+u+'">','')
            return {**response(u,t,**k),'text':html}
        fetch=Mock(side_effect=altered);state=self.run(fetcher=fetch);self.assertEqual(fetch.call_count,2);self.assertEqual(state['status'],c.PENDING);record=c.load(self.root/'row_checks/TC_TEST_000000.json')['record'];self.assertEqual(record['critical_flags'],[]);self.assertEqual(record['collection_quality_status'],c.QUARANTINE)
    def test_unconfirmed_missing_heading_not_a_confirmed_source_gap(self):
        self.freeze()
        def altered(u,t,**k):
            html=page(u)
            if u.endswith('new-0/'):html=html.replace('<h1>Article</h1>','').replace('<title>Article</title>','<title></title>').replace('content="Article"','content=""').replace('"headline": "Article"','"headline": ""')
            return {**response(u,t,**k),'text':html}
        state=self.run(fetcher=Mock(side_effect=altered));self.assertEqual(state['status'],c.PENDING);folder=next((self.root/'automatic_checks/batch_000001').iterdir());self.assertTrue(pd.read_csv(folder/'source_gaps.csv').empty);self.assertEqual(len(pd.read_csv(folder/'quarantined_results.csv')),1)
    def test_native_true_alias_membership_preserves_all_requests(self):
        for collision in [False,True]:
            self.root=self.root.with_name('alias_'+str(collision));self.freeze(3)
            def altered(u,t,**k):
                html=page(candidate(0)['url']) if u.endswith('new-1/') else page(u)
                if collision and u.endswith('new-1/'):html=html.replace('Summary new-0.','Different summary new-0.')
                return {**response(u,t,**k),'text':html}
            fetch=Mock(side_effect=altered);state=self.run(fetcher=fetch);self.assertEqual(fetch.call_count,3);self.assertEqual(state['status'],c.PENDING)
            B=self.root/'batches/batch_000001';self.assertEqual(len(pd.read_parquet(B/'articles.parquet')),3 if collision else 2)
            folder=next((self.root/'automatic_checks/batch_000001').iterdir());self.assertEqual(len(pd.read_parquet(folder/'all_results.parquet')),3);self.assertEqual(len(pd.read_csv(folder/'quarantined_results.csv')),1);self.assertEqual(len(pd.read_csv(folder/'usable_candidates.csv')),2)
    def test_native_alias_whitespace_normalization_matches_saved_members(self):
        self.freeze(3)
        def altered(u,t,**k):
            html=page(candidate(0)['url']) if u.endswith('new-1/') else page(u)
            if u.endswith('new-1/'):html=html.replace('preserved. Report','preserved.</p><p>Report',1)
            return {**response(u,t,**k),'text':html}
        fetch=Mock(side_effect=altered);state=self.run(fetcher=fetch)
        self.assertEqual(fetch.call_count,3);self.assertEqual(state['status'],c.PENDING)
        B=self.root/'batches/batch_000001';self.assertEqual(len(pd.read_parquet(B/'articles.parquet')),2)
        folder=next((self.root/'automatic_checks/batch_000001').iterdir())
        self.assertEqual(len(pd.read_parquet(folder/'all_results.parquet')),3)
        self.assertEqual(len(pd.read_csv(folder/'quarantined_results.csv')),1)
        self.assertEqual(len(pd.read_csv(folder/'usable_candidates.csv')),2)
    def test_source_diagnosis_independently_protects_caption_and_detects_ui_leak(self):
        B=self.base/'independent_ig';B.mkdir();row=dict(self.seedrows[0]);html=page(row['url'],body_extra=timed_instagram())
        (B/'source.html').write_text(html);row.update(snapshot_path='source.html',snapshot_sha256=source.sha_file(B/'source.html'),media_embeds=json.dumps([IG_POST]))
        expected=row['main_text']+'\nREAL CAPTION stays.';row['main_text']=expected
        record=source.diagnose(row,B)
        self.assertNotIn('raw_visible_body_difference_requires_reading',record['automatic_flags'])
        self.assertEqual([r['reason'] for r in record['independently_recognized_template_ui']],['instagram_timed_shared_post_ui'])
        row['main_text']=expected.replace('REAL CAPTION stays.','')
        self.assertIn('raw_visible_body_difference_requires_reading',source.diagnose(row,B)['automatic_flags'])
        row['main_text']=expected+'\nUna publicación compartida de Suelta la Sopa (@sueltalasopatv) el 29 Mar, 2019 a las 12:28 PDT'
        self.assertIn('raw_visible_body_difference_requires_reading',source.diagnose(row,B)['automatic_flags'])
    def test_lock_refuses_second_worker(self):
        self.freeze();fetch=Mock()
        with pilot.exclusive_run(self.root),self.assertRaises(pilot.PilotError):self.run(fetcher=fetch)
        fetch.assert_not_called()

if __name__=='__main__':unittest.main()

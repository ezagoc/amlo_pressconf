"""Offline v5 regression with real pilot SQLite and fake responses, no HTTP."""
import contextlib,io,json,sqlite3,unittest,sys
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
try:
    from crawler_core import tiempo_continuous_v5 as v5, tiempo_scheduler_v5 as scheduler
except ImportError:
    import tiempo_continuous_v5 as v5
    import tiempo_scheduler_v5 as scheduler
import test_tiempo_continuous as fixtures
candidate,response,page,writecsv,Clock=fixtures.candidate,fixtures.response,fixtures.page,fixtures.writecsv,fixtures.Clock

class V5Tests(unittest.TestCase):
    setUp=fixtures.ContinuousTests.setUp
    def freeze(self,n=2,classes=None,budget=None):
        self.root=self.media/'data/00-newspaper_data/crawler/pilots/Kevin/tiempo_continuous_v5/testv5'
        rows=[{**candidate(i),'candidate_id':str(i),'sample_id':f'TC5_TEST_{i:06d}','baseline_classes_json':'[]'} for i in range(n)]
        if classes:
            for row,cl in zip(rows,classes):
                row['queue_class']=row['identity_class']=cl
                if cl=='old_missing_fields_review':row.update(baseline_protected='1',baseline_classes_json='["old_missing_required_field"]')
        self.input=self.base/'v5.csv';writecsv(self.input,rows);self.queue_db=self.base/'v5queue.sqlite'
        with sqlite3.connect(self.queue_db) as db:
            columns=[k for k in rows[0] if k not in {'sample_id','selection_reason','expected_year','expected_kind'}]
            db.execute('CREATE TABLE candidates ('+', '.join(k+' TEXT' for k in columns)+')')
            db.executemany('INSERT INTO candidates VALUES ('+','.join('?' for _ in columns)+')',[[r[k] for k in columns] for r in rows])
        self.rows=rows
        return v5.freeze(self.input,self.root,self.media,self.registry_path,v5.sha_file(self.registry_path),self.exclusions,start='2024-06-01',end='2024-06-02',max_fetch_calls=budget or n*3,queue_db_path=self.queue_db,queue_db_sha256=v5.sha_file(self.queue_db),min_free_bytes=1)
    def execute(self,fetch=None,**opts):
        kwargs=dict(max_batches=25,fetcher=fetch or Mock(side_effect=response),clock=self.clock.now,sleep=self.clock.sleep);kwargs.update(opts)
        with contextlib.redirect_stdout(io.StringIO()):return v5.run(self.root,self.media,**kwargs)
    def current(self):
        with sqlite3.connect((self.root/'batches/batch_000001/pilot.sqlite').as_uri()+'?mode=ro',uri=True) as db:return [json.loads(x[0]) for x in db.execute('select payload_json from articles order by ordinal')]
    def test_all_four_classes_preserved_old_missing_protected(self):
        self.freeze(4,classes=['new_urls','old_error_review','old_short_review','old_missing_fields_review']);f=Mock(side_effect=response);s=self.execute(f)
        self.assertTrue(s['collection_inputs_finished']);self.assertEqual(f.call_count,4)
        for row,expected in zip(self.current(),self.rows):self.assertEqual(json.loads(row['sample_metadata_json'])['queue_class'],expected['queue_class'])
    def test_structural_good_cannot_be_relabelled(self):
        self.freeze();bad={**self.rows[0],'baseline_protected':'1','baseline_classes_json':'["old_structural_pass_unreviewed"]'}
        with self.assertRaises(ValueError):v5._validate_rows([bad],'2024-06-01','2024-06-02')
        altered={**self.rows[0],'queue_class':'old_error_review','identity_class':'old_error_review'}
        with self.assertRaises(ValueError):v5._queue_binding([altered],self.queue_db,v5.sha_file(self.queue_db))
    def test_timeout_500_200_all_attempts_saved_one_result(self):
        self.freeze(1);url=self.rows[0]['url'];seq=[{**response(url,1),'status':None,'text':'PARTIAL TIMEOUT','error':'operation timed out'}, {**response(url,1),'status':500,'text':'SERVICE ERROR'},response(url,1)]
        f=Mock(side_effect=seq);s=self.execute(f);self.assertTrue(s['collection_inputs_finished']);self.assertEqual(f.call_count,3);self.assertEqual(len(self.current()),1);self.assertEqual(self.current()[0]['qa_status'],'success')
        self.assertEqual([(self.root/f'transport_snapshots/{i:08d}.html').read_text() for i in [1,2]],['PARTIAL TIMEOUT','SERVICE ERROR'])
        self.assertEqual(len(v5._ledger(self.root,v5.load(self.root/'continuous_plan.json'))),6);self.assertEqual(self.clock.waits,[5,15])
    def test_unavailable_and_soft404_do_not_halt_or_become_success(self):
        self.freeze(4)
        def fake(u,t,**kw):
            i=int(u.strip('/').split('-')[-1]);r=response(u,t)
            if i<2:r.update(status=[404,410][i],text='<h1>Unavailable</h1>')
            elif i==2:r['text']='<h1>Ocurrió un error al procesar la noticia</h1>'
            return r
        f=Mock(side_effect=fake);s=self.execute(f);self.assertTrue(s['collection_inputs_finished']);self.assertEqual(f.call_count,4)
        self.assertEqual([x['qa_status'] for x in self.current()],['error','error','error','success'])
        checks=[v5.load(x)['record'] for x in sorted((self.root/'row_checks').glob('*.json'))];self.assertEqual([x['collection_outcome'] for x in checks],['source_unavailable']*3+['article_candidate'])
        self.assertTrue(all(not x['service_failure'] for x in checks))
    def test_article_prose_404_not_soft404(self):
        self.freeze(1);f=Mock(side_effect=lambda u,t,**k:{**response(u,t),'text':page(u,body_extra='<p>The investigation refers to case 404.</p>')});s=self.execute(f);self.assertTrue(s['collection_inputs_finished']);self.assertEqual(self.current()[0]['qa_status'],'success')
    def test_each_403_429_challenge_external_stops_after_saved_row(self):
        self.freeze(2)
        for case in ['403','429','challenge','external']:
            with self.subTest(case=case):
                # Each subcase needs independent already-bound input/namespace.
                if case!='403':
                    self.root=self.root.with_name('case_'+case);v5.freeze(self.input,self.root,self.media,self.registry_path,v5.sha_file(self.registry_path),self.exclusions,start='2024-06-01',end='2024-06-02',max_fetch_calls=6,queue_db_path=self.queue_db,queue_db_sha256=v5.sha_file(self.queue_db),min_free_bytes=1)
                def fake(u,t,**kw):
                    r=response(u,t)
                    if case.isdigit():r['status']=int(case)
                    elif case=='external':r['final_url']='https://outside.invalid/story'
                    else:r['text']='<html><title>Just a moment...</title><form id="challenge-form"></form></html>'
                    return r
                f=Mock(side_effect=fake);s=self.execute(f);self.assertEqual(f.call_count,1);self.assertEqual(s['status'],'halted_no_automatic_resume');self.assertEqual(len(self.current()),1)
                again=Mock();self.execute(again);again.assert_not_called()
    def test_three_exhausted_service_urls_stop_before_fourth(self):
        self.freeze(4);f=Mock(side_effect=lambda u,t,**k:{**response(u,t),'status':503,'text':'Service unavailable'});s=self.execute(f)
        self.assertEqual(f.call_count,9);self.assertEqual(len(self.current()),3);self.assertEqual(s['status'],'halted_no_automatic_resume')
        self.assertEqual(v5.load(self.root/'safety_halt.json')['reason'],'three_consecutive_terminal_service_failures')
    def test_isolated_exhausted_service_failure_continues(self):
        self.freeze(2);f=Mock(side_effect=lambda u,t,**k:{**response(u,t),'status':503,'text':'Server temporarily down'} if 'new-0/' in u else response(u,t));s=self.execute(f)
        self.assertTrue(s['collection_inputs_finished']);self.assertEqual(f.call_count,4);self.assertEqual([x['qa_status'] for x in self.current()],['error','success'])
    def test_completed_resume_zero_request_and_tampered_subset_halts(self):
        self.freeze();self.execute();f=Mock(side_effect=AssertionError('no fetch'));self.assertTrue(self.execute(f)['collection_inputs_finished']);f.assert_not_called()
        folder=next((self.root/'automatic_checks/batch_000001').iterdir());(folder/'source_unavailable.csv').write_text('tamper')
        s=self.execute(f);self.assertEqual(s['status'],'halted_no_automatic_resume');f.assert_not_called()
    def test_terminal_cache_before_pilot_save_resumes_without_repeat(self):
        self.freeze(2);f=Mock(side_effect=response)
        with patch.object(v5.pilot,'save_snapshot',side_effect=KeyboardInterrupt):self.execute(f)
        self.assertEqual(f.call_count,1)
        s=self.execute(f);self.assertTrue(s['collection_inputs_finished']);self.assertEqual(f.call_count,2)
    def test_intermediate_retry_cache_interrupt_is_not_repeated(self):
        self.freeze(1);f=Mock(side_effect=lambda u,t,**k:{**response(u,t),'status':500,'text':'server'})
        with patch.object(self.clock,'sleep',side_effect=KeyboardInterrupt):self.execute(f)
        self.assertEqual(f.call_count,1);s=self.execute(f);self.assertEqual(f.call_count,1);self.assertEqual(s['status'],'halted_no_automatic_resume')
        self.assertIn('Interrupted retry chain',v5.load(self.root/'safety_halt.json')['detail'])
    def test_uncertain_fetch_or_deleted_ledger_does_not_repeat(self):
        self.freeze();f=Mock(side_effect=KeyboardInterrupt);self.execute(f);s=self.execute(f);self.assertEqual(f.call_count,1);self.assertEqual(s['status'],'halted_no_automatic_resume')
    def test_ledger_complete_prefix_truncation_fails_closed(self):
        self.freeze(2);self.execute();p=self.root/'transport_calls.jsonl';p.write_text('\n'.join(p.read_text().splitlines()[:2])+'\n');f=Mock();self.assertEqual(self.execute(f)['status'],'halted_no_automatic_resume');f.assert_not_called()
    def test_low_disk_before_initial_or_retry_stops_before_next_request(self):
        self.freeze();f=Mock(side_effect=response);s=self.execute(f,disk_free=lambda p:0);f.assert_not_called();self.assertEqual(s['status'],'halted_no_automatic_resume')
    def test_source_failure_window_80_and_once_per_row(self):
        normal={'critical_flags':[],'unexplained_flags':[],'unexplained_families':[]};bad={**normal,'unexplained_flags':['body','media'],'unexplained_families':['body_or_media']}
        h=[normal.copy() for _ in range(81)]
        for i in [0,39,79]:h[i]=bad
        self.assertEqual(v5._window_trigger(h[:80]),'three_unexplained_rows_in_rolling80');self.assertIsNone(v5._window_trigger(h[:81]))
        service={**normal,'service_failure':True};h=[normal.copy() for _ in range(80)]
        for i in range(0,80,10):h[i]=service
        self.assertEqual(v5._window_trigger(h),'eight_terminal_service_failures_in_rolling80')
    def setup_campaign(self,n=3,chunk=2):
        self.freeze(n);self.prepared=self.base/'prepared';scheduler.prepare(self.queue_db,v5.sha_file(self.queue_db),self.exclusions,self.prepared,start='2024-06-01',end='2024-06-02',chunk_size=chunk)
        self.master=self.media/'data/00-newspaper_data/crawler/pilots/Kevin/tiempo_continuous_v5_campaigns/master'
        scheduler.bind(self.prepared,self.master,self.media,self.registry_path,v5.sha_file(self.registry_path),max_fetch_calls=n*3,min_free_bytes=1)
    def run_campaign(self,fetch=None,**opts):
        args=dict(max_plans=10,max_batches_per_plan=25,fetcher=fetch or Mock(side_effect=response),clock=self.clock.now,sleep=self.clock.sleep);args.update(opts)
        with contextlib.redirect_stdout(io.StringIO()):return scheduler.run(self.master,self.media,**args)
    def test_scheduler_union_disjoint_and_resume_no_fetch(self):
        self.setup_campaign(3,2);m=scheduler.validate_preparation(self.prepared);self.assertEqual([p['rows'] for p in m['parts']],[2,1]);f=Mock(side_effect=response)
        s=self.run_campaign(f,max_plans=1);self.assertEqual(f.call_count,2);self.assertEqual(s['completed_plans'],1)
        s=self.run_campaign(f);self.assertEqual(f.call_count,3);self.assertEqual(s['result_rows'],3);self.assertEqual(s['transport_reservations'],3);self.assertIn('pending_Joaquin',s['status']);self.assertEqual(self.clock.waits,[1,1])
        self.run_campaign(f);self.assertEqual(f.call_count,3)
    def test_scheduler_cross_plan_anomaly_window_cannot_reset(self):
        self.setup_campaign(3,1);f=Mock(side_effect=lambda u,t,**k:{**response(u,t),'text':page(u,body_extra='<div class="ad">Missed article prose</div>')})
        s=self.run_campaign(f);self.assertEqual(f.call_count,2);self.assertEqual(s['status'],'halted_no_automatic_resume');self.assertEqual(s['completed_plans'],1)
        self.run_campaign(f);self.assertEqual(f.call_count,2)
    def test_scheduler_deleted_child_or_progress_refuses_adoption(self):
        self.setup_campaign(3,2);self.run_campaign(max_plans=1);p=self.master/'progress.json';j=v5.load(p);j['initialized_children']=[];j['completed']=[];j['actual_transport_reservations']=0;p.write_text(json.dumps(j));f=Mock()
        with self.assertRaises(ValueError):self.run_campaign(f)
        f.assert_not_called()
    def test_original_candidate_column_mutation_rejected(self):
        self.setup_campaign(3,2);part=self.prepared/'plan_000001.csv';rows=v5.readcsv(part);rows[0]['baseline_protected']='1';writecsv(part,rows)
        with self.assertRaises(ValueError):scheduler.validate_preparation(self.prepared)
    def test_global_budget_never_resets_between_children(self):
        self.setup_campaign(3,2);m=v5.load(self.master/'campaign.json');m['max_fetch_calls']=2;m.pop('campaign_sha256');m['campaign_sha256']=v5.digest(m);v5.write(self.master,'campaign.json',m);p=v5.load(self.master/'progress.json');p['campaign_sha256']=m['campaign_sha256'];v5.write(self.master,'progress.json',p)
        f=Mock(side_effect=response);s=self.run_campaign(f);self.assertEqual(f.call_count,2);self.assertEqual(s['status'],'stopped_global_request_budget_exhausted')

    def test_partial_freeze_is_fail_closed_not_silently_adopted(self):
        self.setup_campaign(3,2);original=v5.freeze
        def broken(*args,**kwargs):
            raise KeyboardInterrupt()
        with patch.object(v5,'freeze',side_effect=broken),self.assertRaises(KeyboardInterrupt):self.run_campaign()
        f=Mock()
        with self.assertRaisesRegex(ValueError,'Child directory/progress mismatch'):self.run_campaign(f)
        f.assert_not_called()
    def test_finished_child_before_completion_receipt_resumes_zero_repeat(self):
        self.setup_campaign(3,2);f=Mock(side_effect=response);original=scheduler.write
        def crash(root,name,obj):
            if name=='completion_receipt.json':raise KeyboardInterrupt()
            return original(root,name,obj)
        with patch.object(scheduler,'write',side_effect=crash),self.assertRaises(KeyboardInterrupt):self.run_campaign(f,max_plans=1)
        self.assertEqual(f.call_count,2)
        s=self.run_campaign(f,max_plans=1);self.assertEqual(f.call_count,2);self.assertEqual(s['completed_plans'],1)
        s=self.run_campaign(f);self.assertEqual(f.call_count,3);self.assertEqual(s['result_rows'],3)
    def test_active_calls_are_in_reported_total_budget(self):
        self.setup_campaign(81,81);f=Mock(side_effect=response);s=self.run_campaign(f,max_plans=1,max_batches_per_plan=1)
        self.assertEqual(f.call_count,80);self.assertEqual(s['completed_plan_transport_reservations'],0)
        self.assertEqual(s['active_plan_transport_reservations'],80);self.assertEqual(s['total_transport_reservations'],80)
        s=self.run_campaign(f);self.assertEqual(f.call_count,81);self.assertEqual(s['total_transport_reservations'],81)
    def test_single_worker_campaign_lock_blocks_second_invocation(self):
        self.setup_campaign(2,2);f=Mock()
        with v5.pilot.exclusive_run(self.master.parent),self.assertRaises(v5.pilot.PilotError):self.run_campaign(f)
        f.assert_not_called()

    def test_directory_date_judgment_retained_without_technical_halt(self):
        self.freeze(3)
        # Use a larger true article window; directory remains June1, article is June2.
        plan=v5.load(self.root/'continuous_plan.json');plan['date_end_exclusive']='2024-06-03';plan.pop('plan_sha256');plan['plan_sha256']=v5.digest(plan)
        v5.write(self.root,'continuous_plan.json',plan);state=v5.load(self.root/'transport_state.json');state['plan_sha256']=plan['plan_sha256'];v5.write(self.root,'transport_state.json',state)
        def fake(u,t,**kw):
            r=response(u,t);r['text']=page(u,date='2024-06-02T12:01:33').replace('01 Junio','02 Junio');return r
        f=Mock(side_effect=fake);result=self.execute(f);self.assertTrue(result['collection_inputs_finished']);self.assertEqual(f.call_count,3)
        for path in (self.root/'row_checks').glob('*.json'):
            rec=v5.load(path)['record'];self.assertEqual(rec['source_judgment_flags'],['article_vs_discovery_day_difference']);self.assertFalse(rec['unexplained_flags']);self.assertEqual(rec['collection_quality_status'],v5.QUARANTINE)
    def test_true_short_text_judgment_does_not_halt_or_fake_success(self):
        self.freeze(3)
        def fake(u,t,**kw):
            r=response(u,t);s=page(u);start=s.index('<div class="complementos-container">');s=s[:start]+'<div class="complementos-container"><p>Short verified statement '+u.rsplit('-',1)[-1]+'</p></div></article></body></html>';r['text']=s;return r
        f=Mock(side_effect=fake);result=self.execute(f);self.assertTrue(result['collection_inputs_finished']);self.assertEqual(f.call_count,3)
        for path in (self.root/'row_checks').glob('*.json'):
            rec=v5.load(path)['record'];self.assertIn('suspicious_very_short_body_review_only',rec['source_judgment_flags']);self.assertFalse(rec['unexplained_flags']);self.assertEqual(rec['collection_quality_status'],v5.QUARANTINE)

    def test_invalid_finish_clock_outranks_original_timeout(self):
        self.freeze(2);ticks=[100.,100.,float('nan')]
        def clock():return ticks.pop(0) if ticks else self.clock.now()
        f=Mock(side_effect=lambda u,t,**k:{**response(u,t),'status':None,'text':'Partial source body','error':'operation timed out'})
        state=self.execute(f,clock=clock)
        self.assertEqual(f.call_count,1);self.assertEqual(state['status'],'halted_no_automatic_resume')
        self.assertEqual(len(self.current()),1);self.assertEqual(self.current()[0]['qa_status'],'error')
        receipt=v5.load(self.root/'transport_snapshots/00000001.json')
        self.assertEqual(receipt['response_kind'],'critical_transport_clock');self.assertTrue(receipt['terminal'])
        self.assertEqual((self.root/'transport_snapshots/00000001.html').read_text(),'Partial source body')
        self.assertIn('operation timed out',receipt['response']['error'])

if __name__=='__main__':unittest.main()

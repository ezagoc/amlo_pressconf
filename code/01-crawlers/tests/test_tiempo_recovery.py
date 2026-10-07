"""Offline recovery bridge tests: real storage/entrypoints, fake transport only."""
import contextlib
import io
import json
import runpy
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawler_core import tiempo_continuous_v5 as w, tiempo_scheduler_v5 as scheduler, tiempo_recovery as recovery
import test_tiempo_continuous as fixtures


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        fixtures.ContinuousTests.setUp(self)
        self.base = self.base.resolve()
        self.media = self.media.resolve()
        self.patches = [patch('subprocess.Popen', side_effect=AssertionError('No real subprocess/HTTP in recovery tests')),
                        patch('socket.socket.connect', side_effect=AssertionError('No real sockets')),
                        patch('socket.getaddrinfo', side_effect=AssertionError('No DNS'))]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def donor(self, n=4, saved=2, master_budget=None, chunk_size=2000, completed=0):
        rows = [{**fixtures.candidate(i), 'candidate_id': str(i), 'sample_id': 'TC5_'+str(i),
                 'baseline_classes_json': '[]'} for i in range(n)]
        queue = self.base/'donor_queue.sqlite'
        with sqlite3.connect(queue) as db:
            columns = [k for k in rows[0] if k not in {'sample_id','selection_reason','expected_year','expected_kind'}]
            db.execute('CREATE TABLE candidates ('+', '.join(k+' TEXT' for k in columns)+')')
            db.executemany('INSERT INTO candidates VALUES ('+','.join('?' for _ in columns)+')', [[r[k] for k in columns] for r in rows])
        prepared = self.base/'prepared'
        prep = scheduler.prepare(queue, w.sha_file(queue), self.exclusions, prepared,
                                 start='2024-06-01', end='2024-06-02', chunk_size=chunk_size)
        campaign_root = self.media/'data/00-newspaper_data/crawler/pilots/Kevin/tiempo_continuous_v5_campaigns/donor'
        camp = scheduler.bind(prepared, campaign_root, self.media, self.registry_path, w.sha_file(self.registry_path),
                              max_fetch_calls=master_budget or n*3, min_free_bytes=1)
        prior_context = None
        child_parent = self.media/'data/00-newspaper_data/crawler/pilots/Kevin/tiempo_continuous_v5'
        if completed:
            with contextlib.redirect_stdout(io.StringIO()):
                prior_result = scheduler.run(campaign_root, self.media, max_plans=completed, max_batches_per_plan=25,
                    fetcher=fixtures.response, clock=self.clock.now, sleep=self.clock.sleep)
            self.assertEqual(prior_result['completed_plans'], completed)
            prior_context = w.load(child_parent/camp['child_names'][completed-1]/'continuation_context.json')
        child = child_parent/camp['child_names'][completed]
        part = prep['parts'][completed]
        plan = w.freeze(prepared/part['path'], child, self.media, self.registry_path, w.sha_file(self.registry_path),
                        self.exclusions, start='2024-06-01', end='2024-06-02', max_fetch_calls=part['rows']*3,
                        queue_db_path=queue, queue_db_sha256=w.sha_file(queue), min_free_bytes=1, seed_context=prior_context)
        # A controlled fixture stop after a durable commit: no uncertain GET is fabricated.
        real_assess = w._assess_row
        seen = 0
        def stop_after_commit(*args, **kwargs):
            nonlocal seen
            rec, trigger = real_assess(*args, **kwargs)
            seen += 1
            # Synthetic injection of a supported source-risk halt after native commit.
            return rec, 'three_unexplained_rows_in_rolling80' if seen == saved else trigger
        with contextlib.redirect_stdout(io.StringIO()), patch.object(w, '_assess_row', side_effect=stop_after_commit):
            state = w.run(child, self.media, max_batches=25, fetcher=fixtures.response,
                          clock=self.clock.now, sleep=self.clock.sleep)
        self.assertEqual(state['status'], 'halted_no_automatic_resume')
        progress = w.load(campaign_root/'progress.json')
        progress['initialized_children'] = list(range(1, completed+2))
        w.write(campaign_root,'progress.json',progress)
        self.donor_child=child
        self.donor_campaign=campaign_root
        self.oldplan=plan
        self.donor_rows=[r for b in plan['batches'] for r in w._rows(child,b)]
        self.assertEqual(len(self.donor_rows),saved)
        self.protected={str(p):w.sha_file(p) for root in [campaign_root, *[child_parent/name for name in camp['child_names'][:completed+1]]] for p in root.rglob('*') if p.is_file() and p.name!='.pilot.lock'}
        protected_path=self.base/'protected.json';w.write(self.base,protected_path.name,self.protected)
        history=self.base/'history.json'
        if prior_context is None:
            w.write(self.base,history.name,{'schema':'tiempo-history-identity-index-v1','records':[],'parent':None})
            prior_context={'source_history':[],'service_history':[],'last_transport_finish':None,
                'prior_plan_receipts':[], 'history_index':{'path':str(history),'sha256':w.sha_file(history)}}
        else:
            history=Path(prior_context['history_index']['path'])
        seed=self.base/'seed.json';w.write(self.base,seed.name,prior_context)
        self.newmedia=self.base/'RecoveryMedia'
        self.newchild=self.newmedia/'data/00-newspaper_data/crawler/pilots/Kevin/tiempo_continuous_v5/successor'
        self.capsule=self.base/'capsule'
        self.config=self.base/'config.json'
        cfg={'capsule':str(self.capsule),'isolated_media':str(self.newmedia),'new_child':str(self.newchild),
             'source_campaign':str(campaign_root),'source_child':str(child),'expected_active_saved':saved,
             'protected_sources':str(protected_path),'seed_context':str(seed),'registry':str(self.registry_path),'history_index':str(history)}
        w.write(self.base,self.config.name,cfg)
        return cfg

    def prepare(self):
        with contextlib.redirect_stdout(io.StringIO()):return recovery.prepare(self.config)

    def run_trial(self, fetcher=None, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return recovery.run_trial(self.capsule,fetcher=fetcher,clock=self.clock.now,sleep=self.clock.sleep,**kwargs)

    def preserved(self):
        self.assertEqual({p:w.sha_file(p) for p in self.protected},self.protected)

    def test_actual_cli_prepare_inspect_and_explicit_real_dispatch_mocked(self):
        self.donor()
        script=Path(recovery.__file__).parents[1]/'scripts/run_tiempo_recovery.py'
        for argv in [['prepare','--config',str(self.config)],['inspect','--capsule',str(self.capsule)]]:
            with patch.object(sys,'argv',[str(script),*argv]), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as ex:
                runpy.run_path(str(script),run_name='__main__')
            self.assertEqual(ex.exception.code,0)
        with self.assertRaisesRegex(ValueError,'Explicit live authorization'):
            recovery.run_trial(self.capsule)
        with patch('crawler_core.capabilities.fetch',side_effect=fixtures.response) as fetch:
            result=self.run_trial(allow_network=True)
        self.assertEqual(fetch.call_count,2)
        self.assertEqual(result['status'],'bounded_trial_finished_pending_review')
        _,_,status=recovery.inspect(self.capsule)
        self.assertEqual(status['total_charged_transport_reservations'],4)
        again=Mock(side_effect=AssertionError('Completed trial must not fetch'))
        self.assertEqual(self.run_trial(again)['network_calls_this_invocation'],0)
        again.assert_not_called();self.preserved()

    def test_full_original_plan_and_batch_boundary_not_replaced_by_pending_subset(self):
        self.donor(n=82,saved=78);capsule=self.prepare()
        self.assertEqual(capsule['trial_sample_ids'],self.oldplan['batches'][0]['sample_ids'][78:])
        self.assertEqual(w.load(self.newchild/'continuous_plan.json')['row_count'],82)
        self.assertEqual(len(w.readcsv(self.newchild/'queue.csv')),82)
        fetch=Mock(side_effect=fixtures.response);result=self.run_trial(fetch)
        self.assertEqual(fetch.call_count,2);self.assertEqual(result['saved_active_rows'],80)
        self.assertFalse((self.newchild/'batches/batch_000002/pilot.sqlite').exists())
        self.preserved()

    def test_retry_charge_and_snapshots_preserved_all_three_responses(self):
        self.donor();c=self.prepare();attempts=0
        def fake(url,timeout,**kw):
            nonlocal attempts
            attempts+=1
            if attempts==1:return {**fixtures.response(url,timeout),'status':None,'text':'Partial timeout bytes','error':'operation timed out'}
            if attempts==2:return {**fixtures.response(url,timeout),'status':503,'text':'Service unavailable'}
            return fixtures.response(url,timeout)
        fetch=Mock(side_effect=fake);result=self.run_trial(fetch)
        self.assertEqual(fetch.call_count,4);self.assertEqual(result['new_transport_reservations'],4)
        self.assertEqual((self.newchild/'transport_snapshots/00000003.html').read_text(),'Partial timeout bytes')
        self.assertEqual((self.newchild/'transport_snapshots/00000004.html').read_text(),'Service unavailable')
        self.preserved()

    def test_terminal_response_before_native_commit_recovers_without_duplicate_fetch(self):
        self.donor();self.prepare();fetch=Mock(side_effect=fixtures.response)
        with patch.object(w.pilot,'save_snapshot',side_effect=KeyboardInterrupt):self.run_trial(fetch)
        self.assertEqual(fetch.call_count,1)
        result=self.run_trial(fetch)
        self.assertEqual(fetch.call_count,2);self.assertEqual(result['status'],'bounded_trial_finished_pending_review')
        self.preserved()

    def test_unknown_network_window_is_not_retried(self):
        self.donor();self.prepare();fetch=Mock(side_effect=KeyboardInterrupt)
        self.run_trial(fetch);result=self.run_trial(fetch)
        self.assertEqual(fetch.call_count,1);self.assertEqual(result['status'],'halted_no_automatic_resume')
        self.preserved()

    def test_master_budget_stops_before_extra_reservation(self):
        self.donor(master_budget=3);self.prepare();fetch=Mock(side_effect=fixtures.response)
        result=self.run_trial(fetch)
        self.assertEqual(fetch.call_count,1);self.assertEqual(result['status'],'halted_no_automatic_resume')
        self.assertEqual(result['total_charged_transport_reservations'],3)
        self.assertEqual(sum(e['event']=='start' for e in w._ledger(self.newchild,w.load(self.newchild/'continuous_plan.json'))),3)
        self.preserved()

    def test_access_failure_and_resume_are_fail_closed(self):
        self.donor();self.prepare();fetch=Mock(side_effect=lambda u,t,**kw:{**fixtures.response(u,t),'status':403,'text':'Forbidden'})
        result=self.run_trial(fetch)
        self.assertEqual(fetch.call_count,1);self.assertEqual(result['status'],'halted_no_automatic_resume')
        self.run_trial(fetch);self.assertEqual(fetch.call_count,1);self.preserved()

    def test_low_disk_prevents_any_new_reservation(self):
        self.donor();self.prepare();fetch=Mock(side_effect=fixtures.response)
        result=self.run_trial(fetch,disk_free=lambda path:0)
        fetch.assert_not_called();self.assertEqual(result['new_transport_reservations'],0)
        self.assertEqual(result['status'],'halted_no_automatic_resume');self.preserved()

    def test_protected_source_change_rejected_before_prepare_and_trial(self):
        self.donor();self.prepare()
        target=self.donor_child/'Kevin_NOTE.md'
        original=target.read_bytes();target.write_bytes(original+b'\nUnexpected change\n')
        fetch=Mock(side_effect=fixtures.response)
        with self.assertRaisesRegex(ValueError,'Protected evidence changed'):self.run_trial(fetch)
        fetch.assert_not_called();target.write_bytes(original);self.preserved()

    def test_review_obligation_and_imported_prefix_tampering_fail_closed(self):
        self.donor();self.prepare();obligation=self.capsule/'Inherited_Review_Obligations.json'
        doc=w.load(obligation);self.assertEqual(doc['original_frozen_batch_selections'][0]['batch_id'],'batch_000001')
        original=obligation.read_bytes();obligation.write_bytes(b'{}\n')
        with self.assertRaisesRegex(ValueError,'Protected evidence changed'):recovery.inspect(self.capsule)
        obligation.write_bytes(original)
        B=self.newchild/'batches/batch_000001';p=B/'pilot.sqlite'
        with sqlite3.connect(p) as db:
            row=json.loads(db.execute('SELECT payload_json FROM articles ORDER BY ordinal LIMIT 1').fetchone()[0]);row['title']='Corrupt imported title'
            db.execute('UPDATE articles SET payload_json=?,title=? WHERE sample_id=?',(json.dumps(row),row['title'],row['sample_id']))
        with self.assertRaises(ValueError):recovery.inspect(self.capsule)
        self.preserved()

    def refresh_protection(self):
        self.protected = {p:w.sha_file(p) for p in self.protected}
        path=Path(w.load(self.config)['protected_sources'])
        w.write(path.parent,path.name,self.protected)

    def test_omitted_required_halt_protection_rejected_before_copy(self):
        cfg=self.donor();protected=w.load(cfg['protected_sources'])
        protected.pop(str(self.donor_child/'safety_halt.json'))
        w.write(Path(cfg['protected_sources']).parent,Path(cfg['protected_sources']).name,protected)
        with self.assertRaises(ValueError):self.prepare()
        self.assertFalse(self.newchild.exists());self.preserved()

    def test_foreign_state_plan_rejected_even_with_current_file_hash(self):
        self.donor();state=w.load(self.donor_child/'continuous_state.json')
        state['plan_sha256']='f'*64;w.write(self.donor_child,'continuous_state.json',state)
        self.refresh_protection()
        with self.assertRaises(ValueError):self.prepare()
        self.assertFalse(self.newchild.exists());self.preserved()

    def test_foreign_halt_plan_rejected_even_with_matching_state_digest(self):
        self.donor();halt=w.load(self.donor_child/'safety_halt.json')
        halt['plan_sha256']='f'*64;w.write(self.donor_child,'safety_halt.json',halt)
        state=w.load(self.donor_child/'continuous_state.json')
        state['halt_sha256']=w.sha_file(self.donor_child/'safety_halt.json')
        w.write(self.donor_child,'continuous_state.json',state);self.refresh_protection()
        with self.assertRaises(ValueError):self.prepare()
        self.assertFalse(self.newchild.exists());self.preserved()

    def test_progress_foreign_campaign_rejected_before_copy(self):
        self.donor();progress=w.load(self.donor_campaign/'progress.json')
        progress['campaign_sha256']='f'*64;w.write(self.donor_campaign,'progress.json',progress)
        self.refresh_protection()
        with self.assertRaises(ValueError):self.prepare()
        self.assertFalse(self.newchild.exists());self.preserved()

    def test_successor_nested_under_donor_is_rejected_before_writes(self):
        cfg=self.donor();media=self.donor_child/'nested_media'
        cfg.update(isolated_media=str(media),new_child=str(media/'data/00-newspaper_data/crawler/pilots/Kevin/tiempo_continuous_v5/successor'))
        w.write(self.config.parent,self.config.name,cfg)
        with self.assertRaises(ValueError):self.prepare()
        self.assertFalse(media.exists());self.preserved()

    def test_valid_completed_child_context_preserves_global_charges(self):
        self.donor(n=8,saved=2,chunk_size=4,completed=1);capsule=self.prepare()
        self.assertEqual(capsule['historical_completed_rows'],4)
        self.assertEqual(capsule['original_completed_transport_calls'],4)
        fetch=Mock(side_effect=fixtures.response);result=self.run_trial(fetch)
        self.assertEqual(fetch.call_count,2)
        self.assertEqual(result['total_charged_transport_reservations'],8)
        self.assertEqual(result['status'],'bounded_trial_finished_pending_review');self.preserved()

    def test_fake_empty_prior_source_seed_rejected_before_copy(self):
        cfg=self.donor(n=8,saved=2,chunk_size=4,completed=1)
        seed=w.load(cfg['seed_context']);self.assertEqual(len(seed['source_history']),4)
        seed['source_history']=[];w.write(Path(cfg['seed_context']).parent,Path(cfg['seed_context']).name,seed)
        with self.assertRaises(ValueError):self.prepare()
        self.assertFalse(self.newchild.exists());self.preserved()

    def test_truncated_completed_identity_history_rejected_before_copy(self):
        cfg=self.donor(n=8,saved=2,chunk_size=4,completed=1)
        seed=w.load(cfg['seed_context'])
        records=w.load_history_index(seed['history_index'])
        self.assertEqual(len(records),4)
        truncated=self.base/'truncated_history.json'
        w.write(self.base,truncated.name,{'schema':w.HISTORY_SCHEMA,'records':records[1:],'parent':None})
        seed['history_index']={'path':str(truncated),'sha256':w.sha_file(truncated)}
        w.write(Path(cfg['seed_context']).parent,Path(cfg['seed_context']).name,seed)
        cfg['history_index']=str(truncated);w.write(self.config.parent,self.config.name,cfg)
        with self.assertRaises(ValueError):self.prepare()
        self.assertFalse(self.newchild.exists());self.preserved()

    def test_completed_ledger_charge_mismatch_rejected_before_copy(self):
        self.donor(n=8,saved=2,chunk_size=4,completed=1)
        progress=w.load(self.donor_campaign/'progress.json')
        progress['actual_transport_reservations']-=1
        w.write(self.donor_campaign,'progress.json',progress);self.refresh_protection()
        with self.assertRaises(ValueError):self.prepare()
        self.assertFalse(self.newchild.exists());self.preserved()


if __name__=='__main__':unittest.main()

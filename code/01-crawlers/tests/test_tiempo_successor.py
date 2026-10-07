"""Targeted successor integration tests: real storage, synthetic offline transport.

One immutable fixture completes a genuine prior recovery capsule to160 rows.
Fresh successor destinations exercise only the original next80 boundary.
"""
import contextlib
import io
import json
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_tiempo_recovery as recovery_fixtures
import test_tiempo_continuous as fixtures
from crawler_core import tiempo_continuous_v5 as w, tiempo_recovery as recovery
from crawler_core import tiempo_successor as successor


class SuccessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Call fixture methods without inheriting/collecting the old19 tests.
        helper = recovery_fixtures.RecoveryTests('test_full_original_plan_and_batch_boundary_not_replaced_by_pending_subset')
        helper.setUp()
        cls.addClassCleanup(helper.doCleanups)
        cls.fixture = helper
        with contextlib.redirect_stdout(io.StringIO()):
            helper.donor(n=482, saved=146, chunk_size=241, completed=1)
            helper.prepare()
            cls.finish_fetch = Mock(side_effect=fixtures.response)
            result = helper.run_trial(cls.finish_fetch)
        if result['saved_active_rows'] != 160 or cls.finish_fetch.call_count != 14:
            raise AssertionError('Synthetic source recovery did not close the original14')
        cls.source_capsule = helper.capsule
        cls.source_child = helper.newchild
        cls.source_plan = w.load(cls.source_child/'continuous_plan.json')
        cls.source_rows = [r for b in cls.source_plan['batches'] for r in w._rows(cls.source_child,b)]
        cls.source_native = {str(p.relative_to(cls.source_child)):w.sha_file(p)
                             for p in cls.source_child.glob('batches/*/pilot.sqlite')}
        cls.source_all = {str(p):w.sha_file(p) for root in (cls.source_capsule,cls.source_child)
                          for p in root.rglob('*') if p.is_file() and p.name != '.pilot.lock'}
        cls.closure = helper.base/'source_closure.json'
        w.write(helper.base,cls.closure.name,{'author':'Kevin','status':'PASS_SYNTHETIC_OFFLINE_CLOSURE',
            'native_successor_records':160,'no_automatic_expansion':True,'article_acceptance':False,
            'synthetic_test_fixture':True,'human_approval':False,
            'source_binding':{'capsule_file_sha256':w.sha_file(cls.source_capsule/'capsule.json'),
                'saved_active_rows':160,'transport_ledger_sha256':w.sha_file(cls.source_child/'transport_calls.jsonl'),
                'native_databases':[{'path':str(p),'sha256':w.sha_file(p)} for p in sorted(cls.source_child.glob('batches/*/pilot.sqlite'))]}})

    def setUp(self):
        self.base = self.fixture.base/self._testMethodName
        self.base.mkdir()
        self.media = self.base/'Media'
        self.child = self.media/'data/00-newspaper_data/crawler/pilots/Kevin/tiempo_continuous_v5/next80'
        self.root = self.base/'capsule'
        self.config = self.base/'config.json'
        self.cfg = {'source_capsule':str(self.source_capsule),'source_closure':str(self.closure),
            'source_closure_sha256':w.sha_file(self.closure),'capsule':str(self.root),
            'isolated_media':str(self.media),'new_child':str(self.child),'expected_active_saved':160,
            'expected_batch_id':'batch_000003','expected_sample_ids':self.source_plan['batches'][2]['sample_ids'],
            'max_additional_transport_calls':240}
        self.clock = fixtures.Clock()
        self.clock.t = w._ledger(self.source_child,self.source_plan)[-1]['epoch']+1
        self.write_config()

    def write_config(self):
        w.write(self.base,self.config.name,self.cfg)

    def prepare(self):
        with contextlib.redirect_stdout(io.StringIO()):return successor.prepare(self.config)

    def run_trial(self, fetcher=None, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return successor.run_trial(self.root,fetcher=fetcher,clock=self.clock.now,sleep=self.clock.sleep,**kw)

    def assert_source_preserved(self):
        self.assertEqual({p:w.sha_file(p) for p in self.source_all},self.source_all)
        self.fixture.preserved()
        self.assertTrue((self.fixture.donor_child/'safety_halt.json').exists())

    def assert_prefix_preserved(self):
        plan=w.load(self.child/'continuous_plan.json')
        rows=[r for b in plan['batches'] for r in w._rows(self.child,b)]
        self.assertEqual(rows[:160],self.source_rows)
        for relative,expected in self.source_native.items():
            self.assertEqual(w.sha_file(self.child/relative),expected)
        for b in self.source_plan['batches'][:2]:
            for p in (self.source_child/'batches'/b['batch_id']/'raw_html').glob('*/*'):
                if p.is_file():self.assertEqual(w.sha_file(self.child/p.relative_to(self.source_child)),w.sha_file(p))
        self.assert_source_preserved()

    def test_real_entrypoints_collect_exact80_then_stop_before4_and_completed_repeat_zero(self):
        self.prepare();c,plan,before=successor.inspect(self.root)
        self.assertEqual(before['saved_active_rows'],160)
        self.assertEqual(before['new_transport_reservations'],0)
        self.assertEqual(plan['batches'],self.source_plan['batches'])
        self.assertEqual((self.child/'queue.csv').read_bytes(),(self.source_child/'queue.csv').read_bytes())
        fetch=Mock(side_effect=fixtures.response);result=self.run_trial(fetch)
        self.assertEqual(fetch.call_count,80)
        expected=[r['url'] for r in w.readcsv(self.child/'queue.csv')][160:240]
        self.assertEqual([call.args[0] for call in fetch.call_args_list],expected)
        self.assertEqual(result['saved_active_rows'],240)
        self.assertEqual(result['new_transport_reservations'],80)
        self.assertEqual(result['total_charged_transport_reservations'],481) # prior child241 + active240
        self.assertEqual(sum(e['event']=='start' for e in w._ledger(self.child,plan)),240)
        self.assertFalse((self.child/'batches/batch_000004/pilot.sqlite').exists())
        nofetch=Mock(side_effect=AssertionError('Finished next80 cannot request batch4'))
        again=self.run_trial(nofetch);nofetch.assert_not_called()
        self.assertEqual(again['saved_active_rows'],240)
        self.assertFalse(list(self.child.rglob('review_annotations.json')))
        self.assert_prefix_preserved()

    def test_inherited_history_risk_and_transport_context_not_reset(self):
        self.prepare();c,plan,status=successor.inspect(self.root)
        self.assertEqual(plan['seed_context'],self.source_plan['seed_context'])
        seed=plan['seed_context']
        self.assertEqual(len(seed['source_history']),79)
        self.assertEqual(len(w.load_history_index(seed['history_index'])),241)
        self.assertEqual(seed['last_transport_finish'],self.source_plan['seed_context']['last_transport_finish'])
        self.assertEqual(status['total_charged_transport_reservations'],401)
        for p in sorted((self.source_child/'row_checks').glob('*.json')):
            old=w.load(p)['record'];new=w.load(self.child/'row_checks'/p.name)['record']
            self.assertEqual(old['sample_id'],new['sample_id'])
            self.assertEqual(old['fields_sha256'],new['fields_sha256'])
            self.assertEqual(old['snapshot_sha256'],new['snapshot_sha256'])
        self.assert_prefix_preserved()

    def test_retry_budget_allows_at_most240_charged_calls_for80_urls(self):
        self.prepare();attempts={}
        def retry(url,timeout,**kw):
            attempts[url]=attempts.get(url,0)+1
            if attempts[url]==1:return {**fixtures.response(url,timeout),'status':None,'error':'operation timed out','text':'Synthetic timeout evidence'}
            if attempts[url]==2:return {**fixtures.response(url,timeout),'status':503,'text':'Synthetic transient service evidence'}
            return fixtures.response(url,timeout)
        fetch=Mock(side_effect=retry);result=self.run_trial(fetch)
        self.assertEqual(fetch.call_count,240)
        self.assertEqual(len(attempts),80)
        self.assertEqual(set(attempts.values()),{3})
        self.assertEqual(result['saved_active_rows'],240)
        self.assertEqual(result['new_transport_reservations'],240)
        self.assertEqual(result['total_charged_transport_reservations'],641)
        self.assertFalse((self.child/'batches/batch_000004/pilot.sqlite').exists())
        self.assert_prefix_preserved()

    def test_terminal_response_interruption_recovers_without_duplicate_request(self):
        self.prepare();fetch=Mock(side_effect=fixtures.response)
        with patch.object(w.pilot,'save_snapshot',side_effect=KeyboardInterrupt):self.run_trial(fetch)
        self.assertEqual(fetch.call_count,1)
        result=self.run_trial(fetch)
        self.assertEqual(fetch.call_count,80)
        self.assertEqual(len({call.args[0] for call in fetch.call_args_list}),80)
        self.assertEqual(result['saved_active_rows'],240)
        self.assertEqual(result['new_transport_reservations'],80)
        self.assert_prefix_preserved()

    def test_unknown_inflight_window_halts_without_automatic_refetch(self):
        self.prepare();fetch=Mock(side_effect=KeyboardInterrupt)
        self.run_trial(fetch);result=self.run_trial(fetch)
        self.assertEqual(fetch.call_count,1)
        self.assertEqual(result['status'],'halted_no_automatic_resume')
        self.assertEqual(result['saved_active_rows'],160)
        self.assertTrue((self.child/'safety_halt.json').exists())
        self.assert_prefix_preserved()

    def test_no_explicit_authorization_or_injected_fetcher_rejected(self):
        self.prepare()
        with self.assertRaises(ValueError):self.run_trial()
        _,_,status=successor.inspect(self.root)
        self.assertEqual(status['new_transport_reservations'],0)
        self.assert_prefix_preserved()

    def test_403_halt_persists_and_second_invocation_does_not_fetch(self):
        self.prepare();fetch=Mock(side_effect=lambda u,t,**kw:{**fixtures.response(u,t),'status':403,'text':'Forbidden synthetic response'})
        result=self.run_trial(fetch);self.assertEqual(fetch.call_count,1)
        self.assertEqual(result['status'],'halted_no_automatic_resume')
        halt=w.sha_file(self.child/'safety_halt.json')
        self.run_trial(fetch);self.assertEqual(fetch.call_count,1)
        self.assertEqual(w.sha_file(self.child/'safety_halt.json'),halt)
        self.assert_prefix_preserved()

    def test_low_disk_halts_before_new_reservation(self):
        self.prepare();fetch=Mock(side_effect=fixtures.response)
        result=self.run_trial(fetch,disk_free=lambda p:0)
        fetch.assert_not_called();self.assertEqual(result['new_transport_reservations'],0)
        self.assertEqual(result['status'],'halted_no_automatic_resume')
        self.assert_prefix_preserved()

    def test_wrong_ids_reorder_rejected_before_destination(self):
        self.cfg['expected_sample_ids']=list(reversed(self.cfg['expected_sample_ids']));self.write_config()
        with self.assertRaises(ValueError):self.prepare()
        self.assertFalse(self.child.exists());self.assert_source_preserved()

    def test_wrong_batch_boundary_rejected_before_destination(self):
        self.cfg['expected_batch_id']='batch_000004';self.cfg['expected_sample_ids']=self.source_plan['batches'][3]['sample_ids'];self.write_config()
        with self.assertRaises(ValueError):self.prepare()
        self.assertFalse(self.child.exists());self.assert_source_preserved()

    def test_excessive_or_negative_call_budget_rejected_before_destination(self):
        for budget in (241,-1):
            with self.subTest(budget=budget):
                self.cfg['max_additional_transport_calls']=budget;self.write_config()
                with self.assertRaises(ValueError):self.prepare()
                self.assertFalse(self.child.exists())
        self.assert_source_preserved()

    def test_closure_bad_digest_or_acceptance_not_sufficient(self):
        self.cfg['source_closure_sha256']='0'*64;self.write_config()
        with self.assertRaises(ValueError):self.prepare()
        bad=self.base/'bad_closure.json';doc=w.load(self.closure);doc['article_acceptance']=True
        w.write(self.base,bad.name,doc);self.cfg['source_closure']=str(bad);self.cfg['source_closure_sha256']=w.sha_file(bad);self.write_config()
        with self.assertRaises(ValueError):self.prepare()
        self.assertFalse(self.child.exists());self.assert_source_preserved()

    def test_rehashed_closure_with_wrong_source_binding_rejected(self):
        for key in ('capsule_file_sha256','transport_ledger_sha256','native_databases'):
            with self.subTest(binding=key):
                doc=w.load(self.closure)
                doc['source_binding'][key]=[] if key=='native_databases' else '0'*64
                bad=self.base/(key+'_closure.json');w.write(self.base,bad.name,doc)
                self.cfg.update(source_closure=str(bad),source_closure_sha256=w.sha_file(bad));self.write_config()
                with self.assertRaises(ValueError):self.prepare()
                self.assertFalse(self.child.exists())
        self.assert_source_preserved()

    def test_frozen_queue_and_capsule_tamper_rejected_before_fetch(self):
        self.prepare();fetch=Mock(side_effect=fixtures.response)
        queue=self.child/'queue.csv';original=queue.read_bytes();queue.write_bytes(original+b'\n')
        with self.assertRaises(ValueError):self.run_trial(fetch)
        fetch.assert_not_called();queue.write_bytes(original)
        cap=self.root/'capsule.json';doc=w.load(cap);doc['trial_sample_ids']=['TC5_OUTSIDE_ORIGINAL_SCOPE'];w.write(self.root,cap.name,doc)
        with self.assertRaises(ValueError):self.run_trial(fetch)
        fetch.assert_not_called();self.assert_source_preserved()

    def test_imported_native_payload_tamper_rejected(self):
        self.prepare();p=self.child/'batches/batch_000001/pilot.sqlite'
        with sqlite3.connect(p) as db:
            row=json.loads(db.execute('SELECT payload_json FROM articles ORDER BY ordinal LIMIT 1').fetchone()[0]);row['title']='Tampered synthetic title'
            db.execute('UPDATE articles SET title=?,payload_json=? WHERE sample_id=?',(row['title'],json.dumps(row),row['sample_id']))
        with self.assertRaises(ValueError):successor.inspect(self.root)
        self.assert_source_preserved()

    def test_completed_noop_rejects_deleted_halt_and_state_reset_with_receipt(self):
        self.prepare();fetch=Mock(side_effect=fixtures.response)
        finished=self.run_trial(fetch)
        self.assertEqual(finished['saved_active_rows'],240)
        self.assertEqual(fetch.call_count,80)
        plan=w.load(self.child/'continuous_plan.json')
        w._halt(self.child,plan,'synthetic_completed_successor_halt')
        halt=self.child/'safety_halt.json';raw=halt.read_bytes()
        nofetch=Mock(side_effect=AssertionError('Completed halted successor must not fetch'))
        self.assertEqual(self.run_trial(nofetch)['status'],'halted_no_automatic_resume')
        self.assertEqual(halt.read_bytes(),raw);nofetch.assert_not_called()
        halt.unlink()
        with self.assertRaises(ValueError):successor.inspect(self.root)
        with self.assertRaises(ValueError):self.run_trial(nofetch)
        nofetch.assert_not_called()
        # A reset status must not erase the independent permanent halt receipt.
        halt.write_bytes(raw);w._state(self.child,plan,w.PENDING)
        with self.assertRaises(ValueError):successor.inspect(self.root)
        halt.unlink()
        with self.assertRaises(ValueError):self.run_trial(nofetch)
        nofetch.assert_not_called();self.assert_prefix_preserved()

    def test_declared_closure_optional_hashes_are_checked_even_with_fresh_closure_sha(self):
        expected={'queue_sha256':w.sha_file(self.source_child/'queue.csv'),
                  'transport_state_sha256':w.sha_file(self.source_child/'transport_state.json'),
                  'continuous_state_sha256':w.sha_file(self.source_child/'continuous_state.json')}
        for key in expected:
            with self.subTest(binding=key):
                doc=w.load(self.closure);doc['source_binding'].update(expected);doc['source_binding'][key]='0'*64
                bad=self.base/(key+'_closure.json');w.write(self.base,bad.name,doc)
                self.cfg.update(source_closure=str(bad),source_closure_sha256=w.sha_file(bad));self.write_config()
                with self.assertRaises(ValueError):self.prepare()
                self.assertFalse(self.child.exists())
        valid=self.base/'fully_bound_closure.json';doc=w.load(self.closure);doc['source_binding'].update(expected)
        w.write(self.base,valid.name,doc);self.cfg.update(source_closure=str(valid),source_closure_sha256=w.sha_file(valid));self.write_config()
        self.prepare();_,_,status=successor.inspect(self.root)
        self.assertEqual(status['saved_active_rows'],160);self.assertEqual(status['new_transport_reservations'],0)
        self.assert_prefix_preserved()

    def test_successor_destination_under_source_rejected(self):
        nested=self.source_child/'should_not_exist'
        self.cfg.update(isolated_media=str(nested),new_child=str(nested/'data/00-newspaper_data/crawler/pilots/Kevin/tiempo_continuous_v5/next80'))
        self.write_config()
        with self.assertRaises(ValueError):self.prepare()
        self.assertFalse(nested.exists());self.assert_source_preserved()


if __name__=='__main__':unittest.main()

"""Offline659/661 recovery and inherited400 proof; generated transport/receipts only."""
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import Mock,patch
import test_tiempo_remaining_campaign as cf
import test_tiempo_continuous_v5 as fixtures
import test_tiempo_source_gap_recovery as receipt_fixture
from crawler_core import tiempo_continuous_v5 as w
from crawler_core import tiempo_remaining_campaign as campaign
from crawler_core import tiempo_resumable_worker as worker
from crawler_core import tiempo_source_classification_recovery as recovery


from test_tiempo_source_encoding import encoding_response

class EncodingRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old=old=cf.RemainingCampaignTests('runTest');old.setUp();cls.addClassCleanup(old.doCleanups)
        old.build(total=1611,chunk=801)
        cls.donor=old.campaign_root;cls.donor_child=campaign.child_path(old.m,2)
        queue=w.readcsv(old.m['parts'][0]['path']);cls.source_ids=[queue[i-1]['sample_id'] for i in (595,629,659)]
        fault_urls={queue[i-1]['url'] for i in (595,629,659)};service_url=queue[378]['url']
        def response(url,timeout,**kwargs):
            if url==service_url:return {**fixtures.response(url,timeout),'status':500}
            return encoding_response(url,timeout) if url in fault_urls else fixtures.response(url,timeout)
        with old.synthetic_reading_gate():state=old.execute(Mock(side_effect=response))
        if state['status']!='technical_stop_requires_investigation':raise AssertionError(state)
        counts=campaign._counts(cls.donor_child,w.load(cls.donor_child/'continuous_plan.json'))
        if counts!={'saved':659,'calls':661,'pending_native_attempts':0,'open_transport':False}:raise AssertionError(counts)
        if w.load(cls.donor_child/'safety_halt.json')['reason']!='three_unexplained_rows_in_rolling80':raise AssertionError('wrong synthetic stop')
        cls.next_id=queue[659]['sample_id'];cls.next_url=queue[659]['url']
        cls.hashes={str(p):w.sha_file(p) for p in cls.donor.rglob('*') if p.is_file() and p.name!='.pilot.lock'}

    def setUp(self):
        self.base=self.old.base/self._testMethodName;self.base.mkdir();self.campaign_root=self.base/'successor';self.config=self.base/'config.json'
        self.clock=fixtures.Clock();self.clock.t=self.old.clock.now()+100
        plan=w.load(self.donor_child/'continuous_plan.json');prefix=worker.inherited_prefix_evidence(self.donor_child,plan,659);rows={x['row']['sample_id']:x for x in prefix['rows']}
        w.write(self.base,'synthetic_reading.json',{'human_approval':False,'note':'SYNTHETIC TEST ONLY; no real source reading or gate approval'})
        records=[]
        for sid in self.source_ids:
            x=rows[sid];records.append({'sample_id':sid,'raw':campaign._bound(self.donor_child/'batches'/x['batch_id']/x['row']['snapshot_path']),
                'native_row_check':campaign._bound(self.donor_child/'row_checks'/(sid+'.json')),
                'reading_evidence':campaign._bound(self.base/'synthetic_reading.json')})
        w.write(self.base,'source_review.json',{'author':'Kevin','human_approval':False,'article_acceptance':False,'new_checkpoint_reading_credit':0,'records':records})
        self.cfg={'root':str(self.campaign_root),'donor_root':str(self.donor),'donor_code_root':str(Path(__file__).resolve().parents[3]),
            'expected_child_index':2,'expected_saved':659,'expected_calls':661,'next_sample_id':self.next_id,
            'expected_halt_reason':'three_unexplained_rows_in_rolling80','source_sample_ids':self.source_ids,'synthetic_fixture':True,
            'source_review':campaign._bound(self.base/'source_review.json'),'donor_campaign_sha256':w.sha_file(self.donor/'campaign.json'),
            'donor_master_halt_sha256':w.sha_file(self.donor/'technical_stop.json'),'donor_native_halt_sha256':w.sha_file(self.donor_child/'safety_halt.json')}
        w.write(self.base,self.config.name,self.cfg)

    def prepare(self):
        with contextlib.redirect_stdout(io.StringIO()):result=recovery.prepare(self.config)
        self.m,_=campaign.read_bound(self.campaign_root,full=True);self.child=campaign.child_path(self.m,2);return result
    execute=receipt_fixture.SourceGapRecoveryTests.execute
    receipt=receipt_fixture.SourceGapRecoveryTests.receipt
    def selection(self,rows=800,index=2):return self.campaign_root/f'reviews/plan_{index:06d}'/f'checkpoint_{rows:08d}'/f'selection_{rows:08d}.json'
    def originals(self):
        for p,h in self.hashes.items():self.assertEqual(w.sha_file(p),h,p)

    def test659_to800_inherits400_without_recount_or_duplicate_request(self):
        self.prepare();plan=w.load(self.child/'continuous_plan.json');prefix=worker.inherited_prefix_evidence(self.child,plan,659)
        proof=w.load(self.m['source_classification_recovery']['provenance']['path']);self.assertEqual(len(proof['inherited_checkpoint_gates']),1)
        self.assertEqual(proof['inherited_checkpoint_gates'][0]['rows'],400);self.assertEqual(proof['new_actual_ai_read_count'],0)
        self.assertEqual(len((self.child/'transport_calls.jsonl').read_bytes().splitlines()),1322)
        self.assertEqual((self.child/'continuous_plan.json').read_bytes(),(self.donor_child/'continuous_plan.json').read_bytes())
        summary=w.load(self.child/'source_classification_summaries/saved_00000659.json');self.assertEqual(summary['classified_encoding_correction_count'],3);self.assertEqual(summary['classified_source_gap_count'],0)
        for sid in self.source_ids:
            doc=w.load(self.child/'source_classifications'/(sid+'.json'));self.assertEqual(doc['effective_outcome'],'article_candidate');self.assertTrue(doc['article_candidate']);self.assertIsNone(doc['source_gap_kind']);self.assertIsNotNone(doc['correction_kind'])
        fetch=Mock(side_effect=fixtures.response);state=self.execute(fetch);self.assertEqual(state['status'],'paused_safe',state);self.assertEqual(fetch.call_count,141);self.assertEqual(fetch.call_args_list[0].args[0],self.next_url)
        gates=campaign._checkpoint_gate_events(self.m,campaign.events(self.campaign_root),2);self.assertEqual(len(gates),1);self.assertEqual(gates[0]['kind'],'checkpoint_gate_inherited');self.assertEqual(gates[0]['new_actual_ai_read_count'],0)
        self.assertFalse(self.selection(400).exists());self.assertTrue(self.selection().exists())
        selection=w.load(self.selection());old_coverage=proof['inherited_checkpoint_gates'][0]['coverage']
        self.assertIn(old_coverage,selection['history']['coverage_seals'])
        old_ids={r['sample_id'] for r in w.load(old_coverage['path'])['records']}
        self.assertTrue(old_ids.issubset(set(selection['history']['distinct_actual_ai_read_ids'])))
        self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,141)
        self.receipt(self.selection());self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,142)
        self.receipt(self.selection(801));self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,151)
        self.receipt(self.selection(9,3));self.assertEqual(self.execute(fetch,resume=True)['status'],'frozen_queue_processed_pending_coverage_review')
        after=worker.inherited_prefix_evidence(self.child,plan,659)
        for k in recovery.PREFIX_KEYS:self.assertEqual(prefix[k],after[k])
        self.originals()

    def test_saved_response_interruption_reuse_and_native_safe_pause(self):
        self.prepare();fetch=Mock(side_effect=fixtures.response)
        kw={'max_batches':25,'fetcher':fetch,'clock':self.clock.now,'sleep':self.clock.sleep,'stop_at_saved_rows':660,
            'source_classification_policy':self.m['source_classification_recovery']['policy'],'install_signal_handlers':False}
        with contextlib.redirect_stdout(io.StringIO()):
            with patch.object(w.pilot,'save_snapshot',side_effect=KeyboardInterrupt):state=worker.run(self.child,self.m['media'],**kw)
            self.assertEqual(state['status'],'interrupted_requires_explicit_invocation');state=worker.run(self.child,self.m['media'],**kw)
        self.assertEqual(fetch.call_count,1);self.assertTrue(state['checkpoint_boundary_reached'])
        def pause(u,t,**k):campaign.request_pause(self.campaign_root);return fixtures.response(u,t)
        p=Mock(side_effect=pause);self.assertEqual(self.execute(p)['status'],'paused_safe');self.assertEqual(p.call_count,1)
        f=Mock(side_effect=fixtures.response);self.execute(f,resume=True);self.assertEqual(f.call_count,139);self.assertEqual(campaign._counts(self.child,w.load(self.child/'continuous_plan.json'))['calls'],802);self.originals()

    def test_new_identity_fault_still_stops(self):
        self.prepare();fetch=Mock(side_effect=lambda u,t,**k:{**fixtures.response(u,t),'final_url':'https://outside.example/forbidden'})
        self.assertEqual(self.execute(fetch)['status'],'technical_stop_requires_investigation');self.assertEqual(fetch.call_count,1);self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,1);self.originals()

    def test_source_reading_or_inherited_gate_tamper_blocks_before_requests(self):
        self.prepare();m=dict(self.m);m['source_classification_recovery']=dict(m['source_classification_recovery']);m['source_classification_recovery']['inherited_checkpoint_gates']=[]
        with self.assertRaisesRegex(ValueError,'Inherited actual checkpoint'):recovery.verify(m)
        review=w.load(self.base/'source_review.json');review['new_checkpoint_reading_credit']=1;w.write(self.base,'source_review.json',review)
        fetch=Mock(side_effect=fixtures.response)
        with self.assertRaises(ValueError):self.execute(fetch)
        fetch.assert_not_called();self.originals()

if __name__=='__main__':unittest.main()

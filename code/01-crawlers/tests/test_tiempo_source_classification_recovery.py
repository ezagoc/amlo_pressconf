"""Generated offline campaigns test feature-based334 recovery and real native storage."""
import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crawler_core import tiempo_continuous_v5 as w
from crawler_core import tiempo_remaining_campaign as campaign
from crawler_core import tiempo_resumable_worker as worker
from crawler_core import tiempo_source_classification_recovery as recovery
from crawler_core import tiempo_source_classification_policy as policy
import test_tiempo_source_gap_recovery as prior_fixture
import test_tiempo_continuous_v5 as fixtures
from test_tiempo_empty_shell import qualifying_case


def shell_response(url,timeout,**kwargs):
    slug=url.rstrip('/').split('/')[-1]
    row,raw,response,check=qualifying_case(title='Report '+slug,slug=slug,published='2024-06-01T12:01:33')
    return {**response,'status':200,'final_url':url,'text':raw.decode()}


class ClassificationRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Build a genuine prior exact-two recovery, then a NEW third source gap.
        with patch.object(prior_fixture,'empty_source',side_effect=shell_response):
            prior_fixture.SourceGapRecoveryTests.setUpClass()
        cls.addClassCleanup(prior_fixture.SourceGapRecoveryTests.doClassCleanups)
        cls.old=old=prior_fixture.SourceGapRecoveryTests('runTest');old.setUp();old.prepare()
        state=old.execute(Mock(side_effect=shell_response))
        if state['status']!='technical_stop_requires_investigation':raise AssertionError(state)
        cls.donor=old.campaign_root;cls.donor_child=old.child
        cls.source_ids=[*old.source_ids,old.next_id]
        queue=w.readcsv(old.child/'queue.csv');cls.next_id=queue[334]['sample_id'];cls.next_url=queue[334]['url']
        cls.hashes={str(p):w.sha_file(p) for p in cls.donor.rglob('*') if p.is_file() and p.name!='.pilot.lock'}
        if campaign.inspect(cls.donor)['active']['saved']!=334:raise AssertionError('Wrong donor334')

    def setUp(self):
        self.base=self.old.base/self._testMethodName;self.base.mkdir()
        self.campaign_root=self.base/'classified';self.config=self.base/'config.json'
        self.clock=fixtures.Clock();self.clock.t=self.old.clock.now()+100
        self.cfg={'root':str(self.campaign_root),'donor_root':str(self.donor),
            'donor_code_root':str(Path(__file__).resolve().parents[3]),'expected_child_index':3,
            'expected_saved':334,'expected_calls':334,'next_sample_id':self.next_id,'synthetic_fixture':True,
            'donor_campaign_sha256':w.sha_file(self.donor/'campaign.json'),
            'donor_master_halt_sha256':w.sha_file(self.donor/'technical_stop.json'),
            'donor_native_halt_sha256':w.sha_file(self.donor_child/'safety_halt.json')}
        w.write(self.base,self.config.name,self.cfg)

    def prepare(self):
        with contextlib.redirect_stdout(io.StringIO()):result=recovery.prepare(self.config)
        self.m,_=campaign.read_bound(self.campaign_root,full=True);self.child=campaign.child_path(self.m,3)
        return result

    execute=prior_fixture.SourceGapRecoveryTests.execute
    selection=prior_fixture.SourceGapRecoveryTests.selection
    receipt=prior_fixture.SourceGapRecoveryTests.receipt

    def assert_originals(self):
        for path,digest in self.hashes.items():self.assertEqual(w.sha_file(path),digest,path)

    def test_334_to400_gate_new_identity_gap_and_cross_child(self):
        self.prepare();plan=w.load(self.child/'continuous_plan.json')
        with self.assertRaisesRegex(ValueError,'New disjoint source-classification runtime required'):
            recovery.prepare(self.config)
        self.assertEqual((self.child/'continuous_plan.json').read_bytes(),(self.donor_child/'continuous_plan.json').read_bytes())
        original=worker.inherited_prefix_evidence(self.child,plan,334)
        summary=w.load(self.child/'source_classification_summaries/saved_00000334.json')
        self.assertEqual(summary['classified_source_gap_count'],3)
        # A fourth ID/URL has never appeared in the recovery acknowledgment.
        # Identical verified features, rather than its identity, allow continuation.
        count=[0]
        def response(url,timeout,**kwargs):
            count[0]+=1
            return shell_response(url,timeout) if count[0]==1 else fixtures.response(url,timeout)
        fetch=Mock(side_effect=response);state=self.execute(fetch)
        self.assertEqual(state['status'],'paused_safe',state);self.assertEqual(fetch.call_count,66)
        self.assertEqual(fetch.call_args_list[0].args[0],self.next_url)
        derived=w.load(self.child/'source_classifications'/(self.next_id+'.json'))
        self.assertTrue(derived['decision']['matched']);self.assertEqual(derived['effective_outcome'],'source_unavailable')
        self.assertFalse(derived['article_candidate']);self.assertEqual(derived['manual_review_status'],'not_reviewed')
        check=w.load(self.child/'row_checks'/(self.next_id+'.json'))['record']
        self.assertIn('missing_body',check['automatic_flags']);self.assertEqual(check['qa_status'],'error')
        self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,66)
        self.assertTrue(set(self.source_ids+[self.next_id])<=set(w.load(self.selection())['selected_ids']))
        self.receipt(self.selection());self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,67)
        self.receipt(self.selection(401));self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,71)
        other=campaign.child_path(self.m,4);seed=w.load(other/'continuous_plan.json')['seed_context']
        self.assertTrue(set(self.source_ids+[self.next_id])<=set(x['sample_id'] for x in seed['source_history']))
        annotations=seed['source_classification_history'];self.assertEqual(len(annotations),4)
        self.assertTrue(all(x['binding']['sha256'] for x in annotations))
        self.receipt(self.selection(4,4));state=self.execute(fetch,resume=True)
        self.assertEqual(state['status'],'frozen_queue_processed_pending_coverage_review',state)
        self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,71)
        current=worker.inherited_prefix_evidence(self.child,plan,334)
        for key in recovery.PREFIX_KEYS:self.assertEqual(current[key],original[key])
        self.assert_originals()

    def test_unknown_dynamic_empty_body_immediately_stops(self):
        self.prepare()
        def response(url,timeout,**kwargs):
            r=shell_response(url,timeout);r['text']=r['text'].replace('</body>','<script>fetch("/unknown-article-body")</script></body>');return r
        fetch=Mock(side_effect=response);state=self.execute(fetch)
        self.assertEqual(state['status'],'technical_stop_requires_investigation',state);self.assertEqual(fetch.call_count,1)
        self.assertEqual(w.load(self.child/'safety_halt.json')['reason'],'unclassified_source_gap')
        self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,1);self.assert_originals()

    def test_new_identity_failure_still_halts(self):
        self.prepare();fetch=Mock(side_effect=lambda u,t,**k:{**shell_response(u,t),'final_url':'https://outside.example/local/a/'})
        self.assertEqual(self.execute(fetch)['status'],'technical_stop_requires_investigation')
        self.assertEqual(fetch.call_count,1);self.assertIn('critical_identity',w.load(self.child/'safety_halt.json')['risks'])
        self.assert_originals()

    def test_low_disk_and_native_pause_restore_without_recount(self):
        self.prepare();fetch=Mock(side_effect=fixtures.response)
        state=self.execute(fetch,disk_free=lambda _:0);self.assertIn(state['status'],{'resource_pause_low_disk','resource_pause_storage_forecast'})
        fetch.assert_not_called()
        def response(url,timeout,**kwargs):
            campaign.request_pause(self.campaign_root);return fixtures.response(url,timeout)
        first=Mock(side_effect=response);self.assertEqual(self.execute(first)['status'],'paused_safe')
        self.assertEqual(first.call_count,1);second=Mock(side_effect=fixtures.response)
        self.execute(second,resume=True);self.assertEqual(second.call_count,65)
        self.assertNotIn(self.next_url,[x.args[0] for x in second.call_args_list]);self.assert_originals()

    def test_prefix_decision_tamper_blocks_before_fetch(self):
        self.prepare();path=self.child/'source_classifications'/(self.source_ids[-1]+'.json')
        doc=w.load(path);doc['decision']['matched']=False;w.write(path.parent,path.name,doc)
        fetch=Mock(side_effect=fixtures.response)
        with self.assertRaises(ValueError):self.execute(fetch)
        fetch.assert_not_called();self.assert_originals()

    def test_saved_response_reuse_after_interrupted_native_save(self):
        self.prepare();plan=w.load(self.child/'continuous_plan.json');fetch=Mock(side_effect=fixtures.response)
        kw={'max_batches':25,'fetcher':fetch,'clock':self.clock.now,'sleep':self.clock.sleep,
            'source_classification_policy':self.m['source_classification_recovery']['policy'],
            'stop_at_saved_rows':335,'install_signal_handlers':False}
        with contextlib.redirect_stdout(io.StringIO()):
            with patch.object(w.pilot,'save_snapshot',side_effect=KeyboardInterrupt):
                state=worker.run(self.child,self.m['media'],**kw)
            self.assertEqual(state['status'],'interrupted_requires_explicit_invocation')
            self.assertEqual(fetch.call_count,1)
            state=worker.run(self.child,self.m['media'],**kw)
        self.assertTrue(state['checkpoint_boundary_reached']);self.assertEqual(fetch.call_count,1)
        self.assertEqual(campaign._counts(self.child,plan)['saved'],335)
        self.assertEqual(campaign._counts(self.child,plan)['calls'],335);self.assert_originals()


class WindowPolicyTests(unittest.TestCase):
    def test_current_decision_uses_verified_evidence_without_unbound_reread(self):
        record={'sample_id':'gap','critical_flags':[],'unexplained_flags':['missing_body','unexplained_result_error'],
            'unexplained_families':['body_or_media'],'automatic_flags':['missing_body']}
        binding={'path':'must-not-be-reopened','sha256':'synthetic'}
        with patch.object(policy,'verify_decision',return_value={'decision':{'matched':True}}), \
                patch.object(policy.w,'load',side_effect=AssertionError('Unverified classification reopen')):
            self.assertIsNone(policy.trigger([record],{'gap':binding},binding,{'error':'missing_body'},{}))

    def test_explained_gap_does_not_clear_unknown_rolling_history(self):
        def rec(sid,flags):return {'sample_id':sid,'critical_flags':[],'unexplained_flags':flags,
            'unexplained_families':['body_or_media'] if flags else [],'automatic_flags':flags}
        a=rec('unknown1',['unknown_body']);gap=rec('arbitrary_gap',['missing_body','unexplained_result_error'])
        b=rec('unknown2',['unknown_body']);c=rec('unknown3',['different_problem']);c['unexplained_families']=['other_unexplained']
        binding={'path':'synthetic','sha256':'sha'};bindings={'arbitrary_gap':binding}
        # Only this control-window unit uses injected validated annotation evidence.
        # End-to-end tests above exercise the real classifier, hashes and sources.
        with patch.object(policy,'verify_decision',return_value={'decision':{'matched':True}}):
            self.assertIsNone(policy.trigger([a,gap,b],bindings,binding,{'error':None},{}))
            self.assertEqual(policy.trigger([a,gap,b,c],bindings,binding,{'error':None},{}),'three_unexplained_rows_in_rolling80')
        self.assertEqual(gap['unexplained_flags'],['missing_body','unexplained_result_error'])

    def test_native_missing_body_flag_with_inconsistent_error_fails_closed(self):
        record={'sample_id':'x','critical_flags':[],'unexplained_flags':['missing_body'],
            'unexplained_families':['body_or_media'],'automatic_flags':['missing_body']}
        self.assertEqual(policy.trigger([record],{},None,{'error':None},{}),'unclassified_source_gap')

if __name__=='__main__':unittest.main()

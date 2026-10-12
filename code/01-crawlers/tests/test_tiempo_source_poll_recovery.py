"""Offline335 successor tests; all requests and source approvals are synthetic."""
import contextlib
import io
from pathlib import Path
import unittest
from unittest.mock import Mock,patch

import test_tiempo_source_classification_recovery as prior
from test_tiempo_empty_shell import sidebar_poll
from crawler_core import tiempo_continuous_v5 as w
from crawler_core import tiempo_remaining_campaign as campaign
from crawler_core import tiempo_resumable_worker as worker
from crawler_core import tiempo_source_classification_recovery as recovery
from crawler_core import tiempo_empty_shell as classifier


def poll_response(url,timeout,**kwargs):
    r=prior.shell_response(url,timeout)
    r['text']=r['text'].replace('</body>',sidebar_poll('42.72','87654321')+'</body>')
    return r


class PollRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prior.ClassificationRecoveryTests.setUpClass()
        cls.addClassCleanup(prior.ClassificationRecoveryTests.doClassCleanups)
        cls.old=old=prior.ClassificationRecoveryTests('runTest');old.setUp();old.prepare()
        original_classifier=classifier.classify_empty_article_shell
        def old_rule_rejection(row,raw,response,check):
            result=original_classifier(row,raw,response,check)
            # Inject the previous rule's exact rejection into a synthetic donor.
            # No real record, policy or human reading is manufactured by this fixture.
            if row['sample_id']==old.next_id:
                result={**result,'matched':False,'classification':None,
                    'rejection_reasons':['unrecognized_comment_content']}
            return result
        with patch.object(classifier,'classify_empty_article_shell',side_effect=old_rule_rejection):
            state=old.execute(Mock(side_effect=poll_response))
        if state['status']!='technical_stop_requires_investigation':raise AssertionError(state)
        cls.donor=old.campaign_root;cls.donor_child=old.child
        queue=w.readcsv(old.child/'queue.csv');cls.next_id=queue[335]['sample_id'];cls.next_url=queue[335]['url']
        cls.source_ids=old.source_ids+[old.next_id]
        cls.hashes={str(p):w.sha_file(p) for p in cls.donor.rglob('*') if p.is_file() and p.name!='.pilot.lock'}

    def setUp(self):
        self.base=self.old.base/self._testMethodName;self.base.mkdir()
        self.campaign_root=self.base/'successor';self.config=self.base/'config.json'
        self.clock=prior.fixtures.Clock();self.clock.t=self.old.clock.now()+100
        self.cfg={'root':str(self.campaign_root),'donor_root':str(self.donor),
            'donor_code_root':str(Path(__file__).resolve().parents[3]),'expected_child_index':3,
            'expected_saved':335,'expected_calls':335,'next_sample_id':self.next_id,'synthetic_fixture':True,
            'donor_campaign_sha256':w.sha_file(self.donor/'campaign.json'),
            'donor_master_halt_sha256':w.sha_file(self.donor/'technical_stop.json'),
            'donor_native_halt_sha256':w.sha_file(self.donor_child/'safety_halt.json')}
        w.write(self.base,self.config.name,self.cfg)

    def prepare(self):
        with contextlib.redirect_stdout(io.StringIO()):result=recovery.prepare(self.config)
        self.m,_=campaign.read_bound(self.campaign_root,full=True);self.child=campaign.child_path(self.m,3)
        return result

    execute=prior.ClassificationRecoveryTests.execute
    selection=prior.ClassificationRecoveryTests.selection
    receipt=prior.ClassificationRecoveryTests.receipt
    assert_originals=prior.ClassificationRecoveryTests.assert_originals

    def test_335_prefix_old_rejection_preserved_and_actual400_gate(self):
        self.prepare();plan=w.load(self.child/'continuous_plan.json')
        proof=w.load(self.m['source_classification_recovery']['provenance']['path'])
        original_pre=w.load(w.load(self.donor/'campaign.json')['preflight']['path'])
        successor_pre=w.load(self.m['preflight']['path'])
        self.assertEqual(successor_pre['review_obligations']['inherited_source_gap_recovery'],
                         original_pre['review_obligations']['inherited_source_gap_recovery'])
        old_pending=original_pre['review_obligations']['native_pending_file_bindings']
        new_pending=successor_pre['review_obligations']['native_pending_file_bindings']
        self.assertEqual(new_pending[:len(old_pending)],old_pending)
        # The donor's newly frozen334 pending obligation is additionally carried;
        # preserving the older entries must not discard this later duty.
        self.assertTrue(any(b['path']==str(self.donor_child/'checkpoint_00000334/pending_source_review_samples.csv')
                            for b in new_pending))
        self.assertEqual(len(proof['prior_classification_decisions']),4)
        old=w.load(self.donor_child/'source_classifications'/(self.source_ids[-1]+'.json'))
        new=w.load(self.child/'source_classifications'/(self.source_ids[-1]+'.json'))
        self.assertFalse(old['decision']['matched']);self.assertTrue(new['decision']['matched'])
        self.assertEqual(new['effective_outcome'],'source_unavailable');self.assertFalse(new['article_candidate'])
        self.assertEqual((self.child/'continuous_plan.json').read_bytes(),(self.donor_child/'continuous_plan.json').read_bytes())
        prefix=worker.inherited_prefix_evidence(self.child,plan,335)
        with self.assertRaises(ValueError):recovery.prepare(self.config)
        fetch=Mock(side_effect=poll_response);state=self.execute(fetch)
        self.assertEqual(state['status'],'paused_safe');self.assertEqual(fetch.call_count,65)
        self.assertEqual(fetch.call_args_list[0].args[0],self.next_url)
        self.assertEqual(campaign._counts(self.child,plan)['saved'],400)
        self.assertEqual(campaign._counts(self.child,plan)['calls'],400)
        self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,65)
        self.assertTrue(set(self.source_ids)<=set(w.load(self.selection())['selected_ids']))
        self.receipt(self.selection());self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,66)
        current=worker.inherited_prefix_evidence(self.child,plan,335)
        for key in recovery.PREFIX_KEYS:self.assertEqual(current[key],prefix[key])
        self.assert_originals()

    def test_pause_restart_and_saved_response_reuse(self):
        self.prepare();plan=w.load(self.child/'continuous_plan.json');fetch=Mock(side_effect=prior.fixtures.response)
        kw={'max_batches':25,'fetcher':fetch,'clock':self.clock.now,'sleep':self.clock.sleep,
            'source_classification_policy':self.m['source_classification_recovery']['policy'],
            'stop_at_saved_rows':336,'install_signal_handlers':False}
        with contextlib.redirect_stdout(io.StringIO()):
            with patch.object(w.pilot,'save_snapshot',side_effect=KeyboardInterrupt):state=worker.run(self.child,self.m['media'],**kw)
            self.assertEqual(state['status'],'interrupted_requires_explicit_invocation')
            state=worker.run(self.child,self.m['media'],**kw)
        self.assertEqual(fetch.call_count,1);self.assertTrue(state['checkpoint_boundary_reached'])
        def pause(url,timeout,**kwargs):
            campaign.request_pause(self.campaign_root);return prior.fixtures.response(url,timeout)
        f=Mock(side_effect=pause);self.assertEqual(self.execute(f)['status'],'paused_safe');self.assertEqual(f.call_count,1)
        g=Mock(side_effect=prior.fixtures.response);self.execute(g,resume=True);self.assertEqual(g.call_count,63)
        self.assertEqual(campaign._counts(self.child,plan)['calls'],400);self.assert_originals()

    def test_frozen_donor_subprocess_failure_blocks_before_copy(self):
        result=Mock(returncode=1,stderr='synthetic frozen donor hash mismatch',stdout='')
        with patch.object(recovery.subprocess,'run',return_value=result):
            with self.assertRaisesRegex(ValueError,'Frozen donor classification validation failed'):self.prepare()
        self.assertFalse(self.campaign_root.exists());self.assert_originals()

    def test_unknown_comment_remains_technical_stop(self):
        self.prepare()
        def unknown(url,timeout,**kwargs):
            r=poll_response(url,timeout);r['text']=r['text'].replace('</article>','<!-- Actual omitted article detail. --></article>');return r
        fetch=Mock(side_effect=unknown);state=self.execute(fetch)
        self.assertEqual(state['status'],'technical_stop_requires_investigation');self.assertEqual(fetch.call_count,1)
        self.assertEqual(w.load(self.child/'safety_halt.json')['reason'],'unclassified_source_gap')
        self.assert_originals()


if __name__=='__main__':unittest.main()

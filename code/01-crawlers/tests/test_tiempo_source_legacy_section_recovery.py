"""Offline340 successor tests; transport and gate receipts are synthetic only."""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import unittest
from unittest.mock import Mock, patch

import test_tiempo_source_classification_recovery as prior
import test_tiempo_source_representation_recovery as prior_fixture
from test_tiempo_empty_shell import qualifying_case
from crawler_core import tiempo_continuous_v5 as w
from crawler_core import tiempo_remaining_campaign as campaign
from crawler_core import tiempo_resumable_worker as worker
from crawler_core import tiempo_source_classification_recovery as recovery
from crawler_core import tiempo_empty_shell as classifier


def legacy_response(url, timeout, **kwargs):
    slug=url.rstrip('/').split('/')[-1]
    _,raw,response,_=qualifying_case(title='Report '+slug, slug=slug,
        published='2024-06-01T12:01:33', section='videos')
    return {**response,'status':200,'final_url':url,'text':raw.decode('utf-8')}


@unittest.skipUnless(os.environ.get('TIEMPO_EMPTY_SHELL_REAL_BATCH'), 'Explicit saved local fixture for prior lineage required; no HTTP.')
class LegacySectionRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prior_fixture.RepresentationRecoveryTests.setUpClass()
        cls.addClassCleanup(prior_fixture.RepresentationRecoveryTests.doClassCleanups)
        cls.old=old=prior_fixture.RepresentationRecoveryTests('runTest');old.setUp();old.prepare()
        queue=w.readcsv(old.child/'queue.csv');stop_id=queue[339]['sample_id']
        original=classifier.classify_empty_article_shell
        def previous_rule(row,raw,response,check):
            result=original(row,raw,response,check)
            if row['sample_id']==stop_id:
                result={**result,'matched':False,'classification':None,
                    'rejection_reasons':['classification_input_rejected:unrecognized_article_route']}
            return result
        # The old helper rejection is simulated only in this isolated donor.
        # Native extraction and source flags are never injected or overwritten.
        with patch.object(classifier,'classify_empty_article_shell',side_effect=previous_rule):
            fetch=Mock(side_effect=legacy_response);state=old.execute(fetch)
        if state['status']!='technical_stop_requires_investigation' or fetch.call_count!=1:
            raise AssertionError(state)
        cls.donor=old.campaign_root;cls.donor_child=old.child
        cls.next_id=queue[340]['sample_id'];cls.next_url=queue[340]['url']
        cls.source_ids=old.source_ids+[stop_id]
        cls.hashes={str(p):w.sha_file(p) for p in cls.donor.rglob('*') if p.is_file() and p.name!='.pilot.lock'}

    def setUp(self):
        self.base=self.old.base/self._testMethodName;self.base.mkdir()
        self.campaign_root=self.base/'successor';self.config=self.base/'config.json'
        self.clock=prior.fixtures.Clock();self.clock.t=self.old.clock.now()+100
        self.cfg={'root':str(self.campaign_root),'donor_root':str(self.donor),
            'donor_code_root':str(Path(__file__).resolve().parents[3]),'expected_child_index':3,
            'expected_saved':340,'expected_calls':340,'next_sample_id':self.next_id,'synthetic_fixture':True,
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

    def test_340_preserved_unseen_legacy_urls_and_synthetic400_gate(self):
        self.prepare();plan=w.load(self.child/'continuous_plan.json')
        proof=w.load(self.m['source_classification_recovery']['provenance']['path'])
        before=w.load(w.load(self.donor/'campaign.json')['preflight']['path'])['review_obligations']
        after=w.load(self.m['preflight']['path'])['review_obligations']
        self.assertEqual(after['inherited_source_gap_recovery'],before['inherited_source_gap_recovery'])
        pending=before['native_pending_file_bindings']
        self.assertEqual(after['native_pending_file_bindings'][:len(pending)],pending)
        self.assertTrue(any(x['path']==str(self.donor_child/'checkpoint_00000339/pending_source_review_samples.csv')
                            for x in after['native_pending_file_bindings']))
        self.assertEqual(len(proof['prior_classification_decisions']),9)
        old=w.load(self.donor_child/'source_classifications'/(self.source_ids[-1]+'.json'))
        new=w.load(self.child/'source_classifications'/(self.source_ids[-1]+'.json'))
        self.assertFalse(old['decision']['matched']);self.assertTrue(new['decision']['matched'])
        self.assertEqual(new['effective_outcome'],'source_unavailable');self.assertFalse(new['article_candidate'])
        self.assertEqual((self.child/'continuous_plan.json').read_bytes(),(self.donor_child/'continuous_plan.json').read_bytes())
        oldledger=(self.donor_child/'transport_calls.jsonl').read_bytes()
        self.assertEqual(len(oldledger.splitlines()),680)
        self.assertEqual((self.child/'transport_calls.jsonl').read_bytes(),oldledger)
        prefix=worker.inherited_prefix_evidence(self.child,plan,340)
        with self.assertRaises(ValueError):recovery.prepare(self.config)
        fetch=Mock(side_effect=legacy_response);state=self.execute(fetch)
        self.assertEqual(state['status'],'paused_safe',state);self.assertEqual(fetch.call_count,60)
        self.assertEqual(fetch.call_args_list[0].args[0],self.next_url)
        derived=w.load(self.child/'source_classifications'/(self.next_id+'.json'))
        native=w.load(self.child/'row_checks'/(self.next_id+'.json'))['record']
        self.assertTrue(derived['decision']['matched']);self.assertEqual(derived['native_error'],'missing_body')
        self.assertEqual(derived['effective_outcome'],'source_unavailable');self.assertFalse(derived['article_candidate'])
        self.assertFalse(native['recognized_video_only']);self.assertIn('missing_body',native['unexplained_flags'])
        with sqlite3.connect(derived['database']) as db:
            row=json.loads(db.execute('SELECT payload_json FROM articles WHERE sample_id=?',(self.next_id,)).fetchone()[0])
        self.assertEqual(row['section'],'Videos');self.assertEqual(row['article_kind'],'article')
        self.assertIsNone(row['main_text']);self.assertEqual(row['qa_status'],'error')
        self.assertEqual(campaign._counts(self.child,plan)['saved'],400)
        self.assertEqual(campaign._counts(self.child,plan)['calls'],400)
        self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,60)
        self.assertTrue(set(self.source_ids)<=set(w.load(self.selection())['selected_ids']))
        # This is a labeled synthetic fixture receipt, never real AI reading.
        self.receipt(self.selection());self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,61)
        current=worker.inherited_prefix_evidence(self.child,plan,340)
        for key in recovery.PREFIX_KEYS:self.assertEqual(current[key],prefix[key])
        self.assertTrue((self.child/'transport_calls.jsonl').read_bytes().startswith(oldledger))
        self.assert_originals()

    def test_pause_restart_and_saved_response_reuse(self):
        self.prepare();plan=w.load(self.child/'continuous_plan.json');fetch=Mock(side_effect=prior.fixtures.response)
        kw={'max_batches':25,'fetcher':fetch,'clock':self.clock.now,'sleep':self.clock.sleep,
            'source_classification_policy':self.m['source_classification_recovery']['policy'],
            'stop_at_saved_rows':341,'install_signal_handlers':False}
        with contextlib.redirect_stdout(io.StringIO()):
            with patch.object(w.pilot,'save_snapshot',side_effect=KeyboardInterrupt):state=worker.run(self.child,self.m['media'],**kw)
            self.assertEqual(state['status'],'interrupted_requires_explicit_invocation')
            state=worker.run(self.child,self.m['media'],**kw)
        self.assertEqual(fetch.call_count,1);self.assertTrue(state['checkpoint_boundary_reached'])
        def pause(url,timeout,**kwargs):
            campaign.request_pause(self.campaign_root);return prior.fixtures.response(url,timeout)
        f=Mock(side_effect=pause);self.assertEqual(self.execute(f)['status'],'paused_safe');self.assertEqual(f.call_count,1)
        g=Mock(side_effect=prior.fixtures.response);self.execute(g,resume=True);self.assertEqual(g.call_count,58)
        self.assertEqual(campaign._counts(self.child,plan)['calls'],400);self.assert_originals()

    def test_frozen_donor_failure_blocks_before_copy(self):
        result=Mock(returncode=1,stderr='synthetic frozen donor mismatch',stdout='')
        with patch.object(recovery.subprocess,'run',return_value=result):
            with self.assertRaisesRegex(ValueError,'Frozen donor classification validation failed'):self.prepare()
        self.assertFalse(self.campaign_root.exists());self.assert_originals()

    def test_unknown_media_does_not_become_legacy_video_success(self):
        self.prepare()
        def unknown(url,timeout,**kwargs):
            r=legacy_response(url,timeout)
            r['text']=r['text'].replace('</article>','<iframe src="https://unknown.example/player/123"></iframe></article>')
            return r
        fetch=Mock(side_effect=unknown);state=self.execute(fetch)
        self.assertEqual(state['status'],'technical_stop_requires_investigation');self.assertEqual(fetch.call_count,1)
        self.assertFalse(w.load(self.child/'source_classifications'/(self.next_id+'.json'))['decision']['matched'])
        self.assert_originals()

    def test_real_title_disagreement_still_stops(self):
        self.prepare()
        def wrong(url,timeout,**kwargs):
            r=legacy_response(url,timeout)
            r['text']=re.sub(r'(<h1\b[^>]*>).*?(</h1>)',r'\1A genuinely different title\2',r['text'],count=1,flags=re.S)
            return r
        fetch=Mock(side_effect=wrong);state=self.execute(fetch)
        self.assertEqual(state['status'],'technical_stop_requires_investigation');self.assertEqual(fetch.call_count,1)
        self.assertFalse(w.load(self.child/'source_classifications'/(self.next_id+'.json'))['decision']['matched'])
        self.assert_originals()

    def test_real_identity_error_still_stops(self):
        self.prepare()
        fetch=Mock(side_effect=lambda u,t,**k:{**legacy_response(u,t),'final_url':'https://outside.example/other-article/'})
        state=self.execute(fetch)
        self.assertEqual(state['status'],'technical_stop_requires_investigation');self.assertEqual(fetch.call_count,1)
        self.assertIn('critical_identity',w.load(self.child/'safety_halt.json')['risks'])
        self.assert_originals()


if __name__=='__main__':unittest.main()

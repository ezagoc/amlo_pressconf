"""Offline375 image-reference delta tests; no production requests or approvals."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import unittest
from unittest.mock import Mock, patch

import test_tiempo_source_classification_recovery as prior
import test_tiempo_source_share_format_recovery as prior_fixture
from test_tiempo_empty_shell import header_image_case
from crawler_core import tiempo_continuous_v5 as w
from crawler_core import tiempo_remaining_campaign as campaign
from crawler_core import tiempo_resumable_worker as worker
from crawler_core import tiempo_source_classification_recovery as recovery
from crawler_core import tiempo_source_classification_policy as policy
from crawler_core import tiempo_empty_shell as classifier


def image_response(url, timeout, **kwargs):
    slug=url.rstrip('/').split('/')[-1]
    _,raw,response,_=header_image_case(title='Report '+slug,slug=slug,
        published='2024-06-01T12:01:33',image_id='765432',image_name='principal_fixture.jpg')
    return {**response,'status':200,'final_url':url,'text':raw.decode('utf-8')}


@unittest.skipUnless(os.environ.get('TIEMPO_EMPTY_SHELL_REAL_BATCH'), 'Explicit saved local prior source required; no HTTP.')
class ImageReferenceRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prior_fixture.ShareFormatRecoveryTests.setUpClass()
        cls.addClassCleanup(prior_fixture.ShareFormatRecoveryTests.doClassCleanups)
        cls.old=old=prior_fixture.ShareFormatRecoveryTests('runTest');old.setUp();old.prepare()
        queue=w.readcsv(old.child/'queue.csv');stop_id=queue[374]['sample_id']
        original=classifier.classify_empty_article_shell
        def previous_rule(row,raw,response,check):
            result=original(row,raw,response,check)
            if row['sample_id']==stop_id:
                result={**result,'matched':False,'classification':None,
                    'rejection_reasons':['article_image_outside_known_ui']}
            return result
        # Preserve eight ordinary records plus twenty missing-body records in
        # this synthetic28-row segment. Do not relabel real donor outcomes.
        calls=[0]
        def response(url,timeout,**kwargs):
            calls[0]+=1
            if calls[0]<=8:return prior.fixtures.response(url,timeout)
            return image_response(url,timeout) if calls[0]==28 else prior_fixture.share_response(url,timeout)
        with patch.object(classifier,'classify_empty_article_shell',side_effect=previous_rule):
            fetch=Mock(side_effect=response);state=old.execute(fetch)
        if state['status']!='technical_stop_requires_investigation' or fetch.call_count!=28:
            raise AssertionError(state)
        cls.donor=old.campaign_root;cls.donor_child=old.child
        cls.next_id=queue[375]['sample_id'];cls.next_url=queue[375]['url']
        cls.source_ids=old.source_ids+[x['sample_id'] for x in queue[355:375]]
        cls.hashes={str(p):w.sha_file(p) for p in cls.donor.rglob('*') if p.is_file() and p.name!='.pilot.lock'}

    def setUp(self):
        self.base=self.old.base/self._testMethodName;self.base.mkdir()
        self.campaign_root=self.base/'successor';self.config=self.base/'config.json'
        self.clock=prior.fixtures.Clock();self.clock.t=self.old.clock.now()+100
        self.cfg={'root':str(self.campaign_root),'donor_root':str(self.donor),
            'donor_code_root':str(Path(__file__).resolve().parents[3]),'expected_child_index':3,
            'expected_saved':375,'expected_calls':375,'next_sample_id':self.next_id,'synthetic_fixture':True,
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

    def test_375_preserved_unseen_image_refs_and_synthetic400_gate(self):
        self.prepare();plan=w.load(self.child/'continuous_plan.json')
        proof=w.load(self.m['source_classification_recovery']['provenance']['path'])
        before=w.load(w.load(self.donor/'campaign.json')['preflight']['path'])['review_obligations']
        after=w.load(self.m['preflight']['path'])['review_obligations']
        self.assertEqual(after['inherited_source_gap_recovery'],before['inherited_source_gap_recovery'])
        pending=before['native_pending_file_bindings']
        self.assertEqual(after['native_pending_file_bindings'][:len(pending)],pending)
        self.assertTrue(any(x['path']==str(self.donor_child/'checkpoint_00000347/pending_source_review_samples.csv')
                            for x in after['native_pending_file_bindings']))
        self.assertEqual(len(proof['prior_classification_decisions']),36)
        old=w.load(self.donor_child/'source_classifications'/(self.source_ids[-1]+'.json'))
        new=w.load(self.child/'source_classifications'/(self.source_ids[-1]+'.json'))
        self.assertFalse(old['decision']['matched']);self.assertTrue(new['decision']['matched'])
        self.assertEqual(new['effective_outcome'],'source_unavailable');self.assertFalse(new['article_candidate'])
        self.assertEqual((self.child/'continuous_plan.json').read_bytes(),(self.donor_child/'continuous_plan.json').read_bytes())
        oldledger=(self.donor_child/'transport_calls.jsonl').read_bytes()
        self.assertEqual(len(oldledger.splitlines()),750)
        self.assertEqual((self.child/'transport_calls.jsonl').read_bytes(),oldledger)
        prefix=worker.inherited_prefix_evidence(self.child,plan,375)
        with self.assertRaises(ValueError):recovery.prepare(self.config)
        fetch=Mock(side_effect=image_response);state=self.execute(fetch)
        self.assertEqual(state['status'],'paused_safe',state);self.assertEqual(fetch.call_count,25)
        self.assertEqual(fetch.call_args_list[0].args[0],self.next_url)
        derived=w.load(self.child/'source_classifications'/(self.next_id+'.json'))
        native=w.load(self.child/'row_checks'/(self.next_id+'.json'))['record']
        self.assertTrue(derived['decision']['matched']);self.assertEqual(derived['native_error'],'missing_body')
        self.assertEqual(derived['effective_outcome'],'source_unavailable');self.assertFalse(derived['article_candidate'])
        self.assertFalse(native['recognized_video_only']);self.assertIn('missing_body',native['unexplained_flags'])
        self.assertEqual(derived['source_gap_kind'],classifier.HEADER_IMAGE_CLASSIFICATION)
        self.assertEqual(derived['decision']['classification'],classifier.HEADER_IMAGE_CLASSIFICATION)
        image=derived['decision']['evidence']['header_image_reference']
        self.assertIn('https://static.tiempo.com.mx/uploads/imagen/imagen/765432/principal_fixture.jpg',json.dumps(image))
        self.assertIs(image['visual_content_reviewed'],False)
        self.assertIs(image['image_bytes_fetched'],False)
        for i,wrong in enumerate([classifier.CLASSIFICATION,'arbitrary_unbound_kind']):
            bad=copy.deepcopy(derived);bad['source_gap_kind']=wrong
            p=self.base/f'Bad_Derived_Kind_{i}.json';w.write(self.base,p.name,bad)
            with self.assertRaisesRegex(ValueError,'Classification outcome/status changed'):
                policy.verify_decision(campaign._bound(p),native,self.m['source_classification_recovery']['policy'])
        with sqlite3.connect(derived['database']) as db:
            row=json.loads(db.execute('SELECT payload_json FROM articles WHERE sample_id=?',(self.next_id,)).fetchone()[0])
        self.assertEqual(row['section'],'Local');self.assertEqual(row['article_kind'],'article')
        self.assertIsNone(row['main_text']);self.assertEqual(row['qa_status'],'error')
        self.assertEqual(campaign._counts(self.child,plan)['saved'],400)
        self.assertEqual(campaign._counts(self.child,plan)['calls'],400)
        self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,25)
        self.assertTrue(set(self.source_ids)<=set(w.load(self.selection())['selected_ids']))
        # This is a labeled synthetic fixture receipt, never real AI reading.
        self.receipt(self.selection());self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,26)
        current=worker.inherited_prefix_evidence(self.child,plan,375)
        for key in recovery.PREFIX_KEYS:self.assertEqual(current[key],prefix[key])
        self.assertTrue((self.child/'transport_calls.jsonl').read_bytes().startswith(oldledger))
        self.assert_originals()

    def test_pause_restart_and_saved_response_reuse(self):
        self.prepare();plan=w.load(self.child/'continuous_plan.json');fetch=Mock(side_effect=prior.fixtures.response)
        kw={'max_batches':25,'fetcher':fetch,'clock':self.clock.now,'sleep':self.clock.sleep,
            'source_classification_policy':self.m['source_classification_recovery']['policy'],
            'stop_at_saved_rows':376,'install_signal_handlers':False}
        with contextlib.redirect_stdout(io.StringIO()):
            with patch.object(w.pilot,'save_snapshot',side_effect=KeyboardInterrupt):state=worker.run(self.child,self.m['media'],**kw)
            self.assertEqual(state['status'],'interrupted_requires_explicit_invocation')
            state=worker.run(self.child,self.m['media'],**kw)
        self.assertEqual(fetch.call_count,1);self.assertTrue(state['checkpoint_boundary_reached'])
        def pause(url,timeout,**kwargs):
            campaign.request_pause(self.campaign_root);return prior.fixtures.response(url,timeout)
        f=Mock(side_effect=pause);self.assertEqual(self.execute(f)['status'],'paused_safe');self.assertEqual(f.call_count,1)
        g=Mock(side_effect=prior.fixtures.response);self.execute(g,resume=True);self.assertEqual(g.call_count,23)
        self.assertEqual(campaign._counts(self.child,plan)['calls'],400);self.assert_originals()

    def _assert_bad_image_stops(self,transform):
        self.prepare()
        def response(url,timeout,**kwargs):
            r=image_response(url,timeout);original=r['text'];r['text']=transform(original)
            self.assertNotEqual(r['text'],original,'Synthetic mutation must actually change the source')
            return r
        fetch=Mock(side_effect=response);state=self.execute(fetch)
        self.assertEqual(state['status'],'technical_stop_requires_investigation');self.assertEqual(fetch.call_count,1)
        self.assertEqual(w.load(self.child/'safety_halt.json')['reason'],'unclassified_source_gap')
        self.assertFalse(w.load(self.child/'source_classifications'/(self.next_id+'.json'))['decision']['matched'])
        self.assert_originals()

    def test_additional_article_media_remains_a_stop(self):
        self._assert_bad_image_stops(lambda s:s.replace('</article>',
            '<img src="https://static.tiempo.com.mx/uploads/imagen/imagen/123456/other.jpg" alt=""/></article>',1))

    def test_nonmatching_image_metadata_remains_a_stop(self):
        self._assert_bad_image_stops(lambda s:s.replace(
            'https://static.tiempo.com.mx/uploads/imagen/imagen/765432/principal_fixture.jpg',
            'https://static.tiempo.com.mx/uploads/imagen/imagen/765433/different.jpg',1))


if __name__=='__main__':unittest.main()

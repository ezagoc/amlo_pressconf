"""Exact source-gap successor tests. Generated fixtures only; never real HTTP/AI approval."""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawler_core import tiempo_continuous_v5 as w
from crawler_core import tiempo_remaining_campaign as campaign
from crawler_core import tiempo_resumable_worker as worker
from crawler_core import tiempo_source_gap_recovery as adapter
from crawler_core import tiempo_stage_review as review
import test_tiempo_remaining_campaign as campaign_fixtures
import test_tiempo_continuous_v5 as fixtures


def empty_source(url, timeout, **kwargs):
    result=fixtures.response(url,timeout)
    dom=BeautifulSoup(result['text'],'html.parser')
    dom.select_one('.complementos-container').clear()
    dom.select_one('blockquote p').clear()
    result['text']=str(dom)
    return result


class SourceGapRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.donor=donor=campaign_fixtures.RemainingCampaignTests('runTest')
        donor.setUp();cls.addClassCleanup(donor.doCleanups)
        donor.build(total=1207,chunk=401)
        cls.donor_child=campaign.child_path(donor.m,3)
        queue=w.readcsv(donor.m['parts'][1]['path'])
        cls.source_ids=[q['sample_id'] for q in queue[331:333]]
        urls=[q['url'] for q in queue[331:333]]
        cls.next_id=queue[333]['sample_id'];cls.next_url=queue[333]['url']
        def response(url,timeout,**kwargs):
            return empty_source(url,timeout) if url in urls else fixtures.response(url,timeout)
        with donor.synthetic_reading_gate(): state=donor.execute(Mock(side_effect=response))
        if state['status']!='technical_stop_requires_investigation': raise AssertionError(state)
        if campaign.inspect(donor.campaign_root)['active']['saved']!=333: raise AssertionError(state)
        cls.donor_hashes={str(p):w.sha_file(p) for p in donor.campaign_root.rglob('*') if p.is_file() and p.name!='.pilot.lock'}

    def setUp(self):
        self.base=self.donor.base/self._testMethodName;self.base.mkdir()
        self.campaign_root=self.base/'recovered';self.config=self.base/'config.json'
        self.clock=fixtures.Clock();self.clock.t=self.donor.clock.now()+100
        plan=w.load(self.donor_child/'continuous_plan.json')
        prefix=worker.inherited_prefix_evidence(self.donor_child,plan,333)
        sources=adapter._source_bindings(self.donor_child,plan,prefix)
        first=[];second=[]
        for s in sources:
            common={'sample_id':s['sample_id'],'actual_ai_read':True,'human_approval':False,
                    'article_acceptance':False,'research_status':'NEEDS_JOAQUIN_REVIEW'}
            first.append({**common,'bound_source':{'sha256':s['snapshot_sha256'],'payload_utf8_sha256':s['payload_sha256'],
                'fields_sha256':s['fields_sha256'],'rowcheck_sha256':s['row_check_sha256'],'attempt_id':s['attempt_id']},
                'actual_ai_source_findings':{'article_subtree_fully_read':True,'actual_prose_omission_detected':False,
                  'source_body_unavailable_in_this_saved_response':True,'unknown_article_embed_element_found':False,
                  'confirmed_video_only':False}})
            second.append({**common,**{k:s[k] for k in ('snapshot_sha256','payload_sha256','fields_sha256','row_check_sha256')},
                'diagnosis':'source_response_missing_body_no_extraction_loss','technical_blockers':[]})
        w.write(self.base,'source_fixture.json',{'records':first,'human_approval':False,'article_acceptance':False,
            'collection_gate_65_400_completed':False,'note':'GENERATED SYNTHETIC FIXTURE ONLY, NO REAL READING'})
        source_review=campaign._bound(self.base/'source_fixture.json')
        w.write(self.base,'independent_fixture.json',{'records':second,'human_approval':False,'article_acceptance':False,
            'source_review':source_review,'parser_fix_demonstrated':False,'note':'GENERATED SYNTHETIC FIXTURE ONLY'})
        self.cfg={'root':str(self.campaign_root),'donor_root':str(self.donor.campaign_root),
            'donor_code_root':str(Path(__file__).resolve().parents[3]),'expected_child_index':3,
            'expected_saved':333,'expected_calls':333,'source_sample_ids':self.source_ids,'next_sample_id':self.next_id,
            'donor_campaign_sha256':w.sha_file(self.donor.campaign_root/'campaign.json'),
            'donor_master_halt_sha256':w.sha_file(self.donor.campaign_root/'technical_stop.json'),
            'donor_native_halt_sha256':w.sha_file(self.donor_child/'safety_halt.json'),
            'synthetic_fixture':True,'source_review':source_review,
            'independent_review':campaign._bound(self.base/'independent_fixture.json')}
        w.write(self.base,self.config.name,self.cfg)

    def prepare(self):
        with contextlib.redirect_stdout(io.StringIO()): result=adapter.prepare(self.config)
        self.m,_=campaign.read_bound(self.campaign_root,full=True)
        self.child=campaign.child_path(self.m,3)
        return result

    def execute(self, fetch=None, **kwargs):
        opts={'fetcher':fetch if fetch is not None else Mock(side_effect=fixtures.response),
              'clock':self.clock.now,'sleep':self.clock.sleep,'disk_free':lambda _:10**10,
              'wait_for_review':False,'probe':Mock(side_effect=AssertionError('No real network in fixtures'))}
        opts.update(kwargs)
        with contextlib.redirect_stdout(io.StringIO()):return campaign.run(self.campaign_root,**opts)

    def selection(self,rows=400,index=3):
        return self.campaign_root/f'reviews/plan_{index:06d}'/f'checkpoint_{rows:08d}'/f'selection_{rows:08d}.json'

    def receipt(self,selection):
        doc=w.load(selection);records=[]
        for s in doc['selected_records']:
            records.append({**{k:s[k] for k in ('sample_id','snapshot_sha256','payload_sha256','row_check_sha256')},
                'actual_ai_read':True,'human_approval':False,'technical_blockers':[],
                'research_status':'NEEDS_JOAQUIN_REVIEW' if s['sample_id'] in self.source_ids else None,
                'scope':review.READ_SCOPE,'note':'SYNTHETIC TEST FIXTURE ONLY, not actual news or human approval: '+s['sample_id']})
        target=selection.parent/'receipts/synthetic_fixture.json'
        w.write(target.parent,target.name,{'schema':review.SCHEMA,'selection_sha256':doc['selection_sha256'],
            'runtime_binding_sha256':w.digest(doc['snapshot']['bindings']),'actual_ai_read_ids':[r['sample_id'] for r in records],
            'actual_ai_read_count':len(records),'human_approval':False,'technical_blockers':[],'records':records})
        return target

    def assert_donor_unchanged(self):
        for name,digest in self.donor_hashes.items():self.assertEqual(w.sha_file(name),digest,name)

    def test_prefix_replay_twice_400_gate_and_cross_child_history(self):
        self.prepare();before=campaign.inspect(self.campaign_root)
        self.assertEqual((before['active']['saved'],before['active']['calls']),(333,333))
        plan=w.load(self.child/'continuous_plan.json')
        prefix=worker.inherited_prefix_evidence(self.child,plan,333)
        fetch=Mock(side_effect=fixtures.response)
        state=self.execute(fetch);self.assertEqual(state['status'],'paused_safe',state)
        self.assertEqual(fetch.call_count,67);self.assertEqual(fetch.call_args_list[0].args[0],self.next_url)
        self.assertTrue(set(self.source_ids)<=set(w.load(self.selection())['selected_ids']))
        self.assertEqual(review.validate_gate(self.selection())['status'],'blocked_pending_actual_ai_reading')
        self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,67)
        self.receipt(self.selection());self.execute(fetch,resume=True)
        self.assertEqual(fetch.call_count,68);self.assertTrue(self.selection(401).exists())
        self.assertFalse(campaign.child_path(self.m,4).exists())
        self.receipt(self.selection(401));self.execute(fetch,resume=True)
        self.assertEqual(fetch.call_count,72)
        next_child=campaign.child_path(self.m,4);context=w.load(next_child/'continuous_plan.json')['seed_context']
        self.assertEqual([r['sample_id'] for r in context['source_history'] if r['sample_id'] in self.source_ids],self.source_ids)
        self.assertEqual(context['inherited_source_gaps'][0]['manual_review_status'],'not_reviewed')
        self.receipt(self.selection(4,4));state=self.execute(fetch,resume=True)
        self.assertEqual(state['status'],'frozen_queue_processed_pending_coverage_review',state)
        self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,72)
        after=worker.inherited_prefix_evidence(self.child,plan,333)
        for key in ('prefix_payload_sha256','prefix_attempts_sha256','prefix_articles_sha256'):self.assertEqual(prefix[key],after[key])
        for sid in self.source_ids:
            rec=w.load(self.child/'row_checks'/(sid+'.json'))['record']
            self.assertEqual(rec['manual_review_status'],'not_reviewed');self.assertIn('missing_body',rec['automatic_flags'])
        self.assert_donor_unchanged()

    def test_new_third_source_gap_still_halts(self):
        self.prepare();fetch=Mock(side_effect=empty_source);state=self.execute(fetch)
        self.assertEqual(state['status'],'technical_stop_requires_investigation',state)
        self.assertEqual(fetch.call_count,1)
        halt=w.load(self.child/'safety_halt.json');self.assertEqual(halt['sample_id'],self.next_id)
        self.assertEqual(halt['reason'],'two_consecutive_same_family_anomalies')
        original=(self.child/'safety_halt.json').read_bytes()
        self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,1)
        self.assertEqual(original,(self.child/'safety_halt.json').read_bytes());self.assert_donor_unchanged()

    def test_new_transport_failure_still_halts(self):
        self.prepare();fetch=Mock(side_effect=ConnectionError('new connection failure'))
        self.assertEqual(self.execute(fetch)['status'],'technical_stop_requires_investigation')
        self.assertEqual(fetch.call_count,1);self.assert_donor_unchanged()

    def test_new_identity_error_still_halts(self):
        self.prepare()
        fetch=Mock(side_effect=lambda u,t,**k:{**fixtures.response(u,t), 'final_url':'https://outside.example/local/article/'})
        self.assertEqual(self.execute(fetch)['status'],'technical_stop_requires_investigation')
        self.assertEqual(fetch.call_count,1)
        self.assertIn('critical_identity',w.load(self.child/'safety_halt.json')['risks'])
        self.assert_donor_unchanged()

    def test_new_unknown_embed_still_halts_without_video_approval(self):
        self.prepare()
        def response(u,t,**k):
            r=empty_source(u,t)
            r['text']=r['text'].replace('<div class="complementos-container"></div>',
                    '<div class="complementos-container"><iframe src="https://unknown.example/embed/a"></iframe></div>')
            return r
        fetch=Mock(side_effect=response)
        self.assertEqual(self.execute(fetch)['status'],'technical_stop_requires_investigation')
        self.assertEqual(fetch.call_count,1)
        check=w.load(self.child/'row_checks'/(self.next_id+'.json'))['record']
        self.assertFalse(check.get('recognized_video_only'));self.assertIn('missing_body',check['automatic_flags'])
        self.assert_donor_unchanged()

    def test_new_real_prose_omission_still_halts(self):
        self.prepare()
        def response(u,t,**k):
            r=fixtures.response(u,t)
            r['text']=r['text'].replace('</article>','<p>Additional actual prose outside recognized body.</p></article>')
            return r
        fetch=Mock(side_effect=response)
        self.assertEqual(self.execute(fetch)['status'],'technical_stop_requires_investigation')
        self.assertEqual(fetch.call_count,1)
        risks=w.load(self.child/'safety_halt.json')['risks']
        self.assertIn('unexplained_article_text_outside_recognized_containers',risks)
        self.assert_donor_unchanged()

    def test_existing_donor_export_is_verified_before_copy(self):
        with patch.object(worker,'_export_preview',return_value={'files':{}}):
            with self.assertRaisesRegex(ValueError,'export readback'):
                self.prepare()
        self.assertFalse(self.campaign_root.exists());self.assert_donor_unchanged()

    def test_investigation_cannot_assert_human_pass(self):
        path=Path(self.cfg['independent_review']['path']);doc=w.load(path)
        doc['records'][0]['human_approval']=True;w.write(path.parent,path.name,doc)
        self.cfg['independent_review']=campaign._bound(path);w.write(self.base,self.config.name,self.cfg)
        with self.assertRaisesRegex(ValueError,'review status'):
            self.prepare()
        self.assertFalse(self.campaign_root.exists());self.assert_donor_unchanged()

    def test_low_disk_starts_no_request(self):
        self.prepare();fetch=Mock(side_effect=fixtures.response)
        state=self.execute(fetch,disk_free=lambda _:0)
        self.assertIn(state['status'],{'resource_pause_low_disk','resource_pause_storage_forecast'})
        fetch.assert_not_called();self.assert_donor_unchanged()

    def test_pause_after_one_request_restarts_at_next_without_duplication(self):
        self.prepare()
        def fetch(url,timeout,**kwargs):
            campaign.request_pause(self.campaign_root)
            return fixtures.response(url,timeout)
        f=Mock(side_effect=fetch);state=self.execute(f)
        self.assertEqual(state['status'],'paused_safe',state);self.assertEqual(f.call_count,1)
        g=Mock(side_effect=fixtures.response);self.execute(g,resume=True)
        self.assertEqual(g.call_count,66);self.assertNotIn(self.next_url,[x.args[0] for x in g.call_args_list])
        self.assert_donor_unchanged()

    def test_changed_review_hash_is_rejected_before_copy(self):
        Path(self.cfg['source_review']['path']).write_text('{}')
        with self.assertRaises(ValueError):self.prepare()
        self.assertFalse(self.campaign_root.exists());self.assert_donor_unchanged()

    def test_wrong_next_identity_and_synthetic_live_mismatch_are_rejected(self):
        for key,value in [('next_sample_id',self.source_ids[0]),('synthetic_fixture',False)]:
            cfg={**self.cfg,key:value};w.write(self.base,self.config.name,cfg)
            with self.assertRaises(ValueError):self.prepare()
            self.assertFalse(self.campaign_root.exists())
        self.assert_donor_unchanged()

    def test_changed_acknowledgment_starts_no_request(self):
        self.prepare();path=Path(self.m['source_gap_recovery']['acknowledgment']['path'])
        path.write_bytes(path.read_bytes()+b'\n');fetch=Mock(side_effect=fixtures.response)
        with self.assertRaises(ValueError):self.execute(fetch)
        fetch.assert_not_called();self.assert_donor_unchanged()

    def test_source_gap_cannot_be_omitted_from_actual_gate(self):
        self.prepare();fetch=Mock(side_effect=fixtures.response);self.execute(fetch)
        receipt=self.receipt(self.selection());doc=w.load(receipt)
        doc['records']=[r for r in doc['records'] if r['sample_id']!=self.source_ids[0]]
        doc['actual_ai_read_ids']=[r['sample_id'] for r in doc['records']];doc['actual_ai_read_count']=len(doc['records'])
        w.write(receipt.parent,receipt.name,doc)
        self.assertEqual(review.validate_gate(self.selection(),[receipt])['status'],'blocked_pending_actual_ai_reading')
        self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,67)
        self.assert_donor_unchanged()

if __name__=='__main__':unittest.main()

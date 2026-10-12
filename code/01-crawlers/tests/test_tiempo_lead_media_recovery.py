"""Offline paused800 media-supplement recovery; synthetic transport/readings only."""
import contextlib,io,json,re,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import test_tiempo_remaining_campaign as cf
import test_tiempo_continuous_v5 as fixtures
import test_tiempo_source_gap_recovery as receipt_fixture
from crawler_core import tiempo_continuous_v5 as w,tiempo_remaining_campaign as campaign,tiempo_resumable_worker as worker,tiempo_stage_review as review
from crawler_core import tiempo_lead_media_recovery as recovery


def response(url,timeout,**kwargs):
    return {**fixtures.response(url,timeout),'curl_exit_code':0,'body_encoding':'utf-8','body_encoding_source':'http_charset','content_type':'text/html; charset=utf-8','body_text_limit_exceeded':False}


def lead_response(url,timeout,**kwargs):
    result=response(url,timeout)
    html=result['text'].replace('</p>Por:', '<iframe src="https://www.youtube.com/embed/R8NeB10INDo"></iframe></p>Por:')
    html=re.sub(r'<div class="complementos-container">.*?</div>', '<div class="complementos-container"></div>',html,flags=re.S)
    return {**result,'text':html}


class LeadMediaRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old=old=cf.RemainingCampaignTests('runTest');old.setUp();cls.addClassCleanup(old.doCleanups);old.build(total=1611,chunk=801)
        cls.donor=old.campaign_root;cls.donor_child=campaign.child_path(old.m,2);queue=w.readcsv(old.m['parts'][0]['path']);cls.source_ids=[queue[499]['sample_id']];cls.source_url=queue[499]['url']
        service_url=queue[378]['url'];cls.next_id=queue[800]['sample_id'];cls.next_url=queue[800]['url']
        def fetch(url,timeout,**kwargs):
            if url==service_url:return {**response(url,timeout),'status':500}
            return lead_response(url,timeout) if url==cls.source_url else response(url,timeout)
        original=review.validate_gate
        def gate(selection,paths=()):
            doc=w.load(selection)
            if doc['snapshot']['checkpoint_rows']==400:
                path=old.synthetic_reading_receipt(selection)
                if path not in paths:paths.append(path)
            else:cls.token=campaign.request_pause(cls.donor)['request_id']
            return original(selection,paths)
        with patch.object(review,'validate_gate',side_effect=gate):state=old.execute(Mock(side_effect=fetch))
        if state['status']!='paused_safe':raise AssertionError(state)
        counts=campaign._counts(cls.donor_child,w.load(cls.donor_child/'continuous_plan.json'))
        if counts!={'saved':800,'calls':802,'pending_native_attempts':0,'open_transport':False}:raise AssertionError(counts)
        cls.selection=cls.donor/'reviews/plan_000002/checkpoint_00000800/selection_00000800.json';doc=w.load(cls.selection)
        if not set(cls.source_ids)<=set(doc['selected_ids']):raise AssertionError('Lead case was not selected')
        records=[]
        for r in doc['selected_records']:
            records.append({**{k:r[k] for k in ('sample_id','snapshot_sha256','payload_sha256','row_check_sha256')},'actual_ai_read':True,'human_approval':False,'research_status':None,'scope':review.READ_SCOPE,
                'technical_blockers':['SYNTHETIC original lead-media omission'] if r['sample_id'] in cls.source_ids else [],
                'note':'SYNTHETIC FIXTURE ONLY. Generated HTML reading note is test evidence, not real news reading or human acceptance: '+r['sample_id']})
        cls.draft=cls.selection.parent/'drafts/original_blocked_draft.json';w.write(cls.draft.parent,cls.draft.name,{'schema':review.SCHEMA,'selection_sha256':doc['selection_sha256'],
            'runtime_binding_sha256':w.digest(doc['snapshot']['bindings']),'actual_ai_read_ids':[r['sample_id'] for r in records],'actual_ai_read_count':len(records),'human_approval':False,'technical_blockers':[],'records':records})
        cls.hashes={str(p):w.sha_file(p) for p in cls.donor.rglob('*') if p.is_file() and p.name!='.pilot.lock'}

    def setUp(self):
        self.base=self.old.base/self._testMethodName;self.base.mkdir();self.campaign_root=self.base/'successor';self.config=self.base/'config.json';self.clock=fixtures.Clock();self.clock.t=self.old.clock.now()+100
        native=w.load(self.donor_child/'continuous_state.json')
        self.cfg={'root':str(self.campaign_root),'donor_root':str(self.donor),'donor_code_root':str(Path(__file__).resolve().parents[3]),'synthetic_fixture':True,
            'expected_child_index':2,'expected_saved':800,'expected_calls':802,'next_sample_id':self.next_id,'donor_campaign_sha256':w.sha_file(self.donor/'campaign.json'),
            'donor_status_sha256':w.sha_file(self.donor/'status.json'),'donor_native_state_sha256':w.sha_file(self.donor_child/'continuous_state.json'),
            'donor_pause_receipt_sha256':native['pause_receipt_sha256'],'pause_request_token':self.token,'pending_selection':campaign._bound(self.selection),
            'draft_receipts':[campaign._bound(self.draft)]}
        w.write(self.base,self.config.name,self.cfg)

    def prepare(self):
        with contextlib.redirect_stdout(io.StringIO()):result=recovery.prepare(self.config)
        self.m,_=campaign.read_bound(self.campaign_root,full=True);self.child=campaign.child_path(self.m,2);return result
    execute=receipt_fixture.SourceGapRecoveryTests.execute
    def receipt(self,selection):
        path=receipt_fixture.SourceGapRecoveryTests.receipt(self,selection)
        doc=w.load(path);chosen={r['sample_id']:r for r in w.load(selection)['selected_records']}
        for record in doc['records']:
            original=chosen[record['sample_id']]
            if original.get('effective_media_correction'):
                record['effective_media_correction']=original['effective_media_correction'];record['effective_media_read']=True
        w.write(path.parent,path.name,doc)
        return path
    def selection_new(self,n=800,index=2):return self.campaign_root/f'reviews/plan_{index:06d}'/f'checkpoint_{n:08d}'/f'selection_{n:08d}.json'
    def originals(self):
        for path,digest in self.hashes.items():self.assertEqual(w.sha_file(path),digest,path)

    def test_preserves800_802_and_requires_real_gate_before801(self):
        self.prepare();plan=w.load(self.child/'continuous_plan.json');prefix=worker.inherited_prefix_evidence(self.child,plan,800)
        proof=w.load(self.m['lead_media_recovery']['provenance']['path']);self.assertFalse(proof['pending_boundary_gate_approved']);self.assertEqual(proof['new_actual_ai_read_count'],0)
        self.assertEqual(len(proof['inherited_checkpoint_gates']),1);self.assertEqual(proof['inherited_checkpoint_gates'][0]['rows'],400)
        self.assertTrue(proof['pending_actual_reading']['preserved_blockers']);self.assertEqual((self.child/'continuous_plan.json').read_bytes(),(self.donor_child/'continuous_plan.json').read_bytes())
        self.assertEqual(len((self.child/'transport_calls.jsonl').read_bytes().splitlines()),1604)
        doc=w.load(self.child/'lead_media_checks'/(self.source_ids[0]+'.json'));self.assertEqual(doc['result']['status'],'effective_media_correction')
        self.assertEqual(json.loads(doc['result']['original']['media_embeds']),[]);self.assertIn('https://www.youtube.com/embed/R8NeB10INDo',json.loads(doc['result']['effective']['media_embeds']))
        fetch=Mock(side_effect=response);self.assertEqual(self.execute(fetch)['status'],'paused_safe');fetch.assert_not_called()
        selection=self.selection_new();self.assertTrue(selection.exists());self.assertIn(self.source_ids[0],w.load(selection)['selected_ids'])
        self.assertEqual(self.execute(fetch,resume=True)['status'],'paused_safe');fetch.assert_not_called()
        self.receipt(selection);self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,1);self.assertEqual(fetch.call_args.args[0],self.next_url)
        self.receipt(self.selection_new(801));self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,10)
        self.receipt(self.selection_new(9,3));self.assertEqual(self.execute(fetch,resume=True)['status'],'frozen_queue_processed_pending_coverage_review')
        after=worker.inherited_prefix_evidence(self.child,plan,800)
        for key in recovery.PREFIX_KEYS:self.assertEqual(prefix[key],after[key])
        self.originals()

    def test_unresolved_gate_and_tampered_media_cannot_open_network(self):
        self.prepare();fetch=Mock(side_effect=response);self.execute(fetch)
        bound=self.child/'lead_media_checks'/(self.source_ids[0]+'.json');doc=w.load(bound);doc['result']['effective']['media_embeds']='[]';w.write(bound.parent,bound.name,doc)
        with self.assertRaises(ValueError):campaign.read_bound(self.campaign_root,full=True)
        fetch.assert_not_called();self.originals()

    def test_new_unsupported_lead_is_stopped_and_originals_kept(self):
        self.prepare();self.execute(Mock(side_effect=response));self.receipt(self.selection_new())
        def bad(url,timeout,**kwargs):return {**lead_response(url,timeout),'text':lead_response(url,timeout)['text'].replace('https://www.youtube.com/embed/R8NeB10INDo','javascript:unknown()')}
        fetch=Mock(side_effect=bad);state=self.execute(fetch,resume=True);self.assertEqual(state['status'],'technical_stop_requires_investigation');self.assertEqual(fetch.call_count,1)
        self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,1);self.originals()

    def test_malformed_original_draft_cannot_prepare_successor(self):
        original=w.load(self.draft);original['human_approval']=True
        path=self.base/'invalid_draft.json';w.write(path.parent,path.name,original)
        self.cfg['draft_receipts']=[campaign._bound(path)];w.write(self.base,self.config.name,self.cfg)
        with self.assertRaisesRegex(ValueError,'Pending reading draft'):recovery.prepare(self.config)
        self.assertFalse(self.campaign_root.exists());self.originals()

    def test_saved_response_interruption_reuses_call_and_draft_tamper_blocks(self):
        self.prepare();self.execute(Mock(side_effect=response));self.receipt(self.selection_new())
        fetch=Mock(side_effect=response)
        with patch.object(w.pilot,'save_snapshot',side_effect=KeyboardInterrupt):state=self.execute(fetch,resume=True)
        self.assertEqual(fetch.call_count,1)
        self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,1)
        self.assertEqual(campaign._counts(self.child,w.load(self.child/'continuous_plan.json'))['calls'],803)
        self.originals()

if __name__=='__main__':unittest.main()

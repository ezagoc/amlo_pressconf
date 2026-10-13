"""Offline bounded recovery delta: synthetic400 gate models production1600.

Unchanged checkpoint cadence is used, not mocked approval. Generated requests,
fixtures and test receipts prove no actual source reading or human acceptance.
"""
import contextlib,io,json,html,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import test_tiempo_remaining_campaign as cf
import test_tiempo_continuous_v5 as fixtures
import test_tiempo_source_gap_recovery as rf
import test_tiempo_lead_media_recovery as lf
from crawler_core import tiempo_continuous_v5 as w,tiempo_remaining_campaign as campaign,tiempo_resumable_worker as worker,tiempo_stage_review as review
from crawler_core import tiempo_media_url_recovery as recovery


def malformed_response(url,timeout,**kwargs):
    result=lf.response(url,timeout)
    # HTML is deliberately a literal source.src attribute, not visible prose.
    raw='<blockquote class="instagram-media" data-instgrm-permalink="https:/www.instagram.com/p/fixture/"><p><a href="https:/www.instagram.com/p/fixture/">Source attribute caption</a></p></blockquote><script async src="/www.instagram.com/embed.js"></script>'
    markup='<video><source src="'+html.escape(raw,quote=True)+'"></video>'
    result['text']=result['text'].replace('<div class="complementos-container">','<div class="complementos-container">'+markup)
    return result


class MediaURLRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old=old=cf.RemainingCampaignTests('runTest');old.setUp();cls.addClassCleanup(old.doCleanups);old.build(total=811,chunk=401)
        cls.donor=old.campaign_root;cls.donor_child=campaign.child_path(old.m,2);queue=w.readcsv(old.m['parts'][0]['path']);cls.source_ids=[queue[299]['sample_id']];cls.source_url=queue[299]['url'];service=queue[378]['url'];cls.next_id=queue[400]['sample_id'];cls.next_url=queue[400]['url']
        def fetch(url,timeout,**kw):
            if url==service:return {**lf.response(url,timeout),'status':500}
            return malformed_response(url,timeout) if url==cls.source_url else lf.response(url,timeout)
        original=review.validate_gate
        def hold(selection,receipts=()):
            cls.token=campaign.request_pause(cls.donor)['request_id'];return original(selection,receipts)
        with patch.object(review,'validate_gate',side_effect=hold):state=old.execute(Mock(side_effect=fetch))
        assert state['status']=='paused_safe',state
        assert campaign._counts(cls.donor_child,w.load(cls.donor_child/'continuous_plan.json'))=={'saved':400,'calls':402,'pending_native_attempts':0,'open_transport':False}
        cls.selection=cls.donor/'reviews/plan_000002/checkpoint_00000400/selection_00000400.json';doc=w.load(cls.selection);assert set(cls.source_ids)<=set(doc['selected_ids'])
        records=[{**{k:r[k] for k in ('sample_id','snapshot_sha256','payload_sha256','row_check_sha256')},'actual_ai_read':True,'human_approval':False,'research_status':None,'scope':review.READ_SCOPE,'technical_blockers':['SYNTHETIC malformed body source URL promoted to media'] if r['sample_id'] in cls.source_ids else [],'note':'SYNTHETIC GENERATED FIXTURE ONLY. No real news reading or human acceptance. Source identity: '+r['sample_id']} for r in doc['selected_records']]
        cls.draft=cls.selection.parent/'drafts/held_test_only.json';w.write(cls.draft.parent,cls.draft.name,{'schema':review.SCHEMA,'selection_sha256':doc['selection_sha256'],'runtime_binding_sha256':w.digest(doc['snapshot']['bindings']),'actual_ai_read_ids':[r['sample_id'] for r in records],'actual_ai_read_count':len(records),'human_approval':False,'technical_blockers':[],'records':records})
        cls.hashes={str(p):w.sha_file(p) for p in cls.donor.rglob('*') if p.is_file() and p.name!='.pilot.lock'}

    def setUp(self):
        self.base=self.old.base/self._testMethodName;self.base.mkdir();self.campaign_root=self.base/'successor';self.config=self.base/'config.json';self.clock=fixtures.Clock();self.clock.t=self.old.clock.now()+100
        native=w.load(self.donor_child/'continuous_state.json')
        self.cfg={'root':str(self.campaign_root),'donor_root':str(self.donor),'donor_code_root':str(Path(__file__).resolve().parents[3]),'synthetic_fixture':True,'expected_child_index':2,'expected_saved':400,'expected_calls':402,'next_sample_id':self.next_id,'donor_campaign_sha256':w.sha_file(self.donor/'campaign.json'),'donor_status_sha256':w.sha_file(self.donor/'status.json'),'donor_native_state_sha256':w.sha_file(self.donor_child/'continuous_state.json'),'donor_pause_receipt_sha256':native['pause_receipt_sha256'],'pause_request_token':self.token,'pending_selection':campaign._bound(self.selection),'draft_receipts':[campaign._bound(self.draft)]};w.write(self.base,self.config.name,self.cfg)
    def prepare(self):
        with contextlib.redirect_stdout(io.StringIO()):recovery.prepare(self.config)
        self.m,_=campaign.read_bound(self.campaign_root,full=True);self.child=campaign.child_path(self.m,2)
    execute=rf.SourceGapRecoveryTests.execute
    receipt=lf.LeadMediaRecoveryTests.receipt
    def selected(self,n=400,index=2):return self.campaign_root/f'reviews/plan_{index:06d}'/f'checkpoint_{n:08d}'/f'selection_{n:08d}.json'
    def originals(self):
        for path,digest in self.hashes.items():self.assertEqual(w.sha_file(path),digest,path)

    def test_preserved_prefix_pending_gate_saved_response_reuse_and_cross_child(self):
        self.prepare();plan=w.load(self.child/'continuous_plan.json');before=worker.inherited_prefix_evidence(self.child,plan,400);proof=w.load(self.m['media_url_recovery']['provenance']['path']);self.assertFalse(proof['pending_boundary_gate_approved']);self.assertEqual(proof['new_actual_ai_read_count'],0);self.assertTrue(proof['pending_actual_reading']['preserved_blockers']);self.assertEqual((self.child/'continuous_plan.json').read_bytes(),(self.donor_child/'continuous_plan.json').read_bytes());self.assertEqual(len((self.child/'transport_calls.jsonl').read_bytes().splitlines()),804)
        changed=w.load(self.child/'lead_media_checks'/(self.source_ids[0]+'.json'))['result'];self.assertEqual(changed['status'],'effective_media_correction');self.assertTrue(changed['quarantined_source_targets']);self.assertTrue(changed['source_media_warnings']);self.assertEqual(json.loads(changed['effective']['media_embeds']),[]);self.assertTrue(json.loads(changed['original']['media_embeds']));self.assertTrue(changed['native_other_fields_unchanged'])
        fetch=Mock(side_effect=lf.response);self.assertEqual(self.execute(fetch)['status'],'paused_safe');fetch.assert_not_called();self.assertIn(self.source_ids[0],w.load(self.selected())['selected_ids']);self.execute(fetch,resume=True);fetch.assert_not_called()
        self.receipt(self.selected())
        # A deliberate KeyboardInterrupt becomes a technical stop by design;
        # model an unexpected process exit so the existing reconciliation path
        # can adopt the already durable response without erasing any halt.
        with self.assertRaises(SystemExit):
            with patch.object(w.pilot,'save_snapshot',side_effect=SystemExit('SYNTHETIC abrupt process exit')):self.execute(fetch,resume=True)
        self.assertFalse((self.campaign_root/'technical_stop.json').exists())
        self.assertEqual(fetch.call_count,1);self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,1);self.assertEqual(fetch.call_args.args[0],self.next_url)
        self.assertEqual(campaign._counts(self.child,plan),{'saved':401,'calls':403,'pending_native_attempts':0,'open_transport':False})
        batch=plan['batches'][-1];B=self.child/'batches'/batch['batch_id'];items,h=w.pilot.load_input(self.child/batch['input_path']);self.assertEqual(worker._export_preview(B,items,h)['files'],w.load(B/'export_manifest.json')['files'])
        self.receipt(self.selected(401));self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,10);self.receipt(self.selected(9,3));self.assertEqual(self.execute(fetch,resume=True)['status'],'frozen_queue_processed_pending_coverage_review')
        after=worker.inherited_prefix_evidence(self.child,plan,400)
        for key in recovery.PREFIX_KEYS:self.assertEqual(before[key],after[key])
        self.originals()

    def test_new_unknown_media_stops_and_cannot_restart_past_halt(self):
        self.prepare();self.execute(Mock(side_effect=lf.response));self.receipt(self.selected())
        def bad(url,timeout,**kw):
            response=lf.lead_response(url,timeout);response['text']=response['text'].replace('https://www.youtube.com/embed/R8NeB10INDo','javascript:unknown()');return response
        fetch=Mock(side_effect=bad);self.assertEqual(self.execute(fetch,resume=True)['status'],'technical_stop_requires_investigation');self.assertEqual(fetch.call_count,1);self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,1);self.originals()

    def test_false_held_approval_or_changed_pause_rejects_before_copy(self):
        draft=w.load(self.draft);draft['human_approval']=True;p=self.base/'bad_draft.json';w.write(p.parent,p.name,draft);self.cfg['draft_receipts']=[campaign._bound(p)];w.write(self.base,self.config.name,self.cfg)
        with self.assertRaisesRegex(ValueError,'Pending reading draft'):recovery.prepare(self.config)
        self.assertFalse(self.campaign_root.exists());self.cfg['draft_receipts']=[campaign._bound(self.draft)];self.cfg['donor_pause_receipt_sha256']='0'*64;w.write(self.base,self.config.name,self.cfg)
        with self.assertRaises(ValueError):recovery.prepare(self.config)
        self.assertFalse(self.campaign_root.exists());self.originals()

    def test_tampered_effective_warning_or_export_blocks_without_network(self):
        self.prepare();fetch=Mock(side_effect=lf.response);self.execute(fetch);p=self.child/'lead_media_checks'/(self.source_ids[0]+'.json');doc=w.load(p);doc['result']['source_media_warnings']=[];w.write(p.parent,p.name,doc)
        with self.assertRaises(ValueError):campaign.read_bound(self.campaign_root,full=True)
        fetch.assert_not_called();self.originals()

if __name__=='__main__':unittest.main()

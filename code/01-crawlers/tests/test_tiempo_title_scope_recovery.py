"""Bound title recovery: generated URLs/readings and simulated transport only.

One shared107-row stopped fixture exercises original27-row tail, predecessor
completion/history, the unchanged400 gate, and final401 tail gate. Actual
production531 bounds are separately fixed and checked during preparation.
"""
import contextlib,hashlib,io,json,re,sqlite3,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
import test_tiempo_remaining_campaign as cf
import test_tiempo_continuous_v5 as fixtures
import test_tiempo_source_gap_recovery as rf
import test_tiempo_lead_media_recovery as lf
from crawler_core import tiempo_continuous_v5 as w,tiempo_remaining_campaign as campaign,tiempo_resumable_worker as worker,tiempo_stage_review as review
from crawler_core import tiempo_title_scope_recovery as recovery

NOTES=Path('/Users/kevinfu/Library/CloudStorage/Dropbox/Media/data/00-newspaper_data/crawler/pilots/Kevin/Continuations/Remaining_Media_URL_Recovery_20261013/diagnostics/Stopped107_Source_Notes.json')

class TitleScopeRecoveryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  if not NOTES.exists():raise unittest.SkipTest('Opt-in existing source template is unavailable')
  bound=w.load(NOTES)['records'][0];cls.template=Path(bound['raw_path']).read_bytes().decode('utf-8');cls.original_slug=urlsplit(bound['request_url']).path.strip('/').split('/')[-1]
  cls.old=old=cf.RemainingCampaignTests('runTest');old.setUp();cls.addClassCleanup(old.doCleanups);old.build(total=1203,chunk=401)
  cls.donor=old.campaign_root;cls.donor_child=campaign.child_path(old.m,3);queue=w.readcsv(old.m['parts'][1]['path']);cls.source_positions=[81,88,107];cls.source_ids=[queue[p-1]['sample_id'] for p in cls.source_positions];cls.source_urls={queue[p-1]['url'] for p in cls.source_positions};cls.next_id=queue[107]['sample_id'];cls.next_url=queue[107]['url']
  def fetch(url,timeout,**kw):return cls.title_response(url,timeout) if url in cls.source_urls else lf.response(url,timeout)
  with old.synthetic_reading_gate():state=old.execute(Mock(side_effect=fetch))
  assert state['status']=='technical_stop_requires_investigation',state
  counts=campaign._counts(cls.donor_child,w.load(cls.donor_child/'continuous_plan.json'));assert counts=={'saved':107,'calls':107,'pending_native_attempts':0,'open_transport':False},counts
  assert w.load(cls.donor_child/'safety_halt.json')['reason']=='three_unexplained_rows_in_rolling80'
  for sid in cls.source_ids:
   rec=w.load(cls.donor_child/'row_checks'/(sid+'.json'))['record'];assert not rec['critical_flags'] and set(rec['unexplained_flags'])=={'unexplained_result_error'},rec['automatic_flags']
  native_rows=worker.inherited_prefix_evidence(cls.donor_child,w.load(cls.donor_child/'continuous_plan.json'),107)['rows']
  assert all(x['row']['error']=='missing_title' and x['row']['date_published']=='2024-06-01T08:24:29' for x in native_rows if x['row']['sample_id'] in cls.source_ids)
  cls.hashes={str(p):w.sha_file(p) for p in cls.donor.rglob('*') if p.is_file() and p.name!='.pilot.lock'}
 @classmethod
 def title_response(cls,url,timeout,**kwargs):
  r=lf.response(url,timeout);slug=urlsplit(url).path.strip('/').split('/')[-1];r['text']=cls.template.replace(cls.original_slug,slug).replace('2021-07-17T08:24:29','2024-06-01T08:24:29').replace('17 Julio 2021','01 Junio 2024');return r
 def setUp(self):
  self.base=self.old.base/self._testMethodName;self.base.mkdir();self.campaign_root=self.base/'successor';self.config=self.base/'config.json';self.clock=fixtures.Clock();self.clock.t=self.old.clock.now()+100
  plan=w.load(self.donor_child/'continuous_plan.json');prefix=worker.inherited_prefix_evidence(self.donor_child,plan,107);records=[]
  for x in prefix['rows']:
   row=x['row'];sid=row['sample_id']
   if sid not in self.source_ids:continue
   B=self.donor_child/'batches'/x['batch_id'];raw=B/row['snapshot_path'];check=self.donor_child/'row_checks'/(sid+'.json')
   with sqlite3.connect((B/'pilot.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True) as db:payload=next(x[0] for x in db.execute('SELECT payload_json FROM articles') if json.loads(x[0])['sample_id']==sid)
   n=len(BeautifulSoup(raw.read_bytes().decode('utf-8'),'html.parser').select('article#article-post .complementos-container h1'))
   records.append({'sample_id':sid,'request_url':row['url'],'raw_path':str(raw),'raw_sha256':w.sha_file(raw),'payload_sha256':hashlib.sha256(payload.encode()).hexdigest(),'row_check_path':str(check),'row_check_sha256':w.sha_file(check),'native_title':None,'native_error':'missing_title','native_manual_review_status':'not_reviewed','body_h1_count':n,'body_h1_all_in_preserved_text':True,'normalized_full_jsonld_article_body_equals_native_text':True,'research_status':'NEEDS_JOAQUIN_REVIEW','gate_approval':False,'actual_ai_read_note':'SYNTHETIC GENERATED SOURCE AND TEST READING ONLY. The fixture copies an approved editor structure into generated request identities. This is not real news reading or human approval.'})
  w.write(self.base,'source_review.json',{'schema':'tiempo-focused-stopped-source-reading-v1','author':'Kevin','human_approval':False,'actual_ai_read':True,'native_review_state_changed':False,'network_requests':0,'synthetic_fixture':True,'records':records})
  self.cfg={'root':str(self.campaign_root),'donor_root':str(self.donor),'donor_code_root':str(Path(__file__).resolve().parents[3]),'synthetic_fixture':True,'expected_child_index':3,'expected_saved':107,'expected_calls':107,'next_sample_id':self.next_id,'source_sample_ids':self.source_ids,'source_review':campaign._bound(self.base/'source_review.json'),'donor_campaign_sha256':w.sha_file(self.donor/'campaign.json'),'donor_master_halt_sha256':w.sha_file(self.donor/'technical_stop.json'),'donor_native_halt_sha256':w.sha_file(self.donor_child/'safety_halt.json')};w.write(self.base,self.config.name,self.cfg)
 def prepare(self):
  try:
   with contextlib.redirect_stdout(io.StringIO()):recovery.prepare(self.config)
  except Exception:
   for p in self.campaign_root.glob('Media/**/safety_halt.json'):print('SYNTHETIC HALT',p.read_text(),file=sys.stderr)
   for p in self.campaign_root.glob('Media/**/source_classifications/*.json'):
    d=w.load(p)
    if not d['decision']['matched']:print('SYNTHETIC REJECTION',d['sample_id'],d['decision']['rejection_reasons'],file=sys.stderr)
   raise
  self.m,_=campaign.read_bound(self.campaign_root,full=True);self.child=campaign.child_path(self.m,3)
 execute=rf.SourceGapRecoveryTests.execute
 receipt=lf.LeadMediaRecoveryTests.receipt
 def selection(self,n):return self.campaign_root/f'reviews/plan_000003/checkpoint_{n:08d}/selection_{n:08d}.json'
 def originals(self):
  for p,digest in self.hashes.items():self.assertEqual(w.sha_file(p),digest,p)
 def test_original27_partial_to80_response_reuse400_gate_and_final_boundary(self):
  self.prepare();plan=w.load(self.child/'continuous_plan.json');before=worker.inherited_prefix_evidence(self.child,plan,107);proof=w.load(self.m['title_scope_recovery']['provenance']['path'])
  self.assertEqual(proof['inherited_checkpoint_gates'],[]);self.assertEqual(proof['new_actual_ai_read_count'],0);self.assertTrue(proof['original_partial_certificate_missing']);self.assertFalse(proof['next_gate_approved'])
  self.assertEqual([e['rows'] for e in proof['completed_predecessor_gates']],[400,401]);self.assertEqual(len((self.child/'transport_calls.jsonl').read_bytes().splitlines()),214);self.assertEqual((self.child/'continuous_plan.json').read_bytes(),(self.donor_child/'continuous_plan.json').read_bytes());self.assertEqual(self.m['baseline_saved'],802);self.assertEqual(self.m['remaining_rows'],401)
  for sid in self.source_ids:
   d=w.load(self.child/'source_classifications'/(sid+'.json'));self.assertTrue(d['decision']['matched']);self.assertTrue(d['article_candidate']);self.assertEqual(d['effective_outcome'],'article_candidate');self.assertEqual(d['correction_kind'],'source_title_channel_scope_correction');self.assertIsNone(d['source_gap_kind'])
  fetch=Mock(side_effect=lf.response);kw={'max_batches':25,'fetcher':fetch,'clock':self.clock.now,'sleep':self.clock.sleep,'stop_at_saved_rows':160,'source_classification_policy':self.m['title_scope_recovery']['policy'],'install_signal_handlers':False}
  with contextlib.redirect_stdout(io.StringIO()):
   with patch.object(w.pilot,'save_snapshot',side_effect=KeyboardInterrupt):state=worker.run(self.child,self.m['media'],**kw)
   self.assertEqual(state['status'],'interrupted_requires_explicit_invocation');self.assertEqual(fetch.call_count,1)
   state=worker.run(self.child,self.m['media'],**kw)
  self.assertTrue(state['checkpoint_boundary_reached']);self.assertEqual(fetch.call_count,53);self.assertEqual(fetch.call_args_list[0].args[0],self.next_url)
  b=plan['batches'][1];B=self.child/'batches'/b['batch_id'];self.assertEqual(len(w._rows(self.child,b)),80);items,h=w.pilot.load_input(self.child/b['input_path']);self.assertEqual(worker._export_preview(B,items,h)['files'],w.load(B/'export_manifest.json')['files'])
  self.assertEqual(self.execute(fetch)['status'],'paused_safe');self.assertEqual(fetch.call_count,293);sel=w.load(self.selection(400));last=proof['completed_predecessor_gates'][-1];self.assertIn(last['coverage'],sel['history']['coverage_seals']);self.assertTrue(set(review._coverage(last['coverage']['path'])['distinct_actual_ai_read_ids'])<=set(sel['history']['distinct_actual_ai_read_ids']))
  self.assertEqual(campaign._checkpoint_gate_events(self.m,campaign.events(self.campaign_root),3),[]);self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,293)
  self.receipt(self.selection(400));self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,294);self.receipt(self.selection(401));self.assertEqual(self.execute(fetch,resume=True)['status'],'frozen_queue_processed_pending_coverage_review');self.assertEqual(fetch.call_count,294)
  after=worker.inherited_prefix_evidence(self.child,plan,107)
  for k in recovery.PREFIX_KEYS:self.assertEqual(before[k],after[k])
  self.assertEqual(campaign._counts(self.child,plan),{'saved':401,'calls':401,'pending_native_attempts':0,'open_transport':False});self.originals()
 def test_changed_source_and_halt_bindings_reject_before_copy(self):
  self.cfg['donor_native_halt_sha256']='0'*64;w.write(self.base,self.config.name,self.cfg)
  with self.assertRaises(ValueError):recovery.prepare(self.config)
  self.assertFalse(self.campaign_root.exists());self.cfg['donor_native_halt_sha256']=w.sha_file(self.donor_child/'safety_halt.json');self.cfg['source_review']['sha256']='0'*64;w.write(self.base,self.config.name,self.cfg)
  with self.assertRaises(ValueError):recovery.prepare(self.config)
  self.assertFalse(self.campaign_root.exists());self.originals()
 def test_unsupported_new_title_role_still_stops(self):
  self.prepare();fetch=Mock(side_effect=self.title_response);state=self.execute(fetch);self.assertEqual(state['status'],'technical_stop_requires_investigation');self.assertLessEqual(fetch.call_count,3);self.assertGreater(fetch.call_count,0);self.execute(fetch,resume=True);self.assertLessEqual(fetch.call_count,3);self.originals()
 def test_new_identity_or_media_fault_remains_hard_stop(self):
  self.prepare()
  def bad(url,timeout,**kw):return {**lf.response(url,timeout),'final_url':'https://outside.invalid/different-article'}
  fetch=Mock(side_effect=bad);self.assertEqual(self.execute(fetch)['status'],'technical_stop_requires_investigation');self.assertEqual(fetch.call_count,1);self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,1);self.originals()

if __name__=='__main__':unittest.main()

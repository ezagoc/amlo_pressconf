"""Bound offline1517 recovery; generated sources and synthetic readings only."""
import contextlib,io,json,unittest,sqlite3
from pathlib import Path
from unittest.mock import Mock,patch
import test_tiempo_remaining_campaign as cf
import test_tiempo_continuous_v5 as fixtures
import test_tiempo_source_gap_recovery as rf
import test_tiempo_lead_media_recovery as lf
from test_tiempo_source_classification_recovery import shell_response
from crawler_core import tiempo_continuous_v5 as w,tiempo_remaining_campaign as campaign,tiempo_resumable_worker as worker,tiempo_stage_review as review
from crawler_core import tiempo_comment_space_recovery as recovery


def build_fixture(cls,saved,chunk):
 old=cf.RemainingCampaignTests('runTest');old.setUp();cls.addClassCleanup(old.doCleanups)
 if chunk*2+9>2000:
  def queue_only(n):
   # Build a campaign input database, not one illegal >2000-row native plan.
   # The unchanged scheduler subsequently freezes separate1601-row parts.
   old.root=old.media/'data/00-newspaper_data/crawler/pilots/Kevin/tiempo_continuous_v5/testv5'
   rows=[{**fixtures.candidate(i),'candidate_id':str(i),'sample_id':f'TC5_TEST_{i:06d}','baseline_classes_json':'[]'} for i in range(n)]
   old.input=old.base/'v5.csv';fixtures.writecsv(old.input,rows);old.queue_db=old.base/'v5queue.sqlite';old.rows=rows
   columns=[k for k in rows[0] if k not in {'sample_id','selection_reason','expected_year','expected_kind'}]
   with sqlite3.connect(old.queue_db) as db:
    db.execute('CREATE TABLE candidates ('+', '.join(k+' TEXT' for k in columns)+')')
    db.executemany('INSERT INTO candidates VALUES ('+','.join('?' for _ in columns)+')',[[r[k] for k in columns] for r in rows])
  old.freeze=queue_only
 old.build(total=chunk*2+9,chunk=chunk);cls.old=old;cls.saved=saved
 cls.donor=old.campaign_root;cls.donor_child=campaign.child_path(old.m,2);queue=w.readcsv(old.m['parts'][0]['path']);cls.sid=queue[saved-1]['sample_id'];cls.url=queue[saved-1]['url'];cls.next_id=queue[saved]['sample_id'];cls.next_url=queue[saved]['url'];cls.source_ids=[cls.sid]
 service=queue[min(378,saved-10)]['url'];media_url=queue[499]['url'] if saved>500 else None
 original=w._window_trigger
 def former_trigger(history):
  # Explicit synthetic old-policy rejection, not an altered native diagnostic.
  return 'unclassified_source_gap' if history and history[-1]['sample_id']==cls.sid else original(history)
 def fetch(url,timeout,**kw):
  if url==cls.url:return shell_response(url,timeout)
  if url==service:return {**lf.response(url,timeout),'status':500}
  if url==media_url:
   response=lf.lead_response(url,timeout)
   # Match the existing explicitly synthetic reader's fixture marker while
   # preserving the omitted lead iframe and source structure under test.
   response['text']=response['text'].replace('Summary new-','Report new-')
   return response
  return lf.response(url,timeout)
 with old.synthetic_reading_gate(),patch.object(w,'_window_trigger',side_effect=former_trigger):state=old.execute(Mock(side_effect=fetch))
 assert state['status']=='technical_stop_requires_investigation',state
 counts=campaign._counts(cls.donor_child,w.load(cls.donor_child/'continuous_plan.json'));assert counts=={'saved':saved,'calls':saved+2,'pending_native_attempts':0,'open_transport':False}, {'counts':counts,'master':w.load(cls.donor/'technical_stop.json'),'halt':w.load(cls.donor_child/'safety_halt.json') if (cls.donor_child/'safety_halt.json').exists() else None}
 cls.hashes={str(p):w.sha_file(p) for p in cls.donor.rglob('*') if p.is_file() and p.name!='.pilot.lock'}

class _Methods:
 def configure(self,suffix=''):
  self.base=self.old.base/(self._testMethodName+suffix);self.base.mkdir();self.campaign_root=self.base/'successor';self.config=self.base/'config.json';self.clock=fixtures.Clock();self.clock.t=self.old.clock.now()+100
  plan=w.load(self.donor_child/'continuous_plan.json');prefix=worker.inherited_prefix_evidence(self.donor_child,plan,self.saved);last=prefix['rows'][-1];row=last['row']
  w.write(self.base,'synthetic_source_reading.json',{'author':'Kevin','human_approval':False,'note':'SYNTHETIC SOURCE AND TEST READING ONLY; not real news or human approval.'})
  rec={'sample_id':self.sid,'raw':campaign._bound(self.donor_child/'batches'/last['batch_id']/row['snapshot_path']),'native_row_check':campaign._bound(self.donor_child/'row_checks'/(self.sid+'.json')),'reading_evidence':campaign._bound(self.base/'synthetic_source_reading.json')}
  w.write(self.base,'source_review.json',{'author':'Kevin','human_approval':False,'article_acceptance':False,'new_checkpoint_reading_credit':0,'records':[rec]})
  self.cfg={'root':str(self.campaign_root),'donor_root':str(self.donor),'donor_code_root':str(Path(__file__).resolve().parents[3]),'synthetic_fixture':True,'expected_child_index':2,'expected_saved':self.saved,'expected_calls':self.saved+2,'next_sample_id':self.next_id,'source_sample_id':self.sid,'source_review':campaign._bound(self.base/'source_review.json'),'donor_campaign_sha256':w.sha_file(self.donor/'campaign.json'),'donor_master_halt_sha256':w.sha_file(self.donor/'technical_stop.json'),'donor_native_halt_sha256':w.sha_file(self.donor_child/'safety_halt.json')};w.write(self.base,self.config.name,self.cfg)
 def prepare(self):
  with contextlib.redirect_stdout(io.StringIO()):recovery.prepare(self.config)
  self.m,_=campaign.read_bound(self.campaign_root,full=True);self.child=campaign.child_path(self.m,2)
 execute=rf.SourceGapRecoveryTests.execute
 receipt=lf.LeadMediaRecoveryTests.receipt
 def selection(self,n,index=2):return self.campaign_root/f'reviews/plan_{index:06d}/checkpoint_{n:08d}/selection_{n:08d}.json'
 def originals(self):
  for p,digest in self.hashes.items():self.assertEqual(w.sha_file(p),digest,p)

class Full1517RecoveryTests(_Methods,unittest.TestCase):
 @classmethod
 def setUpClass(cls):build_fixture(cls,1517,1601)
 def test_1517_partial77_to1520_and1600_gate_then_cross_child(self):
  self.configure();self.prepare();plan=w.load(self.child/'continuous_plan.json');before=worker.inherited_prefix_evidence(self.child,plan,1517);proof=w.load(self.m['comment_space_recovery']['provenance']['path'])
  self.assertEqual([g['rows'] for g in proof['inherited_checkpoint_gates']],[400,800,1200]);self.assertEqual(proof['new_actual_ai_read_count'],0);self.assertTrue(proof['original_partial_certificate_missing']);self.assertFalse(proof['next_gate_approved'])
  self.assertEqual(len((self.child/'transport_calls.jsonl').read_bytes().splitlines()),3038)
  self.assertEqual((self.child/'continuous_plan.json').read_bytes(),(self.donor_child/'continuous_plan.json').read_bytes())
  self.assertFalse((self.donor_child/'automatic_checks/batch_000019').exists());self.assertTrue(list((self.child/'automatic_checks/batch_000019').glob('*/check.json')))
  decision=w.load(self.child/'source_classifications'/(self.sid+'.json'));self.assertTrue(decision['decision']['matched']);self.assertEqual(decision['effective_outcome'],'source_unavailable');self.assertFalse(decision['article_candidate'])
  self.assertEqual(before['rows'][-1]['row']['error'],'missing_body');self.assertEqual(w.load(self.child/'row_checks'/(self.sid+'.json'))['record']['manual_review_status'],'not_reviewed')
  fetch=Mock(side_effect=lf.response);kw={'max_batches':25,'fetcher':fetch,'clock':self.clock.now,'sleep':self.clock.sleep,'stop_at_saved_rows':1520,'source_classification_policy':self.m['comment_space_recovery']['policy'],'install_signal_handlers':False}
  with contextlib.redirect_stdout(io.StringIO()):
   with patch.object(w.pilot,'save_snapshot',side_effect=KeyboardInterrupt):state=worker.run(self.child,self.m['media'],**kw)
   self.assertEqual(state['status'],'interrupted_requires_explicit_invocation');self.assertEqual(fetch.call_count,1)
   state=worker.run(self.child,self.m['media'],**kw)
  self.assertTrue(state['checkpoint_boundary_reached']);self.assertEqual(fetch.call_count,3);self.assertEqual(fetch.call_args_list[0].args[0],self.next_url)
  b=plan['batches'][18];rows=w._rows(self.child,b);self.assertEqual(len(rows),80);B=self.child/'batches'/b['batch_id'];items,h=w.pilot.load_input(self.child/b['input_path']);self.assertEqual(worker._export_preview(B,items,h)['files'],w.load(B/'export_manifest.json')['files'])
  state=self.execute(fetch);self.assertEqual(state['status'],'paused_safe');self.assertEqual(fetch.call_count,83);selection=w.load(self.selection(1600));self.assertIn(proof['inherited_checkpoint_gates'][-1]['coverage'],selection['history']['coverage_seals'])
  old_ids=set(review._coverage(proof['inherited_checkpoint_gates'][-1]['coverage']['path'])['distinct_actual_ai_read_ids']);self.assertTrue(old_ids<=set(selection['history']['distinct_actual_ai_read_ids']))
  self.assertEqual([g['rows'] for g in campaign._checkpoint_gate_events(self.m,campaign.events(self.campaign_root),2)],[400,800,1200])
  self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,83)
  self.receipt(self.selection(1600));self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,84)
  self.receipt(self.selection(1601));self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,93)
  self.receipt(self.selection(9,3));self.assertEqual(self.execute(fetch,resume=True)['status'],'frozen_queue_processed_pending_coverage_review')
  after=worker.inherited_prefix_evidence(self.child,plan,1517)
  for k in recovery.PREFIX_KEYS:self.assertEqual(before[k],after[k])
  self.originals()

class FocusedRecoveryTests(_Methods,unittest.TestCase):
 @classmethod
 def setUpClass(cls):build_fixture(cls,117,241)
 def test_new_unknown_comment_media_body_or_identity_stops(self):
  for kind in ('comment','media','body','identity'):
   with self.subTest(kind=kind):
    self.configure('_'+kind);self.prepare()
    def bad(url,timeout,**kw):
     r=shell_response(url,timeout)
     if kind=='comment':r['text']=r['text'].replace('</article>','<!-- novel source prose --> </article>')
     elif kind=='media':r['text']=r['text'].replace('</article>','<iframe src="https://unknown.example/player"></iframe></article>')
     elif kind=='body':r['text']=r['text'].replace('</article>','<div class="unexpected-article-body">Actual omitted source prose must never become a recognized empty page.</div></article>')
     else:r['final_url']='https://outside.example/article/'
     return r
    fetch=Mock(side_effect=bad);self.assertEqual(self.execute(fetch)['status'],'technical_stop_requires_investigation');self.assertEqual(fetch.call_count,1)
    self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,1);self.originals()
 def test_added_old_partial_certificate_is_rejected(self):
  self.configure();self.prepare();plan=w.load(self.donor_child/'continuous_plan.json');last=worker.inherited_prefix_evidence(self.donor_child,plan,self.saved)['rows'][-1]['batch_id']
  fake=self.donor_child/'automatic_checks'/last/'synthetic_added_certificate'/'check.json'
  w.write(fake.parent,fake.name,{'synthetic':True,'rows':37})
  try:
   with self.assertRaisesRegex(ValueError,'partial certificate inventory'):recovery.verify(self.m)
  finally:fake.unlink();fake.parent.rmdir()
  self.originals()
 def test_changed_source_or_halt_binding_rejected_before_copy(self):
  self.configure();self.cfg['donor_native_halt_sha256']='0'*64;w.write(self.base,self.config.name,self.cfg)
  with self.assertRaises(ValueError):recovery.prepare(self.config)
  self.assertFalse(self.campaign_root.exists());self.cfg['donor_native_halt_sha256']=w.sha_file(self.donor_child/'safety_halt.json');self.cfg['source_review']['sha256']='0'*64;w.write(self.base,self.config.name,self.cfg)
  with self.assertRaises(ValueError):recovery.prepare(self.config)
  self.assertFalse(self.campaign_root.exists());self.originals()

if __name__=='__main__':unittest.main()

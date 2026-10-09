"""Generated offline fixtures only; no real source reading or HTTP."""
import contextlib
import copy
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crawler_core import tiempo_continuous_v5 as w
from crawler_core import tiempo_remaining_campaign as c
from crawler_core import tiempo_resumable_worker as worker
from crawler_core import tiempo_stage_review as review
from crawler_core import tiempo_review_recovery as recovery
import test_tiempo_remaining_campaign as fixture
import test_tiempo_continuous_v5 as native


class ReviewRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.donor = d = fixture.RemainingCampaignTests('runTest'); d.setUp(); cls.addClassCleanup(d.doCleanups)
        d.build(total=1207,chunk=401)
        original=review.validate_gate
        def receipts(selection_path,receipt_paths=()):
            p=d.synthetic_reading_receipt(selection_path)
            if p not in receipt_paths: receipt_paths.append(p)
            selection=w.load(selection_path)
            if selection['snapshot']['checkpoint_rows']==400 and 'remaining_plan_000003' in selection['snapshot']['child']:
                doc=w.load(p); doc['records'][-1]['research_status']='none'; w.write(p.parent,p.name,doc)
                cls.selection=Path(selection_path); cls.bad_id=doc['records'][-1]['sample_id']; cls.corrected=p
            return original(selection_path,receipt_paths)
        with patch.object(review,'validate_gate',side_effect=receipts): state=d.execute()
        if state['status']!='technical_stop_requires_investigation': raise AssertionError(state)
        cls.source=c.child_path(d.m,3)
        cls.bad=cls.selection.parent/'receipt_format_corrections/original.json'
        cls.bad.parent.mkdir(); cls.bad.write_bytes(cls.corrected.read_bytes())
        fixed=w.load(cls.corrected);fixed['records'][-1]['research_status']=None
        fixed['format_correction']={'preserved_unaccepted_receipt':str(cls.bad),
          'preserved_sha256':w.sha_file(cls.bad),'reason':'SYNTHETIC TEST serialization-only correction','author':'Kevin'}
        w.write(cls.corrected.parent,cls.corrected.name,fixed)
        cls.hashes={str(p):w.sha_file(p) for p in d.campaign_root.rglob('*') if p.is_file() and p.name!='.pilot.lock'}

    def setUp(self):
        self.base=self.donor.base/self._testMethodName;self.base.mkdir();self.root=self.base/'successor'
        self.config=self.base/'config.json'
        self.cfg={'root':str(self.root),'donor_root':str(self.donor.campaign_root),
          'donor_code_root':str(Path(__file__).resolve().parents[3]),'expected_child_index':3,
          'expected_saved':400,'expected_calls':400,'next_sample_id':w.readcsv(self.source/'queue.csv')[400]['sample_id'],
          'corrected_sample_id':self.bad_id,'donor_campaign_sha256':w.sha_file(self.donor.campaign_root/'campaign.json'),
          'donor_master_halt_sha256':w.sha_file(self.donor.campaign_root/'technical_stop.json'),
          'donor_stop_event_sha256':c.events(self.donor.campaign_root)[-1]['event_sha256'],
          'selection':str(self.selection),'selection_sha256':w.sha_file(self.selection),
          'unaccepted_receipt':str(self.bad),'unaccepted_receipt_sha256':w.sha_file(self.bad),
          'corrected_receipt':str(self.corrected),'corrected_receipt_sha256':w.sha_file(self.corrected),
          'receipt_paths':[str(self.corrected)],'synthetic_fixture':True}
        w.write(self.base,self.config.name,self.cfg)
        self.clock=native.Clock();self.clock.t=self.donor.clock.now()+100

    def prepare(self):
        with contextlib.redirect_stdout(io.StringIO()): state=recovery.prepare(self.config)
        self.m,_=c.read_bound(self.root,full=True);self.child=c.child_path(self.m,3)
        return state

    def execute(self,fetch=None,**kwargs):
        opts={'fetcher':fetch or Mock(side_effect=native.response),'clock':self.clock.now,
              'sleep':self.clock.sleep,'disk_free':lambda _:10**10,'wait_for_review':False}
        opts.update(kwargs)
        with contextlib.redirect_stdout(io.StringIO()):return c.run(self.root,**opts)

    def test_prefix_gate_then401_and_repeated_resume_without_duplicate_calls(self):
        self.prepare(); before=c.inspect(self.root)
        self.assertEqual((before['active']['saved'],before['active']['calls']),(400,400))
        prefix=worker.inherited_prefix_evidence(self.child,w.load(self.child/'continuous_plan.json'),400)
        gates=[e for e in c.events(self.root) if e['kind']=='checkpoint_gate_satisfied']
        self.assertEqual([e['rows'] for e in gates],[400]);self.assertEqual(gates[0]['new_actual_ai_read_count'],0)
        fetch=Mock(side_effect=native.response);self.execute(fetch)
        self.assertEqual(fetch.call_count,1);self.assertEqual(fetch.call_args.args[0],w.readcsv(self.source/'queue.csv')[400]['url'])
        self.assertTrue((self.root/'reviews/plan_000003/checkpoint_00000401/selection_00000401.json').exists())
        self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,1)
        after=worker.inherited_prefix_evidence(self.child,w.load(self.child/'continuous_plan.json'),400)
        for key in recovery.PREFIX_KEYS:self.assertEqual(prefix[key],after[key])
        for path,digest in self.hashes.items():self.assertEqual(w.sha_file(path),digest)

    def test_cross_child_and_gate_obligation_inherit_without_double_count(self):
        self.prepare();fetch=Mock(side_effect=native.response)
        with self.donor.synthetic_reading_gate():state=self.execute(fetch)
        self.assertEqual(state['status'],'frozen_queue_processed_pending_coverage_review')
        self.assertEqual(fetch.call_count,5)
        status=c.inspect(self.root);self.assertEqual(status['original_plan_saved'],1207)
        self.assertEqual(status['global_charged_calls'],1207)
        self.assertEqual(w.load(c.child_path(self.m,4)/'continuous_plan.json')['seed_context'],
                         w.load(self.child/'continuation_context.json'))
        self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,5)

    def test_changed_reading_or_research_conclusion_rejected(self):
        old=w.load(self.corrected)
        try:
            for field,value in [('note','changed actual reading'),('research_status','NEEDS_JOAQUIN_REVIEW'),
                                ('snapshot_sha256','0'*64)]:
                changed=copy.deepcopy(old);changed['records'][-1][field]=value;w.write(self.corrected.parent,self.corrected.name,changed)
                cfg={**self.cfg,'corrected_receipt_sha256':w.sha_file(self.corrected)}
                with self.assertRaisesRegex(ValueError,'Correction changed'):recovery.validate_correction(cfg)
        finally:w.write(self.corrected.parent,self.corrected.name,old)

    def test_missing_other_reading_cannot_prepare(self):
        cfg={**self.cfg,'receipt_paths':[]};w.write(self.base,self.config.name,cfg)
        with self.assertRaises(ValueError):self.prepare()
        self.assertFalse(self.root.exists())

    def test_corrupt_original_export_rejected_before_namespace_or_regeneration(self):
        path=next(self.source.glob('batches/*/articles.csv'));original=path.read_bytes()
        try:
            path.write_bytes(original+b'corruption')
            with self.assertRaisesRegex(ValueError,'Original export bytes differ'):self.prepare()
            self.assertFalse(self.root.exists());self.assertEqual(path.read_bytes(),original+b'corruption')
        finally:path.write_bytes(original)

    def test_interrupted_preparation_cannot_launch_or_reprepare(self):
        with patch.object(worker,'close_saved_boundary',side_effect=RuntimeError('simulated interruption')):
            with self.assertRaisesRegex(RuntimeError,'simulated'):self.prepare()
        with self.assertRaisesRegex(ValueError,'preparation incomplete'):c.read_bound(self.root)
        with self.assertRaisesRegex(ValueError,'separate empty'):self.prepare()
        self.assertTrue((self.donor.campaign_root/'technical_stop.json').exists())

    def test_removed_gate_blocks_network(self):
        self.prepare();last=sorted((self.root/'events').glob('*.json'))[-1];data=last.read_bytes();last.unlink()
        fetch=Mock(side_effect=native.response)
        try:
            with self.assertRaisesRegex(ValueError,'Recovered400'):self.execute(fetch)
            self.assertEqual(fetch.call_count,0)
        finally:last.write_bytes(data)

    def test_new_dns_failure_stops_and_cannot_reenter(self):
        self.prepare()
        def failed(url,timeout,**kwargs):
            return {**native.response(url,timeout),'text':'','status':0,'curl_exit_code':6,
                    'error':'transport_error: curl_exit_6: Could not resolve host'}
        fetch=Mock(side_effect=failed);state=self.execute(fetch)
        self.assertEqual(state['status'],'technical_stop_requires_investigation');self.assertTrue((self.root/'technical_stop.json').exists())
        calls=fetch.call_count;self.execute(fetch,resume=True);self.assertEqual(fetch.call_count,calls)
        self.assertGreater(calls,0)

    def test_disk_floor_stops_without_request(self):
        self.prepare();fetch=Mock(side_effect=native.response)
        state=self.execute(fetch,disk_free=lambda _:0)
        self.assertEqual(state['status'],'resource_pause_low_disk');self.assertEqual(fetch.call_count,0)

if __name__=='__main__':unittest.main()

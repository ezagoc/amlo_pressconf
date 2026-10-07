"""Only new stage boundaries/recovery: native storage with synthetic transport."""
import contextlib
import io
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_tiempo_recovery as recovery_fixtures
import test_tiempo_continuous as fixtures
from crawler_core import tiempo_continuous_v5 as w, tiempo_bounded_stage as stage


class BoundedStageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helper = recovery_fixtures.RecoveryTests('test_full_original_plan_and_batch_boundary_not_replaced_by_pending_subset')
        helper.setUp(); cls.addClassCleanup(helper.doCleanups); cls.fixture = helper
        with contextlib.redirect_stdout(io.StringIO()):
            helper.donor(n=1200, saved=226)
            helper.prepare(); fetched = Mock(side_effect=fixtures.response)
            result = helper.run_trial(fetched)
        if result['saved_active_rows'] != 240 or fetched.call_count != 14:
            raise AssertionError('Synthetic closed source is not 240 committed rows')
        cls.source = helper.capsule; cls.source_child = helper.newchild
        cls.source_plan = w.load(cls.source_child / 'continuous_plan.json')
        cls.source_rows = [r for b in cls.source_plan['batches'] for r in w._rows(cls.source_child, b)]
        cls.source_files = {str(p): w.sha_file(p) for root in (cls.source, cls.source_child)
                            for p in root.rglob('*') if p.is_file() and p.name != '.pilot.lock'}
        cls.closure = helper.base / 'source240_closure.json'
        w.write(helper.base, cls.closure.name, {'author': 'Kevin', 'status': 'PASS_SYNTHETIC_OFFLINE_CLOSURE',
            'native_successor_records': 240, 'no_automatic_expansion': True, 'article_acceptance': False,
            'human_approval': False, 'synthetic_fixture': True,
            'source_binding': {'capsule_file_sha256': w.sha_file(cls.source / 'capsule.json'),
                'saved_active_rows': 240, 'transport_ledger_sha256': w.sha_file(cls.source_child / 'transport_calls.jsonl'),
                'native_databases': [{'path': str(p), 'sha256': w.sha_file(p)}
                                     for p in sorted(cls.source_child.glob('batches/*/pilot.sqlite'))]}})

    def setUp(self):
        self.base = self.fixture.base / self._testMethodName; self.base.mkdir()
        self.media = self.base / 'Media'; self.root = self.base / 'capsule'
        self.child = self.media / 'data/00-newspaper_data/crawler/pilots/Kevin/tiempo_continuous_v5/remainder'
        self.config = self.base / 'config.json'
        targets = self.source_plan['batches'][3:]
        self.cfg = {'source_capsule': str(self.source), 'source_closure': str(self.closure),
                    'source_closure_sha256': w.sha_file(self.closure), 'capsule': str(self.root),
                    'isolated_media': str(self.media), 'new_child': str(self.child), 'expected_active_saved': 240,
                    'expected_batch_ids': [b['batch_id'] for b in targets],
                    'expected_sample_ids': [sid for b in targets for sid in b['sample_ids']],
                    'checkpoint_saved_rows': [400, 800, 1200], 'max_additional_transport_calls': 2880}
        self.write_config(); self.clock = fixtures.Clock()
        self.clock.t = w._ledger(self.source_child, self.source_plan)[-1]['epoch'] + 1

    def write_config(self):
        w.write(self.base, self.config.name, self.cfg)

    def prepare(self):
        with contextlib.redirect_stdout(io.StringIO()): return stage.prepare(self.config)

    def run_checkpoint(self, fetcher=None, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return stage.run_checkpoint(self.root, fetcher=fetcher, clock=self.clock.now, sleep=self.clock.sleep, **kw)

    def preserved(self):
        self.assertEqual({p: w.sha_file(p) for p in self.source_files}, self.source_files)
        self.fixture.preserved()
        if self.child.exists():
            plan = w.load(self.child / 'continuous_plan.json')
            rows = [r for b in plan['batches'] for r in w._rows(self.child, b)]
            self.assertEqual(rows[:240], self.source_rows)
            for relative, sha in w.load(self.root / 'Copied_Native_Files.json').items():
                self.assertEqual(w.sha_file(self.child / relative), sha)

    def test_real_entry_exact_sequential400_checkpoints_final_noop_and_old240(self):
        self.prepare(); fetch = Mock(side_effect=fixtures.response)
        calls = 0
        for target, delta in ((400, 160), (800, 400), (1200, 400)):
            result = self.run_checkpoint(fetch); calls += delta
            self.assertEqual(fetch.call_count, calls)
            self.assertEqual(result['saved_active_rows'], target)
            self.assertEqual(result['checkpoint_target_saved_rows'], target)
            self.assertEqual(result['new_transport_reservations'], calls)
            self.assertEqual(result['runtime_binding']['checkpoint_summary_sha256'],
                             w.sha_file(self.child / f'checkpoint_{target:08d}/summary.json'))
            if target < 1200:
                self.assertFalse((self.child / f'batches/batch_{target//80+1:06d}/pilot.sqlite').exists())
        expected = [r['url'] for r in w.readcsv(self.child / 'queue.csv')][240:1200]
        self.assertEqual([call.args[0] for call in fetch.call_args_list], expected)
        self.assertEqual(result['status'], 'bounded_stage_finished_pending_review')
        self.assertEqual(result['stage_remaining_urls'], 0)
        nofetch = Mock(side_effect=AssertionError('Completed stage cannot fetch'))
        self.assertEqual(self.run_checkpoint(nofetch)['network_calls_this_invocation'], 0)
        nofetch.assert_not_called(); self.assertEqual(len(list((self.root / 'run_receipts').glob('*.json'))), 3)
        self.preserved()

    def test_terminal_response_interruption_recovers_to_same_checkpoint_without_duplicate(self):
        self.prepare(); fetch = Mock(side_effect=fixtures.response)
        with patch.object(w.pilot, 'save_snapshot', side_effect=KeyboardInterrupt): self.run_checkpoint(fetch)
        self.assertEqual(fetch.call_count, 1)
        result = self.run_checkpoint(fetch)
        self.assertEqual(fetch.call_count, 160)
        self.assertEqual(len({call.args[0] for call in fetch.call_args_list}), 160)
        self.assertEqual(result['saved_active_rows'], 400)
        self.assertEqual(result['new_transport_reservations'], 160)
        self.assertFalse((self.child / 'batches/batch_000006/pilot.sqlite').exists()); self.preserved()

    def test_last_saved_row_before_checkpoint_crash_closes_offline_without_advancing(self):
        self.prepare(); fetch = Mock(side_effect=fixtures.response)
        with patch.object(w, '_checkpoint', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.run_checkpoint(fetch)
        self.assertEqual(fetch.call_count, 160)
        _, _, interrupted = stage.inspect(self.root)
        self.assertEqual(interrupted['saved_active_rows'], 400)
        self.assertEqual(interrupted['next_checkpoint_saved_rows'], 400)
        self.assertTrue(interrupted['checkpoint_reconciliation_pending'])
        nofetch = Mock(side_effect=AssertionError('Checkpoint reconciliation must stay offline'))
        closed = self.run_checkpoint(nofetch); nofetch.assert_not_called()
        self.assertEqual(closed['saved_active_rows'], 400)
        self.assertEqual(closed['network_calls_this_invocation'], 0)
        self.assertFalse(closed['checkpoint_reconciliation_pending'])
        self.assertEqual(closed['next_checkpoint_saved_rows'], 800)
        self.assertFalse((self.child / 'batches/batch_000006/pilot.sqlite').exists())
        self.preserved()

    def test_checkpoint_receipt_crash_closes_offline_even_when_worker_summary_exists(self):
        self.prepare(); fetch = Mock(side_effect=fixtures.response)
        with patch.object(stage, '_write_receipt', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.run_checkpoint(fetch)
        self.assertEqual(fetch.call_count, 160)
        self.assertTrue((self.child / 'checkpoint_00000400/summary.json').is_file())
        _, _, interrupted = stage.inspect(self.root)
        self.assertTrue(interrupted['checkpoint_reconciliation_pending'])
        nofetch = Mock(side_effect=AssertionError('Receipt reconciliation must not fetch'))
        closed = self.run_checkpoint(nofetch); nofetch.assert_not_called()
        self.assertEqual(closed['saved_active_rows'], 400)
        self.assertFalse(closed['checkpoint_reconciliation_pending']); self.preserved()

    def test_receipt_number_gap_never_overwrites_prior_receipt(self):
        self.root.mkdir()
        stage._write_receipt(self.root, {'synthetic_fixture': True, 'ordinal': 1})
        stage._write_receipt(self.root, {'synthetic_fixture': True, 'ordinal': 3})
        folder = self.root / 'run_receipts'
        (folder / '000002.json').rename(folder / '000003.json')
        previous = (folder / '000003.json').read_bytes()
        stage._write_receipt(self.root, {'synthetic_fixture': True, 'ordinal': 4})
        self.assertEqual((folder / '000003.json').read_bytes(), previous)
        self.assertTrue((folder / '000004.json').is_file())

    def test_next_segment_first_terminal_response_recovers_without_repeating_401(self):
        self.prepare(); fetch = Mock(side_effect=fixtures.response)
        first = self.run_checkpoint(fetch)
        self.assertEqual(first['saved_active_rows'], 400); self.assertEqual(fetch.call_count, 160)
        with patch.object(w.pilot, 'save_snapshot', side_effect=KeyboardInterrupt): self.run_checkpoint(fetch)
        self.assertEqual(fetch.call_count, 161)
        _, _, interrupted = stage.inspect(self.root)
        self.assertEqual(interrupted['saved_active_rows'], 400)
        self.assertFalse(interrupted['checkpoint_reconciliation_pending'])
        self.assertEqual(interrupted['next_checkpoint_saved_rows'], 800)
        original = w._assess_row
        expected_id = self.source_plan['batches'][5]['sample_ids'][0]
        def stop_after_recovered_commit(*args, **kw):
            answer = original(*args, **kw)
            if args[2]['sample_id'] == expected_id: raise KeyboardInterrupt()
            return answer
        with patch.object(w, '_assess_row', side_effect=stop_after_recovered_commit):
            recovered = self.run_checkpoint(fetch)
        self.assertEqual(recovered['saved_active_rows'], 401)
        self.assertEqual(fetch.call_count, 161)
        self.assertEqual(len({call.args[0] for call in fetch.call_args_list}), 161)
        self.assertEqual(recovered['new_transport_reservations'], 161)
        self.assertEqual(recovered['next_checkpoint_saved_rows'], 800)
        self.preserved()

    def test_partial_second_batch_resume_counts_remaining_batches_not_full_checkpoint_again(self):
        self.prepare(); fetch = Mock(side_effect=fixtures.response); real = w.pilot.save_snapshot
        count = 0
        def interrupted(*args, **kw):
            nonlocal count
            count += 1
            if count == 85: raise KeyboardInterrupt()
            return real(*args, **kw)
        with patch.object(w.pilot, 'save_snapshot', side_effect=interrupted): self.run_checkpoint(fetch)
        self.assertEqual(fetch.call_count, 85)
        _, _, partial = stage.inspect(self.root); self.assertEqual(partial['saved_active_rows'], 324)
        result = self.run_checkpoint(fetch)
        self.assertEqual(result['saved_active_rows'], 400); self.assertEqual(fetch.call_count, 160)
        self.assertFalse((self.child / 'batches/batch_000006/pilot.sqlite').exists()); self.preserved()

    def test_bound_retry_budget_stops_before_second_transport_and_no_resume(self):
        self.cfg['max_additional_transport_calls'] = 1; self.write_config(); self.prepare()
        fetch = Mock(side_effect=lambda u, t, **kw: {**fixtures.response(u, t), 'status': 503, 'text': 'Synthetic transient failure'})
        result = self.run_checkpoint(fetch)
        self.assertEqual(result['status'], 'halted_no_automatic_resume')
        self.assertEqual(result['new_transport_reservations'], 1); self.assertEqual(fetch.call_count, 1)
        self.run_checkpoint(fetch); self.assertEqual(fetch.call_count, 1); self.preserved()

    def test_unknown_inflight_halt_is_not_retried(self):
        self.prepare(); fetch = Mock(side_effect=KeyboardInterrupt)
        self.run_checkpoint(fetch); result = self.run_checkpoint(fetch)
        self.assertEqual(result['status'], 'halted_no_automatic_resume')
        self.assertEqual(fetch.call_count, 1); self.preserved()

    def test_low_disk_stops_before_any_new_reservation(self):
        self.prepare(); fetch = Mock(side_effect=fixtures.response)
        result = self.run_checkpoint(fetch, disk_free=lambda p: 0)
        fetch.assert_not_called(); self.assertEqual(result['new_transport_reservations'], 0)
        self.assertEqual(result['status'], 'halted_no_automatic_resume'); self.preserved()

    def test_access_halt_is_permanent_and_deleted_halt_or_reset_status_rejected(self):
        self.prepare(); fetch = Mock(side_effect=lambda u, t, **kw: {**fixtures.response(u, t), 'status': 403, 'text': 'Forbidden fixture'})
        result = self.run_checkpoint(fetch); self.assertEqual(result['status'], 'halted_no_automatic_resume')
        halt = self.child / 'safety_halt.json'; raw = halt.read_bytes()
        self.run_checkpoint(fetch); self.assertEqual(fetch.call_count, 1)
        halt.unlink()
        with self.assertRaises(ValueError): stage.inspect(self.root)
        halt.write_bytes(raw); plan = w.load(self.child / 'continuous_plan.json'); w._state(self.child, plan, w.PENDING)
        with self.assertRaises(ValueError): self.run_checkpoint(fetch)
        self.assertEqual(fetch.call_count, 1); self.preserved()

    def test_wrong_order_scope_checkpoint_and_budget_fail_before_destination(self):
        baseline = dict(self.cfg)
        cases = {'expected_sample_ids': list(reversed(self.cfg['expected_sample_ids'])),
                 'expected_batch_ids': self.cfg['expected_batch_ids'][1:],
                 'checkpoint_saved_rows': [480, 800, 1200], 'max_additional_transport_calls': 2881}
        for key, value in cases.items():
            with self.subTest(key=key):
                self.cfg = {**baseline, key: value}; self.write_config()
                with self.assertRaises(ValueError): self.prepare()
                self.assertFalse(self.child.exists())
        self.preserved()

    def test_no_authorization_no_fetch_and_native_prefix_tamper_rejected(self):
        self.prepare()
        with self.assertRaises(ValueError): self.run_checkpoint()
        p = self.child / 'batches/batch_000001/pilot.sqlite'
        with sqlite3.connect(p) as db:
            db.execute("UPDATE articles SET title='Changed' WHERE ordinal=0")
        with self.assertRaises(ValueError): stage.inspect(self.root)
        self.assertEqual({p: w.sha_file(p) for p in self.source_files}, self.source_files)

    def test_frozen_queue_mutation_rejected_without_fetch(self):
        self.prepare(); p = self.child / 'queue.csv'; p.write_bytes(p.read_bytes() + b'\n')
        fetch = Mock(side_effect=fixtures.response)
        with self.assertRaises(ValueError): self.run_checkpoint(fetch)
        fetch.assert_not_called(); self.assertEqual({p: w.sha_file(p) for p in self.source_files}, self.source_files)


if __name__ == '__main__': unittest.main()

"""Offline supervisor-path tests for inherited checkpoint readings.

Generated control seals have empty synthetic reading sets. These fixtures test
reuse/order/bindings only and attest no real source reading. The native-worker
and adapter integration suites separately exercise SQL, transport and export
reconciliation. No production data or network is accessed here.
"""
import contextlib
import tempfile
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawler_core import tiempo_remaining_campaign as c
from crawler_core import tiempo_stage_review as review
from crawler_core import tiempo_continuous_v5 as w


class InheritedGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'new'
        self.root.mkdir()
        self.donor = self.base / 'old'
        self.donor.mkdir()
        self.plan = {'plan_sha256': 'a' * 64, 'seed_context': {}, 'original_input_sha256': 'b' * 64,
                     'row_count': 2000, 'max_fetch_calls': 6000, 'batches': [{}] * 25}
        self.part = {'plan_index': 42, 'rows': 2000, 'sha256': 'b' * 64}
        w.write(self.root, 'provenance.json', {'synthetic_fixture': True})
        self.m = {'root': str(self.root), 'media': str(self.root / 'Media'), 'synthetic_fixture': True,
                  'parts': [self.part], 'program_sha256': c.code_binding(), 'min_free_bytes': 1,
                  'baseline_saved': 82000, 'max_new_calls': 6000, 'remaining_rows': 2000,
                  'obligations': {'path': str(self.root / 'pending.json')},
                  'connection_recovery': {'child_index': 42, 'acknowledgment': {'synthetic': True},
                                           'provenance': c._bound(self.root / 'provenance.json')}}
        self.child = c.child_path(self.m, 42)
        self.child.mkdir(parents=True)
        w.write(self.child, 'continuous_plan.json', self.plan)
        self.inherited = [self.gate(self.donor, n) for n in (400, 800, 1200)]
        self.m['connection_recovery']['inherited_checkpoint_gates'] = self.inherited
        last = self.inherited[-1]['coverage']
        self.m['historical_ai_receipts'] = [{'coverage': last['path'], 'sha256': last['sha256']}]
        self.counts = {'saved': 1590, 'calls': 1591, 'pending_native_attempts': 0, 'open_transport': False}
        self.new_requests = 0
        self.callback_results = []
        self.selected_history = []
        self.after_fresh_gate = False

    def files(self, folder, n):
        folder.mkdir(parents=True, exist_ok=True)
        selection = {'schema': review.SCHEMA, 'synthetic_control_fixture': True,
                     'snapshot': {'plan_sha256': self.plan['plan_sha256'], 'checkpoint_rows': n},
                     'human_approval': False}
        selection['selection_sha256'] = w.digest(selection)
        sp = folder / f'selection_{n:08d}.json'
        w.write(folder, sp.name, selection)
        cov = {'schema': review.COVERAGE_SCHEMA, 'gate_status': 'collection_gate_satisfied',
               'selection_binding': c._bound(sp), 'records': [], 'distinct_actual_ai_read_ids': [],
               'receipt_bindings': [], 'previous_seals': [], 'covered_strata': [],
               'human_approval': False, 'synthetic_control_fixture': True}
        cov['coverage_sha256'] = w.digest(cov)
        cp = folder / 'coverage.json'
        w.write(folder, cp.name, cov)
        return c._bound(sp), c._bound(cp)

    def gate(self, root, n):
        selection, coverage = self.files(root / f'gate_{n}', n)
        return c.event(root, 'checkpoint_gate_satisfied', index=42, rows=n,
                       selection=selection, coverage=coverage, new_saved=n, new_calls=n)

    def select(self, child, folder, *, checkpoint_rows, history_receipts, **kwargs):
        self.assertEqual(checkpoint_rows, 1600, 'Historical checkpoint must not be reselected')
        self.assertEqual(kwargs['inherited_failure_acknowledgment'], self.m['connection_recovery']['acknowledgment'])
        self.selected_history.append([dict(item) for item in history_receipts])
        selection, _ = self.files(folder, checkpoint_rows)
        return {'selection_path': selection['path']}

    def fake_worker(self, child, media, *, checkpoint_callback, **kwargs):
        for n in (400, 800, 1200):
            result = checkpoint_callback(child, self.plan, [{'rows': n}])
            self.callback_results.append((n, result))
            if not result:
                return self.paused()
        if self.counts['saved'] < 1600:
            self.new_requests += 1600 - self.counts['saved']
            self.counts['calls'] += 1600 - self.counts['saved']
            self.counts['saved'] = 1600
        passed = checkpoint_callback(child, self.plan, [{'rows': 1600}])
        self.callback_results.append((1600, passed))
        if not passed:
            return self.paused()
        self.after_fresh_gate = True
        # This injected new technical failure must still stop the real supervisor.
        return {'status': 'halted_no_automatic_resume', 'result_rows': 1600,
                'synthetic_new_failure': 'connection_failure_after_fresh_gate'}

    def paused(self):
        p = self.root / 'native_pause.json'
        w.write(self.root, p.name, {'synthetic_fixture': True})
        return {'status': c.worker.PAUSED, 'pause_receipt_path': str(p), 'pause_receipt_sha256': c.sha(p)}

    def execute(self, *, approve=False, worker=None):
        def seal(selection, paths, output):
            self.files(Path(output).parent, 1600)
        with contextlib.ExitStack() as stack:
            patches = [(c, 'read_bound', lambda *a, **k: (self.m, c.events(self.root))),
                       (c, 'other_collectors', lambda: []),
                       (c, '_completed', lambda *a: ([], {}, 0, 0)),
                       (c, 'inspect', lambda *a: {'active': {'path': str(self.child), **self.counts}}),
                       (c, 'storage_forecast', lambda *a, **k: {'enough_for_forecast_and_floor': True}),
                       (w, 'load_plan', lambda *a: (self.plan, [])),
                       (c, '_counts', lambda *a: dict(self.counts)),
                       (c.worker, 'run', worker or self.fake_worker),
                       (review, 'select_checkpoint', self.select),
                       (review, 'validate_gate', lambda *a: {'status': 'collection_gate_satisfied' if approve else
                                                          'blocked_pending_actual_ai_reading'}),
                       (review, 'seal_gate', seal)]
            for obj, key, value in patches:
                stack.enter_context(patch.object(obj, key, side_effect=value))
            return c.run(self.root, resume=True, fetcher=Mock(side_effect=AssertionError('NO HTTP')),
                         disk_free=lambda _: 10**12, wait_for_review=False)

    def test_reuses_prior_gates_before_selection_preserves_latest_history_and_blocks_1601(self):
        state = self.execute()
        self.assertEqual(state['status'], 'paused_safe')
        self.assertEqual(self.new_requests, 10)
        self.assertEqual(self.callback_results, [(400, True), (800, True), (1200, True), (1600, False)])
        self.assertEqual(self.selected_history, [self.m['historical_ai_receipts']])
        markers = [e for e in c.events(self.root) if e['kind'] == 'checkpoint_gate_inherited']
        self.assertEqual([e['rows'] for e in markers], [400, 800, 1200])
        self.assertTrue(all(e['new_actual_ai_read_count'] == 0 and not e['human_approval'] for e in markers))
        self.assertFalse(self.after_fresh_gate)
        self.assertFalse((self.root / 'reviews/plan_000042/checkpoint_00000400').exists())
        state = self.execute()
        self.assertEqual(state['status'], 'paused_safe')
        self.assertEqual(self.new_requests, 10)
        self.assertEqual(len([e for e in c.events(self.root) if e['kind'] == 'checkpoint_gate_inherited']), 3)

    def test_interrupt_after_first_inherited_marker_preserves_1200_history(self):
        original = c.event
        def interrupt(root, kind, **kw):
            entry = original(root, kind, **kw)
            if kind == 'checkpoint_gate_inherited':
                raise KeyboardInterrupt('synthetic interruption after durable imported gate')
            return entry
        with patch.object(c, 'event', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.execute()
        self.assertEqual(self.new_requests, 0)
        self.execute()
        self.assertEqual(self.selected_history, [self.m['historical_ai_receipts']])
        self.assertEqual(len([e for e in c.events(self.root) if e['kind'] == 'checkpoint_gate_inherited']), 3)

    def test_changed_historical_selection_stops_before_new_requests(self):
        p = Path(self.inherited[0]['selection']['path'])
        p.write_bytes(p.read_bytes() + b' ')
        state = self.execute()
        self.assertEqual(state['status'], 'technical_stop_requires_investigation')
        self.assertEqual(self.new_requests, 0)

    def test_wrong_native_plan_is_not_excused_by_inherited_seal(self):
        self.plan['plan_sha256'] = 'c' * 64
        state = self.execute()
        self.assertEqual(state['status'], 'technical_stop_requires_investigation')
        self.assertEqual(self.new_requests, 0)
        self.assertIn('another native plan', w.load(self.root / 'technical_stop.json')['detail'])

    def test_fresh_1600_pass_needed_and_new_technical_fault_still_halts(self):
        state = self.execute(approve=True)
        self.assertTrue(self.after_fresh_gate)
        self.assertEqual(state['status'], 'technical_stop_requires_investigation')
        gates = c._checkpoint_gate_events(self.m, c.events(self.root), 42)
        self.assertEqual([e['rows'] for e in gates], [400, 800, 1200, 1600])
        self.assertEqual(gates[-1]['kind'], 'checkpoint_gate_satisfied')
        self.assertFalse(gates[-1]['human_approval'])
        stopped_worker = Mock(side_effect=AssertionError('No restart after fresh technical fault'))
        self.assertEqual(self.execute(worker=stopped_worker)['status'], 'technical_stop_requires_investigation')
        stopped_worker.assert_not_called()

    def test_completion_receipt_adoption_accepts_inherited_and_fresh_exact_targets(self):
        self.execute(approve=True)
        self.gate(self.root, 2000)
        self.m['campaign_sha256'] = 'd' * 64
        doc = {'campaign_sha256': self.m['campaign_sha256'], 'index': 42,
               'saved': 2000, 'calls': 2001, 'bindings': []}
        doc['receipt_sha256'] = w.digest(doc)
        w.write(self.child, 'remaining_completion_receipt.json', doc)
        w.write(self.child, 'continuous_state.json', {'collection_inputs_finished': True})
        counts = {'saved': 2000, 'calls': 2001, 'pending_native_attempts': 0, 'open_transport': False}
        with patch.object(c, '_counts', return_value=counts):
            adopted, path = c._adopt_closed_child(self.m, self.part, self.child)
        self.assertEqual(adopted, doc)
        self.assertEqual(path.name, 'remaining_completion_receipt.json')

    def test_duplicate_or_changed_inherited_marker_is_rejected(self):
        self.execute()
        events = c.events(self.root)
        marker = next(e for e in events if e['kind'] == 'checkpoint_gate_inherited')
        with self.assertRaisesRegex(ValueError, 'Duplicate checkpoint'):
            c._checkpoint_gate_events(self.m, events + [marker])
        with self.assertRaisesRegex(ValueError, 'differs from bound'):
            c._verify_inherited_gate_event(self.m, {**marker, 'new_actual_ai_read_count': 1})


if __name__ == '__main__':
    unittest.main()

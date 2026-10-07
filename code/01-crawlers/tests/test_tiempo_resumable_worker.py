"""Isolated pause/crash tests with real native storage and no news network."""
import contextlib
import io
import json
from pathlib import Path
import signal
import sqlite3
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawler_core import tiempo_resumable_worker as worker
from crawler_core import tiempo_continuous_v5 as w
import test_tiempo_continuous_v5 as fixtures
response = fixtures.response


class ResumableWorkerTests(unittest.TestCase):
    setUp = fixtures.V5Tests.setUp
    freeze = fixtures.V5Tests.freeze
    current = fixtures.V5Tests.current

    def execute(self, fetch=None, **options):
        args = dict(max_batches=25, fetcher=fetch or Mock(side_effect=response),
                    clock=self.clock.now, sleep=self.clock.sleep,
                    install_signal_handlers=False)
        args.update(options)
        with contextlib.redirect_stdout(io.StringIO()):
            return worker.run(self.root, self.media, **args)

    def counts(self):
        result = {'articles': 0, 'attempts': 0, 'pending': 0}
        for path in self.root.glob('batches/*/pilot.sqlite'):
            with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
                result['articles'] += db.execute('SELECT count(*) FROM articles').fetchone()[0]
                result['attempts'] += db.execute('SELECT count(*) FROM fetch_attempts').fetchone()[0]
                result['pending'] += db.execute('SELECT count(*) FROM fetch_attempts WHERE completed_at IS NULL').fetchone()[0]
        return result

    def assert_paused(self, state, rows):
        self.assertEqual(state['status'], worker.PAUSED)
        self.assertEqual(state['result_rows'], rows)
        self.assertFalse((self.root / 'safety_halt.json').exists())
        self.assertEqual(self.counts()['pending'], 0)
        receipt = w.load(state['pause_receipt_path'])
        self.assertEqual(receipt['incomplete_native_attempts'], 0)
        self.assertEqual(receipt['open_transport_calls'], 0)
        self.assertFalse(receipt['article_acceptance'])
        self.assertEqual(w.sha_file(state['pause_receipt_path']), state['pause_receipt_sha256'])

    def test_pause_before_first_url_creates_no_attempt_and_resumes(self):
        self.freeze(2); fetch = Mock(side_effect=response)
        paused = self.execute(fetch, stop_requested=lambda: True)
        self.assert_paused(paused, 0); fetch.assert_not_called()
        self.assertEqual(self.counts(), {'articles': 0, 'attempts': 0, 'pending': 0})
        pause_bytes = Path(paused['pause_receipt_path']).read_bytes()
        finished = self.execute(fetch)
        self.assertTrue(finished['collection_inputs_finished']); self.assertEqual(fetch.call_count, 2)
        self.assertEqual(Path(paused['pause_receipt_path']).read_bytes(), pause_bytes)

    def test_pause_during_request_finishes_current_save_and_check(self):
        self.freeze(3); flag = [False]
        def fake(url, timeout, **kw):
            flag[0] = True
            return response(url, timeout)
        fetch = Mock(side_effect=fake)
        state = self.execute(fetch, stop_requested=lambda: flag[0])
        self.assert_paused(state, 1); self.assertEqual(fetch.call_count, 1)
        self.assertEqual(len(list((self.root / 'row_checks').glob('*.json'))), 1)
        self.assertEqual(w.load(self.root / 'batches/batch_000001/export_manifest.json')['result_rows'], 1)

    def test_pause_during_interrequest_wait_leaves_no_fake_pending_attempt(self):
        self.freeze(3); flag = [False]; fetch = Mock(side_effect=response)
        def sleeping(seconds):
            self.clock.sleep(seconds); flag[0] = True
        state = self.execute(fetch, sleep=sleeping, stop_requested=lambda: flag[0])
        self.assert_paused(state, 1); self.assertEqual(fetch.call_count, 1)
        self.assertEqual(self.counts(), {'articles': 1, 'attempts': 1, 'pending': 0})
        resumed = self.execute(fetch)
        self.assertTrue(resumed['collection_inputs_finished']); self.assertEqual(fetch.call_count, 3)

    def test_pause_mid_retry_finishes_same_logical_request_with_original_policy(self):
        self.freeze(2); flag = [False]; calls = []
        def fake(url, timeout, **kw):
            calls.append(url); flag[0] = True
            if len(calls) == 1:
                return {**response(url, timeout), 'status': None, 'error': 'operation timed out', 'text': 'partial'}
            if len(calls) == 2:
                return {**response(url, timeout), 'status': 503, 'text': 'service down'}
            return response(url, timeout)
        state = self.execute(Mock(side_effect=fake), stop_requested=lambda: flag[0])
        self.assert_paused(state, 1); self.assertEqual(calls, [self.rows[0]['url']] * 3)
        self.assertEqual(self.clock.waits, [5, 15]); self.assertEqual(len(w._ledger(self.root, w.load(self.root / 'continuous_plan.json'))), 6)

    def test_pause_after_commit_before_next_url_partial_batch_resumes_without_refetch(self):
        self.freeze(4); flag = [False]; original = w._assess_row; fetch = Mock(side_effect=response)
        def assess(*args, **kw):
            result = original(*args, **kw)
            if args[2]['sample_id'] == self.rows[1]['sample_id']:
                flag[0] = True
            return result
        with patch.object(w, '_assess_row', side_effect=assess):
            state = self.execute(fetch, stop_requested=lambda: flag[0])
        self.assert_paused(state, 2); first = self.current()
        self.assertTrue(self.execute(fetch)['collection_inputs_finished'])
        self.assertEqual(fetch.call_count, 4); self.assertEqual(self.current()[:2], first)

    def test_terminal_response_mid_save_reused_on_resume_with_pause(self):
        self.freeze(2); fetch = Mock(side_effect=response)
        with patch.object(w.pilot, 'save_snapshot', side_effect=KeyboardInterrupt):
            state = self.execute(fetch)
        self.assertEqual(state['status'], 'interrupted_requires_explicit_invocation')
        self.assertEqual(fetch.call_count, 1)
        resumed = self.execute(fetch, stop_requested=lambda: True)
        self.assert_paused(resumed, 1); self.assertEqual(fetch.call_count, 1)
        self.assertTrue(self.execute(fetch)['collection_inputs_finished']); self.assertEqual(fetch.call_count, 2)

    def test_uncertain_transport_never_claims_safe_pause_and_never_refetches(self):
        self.freeze(2); fetch = Mock(side_effect=KeyboardInterrupt)
        self.execute(fetch)
        state = self.execute(fetch, stop_requested=lambda: True)
        self.assertEqual(state['status'], 'halted_no_automatic_resume')
        self.assertEqual(fetch.call_count, 1); self.assertFalse((self.root / 'pause_receipts').exists())
        halt = (self.root / 'safety_halt.json').read_bytes()
        self.execute(fetch); self.assertEqual(fetch.call_count, 1)
        self.assertEqual((self.root / 'safety_halt.json').read_bytes(), halt)

    def test_transport_connection_loss_is_preserved_technical_halt(self):
        self.freeze(2); fetch = Mock(side_effect=ConnectionError('network disconnected'))
        state = self.execute(fetch, stop_requested=lambda: fetch.call_count > 0)
        self.assertEqual(state['status'], 'halted_no_automatic_resume')
        self.assertEqual(fetch.call_count, 1); self.assertEqual(self.counts()['articles'], 1)
        self.assertEqual(self.current()[0]['qa_status'], 'error')
        self.assertFalse((self.root / 'pause_receipts').exists())

    def test_initial_low_disk_is_halt_without_fake_pending_attempt(self):
        self.freeze(2); fetch = Mock(side_effect=response)
        state = self.execute(fetch, disk_free=lambda path: 0)
        self.assertEqual(state['status'], 'halted_no_automatic_resume'); fetch.assert_not_called()
        self.assertEqual(self.counts()['attempts'], 0)
        self.assertEqual(w.load(self.root / 'safety_halt.json')['reason'], 'low_disk_space')

    def test_low_disk_during_retry_remains_technical_halt(self):
        self.freeze(2); fetch = Mock(side_effect=lambda u, t, **kw: {**response(u, t), 'status': 503})
        space = Mock(side_effect=[100, 100, 0])
        state = self.execute(fetch, disk_free=space, stop_requested=lambda: fetch.call_count > 0)
        self.assertEqual(state['status'], 'halted_no_automatic_resume'); self.assertEqual(fetch.call_count, 1)
        self.assertFalse((self.root / 'pause_receipts').exists())

    def test_sigint_and_sigterm_handler_only_record_intent_and_restore(self):
        controller = worker.StopController(); prior = signal.getsignal(signal.SIGINT)
        with worker.graceful_signals(controller):
            signal.getsignal(signal.SIGINT)(signal.SIGINT, None)
            self.assertTrue(controller()); self.assertEqual(controller.signal_number, signal.SIGINT)
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
            self.assertEqual(controller.signal_number, signal.SIGTERM)
        self.assertEqual(signal.getsignal(signal.SIGINT), prior)

    def test_hard_saved_boundary_and_offline_closure_make_no_next_request(self):
        self.freeze(5); fetch = Mock(side_effect=response)
        state = self.execute(fetch, stop_at_saved_rows=3)
        self.assertTrue(state['checkpoint_boundary_reached']); self.assertEqual(fetch.call_count, 3)
        with contextlib.redirect_stdout(io.StringIO()):
            closed = worker.close_saved_boundary(self.root, self.media, 3, install_signal_handlers=False)
        self.assertTrue(closed['checkpoint_boundary_reached']); self.assertEqual(fetch.call_count, 3)
        self.assertEqual(w.load(self.root / 'checkpoint_00000003/summary.json')['rows'], 3)
        self.assertTrue(self.execute(fetch)['collection_inputs_finished']); self.assertEqual(fetch.call_count, 5)

    def test_commit_before_export_crash_offline_boundary_repairs_exports_without_refetch(self):
        self.freeze(3); fetch = Mock(side_effect=response)
        with patch.object(w.pilot, 'export_outputs', side_effect=RuntimeError('simulated power loss during export')):
            with self.assertRaises(RuntimeError):
                self.execute(fetch, stop_at_saved_rows=2)
        self.assertEqual(self.counts()['articles'], 2); self.assertEqual(fetch.call_count, 2)
        state = self.execute(fetch, stop_at_saved_rows=2)
        self.assertTrue(state['checkpoint_boundary_reached']); self.assertEqual(fetch.call_count, 2)

    def test_terminal_404_mid_save_reuses_error_result_without_refetch(self):
        self.freeze(2); fetch = Mock(side_effect=lambda u, t, **kw: {**response(u, t), 'status': 404, 'text': 'gone'})
        with patch.object(w.pilot, 'save_snapshot', side_effect=KeyboardInterrupt):
            self.execute(fetch)
        state = self.execute(fetch, stop_at_saved_rows=1)
        self.assertTrue(state['checkpoint_boundary_reached']); self.assertEqual(fetch.call_count, 1)
        self.assertEqual(self.current()[0]['qa_status'], 'error')

    def test_incomplete_retry_chain_never_refetches_on_resume(self):
        self.freeze(2); fetch = Mock(side_effect=lambda u, t, **kw: {**response(u, t), 'status': 503})
        with patch.object(self.clock, 'sleep', side_effect=KeyboardInterrupt):
            self.execute(fetch, sleep=self.clock.sleep)
        state = self.execute(fetch)
        self.assertEqual(state['status'], 'halted_no_automatic_resume'); self.assertEqual(fetch.call_count, 1)

    def test_final_partial_checkpoint_callback_hold_replayed_before_finish(self):
        self.freeze(3); fetch = Mock(side_effect=response); calls = []
        def gate(root, plan, summaries):
            calls.append(sum(s['rows'] for s in summaries)); return False
        state = self.execute(fetch, checkpoint_callback=gate)
        self.assert_paused(state, 3); self.assertEqual(calls, [3]); self.assertEqual(fetch.call_count, 3)
        self.assertFalse((self.root / 'continuation_context.json').exists())
        gate_ok = Mock(return_value=True)
        state = self.execute(fetch, checkpoint_callback=gate_ok)
        self.assertTrue(state['collection_inputs_finished']); gate_ok.assert_called_once()
        self.assertEqual(fetch.call_count, 3)

    def test_changed_native_review_or_export_cannot_be_certified_as_paused(self):
        self.freeze(3); fetch = Mock(side_effect=response)
        self.execute(fetch, stop_at_saved_rows=1)
        path = self.root / 'batches/batch_000001/retained_results.csv'
        path.write_text('tampered')
        state = self.execute(fetch, stop_requested=lambda: True)
        self.assertEqual(state['status'], 'halted_no_automatic_resume')
        self.assertEqual(fetch.call_count, 1)

    def test_corrupt_native_export_and_spoofed_manifest_count_are_preserved_and_halted(self):
        self.freeze(3); fetch = Mock(side_effect=response)
        self.execute(fetch, stop_at_saved_rows=1)
        B = self.root / 'batches/batch_000001'
        (B / 'retained_results.csv').write_bytes(b'CORRUPTED NATIVE EXPORT')
        manifest = w.load(B / 'export_manifest.json'); manifest['result_rows'] = 0
        w.write(B, 'export_manifest.json', manifest)
        before = (B / 'export_manifest.json').read_bytes()
        state = self.execute(fetch, stop_requested=lambda: True)
        self.assertEqual(state['status'], 'halted_no_automatic_resume')
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual((B / 'retained_results.csv').read_bytes(), b'CORRUPTED NATIVE EXPORT')
        self.assertEqual((B / 'export_manifest.json').read_bytes(), before)

    def test_corrupt_native_export_and_deleted_manifest_are_preserved_and_halted(self):
        self.freeze(3); fetch = Mock(side_effect=response)
        self.execute(fetch, stop_at_saved_rows=1)
        B = self.root / 'batches/batch_000001'
        (B / 'retained_results.csv').write_bytes(b'CORRUPTED NATIVE EXPORT')
        (B / 'export_manifest.json').unlink()
        state = self.execute(fetch, stop_requested=lambda: True)
        self.assertEqual(state['status'], 'halted_no_automatic_resume')
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual((B / 'retained_results.csv').read_bytes(), b'CORRUPTED NATIVE EXPORT')
        self.assertFalse((B / 'export_manifest.json').exists())

    def test_corrupt_certified_export_halts_before_ordinary_resume_fetch_or_rewrite(self):
        self.freeze(3); fetch = Mock(side_effect=response)
        self.execute(fetch, stop_at_saved_rows=1)
        path = self.root / 'batches/batch_000001/retained_results.csv'
        path.write_bytes(b'CORRUPTED NATIVE EXPORT')
        state = self.execute(fetch)
        self.assertEqual(state['status'], 'halted_no_automatic_resume')
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(path.read_bytes(), b'CORRUPTED NATIVE EXPORT')

    def test_invented_review_state_halts_before_ordinary_resume_and_remains_visible(self):
        self.freeze(3); fetch = Mock(side_effect=response)
        self.execute(fetch, stop_at_saved_rows=1)
        B = self.root / 'batches/batch_000001'
        manifest = w.load(B / 'export_manifest.json')
        manifest['manual_review']['status_counts']['reviewed'] = 1
        w.write(B, 'export_manifest.json', manifest)
        before = (B / 'export_manifest.json').read_bytes()
        state = self.execute(fetch)
        self.assertEqual(state['status'], 'halted_no_automatic_resume')
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual((B / 'export_manifest.json').read_bytes(), before)

    def test_changed_native_accounting_halts_before_ordinary_resume_and_is_preserved(self):
        self.freeze(3); fetch = Mock(side_effect=response)
        self.execute(fetch, stop_at_saved_rows=1)
        B = self.root / 'batches/batch_000001'
        manifest = w.load(B / 'export_manifest.json'); manifest['retained_result_rows'] = 0
        w.write(B, 'export_manifest.json', manifest)
        before = (B / 'export_manifest.json').read_bytes()
        state = self.execute(fetch)
        self.assertEqual(state['status'], 'halted_no_automatic_resume')
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual((B / 'export_manifest.json').read_bytes(), before)

    def test_old_partial_exported_one_then_commit_two_crash_recovers_without_refetch(self):
        self.freeze(3); fetch = Mock(side_effect=response)
        self.execute(fetch, stop_at_saved_rows=1)
        B = self.root / 'batches/batch_000001'
        first_rows = self.current(); old_manifest = (B / 'export_manifest.json').read_bytes()
        with patch.object(w.pilot, 'export_outputs', side_effect=RuntimeError('crash before replacing old export')):
            with self.assertRaises(RuntimeError):
                self.execute(fetch, stop_at_saved_rows=2)
        self.assertEqual(fetch.call_count, 2); self.assertEqual(self.counts()['articles'], 2)
        self.assertEqual((B / 'export_manifest.json').read_bytes(), old_manifest)
        state = self.execute(fetch, stop_at_saved_rows=2)
        self.assertTrue(state['checkpoint_boundary_reached']); self.assertEqual(fetch.call_count, 2)
        self.assertEqual(self.current()[:1], first_rows)
        self.assertEqual(w.load(B / 'export_manifest.json')['result_rows'], 2)

    def test_partial_native_export_replacement_accepts_only_exact_old_or_current_bytes(self):
        self.freeze(3); fetch = Mock(side_effect=response)
        self.execute(fetch, stop_at_saved_rows=1)
        B = self.root / 'batches/batch_000001'
        old_csv = (B / 'articles.csv').read_bytes()
        original = w.pilot.atomic_bytes
        def interrupted_write(path, data):
            original(path, data)
            if Path(path).resolve() == (B / 'articles.csv').resolve():
                raise RuntimeError('power loss after first native export replacement')
        with patch.object(w.pilot, 'atomic_bytes', side_effect=interrupted_write):
            with self.assertRaises(RuntimeError):
                self.execute(fetch, stop_at_saved_rows=2)
        self.assertEqual(fetch.call_count, 2)
        self.assertNotEqual((B / 'articles.csv').read_bytes(), old_csv)
        self.assertEqual(w.load(B / 'export_manifest.json')['result_rows'], 1)
        state = self.execute(fetch, stop_at_saved_rows=2)
        self.assertTrue(state['checkpoint_boundary_reached']); self.assertEqual(fetch.call_count, 2)
        self.assertEqual(w.load(B / 'export_manifest.json')['result_rows'], 2)

    def test_checkpoint_400_gate_holds_and_replays_before_url_401(self):
        self.freeze(401); fetch = Mock(side_effect=response); observations = []
        def hold(root, plan, summaries):
            observations.append((sum(s['rows'] for s in summaries), fetch.call_count))
            return False
        state = self.execute(fetch, checkpoint_callback=hold)
        self.assert_paused(state, 400); self.assertEqual(observations, [(400, 400)])
        # A crash after saving a checkpoint but before any approval must revisit
        # its callback before fetching the next URL. Existing native rows stay.
        resumed_observations = []
        def approve(root, plan, summaries):
            resumed_observations.append((sum(s['rows'] for s in summaries), fetch.call_count))
            return True
        state = self.execute(fetch, checkpoint_callback=approve)
        self.assertTrue(state['collection_inputs_finished'])
        self.assertEqual(resumed_observations, [(400, 400), (401, 401)])
        self.assertEqual(fetch.call_count, 401)


if __name__ == '__main__':
    unittest.main()

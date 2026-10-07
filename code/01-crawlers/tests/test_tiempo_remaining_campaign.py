"""End-to-end continuation fixtures: fake HTTP and SYNTHETIC reading receipts only.

No production source, capsule, review receipt or network is accessed. Explicit
synthetic_fixture=True forbids replacing the injected transport with news HTTP.
"""
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
from crawler_core import tiempo_continuous_v5 as w
from crawler_core import tiempo_scheduler_v5 as scheduler
from crawler_core import tiempo_remaining_campaign as campaign
from crawler_core import tiempo_stage_review as review
import test_tiempo_continuous_v5 as fixtures


class RemainingCampaignTests(unittest.TestCase):
    setUp = fixtures.V5Tests.setUp
    freeze = fixtures.V5Tests.freeze

    def build(self, total=10, chunk=4, legacy_risk_rows=0):
        self.freeze(total)
        prepared = self.base / 'prepared_remainder'
        partition = scheduler.prepare(self.queue_db, w.sha_file(self.queue_db), self.exclusions,
            prepared, start='2024-06-01', end='2024-06-02', chunk_size=chunk)
        self.source = self.root.with_name('completed_predecessor').resolve()
        context = None
        if legacy_risk_rows:
            context = {'source_history': [
                {'sample_id': f'SYNTHETIC_LEGACY_RISK_{i}', 'critical_flags': [],
                 'unexplained_flags': [], 'unexplained_families': [], 'service_failure': False}
                for i in range(legacy_risk_rows)],
                'service_history': [], 'last_transport_finish': None, 'prior_plan_receipts': []}
        w.freeze(prepared / partition['parts'][0]['path'], self.source, self.media,
            self.registry_path, w.sha_file(self.registry_path), self.exclusions,
            start='2024-06-01', end='2024-06-02', max_fetch_calls=chunk * 3,
            queue_db_path=self.queue_db, queue_db_sha256=w.sha_file(self.queue_db),
            min_free_bytes=1, seed_context=context)
        with contextlib.redirect_stdout(io.StringIO()):
            state = w.run(self.source, self.media, max_batches=25, fetcher=fixtures.response,
                          clock=self.clock.now, sleep=self.clock.sleep)
        self.assertTrue(state['collection_inputs_finished'])
        source_context = w.load(self.source / 'continuation_context.json')
        protected = self.base / 'original_technical_halt_control.json'
        w.write(self.base, protected.name, {'synthetic': True, 'status': 'original_halt_immutable'})
        paths = sorted(p for p in self.source.rglob('*') if p.is_file())
        paths += [self.queue_db, self.registry_path]
        paths += [Path(x['path']) for x in self.exclusions]
        self.source_hashes = {str(p.resolve()): w.sha_file(p) for p in paths + [protected]}
        preflight = {
            'status': 'PASS_SCOPE_AND_SOURCE_PREFLIGHT', 'issues': [],
            'source_bindings': {f'synthetic_source_{i}': campaign._bound(p) for i, p in enumerate(paths)},
            'protected_control_bindings': [campaign._bound(protected)],
            'review_obligations': {'native_pending_file_bindings': [],
                'synthetic_inherited_pending': [{'sample_id': 'SYNTHETIC_OLD_PENDING', 'status': 'not_reviewed'}]},
            'freeze_input_paths': {'prepared_path': str(prepared.resolve()), 'registry': campaign._bound(self.registry_path)},
            'source_runtime': str(self.source),
            'boundary': {'remaining_original_plan_indices': [2, len(partition['parts'])],
                'reconciled_completed_request_URLs': chunk, 'remaining_request_URLs': total - chunk,
                'global_identity_records_including_legacy2270': len(w.load_history_index(source_context['history_index'])),
                'global_charged_calls': chunk},
            'storage_projection': {'observed_allocated_bytes_per_URL': 128},
        }
        self.preflight = self.base / 'synthetic_scope_preflight.json'
        w.write(self.base, self.preflight.name, preflight)
        self.campaign_root = (self.base / 'remaining_campaign').resolve()
        self.config = self.base / 'synthetic_campaign_config.json'
        w.write(self.base, self.config.name, {'root': str(self.campaign_root),
            'preflight': campaign._bound(self.preflight), 'max_new_calls': 3 * (total - chunk),
            'synthetic_fixture': True, 'forecast_growth_multiplier': 1.1})
        self.assertEqual(campaign.prepare(self.config)['status'], 'prepared_offline_not_started')
        self.m, _ = campaign.read_bound(self.campaign_root, full=True)
        self.fixture_rows = total; self.fixture_baseline = chunk
        return self.m

    def synthetic_reading_receipt(self, selection_path):
        """Test-only reader of generated HTML; never used for real source reviews."""
        doc = w.load(selection_path)
        path = Path(selection_path).parent / 'receipts' / 'synthetic_fixture_reader.json'
        if path.exists():
            return path
        records = []
        for selected in doc['selected_records']:
            source = Path(selected['snapshot_path']).read_text()
            self.assertIn('Report new-', source)
            record = {key: selected[key] for key in (
                'sample_id', 'snapshot_sha256', 'payload_sha256', 'row_check_sha256')}
            record.update(actual_ai_read=True, human_approval=False, technical_blockers=[],
                research_status=None, scope=review.READ_SCOPE,
                note='SYNTHETIC TEST ONLY. Generated source fixture was read for this test; '
                     'this attestation proves no real news reading or research approval. '
                     'Fixture identity: ' + selected['sample_id'])
            records.append(record)
        receipt = {'schema': review.SCHEMA, 'selection_sha256': doc['selection_sha256'],
            'runtime_binding_sha256': w.digest(doc['snapshot']['bindings']),
            'actual_ai_read_ids': [r['sample_id'] for r in records],
            'actual_ai_read_count': len(records), 'human_approval': False,
            'technical_blockers': [], 'records': records}
        w.write(path.parent, path.name, receipt)
        return path

    @contextlib.contextmanager
    def synthetic_reading_gate(self):
        original = review.validate_gate
        def read_then_validate(selection_path, receipt_paths=()):
            receipt = self.synthetic_reading_receipt(selection_path)
            if receipt not in receipt_paths:
                # The supervisor seals exactly this list after validation.
                # Mutating this injected test argument models receipt arrival.
                receipt_paths.append(receipt)
            return original(selection_path, receipt_paths)
        with patch.object(review, 'validate_gate', side_effect=read_then_validate):
            yield

    def execute(self, fetch=None, **kwargs):
        options = dict(fetcher=fetch or Mock(side_effect=fixtures.response), clock=self.clock.now,
            sleep=self.clock.sleep, disk_free=lambda path: 10**10, wait_for_review=False,
            probe=Mock(side_effect=AssertionError('Synthetic tests cannot probe the internet')))
        options.update(kwargs)
        with contextlib.redirect_stdout(io.StringIO()):
            return campaign.run(self.campaign_root, **options)

    def assert_originals_unchanged(self):
        for path, sha in self.source_hashes.items():
            self.assertEqual(w.sha_file(path), sha, path)

    def test_cross_child_history_counts_final_partial_and_native_review_preserved(self):
        self.build(10, 4, legacy_risk_rows=78); fetch = Mock(side_effect=fixtures.response)
        source_context = w.load(self.source / 'continuation_context.json')
        self.assertEqual(len(source_context['source_history']), 79)
        with self.synthetic_reading_gate():
            state = self.execute(fetch)
        self.assertEqual(state['status'], 'frozen_queue_processed_pending_coverage_review', state)
        self.assertEqual(fetch.call_count, 6)
        status = campaign.inspect(self.campaign_root, full=True)
        self.assertEqual((status['new_saved'], status['new_calls'], status['original_plan_saved'],
                          status['global_charged_calls'], status['remaining']), (6, 6, 10, 10, 0))
        previous = source_context
        for part in self.m['parts']:
            child = campaign.child_path(self.m, part['plan_index'])
            plan = w.load(child / 'continuous_plan.json')
            self.assertEqual(plan['seed_context'], previous)
            context = w.load(child / 'continuation_context.json')
            self.assertEqual(len(context['source_history']), 79)
            records = [w.load(p)['record'] for p in sorted((child / 'row_checks').glob('*.json'))]
            self.assertEqual(context['source_history'], (previous['source_history'] + records)[-79:])
            self.assertEqual(context['history_index']['path'], str(child / 'identity_index.json'))
            identity = w.load(child / 'identity_index.json')
            self.assertEqual(identity['parent'], previous['history_index'])
            for path in child.glob('batches/*/export_manifest.json'):
                native = w.load(path)
                self.assertFalse(native['manual_review']['annotation_file_present'])
                self.assertEqual(native['manual_review']['status_counts'].get('reviewed', 0), 0)
            previous = context
        self.assertEqual(len(w.load_history_index(previous['history_index'])), 10)
        self.assertEqual(w.load(campaign.child_path(self.m, 3) / 'checkpoint_00000002/summary.json')['rows'], 2)
        self.assert_originals_unchanged()

    def test_missing_ai_receipts_stop_before_next_child_then_resume_with_bound_receipts(self):
        self.build(); fetch = Mock(side_effect=fixtures.response)
        state = self.execute(fetch)
        self.assertEqual(state['status'], 'paused_safe', state); self.assertEqual(fetch.call_count, 4)
        self.assertFalse(campaign.child_path(self.m, 3).exists())
        self.assertFalse((self.campaign_root / 'technical_stop.json').exists())
        selections = list((self.campaign_root / 'reviews').rglob('selection*.json'))
        self.assertEqual(len(selections), 1)
        self.assertEqual(review.validate_gate(selections[0])['status'], 'blocked_pending_actual_ai_reading')
        self.execute(fetch); self.assertEqual(fetch.call_count, 4)
        with self.synthetic_reading_gate():
            state = self.execute(fetch, resume=True)
        self.assertEqual(state['status'], 'frozen_queue_processed_pending_coverage_review', state)
        self.assertEqual(fetch.call_count, 6); self.assert_originals_unchanged()

    def test_pause_request_during_fetch_finishes_one_and_resume_acknowledges_exact_token(self):
        self.build(); issued = []
        def fake(url, timeout, **kwargs):
            if not issued:
                issued.append(campaign.request_pause(self.campaign_root)['request_id'])
            return fixtures.response(url, timeout)
        fetch = Mock(side_effect=fake)
        state = self.execute(fetch)
        self.assertEqual(state['status'], 'paused_safe', state); self.assertEqual(fetch.call_count, 1)
        self.assertFalse((self.campaign_root / 'technical_stop.json').exists())
        status = campaign.inspect(self.campaign_root)
        self.assertEqual(status['pending_pause_requests'], issued)
        self.assertEqual(status['active']['pending_native_attempts'], 0)
        self.assertFalse(status['active']['open_transport'])
        pending = self.execute(fetch)
        self.assertEqual(pending['status'], 'pause_request_pending_use_explicit_resume')
        self.assertEqual(fetch.call_count, 1)
        with self.synthetic_reading_gate():
            state = self.execute(fetch, resume=True)
        self.assertEqual(state['status'], 'frozen_queue_processed_pending_coverage_review', state)
        self.assertEqual(fetch.call_count, 6)
        self.assertEqual(campaign.inspect(self.campaign_root)['pending_pause_requests'], [])
        self.assertTrue((self.campaign_root / 'control/pause_requests' / (issued[0] + '.json')).exists())
        self.assert_originals_unchanged()

    def test_technical_network_loss_preserves_halt_and_never_becomes_normal_resume(self):
        self.build(); fetch = Mock(side_effect=ConnectionError('synthetic link loss'))
        state = self.execute(fetch)
        self.assertEqual(state['status'], 'technical_stop_requires_investigation', state)
        self.assertEqual(fetch.call_count, 1)
        old = (self.campaign_root / 'technical_stop.json').read_bytes()
        issued = campaign.request_pause(self.campaign_root)
        self.assertEqual(issued['status'], 'pause_requested_not_yet_confirmed')
        self.assertEqual(self.execute(fetch, resume=True)['status'], 'technical_stop_requires_investigation')
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual((self.campaign_root / 'technical_stop.json').read_bytes(), old)
        self.assertFalse(campaign.child_path(self.m, 3).exists()); self.assert_originals_unchanged()

    def test_crash_after_child_receipt_before_master_event_adopts_without_refetch(self):
        self.build(); fetch = Mock(side_effect=fixtures.response); original = campaign.event
        def crash(root, kind, **details):
            if kind == 'child_complete':
                raise KeyboardInterrupt('synthetic process termination after child receipt')
            return original(root, kind, **details)
        with self.synthetic_reading_gate(), patch.object(campaign, 'event', side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):
                self.execute(fetch)
        self.assertEqual(fetch.call_count, 4)
        child = campaign.child_path(self.m, 2)
        receipt = child / 'remaining_completion_receipt.json'
        self.assertTrue(receipt.exists()); original_receipt = receipt.read_bytes()
        with self.synthetic_reading_gate():
            state = self.execute(fetch, resume=True)
        self.assertEqual(state['status'], 'frozen_queue_processed_pending_coverage_review', state)
        self.assertEqual(fetch.call_count, 6)
        self.assertEqual(receipt.read_bytes(), original_receipt)
        self.assertEqual(len([e for e in campaign.events(self.campaign_root) if e['kind'] == 'child_complete']), 2)

    def test_tampered_protected_binding_prevents_any_transport(self):
        self.build(); fetch = Mock(side_effect=fixtures.response)
        path = self.base / 'original_technical_halt_control.json'
        path.write_bytes(path.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'Bound evidence changed'):
            self.execute(fetch)
        fetch.assert_not_called(); self.assertFalse(campaign.child_path(self.m, 2).exists())

    def test_changed_or_missing_approved_ai_receipt_blocks_resume_before_transport(self):
        self.build(); fetch = Mock(side_effect=fixtures.response)
        original_event = campaign.event
        def pause_after_approved_gate(root, kind, **details):
            result = original_event(root, kind, **details)
            if kind == 'checkpoint_gate_satisfied':
                campaign.request_pause(root)
            return result
        with self.synthetic_reading_gate(), patch.object(campaign, 'event', side_effect=pause_after_approved_gate):
            state = self.execute(fetch)
        self.assertEqual(state['status'], 'paused_safe', state)
        self.assertEqual(fetch.call_count, 4)
        approved = [e for e in campaign.events(self.campaign_root) if e['kind'] == 'checkpoint_gate_satisfied']
        self.assertEqual(len(approved), 1)
        coverage = review._coverage(approved[0]['coverage']['path'])
        receipt = Path(coverage['receipt_bindings'][0]['path'])
        original = receipt.read_bytes()
        for action in ('change', 'delete'):
            with self.subTest(action=action):
                if action == 'change':
                    receipt.write_bytes(original + b' ')
                else:
                    receipt.unlink()
                next_fetch = Mock(side_effect=AssertionError('Invalid approved reading must block every new request'))
                with self.assertRaisesRegex(ValueError, '(?:Review evidence changed|Missing review evidence)'):
                    self.execute(next_fetch, resume=True)
                next_fetch.assert_not_called()
                self.assertFalse(campaign.child_path(self.m, 3).exists())
                receipt.write_bytes(original)
        self.assert_originals_unchanged()

    def test_signal_pause_failed_network_resume_still_requires_explicit_resume(self):
        self.build()
        controller = campaign.worker.StopController()
        def signal_during_fake_fetch(url, timeout, **kwargs):
            controller.request(signal.SIGINT)
            return fixtures.response(url, timeout)
        fetch = Mock(side_effect=signal_during_fake_fetch)
        with patch.object(campaign.worker, 'StopController', return_value=controller):
            state = self.execute(fetch)
        self.assertEqual(state['status'], 'paused_safe', state)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(campaign.pause_requests(self.campaign_root), {})
        self.assertTrue(campaign._outstanding_safe_pause(campaign.events(self.campaign_root)))

        # Exercise the production-shaped DNS/TLS branch entirely offline. The
        # bound fixture remains synthetic on disk; this local read view lets
        # the injected failing probe run. An independent worker guard makes
        # accidental article transport impossible even if that branch regresses.
        original_read_bound = campaign.read_bound
        def mocked_network_read_view(*args, **kwargs):
            manifest, events = original_read_bound(*args, **kwargs)
            return {**manifest, 'synthetic_fixture': False}, events
        probe = Mock(side_effect=ConnectionError('SYNTHETIC disconnected network'))
        with patch.object(campaign, 'read_bound', side_effect=mocked_network_read_view), \
             patch.object(campaign.worker, 'run', side_effect=AssertionError('No transport after failed offline probe')) as worker:
            failed = campaign.run(self.campaign_root, allow_network=True, resume=True, probe=probe,
                                  clock=self.clock.now, sleep=self.clock.sleep, disk_free=lambda path: 10**10)
        self.assertEqual(failed['status'], 'waiting_for_network_not_started')
        probe.assert_called_once(); worker.assert_not_called()
        events = campaign.events(self.campaign_root)
        self.assertTrue(campaign._outstanding_safe_pause(events))
        self.assertFalse(any(e['kind'] == 'resume_acknowledgment' for e in events))

        next_fetch = Mock(side_effect=fixtures.response)
        blocked = self.execute(next_fetch)
        self.assertEqual(blocked['status'], 'pause_request_pending_use_explicit_resume')
        next_fetch.assert_not_called()
        with self.synthetic_reading_gate():
            resumed = self.execute(next_fetch, resume=True)
        self.assertEqual(resumed['status'], 'frozen_queue_processed_pending_coverage_review', resumed)
        self.assertEqual(next_fetch.call_count, 5)
        self.assertFalse(campaign._outstanding_safe_pause(campaign.events(self.campaign_root)))
        self.assert_originals_unchanged()

    def test_storage_floor_and_forecast_pause_before_any_request_without_technical_halt(self):
        self.build(); fetch = Mock(side_effect=fixtures.response)
        state = self.execute(fetch, disk_free=lambda path: 0)
        self.assertEqual(state['status'], 'resource_pause_low_disk'); fetch.assert_not_called()
        state = self.execute(fetch, disk_free=lambda path: 100)
        self.assertEqual(state['status'], 'resource_pause_storage_forecast', state); fetch.assert_not_called()
        self.assertFalse((self.campaign_root / 'technical_stop.json').exists())
        self.assertFalse(campaign.child_path(self.m, 2).exists()); self.assert_originals_unchanged()

    def test_request_budget_includes_three_attempts_per_url_across_children(self):
        self.build(total=6, chunk=2); called = {}; urls = []
        def flaky(url, timeout, **kwargs):
            urls.append(url); called[url] = called.get(url, 0) + 1
            if called[url] < 3:
                return {**fixtures.response(url, timeout), 'status': 503, 'text': 'synthetic temporary outage'}
            return fixtures.response(url, timeout)
        fetch = Mock(side_effect=flaky)
        with self.synthetic_reading_gate():
            state = self.execute(fetch)
        self.assertEqual(state['status'], 'frozen_queue_processed_pending_coverage_review', state)
        self.assertEqual(fetch.call_count, 12); self.assertEqual(sorted(called.values()), [3] * 4)
        status = campaign.inspect(self.campaign_root)
        self.assertEqual(status['new_calls'], self.m['max_new_calls'])
        self.assertEqual(status['global_charged_calls'], 14)
        self.assert_originals_unchanged()

    def test_service_failure_risk_window_does_not_reset_between_children(self):
        self.build(total=6, chunk=2)
        fetch = Mock(side_effect=lambda url, timeout, **kwargs:
            {**fixtures.response(url, timeout), 'status': 503})
        with self.synthetic_reading_gate():
            state = self.execute(fetch)
        self.assertEqual(state['status'], 'technical_stop_requires_investigation', state)
        # Two terminal service failures close child2. The first URL of child3
        # must trigger the inherited consecutive-three guard, not reset it.
        self.assertEqual(fetch.call_count, 9)
        child = campaign.child_path(self.m, 3)
        self.assertEqual(w.load(child / 'safety_halt.json')['reason'],
                         'three_consecutive_terminal_service_failures')
        status = campaign.inspect(self.campaign_root)
        self.assertEqual(status['new_saved'], 3)
        self.assertEqual(status['remaining'], 1)
        self.execute(fetch, resume=True); self.assertEqual(fetch.call_count, 9)
        self.assert_originals_unchanged()

    def test_synthetic_fixture_never_uses_real_network_even_with_allow_flag(self):
        self.build(); probe = Mock(side_effect=AssertionError('must not probe'))
        with self.assertRaisesRegex(ValueError, 'Synthetic fixture cannot access news websites'):
            campaign.run(self.campaign_root, allow_network=True, probe=probe)
        probe.assert_not_called(); self.assertFalse(campaign.child_path(self.m, 2).exists())


if __name__ == '__main__':
    unittest.main()

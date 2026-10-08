"""Isolated recovery integration tests; generated responses and receipts only.

No production source, reading receipt, halt, or network is accessed. The donor
is a real native synthetic campaign, stopped after 391 retained rows and 392
charged calls, including one durably committed terminal connection failure.
"""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawler_core import tiempo_continuous_v5 as w
from crawler_core import tiempo_remaining_campaign as campaign
from crawler_core import tiempo_stage_review as review
import test_tiempo_remaining_campaign as campaign_fixtures
import test_tiempo_continuous_v5 as fixtures


class ConnectionRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.donor = donor = campaign_fixtures.RemainingCampaignTests('runTest')
        donor.setUp()
        cls.addClassCleanup(donor.doCleanups)
        # A completed predecessor and one completed campaign child give the
        # recovery adapter genuine continuation context and actual test seals.
        donor.build(total=1207, chunk=401)
        cls.donor_child = campaign.child_path(donor.m, 3)
        prepared_rows = w.readcsv(donor.m['parts'][1]['path'])
        cls.failed_id = prepared_rows[390]['sample_id']
        cls.failed_url = prepared_rows[390]['url']
        cls.next_id = prepared_rows[391]['sample_id']
        cls.next_url = prepared_rows[391]['url']
        failed_calls = []

        def response(url, timeout, **kwargs):
            if url == cls.failed_url:
                failed_calls.append(url)
                return {**fixtures.response(url, timeout), 'text': '', 'status': 0,
                        'curl_exit_code': 28 if len(failed_calls) == 1 else 7,
                        'error': ('operation timed out' if len(failed_calls) == 1 else
                                  'transport_error: curl_exit_7: Could not connect to server')}
            return fixtures.response(url, timeout)

        fetch = Mock(side_effect=response)
        with donor.synthetic_reading_gate():
            state = donor.execute(fetch)
        if state['status'] != 'technical_stop_requires_investigation':
            raise AssertionError(state)
        if len(failed_calls) != 2 or campaign.inspect(donor.campaign_root)['active']['saved'] != 391:
            raise AssertionError({'failed_calls': len(failed_calls), 'state': state,
                                  'counts': campaign.inspect(donor.campaign_root),
                                  'halt': w.load(donor.campaign_root / 'technical_stop.json')})
        cls.donor_hashes = {str(p): w.sha_file(p) for p in donor.campaign_root.rglob('*')
                            if p.is_file() and p.name != '.pilot.lock'}

    def setUp(self):
        from crawler_core import tiempo_connection_recovery
        self.adapter = tiempo_connection_recovery
        self.base = self.donor.base / self._testMethodName
        self.base.mkdir()
        self.campaign_root = self.base / 'recovered'
        self.clock = fixtures.Clock()
        self.clock.t = self.donor.clock.now() + 100
        self.config = self.base / 'synthetic_recovery.json'
        self.cfg = {'root': str(self.campaign_root),
                    'donor_root': str(self.donor.campaign_root),
                    'donor_code_root': str(Path(__file__).resolve().parents[3]),
                    'expected_child_index': 3, 'expected_saved': 391, 'expected_calls': 392,
                    'failed_sample_id': self.failed_id, 'next_sample_id': self.next_id,
                    'donor_campaign_sha256': w.sha_file(self.donor.campaign_root / 'campaign.json'),
                    'donor_master_halt_sha256': w.sha_file(self.donor.campaign_root / 'technical_stop.json'),
                    'donor_native_halt_sha256': w.sha_file(self.donor_child / 'safety_halt.json'),
                    'synthetic_fixture': True}
        w.write(self.base, self.config.name, self.cfg)

    def prepare(self):
        with contextlib.redirect_stdout(io.StringIO()):
            result = self.adapter.prepare(self.config)
        self.m, _ = campaign.read_bound(self.campaign_root, full=True)
        self.child = campaign.child_path(self.m, 3)
        return result

    def execute(self, fetch=None, **kwargs):
        options = dict(fetcher=fetch if fetch is not None else Mock(side_effect=fixtures.response),
                       clock=self.clock.now, sleep=self.clock.sleep, disk_free=lambda _: 10**10,
                       wait_for_review=False,
                       probe=Mock(side_effect=AssertionError('Synthetic tests never probe the internet')))
        options.update(kwargs)
        with contextlib.redirect_stdout(io.StringIO()):
            return campaign.run(self.campaign_root, **options)

    def synthetic_receipt(self, selection_path):
        """Explicit fixture evidence, never a claim that real news was read."""
        selection = w.load(selection_path)
        records = []
        for selected in selection['selected_records']:
            source = Path(selected['snapshot_path']).read_text()
            self.assertTrue('Report new-' in source or
                            (selected['sample_id'] == self.failed_id and source == ''))
            record = {key: selected[key] for key in
                      ('sample_id', 'snapshot_sha256', 'payload_sha256', 'row_check_sha256')}
            record.update(actual_ai_read=True, human_approval=False, technical_blockers=[],
                          research_status=None, scope=review.READ_SCOPE,
                          note='SYNTHETIC TEST ONLY: generated source or empty terminal failure '
                               'was inspected; this is no real article reading or human approval. '
                               'Fixture identity: ' + selected['sample_id'])
            records.append(record)
        path = Path(selection_path).parent / 'receipts/synthetic_fixture_reader.json'
        doc = {'schema': review.SCHEMA, 'selection_sha256': selection['selection_sha256'],
               'runtime_binding_sha256': w.digest(selection['snapshot']['bindings']),
               'actual_ai_read_ids': [r['sample_id'] for r in records],
               'actual_ai_read_count': len(records), 'human_approval': False,
               'technical_blockers': [], 'records': records}
        w.write(path.parent, path.name, doc)
        return path

    def selection(self, rows=400, index=3):
        return self.campaign_root / f'reviews/plan_{index:06d}' / f'checkpoint_{rows:08d}' / f'selection_{rows:08d}.json'

    def assert_donor_unchanged(self):
        for name, digest in self.donor_hashes.items():
            self.assertEqual(w.sha_file(name), digest, name)

    def test_imported_prefix_and_pending_check_survive_to_real_400_gate(self):
        self.prepare()
        before = campaign.inspect(self.campaign_root)
        self.assertEqual((before['active']['saved'], before['active']['calls']), (391, 392))
        original_rows = [r for b in w.load(self.child / 'continuous_plan.json')['batches']
                         for r in w._rows(self.child, b)]
        fetch = Mock(side_effect=fixtures.response)
        state = self.execute(fetch)
        self.assertEqual(state['status'], 'paused_safe', state)
        self.assertEqual(fetch.call_count, 9)
        self.assertEqual(fetch.call_args_list[0].args[0], self.next_url)
        self.assertNotIn(self.failed_url, [call.args[0] for call in fetch.call_args_list])
        selection = w.load(self.selection())
        self.assertEqual(selection['snapshot']['checkpoint_rows'], 400)
        self.assertEqual(len(selection['snapshot']['rows']), 400)
        self.assertEqual(selection['sampling_rule']['minimum_distinct_current_sources'], review.MIN_SAMPLES)
        self.assertIn(self.failed_id, selection['selected_ids'])
        check = w.load(self.child / 'row_checks' / (self.failed_id + '.json'))['record']
        self.assertEqual((check['collection_outcome'], check['manual_review_status']),
                         ('critical_failure', 'not_reviewed'))
        self.assertEqual(check['critical_flags'], ['critical_transport'])
        self.assertEqual(review.validate_gate(self.selection())['status'], 'blocked_pending_actual_ai_reading')
        self.assertTrue((self.child / 'automatic_checks/batch_000005').exists())
        rows = [r for b in w.load(self.child / 'continuous_plan.json')['batches'] for r in w._rows(self.child, b)]
        self.assertEqual(rows[:391], original_rows)
        self.execute(fetch, resume=True)
        self.assertEqual(fetch.call_count, 9)
        receipt = self.synthetic_receipt(self.selection())
        self.assertEqual(review.validate_gate(self.selection(), [receipt])['status'], 'collection_gate_satisfied')
        self.execute(fetch, resume=True)
        self.assertEqual(fetch.call_count, 10)  # Final 401-row child gate holds the next child.
        self.assertTrue(self.selection(401).exists())
        self.assertFalse(campaign.child_path(self.m, 4).exists())
        self.synthetic_receipt(self.selection(401))
        self.execute(fetch, resume=True)
        self.assertEqual(fetch.call_count, 14)
        next_child = campaign.child_path(self.m, 4)
        carried = w.load(next_child / 'continuous_plan.json')['seed_context']
        self.assertEqual(carried, w.load(self.child / 'continuation_context.json'))
        failed_context = next(row for row in carried['source_history'] if row['sample_id'] == self.failed_id)
        self.assertEqual(failed_context['collection_outcome'], 'critical_failure')
        self.assertEqual(failed_context['manual_review_status'], 'not_reviewed')
        inherited = carried['inherited_terminal_failures']
        self.assertEqual([row['sample_id'] for row in inherited], [self.failed_id])
        self.assertFalse(inherited[0]['retry_authorized'])
        self.assertFalse(inherited[0]['article_acceptance'])
        self.synthetic_receipt(self.selection(4, index=4))
        state = self.execute(fetch, resume=True)
        self.assertEqual(state['status'], 'frozen_queue_processed_pending_coverage_review', state)
        status = campaign.inspect(self.campaign_root)
        self.assertEqual((status['new_saved'], status['new_calls'], status['original_plan_saved'],
                          status['global_charged_calls'], status['remaining']), (405, 406, 1207, 1208, 0))
        self.assertEqual(fetch.call_count, 14)
        self.assertEqual(w.load(next_child / 'continuation_context.json')['inherited_terminal_failures'], inherited)
        self.execute(fetch, resume=True)
        self.assertEqual(fetch.call_count, 14)
        obligations = w.load(self.m['obligations']['path'])
        self.assertIn(self.failed_id, json.dumps(obligations))
        self.assertIn('SYNTHETIC_OLD_PENDING', json.dumps(obligations))
        self.assert_donor_unchanged()

    def test_low_disk_before_resume_starts_no_transport(self):
        self.prepare()
        fetch = Mock(side_effect=fixtures.response)
        state = self.execute(fetch, disk_free=lambda _: 0)
        self.assertIn(state['status'], {'resource_pause_low_disk', 'resource_pause_storage_forecast'})
        fetch.assert_not_called()
        self.assertEqual(campaign.inspect(self.campaign_root)['active']['saved'], 391)
        self.assert_donor_unchanged()

    def test_a_new_critical_failure_still_halts_and_cannot_resume(self):
        self.prepare()
        fetch = Mock(side_effect=ConnectionError('synthetic NEW connection failure'))
        state = self.execute(fetch)
        self.assertEqual(state['status'], 'technical_stop_requires_investigation')
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(campaign.inspect(self.campaign_root)['active']['saved'], 392)
        halt = (self.campaign_root / 'technical_stop.json').read_bytes()
        self.assertEqual(self.execute(fetch, resume=True)['status'], 'technical_stop_requires_investigation')
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual((self.campaign_root / 'technical_stop.json').read_bytes(), halt)
        self.assert_donor_unchanged()

    def test_mismatched_expected_next_identity_is_rejected_offline(self):
        self.cfg['next_sample_id'] = self.failed_id
        w.write(self.base, self.config.name, self.cfg)
        with self.assertRaises(ValueError):
            self.adapter.prepare(self.config)
        self.assert_donor_unchanged()

    def test_changed_acknowledgment_is_rejected_before_any_transport(self):
        self.prepare()
        binding = self.m['connection_recovery']['acknowledgment']
        path = Path(binding['path'])
        path.write_bytes(path.read_bytes() + b'\n')
        fetch = Mock(side_effect=fixtures.response)
        with self.assertRaises(ValueError):
            self.execute(fetch, resume=True)
        fetch.assert_not_called()
        self.assert_donor_unchanged()

    def test_retained_failed_source_cannot_be_omitted_from_reading_receipt(self):
        self.prepare()
        fetch = Mock(side_effect=fixtures.response)
        self.execute(fetch)
        path = self.synthetic_receipt(self.selection())
        receipt = w.load(path)
        receipt['records'] = [r for r in receipt['records'] if r['sample_id'] != self.failed_id]
        receipt['actual_ai_read_ids'] = [r['sample_id'] for r in receipt['records']]
        receipt['actual_ai_read_count'] = len(receipt['records'])
        w.write(path.parent, path.name, receipt)
        gate = review.validate_gate(self.selection(), [path])
        self.assertEqual(gate['status'], 'blocked_pending_actual_ai_reading', gate)
        self.assertEqual(gate['missing_ids'], [self.failed_id])
        self.execute(fetch, resume=True)
        self.assertEqual(fetch.call_count, 9)
        self.assert_donor_unchanged()

    def test_saved_response_after_interruption_is_adopted_without_another_fetch(self):
        self.prepare()
        fetch = Mock(side_effect=fixtures.response)
        # SystemExit models process termination, not a graceful worker pause.
        # The durable terminal transport exists before the native save begins.
        with patch.object(w.pilot, 'save_snapshot', side_effect=SystemExit('synthetic process termination')):
            with self.assertRaises(SystemExit):
                self.execute(fetch)
        self.assertEqual(fetch.call_count, 1)
        self.assertFalse((self.campaign_root / 'technical_stop.json').exists())
        state = self.execute(fetch, resume=True)
        self.assertEqual(state['status'], 'paused_safe', {
            'state': state, 'calls': fetch.call_count,
            'native_halt': w.load(self.child / 'safety_halt.json')
                           if (self.child / 'safety_halt.json').exists() else None})
        self.assertEqual(fetch.call_count, 9)
        self.assertEqual(sum(call.args[0] == self.next_url for call in fetch.call_args_list), 1)
        self.assertEqual(campaign.inspect(self.campaign_root)['active']['saved'], 400)
        self.assert_donor_unchanged()

    def test_changed_selected_source_invalidates_gate_without_new_fetch(self):
        self.prepare()
        fetch = Mock(side_effect=fixtures.response)
        self.execute(fetch)
        receipt = self.synthetic_receipt(self.selection())
        selected = next(r for r in w.load(self.selection())['selected_records']
                        if r['sample_id'] != self.failed_id)
        raw = Path(selected['snapshot_path'])
        raw.write_bytes(raw.read_bytes() + b'changed synthetic evidence')
        gate = review.validate_gate(self.selection(), [receipt])
        self.assertTrue(gate['integrity_error'])
        self.assertEqual(gate['status'], 'blocked_invalid_evidence')
        state = self.execute(fetch, resume=True)
        self.assertEqual(state['status'], 'technical_stop_requires_investigation', state)
        self.assertEqual(fetch.call_count, 9)
        self.assert_donor_unchanged()

    def test_no_acknowledgment_means_retained_critical_is_still_a_gate_blocker(self):
        self.prepare()
        self.execute(Mock(side_effect=fixtures.response))
        selection = review.select_checkpoint(self.child, self.base / 'no_acknowledgment',
            checkpoint_rows=400, inherited_obligations=self.m['obligations']['path'])
        receipt = self.synthetic_receipt(selection['selection_path'])
        gate = review.validate_gate(selection['selection_path'], [receipt])
        self.assertEqual(gate['status'], 'blocked_technical_review')
        self.assertIn('native_critical_source_flags:' + self.failed_id, gate['technical_blockers'])
        self.assert_donor_unchanged()

    def test_interrupted_preparation_never_permits_transport(self):
        from crawler_core import tiempo_resumable_worker as worker
        original = worker.close_saved_boundary
        for phase in ('before_closure', 'after_closure'):
            with self.subTest(phase=phase):
                self.campaign_root = self.base / phase
                config = self.base / (phase + '.json')
                w.write(self.base, config.name, {**self.cfg, 'root': str(self.campaign_root)})
                def interrupted(*args, **kwargs):
                    if phase == 'after_closure':
                        original(*args, **kwargs)
                    raise SystemExit('synthetic interruption during preparation')
                with patch.object(worker, 'close_saved_boundary', side_effect=interrupted):
                    with self.assertRaises(SystemExit):
                        self.adapter.prepare(config)
                self.assertTrue(w.load(self.campaign_root / 'campaign.json')['connection_recovery_pending'])
                fetch = Mock(side_effect=fixtures.response)
                with self.assertRaisesRegex(ValueError, 'Recovery preparation incomplete'):
                    self.execute(fetch, resume=True)
                fetch.assert_not_called()
        self.assert_donor_unchanged()


if __name__ == '__main__':
    unittest.main()

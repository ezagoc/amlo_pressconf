"""Synthetic, offline native-storage tests for one retained terminal failure."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import unittest
from unittest.mock import Mock, patch

import test_tiempo_resumable_worker as base
response, worker, w = base.response, base.worker, base.w


class InheritedFailureWorkerTests(unittest.TestCase):
    setUp = base.ResumableWorkerTests.setUp
    freeze = base.ResumableWorkerTests.freeze
    current = base.ResumableWorkerTests.current
    execute = base.ResumableWorkerTests.execute
    counts = base.ResumableWorkerTests.counts

    def prepare(self):
        self.freeze(4)
        url = self.rows[1]['url']
        failure = lambda code, error: {'status': 0, 'text': '', 'content_type': None,
                                      'final_url': url, 'error': error, 'curl_exit_code': code}
        fetch = Mock(side_effect=[response(self.rows[0]['url'], 45),
                                 failure(28, 'curl_exit_28: Connection timed out'),
                                 failure(7, 'curl_exit_7: Could not connect to server')])
        stopped = self.execute(fetch)
        self.assertEqual(stopped['status'], 'halted_no_automatic_resume')
        self.assertEqual(fetch.call_count, 3)
        self.donor = self.root.resolve(); self.donor_media = self.media.resolve()
        self.plan = w.load(self.donor / 'continuous_plan.json')
        w.write(self.donor_media, 'technical_stop.json', {
            'reason': 'native_worker_stopped', 'native_result': stopped})
        native = worker.inherited_prefix_evidence(self.donor, self.plan, 2)
        failed = native['rows'][-1]; row = failed['row']
        halt_sha = w.sha_file(self.donor / 'safety_halt.json')
        paths = [self.donor / n for n in ('continuous_plan.json', 'continuous_state.json',
                 'safety_halt.json', 'transport_calls.jsonl', 'transport_state.json')]
        paths += [self.donor / 'halt_receipts' / (halt_sha + '.json'),
                  self.donor / 'row_checks' / (row['sample_id'] + '.json'),
                  self.donor_media / 'technical_stop.json']
        paths += list(self.donor.glob('batches/*/pilot.sqlite'))
        self.media = (self.base / 'SuccessorMedia').resolve()
        self.root = self.media / self.donor.relative_to(self.donor_media)
        # A fresh namespace selectively imports durable native evidence. The
        # immutable donor's halts are retained where they were originally made.
        shutil.copytree(self.donor, self.root, ignore=shutil.ignore_patterns(
            'safety_halt.json', 'halt_receipts', 'continuous_state.json', '.pilot.lock'))
        self.ack = {
            'schema': worker.INHERITED_FAILURE_SCHEMA, 'target_root': str(self.root),
            'donor_root': str(self.donor), 'donor_campaign_root': str(self.donor_media),
            'synthetic_fixture': True, 'prefix_rows': 2, 'prefix_calls': 3,
            'prefix_payload_sha256': native['prefix_payload_sha256'],
            'prefix_attempts_sha256': native['prefix_attempts_sha256'],
            'prefix_articles_sha256': native['prefix_articles_sha256'],
            'donor_bindings': {str(p): w.sha_file(p) for p in paths},
            'failure': {'batch_id': failed['batch_id'],
                        **{k: row[k] for k in ('sample_id', 'url', 'attempt_id', 'snapshot_sha256')},
                        'payload_sha256': hashlib.sha256(native['payloads'][-1].encode()).hexdigest(),
                        'row_check_record_sha256': w.digest(w.load(self.donor / 'row_checks' /
                                                                 (row['sample_id'] + '.json'))['record'])}}
        self.ack_path = self.base / 'acknowledgment.json'
        self.bind_ack()
        self.original = native
        self.donor_bytes = {str(p): w.sha_file(p) for p in self.donor.rglob('*') if p.is_file()}
        return self.binding

    def bind_ack(self):
        w.write(self.ack_path.parent, self.ack_path.name, self.ack)
        self.binding = {'path': str(self.ack_path), 'sha256': w.sha_file(self.ack_path)}

    def assert_donor_unchanged(self):
        self.assertEqual(self.donor_bytes,
                         {str(p): w.sha_file(p) for p in self.donor.rglob('*') if p.is_file()})

    def test_exact_inherited_failure_continues_without_retry_and_retains_context(self):
        self.prepare(); fetch = Mock(side_effect=response)
        result = self.execute(fetch, inherited_failure_acknowledgment=self.binding)
        self.assertTrue(result.get('collection_inputs_finished'), result)
        self.assertEqual([c.args[0] for c in fetch.call_args_list], [r['url'] for r in self.rows[2:]])
        after = worker.inherited_prefix_evidence(self.root, self.plan, 2)
        self.assertEqual(after['prefix_payload_sha256'], self.original['prefix_payload_sha256'])
        self.assertEqual(after['prefix_attempts_sha256'], self.original['prefix_attempts_sha256'])
        self.assertEqual(after['prefix_articles_sha256'], self.original['prefix_articles_sha256'])
        context = w.load(self.root / 'continuation_context.json')
        self.assertEqual(context['inherited_terminal_failures'][0]['sample_id'], self.rows[1]['sample_id'])
        self.assertEqual(context['inherited_terminal_failures'][0]['collection_outcome'], 'critical_failure')
        self.assertEqual(context['inherited_terminal_failures'][0]['resolution_status'], 'unresolved_transport_failure')
        self.assertFalse(context['inherited_terminal_failures'][0]['retry_authorized'])
        self.assertNotIn('research_status', context['inherited_terminal_failures'][0])
        self.assertEqual(context['source_history'][1]['critical_flags'], ['critical_transport'])
        self.assertEqual(context['source_history'][1]['manual_review_status'], 'not_reviewed')
        index = w.load(self.root / 'identity_index.json')
        self.assertIn(self.rows[1]['sample_id'], [r['sample_id'] for r in index['records']])
        self.assert_donor_unchanged()
        self.execute(fetch, inherited_failure_acknowledgment=self.binding)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(w.load(self.root / 'continuation_context.json')['inherited_terminal_failures'],
                         context['inherited_terminal_failures'])

    def test_unresolved_failure_survives_next_child_without_new_acknowledgment(self):
        self.prepare()
        self.execute(inherited_failure_acknowledgment=self.binding)
        context = w.load(self.root / 'continuation_context.json')
        rows = [{**base.fixtures.candidate(10), 'candidate_id': '10',
                 'sample_id': 'TC5_TEST_000010', 'baseline_classes_json': '[]'}]
        source = self.base / 'next.csv'; base.fixtures.writecsv(source, rows)
        queue = self.base / 'next_queue.sqlite'
        with sqlite3.connect(queue) as db:
            columns = [k for k in rows[0] if k not in {'sample_id', 'selection_reason', 'expected_year', 'expected_kind'}]
            db.execute('CREATE TABLE candidates (' + ', '.join(k + ' TEXT' for k in columns) + ')')
            db.execute('INSERT INTO candidates VALUES (' + ','.join('?' for _ in columns) + ')',
                       [rows[0][k] for k in columns])
        self.root = self.root.parent / 'next_child'
        w.freeze(source, self.root, self.media, self.registry_path, w.sha_file(self.registry_path),
                 self.exclusions, start='2024-06-01', end='2024-06-02', max_fetch_calls=3,
                 queue_db_path=queue, queue_db_sha256=w.sha_file(queue), min_free_bytes=1,
                 seed_context=context)
        fetch = Mock(side_effect=response); result = self.execute(fetch)
        self.assertTrue(result['collection_inputs_finished']); self.assertEqual(fetch.call_count, 1)
        after = w.load(self.root / 'continuation_context.json')
        self.assertEqual(after['inherited_terminal_failures'], context['inherited_terminal_failures'])
        self.assertEqual(len(after['inherited_terminal_failures']), 1)
        self.assert_donor_unchanged()

    def interrupt_after_certified_prefix(self, *, old_exports=False):
        self.prepare()
        self.execute(inherited_failure_acknowledgment=self.binding, stop_requested=lambda: True)
        fetch = Mock(side_effect=response)
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(w.pilot, 'save_snapshot', side_effect=SystemExit('power loss')))
            if old_exports:
                stack.enter_context(patch.object(w.pilot, 'export_outputs', side_effect=SystemExit('export interrupted')))
            with self.assertRaises(SystemExit):
                self.execute(fetch, inherited_failure_acknowledgment=self.binding)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(self.counts(), {'articles': 2, 'attempts': 3, 'pending': 1})
        return fetch

    def test_certified_prefix_pending_terminal_response_recovers_without_refetch(self):
        for old_exports in (False, True):
            with self.subTest(old_exports=old_exports):
                self.setUp(); fetch = self.interrupt_after_certified_prefix(old_exports=old_exports)
                result = self.execute(fetch, inherited_failure_acknowledgment=self.binding,
                                      stop_at_saved_rows=3)
                self.assertTrue(result.get('checkpoint_boundary_reached'), result)
                self.assertEqual(fetch.call_count, 1)
                self.assertEqual(self.counts(), {'articles': 3, 'attempts': 3, 'pending': 0})
                after = worker.inherited_prefix_evidence(self.root, self.plan, 2)
                for key in ('prefix_payload_sha256', 'prefix_attempts_sha256', 'prefix_articles_sha256'):
                    self.assertEqual(after[key], self.original[key])
                self.assert_donor_unchanged()

    def test_pending_terminal_response_does_not_permit_export_or_manifest_tamper(self):
        for what in ('native_export', 'review_state', 'pending_accounting'):
            with self.subTest(what=what):
                self.setUp(); fetch = self.interrupt_after_certified_prefix()
                batch = self.root / 'batches/batch_000001'
                path = batch / ('attempts.csv' if what == 'native_export' else 'export_manifest.json')
                if what == 'native_export':
                    path.write_bytes(b'corrupted pending attempts export')
                else:
                    manifest = w.load(path)
                    if what == 'review_state':
                        manifest['manual_review']['status_counts']['reviewed'] = 1
                    else:
                        # Keep the old arithmetic internally balanced; it still
                        # differs from both proved native generations.
                        for key in ('incomplete_attempts', 'attempt_rows', 'network_fetch_calls_started'):
                            manifest[key] += 1
                    w.write(path.parent, path.name, manifest)
                before = path.read_bytes()
                result = self.execute(fetch, inherited_failure_acknowledgment=self.binding)
                self.assertEqual(result['status'], 'halted_no_automatic_resume')
                self.assertEqual(fetch.call_count, 1)
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(self.counts(), {'articles': 2, 'attempts': 3, 'pending': 1})
                self.assert_donor_unchanged()

    def test_prior_manifest_accounting_cannot_change_after_later_commit(self):
        for advance in (False, True):
            for what in ('collision_count', 'pending_count', 'balanced_alias_count'):
                with self.subTest(advance=advance, what=what):
                    self.setUp(); self.freeze(3); fetch = Mock(side_effect=response)
                    self.execute(fetch, stop_at_saved_rows=1)
                    batch = self.root / 'batches/batch_000001'
                    if advance:
                        with patch.object(w.pilot, 'export_outputs', side_effect=RuntimeError('export crash')):
                            with self.assertRaises(RuntimeError):
                                self.execute(fetch, stop_at_saved_rows=2)
                    path = batch / 'export_manifest.json'; manifest = w.load(path)
                    if what == 'collision_count':
                        manifest['canonical_collision_groups'] = 1
                    elif what == 'balanced_alias_count':
                        manifest['article_rows'] -= 1
                        manifest['canonical_alias_rows'] += 1
                    else:
                        for key in ('incomplete_attempts', 'attempt_rows', 'network_fetch_calls_started'):
                            manifest[key] += 1
                    w.write(path.parent, path.name, manifest)
                    before = path.read_bytes(); calls_before = fetch.call_count
                    result = self.execute(fetch, stop_at_saved_rows=2)
                    self.assertEqual(result['status'], 'halted_no_automatic_resume')
                    self.assertEqual(fetch.call_count, calls_before)
                    self.assertEqual(path.read_bytes(), before)

    def test_acknowledgment_is_not_inferred_when_omitted(self):
        self.prepare(); fetch = Mock(side_effect=response)
        state = self.execute(fetch)
        self.assertEqual(state['status'], 'halted_no_automatic_resume')
        fetch.assert_not_called(); self.assert_donor_unchanged()

    def test_new_connection_failure_still_halts_and_cannot_be_acknowledged(self):
        self.prepare(); fetch = Mock(side_effect=ConnectionError('new connection failure'))
        result = self.execute(fetch, inherited_failure_acknowledgment=self.binding)
        self.assertEqual(result['status'], 'halted_no_automatic_resume')
        self.assertEqual(fetch.call_count, 1)
        halt = w.load(self.root / 'safety_halt.json')
        self.assertEqual(halt['sample_id'], self.rows[2]['sample_id'])
        self.execute(fetch, inherited_failure_acknowledgment=self.binding)
        self.assertEqual(fetch.call_count, 1); self.assert_donor_unchanged()

    def test_pause_after_import_then_resume_only_unsaved_urls(self):
        self.prepare(); fetch = Mock(side_effect=response)
        paused = self.execute(fetch, inherited_failure_acknowledgment=self.binding,
                              stop_requested=lambda: True)
        self.assertEqual(paused['status'], worker.PAUSED, paused)
        self.assertEqual(paused['result_rows'], 2); fetch.assert_not_called()
        result = self.execute(fetch, inherited_failure_acknowledgment=self.binding)
        self.assertTrue(result['collection_inputs_finished']); self.assertEqual(fetch.call_count, 2)
        self.assert_donor_unchanged()

    def test_modified_prefix_payload_or_attempt_blocks_before_fetch(self):
        for what in ('payload', 'attempt', 'title_column', 'status_column'):
            with self.subTest(what=what):
                self.setUp(); self.prepare()
                dbpath = self.root / 'batches/batch_000001/pilot.sqlite'
                with sqlite3.connect(dbpath) as db:
                    if what == 'payload':
                        db.execute("UPDATE articles SET payload_json=replace(payload_json, 'News', 'Changed') WHERE ordinal=0")
                        # Ensure a deterministic change independent of fixture prose.
                        db.execute("UPDATE articles SET payload_json=payload_json || ' ' WHERE ordinal=0")
                    elif what == 'attempt':
                        db.execute("UPDATE fetch_attempts SET started_at='changed' WHERE sample_id=?", (self.rows[0]['sample_id'],))
                    elif what == 'title_column':
                        db.execute("UPDATE articles SET title='altered SQL column only' WHERE ordinal=0")
                    else:
                        db.execute("UPDATE articles SET status=403 WHERE ordinal=0")
                fetch = Mock(); result = self.execute(fetch, inherited_failure_acknowledgment=self.binding)
                self.assertEqual(result['status'], 'halted_no_automatic_resume'); fetch.assert_not_called()
                self.assertEqual(w.load(self.root / 'safety_halt.json')['reason'], 'inherited_failure_acknowledgment_invalid')

    def test_changed_donor_halt_ack_binding_or_imported_ledger_blocks(self):
        for what in ('donor_halt', 'ack', 'ledger', 'raw', 'check'):
            with self.subTest(what=what):
                self.setUp(); self.prepare()
                if what == 'donor_halt': p = self.donor / 'safety_halt.json'
                elif what == 'ack': p = self.ack_path
                elif what == 'ledger': p = self.root / 'transport_calls.jsonl'
                elif what == 'raw': p = self.root / 'batches/batch_000001' / self.original['rows'][-1]['row']['snapshot_path']
                else: p = self.root / 'row_checks' / (self.rows[1]['sample_id'] + '.json')
                p.write_bytes(p.read_bytes() + b' ')
                if what == 'check':
                    d = w.load(p); d['record']['manual_review_status'] = 'reviewed'; w.write(p.parent, p.name, d)
                fetch = Mock(); result = self.execute(fetch, inherited_failure_acknowledgment=self.binding)
                self.assertEqual(result['status'], 'halted_no_automatic_resume'); fetch.assert_not_called()

    def test_synthetic_ack_cannot_enable_live_transport(self):
        self.prepare()
        with patch('crawler_core.capabilities.fetch') as fetch, contextlib.redirect_stdout(io.StringIO()):
            result = worker.run(self.root, self.media, max_batches=25, allow_network=True,
                                install_signal_handlers=False, inherited_failure_acknowledgment=self.binding)
        self.assertEqual(result['status'], 'halted_no_automatic_resume'); fetch.assert_not_called()

    def test_production_ack_rejects_any_other_episode(self):
        self.prepare(); self.ack['synthetic_fixture'] = False; self.bind_ack(); fetch = Mock()
        result = self.execute(fetch, inherited_failure_acknowledgment=self.binding)
        self.assertEqual(result['status'], 'halted_no_automatic_resume'); fetch.assert_not_called()


if __name__ == '__main__':
    unittest.main()

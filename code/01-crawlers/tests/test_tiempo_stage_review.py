"""Focused review boundaries and fail-closed evidence; no network or AI calls."""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawler_core import tiempo_continuous_v5 as w, tiempo_stage_review as review


class StageReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.obligations = self.base / 'Inherited_Review_Obligations.json'
        w.write(self.base, self.obligations.name, {
            'rule': 'All original pending obligations remain unresolved.',
            'source_checkpoint_pending_samples': [{'sample_id': 'OLD_1', 'manual_review_status': 'not_reviewed'}],
            'source_capsule_documents': [{'document': {'original_frozen_batch_selections': [{'sample_id': 'OLD_2'}]}}]})

    def child(self, name='child', total=800, saved=400, first_id=1, special=None):
        child = self.base / name
        child.mkdir()
        queue, batches, rows, summaries = [], [], [], []
        for i in range(total):
            sid = f'TC5_{first_id + i}'
            origin = {'sample_id': sid, 'url': f'https://tiempo.com.mx/noticia/{sid}',
                      'queue_class': 'new_urls', 'identity_class': 'new_urls', 'route': 'noticia',
                      'discovery_day': '2025-02-09', 'baseline_classes_json': '[]',
                      'baseline_record_ids_json': '[]', 'source_quality_issues_json': '[]'}
            row = {'sample_id': sid, 'url': origin['url'], 'canonical_url': f'https://tiempo.com.mx/local/{sid}',
                   'title': 'Synthetic title', 'main_text': 'Synthetic complete body. ' * 40,
                   'date_published': '2025-02-09T09:00:00', 'section': 'Local', 'article_kind': 'article',
                   'snapshot_path': f'raw_html/{sid}.html', 'media_embeds': []}
            check = {'route': 'local', 'automatic_flags': [], 'critical_flags': [], 'unexplained_flags': [],
                     'observed_types': [], 'source_judgment_flags': [], 'source_markup_warnings': []}
            if special:
                special(i, row, check, origin)
            queue.append(origin)
            rows.append((row, check))
        w.pilot.atomic_bytes(child / 'queue.csv', w.csvbytes(list(queue[0]), queue))
        for start in range(0, total, 80):
            ids = [r['sample_id'] for r in queue[start:start + 80]]
            batches.append({'batch_id': f'batch_{start // 80 + 1:06d}', 'row_count': len(ids), 'sample_ids': ids})
        plan = {'row_count': total, 'batches': batches, 'queue_sha256': w.sha_file(child / 'queue.csv'),
                'program_sha256': w.program_hashes()}
        plan['plan_sha256'] = w.digest(plan)
        w.write(child, 'continuous_plan.json', plan)
        offset = 0
        for batch in batches:
            end = offset + batch['row_count']
            if end > saved:
                break
            B = child / 'batches' / batch['batch_id']
            B.mkdir(parents=True)
            with sqlite3.connect(B / 'pilot.sqlite') as db:
                db.execute('CREATE TABLE articles (ordinal INTEGER, payload_json TEXT)')
                for ordinal, (row, check) in enumerate(rows[offset:end]):
                    raw = ('<html>Synthetic source ' + row['sample_id'] + '</html>').encode()
                    w.pilot.atomic_bytes(B / row['snapshot_path'], raw)
                    row['snapshot_sha256'] = review._sha(raw)
                    db.execute('INSERT INTO articles VALUES (?,?)', (ordinal, json.dumps(row, sort_keys=True)))
                    check.update(sample_id=row['sample_id'], snapshot_sha256=row['snapshot_sha256'],
                                 fields_sha256=w.fields_digest(row))
                    w.write(child, 'row_checks/' + row['sample_id'] + '.json',
                            {'plan_sha256': plan['plan_sha256'], 'record': check})
            check_path = child / 'automatic_checks' / batch['batch_id'] / 'check.json'
            w.write(check_path.parent, check_path.name, {'synthetic': True, 'batch_id': batch['batch_id']})
            summaries.append({'batch_id': batch['batch_id'], 'rows': batch['row_count'], 'batch_input_complete': True,
                              'check_path': str(check_path), 'check_sha256': w.sha_file(check_path)})
            offset = end
        if offset != saved:
            raise AssertionError('Fixture must have a closed batch boundary')
        folder = child / f'checkpoint_{saved:08d}'
        folder.mkdir()
        pending = [{'sample_id': r['sample_id'], 'manual_review_status': 'not_reviewed'} for r in queue[:saved]]
        w.pilot.atomic_bytes(folder / 'pending_source_review_samples.csv', w.csvbytes(list(pending[0]), pending))
        w.write(folder, 'summary.json', {'rows': saved, 'plan_sha256': plan['plan_sha256'],
            'actual_manual_reviews': 0, 'pending_source_review_sample_count': saved,
            'pending_samples_sha256': w.sha_file(folder / 'pending_source_review_samples.csv'), 'batch_checks': summaries})
        return child

    def select(self, child, output='review', checkpoint=400, **kwargs):
        return review.select_checkpoint(child, self.base / output, checkpoint_rows=checkpoint,
                                        inherited_obligations=self.obligations, **kwargs)

    def receipt(self, selection, name='reading.json', rows=None):
        selected = selection['selected_records'] if rows is None else rows
        records = [{key: r[key] for key in ('sample_id', 'snapshot_sha256', 'payload_sha256', 'row_check_sha256')}
                   for r in selected]
        for r in records:
            r.update(actual_ai_read=True, human_approval=False, technical_blockers=[], research_status=None,
                     scope=review.READ_SCOPE,
                     note='Synthetic test only: reading attestation fixture, never evidence about a real source.')
        doc = {'schema': review.SCHEMA, 'selection_sha256': selection['selection_sha256'],
               'runtime_binding_sha256': w.digest(selection['snapshot']['bindings']),
               'actual_ai_read_ids': [r['sample_id'] for r in records], 'actual_ai_read_count': len(records),
               'human_approval': False, 'technical_blockers': [], 'records': records}
        path = self.base / name
        w.write(self.base, name, doc)
        return path

    def test_withheld_and_partial_receipts_block_before_next_network(self):
        child = self.child()
        selection = self.select(child)
        self.assertEqual(len(selection['selected_ids']), 4)
        fetch = Mock()
        with self.assertRaisesRegex(ValueError, 'gate blocked'):
            review.require_gate(selection['selection_path'])
            fetch()
        fetch.assert_not_called()
        partial = self.receipt(selection, rows=selection['selected_records'][:1])
        result = review.validate_gate(selection['selection_path'], [partial])
        self.assertEqual(len(result['missing_ids']), 3)
        self.assertEqual(result['status'], 'blocked_pending_actual_ai_reading')
        self.assertTrue(result['awaiting_ai_readings'])
        self.assertFalse(result['integrity_error'])
        full = self.receipt(selection, name='full.json')
        self.assertEqual(review.require_gate(selection['selection_path'], [full])['new_actual_ai_read_count'], 4)

    def test_changed_raw_queue_and_native_db_invalidate_receipt(self):
        child = self.child()
        selection = self.select(child)
        receipt = self.receipt(selection)
        for path in (Path(selection['selected_records'][0]['snapshot_path']), child / 'queue.csv',
                     child / 'batches/batch_000001/pilot.sqlite'):
            original = path.read_bytes()
            path.write_bytes(original + b'changed')
            self.assertEqual(review.validate_gate(selection['selection_path'], [receipt])['status'], 'blocked_invalid_evidence')
            self.assertTrue(review.validate_gate(selection['selection_path'], [receipt])['integrity_error'])
            path.write_bytes(original)
        self.assertEqual(review.require_gate(selection['selection_path'], [receipt])['status'], 'collection_gate_satisfied')

    def test_reused_coverage_is_stable_and_same_ids_not_recounted(self):
        child = self.child()
        first = self.select(child)
        receipt = self.receipt(first)
        item = {'receipt': str(receipt), 'selection': first['selection_path']}
        second = self.select(child, 'review2', history_receipts=[item, item])
        self.assertEqual(first['selected_ids'], second['selected_ids'])
        self.assertEqual(len(second['history']['distinct_actual_ai_read_ids']), 4)
        result = review.require_gate(second['selection_path'])
        self.assertEqual(result['new_actual_ai_read_count'], 0)
        self.assertEqual(len(result['reused_actual_ai_read_ids']), 4)
        self.assertEqual(second, self.select(child, 'review2', history_receipts=[item, item]))
        original = receipt.read_bytes()
        receipt.write_bytes(original + b' ')
        self.assertEqual(review.validate_gate(second['selection_path'])['status'], 'blocked_invalid_evidence')

    def test_400_boundary_and_final_partial(self):
        child = self.child()
        for number in (399, 401):
            with self.assertRaisesRegex(ValueError, '400-row boundary'):
                self.select(child, checkpoint=number)
        final = self.child('final', total=531, saved=531)
        selection = self.select(final, 'finalreview', checkpoint=531)
        self.assertEqual(selection['snapshot']['previous_checkpoint_rows'], 400)
        self.assertEqual(len(selection['snapshot']['rows']), 131)
        self.assertEqual(len(selection['selected_ids']), 4)
        tiny = self.child('tiny', total=3, saved=3)
        self.assertEqual(len(self.select(tiny, 'tinyreview', checkpoint=3)['selected_ids']), 3)

    def test_individual_new_strata_and_queue_origin_supplement_history(self):
        original = self.child()
        first = self.select(original)
        receipt = self.receipt(first)
        def special(i, row, check, origin):
            if i == 0:
                row.update(date_published='2024-12-31T12:00:00', section='Deportes', title=None,
                           article_kind='article_with_video', main_text='Short actual synthetic body.',
                           media_embeds=['https://www.youtube.com/embed/example'])
                origin.update(discovery_day='2025-01-01', queue_class='old_error_review', identity_class='old_error_review',
                              baseline_classes_json='["old_error"]')
                check.update(route='deportes')
        child = self.child('new', first_id=1001, special=special)
        selection = self.select(child, 'newreview', history_receipts=[{'receipt': str(receipt), 'selection': first['selection_path']}])
        self.assertIn('TC5_1001', selection['selected_ids'])
        selected = next(r for r in selection['selected_records'] if r['sample_id'] == 'TC5_1001')
        for token in ('publication_year:2024', 'publication_month:2024-12', 'discovery_month:2025-01',
                      'queue_class:old_error_review', 'corpus_origin:old_error', 'route:deportes', 'title:missing'):
            self.assertIn(token, selected['strata'])
        self.assertEqual(len(selection['selected_ids']), 4)
        self.assertNotIn('publication_year:2024', {s for r in selection['history']['records'] for s in r['strata']})

    def test_all_anomalies_selected_and_research_questions_allowed(self):
        def special(i, row, check, origin):
            if i < 7:
                check['automatic_flags'] = ['duplicate_body_requires_review']
            if 10 <= i < 30:
                check['source_judgment_flags'] = ['source_conversation_markup']
        child = self.child(special=special)
        selection = self.select(child)
        self.assertTrue({f'TC5_{i}' for i in range(1, 8)}.issubset(selection['selected_ids']))
        self.assertLess(len(selection['selected_ids']), 15)
        receipt = self.receipt(selection)
        doc = w.load(receipt)
        doc['records'][0]['research_status'] = 'NEEDS_JOAQUIN_REVIEW'
        w.write(self.base, receipt.name, doc)
        review.require_gate(selection['selection_path'], [receipt])
        w.write(child, 'safety_halt.json', {'synthetic_halt': True})
        self.assertIn('native_safety_halt_present', review.validate_gate(selection['selection_path'], [receipt])['technical_blockers'])

    def test_native_pending_and_inherited_obligations_never_discharged(self):
        child = self.child()
        pending = child / 'checkpoint_00000400/pending_source_review_samples.csv'
        before = [p.read_bytes() for p in (pending, self.obligations)]
        selection = self.select(child)
        result = review.require_gate(selection['selection_path'], [self.receipt(selection)])
        self.assertEqual(before, [p.read_bytes() for p in (pending, self.obligations)])
        self.assertEqual(result['native_pending_obligation']['record_count'], 400)
        self.assertEqual(result['native_pending_obligation']['status'], 'unresolved_native_pending_source_review')
        self.assertFalse(result['human_approval'])
        self.assertEqual(len(selection['inherited_obligations']['original_list_counts']), 2)

    def test_receipt_requires_actual_read_hashes_no_human_or_research_pass(self):
        selection = self.select(self.child())
        receipt = self.receipt(selection)
        good = w.load(receipt)
        for field, value in (('actual_ai_read', False), ('note', ''), ('human_approval', True),
                             ('payload_sha256', '0' * 64), ('research_status', 'PASS')):
            bad = json.loads(json.dumps(good))
            bad['records'][0][field] = value
            w.write(self.base, receipt.name, bad)
            self.assertEqual(review.validate_gate(selection['selection_path'], [receipt])['status'], 'blocked_invalid_evidence')
        w.write(self.base, receipt.name, good)
        review.require_gate(selection['selection_path'], [receipt])

    def test_coverage_seal_requires_fulfilled_gate_and_reuses_without_old_corpus_replay(self):
        child = self.child()
        first = self.select(child)
        seal_path = self.base / 'coverage.json'
        with self.assertRaisesRegex(ValueError, 'gate blocked'):
            review.seal_gate(first['selection_path'], [], seal_path)
        self.assertFalse(seal_path.exists())
        receipt = self.receipt(first)
        seal = review.seal_gate(first['selection_path'], [receipt], seal_path)
        self.assertEqual(seal, review.seal_gate(first['selection_path'], [receipt], seal_path))
        self.assertEqual(len(seal['distinct_actual_ai_read_ids']), 4)
        next_child = self.child('next', first_id=1001)
        real_hash = w.sha_file
        def refuse_historical_corpus(path):
            path = Path(path)
            if child in path.parents and ('raw_html' in path.parts or path.name == 'pilot.sqlite'):
                raise AssertionError('Historical corpus must not be replayed')
            return real_hash(path)
        with patch.object(w, 'sha_file', side_effect=refuse_historical_corpus):
            second = self.select(next_child, 'nextreview', history_receipts=[{'coverage': str(seal_path)}])
            next_receipt = self.receipt(second, 'next_reading.json')
            review.require_gate(second['selection_path'], [next_receipt])
            second_seal = review.seal_gate(second['selection_path'], [next_receipt], self.base / 'next_coverage.json')
        self.assertEqual(len(second_seal['distinct_actual_ai_read_ids']), 8)
        self.assertEqual(second_seal['previous_seals'], [review._bound(seal_path)])
        original = seal_path.read_bytes()
        seal_path.write_bytes(original + b' ')
        self.assertEqual(review.validate_gate(second['selection_path'], [next_receipt])['status'], 'blocked_invalid_evidence')
        seal_path.write_bytes(original)
        original_receipt = receipt.read_bytes()
        receipt.write_bytes(original_receipt + b' ')
        self.assertEqual(review.validate_gate(second['selection_path'], [next_receipt])['status'], 'blocked_invalid_evidence')


if __name__ == '__main__':
    unittest.main()

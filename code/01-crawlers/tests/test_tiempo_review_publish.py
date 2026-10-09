"""Synthetic receipts only; publication tests never attest real AI reading."""
import copy
import json
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from crawler_core import tiempo_review_publish as publish, tiempo_stage_review as review
import test_tiempo_stage_review as stage_fixtures


class ReceiptPublicationTests(unittest.TestCase):
    setUp = stage_fixtures.StageReviewTests.setUp
    child = stage_fixtures.StageReviewTests.child
    select = stage_fixtures.StageReviewTests.select
    receipt = stage_fixtures.StageReviewTests.receipt

    def fixture(self):
        selection = self.select(self.child())
        good = json.loads(self.receipt(selection).read_text())
        return selection, good, Path(selection['selection_path']).parent / 'receipts'

    @staticmethod
    def subset(good, records):
        doc = copy.deepcopy(good)
        doc['records'] = records
        doc['actual_ai_read_ids'] = [r['sample_id'] for r in records]
        doc['actual_ai_read_count'] = len(records)
        return doc

    def test_invalid_format_missing_fields_hash_and_human_approval_never_visible(self):
        selection, good, receipts = self.fixture()
        mutations = [lambda d: d['records'][0].update(research_status='none'),
                     lambda d: d['records'][0].pop('research_status'),
                     lambda d: d['records'][0].update(human_approval=True),
                     lambda d: d.update(human_approval=True),
                     lambda d: d['records'][0].update(payload_sha256='0' * 64),
                     lambda d: d.update(actual_ai_read_count=True),
                     lambda d: d['records'][0].update(note=''),
                     lambda d: d['records'][0].update(actual_ai_read=False),
                     lambda d: d.update(records=[])]
        for mutate in mutations:
            bad = copy.deepcopy(good)
            mutate(bad)
            with self.assertRaises(ValueError):
                publish.publish_receipt(selection['selection_path'], bad, 'reviewer_even.json')
            self.assertFalse(list(receipts.glob('*.json')))
        self.assertEqual(good['records'][0]['research_status'], None)

    def test_partial_input_and_duplicate_json_fields_never_visible(self):
        selection, good, receipts = self.fixture()
        draft = self.base / 'draft.json'
        for content in ('{"schema": ', '{"schema": "a", "schema": "b"}',
                        json.dumps(good).replace('"research_status": null', '"research_status": NaN', 1)):
            draft.write_text(content)
            with self.assertRaises(ValueError):
                publish.publish_receipt(selection['selection_path'], draft, 'reviewer_even.json')
            self.assertFalse(list(receipts.glob('*.json')))

    def test_valid_partial_then_combined_success_preserves_claims(self):
        selection, good, receipts = self.fixture()
        first = self.subset(good, good['records'][::2])
        second = self.subset(good, good['records'][1::2])
        result = publish.publish_receipt(selection['selection_path'], first, 'reviewer_odd.json')
        self.assertEqual(result['combined_gate_status'], 'blocked_pending_actual_ai_reading')
        self.assertFalse(result['gate']['integrity_error'])
        self.assertEqual(json.loads((receipts / 'reviewer_odd.json').read_text()), first)
        second['records'][0]['research_status'] = 'NEEDS_JOAQUIN_REVIEW'
        result = publish.publish_receipt(selection['selection_path'], second, 'reviewer_even.json')
        self.assertEqual(result['combined_gate_status'], 'collection_gate_satisfied')
        self.assertEqual(result['new_reading_claims_created_by_helper'], 0)
        self.assertFalse(result['human_approval'])
        self.assertEqual(result['gate']['new_actual_ai_read_count'], len(good['records']))
        self.assertEqual(list((receipts.parent / '.receipt_staging').iterdir()), [])

    def test_duplicate_ids_rejected_and_existing_receipt_never_overwritten(self):
        selection, good, receipts = self.fixture()
        publish.publish_receipt(selection['selection_path'], good, 'reviewer_odd.json')
        original = (receipts / 'reviewer_odd.json').read_bytes()
        for filename in ('reviewer_even.json', 'reviewer_odd.json'):
            with self.assertRaises(ValueError):
                publish.publish_receipt(selection['selection_path'], good, filename)
        self.assertEqual((receipts / 'reviewer_odd.json').read_bytes(), original)
        self.assertFalse((receipts / 'reviewer_even.json').exists())

    def test_simultaneous_duplicate_publication_serializes_before_validation(self):
        selection, good, receipts = self.fixture()
        def submit(filename):
            try:
                return publish.publish_receipt(selection['selection_path'], good, filename)['status']
            except ValueError:
                return 'rejected'
        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(submit, ['reviewer_odd.json', 'reviewer_even.json']))
        self.assertCountEqual(statuses, ['published_immutable', 'rejected'])
        self.assertEqual(len(list(receipts.glob('*.json'))), 1)
        review.require_gate(selection['selection_path'], list(receipts.glob('*.json')))

    def test_exclusive_link_refuses_racing_external_file_without_replacement(self):
        selection, good, receipts = self.fixture()
        real_publish = publish._exclusive_publish
        def racing_publish(staged, final):
            final.write_bytes(b'existing concurrent evidence')
            real_publish(staged, final)
        with patch.object(publish, '_exclusive_publish', side_effect=racing_publish):
            with self.assertRaises(FileExistsError):
                publish.publish_receipt(selection['selection_path'], good, 'reviewer_even.json')
        self.assertEqual((receipts / 'reviewer_even.json').read_bytes(), b'existing concurrent evidence')

    def test_interrupt_before_publication_and_uncertain_after_publication(self):
        selection, good, receipts = self.fixture()
        with patch.object(publish, '_exclusive_publish', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                publish.publish_receipt(selection['selection_path'], good, 'reviewer_even.json')
        self.assertFalse(list(receipts.glob('*.json')))
        self.assertEqual(list((receipts.parent / '.receipt_staging').iterdir()), [])
        with patch.object(publish, '_sync_dir', side_effect=OSError('Synthetic interruption after link')):
            with self.assertRaises(OSError):
                publish.publish_receipt(selection['selection_path'], good, 'reviewer_even.json')
        self.assertEqual(json.loads((receipts / 'reviewer_even.json').read_text()), good)
        with self.assertRaisesRegex(ValueError, 'Immutable receipt already exists'):
            publish.publish_receipt(selection['selection_path'], good, 'reviewer_even.json')
        review.require_gate(selection['selection_path'], list(receipts.glob('*.json')))

    def test_real_technical_blocker_is_published_and_collection_remains_blocked(self):
        selection, good, receipts = self.fixture()
        good['records'][0]['technical_blockers'] = ['actual_body_omission_requires_fix']
        result = publish.publish_receipt(selection['selection_path'], good, 'reviewer_even.json')
        self.assertEqual(result['combined_gate_status'], 'blocked_technical_review')
        self.assertFalse(result['gate']['integrity_error'])
        self.assertIn('actual_body_omission_requires_fix', result['gate']['technical_blockers'])
        with self.assertRaisesRegex(ValueError, 'gate blocked'):
            review.require_gate(selection['selection_path'], list(receipts.glob('*.json')))

    def test_names_and_watched_candidates_rejected(self):
        selection, good, receipts = self.fixture()
        for filename in ('../bad.json', '/tmp/bad.json', 'reviewer/odd.json', '.hidden.json',
                         'reviewer..json', 'reviewer.json.tmp', ''):
            with self.assertRaisesRegex(ValueError, 'Invalid receipt filename'):
                publish.publish_receipt(selection['selection_path'], good, filename)
        receipts.mkdir(exist_ok=True)
        draft = receipts / 'watched.tmp'
        draft.write_text(json.dumps(good))
        with self.assertRaisesRegex(ValueError, 'outside the watched'):
            publish.publish_receipt(selection['selection_path'], draft, 'reviewer_even.json')
        self.assertFalse(list(receipts.glob('*.json')))


if __name__ == '__main__':
    unittest.main()

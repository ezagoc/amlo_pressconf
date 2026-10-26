import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import pandas as pd
from alignment import blind, validate, fingerprint, process, VERSION, DEFAULT_MODEL


class AlignmentEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.row = {'question_id': '2025-01-01:q001', 'text': '¿Cómo va el hospital?',
                    'context_text': 'Ana Pérez, de Medio Uno. Presidenta, sobre el hospital.',
                    'speaker_name': 'Ana Pérez', 'reporter_labels': 'Ana Pérez',
                    'outlet_labels': 'Medio Uno', 'answer': 'No debe llegar al modelo.'}
        self.original = {'question_id': self.row['question_id'], 'question': self.row['text'],
                         'preamble': self.row['context_text']}
        self.result = {'items': [{'question_id': self.row['question_id'], 'alignment': 'neutral',
                                 'evidence': [{'field': 'question', 'quote': '¿Cómo va el hospital?'}],
                                 'reason': 'Solicita un avance sin elogios ni cuestionamiento.'}]}

    def test_blinding_and_no_answer_input(self):
        item = blind(self.row)
        self.assertEqual(set(item), {'question_id', 'question', 'preamble'})
        self.assertNotIn('Ana Pérez', item['preamble'])
        self.assertNotIn('Medio Uno', item['preamble'])
        self.assertIn('Presidenta, sobre el hospital.', item['preamble'])
        validate(self.result, [item], [self.original])

    def test_reject_invented_evidence_or_missing_question(self):
        with self.assertRaises(ValueError): validate({'items': []}, [blind(self.row)], [self.original])
        self.result['items'][0]['evidence'][0]['quote'] = 'Este gran proyecto'
        with self.assertRaises(ValueError): validate(self.result, [blind(self.row)], [self.original])

    def test_completed_retry_resumes_without_api(self):
        with TemporaryDirectory() as temp:
            root = Path(temp); (root/'results').mkdir()
            saved = {'codebook_version': VERSION, 'model': DEFAULT_MODEL, 'batch_size': 10,
                     'input_sha256': fingerprint({'codebook_version': VERSION, 'questions': [blind(self.row)]}),
                     'originals_sha256': fingerprint([self.original]), 'result': self.result}
            (root/'results/2025-01-01.json').write_text(json.dumps(saved))
            with patch('alignment.call') as api:
                self.assertEqual(process('2025-01-01', pd.DataFrame([self.row]), root), saved)
                api.assert_not_called()


if __name__ == '__main__': unittest.main()

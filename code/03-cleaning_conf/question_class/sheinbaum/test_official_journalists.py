"""Offline checks for official-source eligibility and safe pilot reuse."""
from contextlib import redirect_stdout
from io import StringIO
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import pandas as pd
import official_journalists as pipeline


class OfficialJournalistTests(unittest.TestCase):
    def day(self):
        return pd.DataFrame({
            'source_row': [0, 1, 2, 3, 4],
            'participant': ['PRESIDENTA', 'PREGUNTA', 'INTERVENCION', 'REPORTERA', 'PREGUNTA'],
            'participant_raw': ['PRESIDENTA', 'PREGUNTA', 'INTERVENCIÓN', 'REPORTERA', 'PREGUNTA'],
            'is_question_speaker': [False, True, False, False, True],
            'row_kind': ['transcript'] * 4 + ['document_metadata'],
            'text': ['Bienvenidos.', 'Ana, Canal 11.', 'Gracias.', 'Buenos días.', 'Encabezado.'],
            'source_url': ['https://example.org/transcript'] * 5,
            'source_sha256': ['source-hash'] * 5,
        })

    def test_eligibility_includes_generic_press_but_excludes_metadata(self):
        self.assertEqual(pipeline.eligible_rows(self.day()), [1, 2, 3])

    def test_pilot_reuse_is_validated_and_makes_no_api_request(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            day = self.day()
            date = '2024-10-02'
            user = json.dumps({'date': date, 'eligible_source_rows': [1],
                              'transcript': pipeline.transcript(day)}, ensure_ascii=False)
            request = {'model': pipeline.DEFAULT_MODEL, 'system': pipeline.JOURNALISTS_PROMPT,
                       'user': user, 'max_tokens': 16000, 'schema': pipeline.JOURNALISTS_SCHEMA,
                       'api': 'responses', 'reasoning_effort': 'low'}
            fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            checkpoint = {'request': request, 'result': {'periodistas': [
                {'name': 'Ana', 'outlets': ['Canal 11'], 'intro_row': 1, 'evidence_rows': [1]}]},
                'usage': {'input_tokens': 100, 'output_tokens': 10}}
            path = base / 'transcript_analysis/official-pilot-10/checkpoints/journalists' / f'{fingerprint}.json'
            pipeline.atomic_json(path, checkpoint)
            seed = pipeline.pilot_seeds(base, {date: day}, pipeline.DEFAULT_MODEL)[date]
            client = Mock()
            with patch.object(pipeline, 'OpenAI', return_value=client), redirect_stdout(StringIO()):
                result = pipeline.process(date, day, base / 'output', pipeline.DEFAULT_MODEL, seed)
            client.responses.create.assert_not_called()
            self.assertEqual(result['result'], checkpoint['result'])
            self.assertTrue(result['reused_pilot'])
            changed = day.copy()
            changed.loc[1, 'text'] = 'Texto corregido.'
            with self.assertRaisesRegex(ValueError, 'transcript differ'):
                pipeline.pilot_seeds(base, {date: changed}, pipeline.DEFAULT_MODEL)


if __name__ == '__main__':
    unittest.main()

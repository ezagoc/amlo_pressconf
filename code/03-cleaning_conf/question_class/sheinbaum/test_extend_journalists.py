"""Regression checks for safe reuse when extending the extraction corpus."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from extend_journalists import verified_result
from official_journalists import DEFAULT_MODEL, sha, transcript
from test_official_journalists import OfficialJournalistTests


class ExtendedExtractionTests(unittest.TestCase):
    def test_reuse_rejects_changed_text_or_source(self):
        day = OfficialJournalistTests().day(); date = '2024-10-02'; eligible = [1, 2, 3]
        user = json.dumps({'date': date, 'eligible_source_rows': eligible,
                          'transcript': transcript(day)}, ensure_ascii=False)
        payload = {'date': date, 'model': DEFAULT_MODEL, 'input_sha256': sha(user),
            'source_sha256': 'source-hash', 'eligible_rows': eligible,
            'result': {'periodistas': [{'name': None, 'outlets': ['Canal 11'],
                                       'intro_row': 1, 'evidence_rows': [1]}]}}
        with TemporaryDirectory() as temp:
            path = Path(temp)/'result.json'; path.write_text(json.dumps(payload))
            self.assertEqual(verified_result(path, date, day, eligible), payload)
            changed = day.copy(); changed.loc[1, 'text'] = 'Otra persona, otro medio.'
            with self.assertRaisesRegex(AssertionError, 'Stale extraction input'):
                verified_result(path, date, changed, eligible)
            changed = day.copy(); changed['source_sha256'] = 'different-hash'
            with self.assertRaisesRegex(AssertionError, 'Stale source'):
                verified_result(path, date, changed, eligible)


if __name__ == '__main__': unittest.main()

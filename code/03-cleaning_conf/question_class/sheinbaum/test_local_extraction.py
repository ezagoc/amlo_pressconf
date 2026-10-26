"""Check evidence integrity and conservative journalist/outlet attribution."""
from contextlib import redirect_stdout
import hashlib
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

import extract_journalists_local as local


class LocalExtractionTests(unittest.TestCase):
    def fixture(self, root):
        output = root / 'auxiliar'
        output.mkdir()
        texts = {
            1: 'Ana Pérez, de Telesur. Mi pregunta sobre El Financiero.',
            2: 'También represento a 24 Horas.',
            3: 'De Reuters.',
            4: 'De Reuters.',
            5: 'El presidente menciona a Juan López, de Reforma.',
        }
        pd.DataFrame([
            {'date': pd.Timestamp('2025-01-02'), 'source_row': n,
             'text': text, 'source_path': 'fixture.csv'}
            for n, text in texts.items()
        ]).to_parquet(output / 'transcript_rows.parquet', index=False)
        pd.DataFrame({'date': ['2025-01-02', '2025-01-03'],
                      'n_question_rows': [5, 0]}).to_csv(output / 'conference_manifest.csv', index=False)

        def record(rows, reporter, outlets):
            return {'date': '2025-01-02', 'source_row': rows[0],
                    'reporter': reporter, 'evidence_rows': ';'.join(map(str, rows)),
                    'name_status': 'stated' if reporter else 'not_stated',
                    'evidence_sha256': hashlib.sha256(
                        '\n'.join(texts[n] for n in rows).encode()).hexdigest(),
                    'outlets': outlets}

        pd.DataFrame([record([1, 2], 'Ana Pérez', 'Telesur|24 Horas')]).to_csv(
            root / 'reviewed_introductions.tsv', sep='\t', index=False)
        pd.DataFrame([record([n], '', 'Reuters') for n in [3, 4]]).to_csv(
            root / 'reviewed_outlet_only.tsv', sep='\t', index=False)
        return output

    def test_preserves_outlet_only_and_evidence_without_incidental_mentions(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            output = self.fixture(root)
            with patch.object(local, 'HERE', root), redirect_stdout(StringIO()):
                local.export(root)
            daily = pd.read_parquet(output / 'periodistas_v2_all_years.parquet')
            evidence = pd.read_parquet(output / 'journalist_media_evidence.parquet')
            self.assertEqual(len(daily), 3)
            self.assertEqual(len(evidence), 4)
            self.assertEqual(set(daily.outlet), {'Telesur', '24 Horas', 'Reuters'})
            anonymous = daily[daily.outlet.eq('Reuters')].iloc[0]
            self.assertTrue(pd.isna(anonymous.reporter))
            self.assertTrue(anonymous.no_reporter_flag)
            self.assertEqual(anonymous.source_rows, '3')
            named = daily[daily.outlet.eq('24 Horas')].iloc[0]
            self.assertEqual(named.outlet_aux, '24 horas')
            self.assertEqual(named.source_rows, '1;2')
            self.assertEqual(named.reporter_aux, 'ana perez')
            coverage = pd.read_csv(output / 'journalist_media_coverage.csv')
            self.assertEqual(coverage.n_records.tolist(), [3, 0])

    def test_changed_source_requires_review(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            output = self.fixture(root)
            source = pd.read_parquet(output / 'transcript_rows.parquet')
            source.loc[0, 'text'] = 'Changed source.'
            source.to_parquet(output / 'transcript_rows.parquet', index=False)
            with patch.object(local, 'HERE', root):
                with self.assertRaisesRegex(ValueError, 'Source changed; re-review'):
                    local.export(root)

    def test_unsupported_affiliation_rejected(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            ledger = root / 'reviewed_introductions.tsv'
            data = pd.read_csv(ledger, sep='\t')
            data.loc[0, 'outlets'] = 'Reuters'
            data.to_csv(ledger, sep='\t', index=False)
            with patch.object(local, 'HERE', root):
                with self.assertRaisesRegex(ValueError, 'not supported by evidence'):
                    local.export(root)


if __name__ == '__main__':
    unittest.main()

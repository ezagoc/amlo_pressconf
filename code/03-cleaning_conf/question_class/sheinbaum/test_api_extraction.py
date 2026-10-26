"""Offline checks: full text, nullable identities, evidence and API isolation."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import pandas as pd
import httpx
import run_models as models


class ExtractionTests(unittest.TestCase):
    def test_joint_names_require_explicit_conjunction_and_opt_in(self):
        def result(names):
            return {'periodistas': [{'name': name, 'outlets': ['ECODiario'],
                'intro_row': 469, 'evidence_rows': [469]} for name in names]}
        texts = {469: 'Esther Consuegra y Rocío Pedroza, de ECODiario.'}
        people = result(['Esther Consuegra', 'Rocío Pedroza'])
        models.validate_journalists(people, {469}, texts, allow_joint_introductions=True)
        with self.assertRaisesRegex(ValueError, 'Duplicate introduction'):
            models.validate_journalists(people, {469}, texts)
        for bad in [result(['Esther Consuegra', 'Esther Consuegra']),
                    result(['Esther Consuegra', None])]:
            with self.assertRaisesRegex(ValueError, 'Duplicate introduction'):
                models.validate_journalists(bad, {469}, texts, allow_joint_introductions=True)
        with self.assertRaisesRegex(ValueError, 'without an explicit joint'):
            models.validate_journalists(people, {469},
                {469: 'Esther Consuegra, de ECODiario. Mi pregunta es sobre Rocío Pedroza.'},
                allow_joint_introductions=True)

    def test_outlet_interrupted_by_explicit_reporter_name(self):
        result = {'periodistas': [{'name': 'Javier Pérez', 'outlets': ['HCTV Noticias'],
                                  'intro_row': 157, 'evidence_rows': [157]}]}
        for text in ['HCTV —Javier Pérez— Noticias.', 'HCTV (Javier Pérez) Noticias.']:
            models.validate_journalists(result, {157}, {157: text})
        for text in ['Javier Pérez, HCTV —otra persona— Noticias.',
                     'Javier Pérez, HCTV y también Noticias.',
                     'HCTV —Javier Pérez— y otras Noticias.']:
            with self.assertRaises(ValueError):
                models.validate_journalists(result, {157}, {157: text})

    def test_exhausted_credit_stops_without_retry(self):
        response = httpx.Response(429, request=httpx.Request('POST', 'https://api.openai.com/v1/responses'))
        error = models.RateLimitError('Credit exhausted', response=response,
            body={'code': 'credit_balance_exhausted'})
        with TemporaryDirectory() as temp:
            create = Mock(side_effect=error)
            client = SimpleNamespace(responses=SimpleNamespace(create=create))
            with patch.object(models.time, 'sleep') as sleep:
                with self.assertRaises(models.RateLimitError):
                    models.call(client, Path(temp), 'journalists', models.DEFAULT_MODEL,
                        'Extract JSON', 'Evidence', lambda r: None)
                self.assertEqual(create.call_count, 1)
                sleep.assert_not_called()
            self.assertFalse(list(Path(temp).rglob('*.json')))

    def test_nullable_and_partial_names_require_supported_identity(self):
        def result(name=None, outlets=None, evidence_rows=None):
            return {"periodistas": [{"name": name, "outlets": outlets or [],
                "intro_row": 2, "evidence_rows": evidence_rows or [2]}]}
        texts = {2: "Adrián, de W."}
        models.validate_journalists(result(outlets=["W"]), {2}, texts)
        models.validate_journalists(result(name="Adrián"), {2}, texts)
        for bad in [result(), result(name=""), result(name="Ana Pérez"),
                    result(outlets=["Inventado"]), result(outlets=["W"], evidence_rows=[1, 2])]:
            with self.assertRaises(ValueError):
                models.validate_journalists(bad, {2}, texts)

    def test_full_text_context_outlet_only_and_repeated_intro(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            root = Path(temp) / "api"
            (source / "auxiliar").mkdir(parents=True)
            long_text = "Texto de la intervención. " * 30 + "De Grupo Transmedia La Chispa."
            rows = pd.DataFrame({"date": pd.to_datetime(["2024-10-02"] * 3),
                "source_row": [2, 3, 4], "source_path": ["source.csv"] * 3,
                "participant": ["PREGUNTA"] * 3,
                "text": [long_text, "De Grupo Transmedia La Chispa.", "Soy Adrián."]})
            rows.to_parquet(source / "auxiliar/question_rows.parquet", index=False)
            context = pd.concat([rows, pd.DataFrame([{
                "date": pd.Timestamp("2024-10-02"), "source_row": 1,
                "source_path": "source.csv", "participant": "PRESIDENTA",
                "text": "Este párrafo es contexto, no una presentación."}])])
            context.to_parquet(source / "auxiliar/transcript_rows.parquet", index=False)
            original = b"reviewed dataset must remain unchanged"
            reviewed = source / "auxiliar/periodistas_v2_all_years.parquet"
            reviewed.write_bytes(original)

            def fake_call(client, root, stage, model, system, user, validator, **kwargs):
                request = json.loads(user)
                self.assertEqual(request["eligible_source_rows"], [2, 3, 4])
                self.assertEqual(request["transcript"][1]["text"], long_text)
                self.assertEqual(request["transcript"][0]["speaker"], "PRESIDENTA")
                self.assertEqual(kwargs["schema"], models.JOURNALISTS_SCHEMA)
                response = {"periodistas": [
                    {"name": None, "outlets": ["Grupo Transmedia La Chispa"], "intro_row": n, "evidence_rows": [n]}
                    for n in [2, 3]] + [{"name": "Adrián", "outlets": [], "intro_row": 4, "evidence_rows": [4]}]}
                validator(response)
                return response

            with patch.object(models, "call", side_effect=fake_call), redirect_stdout(StringIO()):
                models.journalists_stage(None, root, models.DEFAULT_MODEL, source)
            out = pd.read_parquet(root / "auxiliar/periodistas_v2_all_years.parquet")
            evidence = pd.read_parquet(root / "auxiliar/journalist_media_evidence.parquet")
            self.assertEqual(len(out), 2)
            self.assertEqual(len(evidence), 3)
            self.assertEqual(out.no_reporter_flag.sum(), 1)
            self.assertEqual(out.no_outlet_flag.sum(), 1)
            self.assertEqual(out.iloc[0].evidence_text, long_text)
            self.assertTrue(pd.isna(out.iloc[0].reporter_aux))
            self.assertEqual(reviewed.read_bytes(), original)

    def test_pilot_spans_dates_and_dry_run_does_not_write(self):
        rows = pd.DataFrame({"date": pd.date_range("2024-10-02", periods=221)})
        dates = models.select_dates(rows, 10)
        self.assertEqual(len(set(dates)), 10)
        self.assertEqual(dates[0], rows.date.iloc[0])
        self.assertEqual(dates[-1], rows.date.iloc[-1])
        with TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            root = Path(temp) / "api"
            (source / "auxiliar").mkdir(parents=True)
            rows.assign(text="Transcript").to_parquet(source / "auxiliar/question_rows.parquet")
            with patch.object(models, "call") as call, redirect_stdout(StringIO()):
                models.journalists_stage(None, root, models.DEFAULT_MODEL, source, 10, True)
            call.assert_not_called()
            self.assertFalse(root.exists())

    def test_modern_api_parameters_and_cache(self):
        calls = []
        def create(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(status="completed", output_text='{"periodistas": []}',
                usage=SimpleNamespace(model_dump=lambda: {"input_tokens": 100, "output_tokens": 10}))
        client = SimpleNamespace(responses=SimpleNamespace(create=create))
        with TemporaryDirectory() as temp:
            for _ in range(2):
                models.call(client, Path(temp), "journalists", models.DEFAULT_MODEL,
                    "Extract JSON", "Evidence", lambda r: models.validate_journalists(r, set()),
                    tokens=16000, schema=models.JOURNALISTS_SCHEMA)
            checkpoints = list(Path(temp).rglob('*.json'))
            self.assertEqual(len(checkpoints), 1)
            self.assertEqual(json.loads(checkpoints[0].read_text())["usage"]["input_tokens"], 100)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["reasoning"], {"effort": "low"})
        self.assertEqual(calls[0]["text"]["format"]["type"], "json_schema")
        self.assertFalse(calls[0]["store"])
        self.assertNotIn("temperature", calls[0])
        self.assertNotIn("max_tokens", calls[0])

    def test_no_eligible_rows_produces_coverage_without_api_call(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / 'source'
            root = Path(temp) / 'api'
            (source / 'auxiliar').mkdir(parents=True)
            rows = pd.DataFrame({'date': pd.to_datetime(['2025-02-07']),
                'source_row': [0], 'text': ['Buenos días.'], 'source_path': ['source.csv']})
            rows.to_parquet(source / 'auxiliar/transcript_rows.parquet')
            rows.iloc[:0].to_parquet(source / 'auxiliar/question_rows.parquet')
            with patch.object(models, 'call') as call, redirect_stdout(StringIO()):
                models.journalists_stage(None, root, models.DEFAULT_MODEL, source)
            call.assert_not_called()
            self.assertEqual(len(pd.read_parquet(root / 'auxiliar/periodistas_v2_all_years.parquet')), 0)
            coverage = pd.read_csv(root / 'auxiliar/journalist_media_coverage.csv')
            self.assertEqual(coverage.status.tolist(), ['no_eligible_rows_not_sent'])


if __name__ == '__main__':
    unittest.main()

"""Offline regression checks for discovery, attribution, and resumability."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd

import prepare
import run_models as models


class PipelineTests(unittest.TestCase):
    def test_discovery_uses_filename_not_day_directory(self):
        tree = {"tree": [
            {"path": "2024/10-2024/2 de octubre de 2024/mananera_2_10_2024.csv", "sha": "a"},
            {"path": "2025/8-2025/agosto 22, 2025/mananera_22_08_2025.csv", "sha": "b"},
            {"path": "2025/8-2025/agosto 22, 2025/csv_por_participante/PREGUNTA.csv", "sha": "c"},
        ]}
        self.assertEqual([r["date"] for r in prepare.discover(tree)], ["2024-10-02", "2025-08-22"])
        self.assertEqual(len(prepare.discover(tree, end="2024-12-31")), 1)
        with self.assertRaises(ValueError):
            prepare.discover({**tree, "truncated": True})

    def test_speaker_variants_and_news_weekend(self):
        for label in [" PREGUNTA ", "PREGUNTAS", "INTERLOCUTORA ", "INTERLOCUTIR", "PREGUNTA (VIDEOLLAMADA)"]:
            self.assertTrue(prepare.is_question_speaker(label))
        for label in ["PRESIDENTA CLAUDIA SHEINBAUM PARDO", "INTERVENCION MUJER", "REPORTERO"]:
            self.assertFalse(prepare.is_question_speaker(label))
        self.assertEqual([str(d.date()) for d in prepare.context_dates("2024-10-07")], ["2024-10-04", "2024-10-05", "2024-10-06"])

    def test_followup_survives_and_next_reporter_is_excluded(self):
        rows = pd.DataFrame({"source_row": [1, 2, 8, 10, 11], "text": ["Ana Pérez", "Pregunta", "Seguimiento", "Juan López", "Otra"]})
        people = [{"name": "Juan López", "intro_row": 10}, {"name": "Ana Pérez", "intro_row": 1}]
        blocks = list(models.build_blocks(rows, people))
        self.assertEqual(blocks[0][2].source_row.tolist(), [1, 2, 8])
        self.assertEqual(blocks[1][2].source_row.tolist(), [10, 11])

    def test_rejects_invalid_model_results(self):
        with self.assertRaises(ValueError):
            models.validate_journalists({"periodistas": [{"name": "Ana Pérez", "outlets": [], "intro_row": 5}]}, {1, 2})
        with self.assertRaises(ValueError):
            models.validate_questions({"items": [{"type": "invented", "text": "Text"}]})
        models.validate_questions({"items": []})

    def test_empty_response_is_checkpointed_and_input_changes_invalidate(self):
        calls = []
        def create(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content='{"items": []}'))], usage=None)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with TemporaryDirectory() as temp:
            for user in ["one", "one", "two"]:
                models.call(client, Path(temp), "questions", "gpt-4o-mini", "system", user, models.validate_questions)
        self.assertEqual(len(calls), 2)

    def test_models_pipeline_preserves_multi_outlet_items_without_double_classification(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "auxiliar").mkdir()
            rows = pd.DataFrame({"date": pd.to_datetime(["2024-10-02"] * 3), "source_row": [1, 2, 8],
                "source_path": ["source.csv"] * 3, "text": ["Ana Pérez, W y Canal 11.",
                "Quisiera preguntarle qué hará el gobierno para resolver este problema de seguridad.", "¿Cuándo lo resolverá?"]})
            rows.to_parquet(root / "auxiliar/question_rows.parquet")
            calls = []
            def fake_call(client, root, stage, model, system, user, validator, tokens=6000, schema=None):
                calls.append(stage)
                result = {"journalists": {"periodistas": [{"name": "Ana Pérez", "outlets": ["W", "Canal 11"], "intro_row": 1, "evidence_rows": [1]}]},
                    "questions": {"items": [{"type": "pregunta", "text": "¿Cuándo lo resolverá?"}]},
                    "alignment": {"alignment": "oppositional", "reason": "Solicita rendición de cuentas."}}[stage]
                validator(result)
                return result
            with patch.object(models, "call", side_effect=fake_call):
                models.journalists_stage(None, root, "test")
                models.questions_stage(None, root, "test")
                models.alignment_stage(None, root, "test")
                output = pd.read_parquet(root / "auxiliar/questions_with_alignment.parquet")
                self.assertEqual(len(output), 2)
                self.assertTrue(output.alignment.isna().all())
                self.assertNotIn("alignment", calls)
                pd.DataFrame({"date": pd.to_datetime(["2024-10-01"]), "daily_summary": ["Noticias del día"], "n_articles": [2]}).to_parquet(root / "auxiliar/daily_summaries.parquet")
                models.alignment_stage(None, root, "test")
                self.assertEqual(calls.count("alignment"), 1)
                output = pd.read_parquet(root / "auxiliar/questions_with_alignment.parquet")
                self.assertTrue(output.alignment.eq("oppositional").all())
                self.assertEqual(output.item_id.nunique(), 1)


if __name__ == "__main__":
    unittest.main()

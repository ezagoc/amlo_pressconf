"""Real offline worker/scheduler runs preserve bound historical identity evidence."""
import contextlib
import hashlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawler_core import tiempo_continuous_source as source
from crawler_core import tiempo_continuous_v5 as worker
from crawler_core.tiempo_html import tiempo_fields
import test_tiempo_continuous_v5 as fixtures


class HistoryIdentityTests(unittest.TestCase):
    setUp = fixtures.V5Tests.setUp
    freeze = fixtures.V5Tests.freeze
    execute = fixtures.V5Tests.execute
    current = fixtures.V5Tests.current
    setup_campaign = fixtures.V5Tests.setup_campaign
    run_campaign = fixtures.V5Tests.run_campaign

    def index(self, records, *, name="history.json", parent=None):
        path = self.base / name
        worker.write(self.base, name, {"schema": worker.HISTORY_SCHEMA, "records": records, "parent": parent})
        return {"path": str(path), "sha256": worker.sha_file(path)}

    def past(self, *, sid="HISTORICAL", url="https://www.tiempo.com.mx/local/past/", canonical=None, body=None):
        return {"sample_id": sid, "url": url, "canonical_url": canonical, "body_compact_sha256": body,
                "snapshot_sha256": "a" * 64, "fields_sha256": "b" * 64}

    def bind_history(self, binding):
        self.root = self.root.with_name("with_history")
        context = {"source_history": [], "service_history": [], "last_transport_finish": None,
                   "prior_plan_receipts": [], "history_index": binding}
        return worker.freeze(self.input, self.root, self.media, self.registry_path, worker.sha_file(self.registry_path),
                             self.exclusions, start="2024-06-01", end="2024-06-02", max_fetch_calls=len(self.rows) * 3,
                             queue_db_path=self.queue_db, queue_db_sha256=worker.sha_file(self.queue_db), min_free_bytes=1,
                             seed_context=context)

    def checks(self):
        return [worker.load(self.root / "row_checks" / (r["sample_id"] + ".json"))["record"] for r in self.rows]

    @staticmethod
    def shared_body_response(url, timeout, **kwargs):
        slug = url.rstrip("/").split("/")[-1]
        response = fixtures.response(url, timeout, **kwargs)
        response["text"] = response["text"].replace("Summary " + slug, "Summary shared").replace("Report " + slug, "Report shared")
        return response

    def test_three_historical_canonical_relations_are_judgments_not_false_halt(self):
        self.freeze(3)
        binding = self.index([self.past(sid="OLD_" + str(i), canonical=r["url"]) for i, r in enumerate(self.rows)])
        self.bind_history(binding)
        fetch = Mock(side_effect=fixtures.response)
        result = self.execute(fetch)
        self.assertTrue(result["collection_inputs_finished"])
        self.assertEqual(fetch.call_count, 3)
        for i, record in enumerate(self.checks()):
            self.assertIn("duplicate_canonical_requires_review", record["source_judgment_flags"])
            self.assertEqual(record["unexplained_flags"], [])
            self.assertEqual(record["critical_flags"], [])
            self.assertEqual(record["duplicate_relations"][0]["prior_sample_ids"], ["OLD_" + str(i)])
            self.assertEqual(record["collection_quality_status"], worker.QUARANTINE)
        self.assertFalse((self.root / "safety_halt.json").exists())

    def test_history_body_relation_survives_worker_completion_and_resume(self):
        self.freeze(2)
        text = tiempo_fields(self.shared_body_response(self.rows[0]["url"], 1)["text"], url=self.rows[0]["url"])["main_text"]
        compact_hash = hashlib.sha256(source.compact(text).encode()).hexdigest()
        binding = self.index([self.past(body=compact_hash)])
        self.bind_history(binding)
        fetch = Mock(side_effect=self.shared_body_response)
        self.assertTrue(self.execute(fetch)["collection_inputs_finished"])
        for record in self.checks():
            self.assertIn("duplicate_body_requires_review", record["source_judgment_flags"])
            self.assertTrue(any("HISTORICAL" in r["prior_sample_ids"] for r in record["duplicate_relations"]))
        context = worker.load(self.root / "continuation_context.json")
        records = worker.load_history_index(context["history_index"])
        self.assertEqual({r["sample_id"] for r in records}, {"HISTORICAL", *(r["sample_id"] for r in self.rows)})
        self.assertEqual(worker.load(self.root / "identity_index.json")["parent"], binding)
        resume = Mock(side_effect=AssertionError("Must not refetch saved rows"))
        self.assertTrue(self.execute(resume)["collection_inputs_finished"])
        resume.assert_not_called()

    def test_scheduler_carries_identity_index_across_children(self):
        self.setup_campaign(3, 1)
        fetch = Mock(side_effect=self.shared_body_response)
        result = self.run_campaign(fetch)
        self.assertEqual(result["completed_plans"], 3)
        campaign = worker.load(self.master / "campaign.json")
        child = self.media / "data/00-newspaper_data/crawler/pilots/Kevin/tiempo_continuous_v5" / campaign["child_names"][-1]
        record = worker.load(next((child / "row_checks").glob("*.json")))["record"]
        self.assertIn("duplicate_body_requires_review", record["source_judgment_flags"])
        relation = next(r for r in record["duplicate_relations"] if r["identity_type"] == "body")
        self.assertEqual(len(relation["prior_sample_ids"]), 2)
        index = worker.load_history_index(worker.load(child / "continuation_context.json")["history_index"])
        self.assertEqual(len(index), 3)
        self.run_campaign(fetch)
        self.assertEqual(fetch.call_count, 3)

    def test_self_replay_is_not_a_duplicate_but_conflicting_source_evidence_fails(self):
        self.freeze(1)
        self.execute()
        row = self.current()[0]
        check = self.checks()[0]
        identity = worker._identity_record(row, check)
        binding = self.index([identity])
        seen = worker.seed_history_identities(binding)
        plan, registry = worker.load_plan(self.root, self.media)
        batch_dir = self.root / "batches/batch_000001"
        record, _ = worker._risk(row, batch_dir, registry, seen, plan)
        self.assertEqual(record["duplicate_relations"], [])
        self.assertFalse(any("duplicate_" in f for f in record["automatic_flags"]))
        worker._remember(row, record, seen)
        bad = {**row, "title": "changed saved title"}
        with self.assertRaisesRegex(ValueError, "differs from frozen history"):
            worker._remember(bad, record, seen)

    def test_sidecar_mutation_refuses_before_fetch(self):
        self.freeze(1)
        binding = self.index([self.past()])
        self.bind_history(binding)
        Path(binding["path"]).write_text("{}")
        fetch = Mock()
        with self.assertRaisesRegex(ValueError, "History index hash changed"):
            self.execute(fetch)
        fetch.assert_not_called()
        self.assertEqual(worker._ledger(self.root, worker.load(self.root / "continuous_plan.json")), [])

    def test_bad_schema_and_external_identity_rejected_before_freeze(self):
        self.freeze(1)
        path = self.base / "bad.json"
        worker.write(self.base, path.name, {"schema": "unrecognized", "records": [], "parent": None})
        with self.assertRaisesRegex(ValueError, "history index schema"):
            self.bind_history({"path": str(path), "sha256": worker.sha_file(path)})
        self.assertFalse(self.root.exists())
        binding = self.index([self.past(url="https://example.test/foreign/")], name="foreign.json")
        with self.assertRaises(ValueError):
            self.bind_history(binding)
        self.assertFalse(self.root.exists())

    def test_identical_chained_sample_collapses_conflicting_hash_rejected(self):
        record = self.past()
        parent = self.index([record])
        same = self.index([record], name="same.json", parent=parent)
        self.assertEqual(worker.load_history_index(same), [{**record, "url": worker.normalize_url(record["url"])}])
        bad = self.index([{**record, "snapshot_sha256": "c" * 64}], name="conflict.json", parent=parent)
        with self.assertRaisesRegex(ValueError, "Conflicting history evidence"):
            worker.load_history_index(bad)

    def test_history_does_not_relax_genuine_source_loss_gate(self):
        self.freeze(3)
        self.bind_history(self.index([self.past(canonical=self.rows[0]["url"])]))
        fetch = Mock(side_effect=lambda u, t, **k: {**fixtures.response(u, t), "text": fixtures.page(u, body_extra='<div class="ad">Lost real prose.</div>')})
        result = self.execute(fetch)
        self.assertEqual(result["status"], "halted_no_automatic_resume")
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(worker.load(self.root / "safety_halt.json")["reason"], "two_consecutive_same_family_anomalies")


if __name__ == "__main__":
    unittest.main()

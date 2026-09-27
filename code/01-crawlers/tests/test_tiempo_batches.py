"""Real pilot executor with synthetic offline transport, temporary Media roots."""
from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawler_core import tiempo_batches as batches
from crawler_core import tiempo_pilot as pilot
from crawler_core.tiempo_review import fields_digest


def response(url, timeout, **kwargs):
    return {"status": 200, "final_url": url, "content_type": "text/html", "error": None,
            "text": "<h1>News</h1><article>A short but genuine report.</article>"}


def parser(html, *, url, source_id):
    return {"title": "News", "summary": None, "main_text": "A short but genuine report.",
            "authors": None, "date_published": "2025-01-01T12:00:00", "canonical_url": url,
            "publication_date_source": "visible_article_timestamp", "publication_date_evidence": "2025-01-01 12:00"}


class TiempoBatchTests(unittest.TestCase):
    def test_confirmed_empty_source_title_stays_error_and_is_not_manual_review(self):
        self.freeze(8, 8)
        def empty_title(html, *, url, source_id):
            return {**parser(html, url=url, source_id=source_id), "title": None,
                    "source_title_status": "confirmed_source_empty",
                    "source_title_evidence": json.dumps({"recognized_empty_h1": True, "all_title_channels_empty": True})}
        state = self.run_plan(parser=empty_title)
        self.assertEqual(state["status"], "awaiting_review")
        summary = batches.inspect_batch(self.root, self.plan["batches"][0])
        self.assertEqual(summary["successful_url_rows"], 0)
        self.assertEqual(summary["error_groups"], {"source_gap": 8})
        self.assertEqual(summary["manual_review_counts"]["not_reviewed"], 8)
        self.assertTrue(all(r["error"] == "missing_title" and r["title"] is None for r in summary["rows"]))

    def test_source_empty_title_classification_requires_complete_narrow_evidence(self):
        valid = {**parser("", url="https://www.tiempo.com.mx/local/x/", source_id="tiempo"),
                 "title": None, "status": 200, "qa_status": "error", "error": "missing_title",
                 "source_title_status": "confirmed_source_empty",
                 "source_title_evidence": json.dumps({"recognized_empty_h1": True, "all_title_channels_empty": True})}
        self.assertEqual(batches.error_group(valid), "source_gap")
        changes = [{"source_title_status": None}, {"source_title_evidence": "bad"},
                   {"source_title_evidence": "[]"}, {"source_title_evidence": "{}"},
                   {"source_title_evidence": '{"recognized_empty_h1":1,"all_title_channels_empty":true}'},
                   {"source_title_evidence": '{"recognized_empty_h1":true,"all_title_channels_empty":false}'},
                   {"title": "A real title"}, {"main_text": None}, {"date_published": None},
                   {"canonical_url": None}, {"publication_date_source": None},
                   {"date_conflict": "conflict"}, {"source_specific_error": "unknown_template"},
                   {"error": "missing_main_text"}, {"status": 201}]
        for change in changes:
            with self.subTest(change=change):
                self.assertEqual(batches.error_group({**valid, **change}), "system_quality")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.media = self.base / "Media"
        self.root = self.media / "data/00-newspaper_data/crawler/pilots/tests"
        self.root.mkdir(parents=True)
        (self.root / "Kevin_NOTE.md").write_text("# Kevin offline test\n")
        self.input = self.base / "queue.csv"
        self.fetcher = Mock(side_effect=response)
        self.sleep = patch("time.sleep", return_value=None).start()
        self.addCleanup(patch.stopall)

    def freeze(self, n=5, batch_size=3, **kwargs):
        with self.input.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["sample_id", "url", "expected_year", "selection_reason", "expected_kind"])
            writer.writeheader()
            for i in range(n):
                writer.writerow(dict(sample_id=f"T{i:03d}", url=f"https://www.tiempo.com.mx/local/news-{i}/",
                                     expected_year=2025, selection_reason="offline test", expected_kind="candidate"))
        self.plan = batches.freeze_plan(self.input, self.root, self.media, batch_size=batch_size,
                                        min_reviewed_per_batch=1, min_free_bytes=1, **kwargs)
        return self.plan

    def run_plan(self, **kwargs):
        options = {"fetcher": self.fetcher, "parser": parser}
        options.update(kwargs)
        return batches.run_batches(self.root, self.media, **options)

    def approve(self, ordinal=0, checked=1, result="PASS"):
        batch = self.plan["batches"][ordinal]
        directory = self.root / "batches" / batch["batch_id"]
        summary = batches.inspect_batch(self.root, batch)
        records = [{"sample_id": r["sample_id"], "snapshot_sha256": r["snapshot_sha256"],
                    "fields_sha256": fields_digest(r), "reviewer": "Kevin", "reviewed_at": "2026-09-26T12:00:00-04:00",
                    "review_result": result, "source_quality_issue": None, "review_note": "Independent synthetic fixture check"}
                   for r in summary["rows"][:checked]]
        (directory / "review_annotations.json").write_text(json.dumps({"format_version": 1, "annotations": records}))
        pilot.run_pilot(self.root / batch["input_path"], directory, self.media, export_only=True)
        summary = batches.inspect_batch(self.root, batch)
        approval = dict(format_version=1, decision="proceed", plan_sha256=self.plan["plan_sha256"],
                        batch_id=batch["batch_id"], input_sha256=batch["input_sha256"], evidence_sha256=summary["evidence_sha256"],
                        reviewer="Kevin", reviewed_at="2026-09-26T12:00:00-04:00", note="Checked frozen synthetic fixtures",
                        reviewed_sample_ids=[r["sample_id"] for r in records], accepted_error_groups=sorted(summary["error_groups"]))
        path = self.root / "approvals" / (batch["batch_id"] + ".json")
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(approval))
        return path

    def resolve(self, state):
        sha = state["active_halt_sha256"]
        path = self.root / "resume_authorizations" / (sha + ".json")
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(dict(plan_sha256=self.plan["plan_sha256"], halt_sha256=sha, decision="resume",
                                       reviewer="Kevin", reviewed_at="2026-09-26T12:00:00-04:00", note="Diagnosed synthetic failure")))

    def test_frozen_queue_batches_and_idempotence(self):
        self.freeze(161, 80)
        self.assertEqual([b["row_count"] for b in self.plan["batches"]], [80, 80, 1])
        self.assertEqual(batches.load_plan(self.root), self.plan)
        self.assertEqual(batches.freeze_plan(self.input, self.root, self.media, batch_size=80,
                         min_reviewed_per_batch=1, min_free_bytes=1), self.plan)
        self.assertFalse(self.fetcher.called)

    def test_global_duplicates_and_non_tiempo_rejected_before_freeze(self):
        for content in ["X,https://www.tiempo.com.mx/a/", "X,https://example.com/a/"]:
            with self.subTest(content=content):
                self.input.write_text("sample_id,url,expected_year,selection_reason,expected_kind\n" + content + ",2025,x,x\n" + content + ",2025,x,x\n")
                with self.assertRaises(pilot.PilotError):
                    batches.freeze_plan(self.input, self.root, self.media)
        self.assertFalse((self.root / "plan.json").exists())

    def test_changed_input_and_plan_rejected(self):
        self.freeze()
        path = self.root / self.plan["batches"][0]["input_path"]
        path.write_text(path.read_text().replace("offline test", "changed"))
        with self.assertRaises(batches.BatchError):
            self.run_plan()
        self.assertFalse(self.fetcher.called)

    def test_cap_and_nonfinite_settings(self):
        self.freeze()
        for n in [0, 11, True]:
            with self.subTest(n=n), self.assertRaises(batches.BatchError):
                self.run_plan(max_batches=n)
        with self.assertRaises(batches.BatchError):
            batches.freeze_plan(self.input, self.root, self.media, batch_size=81)
        with self.assertRaises(batches.BatchError):
            batches.freeze_plan(self.input, self.root, self.media, pause_seconds=float("nan"))

    def test_first_gate_stops_even_max_ten_and_unreviewed_not_pass(self):
        self.freeze()
        state = self.run_plan(max_batches=10)
        self.assertEqual(state["status"], "awaiting_review")
        self.assertEqual(self.fetcher.call_count, 3)
        self.assertEqual(state["batches"][0]["manual_review_counts"]["not_reviewed"], 3)
        again = self.run_plan(max_batches=10)
        self.assertEqual(again["status"], "awaiting_review")
        self.assertEqual(self.fetcher.call_count, 3)

    def test_spot_check_gate_proceeds_preserving_unreviewed_rows(self):
        self.freeze()
        self.run_plan()
        self.approve()
        state = self.run_plan(max_batches=1)
        self.assertEqual(self.fetcher.call_count, 5)
        self.assertEqual(state["batches"][0]["review_status"], "partially_reviewed")
        self.assertEqual(state["batches"][0]["manual_review_counts"]["not_reviewed"], 2)
        self.approve(1)
        self.assertEqual(self.run_plan()["status"], "all_batches_operator_accepted")
        self.assertEqual(self.fetcher.call_count, 5)

    def test_stale_gate_and_manual_fail_cannot_proceed(self):
        self.freeze()
        self.run_plan()
        path = self.approve()
        record = json.loads(path.read_text())
        record["evidence_sha256"] = "0" * 64
        path.write_text(json.dumps(record))
        with self.assertRaises(batches.BatchError):
            self.run_plan()
        self.approve(result="FAIL")
        with self.assertRaises(batches.BatchError):
            self.run_plan()
        self.assertEqual(self.fetcher.call_count, 3)

    def test_immediate_http_stops_are_durable_and_no_automatic_retry(self):
        for http_status in [403, 429, 503]:
            with self.subTest(http_status=http_status):
                # Separate temporary root per response.
                if (self.root / "plan.json").exists():
                    self.root = self.root.parent / f"http-{http_status}"
                    self.root.mkdir()
                    (self.root / "Kevin_NOTE.md").write_text("Kevin")
                self.freeze()
                fetch = Mock(side_effect=lambda u, t, **kw: {**response(u, t), "status": http_status})
                state = self.run_plan(fetcher=fetch)
                self.assertEqual((state["status"], fetch.call_count), ("halted", 1))
                self.assertEqual(state["batches"][0]["result_rows"], 1)
                (self.root / "state.json").unlink()  # Durable safety cursor survives status loss.
                self.assertEqual(self.run_plan(fetcher=fetch)["status"], "halted")
                self.assertEqual(fetch.call_count, 1)
                self.resolve(state)
                resumed = self.run_plan()
                self.assertEqual(resumed["status"], "awaiting_review")
                self.assertEqual(resumed["batches"][0]["successful_url_rows"], 2)

    def test_disk_reserve_blocks_before_transport_and_resumes(self):
        self.freeze()
        with patch.object(batches.shutil, "disk_usage", return_value=Mock(free=0)):
            state = self.run_plan()
        self.assertEqual(state["status"], "halted")
        self.assertFalse(self.fetcher.called)
        self.assertEqual(state["batches"][0]["transport_calls_started"], 0)
        self.assertEqual(state["batches"][0]["pilot_fetch_entries"], 1)
        self.resolve(state)
        self.assertEqual(self.run_plan()["batches"][0]["result_rows"], 3)
        self.assertEqual(self.fetcher.call_count, 3)

    def test_system_error_threshold_stops_but_soft_error_queue_does_not(self):
        self.freeze(10, 10)
        bad = lambda text, **kw: {**parser(text, **kw), "title": None}
        state = self.run_plan(parser=bad)
        self.assertEqual(state["status"], "halted")
        self.assertEqual(self.fetcher.call_count, 3)
        self.assertEqual(state["batches"][0]["error_groups"], {"system_quality": 3})
        retry = batches.retry_queue(self.root, ["system_quality"])
        with retry.open() as f:
            self.assertEqual(len(list(csv.DictReader(f))), 3)
        self.assertEqual(self.fetcher.call_count, 3)
        self.resolve(state)
        soft = lambda text, **kw: {**parser(text, **kw), "source_specific_error": "soft_error_page"}
        state = self.run_plan(parser=soft)
        self.assertEqual(state["status"], "awaiting_review")
        self.assertEqual(state["batches"][0]["error_groups"], {"system_quality": 3, "source_gap": 7})

    def test_fraction_threshold_with_nonconsecutive_errors(self):
        self.freeze(10, 10, max_system_error_fraction=0.25, error_fraction_min_results=4)
        count = [0]
        def mixed(text, **kw):
            count[0] += 1
            result = parser(text, **kw)
            if count[0] % 2 == 0:
                result["title"] = None
            return result
        state = self.run_plan(parser=mixed)
        self.assertEqual(state["status"], "halted")
        self.assertEqual(self.fetcher.call_count, 4)

    def test_real_keyboard_interrupt_resumes_without_repeat(self):
        self.freeze()
        count = [0]
        def interrupted(url, timeout, **kw):
            count[0] += 1
            if count[0] == 2:
                raise KeyboardInterrupt()
            return response(url, timeout, **kw)
        state = self.run_plan(fetcher=interrupted)
        self.assertEqual(state["status"], "interrupted")
        self.assertEqual(state["batches"][0]["result_rows"], 1)
        state = self.run_plan()
        self.assertEqual(state["status"], "awaiting_review")
        self.assertEqual(self.fetcher.call_count, 2)

    def test_missing_db_corrupt_snapshot_and_export_fail_before_network(self):
        self.freeze()
        self.run_plan()
        batch = self.root / "batches/batch_000001"
        export = batch / "articles.csv"
        original = export.read_bytes()
        export.write_bytes(b"bad")
        with self.assertRaises(batches.BatchError):
            self.run_plan()
        export.write_bytes(original)
        snapshot = next((batch / "raw_html").rglob("*.html"))
        snapshot.write_bytes(b"bad")
        with self.assertRaises(pilot.PilotError):
            self.run_plan()
        (batch / "pilot.sqlite").unlink()
        with self.assertRaises(batches.BatchError):
            self.run_plan()
        self.assertEqual(self.fetcher.call_count, 3)

    def test_minimum_delay_applied_to_every_request(self):
        self.freeze()
        clock = [1000.0]
        self.sleep.side_effect = lambda seconds: clock.__setitem__(0, clock[0] + seconds)
        with patch("time.time", side_effect=lambda: clock[0]):
            self.run_plan()
        self.assertEqual(self.sleep.call_count, 3)
        self.assertTrue(all(call.args == (1.0,) for call in self.sleep.call_args_list))

    def test_restart_after_http_stop_fills_interval_only(self):
        self.freeze()
        clock = [1000.0]
        self.sleep.side_effect = lambda seconds: clock.__setitem__(0, clock[0] + seconds)
        denied = Mock(side_effect=lambda u, t, **kw: {**response(u, t), "status": 429})
        with patch("time.time", side_effect=lambda: clock[0]):
            state = self.run_plan(fetcher=denied)
            self.assertFalse(self.sleep.called)
            self.resolve(state)
            self.run_plan()
        self.assertEqual(self.sleep.call_count, 3)  # transition gap + two post-commit pauses

    def test_format_and_date_errors_stop_on_first_result(self):
        self.freeze()
        invalid = lambda text, **kw: {**parser(text, **kw), "source_specific_error": "conflicting_publication_dates"}
        state = self.run_plan(parser=invalid)
        self.assertEqual(state["status"], "halted")
        self.assertEqual(self.fetcher.call_count, 1)
        event = json.loads((self.root / "halts" / (state["active_halt_sha256"] + ".json")).read_text())
        self.assertEqual(event["reason"], "format_or_date_error")

    def test_pristine_pilot_initialization_can_resume(self):
        self.freeze()
        batch = self.plan["batches"][0]
        items, sha = pilot.load_input(self.root / batch["input_path"])
        directory = self.root / "batches" / batch["batch_id"]
        (directory / "manifest.json").write_text(json.dumps(dict(format_version=1, source_id="tiempo",
            input_sha256=sha, input_name="sample_manifest.csv", items=items, database_initialized=False)))
        self.assertEqual(self.run_plan()["status"], "awaiting_review")
        self.assertEqual(self.fetcher.call_count, 3)

    def test_program_version_change_blocks_before_requests(self):
        self.freeze()
        with patch.object(batches, "_program_hashes", return_value={}):
            with self.assertRaises(batches.BatchError):
                self.run_plan()
        self.assertFalse(self.fetcher.called)

    def test_malformed_clock_rejected_before_any_pilot_attempt(self):
        self.freeze()
        path = self.root / "transport_clock.json"
        for content in ('{"plan_sha256":', '[]', '{}'):
            with self.subTest(content=content):
                path.write_text(content)
                with self.assertRaises(batches.BatchError):
                    self.run_plan()
                self.assertFalse(self.fetcher.called)
                self.assertFalse((self.root / "batches/batch_000001/pilot.sqlite").exists())
                self.assertEqual(path.read_text(), content)

    def test_clock_corruption_during_run_halts_without_transport(self):
        self.freeze()
        clock_path = self.root / "transport_clock.json"
        def corrupt_during_pause(seconds):
            clock_path.write_text('{')
        self.sleep.side_effect = corrupt_during_pause
        state = self.run_plan()
        self.assertEqual(state["status"], "halted")
        self.assertEqual(self.fetcher.call_count, 1)
        self.assertEqual(state["batches"][0]["result_rows"], 1)
        self.assertEqual(clock_path.read_text(), '{')

    def test_committed_date_error_replayed_after_pre_callback_interrupt(self):
        self.freeze(5, 5)
        invalid = lambda text, **kw: {**parser(text, **kw), "source_specific_error": "conflicting_publication_dates"}
        def crash(*args, **kwargs):
            if args and str(args[0]).startswith("Saved T000 "):
                raise KeyboardInterrupt()
        with patch("builtins.print", side_effect=crash):
            state = self.run_plan(parser=invalid)
        self.assertEqual(state["status"], "interrupted")
        self.assertEqual(self.fetcher.call_count, 1)
        state = self.run_plan()
        self.assertEqual(state["status"], "halted")
        self.assertEqual(self.fetcher.call_count, 1)
        self.resolve(state)
        state = self.run_plan()
        self.assertEqual(state["status"], "awaiting_review")
        self.assertEqual(self.fetcher.call_count, 5)
        cursor = json.loads((self.root / "halt_cursor.json").read_text())
        resolution = cursor["resolutions"]["batch_000001"]
        self.assertEqual(resolution["last_sample_id"], "T000")
        self.assertEqual(resolution["last_ordinal"], 0)
        self.assertEqual(len(resolution["row_keys"]), 1)

    def test_system_threshold_not_reset_by_pre_callback_interrupt(self):
        self.freeze(5, 5)
        invalid = lambda text, **kw: {**parser(text, **kw), "title": None}
        def crash(*args, **kwargs):
            if args and str(args[0]).startswith("Saved T001 "):
                raise KeyboardInterrupt()
        with patch("builtins.print", side_effect=crash):
            state = self.run_plan(parser=invalid)
        self.assertEqual(state["status"], "interrupted")
        self.assertEqual(self.fetcher.call_count, 2)
        state = self.run_plan(parser=invalid)
        self.assertEqual(state["status"], "halted")
        self.assertEqual(self.fetcher.call_count, 3)
        self.assertEqual(state["batches"][0]["error_groups"], {"system_quality": 3})


if __name__ == "__main__":
    unittest.main()

"""Offline safety/resume tests. No live websites or shared data are accessed."""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import pandas as pd

CRAWLER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CRAWLER_DIR))
from crawler_core.tiempo_pilot import PilotError, load_input, run_pilot  # noqa: E402


def response(url, timeout, **kwargs):
    return {"status": 200, "final_url": url, "content_type": "text/html; charset=utf-8", "error": pd.NA,
            "text": "<html><h1>Una noticia</h1><article>Una noticia breve y real.</article></html>"}


def parser(html, *, url, source_id):
    return {"title": "Una noticia", "main_text": "Una noticia breve y real.", "summary": None, "authors": pd.NA,
            "date_published": "2024-06-01T12:00:00-06:00", "date": "2024-06-01T12:00:00-06:00", "date_modified": None,
            "publication_date_source": "visible_article_timestamp", "publication_date_evidence": "1 de junio de 2024",
            "canonical_url": url, "date_conflict": None}


class TiempoPilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.media = self.base / "Media"
        self.run_dir = self.media / "data/00-newspaper_data/crawler/pilots/unit-test"
        self.run_dir.mkdir(parents=True)
        (self.run_dir / "Kevin_NOTE.md").write_text("# Kevin pilot test\n", encoding="utf-8")
        self.input = self.base / "sample.csv"
        self.write_input(2)

    def write_input(self, n, *, duplicate=False, headers=None):
        names = headers or ["sample_id", "url", "expected_year", "selection_reason", "expected_kind"]
        with self.input.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=names)
            writer.writeheader()
            for i in range(n):
                row = {"sample_id": f"P{i+1:03d}", "url": f"https://www.tiempo.com.mx/local/article-{0 if duplicate else i}/",
                       "expected_year": 1999, "selection_reason": "deliberately not an extraction oracle", "expected_kind": "article_candidate",
                       "sample_role": "article_candidate", "stratum": "sample stratum"}
                writer.writerow({k: row[k] for k in names})

    def execute(self, **kwargs):
        options = dict(pause_seconds=0, fetcher=Mock(side_effect=response), parser=parser)
        options.update(kwargs)
        return run_pilot(self.input, self.run_dir, self.media, **options)

    def rows(self, table="articles"):
        with sqlite3.connect(self.run_dir / "pilot.sqlite") as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(f"SELECT * FROM {table}")]

    def test_duplicate_and_more_than_eighty_urls_rejected_before_output(self):
        for n, duplicate in [(2, True), (81, False)]:
            self.write_input(n, duplicate=duplicate)
            fetch = Mock()
            with self.assertRaises(PilotError):
                self.execute(fetcher=fetch)
            fetch.assert_not_called()
            self.assertFalse((self.run_dir / "pilot.sqlite").exists())

    def test_bom_extra_columns_and_manifest_alias_columns(self):
        self.write_input(1, headers=["sample_id", "url", "expected_year", "sample_role", "stratum"])
        rows, _ = load_input(self.input)
        self.assertEqual(rows[0]["expected_kind"], "article_candidate")
        self.assertEqual(rows[0]["selection_reason"], "sample stratum")

    def test_resume_skips_success_and_error_and_preserves_null_short_article(self):
        fetch = Mock(side_effect=[response("https://www.tiempo.com.mx/local/article-0/", 1),
                                  {"status": 404, "content_type": "text/html", "text": "<html>Missing</html>", "error": None}])
        initial = self.execute(fetcher=fetch)
        self.assertEqual(initial["article_rows"], 1)
        resumed_fetch = Mock(side_effect=AssertionError("resume made a request"))
        resumed = self.execute(fetcher=resumed_fetch)
        resumed_fetch.assert_not_called()
        self.assertEqual(resumed["network_fetch_calls_started"], 2)
        self.assertEqual(resumed["error_results"], 1)
        frame = pd.read_parquet(self.run_dir / "articles.parquet")
        self.assertEqual(frame.iloc[0]["date_published"], "2024-06-01T12:00:00-06:00")
        self.assertLess(len(frame.iloc[0]["main_text"]), 500)
        self.assertTrue(pd.isna(frame.iloc[0]["authors"]))

    def test_interrupt_after_committed_row_preserves_it_and_resume_only_fetches_missing(self):
        def stop_after_first(*args):
            raise KeyboardInterrupt
        first_fetch = Mock(side_effect=response)
        first = self.execute(fetcher=first_fetch, after_commit=stop_after_first)
        self.assertTrue(first["interrupted"])
        self.assertEqual(len(self.rows()), 1)
        second_fetch = Mock(side_effect=response)
        resumed = self.execute(fetcher=second_fetch)
        self.assertEqual(second_fetch.call_count, 1)
        self.assertTrue(second_fetch.call_args.args[0].endswith("article-1/"))
        self.assertEqual(resumed["result_rows"], 2)

    def test_complete_snapshot_after_interrupt_recovers_without_new_fetch(self):
        self.write_input(1)
        def stop_after_snapshot(*args):
            raise KeyboardInterrupt
        first = self.execute(after_snapshot=stop_after_snapshot)
        self.assertTrue(first["interrupted"])
        self.assertEqual(len(self.rows()), 0)
        fetch = Mock(side_effect=AssertionError("complete snapshot should be reused"))
        resumed = self.execute(fetcher=fetch)
        fetch.assert_not_called()
        self.assertEqual(resumed["network_fetch_calls_started"], 1)
        self.assertEqual(self.rows("fetch_attempts")[0]["cached_recovery"], 1)
        events = [json.loads(line) for line in (self.run_dir / "attempts.jsonl").read_text().splitlines()]
        self.assertEqual(sum(e.get("network_request", False) for e in events), 1)

    def test_partial_transport_snapshot_is_not_used_as_a_complete_response(self):
        self.write_input(1)
        partial = response("https://www.tiempo.com.mx/local/article-0/", 1)
        partial["error"] = "curl_exit_18: partial file"
        def stop_after_snapshot(*args):
            raise KeyboardInterrupt
        self.execute(fetcher=Mock(return_value=partial), after_snapshot=stop_after_snapshot)
        fetch = Mock(side_effect=response)
        resumed = self.execute(fetcher=fetch)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(resumed["article_rows"], 1)
        self.assertEqual(resumed["network_fetch_calls_started"], 2)

    def test_failed_offline_reparse_cannot_overwrite_success(self):
        self.write_input(1)
        self.execute()
        original = self.rows()[0]["payload_json"]
        bad_parser = lambda *a, **k: {"source_specific_error": "soft_error_page"}
        fetch = Mock(side_effect=AssertionError("offline reparse must not fetch"))
        final = self.execute(reparse_cache=True, parser=bad_parser, fetcher=fetch)
        fetch.assert_not_called()
        self.assertEqual(final["article_rows"], 1)
        self.assertEqual(self.rows()[0]["payload_json"], original)
        self.assertEqual(self.rows("fetch_attempts")[-1]["retained_success"], 1)
        self.assertTrue(list((self.run_dir / "backups").glob("*/pilot.sqlite")))
        self.assertIn("Kevin: Backup before offline cache reparse", (self.run_dir / "Kevin_NOTE.md").read_text())

    def test_retry_errors_only_and_backup_precedes_retry(self):
        fetch = Mock(side_effect=[response("https://www.tiempo.com.mx/local/article-0/", 1),
                                  {"status": 503, "content_type": "text/html", "text": "<html>Down</html>", "error": None}])
        self.execute(fetcher=fetch)
        def retry(url, *args, **kwargs):
            self.assertTrue(list((self.run_dir / "backups").glob("*/pilot.sqlite")))
            return response(url, *args, **kwargs)
        retried = Mock(side_effect=retry)
        result = self.execute(fetcher=retried, retry_errors=True)
        self.assertEqual(retried.call_count, 1)
        self.assertTrue(retried.call_args.args[0].endswith("article-1/"))
        self.assertEqual(result["error_results"], 0)

    def test_manifest_change_refused_except_metadata_only_offline_reparse(self):
        self.write_input(1)
        self.execute()
        self.input.write_text(self.input.read_text(encoding="utf-8-sig").replace("1999", "2000"), encoding="utf-8")
        fetch = Mock()
        with self.assertRaisesRegex(PilotError, "manifest changed"):
            self.execute(fetcher=fetch)
        fetch.assert_not_called()
        self.execute(fetcher=fetch, reparse_cache=True)
        fetch.assert_not_called()
        self.assertEqual(self.rows()[0]["expected_year"], "2000")
        self.assertEqual(self.rows()[0]["date_published"], "2024-06-01T12:00:00-06:00")

    def test_shared_run_dir_missing_note_and_symlink_outputs_are_rejected(self):
        shared = self.media / "data/00-newspaper_data/crawler/articles_sitemap"
        shared.mkdir()
        (shared / "Kevin_NOTE.md").write_text("Kevin")
        with self.assertRaises(PilotError):
            run_pilot(self.input, shared, self.media, fetcher=Mock(), parser=parser)
        (self.run_dir / "Kevin_NOTE.md").unlink()
        with self.assertRaises(PilotError):
            self.execute()
        (self.run_dir / "Kevin_NOTE.md").write_text("Kevin")
        external = self.base / "do-not-change.csv"
        external.write_text("original")
        (self.run_dir / "articles.csv").symlink_to(external)
        with self.assertRaises(PilotError):
            self.execute()
        self.assertEqual(external.read_text(), "original")

    def test_unbound_outputs_rejected_and_changed_bound_exports_backed_up(self):
        target = self.run_dir / "articles.csv"
        target.write_text("unrelated")
        with self.assertRaises(PilotError):
            self.execute()
        self.assertEqual(target.read_text(), "unrelated")
        target.unlink()
        self.execute()
        target.write_text("human-edited pilot export")
        fetch = Mock()
        self.execute(export_only=True, fetcher=fetch)
        fetch.assert_not_called()
        backups = list((self.run_dir / "backups").glob("*/articles.csv"))
        self.assertTrue(any(p.read_text() == "human-edited pilot export" for p in backups))

    def test_transport_nonhtml_soft_error_and_missing_real_date_rejected(self):
        self.write_input(1)
        for response_override, parser_override, expected in [
            ({"error": "curl_exit_60"}, parser, "transport_error"),
            ({"content_type": "application/json"}, parser, "non_html_response"),
            ({}, lambda *a, **k: {"source_specific_error": "soft_error_page"}, "soft_error_page"),
            ({}, lambda *a, **k: {"title": "Title", "main_text": "Body", "date_published": "2024-01-01"}, "missing_verified_publication_date"),
        ]:
            with self.subTest(expected=expected):
                folder = self.run_dir.parent / expected
                folder.mkdir()
                (folder / "Kevin_NOTE.md").write_text("Kevin")
                fetched = response("https://www.tiempo.com.mx/local/article-0/", 1)
                fetched.update(response_override)
                result = run_pilot(self.input, folder, self.media, pause_seconds=0, fetcher=Mock(return_value=fetched), parser=parser_override)
                self.assertEqual(result["article_rows"], 0)
                frame = pd.read_parquet(folder / "attempts.parquet")
                self.assertIn(expected, frame.iloc[0]["error"])

    def test_canonical_aliases_only_merge_identical_content(self):
        def aliases(html, *, url, source_id):
            return {**parser(html, url=url, source_id=source_id), "canonical_url": "https://www.tiempo.com.mx/local/same-story/"}
        result = self.execute(parser=aliases)
        self.assertEqual(result["article_rows"], 1)
        self.assertEqual(result["canonical_alias_rows"], 1)
        self.assertEqual(len(pd.read_parquet(self.run_dir / "attempts.parquet")), 2)
        def collision(html, *, url, source_id):
            return {**aliases(html, url=url, source_id=source_id), "main_text": "Different body " + url}
        final = self.execute(parser=collision, reparse_cache=True)
        self.assertEqual(final["article_rows"], 2)
        self.assertEqual(final["canonical_collision_groups"], 1)
        self.assertEqual(set(pd.read_parquet(self.run_dir / "articles.parquet")["canonical_dedup_status"]), {"collision_review"})

    def test_invalid_double_slash_canonical_does_not_merge_articles(self):
        invalid = lambda html, **kwargs: {**parser(html, **kwargs), "canonical_url": "https://www.tiempo.com.mx/local//"}
        self.assertEqual(self.execute(parser=invalid)["article_rows"], 2)


if __name__ == "__main__":
    unittest.main()

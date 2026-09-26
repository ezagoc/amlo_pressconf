"""Offline manual-review binding and failure-mode tests; no project crawler runs."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawler_core.tiempo_review import (  # noqa: E402
    ReviewAnnotationError, apply_reviews, fields_digest,
)


class TiempoReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "review_annotations.json"
        self.row = {
            "sample_id": "P003", "url": "https://www.tiempo.com.mx/noticia/example/",
            "snapshot_sha256": "a" * 64, "title": "Título",
            "summary": None, "main_text": "First paragraph.\nLast paragraph.",
            "authors": "Redacción", "date_published": "2018-08-18T20:15:40",
            "canonical_url": "https://www.tiempo.com.mx/deportes/example/",
            "media_embeds": '["https://www.youtube.com/embed/example"]',
        }
        self.entry = {
            "sample_id": "P003", "snapshot_sha256": "a" * 64,
            "fields_sha256": fields_digest(self.row), "reviewer": "Kevin",
            "reviewed_at": "2026-09-26T20:00:00+00:00", "review_result": "PASS_SOURCE_GAP_RECORDED",
            "source_quality_issue": "source_fragment_suspected",
            "review_note": "Source appears fragmentary; do not invent missing text.",
        }

    def write(self, entries=None, **extra):
        data = {"format_version": 1, "annotations": entries if entries is not None else [self.entry], **extra}
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_canonical_digest_and_null_media_equivalence(self):
        empty = dict.fromkeys(("title", "summary", "main_text", "authors", "date_published", "canonical_url"))
        expected = hashlib.sha256(json.dumps({**empty, "media_embeds": []}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(fields_digest({}), expected)
        self.assertEqual(fields_digest({"title": "", "summary": float("nan"), "media_embeds": "null"}), expected)
        row = dict(self.row, media_embeds=json.loads(self.row["media_embeds"]))
        self.assertEqual(fields_digest(row), fields_digest(self.row))
        self.assertEqual(fields_digest(dict(self.row, unrelated="metadata")), fields_digest(self.row))

    def test_each_reviewed_field_change_invalidates_review(self):
        self.write()
        for field in ("title", "summary", "main_text", "authors", "date_published", "canonical_url", "media_embeds"):
            with self.subTest(field=field):
                changed = dict(self.row, **{field: '["https://different.example/"]' if field == "media_embeds" else "changed"})
                rows, meta = apply_reviews([changed], self.path)
                self.assertEqual(rows[0]["manual_review_status"], "stale")
                self.assertIsNone(rows[0]["manual_review_result"])
                self.assertEqual(rows[0]["prior_review_result"], "PASS_SOURCE_GAP_RECORDED")
                self.assertEqual(rows[0]["source_quality_issue"], "source_fragment_suspected")
                self.assertEqual(json.loads(rows[0]["review_stale_reasons"]), ["extracted_fields_changed"])
                self.assertEqual(meta["status_counts"]["stale"], 1)

    def test_matching_annotation_is_reviewed_and_input_is_not_modified(self):
        self.write(author="Kevin", fields_digest_version=1)
        before = deepcopy(self.row)
        rows, meta = apply_reviews([self.row], self.path)
        self.assertEqual(self.row, before)
        self.assertEqual(rows[0]["manual_review_status"], "reviewed")
        self.assertEqual(rows[0]["manual_review_result"], "PASS_SOURCE_GAP_RECORDED")
        self.assertEqual(meta["status_counts"], {"reviewed": 1, "stale": 0, "not_reviewed": 0})
        self.assertEqual(meta["annotation_file_sha256"], hashlib.sha256(self.path.read_bytes()).hexdigest())
        reapplied, same_meta = apply_reviews(rows, self.path)
        self.assertEqual(reapplied, rows)
        self.assertEqual(same_meta, meta)

    def test_snapshot_change_and_optional_url_change_mark_stale(self):
        self.entry["url"] = self.row["url"]
        self.write()
        changed = dict(self.row, snapshot_sha256="b" * 64, url="https://www.tiempo.com.mx/different/")
        rows, _ = apply_reviews([changed], self.path)
        self.assertEqual(json.loads(rows[0]["review_stale_reasons"]), ["snapshot_changed", "requested_url_changed"])
        self.assertIsNone(rows[0]["manual_review_result"])

    def test_nonempty_whitespace_change_and_media_order_are_changes(self):
        self.assertNotEqual(fields_digest(self.row), fields_digest(dict(self.row, main_text=self.row["main_text"] + " ")))
        self.assertNotEqual(fields_digest(dict(self.row, media_embeds=["a", "b"])), fields_digest(dict(self.row, media_embeds=["b", "a"])))

    def test_absent_sidecar_marks_not_reviewed_and_keeps_warning_and_prior_evidence(self):
        row = dict(self.row, source_quality_issue="source_fragment_suspected", manual_review_result="PASS", manual_review_note="Previous finding.")
        rows, meta = apply_reviews([row], self.path)
        self.assertFalse(meta["annotation_file_present"])
        self.assertEqual(rows[0]["manual_review_status"], "not_reviewed")
        self.assertIsNone(rows[0]["manual_review_result"])
        self.assertEqual(rows[0]["source_quality_issue"], "source_fragment_suspected")
        self.assertEqual(rows[0]["prior_review_result"], "PASS")
        self.assertEqual(rows[0]["prior_review_note"], "Previous finding.")
        self.assertEqual(rows[0]["review_missing_reason"], "sidecar_absent")
        again, _ = apply_reviews(rows, self.path)
        self.assertEqual(again, rows)

    def test_missing_sample_does_not_inherit_another_annotation(self):
        self.write()
        rows, meta = apply_reviews([dict(self.row, sample_id="P004")], self.path)
        self.assertEqual(rows[0]["manual_review_status"], "not_reviewed")
        self.assertEqual(rows[0]["review_missing_reason"], "no_annotation_for_sample")
        self.assertEqual(meta["unused_annotation_ids"], ["P003"])
        self.assertEqual(meta["annotation_sample_ids"], ["P003"])

    def test_stale_null_warning_cannot_clear_existing_warning(self):
        self.entry["source_quality_issue"] = None
        self.write()
        row = dict(self.row, main_text="Changed", source_quality_issue="known_source_gap")
        out, _ = apply_reviews([row], self.path)
        self.assertEqual(out[0]["source_quality_issue"], "known_source_gap")
        self.assertEqual(out[0]["manual_review_status"], "stale")

    def test_different_old_warning_survives_and_merge_is_idempotent(self):
        self.write()
        row = dict(self.row, main_text="Changed", source_quality_issue="another_source_gap")
        out, _ = apply_reviews([row], self.path)
        self.assertEqual(out[0]["source_quality_issue"], "source_fragment_suspected")
        self.assertEqual(out[0]["prior_source_quality_issue"], "another_source_gap")
        again, _ = apply_reviews(out, self.path)
        self.assertEqual(again, out)

    def test_only_current_annotation_can_resolve_warning_and_keeps_history(self):
        self.entry["source_quality_issue"] = None
        self.entry["review_result"] = "PASS"
        self.write()
        out, _ = apply_reviews([dict(self.row, source_quality_issue="old_warning")], self.path)
        self.assertEqual(out[0]["manual_review_status"], "reviewed")
        self.assertIsNone(out[0]["source_quality_issue"])
        self.assertEqual(out[0]["prior_source_quality_issue"], "old_warning")
        again, _ = apply_reviews(out, self.path)
        self.assertEqual(again, out)

    def test_duplicate_annotation_or_row_ids_fail(self):
        self.write([self.entry, self.entry])
        with self.assertRaisesRegex(ReviewAnnotationError, "Duplicate annotation"):
            apply_reviews([self.row], self.path)
        self.write()
        with self.assertRaisesRegex(ReviewAnnotationError, "Duplicate row"):
            apply_reviews([self.row, self.row], self.path)

    def test_invalid_schema_and_evidence_fail_instead_of_dropping_review(self):
        cases = [
            {"format_version": 2, "annotations": [self.entry]},
            {"format_version": True, "annotations": [self.entry]},
            {"format_version": 1, "annotations": [self.entry], "typo": 1},
            {"format_version": 1, "annotations": "not a list"},
            {"format_version": 1, "annotations": [dict(self.entry, typo="ignored?")]},
            {"format_version": 1, "annotations": [dict(self.entry, snapshot_sha256="A" * 64)]},
            {"format_version": 1, "annotations": [dict(self.entry, fields_sha256="bad")]},
            {"format_version": 1, "annotations": [dict(self.entry, reviewed_at="2026-09-26T12:00:00")]},
            {"format_version": 1, "annotations": [dict(self.entry, review_result="PENDING")]},
            {"format_version": 1, "annotations": [dict(self.entry, source_quality_issue=[])]},
        ]
        for case in cases:
            with self.subTest(case=str(case)):
                self.path.write_text(json.dumps(case))
                with self.assertRaises(ReviewAnnotationError):
                    apply_reviews([self.row], self.path)

    def test_duplicate_json_keys_broken_json_and_nan_fail(self):
        for value in ('{"format_version":1,"format_version":1,"annotations":[]}', '{', '{"format_version":1,"annotations":[],"author":NaN}'):
            with self.subTest(value=value):
                self.path.write_text(value)
                with self.assertRaises(ReviewAnnotationError):
                    apply_reviews([self.row], self.path)

    def test_symlink_and_directory_sidecar_fail(self):
        real = self.path.parent / "real.json"
        real.write_text('{"format_version":1,"annotations":[]}')
        self.path.symlink_to(real)
        with self.assertRaisesRegex(ReviewAnnotationError, "symlink"):
            apply_reviews([self.row], self.path)
        with self.assertRaisesRegex(ReviewAnnotationError, "regular file"):
            apply_reviews([self.row], self.path.parent)

    def test_bad_field_types_or_bad_media_do_not_receive_a_digest(self):
        for field, value in (("title", 123), ("main_text", float("inf")), ("media_embeds", "not JSON"), ("media_embeds", {"url": "a"}), ("media_embeds", [None])):
            with self.subTest(field=field, value=value):
                with self.assertRaises(ReviewAnnotationError):
                    fields_digest(dict(self.row, **{field: value}))


if __name__ == "__main__":
    unittest.main()

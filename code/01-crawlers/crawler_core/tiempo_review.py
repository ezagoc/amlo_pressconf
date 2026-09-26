"""Bind optional manual reviews to both a captured page and extracted fields.

This module only reads the explicitly supplied sidecar. It never changes an
article, annotation file, database, or snapshot. A review is current only when
its sample ID, snapshot digest, field digest and optional URL all match.

Sidecar v1::

    {"format_version": 1, "annotations": [{
      "sample_id": "P003", "snapshot_sha256": "<64 lowercase hex>",
      "fields_sha256": "<fields_digest(row)>", "reviewer": "Kevin",
      "reviewed_at": "2026-09-26T20:00:00+00:00",
      "review_result": "PASS_SOURCE_GAP_RECORDED",
      "source_quality_issue": "source_fragment_suspected",
      "review_note": "Only two paragraphs remain on the captured page."
    }]}

Optional top-level keys: author, created_at, fields_digest_version (must be 1).
An annotation may additionally bind url. Unknown keys and duplicate JSON keys,
sample IDs, malformed hashes or unsupported versions are errors, not a reason
to quietly discard reviews. Annotations not represented in the supplied rows
are reported in metadata: this permits annotating a filtered article export.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re

FORMAT_VERSION = 1
FIELDS_DIGEST_VERSION = 1
MAX_ANNOTATION_BYTES = 16 * 1024 * 1024
REVIEWED_FIELDS = (
    "title", "summary", "main_text", "authors", "date_published",
    "canonical_url", "media_embeds",
)
REVIEW_RESULTS = {"PASS", "PASS_SOURCE_GAP_RECORDED", "FAIL", "REQUIRES_REVIEW"}
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_REQUIRED = {
    "sample_id", "snapshot_sha256", "fields_sha256", "reviewer",
    "reviewed_at", "review_result", "source_quality_issue", "review_note",
}


class ReviewAnnotationError(ValueError):
    """Malformed review evidence; callers must stop rather than drop it."""


def _text(value, field: str):
    # Empty CSV cells and typed database/Parquet nulls represent the same value.
    # Preserve all nonempty text exactly: changing whitespace in a reviewed
    # article must not silently inherit the previous manual acceptance.
    if value is None or isinstance(value, float) and math.isnan(value):
        return None
    if not isinstance(value, str):
        raise ReviewAnnotationError(f"{field} must be text or null")
    return value if value.strip() else None


def _media(value):
    if _is_null(value):
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError) as exc:
            raise ReviewAnnotationError("media_embeds must be a JSON list of strings") from exc
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ReviewAnnotationError("media_embeds must be a list of nonempty strings")
    # The page order is part of the reviewed fields. JSON pretty-printing is not.
    return value


def _is_null(value):
    return value is None or isinstance(value, float) and math.isnan(value) or isinstance(value, str) and not value.strip()


def fields_digest(row: Mapping) -> str:
    """SHA-256 of canonical UTF-8 JSON of the seven reviewed fields (v1).

    Keys are sorted, separators are compact, Unicode is literal, NaN is not
    serialized. Missing/empty scalar fields become null; absent media becomes
    []; media JSON strings and equivalent lists hash identically. Nonempty
    text and media order are preserved. Audit metadata is excluded.
    """
    if not isinstance(row, Mapping):
        raise ReviewAnnotationError("Each row must be a mapping")
    values = {key: _media(row.get(key)) if key == "media_embeds" else _text(row.get(key), key) for key in REVIEWED_FIELDS}
    payload = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _nonempty(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ReviewAnnotationError(f"{field} must be nonempty text")


def _timestamp(value, field):
    _nonempty(value, field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReviewAnnotationError(f"{field} must be an ISO timestamp with timezone") from exc
    if parsed.utcoffset() is None:
        raise ReviewAnnotationError(f"{field} must include its timezone")


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReviewAnnotationError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ReviewAnnotationError(f"Non-JSON constant in sidecar: {value}")


def _load(path: Path | None):
    if path is None:
        return {}, None, False
    if path.is_symlink():
        raise ReviewAnnotationError("Review sidecar must not be a symlink")
    if not path.exists():
        return {}, None, False
    if not path.is_file():
        raise ReviewAnnotationError("Review sidecar must be a regular file")
    if path.stat().st_size > MAX_ANNOTATION_BYTES:
        raise ReviewAnnotationError("Review sidecar exceeds the 16 MiB limit")
    try:
        content = path.read_bytes()
        data = json.loads(content.decode("utf-8-sig"), object_pairs_hook=_no_duplicate_keys, parse_constant=_reject_constant)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ReviewAnnotationError(f"Cannot read valid review annotations: {exc}") from exc
    allowed = {"format_version", "fields_digest_version", "author", "created_at", "annotations"}
    if not isinstance(data, dict) or set(data) - allowed or not {"format_version", "annotations"}.issubset(data):
        raise ReviewAnnotationError("Sidecar must contain format_version and annotations, without unknown keys")
    for key, default in (("format_version", FORMAT_VERSION), ("fields_digest_version", FIELDS_DIGEST_VERSION)):
        value = data.get(key, default)
        if type(value) is not int or value != 1:
            raise ReviewAnnotationError(f"Unsupported {key}: {value!r}")
    if "author" in data:
        _nonempty(data["author"], "author")
    if "created_at" in data:
        _timestamp(data["created_at"], "created_at")
    if not isinstance(data["annotations"], list):
        raise ReviewAnnotationError("annotations must be a list")
    by_id = {}
    for entry in data["annotations"]:
        if not isinstance(entry, dict) or not _REQUIRED.issubset(entry) or set(entry) - (_REQUIRED | {"url"}):
            raise ReviewAnnotationError("Each annotation needs the v1 required fields, without unknown keys")
        for field in ("sample_id", "reviewer", "review_result"):
            _nonempty(entry[field], field)
        sid = entry["sample_id"]
        if sid in by_id:
            raise ReviewAnnotationError(f"Duplicate annotation sample_id: {sid}")
        for field in ("snapshot_sha256", "fields_sha256"):
            if not isinstance(entry[field], str) or not _HASH.fullmatch(entry[field]):
                raise ReviewAnnotationError(f"{sid}: {field} must be 64 lowercase hexadecimal characters")
        if entry["review_result"] not in REVIEW_RESULTS:
            raise ReviewAnnotationError(f"{sid}: unsupported review_result")
        _timestamp(entry["reviewed_at"], "reviewed_at")
        for field in ("source_quality_issue", "review_note"):
            if entry[field] is not None:
                _nonempty(entry[field], field)
        if "url" in entry:
            _nonempty(entry["url"], "url")
        by_id[sid] = dict(entry)
    return by_id, hashlib.sha256(content).hexdigest(), True


def apply_reviews(rows, annotation_path) -> tuple[list[dict], dict]:
    """Return copies annotated as reviewed, stale or not_reviewed.

    Stale evidence is retained separately, but manual_review_result becomes
    null, so a previous PASS cannot masquerade as a current acceptance.
    With stale evidence, its non-null source warning is retained; an existing
    row warning is used if that evidence has none. A different preexisting
    warning remains in prior_source_quality_issue. Without a matching review,
    the existing warning/result/note remain as warning/prior-review fields.
    Only a CURRENT annotation can explicitly resolve an existing warning to
    null, and even then its previous value remains in the prior-warning field.
    No input row or file is mutated. Malformed evidence fails the entire call.
    """
    path = Path(annotation_path) if annotation_path is not None else None
    entries, file_digest, present = _load(path)
    result, seen = [], set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ReviewAnnotationError("Each row must be a mapping")
        sid = row.get("sample_id")
        _nonempty(sid, "row sample_id")
        if sid in seen:
            raise ReviewAnnotationError(f"Duplicate row sample_id: {sid}")
        seen.add(sid)
        actual_digest = fields_digest(row)
        old_issue = _text(row.get("source_quality_issue"), "source_quality_issue")
        old_prior_issue = _text(row.get("prior_source_quality_issue"), "prior_source_quality_issue")
        old_result = _text(row.get("manual_review_result") or row.get("prior_review_result"), "prior_review_result")
        old_note = _text(row.get("manual_review_note") or row.get("prior_review_note"), "prior_review_note")
        entry = entries.get(sid)
        reasons = []
        status = "not_reviewed"
        if entry is not None:
            if row.get("snapshot_sha256") != entry["snapshot_sha256"]:
                reasons.append("snapshot_changed")
            if actual_digest != entry["fields_sha256"]:
                reasons.append("extracted_fields_changed")
            if "url" in entry and row.get("url") != entry["url"]:
                reasons.append("requested_url_changed")
            status = "stale" if reasons else "reviewed"
        warning = entry["source_quality_issue"] if entry and status == "reviewed" else (entry.get("source_quality_issue") if entry else None) or old_issue
        annotated = dict(row)
        annotated.update(
            manual_review_status=status,
            manual_review_result=entry["review_result"] if status == "reviewed" else None,
            prior_review_result=entry["review_result"] if status == "stale" else old_result if status == "not_reviewed" else None,
            manual_reviewer=entry["reviewer"] if entry else None,
            manual_reviewed_at=entry["reviewed_at"] if entry else None,
            manual_review_note=entry["review_note"] if entry else None,
            prior_review_note=entry["review_note"] if status == "stale" else old_note if status == "not_reviewed" else None,
            source_quality_issue=warning,
            prior_source_quality_issue=old_issue if old_issue and old_issue != warning else old_prior_issue,
            review_fields_sha256=actual_digest,
            review_annotation_snapshot_sha256=entry["snapshot_sha256"] if entry else None,
            review_annotation_fields_sha256=entry["fields_sha256"] if entry else None,
            review_stale_reasons=json.dumps(reasons, separators=(",", ":")),
            review_missing_reason=None if entry else "no_annotation_for_sample" if present else "sidecar_absent",
            review_annotation_file_sha256=file_digest,
        )
        result.append(annotated)
    counts = Counter(row["manual_review_status"] for row in result)
    metadata = {
        "format_version": FORMAT_VERSION, "fields_digest_version": FIELDS_DIGEST_VERSION,
        "reviewed_fields": list(REVIEWED_FIELDS), "annotation_path": str(path) if path else None,
        "annotation_file_present": present, "annotation_file_sha256": file_digest,
        "annotation_count": len(entries), "annotation_sample_ids": sorted(entries), "row_count": len(result),
        "status_counts": {key: counts[key] for key in ("reviewed", "stale", "not_reviewed")},
        "unused_annotation_ids": sorted(set(entries) - seen),
        "source_warning_rows": sum(bool(row["source_quality_issue"]) for row in result),
    }
    return result, metadata

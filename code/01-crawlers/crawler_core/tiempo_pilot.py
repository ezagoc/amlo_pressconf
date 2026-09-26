"""Bounded, auditable Tiempo pilots; never writes the shared crawler outputs.

All network calls are explicit and sequential. A complete response snapshot is
durable before an article result is committed, so resume can parse that snapshot
without making a second request. Missing values remain null; no text-length
threshold is used to decide whether a genuine short article is exportable.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pandas as pd

from crawler_core.tiempo_review import ReviewAnnotationError, apply_reviews

MAX_URLS = 80
REQUIRED_INPUT = {"sample_id", "url", "expected_year"}
ARTICLE_COLUMNS = [
    "source_id", "source_name", "sample_id", "url", "canonical_url", "final_url",
    "title", "summary", "main_text", "authors", "date", "date_published",
    "date_modified", "topic", "section", "language", "scrape_timestamp",
    "discovery_strategy", "extractor_strategy", "status", "content_type", "error",
    "qa_status", "publication_date_source", "publication_date_evidence",
    "date_conflict", "author_source", "body_selector", "raw_html_path",
    "snapshot_path", "snapshot_sha256", "snapshot_capture_attempt_id",
    "expected_year", "selection_reason", "expected_kind", "sample_metadata_json",
    "manifest_sha256", "updated_at", "attempt_id",
]
OUTPUT_NAMES = ("articles.csv", "articles.parquet", "attempts.csv", "attempts.parquet", "export_manifest.json")
ANNOTATION_NAME = "review_annotations.json"
REVIEW_COLUMNS = [
    "manual_review_status", "manual_review_result", "prior_review_result",
    "manual_reviewer", "manual_reviewed_at", "manual_review_note", "prior_review_note",
    "source_quality_issue", "prior_source_quality_issue", "review_fields_sha256",
    "review_annotation_snapshot_sha256", "review_annotation_fields_sha256",
    "review_stale_reasons", "review_missing_reason", "review_annotation_file_sha256",
]


class PilotError(ValueError):
    """An invalid input or unsafe output location; fail before requesting URLs."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value):
    """JSON/SQLite-safe scalars, without turning a missing value into 'nan'."""
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        return value if value.strip() else None
    if isinstance(value, (int, float, bool)):
        return value
    if hasattr(value, "item"):
        return clean(value.item())
    return str(value)


def json_bytes(value) -> bytes:
    return (json.dumps(clean(value), ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_path(run_dir: Path, relative: str | Path) -> Path:
    target = run_dir / relative
    if not target.resolve().is_relative_to(run_dir.resolve()):
        raise PilotError(f"Output escapes this pilot (possibly a symlink): {relative}")
    return target


def atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def normalized_input_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    try:
        port = parsed.port
    except ValueError as exc:
        raise PilotError(f"Invalid URL: {url}") from exc
    if parsed.scheme.lower() not in {"http", "https"} or parsed.hostname not in {"tiempo.com.mx", "www.tiempo.com.mx"}:
        raise PilotError(f"Only selected Tiempo HTTP(S) URLs are allowed: {url}")
    if parsed.username or parsed.password or port not in {None, 80, 443}:
        raise PilotError(f"Unexpected credentials or port: {url}")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.query, ""))


def load_input(path: Path) -> tuple[list[dict], str]:
    content = path.read_bytes()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    if not REQUIRED_INPUT.issubset(reader.fieldnames or []):
        raise PilotError("Input must include " + ", ".join(sorted(REQUIRED_INPUT)))
    if not ({"selection_reason", "stratum"} & set(reader.fieldnames or [])) or not ({"expected_kind", "sample_role"} & set(reader.fieldnames or [])):
        raise PilotError("Input needs selection_reason (or stratum), and expected_kind (or sample_role).")
    rows, seen_urls, seen_ids = [], set(), set()
    for ordinal, raw in enumerate(reader):
        if None in raw:
            raise PilotError("CSV row has more values than its header.")
        row = {key: clean(value.strip() if isinstance(value, str) else value) for key, value in raw.items()}
        row.setdefault("selection_reason", row.get("stratum"))
        row.setdefault("expected_kind", row.get("sample_role"))
        sample_id = row.get("sample_id")
        if not sample_id or not row.get("url"):
            raise PilotError("Every row needs sample_id and url.")
        url = normalized_input_url(row["url"])
        if url in seen_urls or sample_id in seen_ids:
            raise PilotError(f"Duplicate URL or sample_id: {sample_id}")
        seen_urls.add(url)
        seen_ids.add(sample_id)
        row.update(url=url, ordinal=ordinal)
        rows.append(row)
    if not 1 <= len(rows) <= MAX_URLS:
        raise PilotError(f"Input must contain 1–{MAX_URLS} distinct URLs; found {len(rows)}.")
    return rows, digest(content)


def validate_run_dir(run_dir: Path, media_root: Path, repo_root: Path | None = None) -> Path:
    run_dir, media_root = run_dir.expanduser().resolve(), media_root.expanduser().resolve()
    allowed = (media_root / "data/00-newspaper_data/crawler/pilots").resolve()
    if run_dir == allowed or not run_dir.is_relative_to(allowed):
        raise PilotError("--run-dir must be an independent subdirectory of MEDIA_ROOT/data/00-newspaper_data/crawler/pilots/.")
    if repo_root and run_dir.is_relative_to(repo_root.resolve()):
        raise PilotError("Pilot outputs cannot be stored in the Git repository.")
    note = safe_path(run_dir, "Kevin_NOTE.md")
    if not note.is_file():
        raise PilotError("Create Kevin_NOTE.md in the pilot directory before running.")
    for name in ("pilot.sqlite", "attempts.jsonl", "manifest.json", ".pilot.lock", "raw_html", "backups", "review_history", ANNOTATION_NAME, *OUTPUT_NAMES):
        safe_path(run_dir, name)
    return run_dir


@contextmanager
def exclusive_run(run_dir: Path):
    # macOS/Linux flock releases automatically after interruption or process exit.
    import fcntl
    with safe_path(run_dir, ".pilot.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PilotError("Another process is already using this pilot directory.") from exc
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def append_note(run_dir: Path, message: str) -> None:
    with safe_path(run_dir, "Kevin_NOTE.md").open("a", encoding="utf-8") as out:
        out.write(f"\n- {now()} — Kevin: {message}\n")
        out.flush()
        os.fsync(out.fileno())


class Backups:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.directory: Path | None = None

    def ensure(self, reason: str) -> Path:
        if self.directory:
            return self.directory
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        destination = safe_path(self.run_dir, Path("backups") / stamp)
        destination.mkdir(parents=True)
        hashes = {}
        for name in ("pilot.sqlite", "manifest.json", "attempts.jsonl", ANNOTATION_NAME, *OUTPUT_NAMES):
            source = safe_path(self.run_dir, name)
            if not source.is_file():
                continue
            target = destination / name
            if name.endswith(".sqlite"):
                with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as original, sqlite3.connect(target) as copied:
                    original.backup(copied)
            else:
                shutil.copy2(source, target)
            hashes[name] = digest(target.read_bytes())
        history = safe_path(self.run_dir, "review_history")
        for source in history.glob("*.json") if history.exists() else []:
            source = safe_path(self.run_dir, source.relative_to(self.run_dir))
            data = source.read_bytes()
            if not re.fullmatch(r"[0-9a-f]{64}", source.stem) or digest(data) != source.stem:
                raise PilotError("Review history hash mismatch; refusing an incomplete backup.")
            relative = Path("review_history") / source.name
            target = destination / relative
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(data)
            hashes[str(relative)] = digest(data)
        atomic_bytes(destination / "backup_manifest.json", json_bytes({"reason": reason, "created_at": now(), "sha256": hashes, "author": "Kevin"}))
        append_note(self.run_dir, f"Backup before {reason}: {destination.relative_to(self.run_dir)}. Existing results/exports retained; no shared source data modified.")
        self.directory = destination
        return destination


def connect_db(run_dir: Path, *, allow_create=False) -> sqlite3.Connection:
    path = safe_path(run_dir, "pilot.sqlite")
    conn = sqlite3.connect(path.as_uri() + ("?mode=rwc" if allow_create else "?mode=rw"), uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA journal_mode=DELETE")
    columns = ", ".join(f'"{column}" {"INTEGER" if column == "status" else "TEXT"}' for column in ARTICLE_COLUMNS)
    conn.execute(f"CREATE TABLE IF NOT EXISTS articles ({columns}, ordinal INTEGER NOT NULL, payload_json TEXT NOT NULL, PRIMARY KEY(url))")
    conn.execute("""CREATE TABLE IF NOT EXISTS fetch_attempts (
        attempt_id TEXT PRIMARY KEY, sample_id TEXT NOT NULL, url TEXT NOT NULL,
        action TEXT NOT NULL, network_request INTEGER NOT NULL,
        started_at TEXT NOT NULL, completed_at TEXT, status INTEGER, error TEXT,
        qa_status TEXT, snapshot_path TEXT, snapshot_sha256 TEXT,
        cached_recovery INTEGER NOT NULL DEFAULT 0, retained_success INTEGER NOT NULL DEFAULT 0,
        manifest_sha256 TEXT NOT NULL, response_json TEXT, result_json TEXT)""")
    conn.commit()
    return conn


def validate_bound_state(conn, run_dir, items, manifest_hash):
    """Reject mixed/restored state before any mutation or export replacement."""
    if [r[0] for r in conn.execute("PRAGMA quick_check")] != ["ok"]:
        raise PilotError("Pilot database integrity check failed; restore a verified backup.")
    selected = {r["url"]: r["sample_id"] for r in items}
    checked_snapshots = set()

    def check_identity(record):
        if selected.get(record["url"]) != record["sample_id"] or record["manifest_sha256"] != manifest_hash:
            raise PilotError("Pilot database does not match this input manifest; restore matching files or use a new directory.")

    def check_snapshot(record):
        key = (record["snapshot_path"], record["snapshot_sha256"], record["url"], record["sample_id"])
        if key in checked_snapshots:
            return
        if not key[0] or not key[1]:
            raise PilotError("A committed result has no bound snapshot.")
        html_path = safe_path(run_dir, key[0])
        metadata_path = safe_path(run_dir, Path(key[0]).with_suffix(".json"))
        try:
            raw = html_path.read_bytes()
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise PilotError(f"Snapshot evidence is missing or unreadable for {record['sample_id']}.") from exc
        if (digest(raw) != key[1] or metadata.get("snapshot_sha256") != key[1]
                or metadata.get("snapshot_bytes") != len(raw) or metadata.get("snapshot_path") != key[0]
                or metadata.get("url") != key[2] or metadata.get("sample_id") != key[3]
                or metadata.get("manifest_sha256") != manifest_hash):
            raise PilotError(f"Snapshot binding/hash mismatch for {record['sample_id']}.")
        checked_snapshots.add(key)

    try:
        for raw in conn.execute("SELECT url,sample_id,manifest_sha256,qa_status,snapshot_path,snapshot_sha256,payload_json FROM articles"):
            record = dict(raw)
            check_identity(record)
            payload = json.loads(record.pop("payload_json"))
            if any(payload.get(k) != v for k, v in record.items()) or payload.get("source_id") != "tiempo":
                raise PilotError("Pilot database columns and article payload disagree.")
            check_snapshot(record)
        for raw in conn.execute("SELECT url,sample_id,manifest_sha256,completed_at,snapshot_path,snapshot_sha256 FROM fetch_attempts"):
            record = dict(raw)
            check_identity(record)
            if record["completed_at"] and record["snapshot_path"]:
                check_snapshot(record)
    except (sqlite3.DatabaseError, ValueError, TypeError, KeyError) as exc:
        if isinstance(exc, PilotError):
            raise
        raise PilotError("Pilot database schema or records are invalid; restore matching files.") from exc


def can_finish_initialization(run_dir, manifest):
    """Only a marked, still-pristine first initialization may create its DB."""
    if manifest.get("database_initialized") is not False:
        return False
    if any(safe_path(run_dir, name).exists() for name in ("attempts.jsonl", "raw_html", *OUTPUT_NAMES)):
        return False
    path = safe_path(run_dir, "pilot.sqlite")
    if not path.exists():
        return True
    try:
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as conn:
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            if any(name not in {"articles", "fetch_attempts"} for name in tables):
                return False
            return all(conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] == 0 for name in tables)
    except sqlite3.DatabaseError:
        return False


def append_log(run_dir: Path, event: dict) -> None:
    with safe_path(run_dir, "attempts.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(clean(event), ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def start_attempt(conn, run_dir, item, manifest_hash, action, *, attempt_id=None, started_at=None, recovering=False):
    attempt_id, started_at = attempt_id or uuid.uuid4().hex, started_at or now()
    with conn:
        conn.execute("INSERT OR IGNORE INTO fetch_attempts(attempt_id,sample_id,url,action,network_request,started_at,manifest_sha256) VALUES(?,?,?,?,?,?,?)",
                     (attempt_id, item["sample_id"], item["url"], action, int(action == "fetch"), started_at, manifest_hash))
    append_log(run_dir, {"event": "snapshot_recovery" if recovering else "started", "attempt_id": attempt_id, "sample_id": item["sample_id"], "url": item["url"], "action": action, "network_request": action == "fetch" and not recovering, "time": started_at})
    return attempt_id


def save_snapshot(run_dir, item, attempt_id, manifest_hash, response):
    response = clean(response)
    text = response.get("text") or ""
    html = text.encode("utf-8")
    relative = Path("raw_html") / digest(item["url"].encode()) / f"{attempt_id}.html"
    atomic_bytes(safe_path(run_dir, relative), html)
    metadata = {"format_version": 1, "response_complete": not bool(response.get("error")),
                "sample_id": item["sample_id"], "url": item["url"], "attempt_id": attempt_id,
                "manifest_sha256": manifest_hash, "captured_at": now(), "snapshot_path": str(relative),
                "snapshot_sha256": digest(html), "snapshot_bytes": len(html),
                "response": {k: v for k, v in response.items() if k != "text"}}
    # The metadata is the completion marker; orphan HTML without it is ignored.
    atomic_bytes(safe_path(run_dir, relative.with_suffix(".json")), json_bytes(metadata))
    return metadata


def find_snapshot(run_dir, item, *, manifest_hash=None, pending_attempt_ids=None):
    folder = safe_path(run_dir, Path("raw_html") / digest(item["url"].encode()))
    if not folder.exists():
        return None
    candidates = []
    for path in folder.glob("*.json"):
        metadata = json.loads(safe_path(run_dir, path.relative_to(run_dir)).read_text(encoding="utf-8"))
        if metadata.get("url") != item["url"] or metadata.get("sample_id") != item["sample_id"]:
            continue
        if pending_attempt_ids is not None and metadata.get("attempt_id") not in pending_attempt_ids:
            continue
        if not metadata.get("response_complete"):
            continue
        if manifest_hash and metadata.get("manifest_sha256") != manifest_hash:
            continue
        html = safe_path(run_dir, metadata["snapshot_path"]).read_bytes()
        if digest(html) != metadata.get("snapshot_sha256") or len(html) != metadata.get("snapshot_bytes"):
            raise PilotError(f"Snapshot hash/size mismatch for {item['sample_id']}; inspect the cache before continuing.")
        metadata["text"] = html.decode("utf-8")
        candidates.append(metadata)
    return max(candidates, key=lambda x: x["captured_at"]) if candidates else None


def extract_result(item, response, metadata, manifest_hash, attempt_id, parser):
    response = clean(response)
    status = response.get("status")
    try:
        status = int(status) if status is not None else None
    except (TypeError, ValueError):
        status = None
    row = {key: None for key in ARTICLE_COLUMNS}
    row.update(source_id="tiempo", source_name="Tiempo La Noticia Digital", sample_id=item["sample_id"], url=item["url"],
               final_url=response.get("final_url"), status=status, content_type=response.get("content_type"),
               scrape_timestamp=metadata["captured_at"], updated_at=now(), attempt_id=attempt_id,
               discovery_strategy="selected_pilot_input", extractor_strategy="tiempo_html_pilot",
               expected_year=item.get("expected_year"), selection_reason=item.get("selection_reason"),
               expected_kind=item.get("expected_kind"), sample_metadata_json=json.dumps(clean(item), ensure_ascii=False),
               manifest_sha256=manifest_hash, raw_html_path=metadata["snapshot_path"], snapshot_path=metadata["snapshot_path"],
               snapshot_sha256=metadata["snapshot_sha256"], snapshot_capture_attempt_id=metadata["attempt_id"], ordinal=item["ordinal"])
    error = None
    if response.get("error"):
        error = "transport_error: " + str(response["error"])
    elif status is None or not 200 <= status < 300:
        error = f"http_status: {status}"
    elif not re.search(r"^(text/html|application/xhtml\+xml)(?:;|$)", str(response.get("content_type") or "").lower()):
        error = "non_html_response"
    elif not response.get("text"):
        error = "empty_html_response"
    else:
        try:
            fields = clean(parser(response["text"], url=response.get("final_url") or item["url"], source_id="tiempo"))
            row.update(fields)
            error = fields.get("source_specific_error")
            if not error and not clean(fields.get("title")):
                error = "missing_title"
            if not error and not clean(fields.get("main_text")):
                error = "missing_body"
            publication = clean(fields.get("date_published"))
            source = str(fields.get("publication_date_source") or "").lower()
            if not error and (not publication or not source or not clean(fields.get("publication_date_evidence")) or any(bad in source for bad in ("modified", "lastmod", "fallback", "url", "assumed", "fetch"))):
                error = "missing_verified_publication_date"
            if not error:
                try:
                    parsed_date = pd.to_datetime(publication, errors="raise")
                    if pd.isna(parsed_date):
                        raise ValueError("missing date")
                except (ValueError, TypeError, OverflowError):
                    error = "invalid_publication_date"
            if not error:
                row["date"] = publication  # Never infer from expected_year, modified date, or fetch time.
        except Exception as exc:
            error = f"parser_error: {type(exc).__name__}: {exc}"
    row.update(status=status, error=str(error) if error else None, qa_status="error" if error else "success")
    return clean(row)


def commit_result(conn, run_dir, row, response, *, cached_recovery=False):
    existing = conn.execute("SELECT qa_status FROM articles WHERE url=?", (row["url"],)).fetchone()
    retained = bool(existing and existing["qa_status"] == "success" and row["qa_status"] != "success")
    with conn:
        if not retained:
            columns = ARTICLE_COLUMNS + ["ordinal", "payload_json"]
            values = []
            for name in ARTICLE_COLUMNS:
                value = clean(row.get(name))
                values.append(json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value)
            values.extend([row["ordinal"], json.dumps(row, ensure_ascii=False)])
            conn.execute(f'INSERT OR REPLACE INTO articles ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})', values)
        conn.execute("""UPDATE fetch_attempts SET completed_at=?,status=?,error=?,qa_status=?,snapshot_path=?,snapshot_sha256=?,
                     cached_recovery=?,retained_success=?,response_json=?,result_json=? WHERE attempt_id=?""",
                     (now(), row.get("status"), row.get("error"), row["qa_status"], row["snapshot_path"], row["snapshot_sha256"],
                      int(cached_recovery), int(retained), json.dumps(clean({k: v for k, v in response.items() if k != "text"}), ensure_ascii=False),
                      json.dumps(row, ensure_ascii=False), row["attempt_id"]))
        # Older attempts interrupted before a committed response are historical,
        # not still-running work once a replacement result has been committed.
        conn.execute("""UPDATE fetch_attempts SET completed_at=?,qa_status='interrupted',
                     error='interrupted_without_committed_result; superseded' WHERE url=? AND manifest_sha256=?
                     AND attempt_id<>? AND completed_at IS NULL""",
                     (now(), row["url"], row["manifest_sha256"], row["attempt_id"]))
    append_log(run_dir, {"event": "completed", "attempt_id": row["attempt_id"], "url": row["url"], "qa_status": row["qa_status"],
                        "status": row.get("status"), "error": row.get("error"), "cached_recovery": cached_recovery, "retained_success": retained, "time": now()})
    return retained


def canonical_identity(row):
    """Only a plausible complete Tiempo article canonical can merge aliases."""
    value = row.get("canonical_url")
    if not isinstance(value, str):
        return None
    p = urlsplit(value)
    if p.scheme not in {"http", "https"} or p.hostname not in {"tiempo.com.mx", "www.tiempo.com.mx"}:
        return None
    if p.username or p.password or p.query or "//" in p.path or len([x for x in p.path.split("/") if x]) < 2:
        return None
    return "https://tiempo.com.mx" + p.path.rstrip("/")


def previous_review_summary(run_dir):
    manifest = safe_path(run_dir, "export_manifest.json")
    if not manifest.is_file():
        return {}
    try:
        prior = json.loads(manifest.read_text(encoding="utf-8")).get("manual_review", {})
        if not isinstance(prior, dict):
            raise ValueError("manual_review must be an object")
    except (ValueError, TypeError, AttributeError) as exc:
        raise PilotError("Existing export manifest is invalid; restore it before continuing.") from exc
    return prior


def validate_review_continuity(run_dir, summary):
    prior = previous_review_summary(run_dir)
    if prior.get("annotation_file_present") and not summary["annotation_file_present"]:
        raise PilotError("Previously used review annotations are missing; restore the sidecar instead of dropping source warnings.")
    removed = set(prior.get("annotation_sample_ids", [])) - set(summary.get("annotation_sample_ids", []))
    if removed:
        raise PilotError("Previously used review records were removed: " + ", ".join(sorted(removed))
                         + ". Preserve the records and explicitly mark a new review decision.")


def review_context(run_dir, *, persist=False):
    """Pin this export's review versions; never use editable CSV as history."""
    current = safe_path(run_dir, ANNOTATION_NAME)
    try:
        _, summary = apply_reviews([], current)
    except ReviewAnnotationError as exc:
        raise PilotError(f"Invalid manual review evidence: {exc}") from exc
    validate_review_continuity(run_dir, summary)
    prior = previous_review_summary(run_dir)
    history = prior.get("annotation_history_sha256", [])
    if not isinstance(history, list) or any(not isinstance(h, str) or not re.fullmatch(r"[0-9a-f]{64}", h) for h in history):
        raise PilotError("Invalid review history in export manifest.")
    existing_history = set(history)
    history = list(history)
    current_hash = summary["annotation_file_sha256"]
    # An export written before history support can be upgraded only if its
    # exact previously used sidecar is still available, never by guessing.
    if not history and prior.get("annotation_file_present"):
        old_hash = prior.get("annotation_file_sha256")
        if not old_hash or old_hash != current_hash:
            raise PilotError("Previous review history is unavailable; restore the exact prior sidecar before changing reviews.")
        history.append(old_hash)
    if current_hash and (not history or history[-1] != current_hash):
        history.append(current_hash)
    paths = []
    for sha in history:
        target = safe_path(run_dir, Path("review_history") / (sha + ".json"))
        if target.exists():
            if target.is_symlink() or not target.is_file() or digest(target.read_bytes()) != sha:
                raise PilotError("Review history hash mismatch; restore the original review evidence.")
            paths.append(target)
        elif sha in existing_history or sha != current_hash:
            raise PilotError("A referenced review history file is missing; restore it before continuing.")
        else:
            data = current.read_bytes()
            if digest(data) != sha:
                raise PilotError("Review sidecar changed during validation; retry with a stable file.")
            if persist:
                atomic_bytes(target, data)
                paths.append(target)
            else:
                paths.append(current)
    return {"paths": paths, "current": current, "history_sha256": history}


def reviewed_rows(rows, run_dir, context=None):
    context = context or review_context(run_dir)
    try:
        # Reapply immutable versions in order. This carries prior warnings and
        # lets only a matching current decision explicitly resolve a warning.
        annotated = list(rows)
        for path in context["paths"] or [context["current"]]:
            annotated, summary = apply_reviews(annotated, path)
        summary["annotation_path"] = str(context["current"])
        summary["annotation_history_sha256"] = context["history_sha256"]
        return annotated, summary
    except ReviewAnnotationError as exc:
        raise PilotError(f"Invalid manual review evidence: {exc}") from exc


def export_outputs(conn, run_dir, manifest_hash, backups, items):
    validate_bound_state(conn, run_dir, items, manifest_hash)
    stored = [json.loads(r[0]) for r in conn.execute("SELECT payload_json FROM articles ORDER BY ordinal")]
    context = review_context(run_dir, persist=True)
    stored, review_summary = reviewed_rows(stored, run_dir, context)
    validate_review_continuity(run_dir, review_summary)
    successful = [r for r in stored if r["qa_status"] == "success"]
    groups, url_to_primary, url_to_role = {}, {}, {}
    for row in successful:
        key = canonical_identity(row) or ("raw:" + row["url"])
        groups.setdefault(key, []).append(row)
    articles, collision_groups = [], 0
    for identity, group in groups.items():
        normalized = lambda value: re.sub(r"\s+", " ", str(value or "")).strip()
        def signature(row):
            fields = ("title", "summary", "main_text", "authors", "date_published", "date_modified", "topic", "section", "language")
            media = row.get("media_embeds") or []
            if isinstance(media, str):
                try:
                    media = json.loads(media)
                except ValueError:
                    media = [media]
            media = tuple(sorted(normalized(x) for x in media)) if isinstance(media, list) else (normalized(media),)
            return tuple(normalized(row.get(k)) for k in fields) + (media,)
        signatures = {signature(r) for r in group}
        collision = len(signatures) > 1
        if collision:
            collision_groups += 1
        # Metadata and embedded-media disagreements also remain visible.
        for subset in ([group] if not collision else [[row] for row in group]):
            row = dict(subset[0])
            row["alias_urls"] = json.dumps([r["url"] for r in subset[1:]], ensure_ascii=False)
            row["alias_sample_ids"] = json.dumps([r["sample_id"] for r in subset[1:]], ensure_ascii=False)
            row["canonical_dedup_status"] = "collision_review" if collision else "identical_aliases_merged" if len(subset) > 1 else "single"
            row["canonical_collision"] = collision
            row["canonical_identity"] = identity if not identity.startswith("raw:") else None
            # Keep each alias's independently bound review. Its source warning
            # must not disappear merely because another URL became the primary.
            row["primary_review_annotation"] = json.dumps(
                {key: subset[0].get(key) for key in ["sample_id", "url", "snapshot_sha256", *REVIEW_COLUMNS]}, ensure_ascii=False)
            row["alias_review_annotations"] = json.dumps([
                {key: member.get(key) for key in ["sample_id", "url", "snapshot_sha256", *REVIEW_COLUMNS]}
                for member in subset[1:]
            ], ensure_ascii=False)
            states = {member["manual_review_status"] for member in subset}
            decisions = {member.get("manual_review_result") or member.get("prior_review_result") for member in subset}
            row["manual_review_disagreement"] = len(states) > 1 or len(decisions) > 1
            row["manual_review_status"] = "stale" if "stale" in states else "not_reviewed" if "not_reviewed" in states else "reviewed"
            row["manual_review_result"] = None
            if row["manual_review_status"] == "reviewed":
                row["manual_review_result"] = next((value for value in ("FAIL", "REQUIRES_REVIEW", "PASS_SOURCE_GAP_RECORDED", "PASS") if value in decisions), None)
            issues = list(dict.fromkeys(member["source_quality_issue"] for member in subset if member.get("source_quality_issue")))
            row["source_quality_issue"] = "; ".join(issues) or None
            articles.append(row)
            for member in subset:
                url_to_primary[member["url"]] = row["url"]
                url_to_role[member["url"]] = "collision_review" if collision else "primary" if member["url"] == row["url"] else "canonical_alias"
    attempts = []
    for raw in conn.execute("SELECT * FROM fetch_attempts ORDER BY started_at, attempt_id"):
        record = dict(raw)
        payload = json.loads(record.pop("result_json") or "null") or {}
        if payload:
            annotated, _ = reviewed_rows([payload], run_dir, context)
            record.update({key: annotated[0].get(key) for key in REVIEW_COLUMNS})
        record.update({k: payload.get(k) for k in ("title", "date_published", "main_text", "expected_kind", "expected_year", "selection_reason")})
        primary = url_to_primary.get(record["url"])
        record["export_role"] = url_to_role.get(record["url"], "not_exported")
        record["primary_export_url"] = primary
        attempts.append(record)
    article_fields = list(dict.fromkeys(ARTICLE_COLUMNS + REVIEW_COLUMNS + [k for row in articles for k in row] + ["alias_urls", "alias_sample_ids", "canonical_dedup_status", "canonical_collision", "canonical_identity", "primary_review_annotation", "alias_review_annotations", "manual_review_disagreement"]))
    attempt_fields = ["attempt_id", "sample_id", "url", "action", "network_request", "started_at", "completed_at", "status", "error", "qa_status",
                      "snapshot_path", "snapshot_sha256", "cached_recovery", "retained_success", "manifest_sha256", "response_json",
                      "title", "date_published", "main_text", "expected_kind", "expected_year", "selection_reason", "export_role", "primary_export_url"]
    attempt_fields += REVIEW_COLUMNS
    staged = {}
    for stem, records, columns in (("articles", articles, article_fields), ("attempts", attempts, attempt_fields)):
        serial = [{k: json.dumps(clean(v), ensure_ascii=False) if isinstance(v, (dict, list)) else clean(v) for k, v in r.items()} for r in records]
        frame = pd.DataFrame(serial, columns=columns)
        for column in ("status", "ordinal", "network_request", "cached_recovery", "retained_success"):
            if column in frame:
                frame[column] = pd.array(frame[column], dtype="Int64")
        staged[f"{stem}.csv"] = frame.to_csv(index=False, na_rep="").encode("utf-8")
        buffer = io.BytesIO()
        frame.to_parquet(buffer, index=False)
        staged[f"{stem}.parquet"] = buffer.getvalue()
    if any(safe_path(run_dir, name).exists() and safe_path(run_dir, name).read_bytes() != data for name, data in staged.items()):
        backups.ensure("replacing changed pilot exports")
    for name, data in staged.items():
        target = safe_path(run_dir, name)
        if not target.exists() or target.read_bytes() != data:
            atomic_bytes(target, data)
    summary = {"manifest_sha256": manifest_hash, "exported_at": now(), "source_id": "tiempo", "article_rows": len(articles),
               "successful_url_rows": len(successful), "canonical_alias_rows": len(successful) - len(articles), "result_rows": len(stored),
               "canonical_collision_groups": collision_groups,
               "error_results": len(stored) - len(successful), "attempt_rows": len(attempts),
               "network_fetch_calls_started": sum(int(r["network_request"]) for r in attempts),
               "request_count_definition": "Calls to capabilities.fetch, including interrupted calls; redirects may add HTTP exchanges.",
               "incomplete_attempts": sum(r["completed_at"] is None for r in attempts),
               "manual_review": review_summary,
               "csv_nulls": "Empty CSV fields denote null; Parquet retains typed nulls.",
               "files": {name: {"sha256": digest(data), "bytes": len(data)} for name, data in staged.items()}}
    atomic_bytes(safe_path(run_dir, "export_manifest.json"), json_bytes(summary))
    return summary


def run_pilot(input_path: Path, run_dir: Path, media_root: Path, *, repo_root=None, pause_seconds=1.0, timeout=45.0,
              retry_errors=False, export_only=False, reparse_cache=False, fetcher=None, parser=None,
              after_snapshot=None, after_commit=None):
    if sum(map(bool, (retry_errors, export_only, reparse_cache))) > 1:
        raise PilotError("--retry-errors, --export-only and --reparse-cache are mutually exclusive.")
    if pause_seconds < 0 or timeout <= 0:
        raise PilotError("pause must be nonnegative and timeout must be positive.")
    items, manifest_hash = load_input(input_path)
    run_dir = validate_run_dir(run_dir, media_root, repo_root)
    with exclusive_run(run_dir):
        # Bad review evidence stops before a fetch, DB change or export rewrite.
        _, review_preflight = reviewed_rows([], run_dir)
        validate_review_continuity(run_dir, review_preflight)
        backups = Backups(run_dir)
        manifest_path = safe_path(run_dir, "manifest.json")
        new_manifest = {"format_version": 1, "source_id": "tiempo", "input_sha256": manifest_hash,
                        "input_name": input_path.name, "created_at": now(), "items": items, "author": "Kevin", "database_initialized": False}
        if manifest_path.exists():
            previous = json.loads(manifest_path.read_text(encoding="utf-8"))
            if previous.get("input_sha256") != manifest_hash or previous.get("items") != items:
                raise PilotError("Input manifest changed. Use the original CSV; changed metadata requires a new independent pilot directory.")
            if previous.get("source_id") != "tiempo" or previous.get("format_version") != 1:
                raise PilotError("Unrecognized pilot manifest.")
        else:
            if export_only or reparse_cache or retry_errors:
                raise PilotError("This mode requires an existing bound pilot manifest.")
            if any(safe_path(run_dir, p).exists() for p in ("pilot.sqlite", "attempts.jsonl", "raw_html", *OUTPUT_NAMES)):
                raise PilotError("Unbound data already exists in run-dir; choose a new pilot directory.")
            atomic_bytes(manifest_path, json_bytes(new_manifest))
            append_note(run_dir, f"Started selected-URL pilot with {len(items)} inputs, input SHA256 {manifest_hash}; one worker, pause {pause_seconds}s. Shared outputs untouched.")
            previous = new_manifest
        initializing = can_finish_initialization(run_dir, previous)
        database_path = safe_path(run_dir, "pilot.sqlite")
        if not database_path.exists() and not initializing:
            raise PilotError("Bound pilot database is missing. Restore its matching database; refusing to create an empty replacement.")
        if initializing and (export_only or reparse_cache or retry_errors):
            raise PilotError("Pilot initialization is incomplete. Resume the original normal run first.")
        if database_path.exists() and not initializing:
            try:
                with sqlite3.connect(database_path.as_uri() + "?mode=ro", uri=True) as checked:
                    checked.row_factory = sqlite3.Row
                    validate_bound_state(checked, run_dir, items, manifest_hash)
            except sqlite3.DatabaseError as exc:
                raise PilotError("Bound pilot database is unreadable; restore matching files.") from exc
        if retry_errors or reparse_cache:
            backups.ensure("retrying existing errors" if retry_errors else "offline cache reparse")
        conn = connect_db(run_dir, allow_create=initializing)
        if initializing:
            try:
                previous["database_initialized"] = True
                atomic_bytes(manifest_path, json_bytes(previous))
            except BaseException:
                conn.close()
                raise
        interrupted = False
        try:
            if not export_only:
                if fetcher is None:
                    from crawler_core.capabilities import fetch
                    fetcher = fetch
                if parser is None:
                    from crawler_core.sitemap_articles import article_fields_from_html
                    parser = article_fields_from_html
                for item in items:
                    existing = conn.execute("SELECT qa_status FROM articles WHERE url=?", (item["url"],)).fetchone()
                    if not reparse_cache and existing and (not retry_errors or existing["qa_status"] == "success"):
                        continue
                    if retry_errors and not existing:
                        continue
                    pending = None
                    if retry_errors:
                        pending = {r[0] for r in conn.execute("SELECT attempt_id FROM fetch_attempts WHERE url=? AND manifest_sha256=? AND action='fetch' AND completed_at IS NULL", (item["url"], manifest_hash))}
                    metadata = find_snapshot(run_dir, item, manifest_hash=manifest_hash, pending_attempt_ids=pending)
                    was_cached = metadata is not None
                    if reparse_cache and not metadata:
                        append_log(run_dir, {"event": "reparse_skipped_no_complete_snapshot", "sample_id": item["sample_id"], "url": item["url"], "time": now()})
                        continue
                    if metadata:
                        action = "reparse" if reparse_cache else "fetch"
                        attempt_id = start_attempt(conn, run_dir, item, manifest_hash, action,
                                                   attempt_id=None if reparse_cache else metadata["attempt_id"],
                                                   started_at=None if reparse_cache else metadata["captured_at"], recovering=not reparse_cache)
                        response = {**metadata["response"], "text": metadata.pop("text")}
                    else:
                        attempt_id = start_attempt(conn, run_dir, item, manifest_hash, "fetch")
                        try:
                            response = clean(fetcher(item["url"], timeout, body_text_limit=12_000_000))
                        except Exception as exc:
                            response = {"status": None, "final_url": None, "content_type": None, "text": "", "error": f"{type(exc).__name__}: {exc}"}
                        metadata = save_snapshot(run_dir, item, attempt_id, manifest_hash, response)
                        if after_snapshot:
                            after_snapshot(item, metadata)
                    row = extract_result(item, response, metadata, manifest_hash, attempt_id, parser)
                    retained = commit_result(conn, run_dir, row, response, cached_recovery=was_cached)
                    print(f"Saved {item['sample_id']} qa={row['qa_status']} status={row['status']} cached={was_cached} retained_success={retained}", flush=True)
                    if after_commit:
                        after_commit(item, row)
                    if pause_seconds and not reparse_cache:
                        time.sleep(pause_seconds)
        except KeyboardInterrupt:
            interrupted = True
            append_note(run_dir, "Interrupted. Committed rows are durable; complete cached responses can be recovered on resume. No successful result was removed.")
        finally:
            try:
                summary = export_outputs(conn, run_dir, manifest_hash, backups, items)
            finally:
                conn.close()
        summary["interrupted"] = interrupted
        summary["pending_input_urls"] = len(items) - summary["result_rows"]
        return summary

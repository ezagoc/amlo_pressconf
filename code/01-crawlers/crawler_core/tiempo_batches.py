"""Frozen, operator-gated batches around the unchanged <=80-URL pilot.

No discovery, shared-data replacement, automatic manual PASS, or run-all mode.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import shutil
import sqlite3
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from crawler_core import tiempo_pilot as pilot
from crawler_core.tiempo_review import fields_digest

MAX_BATCHES_PER_INVOCATION = 10
RETRY_GROUPS = {"access_denied", "rate_limit", "server_error", "transport", "source_gap", "system_quality", "http_other"}


class BatchError(pilot.PilotError):
    """Invalid or changed batch evidence; no further requests are permitted."""


def _read(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise BatchError(f"Duplicate JSON key in {path}: {key}")
            result[key] = value
        return result
    try:
        result = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
        if not isinstance(result, dict):
            raise BatchError(f"Expected a JSON object in {path}.")
        return result
    except (ValueError, OSError) as exc:
        raise BatchError(f"Cannot read {path}: {exc}") from exc


def _sha(path):
    return pilot.digest(path.read_bytes())


def _hash(value):
    return pilot.digest(pilot.json_bytes(value))


def _program_hashes():
    directory = Path(__file__).resolve().parent
    names = ("tiempo_batches.py", "tiempo_pilot.py", "tiempo_review.py", "tiempo_html.py", "sitemap_articles.py", "capabilities.py")
    return {name: _sha(directory / name) for name in names}


def _write(root, relative, value):
    pilot.atomic_bytes(pilot.safe_path(root, relative), pilot.json_bytes(value))


def _transport_events(directory):
    path = pilot.safe_path(directory, "transport_calls.jsonl")
    if not path.exists():
        return []
    try:
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    except ValueError as exc:
        raise BatchError("Transport call log is incomplete; preserve and reconcile it before resume.") from exc


def _read_transport_clock(root, plan):
    path = pilot.safe_path(root, "transport_clock.json")
    if not path.exists():
        return None
    clock = _read(path)
    reference = clock.get("finished_epoch", clock.get("started_epoch"))
    if clock.get("plan_sha256") != plan["plan_sha256"] or type(reference) not in (int, float) or not math.isfinite(reference):
        raise BatchError("Transport clock is invalid; preserve and reconcile it before resume.")
    return reference


def _csv_bytes(headers, rows):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=headers, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


def _queue(content):
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    headers = reader.fieldnames or []
    required = {"sample_id", "url", "expected_year", "selection_reason", "expected_kind"}
    if len(headers) != len(set(headers)) or not required.issubset(headers):
        raise BatchError("Queue requires unique headers: " + ", ".join(sorted(required)))
    rows, ids, urls = [], set(), set()
    for row in reader:
        if None in row or any(v is None for v in row.values()):
            raise BatchError("Malformed queue CSV row.")
        row = {k: v.strip() for k, v in row.items()}
        row["url"] = pilot.normalized_input_url(row["url"])
        if not row["sample_id"] or row["sample_id"] in ids or row["url"] in urls:
            raise BatchError("Duplicate/empty sample ID or duplicate normalized URL in full queue.")
        ids.add(row["sample_id"])
        urls.add(row["url"])
        rows.append(row)
    if not rows:
        raise BatchError("Empty queue.")
    return headers, rows


def freeze_plan(input_path, run_dir, media_root, *, repo_root=None, batch_size=40,
                pause_seconds=1.0, timeout=45.0, min_free_bytes=10 * 1024**3,
                max_consecutive_system_errors=3, max_system_error_fraction=0.25,
                error_fraction_min_results=8, min_reviewed_per_batch=3):
    """Freeze full metadata and <=80-row CSVs; never requests a URL."""
    for name, value, minimum in (("batch_size", batch_size, 1), ("min_free_bytes", min_free_bytes, 1),
                                 ("max_consecutive_system_errors", max_consecutive_system_errors, 1),
                                 ("error_fraction_min_results", error_fraction_min_results, 1),
                                 ("min_reviewed_per_batch", min_reviewed_per_batch, 1)):
        if type(value) is not int or value < minimum:
            raise BatchError(f"Invalid {name}.")
    if batch_size > pilot.MAX_URLS or min_reviewed_per_batch > batch_size:
        raise BatchError("batch_size must be <=80 and >= min_reviewed_per_batch.")
    if not all(math.isfinite(x) for x in (pause_seconds, timeout, max_system_error_fraction)) or pause_seconds < 1 or timeout <= 0 or not 0 < max_system_error_fraction <= 1:
        raise BatchError("Require pause>=1 second, positive timeout, error fraction in (0,1].")
    root = pilot.validate_run_dir(Path(run_dir), Path(media_root), repo_root)
    settings = {"batch_size": batch_size, "pause_seconds": pause_seconds, "timeout": timeout,
                "min_free_bytes": min_free_bytes, "max_consecutive_system_errors": max_consecutive_system_errors,
                "max_system_error_fraction": max_system_error_fraction, "error_fraction_min_results": error_fraction_min_results,
                "min_reviewed_per_batch": min_reviewed_per_batch}
    content = Path(input_path).read_bytes()
    headers, rows = _queue(content)
    with pilot.exclusive_run(root):
        if (root / "plan.json").exists():
            previous = load_plan(root)
            if previous["source_queue_sha256"] != pilot.digest(content) or previous["settings"] != settings:
                raise BatchError("Frozen queue/settings changed; create a new independent plan.")
            return previous
        if any(x.name not in {"Kevin_NOTE.md", ".pilot.lock"} for x in root.iterdir()):
            raise BatchError("Plan directory must initially contain only Kevin_NOTE.md.")
        batches = []
        for start in range(0, len(rows), batch_size):
            part = rows[start:start + batch_size]
            name = f"batch_{len(batches) + 1:06d}"
            rel = f"batches/{name}/inputs/sample_manifest.csv"
            data = _csv_bytes(headers, part)
            batches.append({"batch_id": name, "ordinal": len(batches), "input_path": rel,
                            "input_sha256": pilot.digest(data), "row_count": len(part),
                            "sample_ids": [r["sample_id"] for r in part]})
        plan = {"format_version": 1, "author": "Kevin", "created_at": pilot.now(),
                "source_id": "tiempo", "source_queue_sha256": pilot.digest(content),
                "queue_sha256": pilot.digest(_csv_bytes(headers, rows)), "settings": settings,
                "row_count": len(rows), "batches": batches, "program_sha256": _program_hashes()}
        plan["plan_sha256"] = _hash(plan)
        # Plan is written last; interrupted initialization remains visibly partial.
        pilot.atomic_bytes(pilot.safe_path(root, "source_queue.csv"), content)
        pilot.atomic_bytes(pilot.safe_path(root, "queue.csv"), _csv_bytes(headers, rows))
        for batch, start in zip(batches, range(0, len(rows), batch_size)):
            pilot.atomic_bytes(pilot.safe_path(root, batch["input_path"]), _csv_bytes(headers, rows[start:start + batch_size]))
            note = f"# Kevin\nIndependent Tiempo batch {batch['batch_id']}. Frozen plan {plan['plan_sha256']}.\nShared outputs untouched.\n"
            pilot.atomic_bytes(pilot.safe_path(root, f"batches/{batch['batch_id']}/Kevin_NOTE.md"), note.encode())
        _write(root, "plan.json", plan)
        pilot.append_note(root, f"Froze {len(rows)} queue URLs in {len(batches)} bounded batches; plan {plan['plan_sha256']}.")
    return plan


def load_plan(run_dir):
    root = Path(run_dir).resolve()
    plan = _read(pilot.safe_path(root, "plan.json"))
    unsigned = dict(plan)
    binding = unsigned.pop("plan_sha256", None)
    if plan.get("format_version") != 1 or binding != _hash(unsigned):
        raise BatchError("Plan hash/schema mismatch.")
    if plan.get("program_sha256") != _program_hashes():
        raise BatchError("Frozen execution/parser code changed; restore its version or create a new plan.")
    for name, key in (("queue.csv", "queue_sha256"), ("source_queue.csv", "source_queue_sha256")):
        if _sha(pilot.safe_path(root, name)) != plan[key]:
            raise BatchError(f"Frozen {name} changed.")
    headers, rows = _queue((root / "queue.csv").read_bytes())
    offset = 0
    for ordinal, batch in enumerate(plan["batches"]):
        expected_id = f"batch_{ordinal + 1:06d}"
        if batch["batch_id"] != expected_id or batch["input_path"] != f"batches/{expected_id}/inputs/sample_manifest.csv":
            raise BatchError("Unexpected batch identity/path.")
        path = pilot.safe_path(root, batch["input_path"])
        items, sha = pilot.load_input(path)
        expected = rows[offset:offset + batch["row_count"]]
        if sha != batch["input_sha256"] or path.read_bytes() != _csv_bytes(headers, expected) or [r["sample_id"] for r in items] != batch["sample_ids"]:
            raise BatchError("Batch does not match frozen full queue.")
        offset += len(items)
    if offset != len(rows) or offset != plan["row_count"]:
        raise BatchError("Frozen queue row count mismatch.")
    state_path = pilot.safe_path(root, "state.json")
    if state_path.exists() and _read(state_path).get("plan_sha256") != binding:
        raise BatchError("State belongs to another plan.")
    return plan


def error_group(row):
    if row.get("qa_status") == "success":
        return None
    status, error = row.get("status"), str(row.get("error") or "")
    if status == 403:
        return "access_denied"
    if status == 429:
        return "rate_limit"
    if isinstance(status, int) and 500 <= status <= 599:
        return "server_error"
    if error == "soft_error_page":
        return "source_gap"
    # This is still an error with a null title, never a successful article or a
    # manual review. A verified, otherwise intact source template can omit its
    # title; preserve that separate from an unexplained extraction failure.
    if error == "missing_title" and status == 200 and row.get("source_title_status") == "confirmed_source_empty":
        try:
            evidence = json.loads(row.get("source_title_evidence") or "null")
        except (ValueError, TypeError):
            evidence = None
        if (isinstance(evidence, dict) and evidence.get("recognized_empty_h1") is True
                and evidence.get("all_title_channels_empty") is True
                and not row.get("title") and not row.get("source_specific_error")
                and not row.get("date_conflict")
                and all(row.get(k) for k in ("main_text", "date_published", "canonical_url", "publication_date_source"))):
            return "source_gap"
    if error.startswith("transport_error"):
        return "transport"
    if error.startswith("http_status"):
        return "http_other"
    return "system_quality"


def inspect_batch(root, batch):
    """Read and validate current DB/snapshots/exports. No implicit review PASS."""
    root = Path(root)
    directory = pilot.safe_path(root, f"batches/{batch['batch_id']}")
    result = {"batch_id": batch["batch_id"], "row_count": batch["row_count"],
              "execution_status": "pending", "review_status": "not_reviewed", "rows": []}
    if not (directory / "manifest.json").exists():
        if (directory / "pilot.sqlite").exists():
            raise BatchError("Unbound batch database.")
        return result
    items, input_sha = pilot.load_input(root / batch["input_path"])
    manifest = _read(directory / "manifest.json")
    if manifest.get("input_sha256") != input_sha or manifest.get("items") != items or manifest.get("source_id") != "tiempo" or manifest.get("format_version") != 1:
        raise BatchError("Batch manifest does not match its frozen input.")
    if pilot.can_finish_initialization(directory, manifest):
        return {**result, "execution_status": "incomplete"}
    if not (directory / "pilot.sqlite").is_file():
        raise BatchError("Initialized batch database is missing.")
    with sqlite3.connect((directory / "pilot.sqlite").as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        pilot.validate_bound_state(conn, directory, items, input_sha)
        rows = [json.loads(r[0]) for r in conn.execute("SELECT payload_json FROM articles ORDER BY ordinal")]
        attempts = conn.execute("SELECT count(*),sum(network_request),sum(completed_at IS NULL) FROM fetch_attempts").fetchone()
    rows, reviews = pilot.reviewed_rows(rows, directory)
    errors = Counter(error_group(r) for r in rows if r["qa_status"] != "success")
    complete = len(rows) == batch["row_count"] and not attempts[2]
    exports = None
    if (directory / "export_manifest.json").exists():
        exports = _read(directory / "export_manifest.json")
        for name, value in exports["files"].items():
            if _sha(pilot.safe_path(directory, name)) != value["sha256"]:
                raise BatchError("Batch export hash mismatch; use pilot --export-only before approval.")
        if exports["result_rows"] != len(rows) or exports["manual_review"]["annotation_file_sha256"] != reviews["annotation_file_sha256"]:
            exports = None  # Current sidecar/DB requires a fresh export before the gate.
    result.update(execution_status=("complete_with_errors" if errors else "complete") if complete else "incomplete",
                  result_rows=len(rows), successful_url_rows=sum(r["qa_status"] == "success" for r in rows),
                  error_groups=dict(errors), error_sample_ids=[r["sample_id"] for r in rows if r["qa_status"] != "success"],
                  unique_article_rows=exports["article_rows"] if exports else None,
                  pilot_fetch_entries=int(attempts[1] or 0), transport_calls_started=len(_transport_events(directory)),
                  incomplete_attempts=int(attempts[2] or 0),
                  manual_review_counts=reviews["status_counts"], rows=rows,
                  auto_checks_passed=bool(complete and exports))
    current = reviews["status_counts"].get("reviewed", 0)
    result["review_status"] = "reviewed" if current == len(rows) and rows else "partially_reviewed" if current else "not_reviewed"
    if exports:
        result["evidence_sha256"] = _hash({"input_sha256": input_sha, "files": exports["files"],
                                          "reviews": exports["manual_review"], "result_rows": len(rows)})
    return result


def _signed(record):
    if not isinstance(record.get("reviewer"), str) or not record["reviewer"].strip() or not isinstance(record.get("note"), str) or not record["note"].strip():
        raise BatchError("Operator record needs reviewer and explanatory note.")
    try:
        stamp = datetime.fromisoformat(record["reviewed_at"].replace("Z", "+00:00"))
        if stamp.utcoffset() is None:
            raise ValueError()
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise BatchError("Operator record needs a timezone-aware reviewed_at.") from exc


def _approved(root, plan, batch, summary):
    path = pilot.safe_path(root, f"approvals/{batch['batch_id']}.json")
    if not path.exists():
        return False
    record = _read(path)
    _signed(record)
    if not summary.get("auto_checks_passed") or any(record.get(k) != v for k, v in {
        "format_version": 1, "decision": "proceed", "plan_sha256": plan["plan_sha256"],
        "batch_id": batch["batch_id"], "input_sha256": batch["input_sha256"],
        "evidence_sha256": summary.get("evidence_sha256")}.items()):
        raise BatchError("Approval is stale, incomplete, or belongs to another batch.")
    reviewed = record.get("reviewed_sample_ids")
    if not isinstance(reviewed, list) or not all(isinstance(x, str) for x in reviewed) or len(reviewed) != len(set(reviewed)):
        raise BatchError("Approval needs unique reviewed_sample_ids.")
    eligible = {r["sample_id"] for r in summary["rows"] if r["manual_review_status"] == "reviewed" and r["manual_review_result"] in {"PASS", "PASS_SOURCE_GAP_RECORDED"}}
    minimum = min(plan["settings"]["min_reviewed_per_batch"], batch["row_count"])
    if len(reviewed) < minimum or not set(reviewed).issubset(eligible):
        raise BatchError("Approval lacks enough currently bound, passing manual spot checks.")
    if any(r["manual_review_status"] == "stale" or r.get("manual_review_result") in {"FAIL", "REQUIRES_REVIEW"} for r in summary["rows"]):
        raise BatchError("Resolve stale/failed/pending manual findings before proceeding.")
    accepted = record.get("accepted_error_groups")
    if not isinstance(accepted, list) or not all(isinstance(x, str) for x in accepted) or len(accepted) != len(set(accepted)) or set(accepted) != set(summary["error_groups"]):
        raise BatchError("Approval must explicitly acknowledge every existing error group.")
    return True


def _state(root, plan, status, summaries, **extra):
    result = {"format_version": 1, "plan_sha256": plan["plan_sha256"], "updated_at": pilot.now(),
              "status": status, "batch_count": len(plan["batches"]), "queue_rows": plan["row_count"],
              "batches": [{k: v for k, v in s.items() if k != "rows"} for s in summaries], **extra}
    _write(root, "state.json", result)
    return result


def _row_evidence_key(row):
    return _hash({k: row.get(k) for k in ("sample_id", "url", "snapshot_sha256", "qa_status", "error", "status")} |
                 {"fields_sha256": fields_digest(row)})


def _check_safety(row, counters, settings):
    group = error_group(row)
    error = str(row.get("error") or "")
    counters["total"] += 1
    systemic = group in {"system_quality", "transport", "http_other"}
    counters["system"] += int(systemic)
    counters["consecutive"] = counters["consecutive"] + 1 if systemic else 0
    if group in {"access_denied", "rate_limit", "server_error"}:
        return {"reason": "http_stop", "status": row.get("status"), "url": row["url"]}
    if error in {"unrecognized_tiempo_layout", "unrecognized_tiempo_body", "invalid_article_canonical",
                 "ambiguous_jsonld_article", "conflicting_publication_dates", "invalid_publication_date",
                 "missing_verified_publication_date", "non_html_response", "empty_html_response"} or error.startswith("parser_error"):
        return {"reason": "format_or_date_error", "sample_id": row["sample_id"], "error": error}
    if counters["consecutive"] >= settings["max_consecutive_system_errors"] or (
        counters["total"] >= settings["error_fraction_min_results"] and
        counters["system"] / counters["total"] >= settings["max_system_error_fraction"]):
        return {"reason": "system_error_threshold", "sample_id": row["sample_id"], "counters": dict(counters)}
    return {}


def _record_halt(root, plan, batch, stop):
    event = {"plan_sha256": plan["plan_sha256"], "batch_id": batch["batch_id"], "at": pilot.now(), **stop}
    items, _ = pilot.load_input(root / batch["input_path"])
    stopped_item = next((r for r in items if r["sample_id"] == stop.get("sample_id") or r["url"] == stop.get("url")), None)
    if stopped_item is not None:
        event.update(stop_sample_id=stopped_item["sample_id"], stop_ordinal=stopped_item["ordinal"])
    event_sha = _hash(event)
    _write(root, f"halts/{event_sha}.json", event)
    cursor = _read(root / "halt_cursor.json") if (root / "halt_cursor.json").exists() else {}
    _write(root, "halt_cursor.json", {**cursor, "plan_sha256": plan["plan_sha256"], "active_halt_sha256": event_sha})
    return event_sha


def _resolved_prefix(root, plan, batch, rows):
    cursor = _read(root / "halt_cursor.json") if (root / "halt_cursor.json").exists() else {}
    resolution = cursor.get("resolutions", {}).get(batch["batch_id"])
    if not resolution:
        return 0
    keys = resolution["row_keys"]
    if not isinstance(keys, list) or keys != [_row_evidence_key(r) for r in rows[:len(keys)]]:
        raise BatchError("Previously resolved result prefix changed; investigate instead of skipping safety checks.")
    auth = pilot.safe_path(root, f"resume_authorizations/{resolution['halt_sha256']}.json")
    if _sha(auth) != resolution["authorization_sha256"]:
        raise BatchError("Prior safety resolution authorization changed or disappeared.")
    return len(keys)


def run_batches(run_dir, media_root, *, repo_root=None, max_batches=1, fetcher=None, parser=None):
    """Bounded invocation; approvals control transitions, never generated here."""
    if type(max_batches) is not int or not 1 <= max_batches <= MAX_BATCHES_PER_INVOCATION:
        raise BatchError("max_batches must be 1–10; there is no run-all mode.")
    root = pilot.validate_run_dir(Path(run_dir), Path(media_root), repo_root)
    with pilot.exclusive_run(root):
        plan = load_plan(root)
        # Fail before creating any pilot attempt: the pilot deliberately catches
        # ordinary fetch exceptions, so damaged control state is not a URL error.
        _read_transport_clock(root, plan)
        previous = _read(root / "state.json") if (root / "state.json").exists() else {}
        cursor = _read(root / "halt_cursor.json") if (root / "halt_cursor.json").exists() else {}
        if cursor and cursor.get("plan_sha256") != plan["plan_sha256"]:
            raise BatchError("Safety cursor belongs to another plan.")
        halt_sha = cursor.get("active_halt_sha256") if cursor else previous.get("active_halt_sha256")
        if halt_sha:
            event = _read(pilot.safe_path(root, f"halts/{halt_sha}.json"))
            if _hash(event) != halt_sha or event.get("plan_sha256") != plan["plan_sha256"]:
                raise BatchError("Safety halt evidence is missing or changed.")
            auth = pilot.safe_path(root, f"resume_authorizations/{halt_sha}.json")
            if not auth.exists():
                summaries = [inspect_batch(root, b) for b in plan["batches"]]
                return _state(root, plan, "halted", summaries, active_halt_sha256=halt_sha)
            record = _read(auth)
            _signed(record)
            if record.get("plan_sha256") != plan["plan_sha256"] or record.get("halt_sha256") != halt_sha or record.get("decision") != "resume":
                raise BatchError("Invalid halt resolution.")
            halted_batch = next((b for b in plan["batches"] if b["batch_id"] == event["batch_id"]), None)
            if halted_batch is None:
                raise BatchError("Safety halt names an unknown batch.")
            existing = [r for r in inspect_batch(root, halted_batch)["rows"] if r["ordinal"] <= event.get("stop_ordinal", -1)]
            resolutions = dict(cursor.get("resolutions", {}))
            resolutions[event["batch_id"]] = {"row_keys": [_row_evidence_key(r) for r in existing],
                "last_sample_id": existing[-1]["sample_id"] if existing else None,
                "last_ordinal": existing[-1]["ordinal"] if existing else None,
                "halt_sha256": halt_sha, "authorization_sha256": _sha(auth)}
            pilot.append_note(root, f"Operator resolved halt {halt_sha}; errors remain recorded, no automatic retries.")
            _write(root, "halt_cursor.json", {"plan_sha256": plan["plan_sha256"], "active_halt_sha256": None,
                                             "last_resolved_halt_sha256": halt_sha, "resolutions": resolutions})
        settings, summaries, executed = plan["settings"], [], 0
        for batch in plan["batches"]:
            directory = pilot.safe_path(root, f"batches/{batch['batch_id']}")
            summary = inspect_batch(root, batch)
            counters = {"consecutive": 0, "system": 0, "total": 0}
            prefix = _resolved_prefix(root, plan, batch, summary["rows"])
            # A process may die after SQLite commits but before after_commit.
            # Replay saved results before any new URL; counters survive restart.
            for row in summary["rows"][prefix:]:
                replay_stop = _check_safety(row, counters, settings)
                if replay_stop:
                    event_sha = _record_halt(root, plan, batch, {**replay_stop, "replayed_committed_result": True})
                    summaries.append(summary)
                    return _state(root, plan, "halted", summaries, active_halt_sha256=event_sha)
            complete = summary["execution_status"].startswith("complete")
            if not complete:
                if executed >= max_batches:
                    return _state(root, plan, "invocation_limit", summaries)
                stop = {}
                persisted_stop = {}

                def record_stop():
                    if not persisted_stop:
                        persisted_stop["sha256"] = _record_halt(root, plan, batch, stop)

                def guarded_fetch(url, timeout, **kwargs):
                    if shutil.disk_usage(directory).free < settings["min_free_bytes"]:
                        stop.update(reason="low_disk_space", url=url)
                        record_stop()
                        raise KeyboardInterrupt()
                    # Pilot post-commit sleep normally satisfies the gap. Only
                    # fill a remaining gap at a batch/process transition or halt.
                    try:
                        reference = _read_transport_clock(root, plan)
                    except (BatchError, OSError):
                        stop.update(reason="invalid_transport_clock", url=url)
                        record_stop()
                        raise KeyboardInterrupt()
                    if reference is not None:
                        delay = min(settings["pause_seconds"], max(0, settings["pause_seconds"] - (time.time() - reference)))
                        if delay:
                            time.sleep(delay)
                    started = time.time()
                    _write(root, "transport_clock.json", {"plan_sha256": plan["plan_sha256"], "started_epoch": started})
                    event = {"plan_sha256": plan["plan_sha256"], "url": url, "started_at": pilot.now(), "started_epoch": started}
                    with pilot.safe_path(directory, "transport_calls.jsonl").open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
                        stream.flush()
                        os.fsync(stream.fileno())
                    try:
                        if fetcher is None:
                            from crawler_core.capabilities import fetch
                            response = fetch(url, timeout, **kwargs)
                        else:
                            response = fetcher(url, timeout, **kwargs)
                    finally:
                        _write(root, "transport_clock.json", {"plan_sha256": plan["plan_sha256"], "started_epoch": started, "finished_epoch": time.time()})
                    status = pilot.clean(response.get("status"))
                    if status in {403, 429} or isinstance(status, int) and 500 <= status <= 599:
                        stop.update(reason="http_stop", status=status, url=url)
                        record_stop()
                    return response

                def after_commit(item, row):
                    stop.update(_check_safety(row, counters, settings))
                    if stop:
                        record_stop()
                        raise KeyboardInterrupt()  # pilot commits first, then exports in finally

                outcome = pilot.run_pilot(root / batch["input_path"], directory, Path(media_root),
                    repo_root=repo_root, pause_seconds=settings["pause_seconds"], timeout=settings["timeout"],
                    fetcher=guarded_fetch, parser=parser, after_commit=after_commit)
                executed += 1
                summary = inspect_batch(root, batch)
                if stop:
                    summaries.append(summary)
                    return _state(root, plan, "halted", summaries, active_halt_sha256=persisted_stop["sha256"])
                if outcome["interrupted"]:
                    summaries.append(summary)
                    return _state(root, plan, "interrupted", summaries)
            # Export-only is needed after adding a review sidecar; callers can
            # run the pilot command explicitly, without requesting pages.
            approved = _approved(root, plan, batch, summary)
            summary["operator_gate"] = "approved" if approved else "awaiting_review"
            summaries.append(summary)
            if not approved:
                return _state(root, plan, "awaiting_review", summaries)
        return _state(root, plan, "all_batches_operator_accepted", summaries)


def status(run_dir):
    """Read-only current state; does not request, export, approve, or change rows."""
    root = Path(run_dir).resolve()
    plan = load_plan(root)
    summaries = [inspect_batch(root, b) for b in plan["batches"]]
    return {"plan_sha256": plan["plan_sha256"], "row_count": plan["row_count"],
            "batches": [{k: v for k, v in s.items() if k != "rows"} for s in summaries]}


def retry_queue(run_dir, groups):
    """Export a separate selected retry queue; never retries original batches."""
    groups = sorted(set(groups))
    if not groups or not set(groups).issubset(RETRY_GROUPS):
        raise BatchError("Select known retry groups explicitly.")
    root = Path(run_dir).resolve()
    with pilot.exclusive_run(root):
        plan = load_plan(root)
        headers, queue = _queue((root / "queue.csv").read_bytes())
        selected = {}
        for batch in plan["batches"]:
            for row in inspect_batch(root, batch)["rows"]:
                if error_group(row) in groups:
                    selected[row["sample_id"]] = row
        rows = [r for r in queue if r["sample_id"] in selected]
        if not rows:
            raise BatchError("No current error results in selected retry groups.")
        data = _csv_bytes(headers, rows)
        path = pilot.safe_path(root, f"retry_queues/{'_'.join(groups)}_{pilot.digest(data)[:16]}.csv")
        if path.exists() and path.read_bytes() != data:
            raise BatchError("Retry queue hash collision.")
        if not path.exists():
            pilot.atomic_bytes(path, data)
        return path

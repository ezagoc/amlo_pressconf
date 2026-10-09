"""Kevin: validate and atomically publish one immutable actual-AI receipt.

This helper does not read articles, create an approval, fix receipt fields, or
change the frozen gate validator. Readers supply their complete real evidence
outside receipts/. A valid technical-blocker receipt is published so collection
stops; schema/integrity errors are rejected before becoming collector-visible.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from crawler_core import tiempo_stage_review as review


PUBLISH_SCHEMA = 'tiempo-atomic-ai-receipt-publication-v1'
_ALLOWED_STATUSES = {'collection_gate_satisfied', 'blocked_pending_actual_ai_reading',
                     'blocked_technical_review'}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        _require(key not in obj, 'Duplicate JSON field: ' + key)
        obj[key] = value
    return obj


def _bad_constant(value):
    raise ValueError('Non-finite JSON constant: ' + value)


def _load_candidate(candidate, receipts):
    if isinstance(candidate, dict):
        # JSON round trip detaches caller-owned nested objects and rejects NaN.
        data = json.dumps(candidate, ensure_ascii=False, allow_nan=False).encode('utf-8')
    else:
        path = Path(candidate).resolve(strict=True)
        _require(path != receipts and receipts not in path.parents,
                 'Candidate must be outside the watched receipts directory')
        data = path.read_bytes()
    doc = json.loads(data, object_pairs_hook=_unique_object, parse_constant=_bad_constant)
    _require(isinstance(doc, dict), 'Receipt must be a JSON object')
    return doc


def _schema(doc):
    required = ('schema', 'selection_sha256', 'runtime_binding_sha256', 'actual_ai_read_ids',
                'actual_ai_read_count', 'human_approval', 'technical_blockers', 'records')
    _require(all(key in doc for key in required), 'Receipt required fields missing')
    _require(type(doc['actual_ai_read_count']) is int, 'Actual AI reading count must be an integer')
    _require(isinstance(doc['actual_ai_read_ids'], list) and
             all(isinstance(sid, str) and sid for sid in doc['actual_ai_read_ids']),
             'Actual AI reading IDs must be strings in a list')
    _require(isinstance(doc['records'], list) and bool(doc['records']),
             'Receipt must contain at least one actual reading record')
    for item in [doc] + doc['records']:
        _require(isinstance(item, dict), 'Reading record must be an object')
        _require(isinstance(item.get('technical_blockers'), list) and
                 all(isinstance(x, str) and bool(x.strip()) for x in item['technical_blockers']),
                 'Technical blockers must be an explicit list of nonempty strings')
    fields = ('sample_id', 'snapshot_sha256', 'payload_sha256', 'row_check_sha256',
              'actual_ai_read', 'human_approval', 'note', 'scope', 'technical_blockers', 'research_status')
    for record in doc['records']:
        _require(all(key in record for key in fields), 'Reading record required fields missing')
        _require(record['research_status'] is None or record['research_status'] == 'NEEDS_JOAQUIN_REVIEW',
                 'research_status must be null or NEEDS_JOAQUIN_REVIEW; no automatic conversion')


def _bindings(paths):
    bindings = []
    for path in paths:
        _require(not path.is_symlink() and path.is_file(), 'Published receipt must be a regular non-symlink file')
        bindings.append((str(path), hashlib.sha256(path.read_bytes()).hexdigest()))
    return bindings


def _sync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _exclusive_publish(staged, final):
    # Same-filesystem hard-link is atomic and fails if final already exists.
    # os.replace would overwrite immutable prior reading evidence.
    os.link(staged, final)


def publish_receipt(selection_path, candidate, filename):
    """Publish supplied real evidence once, returning the combined gate status.

    Candidate is a JSON object or an existing draft outside receipts/. No fields
    are repaired/coerced. An exception after the exclusive link can mean the
    complete receipt is already visible: inspect final before any next action,
    never replace it. A process interruption can leave only an unwatched draft.
    """
    _require(isinstance(filename, str) and len(filename) <= 128 and
             re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.json', filename) is not None and
             '..' not in filename,
             'Invalid receipt filename; use one simple .json basename')
    selection = Path(selection_path).resolve(strict=True)
    _require(selection.is_file(), 'Selection must be a file')
    folder = selection.parent
    receipts = folder / 'receipts'
    _require(not receipts.is_symlink(), 'Watched receipts directory cannot be a symlink')
    receipts.mkdir(exist_ok=True)
    doc = _load_candidate(candidate, receipts)
    _schema(doc)
    data = (json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    final = receipts / filename
    staging = folder / '.receipt_staging'
    _require(not staging.is_symlink(), 'Receipt staging directory cannot be a symlink')
    staging.mkdir(exist_ok=True)
    lock_path = folder / '.receipt_publication.lock'
    _require(not lock_path.is_symlink(), 'Receipt publication lock cannot be a symlink')
    staged = None
    with lock_path.open('a+b') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            _require(not final.exists() and not final.is_symlink(), 'Immutable receipt already exists: ' + str(final))
            fd, temp_name = tempfile.mkstemp(prefix='candidate_', suffix='.tmp', dir=staging)
            staged = Path(temp_name)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            paths = sorted(receipts.glob('*.json'))
            before = _bindings(paths)
            # This unchanged gate verifies schema, actual reads, source hashes,
            # runtime, selection, counts and duplicate IDs across both readers.
            gate = review.validate_gate(selection, paths + [staged])
            _require(gate.get('integrity_error') is False and gate.get('status') in _ALLOWED_STATUSES,
                     'Receipt publication rejected: ' + json.dumps(gate, ensure_ascii=False))
            _require(paths == sorted(receipts.glob('*.json')) and before == _bindings(paths),
                     'Published receipts changed during validation')
            _exclusive_publish(staged, final)
            _sync_dir(receipts)
            return {'schema': PUBLISH_SCHEMA, 'author': 'Kevin', 'receipt': str(final),
                    'receipt_sha256': hashlib.sha256(data).hexdigest(), 'status': 'published_immutable',
                    'combined_gate_status': gate['status'], 'gate': gate,
                    'new_reading_claims_created_by_helper': 0, 'human_approval': False}
        finally:
            # Never remove other writers' drafts or any published receipt.
            if staged is not None:
                staged.unlink(missing_ok=True)
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection', required=True)
    parser.add_argument('--candidate', required=True, help='Complete draft JSON outside watched receipts/')
    parser.add_argument('--name', required=True, help='Immutable final basename, e.g. reviewer_even.json')
    args = parser.parse_args(argv)
    try:
        result = publish_receipt(args.selection, args.candidate, args.name)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({'status': 'publication_failed_inspect_final_before_retry',
                          'error': type(exc).__name__ + ': ' + str(exc), 'human_approval': False}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

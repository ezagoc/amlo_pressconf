"""Offline, immutable AI source-reading gate for closed Tiempo checkpoints.

This sidecar supplements the native pending-source-review obligations. It never
writes native rows, annotations, their not_reviewed state, or source files. A
receipt is an explicit record of an external AI reader's actual work; this
module performs no AI call and cannot infer a reading from automated checks.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit

from crawler_core import tiempo_continuous_v5 as w

SCHEMA = 'tiempo-focused-ai-source-review-v1'
COVERAGE_SCHEMA = 'tiempo-actual-ai-coverage-seal-v1'
MIN_SAMPLES = 4  # Includes one reproducible random sample, plus novel strata.
READ_SCOPE = ('Full saved article lead/body, relevant title channels, identity, '
              'publication evidence and embedded-media links; no external fetch.')


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _bound(path):
    path = Path(path).resolve()
    w.require(path.is_file(), 'Missing review evidence: ' + str(path))
    return {'path': str(path), 'sha256': w.sha_file(path)}


def _verify(binding):
    w.require(_bound(binding['path']) == binding, 'Review evidence changed: ' + binding['path'])


def _sealed(doc, key):
    obj = dict(doc)
    claimed = obj.pop(key, None)
    w.require(claimed == w.digest(obj), 'Invalid ' + key)
    return obj


def _save_once(path, doc):
    path = Path(path)
    if path.exists():
        w.require(w.load(path) == doc, 'Frozen review selection cannot be resampled or overwritten')
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        w.write(path.parent, path.name, doc)


def _strings(value):
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except ValueError:
            pass
        return [value] if value else []
    return [str(x) for x in (value or [])]


def strata(row, check, origin):
    """Individual dimensions, deliberately not the native joint signatures."""
    pub = str(row.get('date_published') or '')
    discovery = str(origin.get('discovery_day') or check.get('discovery_day') or '')
    route = check.get('route') or urlsplit(row.get('canonical_url') or '').path.strip('/').split('/')[0]
    tokens = {
        'publication_year:' + (pub[:4] or 'unknown'),
        'publication_month:' + (pub[:7] or 'unknown'),
        'discovery_year:' + (discovery[:4] or 'unknown'),
        'discovery_month:' + (discovery[:7] or 'unknown'),
        'route:' + (route or 'unknown'),
        'section:' + str(row.get('section') or row.get('topic') or 'unknown'),
        'page_type:' + str(row.get('article_kind') or check.get('collection_outcome') or 'unknown'),
        'title:' + ('present' if row.get('title') else 'missing'),
        'length:' + ('very_short' if len(row.get('main_text') or '') < 200 else
                     'short' if len(row.get('main_text') or '') < 600 else 'regular'),
        'queue_class:' + str(origin.get('queue_class') or 'unknown'),
        'identity_class:' + str(origin.get('identity_class') or 'unknown'),
    }
    for value in _strings(origin.get('baseline_classes_json')):
        tokens.add('corpus_origin:' + value)
    media = _strings(row.get('media_embeds'))
    for url in media:
        host = urlsplit(url).hostname
        if host:
            tokens.add('media_host:' + host.lower())
    tokens.add('media:' + ('present' if media else 'absent'))
    for observed in check.get('observed_types', []):
        if not observed.startswith('layout:'):
            continue
        layout = json.loads(observed[len('layout:'):])
        for flag in ('table', 'list', 'body_heading', 'social_quote'):
            if layout.get(flag):
                tokens.add('page_feature:' + flag)
        if layout.get('article_count', 1) > 1:
            tokens.add('page_feature:nested_article')
    # Known conversation markup is a source question, not an automatic anomaly.
    # Its first observed category requires reading; the individual repeated IDs
    # retain their native source-judgment state without invented full reading.
    for value in set(check.get('source_judgment_flags', [])) | set(check.get('source_markup_warnings', [])):
        tokens.add('source_judgment:' + value)
    return sorted(tokens)


def _plan(child):
    plan_path = child / 'continuous_plan.json'
    plan = w.load(plan_path)
    _sealed(plan, 'plan_sha256')
    w.require(w.sha_file(child / 'queue.csv') == plan['queue_sha256'], 'Queue changed')
    queue = w.readcsv(child / 'queue.csv')
    w.require(len(queue) == plan['row_count'] and len({r['sample_id'] for r in queue}) == len(queue),
              'Queue count or sample identities invalid')
    return plan, queue


def _batch_rows(child, batch, origins, bindings):
    B = child / 'batches' / batch['batch_id']
    db_path = B / 'pilot.sqlite'
    before = _bound(db_path)
    with sqlite3.connect(db_path.as_uri() + '?mode=ro&immutable=1', uri=True) as db:
        sql = db.execute('SELECT payload_json FROM articles ORDER BY ordinal').fetchall()
    w.require(_bound(db_path) == before, 'Native database changed during selection')
    bindings.append(before)
    rows = [json.loads(r[0]) for r in sql]
    w.require(len(rows) == batch['row_count'] and [r['sample_id'] for r in rows] == batch['sample_ids'],
              'Review requires complete, closed native batches')
    out = []
    for row, (payload,) in zip(rows, sql):
        sid = row['sample_id']
        w.require(sid in origins and row['url'] == origins[sid]['url'], 'Native row differs from queue identity')
        raw = _bound(B / row['snapshot_path'])
        check_binding = _bound(child / 'row_checks' / (sid + '.json'))
        check_doc = w.load(check_binding['path'])
        check = check_doc['record']
        w.require(raw['sha256'] == row['snapshot_sha256'] == check.get('snapshot_sha256') and
                  check.get('sample_id') == sid and check.get('fields_sha256') == w.fields_digest(row),
                  'Raw, payload and automatic check disagree')
        origin = {key: origins[sid].get(key) for key in ('queue_class', 'identity_class', 'route',
                  'discovery_day', 'baseline_classes_json', 'baseline_record_ids_json',
                  'source_quality_issues_json')}
        flags = sorted(set(check.get('automatic_flags', [])) | set(check.get('critical_flags', [])) |
                       set(check.get('unexplained_flags', [])))
        out.append({'sample_id': sid, 'url': row['url'], 'batch_id': batch['batch_id'],
                    'snapshot_path': raw['path'], 'snapshot_sha256': raw['sha256'],
                    'payload_sha256': _sha(payload.encode()), 'row_check': check_binding,
                    'row_check_sha256': check_binding['sha256'], 'strata': strata(row, check, origin),
                    'origin': origin, 'automatic_flags': flags,
                    'critical_flags': check.get('critical_flags', []),
                    'publication_date': row.get('date_published'),
                    'native_manual_review_status': 'not_reviewed'})
    return out


def _closed(child, checkpoint_rows, previous_checkpoint_rows=None):
    child = Path(child).resolve()
    plan, queue = _plan(child)
    w.require(plan.get('program_sha256') == w.program_hashes(), 'Frozen worker program changed')
    w.require(type(checkpoint_rows) is int and 0 < checkpoint_rows <= plan['row_count'] and
              (checkpoint_rows % 400 == 0 or checkpoint_rows == plan['row_count']),
              'AI gate requires a 400-row boundary or the final remainder')
    start = (checkpoint_rows - 1) // 400 * 400 if previous_checkpoint_rows is None else previous_checkpoint_rows
    w.require(type(start) is int and 0 <= start < checkpoint_rows and
              checkpoint_rows - start <= 400 and start % 80 == 0,
              'Invalid checkpoint segment start')
    summary_path = child / f'checkpoint_{checkpoint_rows:08d}' / 'summary.json'
    summary = w.load(summary_path)
    w.require(summary['rows'] == checkpoint_rows and summary['plan_sha256'] == plan['plan_sha256'] and
              summary.get('actual_manual_reviews') == 0, 'Checkpoint summary is not bound to native rows')
    native_pending = summary_path.parent / 'pending_source_review_samples.csv'
    w.require(w.sha_file(native_pending) == summary['pending_samples_sha256'], 'Native pending review file changed')
    pending = w.readcsv(native_pending)
    w.require(len(pending) == summary['pending_source_review_sample_count'] and
              all(r.get('manual_review_status') == 'not_reviewed' for r in pending),
              'Native pending review duties changed')
    bindings = [_bound(child / 'continuous_plan.json'), _bound(child / 'queue.csv'), _bound(summary_path),
                _bound(native_pending)]
    origins = {r['sample_id']: r for r in queue}
    summaries = {s['batch_id']: s for s in summary['batch_checks']}
    all_rows, offset = [], 0
    for batch in plan['batches']:
        end = offset + batch['row_count']
        if end > checkpoint_rows:
            break
        w.require(batch['batch_id'] in summaries, 'Closed batch is absent from checkpoint checks')
        check_summary = summaries[batch['batch_id']]
        check_file = _bound(check_summary['check_path'])
        w.require(check_file['sha256'] == check_summary['check_sha256'] and
                  check_summary['batch_input_complete'] is True, 'Automatic batch checks changed')
        bindings.append(check_file)
        if end > start:
            w.require(offset >= start, 'Review segment splits a native batch')
            current = _batch_rows(child, batch, origins, bindings)
            for r in current:
                w.require(w.load(r['row_check']['path'])['plan_sha256'] == plan['plan_sha256'],
                          'Row automatic check belongs to another plan')
            all_rows.extend(current)
        offset = end
    w.require(offset == checkpoint_rows and len(all_rows) == checkpoint_rows - start,
              'Checkpoint is not a complete saved prefix')
    return {'child': str(child), 'plan_sha256': plan['plan_sha256'], 'checkpoint_rows': checkpoint_rows,
            'previous_checkpoint_rows': start, 'bindings': bindings, 'rows': all_rows,
            'native_pending_obligation': {'binding': _bound(native_pending), 'record_count': len(pending),
              'status': 'unresolved_native_pending_source_review',
              'rule': 'Preserved original semantics and not_reviewed state; this focused gate does not discharge these duties.'}}


def _read_record(record):
    w.require(record.get('actual_ai_read') is True and record.get('human_approval') is False,
              'A reading must explicitly attest actual AI work and no human approval')
    w.require(isinstance(record.get('note'), str) and len(record['note'].strip()) >= 40 and
              isinstance(record.get('scope'), str) and bool(record['scope'].strip()),
              'Actual AI source-reading note and scope required')
    w.require(isinstance(record.get('technical_blockers'), list), 'Explicit technical blocker list required')


def _legacy_history(item):
    receipt_binding = _bound(item['receipt'])
    doc = w.load(item['receipt'])
    w.require(doc.get('human_approval') is False and doc.get('technical_blockers') == [],
              'Historical reading receipt is not technically clear')
    child = Path(item['child']).resolve()
    plan, queue = _plan(child)
    origins = {r['sample_id']: r for r in queue}
    records = doc.get('records', [])
    ids = [r['sample_id'] for r in records]
    w.require(len(ids) == len(set(ids)) and doc.get('actual_ai_read_count') == len(ids) and
              doc.get('actual_ai_read_ids') == ids, 'Historical AI reading count/identities disagree')
    needed = set(ids)
    bindings = [receipt_binding, _bound(child / 'continuous_plan.json'), _bound(child / 'queue.csv')]
    candidates = {}
    for batch in plan['batches']:
        if needed.intersection(batch['sample_ids']):
            candidates.update({r['sample_id']: r for r in _batch_rows(child, batch, origins, bindings)})
    result = []
    for record in records:
        _read_record(record)
        w.require(record['technical_blockers'] == [] and record['sample_id'] in candidates,
                  'Historical AI evidence has unresolved technical blockers or missing native row')
        current = candidates[record['sample_id']]
        for key in ('snapshot_sha256', 'payload_sha256'):
            w.require(record.get(key) == current[key], 'Historical AI reading source changed')
        result.append({**current, 'reading_receipt': receipt_binding,
                       'reading_note_sha256': _sha(record['note'].encode())})
    # Native DB/raw bindings above were actually checked at this import. The
    # immutable receipt is the persistent reading proof; do not rehash all old
    # native batches each time a later checkpoint is polled.
    return result, [receipt_binding]


def _compact(row):
    return {key: row[key] for key in ('sample_id', 'snapshot_path', 'snapshot_sha256',
            'payload_sha256', 'row_check_sha256', 'strata', 'reading_receipt',
            'reading_note_sha256')}


def _coverage(path):
    doc = w.load(path)
    _sealed(doc, 'coverage_sha256')
    w.require(doc.get('schema') == COVERAGE_SCHEMA and doc.get('human_approval') is False and
              doc.get('gate_status') == 'collection_gate_satisfied', 'Invalid AI coverage seal')
    records = doc['records']
    ids = [r['sample_id'] for r in records]
    w.require(ids == sorted(set(ids)) and ids == doc['distinct_actual_ai_read_ids'],
              'Coverage seal actual-reading identities disagree')
    receipt_map = {b['path']: b for b in doc['receipt_bindings']}
    for binding in doc['receipt_bindings'] + doc['previous_seals']:
        _verify(binding)
    for record in records:
        w.require(record['reading_receipt'] == receipt_map.get(record['reading_receipt']['path']) and
                  len(record['reading_note_sha256']) == 64,
                  'Coverage seal lacks explicit source-reading evidence')
    w.require(doc['covered_strata'] == sorted({s for r in records for s in r['strata']}),
              'Coverage seal strata changed')
    return doc


def _history(items):
    records, bindings, seen_items, seals = {}, [], set(), []
    for item in items:
        key = str(Path(item.get('coverage') or item['receipt']).resolve())
        if item.get('sha256') is not None:
            w.require(w.sha_file(key) == item['sha256'], 'Bound history receipt/seal changed')
        if key in seen_items:
            continue
        seen_items.add(key)
        if 'coverage' in item:
            coverage = _coverage(item['coverage'])
            seal_binding = _bound(item['coverage'])
            sources = coverage['records']
            bindings.extend([seal_binding, *coverage['receipt_bindings']])
            seals.append(seal_binding)
        elif 'selection' in item:
            gate = require_gate(item['selection'], [item['receipt']])
            selection = w.load(item['selection'])
            receipt = _bound(item['receipt'])
            bindings.extend([_bound(item['selection']), receipt])
            notes = {r['sample_id']: _sha(r['note'].encode()) for r in w.load(item['receipt'])['records']}
            # Compatibility import validates only this checkpoint. Its embedded
            # history is already compact; no recursive gate replay occurs.
            sources = selection['history']['records'] + [
                {**r, 'reading_receipt': receipt, 'reading_note_sha256': notes[r['sample_id']]}
                for r in selection['selected_records'] if r['sample_id'] in notes]
            bindings.extend(selection['history']['bindings'])
        else:
            sources, bound = _legacy_history(item)
            bindings.extend(bound)
        for row in sources:
            identity = row['sample_id']
            if identity in records:
                w.require(all(records[identity][k] == row[k] for k in
                              ('snapshot_sha256', 'payload_sha256', 'strata')),
                          'Conflicting historical source evidence for same sample ID')
            else:
                records[identity] = _compact(row)
    unique = {b['path']: b for b in bindings}
    return {'records': sorted(records.values(), key=lambda r: r['sample_id']),
            'bindings': sorted(unique.values(), key=lambda b: b['path']),
            'coverage_seals': seals,
            'distinct_actual_ai_read_ids': sorted(records),
            'rule': 'Only source-bound explicit actual AI receipts contribute coverage; no all-year certification.'}


def _obligations(path):
    binding = _bound(path)
    doc = w.load(path)
    lists = []
    def visit(value, pointer=''):
        if isinstance(value, dict):
            for key, nested in value.items():
                visit(nested, pointer + '/' + key)
        elif isinstance(value, list):
            if any(word in pointer.rsplit('/', 1)[-1] for word in ('pending', 'selections', 'obligations')):
                lists.append({'json_pointer': pointer, 'records': len(value)})
            for index, nested in enumerate(value):
                visit(nested, pointer + '/' + str(index))
    visit(doc)
    return {'binding': binding, 'original_list_counts': lists,
            'status': 'preserved_unresolved_no_discharge_or_reclassification',
            'rule': 'Read original document for each duty; overlapping/nested lists are not a unique total.'}


def select_checkpoint(child, output_dir, *, checkpoint_rows, inherited_obligations,
                      history_receipts=(), previous_checkpoint_rows=None):
    """Freeze selection once; a restart verifies and returns the exact same IDs.

    Legacy history items are {receipt, child}; new ones are {receipt, selection}.
    history_receipts is explicit, never discovered from a mutable directory.
    """
    output = Path(output_dir).resolve() / f'selection_{checkpoint_rows:08d}.json'
    request = {'child': str(Path(child).resolve()), 'checkpoint_rows': checkpoint_rows,
               'inherited_obligations': str(Path(inherited_obligations).resolve()),
               'history_receipts': [dict(i) for i in history_receipts],
               'previous_checkpoint_rows': previous_checkpoint_rows}
    if output.exists():
        existing = _validate_selection(output)
        w.require(existing['request'] == request, 'Restart inputs differ from frozen review selection')
        return {**existing, 'selection_path': str(output)}
    snapshot = _closed(child, checkpoint_rows, previous_checkpoint_rows)
    history = _history(history_receipts)
    historic = {r['sample_id']: r for r in history['records']}
    covered_strata = {s for r in historic.values() for s in r['strata']}
    rows = snapshot['rows']
    rank = lambda row: _sha((snapshot['plan_sha256'] + '\n' + str(checkpoint_rows) + '\n' + row['sample_id']).encode())
    selected = {}
    def add(row, reason):
        selected.setdefault(row['sample_id'], {'row': row, 'reasons': []})['reasons'].append(reason)
    for row in rows:
        if row['automatic_flags']:
            add(row, 'all_current_automatic_anomalies')
    random = min(rows, key=rank)
    add(random, 'deterministic_random')
    novel = {s for r in rows for s in r['strata']} - covered_strata
    while True:
        selection_coverage = {s for chosen in selected.values() for s in chosen['row']['strata']}
        remaining = novel - selection_coverage
        if not remaining:
            break
        best = min((r for r in rows if r['sample_id'] not in selected),
                   key=lambda r: (-len(set(r['strata']) & remaining), rank(r)))
        add(best, 'new_individual_strata:' + ','.join(sorted(set(best['strata']) & remaining)))
    for row in sorted(rows, key=rank):
        if len(selected) >= min(MIN_SAMPLES, len(rows)):
            break
        if row['sample_id'] not in selected:
            add(row, 'four_source_checkpoint_floor')
    selected_rows = []
    for row in rows:
        if row['sample_id'] not in selected:
            continue
        old = historic.get(row['sample_id'])
        if old:
            w.require(all(old[k] == row[k] for k in ('snapshot_sha256', 'payload_sha256')),
                      'Previously read ID has changed raw or payload evidence')
        unchanged = old is not None and old['row_check_sha256'] == row['row_check_sha256'] and old['strata'] == row['strata']
        selected_rows.append({**row, 'selection_reasons': selected[row['sample_id']]['reasons'],
                              'reused_actual_ai_read': unchanged})
    doc = {'schema': SCHEMA, 'request': request, 'snapshot': snapshot,
           'code_binding': {'review_module': _bound(__file__), 'worker_program': w.program_hashes()},
           'inherited_obligations': _obligations(inherited_obligations), 'history': history,
           'sampling_rule': {'minimum_distinct_current_sources': MIN_SAMPLES,
                             'deterministic_random_included': 1,
                             'additional': 'all current automatic anomalies and greedy new individual strata',
                             'joint_signature_sampling': False},
           'selected_records': selected_rows, 'selected_ids': [r['sample_id'] for r in selected_rows],
           'native_manual_review_status': 'not_reviewed', 'human_approval': False,
           'article_acceptance': False, 'receipt_schema': SCHEMA,
           'required_read_scope': READ_SCOPE}
    doc['selection_sha256'] = w.digest(doc)
    _save_once(output, doc)
    return {**doc, 'selection_path': str(output)}


def _validate_selection(path):
    doc = w.load(path)
    _sealed(doc, 'selection_sha256')
    w.require(doc.get('schema') == SCHEMA and doc.get('human_approval') is False,
              'Invalid focused review selection')
    _verify(doc['code_binding']['review_module'])
    w.require(doc['code_binding']['worker_program'] == w.program_hashes(), 'Review worker code changed')
    for binding in doc['snapshot']['bindings'] + doc['history']['bindings']:
        _verify(binding)
    _verify(doc['inherited_obligations']['binding'])
    # Closed current DBs and automatic summaries bind every current row. Only
    # required selected raw/check sources are reread when a receipt arrives.
    # Prior validated coverage is reused via seals/receipt hashes, not by
    # replaying old corpus files or historical review gates.
    for row in doc['selected_records']:
        w.require(w.sha_file(row['snapshot_path']) == row['snapshot_sha256'], 'Selected/history raw source changed')
        _verify(row['row_check'])
    return doc


def validate_gate(selection_path, receipt_paths=()):
    """Return fail-closed status; no receipt never means automatic approval.

    Receipt top-level fields: schema, selection_sha256, runtime_binding_sha256,
    actual_ai_read_ids, actual_ai_read_count, human_approval=False,
    technical_blockers=[], records. Each record has sample_id, snapshot_sha256,
    payload_sha256, row_check_sha256, actual_ai_read=True, human_approval=False,
    note, scope, technical_blockers=[], research_status (null or
    NEEDS_JOAQUIN_REVIEW). No PASS label is accepted or manufactured.
    """
    try:
        doc = _validate_selection(selection_path)
        expected = {r['sample_id']: r for r in doc['selected_records']}
        historical_ids = set(doc['history']['distinct_actual_ai_read_ids'])
        reused = {r['sample_id'] for r in doc['selected_records'] if r['reused_actual_ai_read']}
        covered, blockers, seen = set(reused), [], set()
        for path in receipt_paths:
            receipt = w.load(path)
            w.require(receipt.get('schema') == SCHEMA and
                      receipt.get('selection_sha256') == doc['selection_sha256'] and
                      receipt.get('runtime_binding_sha256') == w.digest(doc['snapshot']['bindings']) and
                      receipt.get('human_approval') is False,
                      'AI receipt selection/runtime/no-human binding mismatch')
            w.require(isinstance(receipt.get('technical_blockers'), list), 'Receipt technical blockers required')
            blockers.extend(receipt['technical_blockers'])
            records = receipt.get('records', [])
            ids = [r['sample_id'] for r in records]
            w.require(len(ids) == len(set(ids)) and receipt.get('actual_ai_read_ids') == ids and
                      receipt.get('actual_ai_read_count') == len(ids), 'AI receipt IDs/count disagree')
            for record in records:
                _read_record(record)
                sid = record['sample_id']
                w.require(sid in expected and sid not in seen, 'Receipt has unselected or duplicate reading ID')
                seen.add(sid)
                for key in ('snapshot_sha256', 'payload_sha256', 'row_check_sha256'):
                    w.require(record.get(key) == expected[sid][key], 'AI receipt source/check hash mismatch')
                w.require(record.get('research_status') in (None, 'NEEDS_JOAQUIN_REVIEW'),
                          'A collection receipt cannot assert research/human PASS')
                blockers.extend(record['technical_blockers'])
                if not record['technical_blockers']:
                    covered.add(sid)
        # Source/transport critical flags cannot be waived by merely writing a
        # narrative. A halted child still requires the separate repair process.
        critical = [r['sample_id'] for r in doc['snapshot']['rows'] if r['critical_flags']]
        if critical:
            blockers.append('native_critical_source_flags:' + ','.join(critical))
        if (Path(doc['snapshot']['child']) / 'safety_halt.json').exists():
            blockers.append('native_safety_halt_present')
        missing = sorted(set(expected) - covered)
        status = ('blocked_technical_review' if blockers else 'blocked_pending_actual_ai_reading' if missing
                  else 'collection_gate_satisfied')
        result = {'schema': SCHEMA, 'selection_sha256': doc['selection_sha256'],
                  'status': status, 'integrity_error': False, 'awaiting_ai_readings': bool(missing and not blockers),
                  'selected_ids': sorted(expected), 'covered_ids': sorted(covered), 'missing_ids': missing,
                  'reused_actual_ai_read_ids': sorted(reused), 'new_actual_ai_read_ids': sorted(seen - historical_ids),
                  'new_actual_ai_read_count': len(seen - historical_ids),
                  'reread_historical_ids': sorted(seen & historical_ids), 'technical_blockers': blockers,
                  'native_pending_obligation': doc['snapshot']['native_pending_obligation'],
                  'human_approval': False, 'article_acceptance': False}
        return result
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        return {'schema': SCHEMA, 'status': 'blocked_invalid_evidence',
                'integrity_error': True, 'awaiting_ai_readings': False,
                'technical_blockers': [type(exc).__name__ + ': ' + str(exc)],
                'human_approval': False, 'article_acceptance': False}


def require_gate(selection_path, receipt_paths=()):
    result = validate_gate(selection_path, receipt_paths)
    w.require(result['status'] == 'collection_gate_satisfied', 'AI source-review gate blocked: ' + json.dumps(result))
    return result


def seal_gate(selection_path, receipt_paths, output_path):
    """Seal only an actually satisfied gate for efficient subsequent coverage.

    New selections accept history_receipts=[{'coverage': output_path}]. The
    seal stores only source hashes, individual strata, reading receipt/note
    hashes, distinct IDs and the immediate previous seal link. No old corpus
    replay is required; a changed prior receipt or seal still fails closed.
    """
    receipt_bindings = [_bound(p) for p in receipt_paths]
    gate = require_gate(selection_path, receipt_paths)
    selection = w.load(selection_path)
    records = {r['sample_id']: r for r in selection['history']['records']}
    selected = {r['sample_id']: r for r in selection['selected_records']}
    for binding in receipt_bindings:
        _verify(binding)
        receipt = w.load(binding['path'])
        for record in receipt['records']:
            sid = record['sample_id']
            if sid not in records or sid in gate['reread_historical_ids']:
                records[sid] = _compact({**selected[sid], 'reading_receipt': binding,
                                        'reading_note_sha256': _sha(record['note'].encode())})
    w.require(set(gate['selected_ids']).issubset(records), 'Cannot seal missing actual AI readings')
    all_receipts = {r['reading_receipt']['path']: r['reading_receipt'] for r in records.values()}
    for binding in all_receipts.values():
        _verify(binding)
    doc = {'schema': COVERAGE_SCHEMA, 'gate_status': gate['status'],
           'selection_binding': _bound(selection_path), 'selection_sha256': selection['selection_sha256'],
           'records': sorted(records.values(), key=lambda r: r['sample_id']),
           'distinct_actual_ai_read_ids': sorted(records),
           'covered_strata': sorted({s for r in records.values() for s in r['strata']}),
           'receipt_bindings': sorted(all_receipts.values(), key=lambda b: b['path']),
           'previous_seals': selection['history']['coverage_seals'],
           'new_actual_ai_read_count': gate['new_actual_ai_read_count'],
           'native_pending_obligation': selection['snapshot']['native_pending_obligation'],
           'inherited_obligations': selection['inherited_obligations'],
           'human_approval': False, 'article_acceptance': False,
           'scope_limit': 'Only listed individual actual AI readings, not all articles/years or human approval.'}
    doc['coverage_sha256'] = w.digest(doc)
    _save_once(output_path, doc)
    return {**doc, 'coverage_path': str(Path(output_path).resolve())}

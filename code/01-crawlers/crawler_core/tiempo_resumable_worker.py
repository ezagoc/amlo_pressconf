"""Kevin's pause-aware adapter for a separately frozen continuation runtime.

The existing parser, pilot, transport policy and source checker are unchanged.
The supervisor must bind this adapter's hash as well as the v5 plan. A pause is
an audited, resumable boundary; a technical halt remains terminal and immutable.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import math
import signal
import sqlite3
import threading
import time
import types

from . import tiempo_continuous_v5 as w

SCHEMA = 'tiempo-resumable-worker-v1'
PAUSED = 'paused_safe'
INHERITED_FAILURE_SCHEMA = 'tiempo-inherited-terminal-failure-v1'
# Rendering uses the frozen function body independently of a test-injected
# interruption at the actual export call; all preview writes are suppressed.
_NATIVE_EXPORT_OUTPUTS = w.pilot.export_outputs


def inherited_prefix_evidence(root, plan, prefix_rows):
    """Read exact native payload/attempt evidence in frozen input order."""
    root = Path(root).resolve()
    w.require(type(prefix_rows) is int and 0 < prefix_rows <= plan['row_count'],
              'Invalid inherited prefix length')
    payloads, attempts, articles, rows, total = [], [], [], [], 0
    for batch in plan['batches']:
        path = root / 'batches' / batch['batch_id'] / 'pilot.sqlite'
        if not path.exists():
            continue
        with sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True) as db:
            db.row_factory = sqlite3.Row
            saved = db.execute('SELECT * FROM articles ORDER BY ordinal').fetchall()
            total += len(saved)
            for saved_row in saved:
                if len(rows) >= prefix_rows:
                    break
                payload = saved_row['payload_json']; row = json.loads(payload)
                attempt = db.execute('SELECT * FROM fetch_attempts WHERE attempt_id=?',
                                     (row['attempt_id'],)).fetchone()
                w.require(attempt is not None and attempt['completed_at'] and
                          attempt['sample_id'] == row['sample_id'] and attempt['url'] == row['url'] and
                          attempt['action'] == 'fetch', 'Inherited native attempt is incomplete or changed')
                payloads.append(payload); attempts.append(dict(attempt)); articles.append(dict(saved_row))
                rows.append({'batch_id': batch['batch_id'], 'row': row})
    expected = [sid for batch in plan['batches'] for sid in batch['sample_ids']][:prefix_rows]
    w.require([item['row']['sample_id'] for item in rows] == expected,
              'Inherited rows are not the exact frozen input prefix')
    return {'prefix_payload_sha256': w.digest(payloads),
            'prefix_attempts_sha256': w.digest(attempts),
            'prefix_articles_sha256': w.digest(articles), 'rows': rows, 'articles': articles,
            'payloads': payloads, 'attempts': attempts, 'total_rows': total}


def validated_inherited_failure_ack(root, plan, binding=None):
    """Validate the one imported terminal failure without changing its evidence.

    The signed successor supplies this binding explicitly. Native plan and
    imported ledger bytes remain identical to the immutable donor. This helper
    reads small controls/DB prefixes and the failed response; ordinary worker
    reconciliation verifies all transport snapshots before any new request.
    """
    if binding is None:
        return None
    root = Path(root).resolve()
    path = Path(binding['path']).resolve()
    w.require(w.sha_file(path) == binding['sha256'], 'Inherited acknowledgment changed')
    ack = w.load(path)
    w.require(ack.get('schema') == INHERITED_FAILURE_SCHEMA and
              ack.get('target_root') == str(root) and type(ack.get('synthetic_fixture')) is bool,
              'Inherited acknowledgment identity changed')
    donor = Path(ack['donor_root']).resolve()
    master = Path(ack['donor_campaign_root']).resolve()
    w.require(donor != root and donor not in root.parents and root not in donor.parents and
              master != root and master not in root.parents and root not in master.parents,
              'Recovery namespace must be disjoint from its donor')
    evidence = ack['donor_bindings']; failure = ack['failure']
    halt_path = donor / 'safety_halt.json'; halt_sha = w.sha_file(halt_path)
    required = [donor / name for name in ('continuous_plan.json', 'continuous_state.json',
                'safety_halt.json', 'transport_calls.jsonl', 'transport_state.json')]
    required += [donor / 'halt_receipts' / (halt_sha + '.json'),
                 donor / 'row_checks' / (failure['sample_id'] + '.json'), master / 'technical_stop.json']
    w.require(all(str(p) in evidence for p in required), 'Missing immutable donor control binding')
    for filename, sha in evidence.items():
        w.require(w.sha_file(filename) == sha, 'Inherited donor evidence changed: ' + filename)
    donor_plan = w.load(donor / 'continuous_plan.json')
    w.require(donor_plan == plan and w.sha_file(root / 'continuous_plan.json') ==
              evidence[str(donor / 'continuous_plan.json')], 'Imported native plan changed')
    halt = w.load(halt_path); state = w.load(donor / 'continuous_state.json')
    master_halt = w.load(master / 'technical_stop.json')
    w.require(halt.get('plan_sha256') == plan['plan_sha256'] and
              halt.get('reason') == 'critical_source_or_access_failure' and
              halt.get('sample_id') == failure['sample_id'] and
              state.get('status') == 'halted_no_automatic_resume' and state.get('halt_sha256') == halt_sha and
              w.load(donor / 'halt_receipts' / (halt_sha + '.json')) == halt and
              master_halt.get('reason') == 'native_worker_stopped' and
              master_halt.get('native_result', {}).get('halt_sha256') == halt_sha,
              'Donor terminal halt does not authorize this retained failure')
    if not ack['synthetic_fixture']:
        w.require(failure['sample_id'] == 'TC5_495573' and
                  failure['attempt_id'] == '87f7b4ae3fe74d38ba1835a56baa61b9' and
                  failure['url'] == 'https://www.tiempo.com.mx/noticia/posverdad_columna_politica_1_julio_2025/' and
                  plan['plan_sha256'] == 'bad8e8eec1eaff8a3b818587764959ef8a327f3442530eea52827a8fdc766728' and
                  halt_sha == '6a4df85fbcba652c27188de7a78c8828ee501972bd3459749d4745e3f998823f' and
                  evidence[str(master / 'technical_stop.json')] ==
                  '122848c71868449625b2752cb1a0854985d6a2813d16a1402d0aeae09cb5c2e1' and
                  ack['prefix_rows'] == 391 and ack['prefix_calls'] == 392,
                  'Only the frozen October 8 connection failure may be acknowledged')
    old = inherited_prefix_evidence(donor, plan, ack['prefix_rows'])
    current = inherited_prefix_evidence(root, plan, ack['prefix_rows'])
    w.require(old['total_rows'] == ack['prefix_rows'] and
              state.get('result_rows') == ack['prefix_rows'] and
              master_halt['native_result'].get('result_rows') == ack['prefix_rows'],
              'Donor retained prefix count changed')
    for key in ('prefix_payload_sha256', 'prefix_attempts_sha256', 'prefix_articles_sha256'):
        w.require(old[key] == current[key] == ack[key], 'Inherited native prefix changed: ' + key)
    entries = w._ledger(root, plan); donor_entries = w._ledger(donor, plan)
    w.require(type(ack['prefix_calls']) is int and ack['prefix_calls'] > 0 and
              len(donor_entries) == 2 * ack['prefix_calls'] and
              entries[:len(donor_entries)] == donor_entries and
              b''.join((root / 'transport_calls.jsonl').read_bytes().splitlines(keepends=True)[:len(donor_entries)]) ==
              (donor / 'transport_calls.jsonl').read_bytes(), 'Inherited transport prefix changed')
    item = current['rows'][-1]; row = item['row']; attempt = current['attempts'][-1]
    w.require(item['batch_id'] == failure['batch_id'] and
              all(row.get(k) == failure[k] for k in ('sample_id', 'url', 'attempt_id', 'snapshot_sha256')) and
              hashlib.sha256(current['payloads'][-1].encode()).hexdigest() == failure['payload_sha256'] and
              row.get('qa_status') == 'error' and attempt.get('qa_status') == 'error',
              'Acknowledged failure is not the exact final inherited record')
    for base in (donor, root):
        check = w.load(base / 'row_checks' / (failure['sample_id'] + '.json'))
        record = check['record']
        raw = base / 'batches' / failure['batch_id'] / row['snapshot_path']
        w.require(check['plan_sha256'] == plan['plan_sha256'] and
                  w.digest(record) == failure['row_check_record_sha256'] and
                  record.get('critical_flags') == ['critical_transport'] and
                  record.get('collection_outcome') == 'critical_failure' and
                  record.get('collection_quality_status') == w.QUARANTINE and
                  record.get('manual_review_status') == 'not_reviewed' and
                  w.sha_file(raw) == failure['snapshot_sha256'], 'Inherited failure/check/raw evidence changed')
    calls = [e for e in donor_entries if e['event'] == 'start' and e['attempt_id'] == failure['attempt_id']]
    w.require(len(calls) == 2 and calls[-1]['sequence'] == ack['prefix_calls'],
              'Acknowledged connection failure has a different retry chain')
    for index, event in enumerate(calls):
        old_receipt, _ = w._transport_receipt(donor, event)
        receipt, response = w._transport_receipt(root, event)
        w.require(receipt == old_receipt and receipt['retry_index'] == index and
                  receipt['terminal'] is bool(index) and
                  receipt['response_kind'] == ('critical_transport' if index else 'retryable_service') and
                  response.get('curl_exit_code') == (7 if index else 28) and
                  response.get('status') == 0 and response.get('text') == '',
                  'Inherited connection failure terminal response changed')
    return ack


def _acknowledged_replay(ack, row, record):
    return bool(ack and row['sample_id'] == ack['failure']['sample_id'] and
                row['attempt_id'] == ack['failure']['attempt_id'] and
                w.digest(record) == ack['failure']['row_check_record_sha256'])


class StopController:
    """A signal handler only records intent; it never interrupts a live request."""
    def __init__(self):
        self.requested = False
        self.signal_number = None

    def request(self, signum=None, frame=None):
        self.requested = True
        self.signal_number = signum

    def __call__(self):
        return self.requested


@contextmanager
def graceful_signals(controller):
    """Install on the main thread and restore the caller's original handlers."""
    w.require(threading.current_thread() is threading.main_thread(),
              'Signal handlers require the main thread')
    old = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        for sig in old:
            signal.signal(sig, controller.request)
        yield controller
    finally:
        for sig, handler in old.items():
            signal.signal(sig, handler)


def _pending_count(root, plan):
    count = 0
    for batch in plan['batches']:
        path = root / 'batches' / batch['batch_id'] / 'pilot.sqlite'
        if path.exists():
            with sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True) as db:
                count += db.execute('SELECT count(*) FROM fetch_attempts WHERE completed_at IS NULL').fetchone()[0]
    return count


def _pilot_with_prebegin(before_begin, *args, **kwargs):
    """Reuse the frozen pilot body with one invocation-local pre-insert hook.

    A private globals dictionary avoids changing a module or process-wide
    function. The original pilot start_attempt and every other operation retain
    their implementations. A cached response already owns its logical request,
    so adopting that response is permitted after a pause request.
    """
    original = w.pilot.run_pilot
    original_start = w.pilot.start_attempt

    def start_attempt(*a, **kw):
        if not kw.get('recovering'):
            before_begin()
        return original_start(*a, **kw)

    namespace = dict(original.__globals__, start_attempt=start_attempt)
    call = types.FunctionType(original.__code__, namespace, original.__name__,
                              original.__defaults__, original.__closure__)
    call.__kwdefaults__ = original.__kwdefaults__
    return call(*args, **kwargs)


def _native_check(root, media, plan, batch, rows, records):
    """Exports have already passed preflight or were produced by this invocation."""
    return w._batch_check(root, batch, rows, records)


def _export_preview(B, items, manifest_hash, *, prefix_rows=None):
    """Render a native generation without changing any on-disk byte.

    A certified older prefix is rendered from an in-memory SQLite copy retaining
    its article rows and completed logical attempts. This proves the manifest's
    accounting as well as its native file hashes after a later commit.
    """
    original = _NATIVE_EXPORT_OUTPUTS
    namespace = dict(original.__globals__, atomic_bytes=lambda *a, **k: None,
                     review_context=lambda directory, **kw: w.pilot.review_context(directory, persist=False))
    call = types.FunctionType(original.__code__, namespace, original.__name__,
                              original.__defaults__, original.__closure__)
    call.__kwdefaults__ = original.__kwdefaults__
    class NoBackups:
        def ensure(self, *args):
            pass
    with sqlite3.connect((B / 'pilot.sqlite').as_uri() + '?mode=ro&immutable=1', uri=True) as db:
        db.row_factory = sqlite3.Row
        if prefix_rows is None:
            return call(db, B, manifest_hash, NoBackups(), items)
        with sqlite3.connect(':memory:') as prior:
            db.backup(prior)
            prior.row_factory = sqlite3.Row
            kept = prior.execute('SELECT url,payload_json FROM articles ORDER BY ordinal LIMIT ?',
                                 (prefix_rows,)).fetchall()
            w.require(len(kept) == prefix_rows and prefix_rows > 0, 'Certified SQL prefix is missing')
            marks = ','.join('?' for _ in kept)
            prior.execute('DELETE FROM articles WHERE url NOT IN (' + marks + ')',
                          [row['url'] for row in kept])
            prior.execute('DELETE FROM fetch_attempts WHERE attempt_id NOT IN (' + marks + ')',
                          [json.loads(row['payload_json'])['attempt_id'] for row in kept])
            w.require(prior.execute('SELECT count(*) FROM fetch_attempts WHERE completed_at IS NOT NULL').fetchone()[0]
                      == prefix_rows, 'Certified native attempts changed')
            return call(prior, B, manifest_hash, NoBackups(), items)


def _export_preflight(root, media, batch, rows):
    """Verify prior certified bytes before a pilot can replace native exports.

    More committed DB rows or a reconciled terminal pending attempt prove an
    interrupted export is possible, but are not permission to erase arbitrary
    bytes. Each extant native file must match
    either its certified old version or a read-only render of the current DB.
    A manifest already present at certification may never disappear.
    """
    B = root / 'batches' / batch['batch_id']
    if not (B / 'pilot.sqlite').exists():
        return
    # The caller has already reconciled every pending attempt with its durable
    # terminal transport response. No uncertain or interrupted retry chain can
    # reach this branch. Pilot's finally block may export that pending attempt
    # without increasing the number of committed article rows.
    with sqlite3.connect((B / 'pilot.sqlite').as_uri() + '?mode=ro&immutable=1', uri=True) as db:
        pending = db.execute('SELECT count(*) FROM fetch_attempts WHERE completed_at IS NULL').fetchone()[0]
    certificates = []
    for path in (root / 'automatic_checks' / batch['batch_id']).glob('*/check.json'):
        check = w.load(path)
        unsigned = {k: v for k, v in check.items() if k != 'derived_files'}
        w.require(w.digest(unsigned) == path.parent.name and check['batch_id'] == batch['batch_id'] and
                  check['input_sha256'] == batch['input_sha256'], 'Existing batch certificate changed')
        for name, sha in check['derived_files'].items():
            w.require(w.sha_file(w.pilot.safe_path(path.parent, name)) == sha, 'Certified derived export changed')
        w.require(check['rows'] <= len(rows), 'Committed rows lost since their certified export')
        for row, record in zip(rows, check['records']):
            w.require(row['sample_id'] == record['sample_id'] and
                      row['snapshot_sha256'] == record['snapshot_sha256'] and
                      w.fields_digest(row) == record['fields_sha256'], 'Certified committed prefix changed')
        certificates.append(check)
    certified = max(certificates, key=lambda c: c['rows']) if certificates else None
    manifest_path = B / 'export_manifest.json'
    old = w.load(manifest_path) if manifest_path.exists() else None
    if old:
        review = old.get('manual_review', {})
        count = old.get('result_rows')
        w.require(type(count) is int and 0 <= count <= len(rows) and
                  old.get('source_id') == 'tiempo' and old.get('manifest_sha256') == batch['input_sha256'],
                  'Native export manifest identity/count changed')
        w.require(review.get('annotation_file_present') is False and
                  review.get('annotation_file_sha256') is None and
                  review.get('annotation_count') == 0 and review.get('row_count') == count and
                  review.get('source_warning_rows') == 0 and
                  review.get('status_counts') == {'not_reviewed': count, 'reviewed': 0, 'stale': 0} and
                  all(review.get(k) == [] for k in ('annotation_history_sha256', 'annotation_sample_ids', 'unused_annotation_ids')),
                  'Native export review state changed; preserve before any rewrite')
        keys = ('article_rows', 'successful_url_rows', 'canonical_alias_rows', 'canonical_collision_groups',
                'error_results', 'attempt_rows', 'network_fetch_calls_started', 'incomplete_attempts', 'retained_result_rows')
        w.require(all(type(old.get(k)) is int and old[k] >= 0 for k in keys) and
                  old['retained_result_rows'] == count and
                  old['successful_url_rows'] + old['error_results'] == count and
                  old['article_rows'] + old['canonical_alias_rows'] == old['successful_url_rows'] and
                  old['canonical_collision_groups'] <= old['article_rows'] and
                  old['attempt_rows'] == count + old['incomplete_attempts'] and
                  old['network_fetch_calls_started'] == old['attempt_rows'],
                  'Native export accounting changed; preserve before any rewrite')
    if certified:
        w.require(old is not None, 'Previously certified export manifest is missing')
    # A pristine initialized pilot has no exported data to restore. Pending
    # snapshots are reconciled separately and will be exported on adoption.
    if not rows and old is None and not any((B / n).exists() for n in w.pilot.OUTPUT_NAMES):
        return
    items, manifest_hash = w.pilot.load_input(root / batch['input_path'])
    expected = _export_preview(B, items, manifest_hash)
    prior = None
    if certified:
        prior = (expected if certified['rows'] == len(rows) and not pending else
                 _export_preview(B, items, manifest_hash, prefix_rows=certified['rows']))
        w.require(prior['files'] == certified['native_files'],
                  'Certified native generation differs from its exact SQL/attempt prefix')
    if old:
        def stable(manifest):
            # A separately imported namespace preserves the old descriptive
            # annotation path. No annotation exists (strictly checked above).
            return {**{k: v for k, v in manifest.items() if k != 'exported_at'},
                    'manual_review': {k: v for k, v in manifest['manual_review'].items()
                                      if k != 'annotation_path'}}
        old_is_current = stable(old) == stable(expected)
        old_is_certified = prior is not None and stable(old) == stable(prior)
        w.require(old_is_current or old_is_certified, 'Export manifest is not a proven old/current generation')
    else:
        old_is_current = False
    repair_needed = not old_is_current
    for name, current in expected['files'].items():
        path = B / name
        if not path.exists():
            w.require(certified is None, 'Previously certified native export disappeared')
            repair_needed = True
            continue
        sha = w.sha_file(path)
        permitted = {current['sha256']}
        if certified:
            permitted.add(certified['native_files'][name]['sha256'])
        w.require(sha in permitted, 'Native export differs from both proven old/current generations')
        repair_needed = repair_needed or sha != current['sha256']
    if repair_needed:
        w.require(not certified or len(rows) > certified['rows'] or pending,
                  'No committed rows or reconciled pending attempt prove an export-recovery window')
        w.pilot.run_pilot(root / batch['input_path'], B, media, export_only=True)


def _validate_stop(root, plan, summaries, result_rows):
    """A normal pause requires fully committed, checked, balanced evidence."""
    entries = w._ledger(root, plan)
    w._snapshot_reconciliation(root, plan, entries)
    entries = w._ledger(root, plan)
    w.require(not entries or entries[-1]['event'] == 'finish', 'Pause has an open transport window')
    w.require(not _pending_count(root, plan), 'Pause has an incomplete native attempt')
    rows = [row for batch in plan['batches'] for row in w._rows(root, batch)]
    w.require(len(rows) == result_rows == sum(s['rows'] for s in summaries),
              'Pause committed/check accounting differs')
    expected = [sid for batch in plan['batches'] for sid in batch['sample_ids']]
    w.require([r['sample_id'] for r in rows] == expected[:result_rows],
              'Pause results are not the exact input prefix')
    for summary in summaries:
        w.require(w.sha_file(summary['check_path']) == summary['check_sha256'],
                  'Pause automatic check changed')
        check = w.load(summary['check_path'])
        w.require(check['manual_reviews'] == 0 and not check['article_acceptance'],
                  'Pause cannot invent review or acceptance')
    return entries


def _finish_boundary(root, plan, summaries, result_rows, *, paused):
    try:
        entries = _validate_stop(root, plan, summaries, result_rows)
        if summaries and (not paused or result_rows % 400 == 0 or result_rows == plan['row_count']):
            w._checkpoint(root, plan, summaries)
        if not paused:
            return w._state(root, plan, w.PENDING, result_rows=result_rows,
                            checkpoint_boundary_reached=True, completed_batches=sum(
                                s['batch_input_complete'] for s in summaries))
        receipt = {
            'schema': SCHEMA, 'plan_sha256': plan['plan_sha256'], 'created_at': w.now(),
            'status': PAUSED, 'result_rows': result_rows,
            'transport_reservations': sum(e['event'] == 'start' for e in entries),
            'transport_event_count': len(entries),
            'transport_ledger_sha256': w.sha_file(root / 'transport_calls.jsonl'),
            'incomplete_native_attempts': 0, 'open_transport_calls': 0,
            'batch_checks': summaries, 'manual_review_status': 'not_reviewed',
            'article_acceptance': False,
        }
        receipt['receipt_sha256'] = w.digest(receipt)
        relative = 'pause_receipts/' + receipt['receipt_sha256'] + '.json'
        path = root / relative
        w.require(not path.exists(), 'Refuse to overwrite a normal pause receipt')
        w.write(root, relative, receipt)
        return w._state(root, plan, PAUSED, result_rows=result_rows,
                        transport_reservations=receipt['transport_reservations'],
                        pending_input_urls=plan['row_count'] - result_rows,
                        pause_receipt_path=str(path), pause_receipt_sha256=w.sha_file(path))
    except Exception as exc:
        return w._halt(root, plan, 'pause_or_boundary_requires_reconciliation',
                       detail=type(exc).__name__ + ': ' + str(exc))


def run(root, media_root, *, max_batches, fetcher=None, parser=None,
        allow_network=False, clock=time.time, sleep=time.sleep, disk_free=None,
        stop_requested=None, install_signal_handlers=True, stop_at_saved_rows=None,
        checkpoint_callback=None, inherited_failure_acknowledgment=None):
    """Finish an active logical URL, then pause before starting another one.

    stop_at_saved_rows is a hard count of retained input URLs in this child,
    including an inherited prefix. A completed child still creates the frozen
    continuation context. A partial hard boundary creates its checkpoint offline.
    """
    controller = StopController()
    def requested():
        if stop_requested and stop_requested():
            controller.request()
        return controller()
    kwargs = dict(max_batches=max_batches, fetcher=fetcher, parser=parser,
                  allow_network=allow_network, clock=clock, sleep=sleep,
                  disk_free=disk_free, stop_requested=requested,
                  stop_at_saved_rows=stop_at_saved_rows,
                  checkpoint_callback=checkpoint_callback,
                  inherited_failure_acknowledgment=inherited_failure_acknowledgment)
    if install_signal_handlers:
        with graceful_signals(controller):
            return _run(root, media_root, **kwargs)
    return _run(root, media_root, **kwargs)


def _run(root, media_root, *, max_batches, fetcher, parser, allow_network,
         clock, sleep, disk_free, stop_requested, stop_at_saved_rows, checkpoint_callback,
         inherited_failure_acknowledgment):
    w.require(fetcher is not None or allow_network, 'Explicit network execution flag required')
    root = w.namespace(root, media_root)
    media = Path(media_root)
    w.require(type(max_batches) is int and 1 <= max_batches <= 10000,
              'Explicit bounded max_batches required')
    with w.pilot.exclusive_run(root.parent), w.pilot.exclusive_run(root):
        plan, registry = w.load_plan(root, media)
        limit = plan['row_count'] if stop_at_saved_rows is None else stop_at_saved_rows
        w.require(type(limit) is int and 0 <= limit <= plan['row_count'], 'Invalid retained-row boundary')
        if (root / 'continuous_state.json').exists():
            old = w.load(root / 'continuous_state.json')
            w.require(old.get('plan_sha256') == plan['plan_sha256'], 'Control state belongs to another plan')
            if old.get('status') == 'halted_no_automatic_resume':
                w.require((root / 'safety_halt.json').is_file() and
                          w.sha_file(root / 'safety_halt.json') == old.get('halt_sha256'),
                          'Safety halt deleted or changed; no automatic resume')
            if old.get('status') == PAUSED:
                receipt = Path(old['pause_receipt_path'])
                w.require(receipt.parent == root / 'pause_receipts' and
                          w.sha_file(receipt) == old['pause_receipt_sha256'], 'Pause receipt changed')
                doc = w.load(receipt); unsigned = dict(doc); signature = unsigned.pop('receipt_sha256', None)
                w.require(signature == w.digest(unsigned) and doc['plan_sha256'] == plan['plan_sha256'],
                          'Pause receipt belongs to another plan')
                lines = (root / 'transport_calls.jsonl').read_bytes().splitlines(keepends=True)
                count = doc['transport_event_count']
                w.require(type(count) is int and 0 <= count <= len(lines) and count % 2 == 0 and
                          hashlib.sha256(b''.join(lines[:count])).hexdigest() == doc['transport_ledger_sha256'],
                          'Receipted pause transport prefix changed')
        if (root / 'halt_receipts').exists():
            w.require((root / 'safety_halt.json').is_file(), 'Permanent halt receipt exists; refusing removed cursor')
        if (root / 'safety_halt.json').exists():
            w.require(w.load(root / 'safety_halt.json')['plan_sha256'] == plan['plan_sha256'], 'Halt belongs to another plan')
            return w._state(root, plan, 'halted_no_automatic_resume', halt_sha256=w.sha_file(root / 'safety_halt.json'))
        try:
            inherited_ack = validated_inherited_failure_ack(root, plan, inherited_failure_acknowledgment)
            w.require(not inherited_ack or not inherited_ack['synthetic_fixture'] or fetcher is not None,
                      'Synthetic inherited acknowledgment cannot enable live transport')
        except Exception as exc:
            return w._halt(root, plan, 'inherited_failure_acknowledgment_invalid',
                           detail=type(exc).__name__ + ': ' + str(exc))
        try:
            w._snapshot_reconciliation(root, plan, w._ledger(root, plan))
        except Exception as exc:
            return w._halt(root, plan, 'transport_state_requires_reconciliation', detail=type(exc).__name__ + ': ' + str(exc))
        saved_total = sum(len(w._rows(root, batch)) for batch in plan['batches'])
        w.require(saved_total <= limit, 'Committed prefix already exceeds the requested boundary')
        seen = w.seed_history_identities(plan['seed_context'].get('history_index'))
        history = list(plan['seed_context']['source_history'])
        summaries = []; executed = 0; processed = 0
        for batch in plan['batches']:
            B = root / 'batches' / batch['batch_id']
            saved = w._rows(root, batch); records = []
            try:
                _export_preflight(root, media, batch, saved)
                for row in saved:
                    record, trigger = w._assess_row(root, plan, row, B, registry, seen, history)
                    records.append(record)
                    if trigger and not (trigger == 'critical_source_or_access_failure' and
                                        _acknowledged_replay(inherited_ack, row, record)):
                        return w._halt(root, plan, trigger, sample_id=row['sample_id'], risks=record['automatic_flags'])
            except Exception as exc:
                return w._halt(root, plan, 'source_check_exception', detail=type(exc).__name__ + ': ' + str(exc))
            stopped = {}; normal = {'requested': False}

            def stop(reason, **evidence):
                stopped.update(reason=reason, **evidence)
                w._halt(root, plan, reason, **evidence)
                raise KeyboardInterrupt()

            def before_begin():
                # Wait BEFORE a native attempt is created. A pause during this
                # delay must not produce a fake unresolved network attempt.
                if stop_requested() or saved_total >= limit:
                    normal['requested'] = True
                    raise KeyboardInterrupt()
                entries = w._ledger(root, plan)
                last = entries[-1]['epoch'] if entries else plan['seed_context'].get('last_transport_finish')
                epoch = clock()
                if not isinstance(epoch, (int, float)) or not math.isfinite(epoch) or (last is not None and epoch < last):
                    stop('invalid_transport_clock')
                if last is not None and epoch - last < plan['pause_seconds']:
                    sleep(plan['pause_seconds'] - (epoch - last))
                if stop_requested() or saved_total >= limit:
                    normal['requested'] = True
                    raise KeyboardInterrupt()
                free = disk_free(B) if disk_free else w.shutil.disk_usage(B).free
                if not isinstance(free, (int, float)) or not math.isfinite(free):
                    stop('invalid_disk_space_measurement')
                if free < plan['min_free_bytes']:
                    stop('low_disk_space', free_bytes=free)
                if sum(e['event'] == 'start' for e in entries) >= plan['max_fetch_calls']:
                    stop('request_budget_exhausted')

            def guarded_fetch(url, timeout, **kwargs):
                return w.transport_with_retries(root, plan, batch, B, url, timeout,
                                                stop, fetcher, clock, sleep, disk_free, kwargs)

            def committed(item, row):
                nonlocal saved_total
                saved_total += 1
                try:
                    record, trigger = w._assess_row(root, plan, row, B, registry, seen, history)
                except Exception as exc:
                    stop('automatic_check_integrity_error', sample_id=row['sample_id'], detail=type(exc).__name__ + ': ' + str(exc))
                records.append(record)
                if trigger:
                    stop(trigger, sample_id=row['sample_id'], risks=record['automatic_flags'])
                if stop_requested() or saved_total >= limit:
                    normal['requested'] = True
                    raise KeyboardInterrupt()

            if len(saved) < batch['row_count']:
                must_stop = saved_total >= limit or stop_requested()
                pending = _pending_count(root, plan)
                if not must_stop or pending:
                    if executed >= max_batches:
                        return w._state(root, plan, w.PENDING, result_rows=saved_total,
                                        completed_batches=len(summaries), invocation_batch_limit_reached=True)
                    outcome = _pilot_with_prebegin(before_begin, root / batch['input_path'], B, media,
                        pause_seconds=0, timeout=plan['timeout'], fetcher=guarded_fetch,
                        parser=parser, after_commit=committed)
                    executed += 1
                    if stopped:
                        return w._state(root, plan, 'halted_no_automatic_resume',
                                        halt_sha256=w.sha_file(root / 'safety_halt.json'), result_rows=saved_total)
                    if outcome['interrupted'] and not normal['requested']:
                        return w._state(root, plan, 'interrupted_requires_explicit_invocation',
                                        pending_input_urls=outcome['pending_input_urls'])
                    saved = w._rows(root, batch)
            if saved:
                try:
                    summaries.append(_native_check(root, media, plan, batch, saved, records))
                except Exception as exc:
                    return w._halt(root, plan, 'batch_readback_failed', batch_id=batch['batch_id'], detail=type(exc).__name__ + ': ' + str(exc))
            processed += len(saved)
            if processed and processed % 400 == 0:
                w._checkpoint(root, plan, summaries)
                if checkpoint_callback and not checkpoint_callback(root, plan, summaries):
                    return _finish_boundary(root, plan, summaries, saved_total, paused=True)
            # Replay all already committed rows before certifying any stop.
            if processed == saved_total and saved_total < plan['row_count'] and (
                    stop_requested() or saved_total >= limit or normal['requested']):
                return _finish_boundary(root, plan, summaries, saved_total, paused=stop_requested())
            if len(saved) != batch['row_count']:
                return w._halt(root, plan, 'incomplete_batch_without_pause')
        w._checkpoint(root, plan, summaries)
        if plan['row_count'] % 400 and checkpoint_callback and not checkpoint_callback(root, plan, summaries):
            return _finish_boundary(root, plan, summaries, saved_total, paused=True)
        identity_doc = {'schema': w.HISTORY_SCHEMA,
                        'records': [seen[('sample', sid)] for batch in plan['batches'] for sid in batch['sample_ids']],
                        'parent': plan['seed_context'].get('history_index')}
        identity_path = root / 'identity_index.json'
        if identity_path.exists():
            w.require(w.load(identity_path) == identity_doc, 'Completed identity index changed')
        else:
            w.write(root, 'identity_index.json', identity_doc)
        entries = _validate_stop(root, plan, summaries, saved_total)
        context = {'source_history': history[-79:], 'service_history': [],
                   'last_transport_finish': entries[-1]['epoch'] if entries else plan['seed_context'].get('last_transport_finish'),
                   'prior_plan_receipts': plan['seed_context'].get('prior_plan_receipts', []),
                   'history_index': {'path': str(identity_path), 'sha256': w.sha_file(identity_path)}}
        inherited_failures = list(plan['seed_context'].get('inherited_terminal_failures', []))
        if inherited_ack:
            failure = {
                **inherited_ack['failure'], 'acknowledgment': inherited_failure_acknowledgment,
                'collection_outcome': 'critical_failure', 'manual_review_status': 'not_reviewed',
                'resolution_status': 'unresolved_transport_failure', 'retry_authorized': False,
                'article_acceptance': False}
            matches = [prior for prior in inherited_failures if
                       (prior.get('sample_id'), prior.get('attempt_id')) ==
                       (failure['sample_id'], failure['attempt_id'])]
            w.require(not matches or matches == [failure], 'Inherited failure context changed or duplicated')
            if not matches:
                inherited_failures.append(failure)
        if inherited_failures:
            context['inherited_terminal_failures'] = inherited_failures
        w.write(root, 'continuation_context.json', context)
        return w._state(root, plan, w.PENDING, collection_inputs_finished=True,
                        completed_batches=len(summaries), result_rows=plan['row_count'],
                        manual_reviews=0, continuation_context_sha256=w.sha_file(root / 'continuation_context.json'))


def close_saved_boundary(root, media_root, saved, **kwargs):
    """Rebuild a saved boundary offline; any attempted fetch is a testable error."""
    def never_fetch(*args, **kw):
        raise AssertionError('Offline boundary closure cannot make a request')
    return run(root, media_root, max_batches=1, fetcher=never_fetch,
               stop_at_saved_rows=saved, **kwargs)

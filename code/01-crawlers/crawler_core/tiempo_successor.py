"""An explicitly authorized next-batch successor of a closed recovery capsule.

Preparation and inspection are offline. The source capsule stays immutable;
only a new namespace can collect the next original batch.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import sqlite3

from . import tiempo_recovery as recovery
from . import tiempo_continuous_v5 as w

SCHEMA = 'tiempo-bounded-successor-capsule-v1'


def code_binding():
    return {**recovery.code_binding(), 'successor_adapter': w.sha_file(__file__),
            'successor_cli': w.sha_file(Path(__file__).parents[1] / 'scripts/run_tiempo_successor.py')}


def _config(path):
    cfg = w.load(path)
    required = {'source_capsule', 'source_closure', 'source_closure_sha256',
                'capsule', 'isolated_media', 'new_child', 'expected_active_saved',
                'expected_batch_id', 'expected_sample_ids', 'max_additional_transport_calls'}
    w.require(required <= set(cfg), 'Explicit successor configuration is incomplete')
    w.require(type(cfg['expected_active_saved']) is int and cfg['expected_active_saved'] > 0,
              'A positive saved prefix is required')
    ids = cfg['expected_sample_ids']
    w.require(isinstance(ids, list) and 0 < len(ids) <= 80 and
              all(isinstance(x, str) for x in ids) and len(set(ids)) == len(ids),
              'Explicit unique next-batch identities required')
    budget = cfg['max_additional_transport_calls']
    w.require(type(budget) is int and 1 <= budget <= len(ids) * w.POLICY['attempts_per_url'],
              'Additional call budget must be within the existing retry policy')
    return cfg


def _files(root):
    paths = []
    for p in sorted(Path(root).rglob('*')):
        w.require(not p.is_symlink(), 'Symlink in immutable source tree: ' + str(p))
        if p.is_file() and p.name != '.pilot.lock':
            paths.append(p)
    return paths


def _source_inspect(root):
    schema = recovery.signed(Path(root) / 'capsule.json', 'capsule_sha256')['schema']
    if schema == recovery.SCHEMA:
        return recovery.inspect(root)
    w.require(schema == SCHEMA, 'Unsupported source capsule schema')
    return inspect(root)


def _next_batch(plan, saved):
    consumed = 0
    for index, batch in enumerate(plan['batches']):
        if consumed == saved:
            return index, batch
        consumed += batch['row_count']
    raise ValueError('Saved prefix must end at a complete original batch before another batch')


def _closed_source(root, capsule, plan, status, cfg):
    child = Path(capsule['new_child'])
    w.require(status['trial_remaining_urls'] == 0 and
              status['saved_active_rows'] == cfg['expected_active_saved'],
              'Source bounded trial must be fully finished at the expected saved prefix')
    state = w.load(child / 'continuous_state.json')
    w.require(state.get('plan_sha256') == plan['plan_sha256'] and
              state.get('status') == w.PENDING and
              not (child / 'safety_halt.json').exists() and
              not (child / 'halt_receipts').exists(),
              'A halted or unclosed source cannot be promoted')
    index, target = _next_batch(plan, cfg['expected_active_saved'])
    w.require(target['batch_id'] == cfg['expected_batch_id'] and
              target['sample_ids'] == cfg['expected_sample_ids'],
              'Configured scope differs from the exact next original batch')
    batches = [(batch, w._rows(child, batch)) for batch in plan['batches']]
    for i, (batch, rows) in enumerate(batches):
        w.require(len(rows) == (batch['row_count'] if i < index else 0),
                  'Source results are not an exact completed native prefix')
        if i >= index:
            B = child / 'batches' / batch['batch_id']
            w.require(not (B / 'pilot.sqlite').exists() and not (B / 'manifest.json').exists(),
                      'Source has already initialized a later batch')
    entries = w._ledger(child, plan)
    w.require(not entries or entries[-1]['event'] == 'finish',
              'Source has an uncertain transport reservation')
    groups = {}
    for start, finish in zip(entries[::2], entries[1::2]):
        rec, response = w._transport_receipt(child, start)
        w.require(finish['response_sha256'] == w.sha_file(child / f'transport_snapshots/{start["sequence"]:08d}.json'),
                  'Source transport receipt differs from durable finish')
        groups.setdefault((start['batch_id'], start['attempt_id']), []).append((start, rec, response))
    seen_attempts = set()
    for batch, rows in batches:
        if not rows:
            continue
        B = child / 'batches' / batch['batch_id']
        with sqlite3.connect((B / 'pilot.sqlite').as_uri() + '?mode=ro&immutable=1', uri=True) as db:
            db.row_factory = sqlite3.Row
            for value in db.execute('SELECT * FROM fetch_attempts'):
                attempt = dict(value); key = (batch['batch_id'], attempt['attempt_id'])
                w.require(attempt['completed_at'] is not None and key in groups,
                          'Source contains an incomplete or unbound attempt')
                calls = groups[key]; seen_attempts.add(key)
                w.require([r['retry_index'] for _, r, _ in calls] == list(range(len(calls))) and
                          len(calls) <= w.POLICY['attempts_per_url'] and calls[-1][1]['terminal'],
                          'Source retry sequence is incomplete')
                w.require(all(e['url'] == attempt['url'] for e, _, _ in calls),
                          'Source attempt URL differs from transport')
                row = next((r for r in rows if r['attempt_id'] == attempt['attempt_id']), None)
                w.require(row is not None and json.loads(attempt['result_json']) == row,
                          'Source terminal attempt has no exact saved result')
                raw = B / row['snapshot_path']; meta = raw.with_suffix('.json')
                w.require(raw.is_file() and meta.is_file() and
                          w.sha_file(raw) == row['snapshot_sha256'] == calls[-1][1]['text_sha256'],
                          'Source saved snapshot is missing or changed')
                metadata = w.load(meta)
                w.require(metadata['snapshot_sha256'] == row['snapshot_sha256'] and
                          metadata['response'] == calls[-1][1]['response'],
                          'Source response metadata differs from transport')
    w.require(seen_attempts == set(groups), 'Source transport contains extra attempts')
    return batches, entries, index, target


def _closure(cfg, source, child, saved):
    path = Path(cfg['source_closure']).resolve()
    w.require(w.sha_file(path) == cfg['source_closure_sha256'], 'Source closure changed')
    closure = w.load(path)
    w.require(isinstance(closure.get('status'), str) and closure['status'].startswith('PASS') and
              closure.get('native_successor_records') == saved and
              closure.get('no_automatic_expansion') is True and closure.get('article_acceptance') is False,
              'Source closure does not certify the completed bounded collection stage')
    protected = recovery.bindings([path])
    # General closures can bind runtime directly. The first live14 closure binds
    # its independently reviewed runtime through its frozen cloud-review receipt.
    runtime = closure.get('source_binding')
    if runtime is None:
        evidence = closure.get('evidence', {})
        name = 'review/Final_Cloud_Review.json'
        w.require(name in evidence, 'Source closure lacks a bound runtime review')
        base = path.parent.parent
        for name_, expected in evidence.items():
            p = (base / name_).resolve()
            w.require(base in p.parents and w.sha_file(p) == expected, 'Closure evidence changed')
            protected[str(p)] = expected
        review = w.load(base / name)
        w.require(review.get('status') == 'PASS', 'Source final review did not pass')
        runtime = review['runtime_closure']
    w.require(runtime.get('capsule_file_sha256') == w.sha_file(source / 'capsule.json') and
              runtime.get('saved_active_rows') == saved and
              runtime.get('transport_ledger_sha256') == w.sha_file(child / 'transport_calls.jsonl'),
              'Source closure is not bound to this exact completed capsule')
    for key, name in (('queue_sha256', 'queue.csv'),
                      ('transport_state_sha256', 'transport_state.json'),
                      ('continuous_state_sha256', 'continuous_state.json')):
        if key in runtime:
            w.require(runtime[key] == w.sha_file(child / name),
                      'Source closure runtime binding changed: ' + key)
    actual = {str(p.resolve()): w.sha_file(p) for p in child.glob('batches/*/pilot.sqlite')}
    evidence = runtime.get('native_databases', [])
    expected = {str(Path(x['path']).resolve()): x['sha256'] for x in evidence}
    w.require(len(expected) == len(evidence) and expected == actual,
              'Source closure native database bindings differ')
    return protected


def prepare(config_path):
    """Validate a closed source and construct a new bounded successor offline."""
    config_path = Path(config_path).resolve(); cfg = _config(config_path)
    source = Path(cfg['source_capsule']).resolve()
    old, oldplan, status = _source_inspect(source)
    oldchild = Path(old['new_child']).resolve()
    root = Path(cfg['capsule']).resolve(); media = Path(cfg['isolated_media']).resolve()
    child = w.namespace(Path(cfg['new_child']).resolve(), media)
    w.require(not root.exists() and not media.exists() and not child.exists(),
              'Independent empty successor destinations required')
    w.require(root != media and root not in media.parents and media not in root.parents,
              'Capsule and isolated media destinations must be disjoint')
    for destination in (root, media, child):
        for prior in (source, oldchild):
            w.require(destination != prior and prior not in destination.parents and destination not in prior.parents,
                      'Successor destinations overlap immutable source trees')
    batches, entries, target_index, target = _closed_source(source, old, oldplan, status, cfg)
    protected = {**old['protected_sources'], **old['recovery_evidence'],
                 **recovery.bindings(_files(source) + _files(oldchild) + [config_path]),
                 **_closure(cfg, source, oldchild, cfg['expected_active_saved'])}
    for destination in (root, media, child):
        w.require(all(destination != Path(p) and destination not in Path(p).parents for p in protected),
                  'Destination would contain immutable source evidence')
    recovery.verify_bindings(protected)
    starts = sum(e['event'] == 'start' for e in entries)
    prior_calls = old['original_completed_transport_calls']
    budget = cfg['max_additional_transport_calls']
    max_calls = min(starts + budget, old['master_max_fetch_calls'] - prior_calls)
    w.require(max_calls >= starts + budget, 'Remaining global budget cannot fund the explicit bounded call limit')
    plan = w.freeze(oldchild / 'queue.csv', child, media, oldchild / 'known_registry.json',
                    oldplan['registry_sha256'], oldplan['exclusions'],
                    start=oldplan['date_start'], end=oldplan['date_end_exclusive'],
                    max_fetch_calls=max_calls, queue_db_path=oldplan['original_queue']['path'],
                    queue_db_sha256=oldplan['original_queue']['sha256'],
                    pause_seconds=oldplan['pause_seconds'], timeout=oldplan['timeout'],
                    min_free_bytes=oldplan['min_free_bytes'], seed_context=oldplan['seed_context'])
    w.require(plan['batches'] == oldplan['batches'] and
              (child / 'queue.csv').read_bytes() == (oldchild / 'queue.csv').read_bytes(),
              'Original full-child topology changed')
    root.mkdir(parents=True, exist_ok=False)
    copied = {}
    for batch, rows in batches:
        if not rows:
            continue
        B = oldchild / 'batches' / batch['batch_id']; out = child / 'batches' / batch['batch_id']
        for p in _files(B):
            relative = p.relative_to(B)
            if p.name == 'Kevin_NOTE.md' or 'inputs' in relative.parts:
                continue
            dest = out / relative
            w.require(not dest.exists(), 'Refuse to overwrite successor native evidence')
            dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(p, dest)
            w.require(w.sha_file(dest) == w.sha_file(p), 'Copied native file differs')
            copied[str(dest.relative_to(child))] = w.sha_file(dest)
    for event in entries:
        rebased = {k: v for k, v in event.items() if k != 'previous_event_sha256'}
        rebased['plan_sha256'] = plan['plan_sha256']
        rebased['imported_from'] = {'plan_sha256': oldplan['plan_sha256'], 'event_sha256': w.digest(event)}
        base = f'transport_snapshots/{event["sequence"]:08d}'
        if event['event'] == 'start':
            dest = child / (base + '.html'); dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(oldchild / (base + '.html'), dest)
            rec = w.load(oldchild / (base + '.json')); rec['plan_sha256'] = plan['plan_sha256']
            rec['imported_from'] = {'path': str(oldchild / (base + '.json')),
                                    'sha256': w.sha_file(oldchild / (base + '.json'))}
            w.write(child, base + '.json', rec)
        else:
            rebased['response_sha256'] = w.sha_file(child / (base + '.json'))
        w._append(child, plan, rebased)
    w._snapshot_reconciliation(child, plan, w._ledger(child, plan))
    _, registry = w.load_plan(child, media)
    seen = w.seed_history_identities(plan['seed_context'].get('history_index'))
    history = list(plan['seed_context']['source_history'])
    for batch, original in batches:
        rows = w._rows(child, batch); w.require(rows == original, 'Inherited native payload changed')
        records = []
        for row in rows:
            rec, trigger = w._assess_row(child, plan, row, child / 'batches' / batch['batch_id'], registry, seen, history)
            before = w.load(oldchild / 'row_checks' / (row['sample_id'] + '.json'))
            w.require(before['plan_sha256'] == oldplan['plan_sha256'] and before['record'] == rec,
                      'Inherited source diagnostics changed')
            w.require(trigger is None, 'Inherited risk context requires investigation before continuation')
            records.append(rec)
        if rows:
            w._batch_check(child, batch, rows, records)
    obligations = []
    for p in source.glob('*Review_Obligations.json'):
        obligations.append({'path': str(p), 'sha256': w.sha_file(p), 'document': w.load(p)})
    pending = [row for p in sorted(oldchild.glob('checkpoint_*/pending_source_review_samples.csv')) for row in w.readcsv(p)]
    selections = []
    for batch in oldplan['batches']:
        rank = lambda sid: hashlib.sha256((oldplan['sampling_seed'] + '\n' + oldplan['plan_sha256'] + '\n' + sid).encode()).hexdigest()
        selections.extend({'batch_id': batch['batch_id'], 'sample_id': sid, 'selection_sha256': rank(sid)}
                          for sid in sorted(batch['sample_ids'], key=rank)[:10 if batch['batch_id'] == 'batch_000001' else 3])
    w.write(root, 'Inherited_Review_Obligations.json', {'author': 'Kevin', 'source_capsule_documents': obligations,
            'source_checkpoint_pending_samples': pending, 'source_plan_frozen_batch_selections': selections,
            'rule': 'All historical obligations remain; new sampling supplements them. No new reading or human approval is inferred.'})
    w.write(root, 'Copied_Native_Files.json', copied)
    w.write(root, 'Inherited_Context.json', {'source_history': history[-79:],
            'initial_seed_context': plan['seed_context'], 'active_rows_replayed': cfg['expected_active_saved'],
            'active_transport_calls': starts, 'global_transport_calls': prior_calls + starts})
    c = {'schema': SCHEMA, 'author': 'Kevin', 'created_at': w.now(), 'config_path': str(config_path),
         'source_capsule': str(source), 'source_child': str(oldchild), 'new_child': str(child), 'isolated_media': str(media),
         'source_plan_sha256': oldplan['plan_sha256'], 'code': code_binding(), 'protected_sources': protected,
         'plan_sha256': plan['plan_sha256'], 'active_imported_rows': cfg['expected_active_saved'],
         'active_imported_transport_calls': starts, 'original_completed_transport_calls': prior_calls,
         'master_max_fetch_calls': old['master_max_fetch_calls'], 'trial_batch_id': target['batch_id'],
         'trial_sample_ids': target['sample_ids'], 'trial_additional_transport_limit': budget,
         'imported_payloads_sha256': w.digest([r for _, rows in batches for r in rows]),
         'imported_transport_events_sha256': w.digest(w._ledger(child, plan)),
         'imported_transport_event_count': len(entries), 'native_copied_bytes_preserved': True,
         'ready_for_bounded_trial': True, 'manual_review_status': 'not_reviewed', 'article_acceptance': False,
         'automatic_promotion': False,
         'recovery_evidence': recovery.bindings([root / n for n in ('Copied_Native_Files.json', 'Inherited_Context.json', 'Inherited_Review_Obligations.json')])}
    c['capsule_sha256'] = w.digest(c); w.write(root, 'capsule.json', c)
    w._state(child, plan, w.PENDING, offline_successor_prepared=True,
             imported_result_rows=cfg['expected_active_saved'], new_transport_calls=0)
    recovery.verify_bindings(protected)
    inspect(root)
    return c


def inspect(root):
    """Read-only validation, including recoverable current-batch interruptions."""
    root = Path(root).resolve(); c = recovery.signed(root / 'capsule.json', 'capsule_sha256')
    w.require(c['schema'] == SCHEMA and c['code'] == code_binding(), 'Successor code/schema changed')
    recovery.verify_bindings(c['protected_sources']); recovery.verify_bindings(c['recovery_evidence'])
    cfg = _config(c['config_path']); child = Path(c['new_child']); plan, _ = w.load_plan(child, c['isolated_media'])
    state = w.load(child / 'continuous_state.json')
    w.require(state.get('schema') == w.MODE and state.get('plan_sha256') == plan['plan_sha256'],
              'Successor control state belongs to another plan')
    halt_path = child / 'safety_halt.json'; halt_receipts = child / 'halt_receipts'
    if state.get('status') == 'halted_no_automatic_resume' or halt_path.exists() or halt_receipts.exists():
        w.require(halt_path.is_file() and state.get('status') == 'halted_no_automatic_resume',
                  'Permanent successor halt was deleted or control state reset')
        halt_sha = w.sha_file(halt_path)
        w.require(w.load(halt_path).get('plan_sha256') == plan['plan_sha256'] and
                  state.get('halt_sha256') == halt_sha and
                  (halt_receipts / (halt_sha + '.json')).is_file(),
                  'Successor halt state or permanent receipt changed')
        for receipt in halt_receipts.iterdir():
            w.require(receipt.name == halt_sha + '.json' and receipt.is_file() and
                      w.sha_file(receipt) == halt_sha, 'Successor halt receipt changed')
    for name in ('source_capsule', 'new_child', 'isolated_media'):
        w.require(str(Path(cfg[name]).resolve()) == c[name], 'Successor configuration path changed')
    w.require(Path(cfg['capsule']).resolve() == root and plan['plan_sha256'] == c['plan_sha256'], 'Successor plan/path changed')
    oldplan = recovery.signed(Path(c['source_child']) / 'continuous_plan.json', 'plan_sha256')
    w.require(oldplan['plan_sha256'] == c['source_plan_sha256'], 'Source plan changed')
    for key in ('batches', 'seed_context', 'continuation_policy', 'row_count', 'queue_sha256',
                'registry_sha256', 'date_start', 'date_end_exclusive', 'original_queue', 'exclusions',
                'pause_seconds', 'timeout', 'min_free_bytes'):
        w.require(plan[key] == oldplan[key], 'Inherited frozen plan component changed: ' + key)
    w.require(c['active_imported_rows'] == cfg['expected_active_saved'], 'Imported row bound changed')
    index, target = _next_batch(plan, c['active_imported_rows'])
    w.require(c['trial_batch_id'] == cfg['expected_batch_id'] == target['batch_id'] and
              c['trial_sample_ids'] == cfg['expected_sample_ids'] == target['sample_ids'] and
              c['trial_additional_transport_limit'] == cfg['max_additional_transport_calls'],
              'Capsule does not bind the exact next original batch')
    expected_cap = c['active_imported_transport_calls'] + c['trial_additional_transport_limit']
    w.require(plan['max_fetch_calls'] == expected_cap and
              c['original_completed_transport_calls'] + expected_cap <= c['master_max_fetch_calls'],
              'Frozen child/global transport budget changed')
    copied = w.load(root / 'Copied_Native_Files.json')
    for relative, expected in copied.items():
        w.require(w.sha_file(w.pilot.safe_path(child, relative)) == expected, 'Inherited native file changed')
    batches = [(b, w._rows(child, b)) for b in plan['batches']]
    for i, (batch, rows) in enumerate(batches):
        if i < index:
            w.require(len(rows) == batch['row_count'], 'Inherited batch lost rows')
        if i > index:
            B = child / 'batches' / batch['batch_id']
            w.require(not rows and not (B / 'pilot.sqlite').exists() and not (B / 'manifest.json').exists(),
                      'A batch outside the authorized successor was initialized')
    prefix = [r for _, rows in batches[:index] for r in rows]
    w.require(len(prefix) == c['active_imported_rows'] and w.digest(prefix) == c['imported_payloads_sha256'],
              'Imported native prefix changed')
    entries = w._ledger(child, plan); count = c['imported_transport_event_count']
    w.require(len(entries) >= count and w.digest(entries[:count]) == c['imported_transport_events_sha256'],
              'Imported transport prefix changed')
    calls = sum(e['event'] == 'start' for e in entries)
    w.require(sum(e['event'] == 'start' for e in entries[:count]) == c['active_imported_transport_calls'],
              'Inherited transport count changed')
    allowed = {r['url'] for r in w.readcsv(child / 'queue.csv')[c['active_imported_rows']:c['active_imported_rows'] + target['row_count']]}
    w.require(all(e['batch_id'] == target['batch_id'] and e['url'] in allowed for e in entries[count:]),
              'Transport escaped the exact next original batch')
    new_calls = calls - c['active_imported_transport_calls']
    w.require(0 <= new_calls <= c['trial_additional_transport_limit'] and
              c['original_completed_transport_calls'] + calls <= c['master_max_fetch_calls'],
              'Successor transport budget exceeded')
    rows = batches[index][1]
    return c, plan, {'saved_active_rows': len(prefix) + len(rows),
                    'trial_remaining_urls': target['row_count'] - len(rows),
                    'new_transport_reservations': new_calls,
                    'total_charged_transport_reservations': c['original_completed_transport_calls'] + calls,
                    'source_capsule_preserved': True, 'article_acceptance': False}


def run_trial(root, *, allow_network=False, fetcher=None, clock=w.time.time, sleep=w.time.sleep, disk_free=None):
    w.require(allow_network or fetcher is not None, 'Explicit live authorization or injected offline fetcher required')
    root = Path(root).resolve()
    with w.pilot.exclusive_run(root):
        c, plan, status = inspect(root); child = Path(c['new_child'])
        w.require(c['ready_for_bounded_trial'], 'Successor is not ready')
        if (child / 'safety_halt.json').exists():
            return {**status, 'status': 'halted_no_automatic_resume'}
        if status['trial_remaining_urls'] == 0:
            return {**status, 'status': 'bounded_trial_finished_pending_review', 'network_calls_this_invocation': 0}
        allowed = {r['url'] for r in w.readcsv(child / 'queue.csv') if r['sample_id'] in c['trial_sample_ids']}
        calls = 0
        def bounded_fetch(url, timeout, **kwargs):
            nonlocal calls
            w.require(url in allowed, 'Request outside authorized successor batch')
            count = sum(e['event'] == 'start' for e in w._ledger(child, plan)) - c['active_imported_transport_calls']
            w.require(count <= c['trial_additional_transport_limit'], 'Successor call budget exhausted')
            w.require(c['original_completed_transport_calls'] + c['active_imported_transport_calls'] + count <= c['master_max_fetch_calls'], 'Global budget exhausted')
            calls += 1
            if fetcher is not None:
                return fetcher(url, timeout, **kwargs)
            from .capabilities import fetch
            return fetch(url, timeout, **kwargs)
        result = w.run(child, c['isolated_media'], max_batches=1, fetcher=bounded_fetch,
                       clock=clock, sleep=sleep, disk_free=disk_free)
        _, _, after = inspect(root)
        answer = {**after, 'worker_result': result, 'network_calls_this_invocation': calls,
                  'status': 'bounded_trial_finished_pending_review' if after['trial_remaining_urls'] == 0 and 'halt' not in result['status'] else result['status']}
        w.write(root, 'trial_last_receipt.json', answer)
        return answer


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='command', required=True)
    a = sub.add_parser('prepare'); a.add_argument('--config', type=Path, required=True)
    a = sub.add_parser('inspect'); a.add_argument('--capsule', type=Path, required=True)
    a = sub.add_parser('trial'); a.add_argument('--capsule', type=Path, required=True); a.add_argument('--allow-network', action='store_true')
    args = p.parse_args(argv)
    if args.command == 'prepare':
        result = prepare(args.config)
    elif args.command == 'inspect':
        c, _, result = inspect(args.capsule); result.update(ready_for_bounded_trial=c['ready_for_bounded_trial'], trial_url_limit=len(c['trial_sample_ids']))
    else:
        result = run_trial(args.capsule, allow_network=args.allow_network)
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0

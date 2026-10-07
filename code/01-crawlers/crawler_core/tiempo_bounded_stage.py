"""Kevin's explicit remainder-of-one-child stage, with fixed 400-row stops.

The reviewed donor and older modules stay immutable. Preparation/inspection
are offline. A run invocation may finish only the next frozen checkpoint.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil

from . import tiempo_successor as successor
from . import tiempo_recovery as recovery
from . import tiempo_continuous_v5 as w

SCHEMA = 'tiempo-bounded-child-remainder-v1'


def code_binding():
    return {**successor.code_binding(), 'bounded_stage_adapter': w.sha_file(__file__),
            'bounded_stage_cli': w.sha_file(Path(__file__).parents[1] / 'scripts/run_tiempo_bounded_stage.py')}


def _config(path):
    cfg = w.load(path)
    required = {'source_capsule', 'source_closure', 'source_closure_sha256',
                'capsule', 'isolated_media', 'new_child', 'expected_active_saved',
                'expected_batch_ids', 'expected_sample_ids', 'checkpoint_saved_rows',
                'max_additional_transport_calls'}
    w.require(required <= set(cfg), 'Explicit bounded-stage configuration is incomplete')
    saved = cfg['expected_active_saved']; ids = cfg['expected_sample_ids']
    w.require(type(saved) is int and saved > 0 and saved % 80 == 0,
              'Saved prefix must end at an original 80-row boundary')
    w.require(isinstance(ids, list) and ids and all(isinstance(x, str) for x in ids)
              and len(set(ids)) == len(ids), 'Explicit ordered unique stage identities required')
    bids = cfg['expected_batch_ids']
    w.require(isinstance(bids, list) and bids and all(isinstance(x, str) for x in bids)
              and len(set(bids)) == len(bids), 'Explicit ordered unique batch identities required')
    budget = cfg['max_additional_transport_calls']
    w.require(type(budget) is int and 1 <= budget <= len(ids) * w.POLICY['attempts_per_url'],
              'Stage budget exceeds the existing bounded retry policy')
    end = saved + len(ids)
    expected = list(range((saved // 400 + 1) * 400, end + 1, 400))
    if not expected or expected[-1] != end:
        expected.append(end)
    w.require(cfg['checkpoint_saved_rows'] == expected,
              'Checkpoints must be every original cumulative 400 rows and final boundary')
    return cfg


def _scope(plan, cfg):
    index, _ = successor._next_batch(plan, cfg['expected_active_saved'])
    targets = plan['batches'][index:]
    w.require([b['batch_id'] for b in targets] == cfg['expected_batch_ids'] and
              [sid for b in targets for sid in b['sample_ids']] == cfg['expected_sample_ids'],
              'Configured scope differs from the exact remaining original child')
    ends = []; consumed = 0
    for batch in plan['batches']:
        consumed += batch['row_count']; ends.append(consumed)
    w.require(all(n in ends for n in cfg['checkpoint_saved_rows']),
              'Checkpoint must end at a complete original batch')
    w.require(consumed == plan['row_count'] == cfg['expected_active_saved'] + len(cfg['expected_sample_ids']),
              'The stage cannot include a different child or omit its final boundary')
    return index, targets


def _halt_integrity(child, plan, state):
    halt = child / 'safety_halt.json'; receipts = child / 'halt_receipts'
    if state.get('status') == 'halted_no_automatic_resume' or halt.exists() or receipts.exists():
        w.require(halt.is_file() and state.get('status') == 'halted_no_automatic_resume',
                  'Permanent stage halt was deleted or control state reset')
        sha = w.sha_file(halt)
        w.require(w.load(halt).get('plan_sha256') == plan['plan_sha256'] and
                  state.get('halt_sha256') == sha and (receipts / (sha + '.json')).is_file(),
                  'Stage halt state or permanent receipt changed')
        for p in receipts.iterdir():
            w.require(p.name == sha + '.json' and p.is_file() and w.sha_file(p) == sha,
                      'Stage halt receipt changed')


def _receipts(root):
    out = []
    for p in sorted((root / 'run_receipts').glob('*.json')):
        w.require(len(p.stem) == 6 and p.stem.isdigit() and int(p.stem) > 0,
                  'Invalid stage receipt filename')
        out.append((int(p.stem), recovery.signed(p, 'receipt_sha256')))
    return out


def _write_receipt(root, answer):
    directory = root / 'run_receipts'; directory.mkdir(exist_ok=True)
    sequence = max((n for n, _ in _receipts(root)), default=0) + 1
    name = f'{sequence:06d}.json'
    w.require(not (directory / name).exists(), 'Refuse to overwrite stage receipt')
    answer = {**answer, 'receipt_sha256': w.digest(answer)}
    w.write(directory, name, answer)


def _checkpoint_receipted(root, child, c, saved):
    receipts = _receipts(root)
    if saved not in c['checkpoint_saved_rows']:
        return True
    summary = child / f'checkpoint_{saved:08d}' / 'summary.json'
    for _, doc in receipts:
        if (doc.get('saved_active_rows') != saved or doc.get('checkpoint_target_saved_rows') != saved
                or doc.get('status') not in {'checkpoint_reached_pending_lightweight_check',
                                            'bounded_stage_finished_pending_review'}):
            continue
        runtime = doc.get('runtime_binding', {})
        w.require(runtime.get('capsule_file_sha256') == w.sha_file(root / 'capsule.json') and
                  runtime.get('plan_sha256') == c['plan_sha256'], 'Checkpoint receipt belongs to another stage')
        w.require(summary.is_file() and runtime.get('checkpoint_summary_sha256') == w.sha_file(summary),
                  'Receipted checkpoint summary missing or changed')
        # A later segment may already have a durable response before its first
        # native commit. Preserve the closed checkpoint's exact ledger prefix,
        # allowing validated append-only calls for the next authorized batch.
        count = runtime.get('transport_event_count')
        lines = (child / 'transport_calls.jsonl').read_bytes().splitlines(keepends=True)
        w.require(type(count) is int and 0 <= count <= len(lines) and count % 2 == 0,
                  'Checkpoint transport event count is invalid or truncated')
        w.require(runtime.get('transport_ledger_sha256') == hashlib.sha256(b''.join(lines[:count])).hexdigest(),
                  'Receipted checkpoint transport prefix changed')
        recovery.verify_bindings(runtime['native_databases'])
        return True
    return False


def _reconcile_saved_boundary(child, media, plan, saved):
    """Close a commit-before-checkpoint crash offline, then return to the caller."""
    if saved == plan['row_count']:
        # Every original batch is complete; the frozen worker replays/checks and
        # writes its final identity context without reaching a fetch operation.
        def never_fetch(*args, **kwargs):
            raise AssertionError('A fully saved child must not fetch while closing')
        return w.run(child, media, max_batches=1, fetcher=never_fetch)
    try:
        w._snapshot_reconciliation(child, plan, w._ledger(child, plan))
        _, registry = w.load_plan(child, media)
        seen = w.seed_history_identities(plan['seed_context'].get('history_index'))
        history = list(plan['seed_context']['source_history']); summaries = []; count = 0
        for batch in plan['batches']:
            rows = w._rows(child, batch)
            if not rows:
                break
            w.require(len(rows) == batch['row_count'], 'Saved checkpoint has an incomplete original batch')
            records = []
            for row in rows:
                record, trigger = w._assess_row(child, plan, row, child / 'batches' / batch['batch_id'], registry, seen, history)
                if trigger:
                    return w._halt(child, plan, trigger, sample_id=row['sample_id'], risks=record['automatic_flags'])
                records.append(record)
            summaries.append(w._batch_check(child, batch, rows, records)); count += len(rows)
        w.require(count == saved, 'Offline checkpoint replay count changed')
        w._checkpoint(child, plan, summaries)
        return w._state(child, plan, w.PENDING, checkpoint_reconciled_offline=True, result_rows=saved)
    except Exception as exc:
        return w._halt(child, plan, 'checkpoint_reconciliation_failed', detail=type(exc).__name__ + ': ' + str(exc))


def prepare(config_path):
    """Import the exact reviewed native prefix into one independent stage."""
    config_path = Path(config_path).resolve(); cfg = _config(config_path)
    source = Path(cfg['source_capsule']).resolve()
    old, oldplan, status = successor._source_inspect(source)
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
    target_index, targets = _scope(oldplan, cfg)
    # Reuse the proven source attempt/snapshot validation through its first-next-
    # batch view, then bind the entire explicitly authorized remainder separately.
    first_cfg = {**cfg, 'expected_batch_id': targets[0]['batch_id'],
                 'expected_sample_ids': targets[0]['sample_ids']}
    batches, entries, _, _ = successor._closed_source(source, old, oldplan, status, first_cfg)
    protected = {**old['protected_sources'], **old['recovery_evidence'],
                 **recovery.bindings(successor._files(source) + successor._files(oldchild) + [config_path]),
                 **successor._closure(cfg, source, oldchild, cfg['expected_active_saved'])}
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
        for p in successor._files(B):
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
         'master_max_fetch_calls': old['master_max_fetch_calls'], 'stage_batch_ids': cfg['expected_batch_ids'],
         'stage_sample_ids': cfg['expected_sample_ids'], 'stage_additional_transport_limit': budget,
         'checkpoint_saved_rows': cfg['checkpoint_saved_rows'], 'stage_end_saved_rows': plan['row_count'],
         'imported_payloads_sha256': w.digest([r for _, rows in batches for r in rows]),
         'imported_transport_events_sha256': w.digest(w._ledger(child, plan)),
         'imported_transport_event_count': len(entries), 'native_copied_bytes_preserved': True,
         'ready_for_bounded_stage': True, 'manual_review_status': 'not_reviewed', 'article_acceptance': False,
         'automatic_promotion': False,
         'recovery_evidence': recovery.bindings([root / n for n in ('Copied_Native_Files.json', 'Inherited_Context.json', 'Inherited_Review_Obligations.json')])}
    c['capsule_sha256'] = w.digest(c); w.write(root, 'capsule.json', c)
    w._state(child, plan, w.PENDING, offline_bounded_stage_prepared=True,
             imported_result_rows=cfg['expected_active_saved'], new_transport_calls=0)
    recovery.verify_bindings(protected)
    inspect(root)
    return c


def inspect(root):
    """Read-only scope, immutable-prefix and charged-request validation."""
    root = Path(root).resolve(); c = recovery.signed(root / 'capsule.json', 'capsule_sha256')
    w.require(c['schema'] == SCHEMA and c['code'] == code_binding(), 'Stage code/schema changed')
    recovery.verify_bindings(c['protected_sources']); recovery.verify_bindings(c['recovery_evidence'])
    cfg = _config(c['config_path']); child = Path(c['new_child'])
    plan, _ = w.load_plan(child, c['isolated_media']); state = w.load(child / 'continuous_state.json')
    w.require(state.get('schema') == w.MODE and state.get('plan_sha256') == plan['plan_sha256'],
              'Stage control state belongs to another plan')
    _halt_integrity(child, plan, state)
    for name in ('source_capsule', 'new_child', 'isolated_media'):
        w.require(str(Path(cfg[name]).resolve()) == c[name], 'Stage configuration path changed')
    w.require(Path(cfg['capsule']).resolve() == root and plan['plan_sha256'] == c['plan_sha256'],
              'Stage plan/path changed')
    oldplan = recovery.signed(Path(c['source_child']) / 'continuous_plan.json', 'plan_sha256')
    w.require(oldplan['plan_sha256'] == c['source_plan_sha256'], 'Source plan changed')
    for key in ('batches', 'seed_context', 'continuation_policy', 'row_count', 'queue_sha256',
                'registry_sha256', 'date_start', 'date_end_exclusive', 'original_queue', 'exclusions',
                'pause_seconds', 'timeout', 'min_free_bytes'):
        w.require(plan[key] == oldplan[key], 'Inherited frozen plan component changed: ' + key)
    w.require(c['active_imported_rows'] == cfg['expected_active_saved'], 'Imported row bound changed')
    index, targets = _scope(plan, cfg)
    for key, configured in (('stage_batch_ids', 'expected_batch_ids'),
                            ('stage_sample_ids', 'expected_sample_ids'),
                            ('stage_additional_transport_limit', 'max_additional_transport_calls'),
                            ('checkpoint_saved_rows', 'checkpoint_saved_rows')):
        w.require(c[key] == cfg[configured], 'Capsule stage scope changed: ' + key)
    w.require(c['stage_end_saved_rows'] == plan['row_count'], 'Stage final boundary changed')
    expected_cap = c['active_imported_transport_calls'] + c['stage_additional_transport_limit']
    w.require(plan['max_fetch_calls'] == expected_cap and
              c['original_completed_transport_calls'] + expected_cap <= c['master_max_fetch_calls'],
              'Frozen child/global transport budget changed')
    for relative, expected in w.load(root / 'Copied_Native_Files.json').items():
        w.require(w.sha_file(w.pilot.safe_path(child, relative)) == expected,
                  'Inherited native file changed')
    batches = [(b, w._rows(child, b)) for b in plan['batches']]
    frontier_seen = False
    for i, (batch, rows) in enumerate(batches):
        if i < index:
            w.require(len(rows) == batch['row_count'], 'Inherited batch lost rows')
        if frontier_seen:
            B = child / 'batches' / batch['batch_id']
            w.require(not rows and not (B / 'pilot.sqlite').exists() and not (B / 'manifest.json').exists(),
                      'Later batch initialized before the unfinished batch completed')
        if len(rows) < batch['row_count']:
            frontier_seen = True
    prefix = [r for _, rows in batches[:index] for r in rows]
    w.require(len(prefix) == c['active_imported_rows'] and w.digest(prefix) == c['imported_payloads_sha256'],
              'Imported native prefix changed')
    entries = w._ledger(child, plan); count = c['imported_transport_event_count']
    w.require(len(entries) >= count and w.digest(entries[:count]) == c['imported_transport_events_sha256'],
              'Imported transport prefix changed')
    calls = sum(e['event'] == 'start' for e in entries)
    w.require(sum(e['event'] == 'start' for e in entries[:count]) == c['active_imported_transport_calls'],
              'Inherited transport count changed')
    queue = w.readcsv(child / 'queue.csv'); by_id = {r['sample_id']: r['url'] for r in queue}
    allowed = {b['batch_id']: {by_id[sid] for sid in b['sample_ids']} for b in targets}
    w.require(all(e['batch_id'] in allowed and e['url'] in allowed[e['batch_id']]
                  for e in entries[count:]), 'Transport escaped its authorized original batch')
    new_calls = calls - c['active_imported_transport_calls']
    w.require(0 <= new_calls <= c['stage_additional_transport_limit'] and
              c['original_completed_transport_calls'] + calls <= c['master_max_fetch_calls'],
              'Stage transport budget exceeded')
    saved = sum(len(rows) for _, rows in batches)
    pending = not _checkpoint_receipted(root, child, c, saved)
    next_checkpoint = saved if pending else next((n for n in c['checkpoint_saved_rows'] if n > saved), None)
    return c, plan, {'saved_active_rows': saved, 'new_saved_rows': saved - c['active_imported_rows'],
                    'stage_remaining_urls': c['stage_end_saved_rows'] - saved,
                    'new_transport_reservations': new_calls,
                    'total_charged_transport_reservations': c['original_completed_transport_calls'] + calls,
                    'next_checkpoint_saved_rows': next_checkpoint,
                    'checkpoint_reconciliation_pending': pending,
                    'source_capsule_preserved': True, 'article_acceptance': False}


def run_checkpoint(root, *, allow_network=False, fetcher=None, clock=w.time.time,
                   sleep=w.time.sleep, disk_free=None):
    """Run at most to the next frozen checkpoint; never call the scheduler."""
    w.require(allow_network or fetcher is not None,
              'Explicit live authorization or injected offline fetcher required')
    root = Path(root).resolve()
    with w.pilot.exclusive_run(root):
        c, plan, before = inspect(root); child = Path(c['new_child'])
        w.require(c['ready_for_bounded_stage'], 'Stage is not ready')
        if (child / 'safety_halt.json').exists():
            return {**before, 'status': 'halted_no_automatic_resume', 'network_calls_this_invocation': 0}
        if before['stage_remaining_urls'] == 0 and not before['checkpoint_reconciliation_pending']:
            return {**before, 'status': 'bounded_stage_finished_pending_review', 'network_calls_this_invocation': 0}
        stop_at = before['next_checkpoint_saved_rows']
        ends = []; consumed = 0
        for batch in plan['batches']:
            consumed += batch['row_count']; ends.append((consumed, batch))
        active_batches = [b for end, b in ends if before['saved_active_rows'] < end <= stop_at]
        w.require(active_batches or before['checkpoint_reconciliation_pending'],
                  'No unfinished authorized batch before checkpoint')
        queue = w.readcsv(child / 'queue.csv'); by_id = {r['sample_id']: r['url'] for r in queue}
        allowed = {b['batch_id']: {by_id[sid] for sid in b['sample_ids']} for b in active_batches}
        calls = 0
        def bounded_fetch(url, timeout, **kwargs):
            nonlocal calls
            ledger = w._ledger(child, plan); last = ledger[-1]
            w.require(last['event'] == 'start' and last['batch_id'] in allowed and
                      url == last['url'] and url in allowed[last['batch_id']],
                      'Request outside the next authorized checkpoint segment')
            count = sum(e['event'] == 'start' for e in ledger) - c['active_imported_transport_calls']
            w.require(count <= c['stage_additional_transport_limit'], 'Stage call budget exhausted')
            w.require(c['original_completed_transport_calls'] + c['active_imported_transport_calls'] + count
                      <= c['master_max_fetch_calls'], 'Global budget exhausted')
            calls += 1
            if fetcher is not None:
                return fetcher(url, timeout, **kwargs)
            from .capabilities import fetch
            return fetch(url, timeout, **kwargs)
        if before['checkpoint_reconciliation_pending']:
            result = _reconcile_saved_boundary(child, c['isolated_media'], plan, before['saved_active_rows'])
        else:
            result = w.run(child, c['isolated_media'], max_batches=len(active_batches), fetcher=bounded_fetch,
                           clock=clock, sleep=sleep, disk_free=disk_free)
        _, _, after = inspect(root)
        w.require(after['saved_active_rows'] <= stop_at, 'Worker exceeded the checkpoint boundary')
        status = result['status']
        if 'halt' not in status and after['saved_active_rows'] == stop_at:
            status = ('bounded_stage_finished_pending_review' if after['stage_remaining_urls'] == 0
                      else 'checkpoint_reached_pending_lightweight_check')
        answer = {**after, 'worker_result': result, 'network_calls_this_invocation': calls,
                  'checkpoint_target_saved_rows': stop_at, 'status': status,
                  'author': 'Kevin', 'created_at': w.now(), 'human_approvals_added': 0,
                  'runtime_binding': {
                      'plan_sha256': plan['plan_sha256'],
                      'capsule_file_sha256': w.sha_file(root / 'capsule.json'),
                      'transport_ledger_sha256': w.sha_file(child / 'transport_calls.jsonl'),
                      'transport_event_count': len(w._ledger(child, plan)),
                      'transport_state_sha256': w.sha_file(child / 'transport_state.json'),
                      'continuous_state_sha256': w.sha_file(child / 'continuous_state.json'),
                      'native_databases': recovery.bindings(sorted(child.glob('batches/*/pilot.sqlite')))}}
        checkpoint = child / f'checkpoint_{stop_at:08d}' / 'summary.json'
        if after['saved_active_rows'] == stop_at and 'halt' not in result['status']:
            w.require(checkpoint.is_file(), 'Checkpoint summary missing at completed stop')
            answer['runtime_binding']['checkpoint_summary_sha256'] = w.sha_file(checkpoint)
            answer['checkpoint_reconciliation_pending'] = False
            answer['next_checkpoint_saved_rows'] = next((n for n in c['checkpoint_saved_rows'] if n > stop_at), None)
        # Keep a small append-only invocation receipt, including interruptions.
        _write_receipt(root, answer)
        # Inspection now sees this closed checkpoint rather than its crash window.
        _, _, settled = inspect(root); answer.update(settled)
        return answer


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='command', required=True)
    a = sub.add_parser('prepare'); a.add_argument('--config', type=Path, required=True)
    a = sub.add_parser('inspect'); a.add_argument('--capsule', type=Path, required=True)
    a = sub.add_parser('run-checkpoint'); a.add_argument('--capsule', type=Path, required=True)
    a.add_argument('--allow-network', action='store_true')
    args = p.parse_args(argv)
    if args.command == 'prepare':
        result = prepare(args.config)
    elif args.command == 'inspect':
        c, _, result = inspect(args.capsule)
        result.update(ready_for_bounded_stage=c['ready_for_bounded_stage'], stage_url_limit=len(c['stage_sample_ids']))
    else:
        result = run_checkpoint(args.capsule, allow_network=args.allow_network)
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0

"""Kevin: one writer for the expressly frozen, remaining Tiempo queue.

Reuses v5 freeze/storage/source checks and a pause-aware worker. Checkpoint AI
review is an external, evidence-bound gate, never an automatic human approval.
Old campaigns are references, not copied or edited. No scheduler/agent service
is installed and no external message is sent by this module.
"""
from __future__ import annotations

from pathlib import Path
from collections import Counter
import argparse
import hashlib
import json
import math
import os
import shutil
import socket
import shlex
import sqlite3
import ssl
import subprocess
import sys
import time
import uuid

from . import tiempo_continuous_v5 as w
from . import tiempo_scheduler_v5 as original
from . import tiempo_resumable_worker as worker
from . import tiempo_stage_review as review

SCHEMA = 'tiempo-remaining-frozen-campaign-v1'
load, write, sha, require = w.load, w.write, w.sha_file, w.require


def code_binding():
    base = Path(__file__).parent
    return {**w.program_hashes(), **{n: sha(base / n) for n in (
        'tiempo_remaining_campaign.py', 'tiempo_resumable_worker.py', 'tiempo_stage_review.py',
        'tiempo_connection_recovery.py')},
        'remaining_cli': sha(base.parent / 'scripts/run_tiempo_remaining.py')}


def _bound(path):
    p = Path(path).resolve()
    return {'path': str(p), 'sha256': sha(p)}


def _verify(binding):
    require(sha(binding['path']) == binding['sha256'], 'Bound evidence changed: ' + binding['path'])


def _signed(path, key):
    doc = load(path); unsigned = dict(doc); value = unsigned.pop(key, None)
    require(value == w.digest(unsigned), 'Signed control evidence changed: ' + str(path))
    return doc


def _save_once(path, value):
    path = Path(path)
    if path.exists():
        require(load(path) == value, 'Refuse to replace immutable evidence: ' + str(path))
    else:
        write(path.parent, path.name, value)


def events(root):
    result = []; previous = None
    for i, path in enumerate(sorted((Path(root) / 'events').glob('*.json')), 1):
        require(path.name == f'{i:06d}.json', 'Campaign event sequence is missing or changed')
        doc = _signed(path, 'event_sha256')
        require(doc['sequence'] == i and doc['previous_event_sha256'] == previous,
                'Campaign event chain changed')
        previous = doc['event_sha256']; result.append(doc)
    return result


def event(root, kind, **details):
    old = events(root)
    doc = {'schema': SCHEMA, 'author': 'Kevin', 'created_at': w.now(), 'sequence': len(old) + 1,
           'previous_event_sha256': old[-1]['event_sha256'] if old else None,
           'kind': kind, 'article_acceptance': False, 'human_approval': False, **details}
    doc['event_sha256'] = w.digest(doc)
    _save_once(Path(root) / 'events' / f'{len(old)+1:06d}.json', doc)
    return doc


def _state(root, status, **details):
    data = {'schema': SCHEMA, 'author': 'Kevin', 'updated_at': w.now(), 'status': status,
            'pid': os.getpid(), 'manual_review_status': 'not_reviewed',
            'article_acceptance': False, 'human_approval': False, **details}
    write(root, 'status.json', data)
    return data


def _technical_stop(root, reason, **details):
    path = Path(root) / 'technical_stop.json'
    if not path.exists():
        value = {'schema': SCHEMA, 'author': 'Kevin', 'created_at': w.now(),
                 'reason': reason, 'article_acceptance': False, **details}
        _save_once(path, value)
        event(root, 'technical_stop', evidence=_bound(path))
    return _state(root, 'technical_stop_requires_investigation', evidence=_bound(path),
                  reason=load(path)['reason'])


def _verify_old(preflight):
    for binding in preflight['source_bindings'].values():
        _verify(binding)
    for binding in preflight['protected_control_bindings']:
        _verify(binding)
    for entry in preflight['review_obligations']['native_pending_file_bindings']:
        _verify(entry); _verify(entry['summary'])
    def verify_references(value):
        if isinstance(value, dict):
            if 'path' in value and 'sha256' in value:
                _verify(value)
            for nested in value.values():
                verify_references(nested)
        elif isinstance(value, list):
            for nested in value:
                verify_references(nested)
    verify_references(preflight['review_obligations'])


def _verify_gate_event(entry):
    """Validate compact reading evidence without replaying unchanged raw pages."""
    _verify(entry['selection']); _verify(entry['coverage'])
    coverage = review._coverage(entry['coverage']['path'])
    require(coverage['selection_binding'] == entry['selection'],
            'Approved coverage belongs to a different source selection')
    return coverage


def _outstanding_safe_pause(ev):
    paused = max((e['sequence'] for e in ev if e['kind'] == 'safe_pause'), default=0)
    resumed = max((e['sequence'] for e in ev if e['kind'] == 'resume_acknowledgment'), default=0)
    return paused > resumed


def prepare(config_path):
    """Offline: bind the original partition and a completed predecessor, no HTTP."""
    cfg = load(config_path); root = Path(cfg['root']).resolve(); media = root / 'Media'
    require(not root.exists(), 'Use a new empty main directory, never broaden an exhausted run')
    preflight_binding = cfg['preflight']; _verify(preflight_binding); pre = load(preflight_binding['path'])
    require(pre['status'] == 'PASS_SCOPE_AND_SOURCE_PREFLIGHT' and not pre['issues'], 'Scope preflight is not valid')
    _verify_old(pre)
    prepared = Path(pre['freeze_input_paths']['prepared_path']).resolve()
    manifest = original.validate_preparation(prepared)
    source = Path(pre['source_runtime']).resolve()
    require(root != source and root not in source.parents and source not in root.parents,
            'Successor must be separate from the old child')
    source_plan = load(source / 'continuous_plan.json'); source_state = load(source / 'continuous_state.json')
    require(source_state.get('collection_inputs_finished') and not (source / 'safety_halt.json').exists(),
            'Predecessor is not completely closed')
    context = load(source / 'continuation_context.json')
    require(sha(source / 'continuation_context.json') == source_state['continuation_context_sha256'],
            'Predecessor continuation context changed')
    history = w.load_history_index(context['history_index'])
    first, last = pre['boundary']['remaining_original_plan_indices']
    parts = manifest['parts'][first-1:last]
    require(first > 1 and last == len(manifest['parts']) and len(parts) == last-first+1,
            'Only the complete frozen remainder is authorized')
    donor_rows = w.readcsv(source / 'queue.csv')
    source_part = w.readcsv(prepared / manifest['parts'][first-2]['path'])
    require([r['url_key'] for r in donor_rows] == [r['url_key'] for r in source_part], 'Wrong predecessor queue')
    rows = [r for p in parts for r in w.readcsv(prepared / p['path'])]
    keys = [r['url_key'] for r in rows]; seen = {r['url'] for r in history}
    require(len(keys) == len(set(keys)) and not set(keys) & seen, 'Repeated old or new requested URL')
    baseline = sum(p['rows'] for p in manifest['parts'][:first-1])
    require(baseline == pre['boundary']['reconciled_completed_request_URLs'] and
            len(rows) == pre['boundary']['remaining_request_URLs'] and
            baseline + len(rows) == manifest['row_count'], 'Remaining partition counts changed')
    ledger = w._ledger(source, source_plan)
    require(not ledger or ledger[-1]['event'] == 'finish', 'Predecessor has an open request')
    require(pre['boundary']['global_identity_records_including_legacy2270'] == len(history), 'History count changed')
    require(cfg['max_new_calls'] == 3 * len(rows), 'New request bound must match the existing retry policy')
    require(source_plan['min_free_bytes'] == 10*1024**3 or cfg.get('synthetic_fixture'), 'Existing10GiB floor required')
    root.mkdir(parents=True)
    # This is a small reference manifest, not copies of old raw data or pending CSVs.
    obligations = {'schema': SCHEMA, 'author': 'Kevin', **pre['review_obligations'],
                   'source_preflight': preflight_binding, 'human_approvals_added': 0}
    write(root, 'Inherited_Review_Obligations.json', obligations)
    doc = {'schema': SCHEMA, 'author': 'Kevin', 'created_at': w.now(), 'root': str(root),
           'media': str(media), 'config_source': _bound(config_path), 'preflight': preflight_binding,
           'source': str(source), 'source_context': _bound(source / 'continuation_context.json'),
           'source_ledger': _bound(source / 'transport_calls.jsonl'), 'source_history_records': len(history),
           'prepared': str(prepared), 'prepared_manifest': _bound(prepared / 'preparation.json'),
           'queue': {'path': manifest['queue_db'], 'sha256': manifest['queue_sha256']},
           'parts': [{**p, 'path': str(prepared / p['path'])} for p in parts],
           'baseline_saved': baseline, 'baseline_calls': pre['boundary']['global_charged_calls'],
           'remaining_rows': len(rows), 'max_new_calls': cfg['max_new_calls'],
           'registry': pre['freeze_input_paths']['registry'], 'exclusions': manifest['exclusions'],
           'date_start': manifest['date_start'], 'date_end_exclusive': manifest['date_end_exclusive'],
           'pause_seconds': source_plan['pause_seconds'], 'timeout': source_plan['timeout'],
           'min_free_bytes': source_plan['min_free_bytes'],
           'initial_allocated_bytes_per_url': pre['storage_projection']['observed_allocated_bytes_per_URL'],
           'forecast_growth_multiplier': cfg.get('forecast_growth_multiplier', 1.1),
           'historical_ai_receipts': [{**item, 'sha256': sha(item.get('coverage') or item['receipt'])}
                                     for item in cfg.get('historical_ai_receipts', [])],
           'connection_recovery_pending': bool(cfg.get('connection_recovery_preparation')),
           'obligations': _bound(root / 'Inherited_Review_Obligations.json'),
           'synthetic_fixture': bool(cfg.get('synthetic_fixture')),
           'program_sha256': code_binding(), 'manual_review_status': 'not_reviewed',
           'article_acceptance': False, 'human_approval': False}
    require(1 <= doc['forecast_growth_multiplier'] <= 2, 'Invalid storage forecast multiplier')
    doc['campaign_sha256'] = w.digest(doc); write(root, 'campaign.json', doc)
    event(root, 'prepared', campaign_sha256=doc['campaign_sha256'], expected_remaining=len(rows), network_requests=0)
    return _state(root, 'prepared_offline_not_started', new_saved=0, new_calls=0, remaining=len(rows))


def read_bound(root, *, full=False):
    root = Path(root).resolve(); m = _signed(root / 'campaign.json', 'campaign_sha256')
    require(m['schema'] == SCHEMA and m['root'] == str(root), 'Wrong campaign namespace')
    require(m['program_sha256'] == code_binding(), 'Frozen code changed; pause and validate a successor version')
    require(not m.get('connection_recovery_pending'), 'Recovery preparation incomplete; no run is permitted')
    if m.get('connection_recovery'):
        from . import tiempo_connection_recovery
        tiempo_connection_recovery.verify(m, full=full)
    for key in ('config_source', 'preflight', 'prepared_manifest', 'source_context', 'source_ledger', 'registry', 'obligations'):
        _verify(m[key])
    for p in m['parts']:
        _verify(p)
    for item in m['historical_ai_receipts']:
        _verify({'path': item.get('coverage') or item['receipt'], 'sha256': item['sha256']})
    if full:
        _verify(m['queue']); _verify_old(load(m['preflight']['path']))
        w.load_history_index(load(m['source_context']['path'])['history_index'])
    ev = events(root)
    stops = [e for e in ev if e['kind'] == 'technical_stop']
    if stops:
        require((root / 'technical_stop.json').exists(), 'A technical stop was removed; refusing resume')
        _verify(stops[-1]['evidence'])
    gates = [e for e in ev if e['kind'] == 'checkpoint_gate_satisfied']
    for e in gates:
        _verify(e['selection']); _verify(e['coverage'])
    if gates:
        _verify_gate_event(gates[-1])
    return m, ev


def child_path(m, index):
    return Path(m['media']) / 'data/00-newspaper_data/crawler/pilots/Kevin/tiempo_continuous_v5' / f'remaining_plan_{index:06d}'


def _counts(child, plan):
    rows = 0; pending = 0
    for b in plan['batches']:
        dbp = child / 'batches' / b['batch_id'] / 'pilot.sqlite'
        if not dbp.exists():
            continue
        with sqlite3.connect(dbp.as_uri()+'?mode=ro', uri=True) as db:
            rows += db.execute('select count(*) from articles').fetchone()[0]
            pending += db.execute('select count(*) from fetch_attempts where completed_at is null').fetchone()[0]
    entries = w._ledger(child, plan)
    return {'saved': rows, 'calls': sum(e['event']=='start' for e in entries),
            'pending_native_attempts': pending, 'open_transport': bool(entries and entries[-1]['event']!='finish')}


def _completed(m, ev):
    done = [e for e in ev if e['kind'] == 'child_complete']
    require([d['index'] for d in done] == [p['plan_index'] for p in m['parts'][:len(done)]],
            'Completed child chain is not an exact ordered prefix')
    context = load(m['source_context']['path']); rows = calls = 0
    for d in done:
        _verify(d['receipt']); doc = _signed(d['receipt']['path'], 'receipt_sha256')
        for b in doc['bindings']:
            _verify(b)
        require(doc['campaign_sha256'] == m['campaign_sha256'] and doc['index'] == d['index'], 'Wrong completion chain')
        child = child_path(m, d['index']); context = load(child / 'continuation_context.json')
        rows += doc['saved']; calls += doc['calls']
    return done, context, rows, calls


def pause_requests(root):
    result = {}
    for p in sorted((Path(root)/'control/pause_requests').glob('*.json')):
        doc = load(p)
        require(doc['request_id'] == p.stem and doc['kind'] == 'user_pause_request', 'Invalid pause control')
        result[p.stem] = _bound(p)
    return result


def request_pause(root):
    root = Path(root).resolve(); require((root/'campaign.json').is_file(), 'Unknown campaign')
    rid = str(uuid.uuid4())
    doc = {'author': 'Kevin', 'kind': 'user_pause_request', 'request_id': rid, 'created_at': w.now(),
           'meaning': 'Request only; wait for paused_safe or a reconciliation/technical state before closing laptop.'}
    _save_once(root/'control/pause_requests'/f'{rid}.json', doc)
    return {'status': 'pause_requested_not_yet_confirmed', 'request_id': rid}


def _acknowledged(ev):
    return {rid for e in ev if e['kind']=='resume_acknowledgment' for rid in e['pause_request_ids']}


def network_probe(host='www.tiempo.com.mx', timeout=8):
    """DNS and TLS connection only; no article/HTTP request or discovery call."""
    context = ssl.create_default_context()
    with socket.create_connection((host,443), timeout=timeout) as tcp:
        with context.wrap_socket(tcp, server_hostname=host):
            pass
    return {'status':'dns_tls_reachable','host':host,'http_requests':0,'checked_at':w.now(),
            'limitation':'Does not certify current article responses or behavior after laptop sleep.'}


def _allocated(path):
    return sum(p.stat().st_blocks*512 for p in Path(path).rglob('*') if p.is_file() and not p.is_symlink())


def storage_forecast(m, completed_rows, remaining, *, disk_free=None, child_allocated=None):
    root = Path(m['root']); free = disk_free(root) if disk_free else shutil.disk_usage(root).free
    require(isinstance(free,(int,float)) and math.isfinite(free), 'Invalid free-space measurement')
    measured = child_allocated if child_allocated is not None else _allocated(root/'Media')
    observed = measured / completed_rows if completed_rows else m['initial_allocated_bytes_per_url']
    # Never forecast less than the verified predecessor's actual per-URL use.
    rate = max(observed, m['initial_allocated_bytes_per_url'])
    projected = math.ceil(rate * remaining * m['forecast_growth_multiplier'])
    return {'free_bytes':free,'saved_new':completed_rows,'remaining_urls':remaining,
            'allocated_new_bytes':measured,'observed_bytes_per_url':observed,'projection_bytes_per_url':rate,
            'growth_multiplier':m['forecast_growth_multiplier'],'projected_remaining_bytes':projected,
            'reserve_bytes':m['min_free_bytes'],'enough_for_forecast_and_floor':free-projected>=m['min_free_bytes'],
            'measurement_is_estimate':True,'auto_deletion':False}


def inspect(root, *, full=False):
    m, ev = read_bound(root, full=full); done, context, saved, calls = _completed(m, ev)
    active = None
    if len(done)<len(m['parts']):
        part=m['parts'][len(done)]; child=child_path(m, part['plan_index'])
        if child.exists():
            require((child/'continuous_plan.json').is_file(), 'Interrupted child initialization requires review')
            counts=_counts(child,load(child/'continuous_plan.json')); saved+=counts['saved']; calls+=counts['calls']
            active={'index':part['plan_index'],'path':str(child),**counts}
    return {'status':load(Path(root)/'status.json')['status'], 'completed_children':len(done),
            'new_saved':saved,'new_calls':calls,'original_plan_saved':m['baseline_saved']+saved,
            'global_charged_calls':m['baseline_calls']+calls,'remaining':m['remaining_rows']-saved,
            'active':active,'pending_pause_requests':sorted(set(pause_requests(root))-_acknowledged(ev)),
            'technical_stop':(Path(root)/'technical_stop.json').exists(), 'article_acceptance':False}


def other_collectors():
    """Read processes, excluding status/pause commands and this writer."""
    names={'run_tiempo_remaining.py','run_tiempo_scheduler_v5.py','run_tiempo_continuous.py',
           'run_tiempo_bounded_stage.py','run_tiempo_recovery.py','run_tiempo_successor.py'}
    matches=[]
    for line in subprocess.check_output(['ps','-axo','pid,args'],text=True).splitlines()[1:]:
        try:
            pid,command=line.strip().split(None,1);args=shlex.split(command)
        except ValueError:continue
        if int(pid)==os.getpid() or not args or 'python' not in Path(args[0]).name.lower():continue
        for i,arg in enumerate(args[:-1]):
            if Path(arg).name in names and args[i+1] in {'run','trial','run-checkpoint'}:
                matches.append({'pid':int(pid),'command':command});break
    return matches


def _adopt_closed_child(m,part,child):
    """A crash after native completion receipt cannot cause a repeat invocation."""
    path=child/'remaining_completion_receipt.json'
    if not path.exists():return None
    doc=_signed(path,'receipt_sha256')
    require(doc['campaign_sha256']==m['campaign_sha256'] and doc['index']==part['plan_index'],
            'Unaccounted completion receipt belongs to another child')
    for binding in doc['bindings']:_verify(binding)
    plan=load(child/'continuous_plan.json');counts=_counts(child,plan);state=load(child/'continuous_state.json')
    require(state.get('collection_inputs_finished') and counts['saved']==doc['saved']==part['rows'] and
            counts['calls']==doc['calls'] and not counts['open_transport'] and not counts['pending_native_attempts'],
            'Unaccounted completion receipt has incomplete native evidence')
    targets=list(range(400,part['rows']+1,400))
    if not targets or targets[-1]!=part['rows']:targets.append(part['rows'])
    approved=[e for e in events(m['root']) if e['kind']=='checkpoint_gate_satisfied' and e['index']==part['plan_index']]
    require([e['rows'] for e in approved]==targets,'Unaccounted child has missing checkpoint review gates')
    for e in approved:_verify_gate_event(e)
    return doc,path


def _complete_child(m, part, child, result):
    require(result.get('collection_inputs_finished'), 'Saved count alone cannot close a child')
    plan = load(child/'continuous_plan.json'); counts=_counts(child,plan)
    require(counts['saved']==part['rows'] and not counts['open_transport'] and not counts['pending_native_attempts'],
            'Child has incomplete results or requests')
    context=load(child/'continuation_context.json')
    require(result['continuation_context_sha256']==sha(child/'continuation_context.json'), 'Child context mismatch')
    w.load_history_index(context['history_index'])
    paths=[child/n for n in ['continuous_plan.json','queue.csv','continuous_state.json','transport_calls.jsonl',
                            'transport_state.json','continuation_context.json','identity_index.json']]
    paths+=sorted(child.glob('batches/*/pilot.sqlite'))
    paths+=sorted(child.glob('batches/*/export_manifest.json'))
    paths+=sorted(child.glob('checkpoint_*/summary.json'))
    doc={'schema':SCHEMA,'campaign_sha256':m['campaign_sha256'],'index':part['plan_index'],
         'saved':counts['saved'],'calls':counts['calls'],'bindings':[_bound(p) for p in paths],
         'article_acceptance':False,'manual_review_status':'not_reviewed'}
    doc['receipt_sha256']=w.digest(doc);p=child/'remaining_completion_receipt.json';_save_once(p,doc)
    return doc,p


def run(root, *, allow_network=False, resume=False, fetcher=None, clock=time.time, sleep=time.sleep,
        disk_free=None, probe=network_probe, wait_for_review=True, review_wait_seconds=5):
    """Finite frozen remainder; one process waits for actual AI review at checkpoints."""
    require(allow_network or fetcher is not None, 'Explicit network flag required')
    root=Path(root).resolve()
    with w.pilot.exclusive_run(root), w.pilot.exclusive_run(root.parent):
        require(not other_collectors(),'Another Tiempo collector is active; no second writer may start')
        m,ev=read_bound(root,full=True)
        require(not(m['synthetic_fixture'] and fetcher is None),'Synthetic fixture cannot access news websites')
        if (root/'technical_stop.json').exists():
            return _state(root,'technical_stop_requires_investigation',evidence=_bound(root/'technical_stop.json'))
        done,context,saved,calls=_completed(m,ev)
        if len(done)==len(m['parts']):
            return _state(root,'frozen_queue_processed_pending_coverage_review',new_saved=saved,new_calls=calls)
        ack=_acknowledged(ev); initial_requests=pause_requests(root); pending=set(initial_requests)-ack
        if (pending or _outstanding_safe_pause(ev)) and not resume:
            return {'status':'pause_request_pending_use_explicit_resume','request_ids':sorted(pending)}
        controller=worker.StopController()
        def requested():
            return controller() or bool(set(pause_requests(root))-ack)
        # Resume checks are offline first. A missing connection does not erase a normal pause.
        current=inspect(root)
        if current['active'] and (current['active']['open_transport'] or current['active']['pending_native_attempts']):
            # The worker may adopt a durable terminal response, but must prove that
            # locally before any network. Uncertain windows remain native halts.
            child=Path(current['active']['path']);plan=load(child/'continuous_plan.json')
            try:
                with w.pilot.exclusive_run(child.parent),w.pilot.exclusive_run(child):
                    w._snapshot_reconciliation(child,plan,w._ledger(child,plan))
            except Exception as exc:return _technical_stop(root,'request_reconciliation_required',detail=str(exc))
        if (disk_free(root) if disk_free else shutil.disk_usage(root).free)<m['min_free_bytes']:
            return _state(root,'resource_pause_low_disk',minimum_free_bytes=m['min_free_bytes'])
        if fetcher is None:
            try:network=probe()
            except Exception as exc:return _state(root,'waiting_for_network_not_started',detail=type(exc).__name__+': '+str(exc))
        else:network={'status':'injected_test_transport','http_requests':0}
        event(root,'connection_preflight',result=network)
        if resume:
            # Acknowledge only requests present before resume checks. New requests
            # arriving during those checks still cause a normal pause.
            ack.update(pending)
            event(root,'resume_acknowledgment',pause_request_ids=sorted(pending),evidence=[initial_requests[r] for r in sorted(pending)])
        previous_gates=[e for e in ev if e['kind']=='checkpoint_gate_satisfied']
        history=([{'coverage':previous_gates[-1]['coverage']['path'],'sha256':previous_gates[-1]['coverage']['sha256']}]
                 if previous_gates else list(m['historical_ai_receipts']))
        event(root,'run_started',baseline_saved=m['baseline_saved'],new_saved=saved,new_calls=calls)
        with worker.graceful_signals(controller):
            try:
                for part in m['parts'][len(done):]:
                    index=part['plan_index'];child=child_path(m,index)
                    if requested():
                        e=event(root,'safe_pause',new_saved=saved,new_calls=calls,between_children=True,
                                pause_requests=pause_requests(root))
                        return _state(root,'paused_safe',new_saved=saved,new_calls=calls,pause_event=e['event_sha256'])
                    forecast=storage_forecast(m,saved,m['remaining_rows']-saved,disk_free=disk_free)
                    event(root,'storage_forecast',**forecast)
                    if not forecast['enough_for_forecast_and_floor']:
                        return _state(root,'resource_pause_storage_forecast',new_saved=saved,new_calls=calls,forecast=forecast)
                    if not child.exists():
                        event(root,'child_initialization_started',index=index,input={'path':part['path'],'sha256':part['sha256']})
                        w.freeze(part['path'],child,m['media'],m['registry']['path'],m['registry']['sha256'],m['exclusions'],
                                 start=m['date_start'],end=m['date_end_exclusive'],max_fetch_calls=min(3*part['rows'],m['max_new_calls']-calls),
                                 queue_db_path=m['queue']['path'],queue_db_sha256=m['queue']['sha256'],pause_seconds=m['pause_seconds'],
                                 timeout=m['timeout'],min_free_bytes=m['min_free_bytes'],seed_context=context)
                        event(root,'child_initialized',index=index,plan=_bound(child/'continuous_plan.json'))
                    plan,_=w.load_plan(child,m['media'])
                    require(plan['seed_context']==context and plan['original_input_sha256']==part['sha256'] and
                            plan['row_count']==part['rows'] and plan['max_fetch_calls']<=m['max_new_calls']-calls,
                            'Cross-child identity, risk context, input or budget mismatch')
                    closed_without_event=_adopt_closed_child(m,part,child)
                    if closed_without_event:
                        closed,p=closed_without_event
                        saved+=closed['saved'];calls+=closed['calls']
                        event(root,'child_complete',index=index,receipt=_bound(p),new_saved=saved,new_calls=calls,
                              recovered_completion_receipt_without_new_requests=True)
                        context=load(child/'continuation_context.json')
                        continue
                    before_saved,before_calls=saved,calls
                    recovery=m.get('connection_recovery',{})
                    inherited_ack=(recovery['acknowledgment'] if recovery.get('child_index')==index else None)
                    def checkpoint_callback(current_child,current_plan,summaries):
                        require(code_binding()==m['program_sha256'],'Frozen running code changed')
                        n=sum(s['rows'] for s in summaries);counts=_counts(current_child,current_plan)
                        require(counts['saved']>=n and before_calls+counts['calls']<=m['max_new_calls'], 'Checkpoint count/budget mismatch')
                        folder=root/'reviews'/f'plan_{index:06d}'/f'checkpoint_{n:08d}'
                        selection_path=folder/f'selection_{n:08d}.json'
                        if not selection_path.exists():
                            selection=review.select_checkpoint(current_child,folder,checkpoint_rows=n,
                                      inherited_obligations=m['obligations']['path'],history_receipts=history,
                                      inherited_failure_acknowledgment=inherited_ack)
                            selection_path=Path(selection['selection_path'])
                        previous_events=events(root)
                        prior=[e for e in previous_events if e['kind']=='checkpoint_gate_satisfied' and e['index']==index and e['rows']==n]
                        if prior:
                            require(len(prior)==1,'Duplicate checkpoint approval event');_verify_gate_event(prior[0])
                            return not requested()
                        _state(root,'waiting_for_required_AI_review',active_child=index,child_saved=counts['saved'],
                               new_saved=before_saved+counts['saved'],new_calls=before_calls+counts['calls'],
                               selection=str(selection_path),required_review='Frozen selection must have actual AI receipts; no automatic approval.')
                        last_fingerprint=None
                        while True:
                            if requested():return False
                            paths=sorted((folder/'receipts').glob('*.json'))
                            fingerprint=tuple((str(p),sha(p)) for p in paths)
                            if fingerprint!=last_fingerprint:
                                gate=review.validate_gate(selection_path,paths);last_fingerprint=fingerprint
                                if gate['status']=='collection_gate_satisfied':
                                    coverage=review.seal_gate(selection_path,paths,folder/'coverage.json')
                                    binding=_bound(folder/'coverage.json')
                                    event(root,'checkpoint_gate_satisfied',index=index,rows=n,selection=_bound(selection_path),
                                          coverage=binding,new_saved=before_saved+counts['saved'],new_calls=before_calls+counts['calls'])
                                    history[:]=[{'coverage':binding['path'],'sha256':binding['sha256']}]
                                    _state(root,'collecting',active_child=index,child_saved=n,new_saved=before_saved+counts['saved'],
                                           new_calls=before_calls+counts['calls'])
                                    return not requested()
                                if gate.get('technical_blockers'):
                                    raise ValueError('Required AI/source gate has technical blockers: '+str(gate['technical_blockers']))
                            if not wait_for_review:return False
                            sleep(review_wait_seconds)
                    active_counts=_counts(child,plan)
                    _state(root,'collecting',active_child=index,new_saved=saved+active_counts['saved'],
                           new_calls=calls+active_counts['calls'])
                    result=worker.run(child,m['media'],max_batches=len(plan['batches']),stop_at_saved_rows=plan['row_count'],
                                      checkpoint_callback=checkpoint_callback,stop_requested=requested,install_signal_handlers=False,
                                      inherited_failure_acknowledgment=inherited_ack,
                                      allow_network=allow_network,fetcher=fetcher,clock=clock,sleep=sleep,disk_free=disk_free)
                    counts=_counts(child,plan);total_saved=before_saved+counts['saved'];total_calls=before_calls+counts['calls']
                    if result['status']==worker.PAUSED:
                        e=event(root,'safe_pause',new_saved=total_saved,new_calls=total_calls,native_pause={
                                'path':result['pause_receipt_path'],'sha256':result['pause_receipt_sha256']},pause_requests=pause_requests(root))
                        return _state(root,'paused_safe',new_saved=total_saved,new_calls=total_calls,active_child=index,
                                      pause_event=e['event_sha256'],native_pause_receipt=result['pause_receipt_path'])
                    if not result.get('collection_inputs_finished'):
                        return _technical_stop(root,'native_worker_stopped',native_result=result,new_saved=total_saved,new_calls=total_calls)
                    closed,p=_complete_child(m,part,child,result)
                    old=[e for e in events(root) if e['kind']=='child_complete' and e['index']==index]
                    require(not old,'Child completion already accounted')
                    event(root,'child_complete',index=index,receipt=_bound(p),new_saved=total_saved,new_calls=total_calls)
                    saved,calls=total_saved,total_calls;context=load(child/'continuation_context.json')
                    require(saved<=m['remaining_rows'] and calls<=m['max_new_calls'],'Campaign scope/budget exceeded')
                return _state(root,'frozen_queue_processed_pending_coverage_review',new_saved=saved,new_calls=calls,
                              original_plan_saved=m['baseline_saved']+saved,remaining=0)
            except Exception as exc:
                return _technical_stop(root,'supervisor_integrity_or_review_error',detail=type(exc).__name__+': '+str(exc))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True)
    a=s.add_parser('prepare');a.add_argument('--config',type=Path,required=True)
    for name in ('inspect','pause','run'):
        a=s.add_parser(name);a.add_argument('--root',type=Path,required=True)
        if name=='inspect':a.add_argument('--full',action='store_true')
        if name=='run':
            a.add_argument('--allow-network',action='store_true');a.add_argument('--resume',action='store_true')
    a=p.parse_args(argv)
    if a.command=='prepare':answer=prepare(a.config)
    elif a.command=='inspect':answer=inspect(a.root,full=a.full)
    elif a.command=='pause':answer=request_pause(a.root)
    else:answer=run(a.root,allow_network=a.allow_network,resume=a.resume)
    print(json.dumps(answer,ensure_ascii=False,indent=2))
    return 2 if 'technical_stop' in answer['status'] else 0


if __name__=='__main__':raise SystemExit(main())

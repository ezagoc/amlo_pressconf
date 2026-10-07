"""Kevin's explicit, bounded recovery capsule. Preparing/inspecting never fetches.

The donor is immutable historical evidence. Only its active native child is
copied; completed children keep their old runtime provenance. This is a bridge
to one original batch boundary, not promotion of the full campaign.
"""
from pathlib import Path
import argparse, json, shutil, sqlite3
from . import tiempo_continuous_v5 as w, tiempo_scheduler_v5 as s
from .tiempo_continuous_source import compact

SCHEMA = 'tiempo-bounded-recovery-capsule-v1'

def bindings(paths):
    return {str(Path(p).resolve()): w.sha_file(p) for p in paths}

def verify_bindings(items):
    for p, h in items.items():
        w.require(w.sha_file(p) == h, 'Protected evidence changed: ' + p)

def signed(path, key):
    data = w.load(path); unsigned = dict(data); expected = unsigned.pop(key, None)
    w.require(w.digest(unsigned) == expected, 'Signed document changed: ' + str(path))
    return data

def code_binding():
    return {**w.program_hashes(), 'recovery_adapter': w.sha_file(__file__),
            'recovery_cli': w.sha_file(Path(__file__).parents[1] / 'scripts/run_tiempo_recovery.py')}

def identity_from_saved(row):
    body=row.get('main_text')
    return w._identity_record(row,{'body_compact_sha256':w.hashlib.sha256(compact(body).encode()).hexdigest() if body else None})

def prepare(config_path):
    """Copy/rebind the active child offline. A failed check leaves evidence intact."""
    cfg = w.load(config_path); root = Path(cfg['capsule']).resolve()
    media = Path(cfg['isolated_media']).resolve(); child = Path(cfg['new_child']).resolve()
    donor = Path(cfg['source_campaign']).resolve(); oldchild = Path(cfg['source_child']).resolve()
    for destination in (root,media,child):
        for source in (donor,oldchild):
            w.require(destination!=source and source not in destination.parents and destination not in source.parents,
                      'Recovery destinations must be disjoint from donor trees')
    w.require(not root.exists() and not child.exists(), 'Independent empty destinations required')
    protected = w.load(cfg['protected_sources']); verify_bindings(protected)
    old = signed(donor / 'campaign.json', 'campaign_sha256')
    oldplan = signed(oldchild / 'continuous_plan.json', 'plan_sha256')
    prepared = s.validate_preparation(old['prepared_path'])
    progress = w.load(donor / 'progress.json'); state = w.load(oldchild / 'continuous_state.json')
    oldhalt=w.load(oldchild/'safety_halt.json')
    w.require(progress['campaign_sha256']==old['campaign_sha256'], 'Donor progress belongs to another campaign')
    w.require(state['plan_sha256']==oldplan['plan_sha256']==oldhalt['plan_sha256'], 'Donor halt or state belongs to another plan')
    w.require(oldhalt['reason'] in {'three_unexplained_rows_in_rolling80','two_consecutive_same_family_anomalies'},
              'Access, identity, transport or storage halts need a separate remediation')
    index = len(progress['completed']) + 1
    w.require(progress['initialized_children'] == list(range(1,index+1)), 'Donor progress is not an ordered active prefix')
    w.require([d['index'] for d in progress['completed']] == list(range(1,index)), 'Donor completed prefix changed')
    w.require(oldchild.name == old['child_names'][index-1], 'Wrong active donor child')
    w.require(oldplan['program_sha256'] == old['program_sha256'], 'Donor runtime differs')
    w.require(state['status'] == 'halted_no_automatic_resume' and
              state['halt_sha256'] == w.sha_file(oldchild/'safety_halt.json'), 'Original halt evidence missing')
    w.require(oldplan['continuation_policy'] == w.POLICY, 'Policy thresholds must not change')
    mandatory=[donor/'campaign.json',donor/'progress.json',oldchild/'continuous_plan.json',
        oldchild/'continuous_state.json',oldchild/'safety_halt.json',oldchild/'transport_calls.jsonl',oldchild/'transport_state.json']
    charged_completed=0; actual_completed=0; previous_context=None; previous_child=None; expected_history={}
    for done in progress['completed']:
        previous_child=oldchild.parent/old['child_names'][done['index']-1]
        prior=signed(previous_child/'continuous_plan.json','plan_sha256')
        receipt=w.load(previous_child/'completion_receipt.json')
        w.require(w.sha_file(previous_child/'completion_receipt.json')==done['receipt_sha256'], 'Completed receipt changed')
        w.require(receipt['campaign_sha256']==old['campaign_sha256'] and receipt['plan_sha256']==prior['plan_sha256'] and
            prior['program_sha256']==old['program_sha256'], 'Completed donor provenance differs')
        w.require(w.sha_file(previous_child/'continuation_context.json')==receipt['continuation_context_sha256'], 'Completed continuation context changed')
        previous_context=w.load(previous_child/'continuation_context.json')
        calls=sum(e['event']=='start' for e in w._ledger(previous_child,prior))
        w.require(calls==receipt['transport_reservations'], 'Completed transport accounting differs')
        charged_completed+=calls;count=0
        receipt_files={item['path']:item['sha256'] for item in receipt['evidence_files']}
        for b in prior['batches']:
            dbpath=previous_child/'batches'/b['batch_id']/'pilot.sqlite'
            w.require(protected.get(str(dbpath))==receipt_files.get(str(dbpath.relative_to(previous_child))) and str(dbpath) in protected,
                      'Completed database lacks matching protected receipt')
            with sqlite3.connect(dbpath.as_uri()+'?mode=ro&immutable=1',uri=True) as db:
                n=db.execute('SELECT count(*) FROM articles').fetchone()[0]
                for (payload,) in db.execute('SELECT payload_json FROM articles ORDER BY ordinal'):
                    row=json.loads(payload);record=identity_from_saved(row)
                    w.require(row['sample_id'] not in expected_history,'Repeated completed sample identity')
                    expected_history[row['sample_id']]=record
            w.require(n==b['row_count'], 'Completed donor batch row count differs');count+=n
        w.require(count==prior['row_count']==receipt['result_rows']==done['result_rows'], 'Completed donor total differs')
        actual_completed+=count
        mandatory.extend(previous_child/name for name in ('continuous_plan.json','completion_receipt.json','continuation_context.json','transport_calls.jsonl','transport_state.json'))
    w.require(charged_completed==progress['actual_transport_reservations'], 'Completed global charges differ')
    for p in oldchild.glob('batches/*/pilot.sqlite'):mandatory.append(p)
    w.require(all(str(p) in protected and protected[str(p)]==w.sha_file(p) for p in mandatory),
              'Mandatory donor evidence missing from protected sources')
    w.require(w.sha_file(Path(old['prepared_path'])/'preparation.json') == old['prepared_sha256'], 'Preparation changed')
    part = prepared['parts'][index-1]
    w.require(part['sha256'] == oldplan['original_input_sha256'], 'Active original input changed')
    rows_by_batch = [(b,w._rows(oldchild,b)) for b in oldplan['batches']]
    counts = [len(rows) for _,rows in rows_by_batch]
    saved = sum(counts); pending = next(i for i,(b,r) in enumerate(rows_by_batch) if len(r)<b['row_count'])
    w.require(all(len(r)==b['row_count'] for b,r in rows_by_batch[:pending]) and
              all(not r for _,r in rows_by_batch[pending+1:]), 'Saved data is not an exact native prefix')
    w.require(saved == cfg['expected_active_saved'], 'Active saved count changed')
    batch, existing = rows_by_batch[pending]
    trial_ids = batch['sample_ids'][len(existing):]
    w.require(trial_ids and len(trial_ids)<=80, 'Invalid original batch boundary')
    entries = w._ledger(oldchild,oldplan)
    w.require(len(entries)%2==0, 'Uncertain donor transport window requires investigation')
    starts = sum(e['event']=='start' for e in entries)
    for e in entries:
        if e['event']=='start':
            rec,_ = w._transport_receipt(oldchild,e)
            finish = entries[entries.index(e)+1]
            w.require(finish['response_sha256']==w.sha_file(oldchild/f'transport_snapshots/{e["sequence"]:08d}.json'), 'Donor transport finish changed')
    seed = w.load(cfg['seed_context'])
    w.require(len(seed['source_history'])<=79 and seed.get('history_index'), 'Explicit risk and identity context required')
    # Loading validates chained historical identities, including payload hashes.
    indexed={record['sample_id']:record for record in w.load_history_index(seed['history_index'])}
    w.require(seed['history_index']=={'path':str(Path(cfg['history_index']).resolve()),'sha256':w.sha_file(cfg['history_index'])}, 'Configured history index differs from seed')
    legacy_rows=0
    if cfg.get('legacy_data_path'):
        legacy=Path(cfg['legacy_data_path']).resolve()
        w.require(w.sha_file(legacy)==cfg['legacy_data_sha256'], 'Legacy saved-data binding changed')
        excluded={w.normalize_url(row['url']) for item in prepared['exclusions'] for row in w.readcsv(item['path'])}
        frame=w.pd.read_parquet(legacy)
        matched=[]
        for row in frame.to_dict('records'):
            if w.normalize_url(row['url']) not in excluded:continue
            row={k:w.pilot.clean(v) for k,v in row.items()};record=identity_from_saved(row)
            w.require(row['sample_id'] not in expected_history,'Legacy overlaps campaign history')
            expected_history[row['sample_id']]=record;matched.append(record['url'])
        w.require(len(matched)==len(set(matched)) and set(matched)==excluded, 'Legacy exclusions lack complete saved-data evidence')
        legacy_rows=len(matched);protected[str(legacy)]=cfg['legacy_data_sha256']
    w.require(indexed==expected_history,'Historical identity index differs from complete bound saved data')
    if previous_context is None:
        w.require(seed['source_history']==[] and seed.get('last_transport_finish') is None and seed.get('service_history')==[], 'First-child seed must be empty')
    else:
        w.require(oldplan['seed_context']==previous_context, 'Donor active context differs from completed prefix')
        w.require(seed.get('last_transport_finish')==previous_context['last_transport_finish'] and
                  seed.get('service_history')==previous_context.get('service_history') and seed.get('prior_plan_receipts')==previous_context.get('prior_plan_receipts'), 'Inherited transport/context state differs')
        wanted=[rec['sample_id'] for rec in previous_context['source_history']]
        w.require([rec['sample_id'] for rec in seed['source_history']]==wanted, 'Inherited risk window was reset or reordered')
        lookup={}
        prior=w.load(previous_child/'continuous_plan.json')
        for b in reversed(prior['batches']):
            for row in w._rows(previous_child,b):
                if row['sample_id'] in wanted:lookup[row['sample_id']]=(row,previous_child/'batches'/b['batch_id'])
            if len(lookup)==len(wanted):break
        registry=w.load_registry(cfg['registry'],w.sha_file(cfg['registry']))
        seen=w.seed_history_identities(seed['history_index']); refreshed=[]
        for sid in wanted:
            row,B=lookup[sid];rec,_=w._risk(row,B,registry,seen,prior);refreshed.append(rec);w._remember(row,rec,seen)
        w.require(refreshed==seed['source_history'], 'Inherited risk diagnostics do not match actual saved sources')
    root.mkdir(parents=True)
    plan = w.freeze(Path(old['prepared_path'])/part['path'],child,media,cfg['registry'],w.sha_file(cfg['registry']),
        prepared['exclusions'],start=prepared['date_start'],end=prepared['date_end_exclusive'],
        max_fetch_calls=min(oldplan['max_fetch_calls'],starts+len(trial_ids)*w.POLICY['attempts_per_url'],old['max_fetch_calls']-progress['actual_transport_reservations']),queue_db_path=prepared['queue_db'],queue_db_sha256=prepared['queue_sha256'],
        pause_seconds=oldplan['pause_seconds'],timeout=oldplan['timeout'],min_free_bytes=oldplan['min_free_bytes'],seed_context=seed)
    w.require(plan['batches']==oldplan['batches'] and (child/'queue.csv').read_bytes()==(oldchild/'queue.csv').read_bytes(), 'Native batch topology changed')
    copied = {}; inherited_samples = []
    for b, rows in rows_by_batch:
        if not rows: continue
        source = oldchild/'batches'/b['batch_id']; target = child/'batches'/b['batch_id']
        for p in sorted(source.rglob('*')):
            if not p.is_file() or p.name in {'.pilot.lock','Kevin_NOTE.md'} or 'inputs' in p.relative_to(source).parts: continue
            relative = p.relative_to(source); out = target/relative
            w.require(not out.exists(), 'Refuse overwrite: '+str(out))
            out.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(p,out)
            w.require(w.sha_file(out)==w.sha_file(p), 'Native copied bytes differ')
            copied[str(out.relative_to(child))] = w.sha_file(out)
    # All original chargeable calls/retries keep their identities and timestamps.
    for e in entries:
        replacement = {k:v for k,v in e.items() if k!='previous_event_sha256'}
        replacement['plan_sha256']=plan['plan_sha256']
        replacement['imported_from']={'plan_sha256':oldplan['plan_sha256'],'event_sha256':w.digest(e)}
        base=f'transport_snapshots/{e["sequence"]:08d}'
        if e['event']=='start':
            dst=child/(base+'.html'); dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(oldchild/(base+'.html'),dst)
            rec=w.load(oldchild/(base+'.json')); rec['plan_sha256']=plan['plan_sha256']
            rec['imported_from']={'path':str(oldchild/(base+'.json')),'sha256':w.sha_file(oldchild/(base+'.json'))}
            w.write(child,base+'.json',rec)
        else: replacement['response_sha256']=w.sha_file(child/(base+'.json'))
        w._append(child,plan,replacement)
    w._snapshot_reconciliation(child,plan,w._ledger(child,plan))
    _,registry=w.load_plan(child,media)
    seen=w.seed_history_identities(seed['history_index']); history=list(seed['source_history']); triggers=[]; check_differences=[]
    for b, oldrows in rows_by_batch:
        newrows=w._rows(child,b); w.require(oldrows==newrows,'Native payload changed')
        records=[]
        for row in newrows:
            rec,trigger=w._assess_row(child,plan,row,child/'batches'/b['batch_id'],registry,seen,history); records.append(rec)
            before=w.load(oldchild/'row_checks'/f'{row["sample_id"]}.json')['record']
            delta={key:{'old':before.get(key),'new':rec.get(key)} for key in sorted(set(before)|set(rec)) if before.get(key)!=rec.get(key)}
            if delta:check_differences.append({'sample_id':row['sample_id'],'automatic_check_only':True,'changes':delta})
            if trigger:triggers.append({'sample_id':row['sample_id'],'trigger':trigger,'flags':rec['automatic_flags']})
        if newrows:w._batch_check(child,b,newrows,records)
    # Preserve old selection obligations, independently of the new plan hash.
    for p in sorted(oldchild.glob('checkpoint_*/pending_source_review_samples.csv')):
        inherited_samples.extend(w.readcsv(p))
    import hashlib
    original_frozen_samples=[]
    for b in oldplan['batches']:
        rank=lambda sid:hashlib.sha256((oldplan['sampling_seed']+'\n'+oldplan['plan_sha256']+'\n'+sid).encode()).hexdigest()
        original_frozen_samples.extend({'batch_id':b['batch_id'],'sample_id':sid,'selection_sha256':rank(sid)}
            for sid in sorted(b['sample_ids'],key=rank)[:10 if b['batch_id']=='batch_000001' else 3])
    w.write(root,'Inherited_Review_Obligations.json',{'author':'Kevin','historic_pending_samples':inherited_samples,
        'original_frozen_batch_selections':original_frozen_samples,
        'original_plan_sha256':oldplan['plan_sha256'],'rule':'Preserve historical selections; new selections supplement them. No human approval is inferred.'})
    w.write(root,'Automatic_Check_Differences.json',check_differences)
    w.write(root,'Copied_Native_Files.json',copied)
    protected.update(bindings([config_path,cfg['protected_sources'],cfg['seed_context'],cfg['registry'],cfg['history_index']]))
    completed_rows=sum(d['result_rows'] for d in progress['completed'])
    prior_calls=progress['actual_transport_reservations']
    capsule={'schema':SCHEMA,'author':'Kevin','created_at':w.now(),'source_campaign':str(donor),'source_child':str(oldchild),
      'new_child':str(child),'isolated_media':str(media),'prepared_path':old['prepared_path'],'prepared_sha256':old['prepared_sha256'],
      'code':code_binding(),'protected_sources':protected,'plan_sha256':plan['plan_sha256'],'child_plan_index':index,
      'completed_original_children':index-1,'historical_completed_rows':completed_rows,'active_imported_rows':saved,
      'campaign_saved_rows':completed_rows+saved,'campaign_total_urls':prepared['row_count'],
      'campaign_pending_urls':prepared['row_count']-completed_rows-saved,'legacy_exclusion_urls':prepared['excluded_unique_urls'],
      'historical_identity_rows':len(indexed),'legacy_identity_rows':legacy_rows,
      'original_completed_transport_calls':prior_calls,'active_imported_transport_calls':starts,
      'master_max_fetch_calls':old['max_fetch_calls'],'trial_batch_id':batch['batch_id'],'trial_sample_ids':trial_ids,
      'trial_additional_transport_limit':len(trial_ids)*w.POLICY['attempts_per_url'],
      'native_copied_bytes_preserved':True,'source_risk_triggers':triggers,'ready_for_bounded_trial':not triggers,
      'imported_payloads_sha256':w.digest([row for _,rows in rows_by_batch for row in rows]),
      'recovery_evidence':bindings([root/'Inherited_Review_Obligations.json',root/'Automatic_Check_Differences.json',root/'Copied_Native_Files.json']),
      'manual_review_status':'not_reviewed','article_acceptance':False,'automatic_promotion':False}
    capsule['capsule_sha256']=w.digest(capsule);w.write(root,'capsule.json',capsule)
    if triggers:w._halt(child,plan,'offline_recovery_source_risk_unresolved',triggers=triggers)
    else:w._state(child,plan,w.PENDING,offline_recovery_prepared=True,imported_result_rows=saved,new_transport_calls=0)
    verify_bindings(protected)
    return capsule

def inspect(root):
    root=Path(root).resolve();c=signed(root/'capsule.json','capsule_sha256')
    w.require(c['schema']==SCHEMA and c['code']==code_binding(),'Recovery code/schema changed')
    verify_bindings(c['protected_sources'])
    verify_bindings(c['recovery_evidence'])
    w.require(w.sha_file(Path(c['prepared_path'])/'preparation.json')==c['prepared_sha256'],'Prepared scope changed')
    child=Path(c['new_child']);plan,_=w.load_plan(child,c['isolated_media'])
    w.require(plan['plan_sha256']==c['plan_sha256'],'Successor plan changed')
    entries=w._ledger(child,plan); active_calls=sum(e['event']=='start' for e in entries)
    w.require(active_calls>=c['active_imported_transport_calls'],'Imported charges lost')
    w.require(active_calls-c['active_imported_transport_calls']<=c['trial_additional_transport_limit'],'Trial request budget exceeded')
    w.require(c['original_completed_transport_calls']+active_calls<=c['master_max_fetch_calls'],'Global request budget exceeded')
    batches=[(b,w._rows(child,b)) for b in plan['batches']]
    saved=sum(len(rows) for _,rows in batches)
    w.require(w.digest([row for _,rows in batches for row in rows][:c['active_imported_rows']])==c['imported_payloads_sha256'], 'Imported native payload prefix changed')
    w.require(c['active_imported_rows']<=saved<=c['active_imported_rows']+len(c['trial_sample_ids']),'Outside bounded trial')
    target=next((b,rows) for b,rows in batches if b['batch_id']==c['trial_batch_id'])
    return c,plan,{'saved_active_rows':saved,'trial_remaining_urls':target[0]['row_count']-len(target[1]),
        'new_transport_reservations':active_calls-c['active_imported_transport_calls'],
        'total_charged_transport_reservations':c['original_completed_transport_calls']+active_calls,
        'old_halt_preserved':True,'article_acceptance':False}

def run_trial(root,*,allow_network=False,fetcher=None,clock=w.time.time,sleep=w.time.sleep,disk_free=None):
    """Only the original active partial batch; repeated completed calls fetch zero."""
    w.require(allow_network or fetcher is not None,'Explicit live authorization or injected offline fetcher required')
    root=Path(root).resolve()
    with w.pilot.exclusive_run(root):
        c,plan,status=inspect(root)
        w.require(c['ready_for_bounded_trial'],'Offline source risks remain unresolved')
        child=Path(c['new_child'])
        if (child/'safety_halt.json').exists():
            return {**status,'status':'halted_no_automatic_resume'}
        if status['trial_remaining_urls']==0:
            return {**status,'status':'bounded_trial_finished_pending_review','network_calls_this_invocation':0}
        allowed={r['url'] for r in w.readcsv(child/'queue.csv') if r['sample_id'] in c['trial_sample_ids']}
        calls=0
        def bounded_fetch(url,timeout,**kwargs):
            nonlocal calls
            w.require(url in allowed,'Request outside original bounded trial')
            count=sum(e['event']=='start' for e in w._ledger(child,plan))-c['active_imported_transport_calls']
            w.require(count<=c['trial_additional_transport_limit'],'Bounded trial transport limit reached')
            w.require(c['original_completed_transport_calls']+c['active_imported_transport_calls']+count<=c['master_max_fetch_calls'],'Global budget exhausted')
            calls+=1
            if fetcher is not None:return fetcher(url,timeout,**kwargs)
            from .capabilities import fetch
            return fetch(url,timeout,**kwargs)
        result=w.run(child,c['isolated_media'],max_batches=1,fetcher=bounded_fetch,clock=clock,sleep=sleep,disk_free=disk_free)
        _,_,after=inspect(root)
        answer={**after,'worker_result':result,'network_calls_this_invocation':calls,
          'status':('bounded_trial_finished_pending_review' if after['trial_remaining_urls']==0 and 'halt' not in result['status'] else result['status'])}
        w.write(root,'trial_last_receipt.json',answer);return answer

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('prepare');a.add_argument('--config',type=Path,required=True)
    a=sub.add_parser('inspect');a.add_argument('--capsule',type=Path,required=True)
    a=sub.add_parser('trial');a.add_argument('--capsule',type=Path,required=True);a.add_argument('--allow-network',action='store_true')
    a=p.parse_args(argv)
    if a.command=='prepare':result=prepare(a.config)
    elif a.command=='inspect':c,_,result=inspect(a.capsule);result.update(ready_for_bounded_trial=c['ready_for_bounded_trial'],trial_url_limit=len(c['trial_sample_ids']))
    else:result=run_trial(a.capsule,allow_network=a.allow_network)
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0

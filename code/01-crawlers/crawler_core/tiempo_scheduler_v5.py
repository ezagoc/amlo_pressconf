"""Portable sequential scheduler. Preparation is offline, never a launch/approval.

Kevin: original queue, old sources, old plans are read-only. New collection is
pending Joaquin review. This module never creates an operator approval.
"""
from __future__ import annotations
from pathlib import Path
from collections import Counter
import argparse,csv,hashlib,json,math,sqlite3,sys
try:
    from . import tiempo_continuous_v5 as worker
except ImportError:
    import tiempo_continuous_v5 as worker

SCHEMA='tiempo-total-queue-scheduler-v5'
ORDER=['new_urls','old_error_review','old_short_review','old_missing_fields_review']
load=worker.load;write=worker.write;sha=worker.sha_file;require=worker.require

def original_rows(path):
    with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as db:
        db.row_factory=sqlite3.Row
        for row in db.execute('SELECT * FROM candidates ORDER BY queue_class,discovery_day,url_key'):
            yield {k:'' if v is None else str(v) for k,v in dict(row).items()}

def exclusion_evidence(items):
    roles={};keys=set();bindings=[]
    for item in items:
        p=Path(item['path']).resolve();require(sha(p)==item['sha256'],'Exclusion hash changed')
        rows=worker.readcsv(p);ids=[worker.normalize_url(r['url']) for r in rows]
        require(item['role'] not in roles and len(ids)==len(set(ids)),'Duplicate exclusion role or identity')
        roles[item['role']]=len(rows);keys.update(ids)
        bindings.append({**item,'path':str(p),'rows':len(rows)})
    require(all(roles.get(k)==n for k,n in worker.REQUIRED_EXCLUSIONS.items()),'Full four original protocols required')
    require(len(keys)>=2270,'Original protocol exclusions overlap unexpectedly')
    return keys,bindings

def prepare(queue_db,queue_sha,exclusions,out,*,start,end,chunk_size=2000):
    """Write a draft partition of all four classes; no registry or run is frozen."""
    queue_db=Path(queue_db).resolve();out=Path(out).resolve()
    require(not out.exists(),'Never overwrite an existing preparation')
    require(type(chunk_size) is int and 1<=chunk_size<=2000,'Chunk size 1..2000 required')
    require(sha(queue_db)==queue_sha,'Original queue hash changed')
    excluded,bindings=exclusion_evidence(exclusions)
    candidates=[];counts=Counter();skipped=Counter();protected=Counter();matched=set()
    for row in original_rows(queue_db):
        q=row['queue_class'];counts[q]+=1
        if q not in ORDER:continue
        if not start<=row['discovery_day']<end:skipped['outside_selected_window']+=1;continue
        if row['url_key'] in excluded:skipped[q]+=1;matched.add(row['url_key']);continue
        row.update(sample_id='TC5_'+str(row['candidate_id']),selection_reason='Kevin v5 original '+q+'; independent new output; no overwrite',expected_kind='article_candidate',expected_year=row['discovery_day'][:4])
        worker._validate_rows([row],start,end)
        candidates.append(row);protected[q]+=int(row['baseline_protected'])
    require(sha(queue_db)==queue_sha,'Queue changed during partition')
    candidates.sort(key=lambda r:(ORDER.index(r['queue_class']),r['discovery_day'],r['url_key']))
    require(candidates and len({r['url_key'] for r in candidates})==len(candidates),'Empty/duplicate selected queue')
    out.mkdir(parents=True);parts=[];header=list(candidates[0])
    for i,offset in enumerate(range(0,len(candidates),chunk_size),1):
        part=candidates[offset:offset+chunk_size];name=f'plan_{i:06d}.csv';raw=worker.csvbytes(header,part)
        worker.pilot.atomic_bytes(out/name,raw)
        parts.append({'plan_index':i,'path':name,'sha256':hashlib.sha256(raw).hexdigest(),'rows':len(part),'classes':dict(Counter(r['queue_class'] for r in part))})
    document={'schema':SCHEMA,'author':'Kevin','status':'prepared_only_not_frozen_not_executed','article_acceptance':False,
              'queue_db':str(queue_db),'queue_sha256':queue_sha,'date_start':start,'date_end_exclusive':end,
              'exclusions':bindings,'excluded_unique_urls':len(excluded),'excluded_selected_urls':len(matched),
              'original_class_counts':dict(counts),'selected_class_counts':dict(Counter(r['queue_class'] for r in candidates)),
              'excluded_class_counts':dict(skipped),'preserved_baseline_protection_flags':dict(protected),
              'row_count':len(candidates),'chunk_size':chunk_size,'parts':parts,
              'selection_sha256':worker.digest([r['url_key'] for r in candidates]),
              'old_structural_pass':'Retained without re-fetch; structural checks are not individual human certification.',
              'missing_fields':'Explicit old_missing_fields_review may retain protected=1; old records are never changed.'}
    document['manifest_sha256']=worker.digest(document);write(out,'preparation.json',document)
    (out/'Kevin_NOTE.md').write_text('# Kevin\nOffline queue preparation only. No HTTP, no formal run freeze, no approval.\n')
    return document

def validate_preparation(folder):
    folder=Path(folder).resolve();m=load(folder/'preparation.json');unsigned=dict(m);h=unsigned.pop('manifest_sha256',None)
    require(m['schema']==SCHEMA and worker.digest(unsigned)==h,'Prepared manifest changed')
    require(sha(m['queue_db'])==m['queue_sha256'],'Original frozen queue changed')
    excluded,bindings=exclusion_evidence(m['exclusions']);require(bindings==m['exclusions'],'Exclusion binding changed')
    rows=[];parts=m['parts'];require(len(parts)>0,'Empty plan partition')
    for i,part in enumerate(parts,1):
        require(part['plan_index']==i and part['path']==f'plan_{i:06d}.csv','Part identity changed')
        p=worker.pilot.safe_path(folder,part['path']);require(sha(p)==part['sha256'],'Part CSV changed')
        current=worker.readcsv(p);worker._validate_rows(current,m['date_start'],m['date_end_exclusive'])
        require(len(current)==part['rows'] and len(current)<=m['chunk_size'] and dict(Counter(r['queue_class'] for r in current))==part['classes'],'Part count/classes changed')
        rows.extend(current)
    keys=[r['url_key'] for r in rows]
    require(len(keys)==m['row_count'] and len(keys)==len(set(keys)) and not set(keys)&excluded and worker.digest(keys)==m['selection_sha256'],'Partition union missing/duplicate/overlap')
    # One streaming pass instead of hashing the multi-GB source per 2000-row part.
    actual={r['url_key']:r for r in original_rows(m['queue_db']) if r['queue_class'] in ORDER and m['date_start']<=r['discovery_day']<m['date_end_exclusive'] and r['url_key'] not in excluded}
    require(set(actual)==set(keys),'Prepared union differs from complete original eligible queue')
    for row in rows:require(all(row.get(k)==v for k,v in actual[row['url_key']].items()),'Original candidate metadata changed')
    require(sha(m['queue_db'])==m['queue_sha256'],'Queue changed during validation')
    return m

def campaign_namespace(root,media):
    root=Path(root).resolve();base=(Path(media)/'data/00-newspaper_data/crawler/pilots/Kevin/tiempo_continuous_v5_campaigns').resolve()
    require(root.parent==base and worker.re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{1,60}',root.name),'Dedicated new v5 campaign namespace required')
    return root

def bind(prepared,root,media,registry,registry_sha,*,max_fetch_calls,pause_seconds=1.,timeout=45.,min_free_bytes=10*1024**3):
    """Offline explicit master binding; root must separately authorize live run."""
    root=campaign_namespace(root,media);require(not root.exists(),'Cannot adopt an existing campaign')
    m=validate_preparation(prepared);worker.load_registry(registry,registry_sha)
    require(type(max_fetch_calls) is int and 1<=max_fetch_calls<=3*m['row_count'],'Explicit total transport budget required')
    require(math.isfinite(pause_seconds) and pause_seconds>=1 and math.isfinite(timeout) and timeout>0 and type(min_free_bytes) is int and min_free_bytes>0,'Unsafe transport settings')
    bound={'schema':SCHEMA,'author':'Kevin','created_at':worker.now(),'prepared_path':str(Path(prepared).resolve()),'prepared_sha256':sha(Path(prepared)/'preparation.json'),
           'registry_path':str(Path(registry).resolve()),'registry_sha256':registry_sha,'program_sha256':worker.program_hashes(),
           'max_fetch_calls':max_fetch_calls,'pause_seconds':pause_seconds,'timeout':timeout,'min_free_bytes':min_free_bytes,
           'row_count':m['row_count'],'plan_count':len(m['parts']),'article_acceptance':False,'manual_review_status':'not_reviewed',
           'child_names':[root.name+'__'+f'plan_{i:06d}' for i in range(1,len(m['parts'])+1)]}
    bound['campaign_sha256']=worker.digest(bound);root.mkdir(parents=True)
    write(root,'campaign.json',bound);write(root,'progress.json',{'campaign_sha256':bound['campaign_sha256'],'initialized_children':[],'completed':[],'actual_transport_reservations':0,'transport_count_definition':'Completed child plans only; active totals are returned separately and remain bound in the active child ledger.'})
    (root/'Kevin_NOTE.md').write_text('# Kevin\nV5 collection. No operator approvals or article acceptance. Joaquín review remains pending.\n')
    return bound

def read_campaign(root,media):
    root=campaign_namespace(root,media);m=load(root/'campaign.json');u=dict(m);h=u.pop('campaign_sha256',None)
    require(m['schema']==SCHEMA and worker.digest(u)==h and m['program_sha256']==worker.program_hashes(),'Campaign or frozen program changed')
    require(sha(Path(m['prepared_path'])/'preparation.json')==m['prepared_sha256'],'Prepared input changed')
    preparation=validate_preparation(m['prepared_path']);worker.load_registry(m['registry_path'],m['registry_sha256'])
    p=load(root/'progress.json');require(p['campaign_sha256']==h,'Progress belongs to another campaign')
    require(p['initialized_children']==list(range(1,len(p['initialized_children'])+1)) and [x['index'] for x in p['completed']]==list(range(1,len(p['completed'])+1)),'Progress is not an ordered prefix')
    require(len(p['completed'])<=len(p['initialized_children'])<=len(p['completed'])+1,'Invalid active child accounting')
    parent=Path(media)/'data/00-newspaper_data/crawler/pilots/Kevin/tiempo_continuous_v5'
    for i,name in enumerate(m['child_names'],1):
        exists=(parent/name).exists()
        require(exists==(i in p['initialized_children']),'Child directory/progress mismatch: never silently adopt/delete a plan')
    return m,preparation,p

def run(root,media,*,max_plans,max_batches_per_plan,allow_network=False,fetcher=None,clock=worker.time.time,sleep=worker.time.sleep,disk_free=None):
    """One sequential worker. A safety halt is never skipped for the next plan."""
    require(allow_network or fetcher is not None,'Explicit network execution authorization required')
    require(type(max_plans) is int and max_plans>0 and type(max_batches_per_plan) is int and 1<=max_batches_per_plan<=25,'Explicit bounded invocation required')
    root=campaign_namespace(root,media)
    with worker.pilot.exclusive_run(root.parent),worker.pilot.exclusive_run(root):
        m,prepared,progress=read_campaign(root,media);parent=Path(media)/'data/00-newspaper_data/crawler/pilots/Kevin/tiempo_continuous_v5'
        context=None;used=0
        # Bind completed subplans/current native results via immutable receipts.
        for done in progress['completed']:
            child=parent/m['child_names'][done['index']-1]
            require(sha(child/'completion_receipt.json')==done['receipt_sha256'],'Completed child receipt changed')
            receipt=load(child/'completion_receipt.json')
            require(receipt['plan_sha256']==load(child/'continuous_plan.json')['plan_sha256'] and sha(child/'continuation_context.json')==receipt['continuation_context_sha256'],'Completed child binding changed')
            for item in receipt['evidence_files']:require(sha(child/item['path'])==item['sha256'],'Previously completed child evidence changed')
            entries=worker._ledger(child,load(child/'continuous_plan.json'));used+=sum(e['event']=='start' for e in entries)
            context=load(child/'continuation_context.json')
        require(used==progress['actual_transport_reservations'],'Global budget progress differs from durable completed ledgers')
        executed=0
        for index in range(len(progress['completed'])+1,len(prepared['parts'])+1):
            if executed>=max_plans:break
            part=prepared['parts'][index-1];child=parent/m['child_names'][index-1]
            if index not in progress['initialized_children']:
                remaining=m['max_fetch_calls']-used
                if remaining<=0:return {'status':'stopped_global_request_budget_exhausted','article_acceptance':False,'completed_plans':len(progress['completed'])}
                # Reserving child slot first makes interrupted initialization fail
                # closed rather than generating a different hidden plan.
                progress['initialized_children'].append(index);write(root,'progress.json',progress)
                worker.freeze(Path(m['prepared_path'])/part['path'],child,media,m['registry_path'],m['registry_sha256'],prepared['exclusions'],start=prepared['date_start'],end=prepared['date_end_exclusive'],max_fetch_calls=min(3*part['rows'],remaining),queue_db_path=prepared['queue_db'],queue_db_sha256=prepared['queue_sha256'],pause_seconds=m['pause_seconds'],timeout=m['timeout'],min_free_bytes=m['min_free_bytes'],seed_context=context)
            plan,_=worker.load_plan(child,media)
            require(plan['original_input_sha256']==part['sha256'] and plan['max_fetch_calls']<=m['max_fetch_calls']-used and plan['seed_context']==(context or {'source_history':[],'service_history':[],'last_transport_finish':None,'prior_plan_receipts':[]}),'Child input/context/global budget binding changed')
            result=worker.run(child,media,max_batches=max_batches_per_plan,fetcher=fetcher,allow_network=allow_network,clock=clock,sleep=sleep,disk_free=disk_free);executed+=1
            if not result.get('collection_inputs_finished'):
                active_calls=sum(e['event']=='start' for e in worker._ledger(child,plan))
                return {'status':result['status'],'child_plan_index':index,'child_state':result,'completed_plans':len(progress['completed']),'completed_plan_transport_reservations':used,'active_plan_transport_reservations':active_calls,'total_transport_reservations':used+active_calls,'article_acceptance':False,'manual_review_status':'not_reviewed'}
            entries=worker._ledger(child,plan);calls=sum(e['event']=='start' for e in entries);used+=calls
            require(used<=m['max_fetch_calls'],'Global request budget exceeded')
            context=load(child/'continuation_context.json')
            # Hash small immutable checks/native exports/raw snapshot evidence.
            files=[]
            for path in sorted(child.rglob('*')):
                if path.is_file() and path.name not in {'.pilot.lock','completion_receipt.json','continuous_state.json','Kevin_NOTE.md'} and 'backups' not in path.parts:
                    files.append({'path':str(path.relative_to(child)),'sha256':sha(path)})
            receipt={'schema':SCHEMA,'campaign_sha256':m['campaign_sha256'],'plan_sha256':plan['plan_sha256'],'result_rows':result['result_rows'],'transport_reservations':calls,'continuation_context_sha256':sha(child/'continuation_context.json'),'evidence_files':files,'article_acceptance':False,'manual_review_status':'not_reviewed'}
            if (child/'completion_receipt.json').exists():require(load(child/'completion_receipt.json')==receipt,'Existing completion receipt changed')
            else:write(child,'completion_receipt.json',receipt)
            progress['completed'].append({'index':index,'receipt_sha256':sha(child/'completion_receipt.json'),'result_rows':result['result_rows']});progress['actual_transport_reservations']=used;write(root,'progress.json',progress)
        return {'status':'collection_inputs_finished_pending_Joaquin_review' if len(progress['completed'])==len(prepared['parts']) else 'bounded_invocation_finished_pending_stage_review','completed_plans':len(progress['completed']),'result_rows':sum(x['result_rows'] for x in progress['completed']),'transport_reservations':used,'completed_plan_transport_reservations':used,'active_plan_transport_reservations':0,'total_transport_reservations':used,'article_acceptance':False,'manual_review_status':'not_reviewed'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('prepare');a.add_argument('--queue-db',type=Path,required=True);a.add_argument('--queue-sha256',required=True);a.add_argument('--exclusions',type=Path,required=True);a.add_argument('--out',type=Path,required=True);a.add_argument('--start',required=True);a.add_argument('--end-exclusive',required=True);a.add_argument('--chunk-size',type=int,default=2000)
    a=sub.add_parser('bind');a.add_argument('--prepared',type=Path,required=True);a.add_argument('--run-dir',type=Path,required=True);a.add_argument('--media-root',type=Path,required=True);a.add_argument('--registry',type=Path,required=True);a.add_argument('--registry-sha256',required=True);a.add_argument('--max-fetch-calls',type=int,required=True)
    a=sub.add_parser('run');a.add_argument('--run-dir',type=Path,required=True);a.add_argument('--media-root',type=Path,required=True);a.add_argument('--max-plans',type=int,required=True);a.add_argument('--max-batches-per-plan',type=int,required=True);a.add_argument('--allow-network',action='store_true')
    a=p.parse_args(argv)
    if a.command=='prepare':r=prepare(a.queue_db,a.queue_sha256,load(a.exclusions),a.out,start=a.start,end=a.end_exclusive,chunk_size=a.chunk_size)
    elif a.command=='bind':r=bind(a.prepared,a.run_dir,a.media_root,a.registry,a.registry_sha256,max_fetch_calls=a.max_fetch_calls)
    else:r=run(a.run_dir,a.media_root,max_plans=a.max_plans,max_batches_per_plan=a.max_batches_per_plan,allow_network=a.allow_network)
    print(json.dumps(r,ensure_ascii=False,indent=2));return 2 if 'halt' in r.get('status','') or r.get('status','').startswith('stopped') else 0

if __name__=='__main__':raise SystemExit(main())

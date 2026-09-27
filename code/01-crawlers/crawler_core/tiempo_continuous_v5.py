"""V5 isolated collection of original new/error/short/missing candidates.

Existing operator-approved batch plans are intentionally unsupported. Safety
halts are terminal for this plan: operator investigation may create a new plan.
"""
from __future__ import annotations
from collections import Counter
from datetime import date,datetime,timezone
from pathlib import Path
import csv,hashlib,io,json,math,os,re,shutil,sqlite3,time
import pandas as pd
from crawler_core import tiempo_pilot as pilot
from crawler_core.tiempo_queue import normalize_url
from crawler_core.tiempo_continuous_source import diagnose,load_registry,sha_file,encoded,require,fields_digest

MODE='tiempo-continuous-recoverable-collection-v5'
POLICY={'version':'v5','consecutive_same_family':2,'rolling_window':80,'unexplained_rows_limit':3,'unknown_joint_type':'novelty_sampling_only','attempts_per_url':3,'retry_backoff_seconds':[5,15],'service_failure_consecutive':3,'service_failure_rolling80':8,'unavailable_404_410_soft404':'preserve_and_continue_not_service_failure'}
ALLOWED_CLASSES={'new_urls','old_error_review','old_short_review','old_missing_fields_review'}
QUARANTINE='quarantined_pending_source_review'
PENDING='automatic_checked_pending_stage_review'
MAX_PLAN_ROWS=2000
REQUIRED_EXCLUSIONS={'validation400':400,'production808':808,'may27':62,'historical20190304':1000}
FROZEN_MODULES=('capabilities.py','sitemap_articles.py','tiempo_html.py','tiempo_pilot.py','tiempo_review.py','tiempo_batches.py','tiempo_queue.py','tiempo_continuous_source.py','tiempo_continuous.py')

def now():return datetime.now(timezone.utc).isoformat()
def load(path):return json.loads(Path(path).read_text())
def digest(obj):return hashlib.sha256(encoded(obj)).hexdigest()
def write(root,name,obj):pilot.atomic_bytes(pilot.safe_path(root,name),encoded(obj))
def csvbytes(headers,rows):
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=headers,lineterminator='\n');writer.writeheader();writer.writerows(rows);return stream.getvalue().encode('utf-8-sig')
def readcsv(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))
def program_hashes():
    base=Path(pilot.__file__).parent
    result={n:sha_file(base/n) for n in FROZEN_MODULES}
    result['v5_worker']=sha_file(__file__)
    result['v5_scheduler']=sha_file(Path(__file__).with_name('tiempo_scheduler_v5.py'))
    cli=Path(__file__).with_name('run_tiempo_scheduler_v5.py')
    if not cli.exists():cli=base.parent/'scripts/run_tiempo_scheduler_v5.py'
    result['v5_cli']=sha_file(cli)
    return result

def namespace(root,media):
    root,base=Path(root).resolve(),(Path(media)/'data/00-newspaper_data/crawler/pilots/Kevin/tiempo_continuous_v5').resolve()
    require(root.parent==base and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{1,100}',root.name),'New dedicated tiempo_continuous_v5/<name> namespace required')
    return root

def _validate_rows(rows,start,end):
    require(date.fromisoformat(start).isoformat()==start and date.fromisoformat(end).isoformat()==end and '2018-01-01'<=start<end<='2026-01-01','Explicit target date range required')
    require(0<len(rows)<=MAX_PLAN_ROWS,'Explicit plan must contain 1..2000 URLs')
    ids=set();keys=set()
    for row in rows:
        require(re.fullmatch(r'TC5_[A-Za-z0-9_]+',row.get('sample_id','')) is not None,'New TC_ sample namespace required')
        key=normalize_url(row['url']);day=row.get('discovery_day','')
        require(key==row.get('url_key') and row['sample_id'] not in ids and key not in keys,'Duplicate or inconsistent input identity')
        ids.add(row['sample_id']);keys.add(key)
        require(row.get('identity_class') in ALLOWED_CLASSES and row.get('discovery_scope')=='target_2018_2025' and row.get('queue_class')==row.get('identity_class') and row.get('discovery_date_status')=='consistent' and (row.get('baseline_protected') in {'0',0} or (row.get('queue_class')=='old_missing_fields_review' and json.loads(row.get('baseline_classes_json','[]'))==['old_missing_required_field'])) and start<=day<end,'Only explicit unprotected new/error/short/missing candidates inside the date window')
        dates=json.loads(row['discovery_dates_json'])
        require(isinstance(dates,list) and bool(dates) and all(isinstance(d,str) and bool(d.strip()) for d in dates),'Nonempty discovery date evidence required')
        require(json.loads(row['discovery_days_json'])==[day] and all(datetime.fromisoformat(d).date().isoformat()==day for d in dates),'Discovery evidence mismatch')
        require(bool(row.get('selection_reason')) and row.get('expected_kind')=='article_candidate' and str(row.get('expected_year'))==day[:4],'Explicit pilot metadata required')
    return keys

def _queue_binding(rows,path,expected_sha256):
    """Every original candidate column is independently read from the frozen queue."""
    path=Path(path).resolve();require(sha_file(path)==expected_sha256,'Original queue database hash changed')
    with sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True) as db:
        db.row_factory=sqlite3.Row
        columns=[r[1] for r in db.execute('PRAGMA table_info(candidates)')]
        require({'url_key','url','queue_class','baseline_protected','discovery_scope','identity_class'}.issubset(columns),'Invalid original candidates schema')
        for row in rows:
            found=db.execute('SELECT * FROM candidates WHERE url_key=?',(row['url_key'],)).fetchall()
            require(len(found)==1,'Input URL absent or duplicated in original queue')
            require(all(k in row and ('' if found[0][k] is None else str(found[0][k]))==str(row[k]) for k in columns),'Input candidate differs from original queue')
    require(sha_file(path)==expected_sha256,'Original queue changed during selection validation')
    return {'path':str(path),'sha256':expected_sha256,'columns':columns,'rows_verified':len(rows)}

def freeze(input_path,root,media_root,registry_path,registry_sha256,exclusions,*,start,end,max_fetch_calls,queue_db_path,queue_db_sha256,pause_seconds=1.0,timeout=45.0,min_free_bytes=10*1024**3,seed_context=None):
    """Offline new plan only. exclusions are caller-bound {role,path,sha256} entries."""
    root=namespace(root,media_root);require(not root.exists(),'Never adopt or overwrite an existing plan')
    rows=readcsv(input_path);keys=_validate_rows(rows,start,end)
    queue_binding=_queue_binding(rows,queue_db_path,queue_db_sha256)
    require(type(max_fetch_calls) is int and 1<=max_fetch_calls<=len(rows)*POLICY['attempts_per_url'],'Explicit fetch budget must be 1..3 times input count')
    require(math.isfinite(pause_seconds) and pause_seconds>=1 and math.isfinite(timeout) and timeout>0 and type(min_free_bytes) is int and min_free_bytes>0,'Unsafe timing/disk settings')
    registry=load_registry(registry_path,registry_sha256)
    roles={};excluded=set();bindings=[]
    for item in exclusions:
        role,path,h=item['role'],Path(item['path']).resolve(),item['sha256']
        require(role not in roles and sha_file(path)==h,'Duplicate or changed exclusion input')
        prior=readcsv(path);prior_keys={normalize_url(r['url']) for r in prior}
        require(len(prior)==len(prior_keys),'Exclusion list has duplicate requested identities')
        roles[role]=len(prior);excluded.update(prior_keys);bindings.append({'role':role,'path':str(path),'sha256':h,'rows':len(prior)})
    require(all(roles.get(k)==n for k,n in REQUIRED_EXCLUSIONS.items()),'All four original protocols must be excluded in full')
    require(not keys&excluded,'Input overlaps an existing planned protocol')
    header=list(rows[0]);queue=csvbytes(header,rows);batches=[]
    for offset in range(0,len(rows),80):
        part=rows[offset:offset+80];bid=f'batch_{offset//80+1:06d}';raw=csvbytes(header,part)
        batches.append({'batch_id':bid,'input_path':f'batches/{bid}/inputs/sample_manifest.csv','input_sha256':hashlib.sha256(raw).hexdigest(),'row_count':len(part),'sample_ids':[r['sample_id'] for r in part]})
    plan={'schema':MODE,'author':'Kevin','created_at':now(),'state':'frozen_for_explicit_collection_not_article_acceptance','date_start':start,'date_end_exclusive':end,'row_count':len(rows),'max_fetch_calls':max_fetch_calls,'pause_seconds':pause_seconds,'timeout':timeout,'min_free_bytes':min_free_bytes,'queue_sha256':hashlib.sha256(queue).hexdigest(),'original_input_sha256':sha_file(input_path),'registry_sha256':registry_sha256,'program_sha256':program_hashes(),'continuation_policy':POLICY,'exclusions':bindings,'original_queue':queue_binding,'batches':batches,'sampling_seed':'Kevin-Tiempo-Continuous-Pending-Review-v1','seed_context':seed_context or {'source_history':[],'service_history':[],'last_transport_finish':None,'prior_plan_receipts':[]},'request_count_definition':'Each transport call including bounded retries and uncertain reservations; redirects may add HTTP exchanges.'}
    plan['plan_sha256']=digest(plan)
    root.mkdir(parents=True,exist_ok=False)
    pilot.atomic_bytes(root/'Kevin_NOTE.md',b'# Kevin\nNew v5 collection only; automatic checks are not manual review. Originals and existing approved protocols untouched.\n')
    pilot.atomic_bytes(root/'queue.csv',queue);pilot.atomic_bytes(root/'known_registry.json',Path(registry_path).read_bytes())
    for i,batch in enumerate(batches):
        B=root/'batches'/batch['batch_id'];pilot.atomic_bytes(B/'Kevin_NOTE.md',b'# Kevin\nContinuous pending-review batch. No automatic manual approval.\n')
        pilot.atomic_bytes(root/batch['input_path'],csvbytes(header,rows[i*80:(i+1)*80]))
    write(root,'continuous_plan.json',plan)
    pilot.atomic_bytes(root/'transport_calls.jsonl',b'')
    write(root,'transport_state.json',{'plan_sha256':plan['plan_sha256'],'reserved_calls':0,'event_count':0,'ledger_sha256':hashlib.sha256(b'').hexdigest()})
    return plan

def load_plan(root,media_root):
    root=namespace(root,media_root);plan=load(root/'continuous_plan.json');unsigned=dict(plan);signature=unsigned.pop('plan_sha256',None)
    require(plan.get('schema')==MODE and signature==digest(unsigned),'Continuous plan hash/schema mismatch')
    require(plan.get('continuation_policy')==POLICY,'Unsupported frozen continuation policy')
    require(plan['program_sha256']==program_hashes(),'Frozen code changed; use a new plan after review')
    require(sha_file(root/'queue.csv')==plan['queue_sha256'],'Queue changed')
    rows=readcsv(root/'queue.csv');keys=_validate_rows(rows,plan['date_start'],plan['date_end_exclusive'])
    require(len(rows)==plan['row_count'],'Queue count changed')
    require(_queue_binding(rows,plan['original_queue']['path'],plan['original_queue']['sha256'])==plan['original_queue'],'Original queue binding changed')
    registry=load_registry(root/'known_registry.json',plan['registry_sha256'])
    excluded=set()
    for item in plan['exclusions']:
        require(sha_file(item['path'])==item['sha256'],'Original exclusion list changed')
        excluded.update(normalize_url(r['url']) for r in readcsv(item['path']))
    require(not keys&excluded,'Planned protocol overlap')
    seen=[]
    for i,batch in enumerate(plan['batches']):
        bid=f'batch_{i+1:06d}';path=pilot.safe_path(root,batch['input_path']);items,h=pilot.load_input(path)
        require(batch['batch_id']==bid and batch['input_path']==f'batches/{bid}/inputs/sample_manifest.csv' and h==batch['input_sha256'] and path.read_bytes()==csvbytes(list(rows[0]),rows[i*80:(i+1)*80]),'Bound batch input changed')
        require([r['sample_id'] for r in items]==batch['sample_ids'] and len(items)==batch['row_count'],'Batch accounting changed')
        seen.extend(batch['sample_ids'])
    require(seen==[r['sample_id'] for r in rows],'Missing/extra batch')
    return plan,registry

def _state(root,plan,status,**extra):
    data={'schema':MODE,'plan_sha256':plan['plan_sha256'],'updated_at':now(),'status':status,'manual_review_status':'not_reviewed','article_acceptance':False,**extra};write(root,'continuous_state.json',data);return data

def _halt(root,plan,reason,**evidence):
    path=root/'safety_halt.json'
    if not path.exists():write(root,'safety_halt.json',{'schema':MODE,'plan_sha256':plan['plan_sha256'],'created_at':now(),'reason':reason,**evidence})
    receipt=pilot.safe_path(root,'halt_receipts/'+sha_file(path)+'.json')
    if not receipt.exists():pilot.atomic_bytes(receipt,path.read_bytes())
    return _state(root,plan,'halted_no_automatic_resume',halt_sha256=sha_file(path),reason=load(path)['reason'])

def _ledger(root,plan):
    path=pilot.safe_path(root,'transport_calls.jsonl');statepath=pilot.safe_path(root,'transport_state.json')
    require(path.is_file() and statepath.is_file(),'Durable transport ledger or high-watermark missing')
    raw=path.read_bytes();state=load(statepath)
    require(state.get('plan_sha256')==plan['plan_sha256'] and state.get('ledger_sha256')==hashlib.sha256(raw).hexdigest(),'Transport ledger truncated, replaced or not durably checkpointed')
    require(not raw or raw.endswith(b'\n'),'Partial transport ledger line')
    entries=[json.loads(line) for line in raw.decode().split('\n') if line]
    starts=[];open_call=None;previous_hash=None
    for e in entries:
        require(e.get('plan_sha256')==plan['plan_sha256'] and e.get('previous_event_sha256')==previous_hash,'Transport ledger chain or plan mismatch')
        require(isinstance(e.get('epoch'),(float,int)) and math.isfinite(e['epoch']),'Nonfinite transport ledger clock')
        require(bool(e.get('attempt_id')),'Transport event lacks pilot attempt binding')
        if e['event']=='start':
            require(open_call is None and e['sequence']==len(starts)+1,'Transport ledger order/overlap invalid');starts.append(e);open_call=e
        elif e['event']=='finish':
            require(open_call is not None and all(e[k]==open_call[k] for k in ['sequence','url','batch_id','attempt_id']),'Transport finish mismatch');open_call=None
        else:raise ValueError('Unknown transport event')
        previous_hash=digest(e)
    require(state.get('event_count')==len(entries) and state.get('reserved_calls')==len(starts),'Transport reservation high-watermark mismatch')
    require(len(starts)<=plan['max_fetch_calls'],'Transport budget already exceeded')
    return entries

def _append(root,plan,event):
    entries=_ledger(root,plan)
    event={**event,'previous_event_sha256':digest(entries[-1]) if entries else None}
    with pilot.safe_path(root,'transport_calls.jsonl').open('a',encoding='utf-8') as stream:
        stream.write(json.dumps(event,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n');stream.flush();os.fsync(stream.fileno())
    # A crash between these two durable writes intentionally fails closed. A
    # reservation is fully checkpointed BEFORE calling the transport.
    write(root,'transport_state.json',{'plan_sha256':plan['plan_sha256'],'reserved_calls':sum(e['event']=='start' for e in entries)+(event['event']=='start'),'event_count':len(entries)+1,'ledger_sha256':sha_file(root/'transport_calls.jsonl')})


def _rows(root,batch):
    B=root/'batches'/batch['batch_id'];manifest_path=B/'manifest.json'
    require(not (B/'review_annotations.json').exists() and not (B/'review_history').exists(),'Continuous collection never adopts manual annotation mutations; export review in a separate stage')
    if not manifest_path.exists():
        require(not (B/'pilot.sqlite').exists(),'Unbound database');return []
    manifest=load(manifest_path);items,h=pilot.load_input(root/batch['input_path'])
    require(manifest['items']==items and manifest['input_sha256']==h,'Pilot input binding changed')
    if pilot.can_finish_initialization(B,manifest):return []
    require((B/'pilot.sqlite').is_file(),'Initialized database missing')
    with sqlite3.connect((B/'pilot.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True) as conn:
        conn.row_factory=sqlite3.Row;pilot.validate_bound_state(conn,B,items,h)
        rows=[json.loads(r[0]) for r in conn.execute('SELECT payload_json FROM articles ORDER BY ordinal')]
    require([r['sample_id'] for r in rows]==batch['sample_ids'][:len(rows)],'Committed results are not an input prefix')
    return rows

def _article_risk(row,B,registry,seen,plan):
    record=diagnose(row,B);reasons=list(record['automatic_flags'])
    published=row.get('date_published') or ''
    if not plan['date_start']<=published[:10]<plan['date_end_exclusive']:reasons.append('article_date_outside_frozen_scope')
    canonical_key=None
    if row.get('canonical_url'):
        try:canonical_key=normalize_url(row['canonical_url'])
        except ValueError:reasons.append('canonical_identity_invalid')
    for key,value in [('canonical',canonical_key),('body',record['body_compact_sha256'])]:
        if value and (key,value) in seen and seen[(key,value)]!=row['sample_id']:reasons.append('duplicate_'+key+'_requires_review')
    critical=set()
    for reason in reasons:
        if reason in {'http_or_transport_status','non_200_response','non_html_response','url_outside_tiempo_scope','final_url_outside_tiempo_scope','canonical_identity_invalid','invalid_canonical_source_identity','ambiguous_canonical_source_identity','invalid_canonical_output_identity'}:critical.add(reason)
        if reason in {'canonical_source_difference','canonical_url_outside_tiempo_scope'} and row.get('canonical_url'):critical.add(reason)
    for channel in ['url','final_url','canonical_url']:
        if row.get(channel):
            try:normalize_url(row[channel])
            except ValueError:critical.add(channel+'_identity_invalid')
    if str(row.get('error') or '').startswith('transport_error'):critical.add('transport_error')
    if row.get('source_specific_error') in {'soft_error_page','invalid_article_canonical'}:critical.add(row['source_specific_error'])
    unexplained=sorted(set(reasons)-critical)
    families=set()
    for reason in unexplained:
        if 'date' in reason:families.add('publication_date')
        elif any(k in reason for k in ['body','summary','media','duplicate_']):families.add('body_or_media')
        elif any(k in reason for k in ['structure','container','layout','jsonld','expected_visible_h1']):families.add('article_structure')
        else:families.add('other_unexplained')
    record.update(automatic_flags=sorted(set(reasons)|critical),critical_flags=sorted(critical),
                  unexplained_flags=unexplained,unexplained_families=sorted(families),
                  novel_type=record['signature'] not in registry['known_signatures'],
                  collection_quality_status=QUARANTINE if critical or unexplained else PENDING)
    return record,record['automatic_flags']

def _remember(row,rec,seen):
    if row.get('canonical_url'):
        try:seen[('canonical',normalize_url(row['canonical_url']))]=row['sample_id']
        except ValueError:pass
    if rec.get('body_compact_sha256'):seen[('body',rec['body_compact_sha256'])]=row['sample_id']

def _window_trigger(history):
    current=history[-1]
    if current['critical_flags']:return 'critical_source_or_access_failure'
    service=[bool(r.get('service_failure')) for r in history]
    if len(service)>=3 and all(service[-3:]):return 'three_consecutive_terminal_service_failures'
    if sum(service[-80:])>=8:return 'eight_terminal_service_failures_in_rolling80'
    eligible={'publication_date','body_or_media','article_structure'}
    if len(history)>=2 and eligible&set(history[-2]['unexplained_families'])&set(current['unexplained_families']):
        return 'two_consecutive_same_family_anomalies'
    if sum(bool(r['unexplained_flags']) for r in history[-POLICY['rolling_window']:])>=POLICY['unexplained_rows_limit']:
        return 'three_unexplained_rows_in_rolling80'
    return None

def _assess_row(root,plan,row,B,registry,seen,history):
    try:record,_=_risk(row,B,registry,seen,plan)
    except Exception as exc:
        record={'sample_id':row['sample_id'],'url':row['url'],'snapshot_sha256':row.get('snapshot_sha256'),
                'fields_sha256':fields_digest(row),'signature':None,'body_compact_sha256':None,
                'critical_flags':['source_check_exception'],'unexplained_flags':[],'unexplained_families':[],
                'automatic_flags':['source_check_exception'],'novel_type':False,
                'collection_quality_status':QUARANTINE,'diagnostic_error':type(exc).__name__+': '+str(exc)}
    receipt={'schema':MODE,'plan_sha256':plan['plan_sha256'],'record':record}
    path=pilot.safe_path(root,'row_checks/'+row['sample_id']+'.json')
    if path.exists():require(load(path)==receipt,'Saved row assessment changed')
    else:write(root,'row_checks/'+row['sample_id']+'.json',receipt)
    history.append(record);_remember(row,record,seen)
    return record,_window_trigger(history)


def _equal(left,right,key='sample_id'):
    require(set(left)==set(right) and len(left)==len(right),'Readback schema/count mismatch')
    a,b=left.set_index(key).sort_index(),right.set_index(key).sort_index();require(a.index.is_unique and b.index.is_unique and a.index.tolist()==b.index.tolist(),'Readback row identity mismatch')
    text=lambda v:'' if v is None or pd.isna(v) else str(v)
    for c in a:require(a[c].map(text).tolist()==b[c].map(text).tolist(),'Readback field mismatch: '+c)

def _verify_native_articles(native,rows,summary):
    """Account every successful request through primary/alias membership."""
    successful={r['sample_id']:r for r in rows if r['qa_status']=='success'}
    require(native.sample_id.is_unique,'Duplicate native primary identity')
    seen=[];primaries=[];groups={}
    normalized=lambda value:re.sub(r'\s+',' ',str(value or '')).strip()
    def signature(row):
        fields=('title','summary','main_text','authors','date_published','date_modified','topic','section','language')
        media=row.get('media_embeds') or []
        if isinstance(media,str):
            try:media=json.loads(media)
            except ValueError:media=[media]
        media=tuple(sorted(normalized(x) for x in media)) if isinstance(media,list) else (normalized(media),)
        return tuple(normalized(row.get(k)) for k in fields)+(media,)
    for row in successful.values():
        identity=pilot.canonical_identity(row) or ('raw:'+row['url'])
        groups.setdefault(identity,[]).append(row)
    for primary in native.to_dict('records'):
        sid=primary['sample_id'];require(sid in successful,'Unknown native primary');primaries.append(successful[sid])
        aliases=json.loads(primary['alias_sample_ids']);urls=json.loads(primary['alias_urls'])
        require(isinstance(aliases,list) and isinstance(urls,list) and len(aliases)==len(urls),'Malformed native alias membership')
        identity=pilot.canonical_identity(successful[sid]) or ('raw:'+successful[sid]['url'])
        group=groups[identity];collision=len({signature(r) for r in group})>1
        expected=[successful[sid]] if collision else group
        require([r['sample_id'] for r in expected]==[sid]+aliases and [r['url'] for r in expected]==[primary['url']]+urls,'Native members differ from current successful requests')
        require(bool(primary['canonical_collision'])==collision,'Native collision flag mismatch')
        status='collision_review' if collision else 'identical_aliases_merged' if len(expected)>1 else 'single'
        require(primary['canonical_dedup_status']==status,'Native deduplication status mismatch')
        require((primary.get('canonical_identity') or None)==(None if identity.startswith('raw:') else identity),'Native canonical identity mismatch')
        seen.extend([sid]+aliases)
    require(len(seen)==len(set(seen)) and set(seen)==set(successful),'Dropped or double-counted native request member')
    require(summary['article_rows']==len(native) and summary['successful_url_rows']==len(successful) and summary['canonical_alias_rows']==len(successful)-len(native),'Native accounting mismatch')
    require(summary['canonical_collision_groups']==sum(len({signature(r) for r in group})>1 for group in groups.values()),'Native collision group count mismatch')
    current=pd.DataFrame(primaries) if primaries else pd.DataFrame(columns=list(rows[0]))
    shared=[k for k in current if k in native];_equal(native[shared],current[shared])

def _batch_check(root,batch,rows,records):
    B=root/'batches'/batch['batch_id'];exp=load(B/'export_manifest.json')
    require(exp['result_rows']==len(rows) and exp['manual_review']['annotation_file_present'] is False and exp['manual_review']['status_counts'].get('reviewed',0)==0,'Unexpected native manual review state')
    for n,meta in exp['files'].items():require(sha_file(B/n)==meta['sha256'],'Native export hash mismatch')
    for n,key in [('articles','sample_id'),('attempts','attempt_id')]:_equal(pd.read_parquet(B/(n+'.parquet')),pd.read_csv(B/(n+'.csv'),dtype=str,keep_default_na=False),key)
    native=pd.read_parquet(B/'articles.parquet');_verify_native_articles(native,rows,exp)
    for n in ['articles','attempts']:
        actual=pd.read_parquet(B/(n+'.parquet'));require(actual.manual_review_status.eq('not_reviewed').all() and actual.manual_review_result.isna().all(),'Native export invented a manual review')
    require(len(rows)==len(records) and [r['sample_id'] for r in rows]==[r['sample_id'] for r in records],'Every saved row needs exactly one current diagnostic record')
    frame=pd.DataFrame([{**r,'collection_review_status':PENDING,'collection_quality_status':rec['collection_quality_status'],
                         'automatic_flags':json.dumps(rec['automatic_flags'],ensure_ascii=False),
                         'unexplained_families':json.dumps(rec['unexplained_families'],ensure_ascii=False),
                         'novel_type':rec['novel_type'],'source_signature':rec['signature'],
                         'confirmed_source_missing_title':bool(rec.get('confirmed_source_empty')),
                         'collection_outcome':rec.get('collection_outcome','article_candidate'),'service_failure':bool(rec.get('service_failure')),
                         'source_judgment_flags':json.dumps(rec.get('source_judgment_flags',[]),ensure_ascii=False),
                         'manual_review_status':'not_reviewed','manual_review_result':None}
                        for r,rec in zip(rows,records)])
    subsets={'failed_or_incomplete_urls.csv':frame.qa_status!='success',
             'core_fields_complete.csv':frame.qa_status=='success',
             'usable_candidates.csv':(frame.qa_status=='success')&(frame.collection_quality_status==PENDING),
             'quarantined_results.csv':frame.collection_quality_status==QUARANTINE,
             'source_judgment.csv':frame.source_judgment_flags.ne('[]'),
             'source_unavailable.csv':frame.collection_outcome.eq('source_unavailable'),
             'service_failures.csv':frame.collection_outcome.eq('service_failure_exhausted'),
             'source_gaps.csv':frame.error.fillna('').eq('missing_title')&frame.confirmed_source_missing_title,
             'novel_types.csv':frame.novel_type}
    evidence={'schema':MODE,'batch_id':batch['batch_id'],'input_sha256':batch['input_sha256'],'state':PENDING,
              'rows':len(rows),'batch_input_complete':len(rows)==batch['row_count'],'records':records,
              'native_files':exp['files'],'manual_reviews':0,'article_acceptance':False,
              'subset_counts':{name:int(mask.sum()) for name,mask in subsets.items()},
              'subset_definition':'Subsets can overlap. Usable means complete fields and no automatic anomaly; it is still not_reviewed, never article acceptance.'}
    binding=digest(evidence);folder=pilot.safe_path(root,f'automatic_checks/{batch["batch_id"]}/{binding}')
    names=['all_results.csv','all_results.parquet',*subsets]
    if not folder.exists():
        folder.mkdir(parents=True);frame.to_csv(folder/'all_results.csv',index=False,encoding='utf-8-sig');frame.to_parquet(folder/'all_results.parquet',index=False)
        for filename,mask in subsets.items():frame[mask].to_csv(folder/filename,index=False,encoding='utf-8-sig')
        write(folder,'check.json',{**evidence,'derived_files':{n:sha_file(folder/n) for n in names}})
    _equal(frame,pd.read_parquet(folder/'all_results.parquet'));_equal(frame,pd.read_csv(folder/'all_results.csv',dtype=str,keep_default_na=False))
    for filename,mask in subsets.items():_equal(frame[mask],pd.read_csv(folder/filename,dtype=str,keep_default_na=False))
    require(load(folder/'check.json')=={**evidence,'derived_files':{n:sha_file(folder/n) for n in names}},'Existing automatic check evidence or exports changed')
    return {'batch_id':batch['batch_id'],'rows':len(rows),'status':PENDING,'check_path':str(folder/'check.json'),
            'check_sha256':sha_file(folder/'check.json'),'all_results_path':str(folder/'all_results.parquet'),
            'all_results_sha256':sha_file(folder/'all_results.parquet'),'batch_input_complete':len(rows)==batch['row_count']}


def _checkpoint(root,plan,summaries):
    frame=pd.concat([pd.read_parquet(s['all_results_path']) for s in summaries],ignore_index=True);require(frame.manual_review_status.eq('not_reviewed').all(),'Checkpoint cannot claim manual reviews')
    end=len(frame);name=f'checkpoint_{end:08d}';path=pilot.safe_path(root,name)
    # Exact immutable receipt; checkpoint contains an index and statistics, not approvals.
    samples=[];sample_reasons={}
    rank=lambda sid:hashlib.sha256((plan['sampling_seed']+'\n'+plan['plan_sha256']+'\n'+sid).encode()).hexdigest()
    for signature,part in frame[frame.novel_type].groupby('source_signature'):
        sid=min(part.sample_id,key=rank);sample_reasons.setdefault(sid,set()).add('novel_signature_representative')
    for sid in frame[frame.collection_quality_status==QUARANTINE].sample_id:sample_reasons.setdefault(sid,set()).add('quarantined_row')
    for s in summaries:
        f=pd.read_parquet(s['all_results_path'])
        count=min(10 if s['batch_id']=='batch_000001' else 3,len(f));ids=sorted(f.sample_id,key=rank)[:count]
        for sid in ids:sample_reasons.setdefault(sid,set()).add('frozen_sha_sample')
        for sid in f.sample_id:
            if sid not in sample_reasons:continue
            r=f[f.sample_id==sid].iloc[0];samples.append({'sample_id':sid,'batch_id':s['batch_id'],'url':r['url'],'snapshot_path':str(root/'batches'/s['batch_id']/r['snapshot_path']),'snapshot_sha256':r['snapshot_sha256'],'selection_sha256':rank(sid),'selection_reasons':';'.join(sorted(sample_reasons[sid])),'manual_review_status':'not_reviewed'})
    result={'schema':MODE,'plan_sha256':plan['plan_sha256'],'status':PENDING,'rows':end,'core_fields_complete':int(frame.qa_status.eq('success').sum()),'usable_candidates':int(((frame.qa_status=='success')&(frame.collection_quality_status==PENDING)).sum()),'quarantined_rows':int((frame.collection_quality_status==QUARANTINE).sum()),'novel_type_rows':int(frame.novel_type.sum()),'errors':dict(Counter(frame.error.fillna('none'))),'date_days':dict(Counter(frame.date_published.fillna('unknown').str[:10])),'collection_outcomes':dict(Counter(frame.collection_outcome)),'actual_manual_reviews':0,'pending_source_review_sample_count':len(samples),'batch_checks':summaries,'newspaper_complete':False,'article_acceptance':False}
    sample_bytes=csvbytes(list(samples[0]),samples);result['pending_samples_sha256']=hashlib.sha256(sample_bytes).hexdigest()
    if path.exists():require(load(path/'summary.json')==result and sha_file(path/'pending_source_review_samples.csv')==result['pending_samples_sha256'],'Existing checkpoint changed')
    else:
        path.mkdir();write(path,'summary.json',result);pilot.atomic_bytes(path/'pending_source_review_samples.csv',sample_bytes);pilot.atomic_bytes(path/'Kevin_NOTE.md',b'# Kevin\nAutomatic checkpoint only; all unreviewed rows remain not_reviewed. Pending samples are not manual PASS.\n')
    return result

def run(root,media_root,*,max_batches,fetcher=None,parser=None,allow_network=False,clock=time.time,sleep=time.sleep,disk_free=None):
    """Explicit invocation, finite max_batches and plan-wide request budget; bounded retries."""
    require(fetcher is not None or allow_network,'Explicit network execution flag required; offline calls must provide a fake fetcher')
    root=namespace(root,media_root);require(type(max_batches) is int and 1<=max_batches<=10000,'Explicit bounded max_batches required')
    with pilot.exclusive_run(root.parent), pilot.exclusive_run(root):
        plan,registry=load_plan(root,media_root)
        if (root/'continuous_state.json').exists():
            old=load(root/'continuous_state.json');require(old.get('plan_sha256')==plan['plan_sha256'],'Control state belongs to another plan')
            if old.get('status')=='halted_no_automatic_resume':require((root/'safety_halt.json').is_file() and sha_file(root/'safety_halt.json')==old.get('halt_sha256'),'Safety halt deleted or changed; no automatic resume')
        if (root/'halt_receipts').exists():require((root/'safety_halt.json').is_file(),'Permanent halt receipt exists; refusing removed cursor')
        if (root/'safety_halt.json').exists():
            require(load(root/'safety_halt.json')['plan_sha256']==plan['plan_sha256'],'Halt belongs to another plan')
            return _state(root,plan,'halted_no_automatic_resume',halt_sha256=sha_file(root/'safety_halt.json'))
        try:entries=_ledger(root,plan);_snapshot_reconciliation(root,plan,entries)
        except Exception as exc:return _halt(root,plan,'transport_state_requires_reconciliation',detail=type(exc).__name__+': '+str(exc))
        seen={};history=list(plan['seed_context']['source_history']);summaries=[];executed=0
        for batch in plan['batches']:
            B=root/'batches'/batch['batch_id'];saved=_rows(root,batch);records=[]
            # Replay durable rows before a new request, including commit-before-callback crashes.
            try:
                for row in saved:
                    rec,trigger=_assess_row(root,plan,row,B,registry,seen,history);records.append(rec)
                    if trigger:
                        partial=_batch_check(root,batch,saved[:len(records)],records)
                        return _halt(root,plan,trigger,sample_id=row['sample_id'],risks=rec['automatic_flags'],partial_check=partial)
            except Exception as exc:return _halt(root,plan,'source_check_exception',detail=type(exc).__name__+': '+str(exc))
            if len(saved)<batch['row_count']:
                if executed>=max_batches:return _state(root,plan,PENDING,completed_batches=len(summaries),invocation_batch_limit_reached=True)
                stopped={}
                def stop(reason,**evidence):
                    stopped.update(reason=reason,**evidence);_halt(root,plan,reason,**evidence);raise KeyboardInterrupt()
                def guarded_fetch(url,timeout,**kwargs):
                    return transport_with_retries(root,plan,batch,B,url,timeout,stop,fetcher,clock,sleep,disk_free,kwargs)
                def committed(item,row):
                    try:rec,trigger=_assess_row(root,plan,row,B,registry,seen,history)
                    except Exception as exc:stop('automatic_check_integrity_error',sample_id=row['sample_id'],detail=type(exc).__name__+': '+str(exc))
                    records.append(rec)
                    if trigger:stop(trigger,sample_id=row['sample_id'],risks=rec['automatic_flags'])
                outcome=pilot.run_pilot(root/batch['input_path'],B,Path(media_root),pause_seconds=0,timeout=plan['timeout'],fetcher=guarded_fetch,parser=parser,after_commit=committed)
                executed+=1
                if stopped:
                    partial=None;saved_partial=_rows(root,batch)
                    if saved_partial and len(saved_partial)==len(records):
                        try:partial=_batch_check(root,batch,saved_partial,records)
                        except Exception as exc:write(root,'halt_readback_error.json',{'error':type(exc).__name__+': '+str(exc),'article_acceptance':False})
                    return _state(root,plan,'halted_no_automatic_resume',halt_sha256=sha_file(root/'safety_halt.json'),pending_input_urls=outcome['pending_input_urls'],partial_check=partial)
                if outcome['interrupted']:return _state(root,plan,'interrupted_requires_explicit_invocation',pending_input_urls=outcome['pending_input_urls'])
                saved=_rows(root,batch)
            try:
                require(len(saved)==batch['row_count'],'Incomplete batch cannot advance')
                summaries.append(_batch_check(root,batch,saved,records))
            except Exception as exc:return _halt(root,plan,'batch_readback_failed',batch_id=batch['batch_id'],detail=type(exc).__name__+': '+str(exc))
            if sum(s['rows'] for s in summaries)%400==0:_checkpoint(root,plan,summaries)
        _checkpoint(root,plan,summaries)
        context={'source_history':history[-79:],'service_history':[],'last_transport_finish':(_ledger(root,plan)[-1]['epoch'] if _ledger(root,plan) else plan['seed_context'].get('last_transport_finish')),'prior_plan_receipts':plan['seed_context'].get('prior_plan_receipts',[])}
        write(root,'continuation_context.json',context)
        return _state(root,plan,PENDING,collection_inputs_finished=True,completed_batches=len(summaries),result_rows=plan['row_count'],manual_reviews=0,continuation_context_sha256=sha_file(root/'continuation_context.json'))


def response_kind(response):
    """Technical response class, never inferred from arbitrary article prose."""
    from urllib.parse import urlsplit
    from bs4 import BeautifulSoup
    status=response.get('status');error=str(response.get('error') or '')
    # Safety metadata outranks any original timeout text. Preserve the response,
    # then stop instead of allowing the timeout branch to schedule a retry.
    if 'invalid_transport_clock_after_response' in error:return 'critical_transport_clock'
    final=response.get('final_url')
    if final:
        u=urlsplit(final)
        if u.scheme not in {'http','https'} or u.hostname not in {'tiempo.com.mx','www.tiempo.com.mx'}:return 'critical_identity'
    soup=BeautifulSoup(response.get('text') or '', 'html.parser')
    title=soup.title.get_text(' ',strip=True).casefold() if soup.title else ''
    if status in {403,429} or soup.select_one('#challenge-form, #cf-challenge-running, .g-recaptcha, iframe[src*="captcha"]') or title in {'just a moment...', 'attention required! | cloudflare', 'verify you are human'}:return 'critical_access'
    # A transport error means HTTP content may be partial: never call it 404.
    if error:
        if re.search(r'timeout|timed?\s*out|curl(?:\s+exit)?\s*[:=]?\s*28',error,re.I):return 'retryable_service'
        return 'critical_transport'
    if status in {404,410}:return 'source_unavailable'
    if isinstance(status,int) and 500<=status<=599:return 'retryable_service'
    if status!=200:return 'critical_access'
    h1=soup.select_one('article#article-post h1') or soup.select_one('h1')
    if h1 and 'ocurrió un error al procesar la noticia' in h1.get_text(' ',strip=True).casefold():return 'source_unavailable'
    return 'article_response'


def _transport_receipt(root,event):
    base=f'transport_snapshots/{event["sequence"]:08d}'
    p=pilot.safe_path(root,base+'.json');record=load(p)
    require(all(record.get(k)==event.get(k) for k in ['plan_sha256','sequence','batch_id','url','attempt_id']),'Transport receipt identity changed')
    raw=pilot.safe_path(root,base+'.html').read_bytes()
    require(hashlib.sha256(raw).hexdigest()==record['text_sha256'],'Transport response snapshot changed')
    require(record['finish_epoch']>=event['epoch'] and math.isfinite(record['finish_epoch']),'Bad transport completion clock')
    response={**record['response'],'text':raw.decode('utf-8')}
    require(response_kind(response)==record['response_kind'],'Transport classification changed')
    return record,response


def _snapshot_reconciliation(root,plan,entries):
    """Saved terminal response can recover before pilot commit without another GET.

    An unfinished retry chain or uncertain network window is preserved and halted,
    never silently repeated. The caller owns any later reconciliation decision.
    """
    starts=[e for e in entries if e['event']=='start'];finishes={e['sequence']:e for e in entries if e['event']=='finish'}
    groups={}
    for e in starts:
        receipt,response=_transport_receipt(root,e)
        f=finishes.get(e['sequence'])
        if f is None:
            require(e==entries[-1],'Unfinished call is not the final reservation')
            _append(root,plan,{**e,'event':'finish','epoch':receipt['finish_epoch'],'response_sha256':sha_file(root/f'transport_snapshots/{e["sequence"]:08d}.json')})
        else:require(f.get('response_sha256')==sha_file(root/f'transport_snapshots/{e["sequence"]:08d}.json'),'Transport receipt does not match durable ledger')
        groups.setdefault((e['batch_id'],e['attempt_id']),[]).append((e,receipt,response))
    db_attempts={}
    for batch in plan['batches']:
        B=root/'batches'/batch['batch_id'];items,h=pilot.load_input(root/batch['input_path'])
        if not (B/'pilot.sqlite').exists():continue
        with sqlite3.connect((B/'pilot.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True) as db:
            db.row_factory=sqlite3.Row
            for a in db.execute('SELECT * FROM fetch_attempts'):
                a=dict(a);key=(batch['batch_id'],a['attempt_id']);db_attempts[key]=a
                require(key in groups and a['action']=='fetch' and all(e['url']==a['url'] for e,_,_ in groups[key]),'Pilot attempt has no matching transport evidence')
                calls=groups[key];last,receipt,response=calls[-1]
                require([r['retry_index'] for _,r,_ in calls]==list(range(len(calls))) and len(calls)<=3,'Invalid bounded retry history')
                require(receipt['terminal'],'Interrupted retry chain needs explicit reconciliation; no repeated request')
                item=next(x for x in items if x['url']==a['url'])
                html=B/'raw_html'/hashlib.sha256(a['url'].encode()).hexdigest()/(a['attempt_id']+'.html')
                meta=html.with_suffix('.json')
                if not meta.exists():
                    require(not a['completed_at'],'Committed result lost its response metadata')
                    # This writes only this new v5 run, never an old plan or shared DB.
                    pilot.save_snapshot(B,item,a['attempt_id'],h,response)
                saved=load(meta);require(saved['snapshot_sha256']==receipt['text_sha256'] and saved['response']=={k:v for k,v in response.items() if k!='text'},'Pilot final response differs from final transport evidence')
                require(sha_file(html)==receipt['text_sha256'],'Pilot response snapshot changed')
                if not a['completed_at'] and response.get('error'):
                    # Frozen pilot intentionally does not adopt incomplete error
                    # snapshots. Preserve them; do not make a fresh hidden retry.
                    raise ValueError('Saved incomplete terminal transport requires reconciliation before resume')
    require(set(groups)==set(db_attempts),'Transport reservations and pilot attempts differ')


def transport_with_retries(root,plan,batch,B,url,timeout,stop,fetcher,clock,sleep,disk_free,kwargs):
    with sqlite3.connect((B/'pilot.sqlite').as_uri()+'?mode=ro',uri=True) as db:
        pending=db.execute("SELECT attempt_id FROM fetch_attempts WHERE url=? AND action='fetch' AND completed_at IS NULL",(url,)).fetchall()
    if len(pending)!=1:stop('ambiguous_pilot_attempt_before_transport')
    for retry_index in range(POLICY['attempts_per_url']):
        free=disk_free(B) if disk_free else shutil.disk_usage(B).free
        if not isinstance(free,(int,float)) or not math.isfinite(free):stop('invalid_disk_space_measurement')
        if free<plan['min_free_bytes']:stop('low_disk_space',free_bytes=free)
        try:ledger=_ledger(root,plan)
        except Exception as exc:stop('transport_state_requires_reconciliation',detail=str(exc))
        starts=[e for e in ledger if e['event']=='start'];epoch=clock()
        if not isinstance(epoch,(int,float)) or not math.isfinite(epoch):stop('invalid_transport_clock')
        if len(starts)>=plan['max_fetch_calls']:stop('request_budget_exhausted',fetch_calls_started=len(starts))
        last=ledger[-1]['epoch'] if ledger else plan['seed_context'].get('last_transport_finish')
        if ledger and ledger[-1]['event']!='finish':stop('uncertain_previous_transport')
        gap=max(plan['pause_seconds'],POLICY['retry_backoff_seconds'][retry_index-1] if retry_index else 0)
        if last is not None:
            if not math.isfinite(last) or epoch<last:stop('invalid_transport_clock')
            if epoch-last<gap:sleep(gap-(epoch-last))
        ready=clock()
        if not isinstance(ready,(int,float)) or not math.isfinite(ready) or ready<epoch or (last is not None and ready-last<gap):stop('transport_pause_not_satisfied')
        event={'event':'start','sequence':len(starts)+1,'plan_sha256':plan['plan_sha256'],'batch_id':batch['batch_id'],'url':url,'attempt_id':pending[0][0],'epoch':ready}
        _append(root,plan,event)
        try:
            if fetcher is None:
                from crawler_core.capabilities import fetch
                response=fetch(url,timeout,**kwargs)
            else:response=fetcher(url,timeout,**kwargs)
        except Exception as exc:response={'status':None,'text':'','content_type':None,'final_url':url,'error':type(exc).__name__+': '+str(exc)}
        response=pilot.clean(response);finish=clock()
        if not isinstance(finish,(int,float)) or not math.isfinite(finish) or finish<ready:
            response={**response,'error':(response.get('error') or '')+' invalid_transport_clock_after_response'};finish=ready
        kind=response_kind(response);terminal=kind!='retryable_service' or retry_index+1==POLICY['attempts_per_url']
        raw=(response.get('text') or '').encode('utf-8');base=f'transport_snapshots/{event["sequence"]:08d}'
        receipt={**event,'retry_index':retry_index,'finish_epoch':finish,'response_kind':kind,'terminal':terminal,'text_sha256':hashlib.sha256(raw).hexdigest(),'response':{k:v for k,v in response.items() if k!='text'}}
        pilot.atomic_bytes(pilot.safe_path(root,base+'.html'),raw);write(root,base+'.json',receipt)
        _append(root,plan,{**event,'event':'finish','epoch':finish,'response_sha256':sha_file(root/(base+'.json'))})
        if terminal:return response
    raise AssertionError('bounded retry loop did not terminate')


def _risk(row,B,registry,seen,plan):
    raw=pilot.safe_path(B,row['snapshot_path']).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==row['snapshot_sha256'],'Snapshot corruption')
    meta=load(pilot.safe_path(B,str(Path(row['snapshot_path']).with_suffix('.json'))))
    kind=response_kind({**meta['response'],'text':raw.decode('utf-8')})
    if kind=='article_response':
        record,flags=_article_risk(row,B,registry,seen,plan)
        judgment={'article_vs_discovery_day_difference','suspicious_very_short_body_review_only'}
        record['source_judgment_flags']=sorted(set(record['unexplained_flags'])&judgment)
        record['unexplained_flags']=[f for f in record['unexplained_flags'] if f not in judgment]
        families=set()
        for reason in record['unexplained_flags']:
            if 'date' in reason:families.add('publication_date')
            elif any(k in reason for k in ['body','summary','media','duplicate_']):families.add('body_or_media')
            elif any(k in reason for k in ['structure','container','layout','jsonld','expected_visible_h1']):families.add('article_structure')
            else:families.add('other_unexplained')
        record['unexplained_families']=sorted(families)
        record.update(collection_outcome='article_candidate',service_failure=False)
        return record,flags
    critical=[kind] if kind.startswith('critical_') else []
    outcome='source_unavailable' if kind=='source_unavailable' else 'service_failure_exhausted' if kind=='retryable_service' else 'critical_failure'
    if row.get('qa_status')!='error':critical.append('nonarticle_response_marked_success')
    record={'sample_id':row['sample_id'],'url':row['url'],'snapshot_sha256':row['snapshot_sha256'],'fields_sha256':fields_digest(row),
            'signature':None,'body_compact_sha256':None,'critical_flags':critical,'automatic_flags':[kind]+critical,
            'unexplained_flags':[],'unexplained_families':[],'novel_type':False,'confirmed_source_empty':False,
            'collection_quality_status':QUARANTINE,'collection_outcome':outcome,'service_failure':kind=='retryable_service','manual_review_status':'not_reviewed'}
    return record,record['automatic_flags']

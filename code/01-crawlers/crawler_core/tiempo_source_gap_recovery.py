"""Kevin: exact child65 source-gap replay, preserving all original anomaly history.

Offline preparation only. No parser/checker exemption, corrected native rows,
new request, article acceptance, or collection-review gate is produced here.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil

from . import tiempo_continuous_v5 as w
from . import tiempo_remaining_campaign as c
from . import tiempo_resumable_worker as worker

from . import tiempo_connection_recovery as connection
from . import tiempo_review_recovery as review_recovery

SCHEMA = 'tiempo-source-gap-successor-v1'
ACK_SCHEMA = 'tiempo-inherited-source-gap-v1'
REASON = 'two_consecutive_same_family_anomalies'
PRODUCTION = {
    'expected_child_index': 65, 'expected_saved': 333, 'expected_calls': 333,
    'source_sample_ids': ['TC5_476522', 'TC5_501081'], 'next_sample_id': 'TC5_552341',
    'donor_campaign_sha256': '1794c186d0e0e82557258a935247ba4ad754d45444d4b946dd8d17b6c62ff2ef',
    'donor_master_halt_sha256': '8c08a6a7a23081fd6e0f54879304783de23265d2ea61e7dc5dfd55509416b277',
    'donor_native_halt_sha256': '665dcf5c47608650e575648a4cb7e4c1abcd8d57e5a5f4da757b4301df2dd0ad',
}
PRODUCTION_REVIEW_HASHES = {
    'source_review': 'cca7738ecd2b644f202902e921f92b022673b81b6c60784f57433e7f50579ede',
    'independent_review': '0f5a8769ef6f6a046b3814fd4e80036181f5474e50df55b6dc01cac631c11cec',
}
_files = connection._files
_donor_code_binding = connection._donor_code_binding
_verified_inherited_gates = connection._verified_inherited_gates


def _source_bindings(root, plan, prefix):
    result = []
    for offset in (-2, -1):
        item = prefix['rows'][offset]; row = item['row']
        check_path = root/'row_checks'/(row['sample_id']+'.json')
        check = w.load(check_path); record = check['record']
        raw = root/'batches'/item['batch_id']/row['snapshot_path']
        w.require(check['plan_sha256'] == plan['plan_sha256'] and
                  row.get('qa_status') == 'error' and row.get('error') == 'missing_body' and
                  not row.get('main_text') and not row.get('summary') and
                  not json.loads(row.get('media_embeds') or '[]') and
                  record.get('critical_flags') == [] and
                  set(record.get('unexplained_flags', [])) == {'missing_body','unexplained_result_error'} and
                  record.get('collection_quality_status') == w.QUARANTINE and
                  record.get('manual_review_status') == 'not_reviewed' and
                  record.get('snapshot_sha256') == row['snapshot_sha256'] and
                  record.get('fields_sha256') == w.fields_digest(row) and
                  w.sha_file(raw) == row['snapshot_sha256'], 'Source-gap native evidence differs')
        result.append({'sample_id': row['sample_id'], 'url': row['url'],
                       'attempt_id': row['attempt_id'], 'batch_id': item['batch_id'],
                       'snapshot_sha256': row['snapshot_sha256'],
                       'payload_sha256': hashlib.sha256(prefix['payloads'][offset].encode()).hexdigest(),
                       'fields_sha256': w.fields_digest(row),
                       'row_check_sha256': w.sha_file(check_path),
                       'row_check_record_sha256': w.digest(record)})
    return result


def _validate_reviews(cfg, root, plan, prefix):
    sources = _source_bindings(root, plan, prefix)
    w.require([s['sample_id'] for s in sources] == cfg['source_sample_ids'], 'Wrong diagnosed source identities')
    for key in ('source_review','independent_review'):
        c._verify(cfg[key])
        if not cfg.get('synthetic_fixture'):
            w.require(cfg[key]['sha256'] == PRODUCTION_REVIEW_HASHES[key], 'Production source review differs')
    first = w.load(cfg['source_review']['path']); second = w.load(cfg['independent_review']['path'])
    w.require(first.get('human_approval') is False and first.get('article_acceptance') is False and
              first.get('collection_gate_65_400_completed') is False and
              second.get('human_approval') is False and second.get('article_acceptance') is False and
              second.get('source_review') == cfg['source_review'] and
              second.get('parser_fix_demonstrated') is False,
              'Source investigation must not assert acceptance or a completed collection gate')
    w.require([r['sample_id'] for r in first['records']] == cfg['source_sample_ids'] and
              [r['sample_id'] for r in second['records']] == cfg['source_sample_ids'],
              'Both independent readings must cover exactly the two saved sources')
    for expected, a, b in zip(sources, first['records'], second['records']):
        for r in (a,b):
            w.require(r.get('actual_ai_read') is True and r.get('human_approval') is False and
                      r.get('article_acceptance') is False and
                      r.get('research_status') == 'NEEDS_JOAQUIN_REVIEW', 'Source gap review status changed')
        bound = a['bound_source']; findings = a['actual_ai_source_findings']
        mapping={'sha256':'snapshot_sha256','payload_utf8_sha256':'payload_sha256',
                 'fields_sha256':'fields_sha256','rowcheck_sha256':'row_check_sha256'}
        w.require(all(bound.get(k)==expected[v] for k,v in mapping.items()) and
                  bound.get('attempt_id')==expected['attempt_id'] and
                  all(b.get(k)==expected[k] for k in ('snapshot_sha256','payload_sha256','fields_sha256','row_check_sha256')),
                  'Source reading bindings differ from saved raw/payload/check')
        w.require(findings.get('article_subtree_fully_read') is True and
                  findings.get('actual_prose_omission_detected') is False and
                  findings.get('source_body_unavailable_in_this_saved_response') is True and
                  findings.get('unknown_article_embed_element_found') is False and
                  findings.get('confirmed_video_only') is False and
                  b.get('diagnosis')=='source_response_missing_body_no_extraction_loss' and
                  b.get('technical_blockers')==[], 'Unresolved extraction/media defect cannot be acknowledged')
    return sources


def validate_ack(root, plan, binding=None):
    if binding is None:
        return None
    root=Path(root).resolve(); c._verify(binding); ack=w.load(binding['path'])
    w.require(ack.get('schema')==ACK_SCHEMA and ack.get('target_root')==str(root) and
              type(ack.get('synthetic_fixture')) is bool and ack.get('human_approval') is False and
              ack.get('article_acceptance') is False and ack.get('research_status')=='NEEDS_JOAQUIN_REVIEW',
              'Source-gap acknowledgment identity/status differs')
    donor=Path(ack['donor_root']).resolve(); master=Path(ack['donor_campaign_root']).resolve()
    w.require(donor != root and donor not in root.parents and root not in donor.parents and
              master != root and master not in root.parents and root not in master.parents,
              'Source-gap successor must be disjoint from donor')
    evidence=ack['donor_bindings']; halt_path=donor/'safety_halt.json'; halt_sha=w.sha_file(halt_path)
    required=[donor/n for n in ('continuous_plan.json','continuous_state.json','safety_halt.json','transport_calls.jsonl','transport_state.json')]
    required += [donor/'halt_receipts'/(halt_sha+'.json'),master/'campaign.json',master/'technical_stop.json']
    required += [donor/'row_checks'/(s['sample_id']+'.json') for s in ack['sources']]
    required += list(donor.glob('batches/*/pilot.sqlite'))
    w.require(all(str(p) in evidence for p in required), 'Missing immutable source-gap donor binding')
    for filename,digest in evidence.items():
        w.require(w.sha_file(filename)==digest, 'Source-gap donor evidence changed: '+filename)
    donor_campaign=c._signed(master/'campaign.json','campaign_sha256')
    donor_events=c.events(master)
    w.require(donor_events[-1]['kind']=='technical_stop' and
              donor_events[-1]['evidence']==c._bound(master/'technical_stop.json'),
              'Source-gap donor has changed after its investigated terminal event')
    w.require(ack['synthetic_fixture']==donor_campaign['synthetic_fixture'], 'Synthetic/live source-gap donor mismatch')
    cfg={'expected_child_index':ack['expected_child_index'], 'expected_saved':ack['prefix_rows'],
         'expected_calls':ack['prefix_calls'], 'source_sample_ids':[s['sample_id'] for s in ack['sources']],
         'next_sample_id':ack['next_sample_id'], 'donor_campaign_sha256':evidence[str(master/'campaign.json')],
         'donor_master_halt_sha256':evidence[str(master/'technical_stop.json')],
         'donor_native_halt_sha256':halt_sha, 'synthetic_fixture':ack['synthetic_fixture'],
         'source_review':ack['source_review'], 'independent_review':ack['independent_review']}
    if not ack['synthetic_fixture']:
        w.require(all(cfg[k]==v for k,v in PRODUCTION.items()), 'Uninvestigated production source-gap acknowledgment')
    w.require(w.load(donor/'continuous_plan.json')==plan and
              w.sha_file(root/'continuous_plan.json')==evidence[str(donor/'continuous_plan.json')],
              'Native source-gap plan changed')
    halt=w.load(halt_path); state=w.load(donor/'continuous_state.json'); master_halt=w.load(master/'technical_stop.json')
    w.require(halt.get('reason')==REASON and halt.get('sample_id')==cfg['source_sample_ids'][-1] and
              halt.get('plan_sha256')==plan['plan_sha256'] and
              w.load(donor/'halt_receipts'/(halt_sha+'.json'))==halt and
              state.get('status')=='halted_no_automatic_resume' and state.get('halt_sha256')==halt_sha and
              master_halt.get('reason')=='native_worker_stopped' and
              master_halt['native_result'].get('halt_sha256')==halt_sha,
              'Acknowledgment does not match the investigated same-family stop')
    old=worker.inherited_prefix_evidence(donor,plan,ack['prefix_rows'])
    current=worker.inherited_prefix_evidence(root,plan,ack['prefix_rows'])
    w.require(old['total_rows']==state.get('result_rows')==master_halt['native_result'].get('result_rows')==ack['prefix_rows'],
              'Source-gap donor prefix count changed')
    for key in ('prefix_payload_sha256','prefix_attempts_sha256','prefix_articles_sha256'):
        w.require(old[key]==current[key]==ack[key], 'Source-gap native prefix changed: '+key)
    w.require(_validate_reviews(cfg,donor,plan,old)==_source_bindings(root,plan,current)==ack['sources'],
              'Source-gap sources changed after copying')
    queue=w.readcsv(root/'queue.csv')
    w.require(queue[ack['prefix_rows']]['sample_id']==ack['next_sample_id'], 'Source-gap next input changed')
    entries=w._ledger(root,plan); donor_entries=w._ledger(donor,plan)
    old_bytes=(donor/'transport_calls.jsonl').read_bytes()
    w.require(len(donor_entries)==2*ack['prefix_calls'] and entries[:len(donor_entries)]==donor_entries and
              b''.join((root/'transport_calls.jsonl').read_bytes().splitlines(keepends=True)[:len(donor_entries)])==old_bytes,
              'Source-gap transport prefix changed')
    for source in ack['sources']:
        calls=[e for e in donor_entries if e['event']=='start' and e['attempt_id']==source['attempt_id']]
        w.require(len(calls)==1, 'Investigated source response request chain changed')
        receipt,response=w._transport_receipt(root,calls[0]); old_receipt,_=w._transport_receipt(donor,calls[0])
        w.require(receipt==old_receipt and receipt['retry_index']==0 and response.get('status')==200 and
                  response.get('curl_exit_code') in (None,0) and response.get('final_url')==source['url'] and
                  bool(response.get('text')), 'Investigated source response transport changed')
    return ack


def acknowledged_replay(ack, row, record, trigger, history):
    """Only the second exact saved row. Never called for a newly fetched result."""
    return bool(ack and trigger==REASON and
                row['sample_id']==ack['sources'][-1]['sample_id'] and
                row['attempt_id']==ack['sources'][-1]['attempt_id'] and
                w.digest(record)==ack['sources'][-1]['row_check_record_sha256'] and
                len(history)>=2 and
                [w.digest(r) for r in history[-2:]]==[s['row_check_record_sha256'] for s in ack['sources']])


def _read_donor(cfg):
    donor=Path(cfg['donor_root']).resolve()
    w.require(w.sha_file(donor/'campaign.json')==cfg['donor_campaign_sha256'], 'Donor campaign changed')
    old=c._signed(donor/'campaign.json','campaign_sha256')
    w.require(old['root']==str(donor) and old['schema']==c.SCHEMA, 'Wrong donor campaign')
    synthetic=bool(cfg.get('synthetic_fixture'))
    w.require(synthetic==bool(old['synthetic_fixture']), 'Synthetic/live donor mismatch')
    if not synthetic:
        w.require(all(cfg.get(k)==v for k,v in PRODUCTION.items()),
                  'Only the exact investigated child65 source-gap halt is authorized')
    code=_donor_code_binding(cfg['donor_code_root'],old['program_sha256'])
    for key in ('config_source','preflight','prepared_manifest','source_context','source_ledger','registry','obligations','queue'):
        c._verify(old[key])
    for p in old['parts']: c._verify(p)
    c._verify_old(w.load(old['preflight']['path']))
    if old.get('connection_recovery'):
        connection.verify(old)
    if old.get('review_recovery'):
        review_recovery.verify(old)
    events=c.events(donor)
    stops=[e for e in events if e['kind']=='technical_stop']
    w.require(len(stops)==1 and events[-1]==stops[0] and
              stops[0]['evidence']==c._bound(donor/'technical_stop.json'), 'Donor final stop event mismatch')
    done,context,closed_saved,closed_calls=c._completed(old,events)
    part=old['parts'][len(done)]
    w.require(part['plan_index']==cfg['expected_child_index'], 'Wrong original child index')
    child=c.child_path(old,part['plan_index'])
    plan,registry=w.load_plan(child,old['media'])
    counts=c._counts(child,plan)
    w.require(counts=={'saved':cfg['expected_saved'],'calls':cfg['expected_calls'],
              'pending_native_attempts':0,'open_transport':False}, 'Donor counts or transport state changed')
    w.require(plan['seed_context']==context, 'Donor predecessor context differs')
    if not synthetic:
        w.require(old['baseline_saved']+closed_saved==128000 and old['baseline_calls']+closed_calls==128061 and
                  old['remaining_rows']-closed_saved==2531 and plan['row_count']==2000 and
                  old['parts'][-1]['plan_index']==66, 'Production source-gap scope/count boundary differs')
    w.require(w.sha_file(donor/'technical_stop.json')==cfg['donor_master_halt_sha256'] and
              w.sha_file(child/'safety_halt.json')==cfg['donor_native_halt_sha256'], 'Specific halt evidence changed')
    state=w.load(child/'continuous_state.json'); halt=w.load(child/'safety_halt.json')
    w.require(state['status']=='halted_no_automatic_resume' and state['halt_sha256']==cfg['donor_native_halt_sha256'] and
              halt['reason']==REASON and halt['sample_id']==cfg['source_sample_ids'][-1], 'Wrong native failure')
    queue=w.readcsv(child/'queue.csv')
    w.require([q['sample_id'] for q in queue[counts['saved']-2:counts['saved']]]==cfg['source_sample_ids'] and
              queue[counts['saved']]['sample_id']==cfg['next_sample_id'], 'Failure/next input differs from frozen queue')
    # Check existing exports without invoking any regeneration path on the donor.
    rows=[]
    for batch in plan['batches']:
        current=w._rows(child,batch); rows.extend(current)
        B=child/'batches'/batch['batch_id']
        if not current: continue
        manifest=w.load(B/'export_manifest.json')
        w.require(manifest['result_rows']==len(current), 'Donor exports do not contain its current saved prefix')
        items,h=w.pilot.load_input(child/batch['input_path'])
        preview=worker._export_preview(B,items,h)
        w.require(preview['files']==manifest['files'], 'Donor export readback differs before copying')
        for name,meta in manifest['files'].items():
            w.require(w.sha_file(B/name)==meta['sha256'], 'Donor export bytes differ before copying')
    w.require([r['sample_id'] for r in rows]==[q['sample_id'] for q in queue[:counts['saved']]], 'Donor rows are not exact input prefix')
    _validate_reviews(cfg, child, plan, worker.inherited_prefix_evidence(child,plan,counts['saved']))
    gates=[e for e in events if e['kind']=='checkpoint_gate_satisfied']
    for gate in gates: c._verify_gate_event(gate)
    _verified_inherited_gates(old, events, cfg['expected_child_index'], cfg['expected_saved'])
    return old,events,done,context,closed_saved,closed_calls,child,plan,rows,code


def prepare(config_path):
    config_path=Path(config_path).resolve(); cfg=w.load(config_path)
    root=Path(cfg['root']).resolve(); donor=Path(cfg['donor_root']).resolve()
    w.require(not c.other_collectors(), 'Collector active; offline recovery preparation forbidden')
    w.require(not root.exists() and root!=donor and root not in donor.parents and donor not in root.parents,
              'Independent empty recovery namespace required')
    old,events,done,context,closed_saved,closed_calls,source,plan,rows,code=_read_donor(cfg)
    index=cfg['expected_child_index']; first=old['parts'][len(done)]
    predecessor=Path(context['history_index']['path']).parent
    # All donor material is hashed once before copying the minimum working state.
    inventory={str(p):w.sha_file(p) for p in _files(source)}
    controls=[donor/'campaign.json', donor/'status.json', donor/'technical_stop.json', donor/'Inherited_Review_Obligations.json']
    controls+=sorted((donor/'events').glob('*.json'))
    if old.get('connection_recovery'):
        controls += [Path(old['connection_recovery'][key]['path']) for key in ('provenance','acknowledgment')]
    if old.get('review_recovery'):
        controls += [Path(old['review_recovery'][key]['path']) for key in ('provenance',)]
    controls += [Path(cfg[key]['path']) for key in ('source_review','independent_review')]
    inherited_gates=_verified_inherited_gates(old,events,index,cfg['expected_saved'])
    donor_controls=[c._bound(p) for p in controls]+code
    oldpre=w.load(old['preflight']['path'])
    obligations=dict(oldpre['review_obligations'])
    pending=list(obligations['native_pending_file_bindings'])
    known_pending={entry['path'] for entry in pending}
    for summary_path in sorted(source.glob('checkpoint_*/summary.json')):
        summary=w.load(summary_path); pending_path=summary_path.parent/'pending_source_review_samples.csv'
        w.require(w.sha_file(pending_path)==summary['pending_samples_sha256'] and
                  len(w.readcsv(pending_path))==summary['pending_source_review_sample_count'],
                  'Inherited native review obligation changed')
        if str(pending_path) not in known_pending:
            pending.append({**c._bound(pending_path),'rows':summary['pending_source_review_sample_count'],
                            'summary':c._bound(summary_path)})
            known_pending.add(str(pending_path))
    obligations['native_pending_file_bindings']=pending
    obligations['investigated_donor_obligations']=c._bound(donor/'Inherited_Review_Obligations.json')
    obligations['prior_checkpoint_gates']=[{'selection':e['selection'],'coverage':e['coverage']} for e in events if e['kind']=='checkpoint_gate_satisfied']
    obligations['prior_completed_children']=[e['receipt'] for e in done]
    obligations['inherited_recovery_lineage'] = {
        'connection_recovery': old.get('connection_recovery'),
        'review_recovery': old.get('review_recovery')}
    obligations['investigated_source_gaps'] = [
        {'sample_id': sid, 'research_status': 'NEEDS_JOAQUIN_REVIEW',
         'native_manual_review_status': 'not_reviewed', 'native_qa_status': 'error',
         'source_review': cfg['source_review'], 'independent_review': cfg['independent_review'],
         'retry_authorized': False, 'article_acceptance': False}
        for sid in cfg['source_sample_ids']]
    pre={**oldpre,'source_runtime':str(predecessor), 'review_obligations':obligations,
         'source_bindings':{**oldpre['source_bindings'],'completed_predecessor_context':c._bound(predecessor/'continuation_context.json'),
             'completed_predecessor_receipt':c._bound(predecessor/'remaining_completion_receipt.json') if (predecessor/'remaining_completion_receipt.json').exists() else c._bound(predecessor/'continuous_state.json')},
         'protected_control_bindings':oldpre['protected_control_bindings']+donor_controls,
         'boundary':{'remaining_original_plan_indices':[index,old['parts'][-1]['plan_index']],
                     'reconciled_completed_request_URLs':old['baseline_saved']+closed_saved,
                     'remaining_request_URLs':old['remaining_rows']-closed_saved,
                     'global_identity_records_including_legacy2270':len(w.load_history_index(context['history_index'])),
                     'global_charged_calls':old['baseline_calls']+closed_calls}}
    # Small preparation inputs live adjacent to, not inside, the data root. They
    # are required recovery controls, not a duplicate delivery package.
    control=root.parent/(root.name+'_Preparation')
    w.require(not control.exists(),'Recovery preparation controls already exist; inspect before retry')
    control.mkdir()
    w.write(control,'Source_Preflight.json',pre)
    gates=obligations['prior_checkpoint_gates']
    history=([{'coverage':gates[-1]['coverage']['path'],'sha256':gates[-1]['coverage']['sha256']}] if gates else old['historical_ai_receipts'])
    setup={'root':str(root),'preflight':c._bound(control/'Source_Preflight.json'),
           'max_new_calls':3*pre['boundary']['remaining_request_URLs'],
           'synthetic_fixture':bool(cfg.get('synthetic_fixture')),
           'forecast_growth_multiplier':old['forecast_growth_multiplier'],
           'historical_ai_receipts':history,'source_gap_recovery_preparation':True}
    # Keep the existing upper bound even if this stricter remainder ceiling is lower.
    w.require(setup['max_new_calls']<=old['max_new_calls']-closed_calls,'Recovery would exceed original campaign request budget')
    w.write(control,'Campaign_Config.json',setup)
    c.prepare(control/'Campaign_Config.json')
    m=c._signed(root/'campaign.json','campaign_sha256'); target=c.child_path(m,index)
    target.mkdir(parents=True)
    allowed_top={'continuous_plan.json','queue.csv','known_registry.json','transport_calls.jsonl','transport_state.json'}
    copy_paths=[]
    for p in _files(source):
        rel=p.relative_to(source)
        if rel.parts[0] in {'row_checks','automatic_checks','transport_snapshots'} or (len(rel.parts)==1 and p.name in allowed_top):
            copy_paths.append(p)
        elif rel.parts[0]=='batches' and not any(x in {'backups','review_history'} for x in rel.parts):
            copy_paths.append(p)
    copied={}
    for p in copy_paths:
        dest=target/p.relative_to(source); dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(p,dest)
        w.require(w.sha_file(dest)==inventory[str(p)],'Recovery copy differs')
        copied[str(dest.relative_to(target))]=inventory[str(p)]
    prefix=worker.inherited_prefix_evidence(source,plan,cfg['expected_saved'])
    required=[source/n for n in ('continuous_plan.json','continuous_state.json','safety_halt.json','transport_calls.jsonl','transport_state.json')]
    required += list((source/'halt_receipts').glob('*.json')) + list(source.glob('batches/*/pilot.sqlite'))
    required += [source/'row_checks'/f"{sid}.json" for sid in cfg['source_sample_ids']]
    required += [donor/'campaign.json', donor/'technical_stop.json']
    ack={'schema': ACK_SCHEMA, 'author': 'Kevin', 'target_root':str(target),
         'donor_root':str(source),'donor_campaign_root':str(donor),
         'synthetic_fixture':bool(cfg.get('synthetic_fixture')),
         'expected_child_index':index, 'prefix_rows':cfg['expected_saved'], 'prefix_calls':cfg['expected_calls'],
         'next_sample_id':cfg['next_sample_id'],
         **{key:prefix[key] for key in ('prefix_payload_sha256','prefix_attempts_sha256','prefix_articles_sha256')},
         'donor_bindings':{str(p):w.sha_file(p) for p in required},
         'sources': _source_bindings(source, plan, prefix),
         'source_review':cfg['source_review'], 'independent_review':cfg['independent_review'],
         'meaning':'Only replay of the exact second saved anomaly is acknowledged. All native errors, risk history, missing source bodies and pending actual AI review duties remain unchanged.',
         'research_status':'NEEDS_JOAQUIN_REVIEW', 'human_approval':False,'article_acceptance':False}
    w.write(root,'Inherited_Source_Gap_Acknowledgment.json',ack)
    binding=c._bound(root/'Inherited_Source_Gap_Acknowledgment.json')
    validate_ack(target,plan,binding)
    # Complete the missing partial-batch technical certificate offline in the
    # new namespace, after proving all existing donor exports above.
    closed=worker.close_saved_boundary(target,m['media'],cfg['expected_saved'],
        inherited_source_gap_acknowledgment=binding,install_signal_handlers=False)
    w.require(closed.get('checkpoint_boundary_reached') and closed['result_rows']==cfg['expected_saved'],
              'Offline inherited-prefix closure did not reach the exact saved boundary')
    proof={'schema':SCHEMA,'author':'Kevin','config':c._bound(config_path),'donor_controls':donor_controls,
           'donor_inventory':inventory,'copied_native_files':copied,'donor_child':str(source),'target_child':str(target),
           'native_plan_binding':c._bound(target/'continuous_plan.json'),'acknowledgment':binding,
           'child_index':index,'inherited_rows':cfg['expected_saved'],'inherited_calls':cfg['expected_calls'],
           'baseline_saved':m['baseline_saved'],'baseline_calls':m['baseline_calls'],
           'inherited_checkpoint_gates':inherited_gates,
           'inherited_recovery_lineage':{'campaign':c._bound(donor/'campaign.json'),
               'connection_recovery':old.get('connection_recovery'), 'review_recovery':old.get('review_recovery')},
           'first_new_sample_id':cfg['next_sample_id'],'offline_prefix_closed':True,'human_approval':False,
           'article_acceptance':False,'remaining_original_calls_ceiling':old['max_new_calls']-closed_calls}
    w.write(root,'Recovery_Provenance.json',proof)
    m.pop('campaign_sha256'); m.pop('source_gap_recovery_pending')
    m['source_gap_recovery']={'provenance':c._bound(root/'Recovery_Provenance.json'),'acknowledgment':binding,
                              'child_index':index,'inherited_checkpoint_gates':inherited_gates}
    m['campaign_sha256']=w.digest(m); w.write(root,'campaign.json',m)
    # Initial prepared event cannot certify another manifest; preserve it as
    # preparation history and bind the final manifest explicitly in a new event.
    c.event(root,'investigated_source_gap_recovery_prepared',campaign_sha256=m['campaign_sha256'],
        provenance=m['source_gap_recovery']['provenance'],inherited_saved=cfg['expected_saved'],
        inherited_calls=cfg['expected_calls'],new_network_calls=0)
    verify(m,full=True)
    return c._state(root,'prepared_offline_not_started',new_saved=cfg['expected_saved'],new_calls=cfg['expected_calls'],
                    original_plan_saved=m['baseline_saved']+cfg['expected_saved'],remaining=m['remaining_rows']-cfg['expected_saved'])


def verify(m, *, full=False):
    bound=m['source_gap_recovery']; c._verify(bound['provenance']); c._verify(bound['acknowledgment'])
    doc=w.load(bound['provenance']['path']); c._verify(doc['config'])
    w.require(doc['schema']==SCHEMA and doc['acknowledgment']==bound['acknowledgment'] and
              doc['child_index']==bound['child_index'] and doc['baseline_saved']==m['baseline_saved'] and
              doc['baseline_calls']==m['baseline_calls'], 'Source-gap provenance differs from campaign')
    for b in doc['donor_controls']: c._verify(b)
    cfg=w.load(doc['config']['path'])
    w.require(str(Path(cfg['root']).resolve())==m['root'] and
              bool(cfg.get('synthetic_fixture'))==m['synthetic_fixture'] and
              doc['target_child']==str(c.child_path(m,cfg['expected_child_index'])) and
              doc['child_index']==cfg['expected_child_index'] and
              doc['inherited_rows']==cfg['expected_saved'] and doc['inherited_calls']==cfg['expected_calls'],
              'Source-gap successor namespace, type, child or boundary differs')
    if not m['synthetic_fixture']:
        w.require(m['baseline_saved']==128000 and m['baseline_calls']==128061 and
                  m['remaining_rows']==2531 and [p['plan_index'] for p in m['parts']]==[65,66],
                  'Production successor scope differs from original remaining partition')
    donor=c._signed(Path(cfg['donor_root'])/'campaign.json','campaign_sha256')
    lineage=doc['inherited_recovery_lineage']
    c._verify(lineage['campaign'])
    w.require(lineage['campaign']==c._bound(Path(cfg['donor_root'])/'campaign.json') and
              lineage['connection_recovery']==donor.get('connection_recovery') and
              lineage['review_recovery']==donor.get('review_recovery'), 'Prior recovery lineage differs')
    if donor.get('connection_recovery'): connection.verify(donor,full=False)
    if donor.get('review_recovery'): review_recovery.verify(donor,full=False)
    inherited=_verified_inherited_gates(donor,c.events(cfg['donor_root']),doc['child_index'],doc['inherited_rows'])
    w.require(inherited==doc['inherited_checkpoint_gates']==bound['inherited_checkpoint_gates'],
              'Inherited source-reading gates differ')
    c._verify(doc['native_plan_binding'])
    validate_ack(Path(doc['target_child']),w.load(doc['native_plan_binding']['path']),bound['acknowledgment'])
    if full:
        for path,sha in doc['donor_inventory'].items():
            w.require(w.sha_file(path)==sha,'Immutable donor evidence changed: '+path)
    return doc


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--config',required=True,type=Path)
    args=p.parse_args(argv)
    print(json.dumps(prepare(args.config),indent=2))

if __name__=='__main__': main()

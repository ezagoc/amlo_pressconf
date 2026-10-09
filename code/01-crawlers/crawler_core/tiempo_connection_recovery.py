"""Kevin: evidence-bound successors for the investigated child36 and child42 halts.

Offline preparation only. Old source trees remain immutable. This adapter never
retries the failed input or relaxes the handling of a new transport failure.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import sqlite3

from . import tiempo_continuous_v5 as w
from . import tiempo_remaining_campaign as c
from . import tiempo_resumable_worker as worker
from . import tiempo_stage_review as review

SCHEMA = 'tiempo-connection-stop-successor-v1'
PRODUCTION = ({
    'expected_child_index': 36, 'expected_saved': 391, 'expected_calls': 392,
    'failed_sample_id': 'TC5_495573', 'next_sample_id': 'TC5_498773',
    'donor_master_halt_sha256': '122848c71868449625b2752cb1a0854985d6a2813d16a1402d0aeae09cb5c2e1',
    'donor_native_halt_sha256': '6a4df85fbcba652c27188de7a78c8828ee501972bd3459749d4745e3f998823f',
}, {
    'expected_child_index': 42, 'expected_saved': 1590, 'expected_calls': 1591,
    'failed_sample_id': 'TC5_13912', 'next_sample_id': 'TC5_14168',
    'donor_master_halt_sha256': '4e4dc96a3b01dfe5dcb803c2bb7da593534c124a194bee8270d13ad4c9126029',
    'donor_native_halt_sha256': 'ebcd7f9f26bf7466be2095134f769ab4c750de92eda6afcd118a0cd9409e6d4f',
})


def _files(root):
    files=[]
    for p in sorted(Path(root).rglob('*')):
        w.require(not p.is_symlink(), 'Recovery evidence must not contain symlinks')
        if p.is_file() and p.name not in {'.pilot.lock', '.DS_Store'}:
            w.require(not (p.stat().st_flags & 0x40000000), 'Required recovery file is online-only: '+str(p))
            files.append(p)
    return files


def _donor_code_binding(repo, wanted):
    base=Path(repo)/'code/01-crawlers'
    aliases={'v5_worker':'crawler_core/tiempo_continuous_v5.py',
             'v5_scheduler':'crawler_core/tiempo_scheduler_v5.py',
             'v5_cli':'scripts/run_tiempo_scheduler_v5.py',
             'remaining_cli':'scripts/run_tiempo_remaining.py',
             'review_publish_cli':'scripts/publish_tiempo_review_receipt.py'}
    actual={key:w.sha_file(base/aliases.get(key, 'crawler_core/'+key)) for key in wanted}
    w.require(actual==wanted, 'Original frozen code binding changed')
    return [c._bound(base/aliases.get(key, 'crawler_core/'+key)) for key in wanted]


def _read_donor(cfg):
    donor=Path(cfg['donor_root']).resolve()
    w.require(w.sha_file(donor/'campaign.json')==cfg['donor_campaign_sha256'], 'Donor campaign changed')
    old=c._signed(donor/'campaign.json','campaign_sha256')
    w.require(old['root']==str(donor) and old['schema']==c.SCHEMA, 'Wrong donor campaign')
    synthetic=bool(cfg.get('synthetic_fixture'))
    w.require(synthetic==bool(old['synthetic_fixture']), 'Synthetic/live donor mismatch')
    if not synthetic:
        w.require(any(all(cfg.get(k)==v for k,v in case.items()) for case in PRODUCTION),
                  'Only the specifically investigated production halts are authorized')
    code=_donor_code_binding(cfg['donor_code_root'],old['program_sha256'])
    for key in ('config_source','preflight','prepared_manifest','source_context','source_ledger','registry','obligations','queue'):
        c._verify(old[key])
    for p in old['parts']: c._verify(p)
    c._verify_old(w.load(old['preflight']['path']))
    if old.get('connection_recovery'):
        verify(old)
    events=c.events(donor)
    stops=[e for e in events if e['kind']=='technical_stop']
    w.require(len(stops)==1 and stops[0]['evidence']==c._bound(donor/'technical_stop.json'), 'Donor stop event mismatch')
    done,context,closed_saved,closed_calls=c._completed(old,events)
    part=old['parts'][len(done)]
    w.require(part['plan_index']==cfg['expected_child_index'], 'Wrong original child index')
    child=c.child_path(old,part['plan_index'])
    plan,registry=w.load_plan(child,old['media'])
    counts=c._counts(child,plan)
    w.require(counts=={'saved':cfg['expected_saved'],'calls':cfg['expected_calls'],
              'pending_native_attempts':0,'open_transport':False}, 'Donor counts or transport state changed')
    w.require(plan['seed_context']==context, 'Donor predecessor context differs')
    w.require(w.sha_file(donor/'technical_stop.json')==cfg['donor_master_halt_sha256'] and
              w.sha_file(child/'safety_halt.json')==cfg['donor_native_halt_sha256'], 'Specific halt evidence changed')
    state=w.load(child/'continuous_state.json'); halt=w.load(child/'safety_halt.json')
    w.require(state['status']=='halted_no_automatic_resume' and state['halt_sha256']==cfg['donor_native_halt_sha256'] and
              halt['reason']=='critical_source_or_access_failure' and halt['sample_id']==cfg['failed_sample_id'], 'Wrong native failure')
    queue=w.readcsv(child/'queue.csv')
    w.require(queue[counts['saved']-1]['sample_id']==cfg['failed_sample_id'] and
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
    gates=[e for e in events if e['kind']=='checkpoint_gate_satisfied']
    for gate in gates: c._verify_gate_event(gate)
    _verified_inherited_gates(old, events, cfg['expected_child_index'], cfg['expected_saved'])
    return old,events,done,context,closed_saved,closed_calls,child,plan,rows,code


def _verified_inherited_gates(donor, events, index, saved):
    """Reuse only signed, sealed gates strictly inside this saved child prefix."""
    gates = [e for e in events if e['kind'] == 'checkpoint_gate_satisfied' and e['index'] == index]
    required = list(range(400, saved + 1, 400))
    w.require([e['rows'] for e in gates] == required,
              'Inherited child is missing or has unexpected prior review gates')
    child = c.child_path(donor, index)
    native_plan = w.load(child / 'continuous_plan.json')
    for gate in gates:
        c._verify_gate_event(gate)
        selection = w.load(gate['selection']['path'])
        snap = selection['snapshot']
        w.require(snap['child'] == str(child) and
                  snap['plan_sha256'] == native_plan['plan_sha256'] and
                  snap['checkpoint_rows'] == gate['rows'],
                  'Inherited source-reading gate belongs to another child or boundary')
    return gates


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
    obligations['inherited_recovery_lineage']=old.get('connection_recovery')
    prior_failures=list(obligations.get('unresolved_failures',[]))
    if obligations.get('unresolved_failure') and obligations['unresolved_failure'] not in prior_failures:
        prior_failures.append(obligations['unresolved_failure'])
    obligations['unresolved_failure']={'sample_id':cfg['failed_sample_id'],'status':'critical_failure_unresolved',
        'native_manual_review_status':'not_reviewed','retry_authorized':False,'donor_native_halt':c._bound(source/'safety_halt.json')}
    obligations['unresolved_failures']=[*prior_failures,obligations['unresolved_failure']]
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
           'historical_ai_receipts':history,'connection_recovery_preparation':True}
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
    failure=rows[-1]; bid=next(b['batch_id'] for b in plan['batches'] if failure['sample_id'] in b['sample_ids'])
    payload=prefix['payloads'][-1]
    required=[source/n for n in ('continuous_plan.json','continuous_state.json','safety_halt.json','transport_calls.jsonl','transport_state.json')]
    required += list((source/'halt_receipts').glob('*.json')) + list(source.glob('batches/*/pilot.sqlite'))
    required += [source/'row_checks'/f"{failure['sample_id']}.json",donor/'technical_stop.json']
    ack={'schema':'tiempo-inherited-terminal-failure-v1','author':'Kevin','target_root':str(target),
         'donor_root':str(source),'donor_campaign_root':str(donor),'synthetic_fixture':bool(cfg.get('synthetic_fixture')),
         'prefix_rows':cfg['expected_saved'],'prefix_calls':cfg['expected_calls'],
         'prefix_payload_sha256':prefix['prefix_payload_sha256'],'prefix_attempts_sha256':prefix['prefix_attempts_sha256'],
         'prefix_articles_sha256':prefix['prefix_articles_sha256'],
         'donor_bindings':{str(p):w.sha_file(p) for p in required},
         'failure':{'batch_id':bid,'sample_id':failure['sample_id'],'url':failure['url'],
                    'attempt_id':failure['attempt_id'],'payload_sha256':hashlib.sha256(payload.encode()).hexdigest(),
                    'snapshot_sha256':failure['snapshot_sha256'],
                    'row_check_record_sha256':w.digest(w.load(source/'row_checks'/f"{failure['sample_id']}.json")['record'])},
         'meaning':'Only this investigated retained failure may be replayed for continuation; it remains unresolved and is never retried by this acknowledgment.',
         'human_approval':False,'article_acceptance':False}
    w.write(root,'Inherited_Failure_Acknowledgment.json',ack)
    binding=c._bound(root/'Inherited_Failure_Acknowledgment.json')
    worker.validated_inherited_failure_ack(target,plan,binding)
    # Complete the missing partial-batch technical certificate offline in the
    # new namespace, after proving all existing donor exports above.
    closed=worker.close_saved_boundary(target,m['media'],cfg['expected_saved'],
        inherited_failure_acknowledgment=binding,install_signal_handlers=False)
    w.require(closed.get('checkpoint_boundary_reached') and closed['result_rows']==cfg['expected_saved'],
              'Offline inherited-prefix closure did not reach the exact saved boundary')
    proof={'schema':SCHEMA,'author':'Kevin','config':c._bound(config_path),'donor_controls':donor_controls,
           'donor_inventory':inventory,'copied_native_files':copied,'donor_child':str(source),'target_child':str(target),
           'native_plan_binding':c._bound(target/'continuous_plan.json'),'acknowledgment':binding,
           'child_index':index,'inherited_rows':cfg['expected_saved'],'inherited_calls':cfg['expected_calls'],
           'baseline_saved':m['baseline_saved'],'baseline_calls':m['baseline_calls'],
           'inherited_checkpoint_gates':inherited_gates,
           'inherited_recovery_lineage':({'campaign':c._bound(donor/'campaign.json'),
               'connection_recovery':old['connection_recovery']} if old.get('connection_recovery') else None),
           'first_new_sample_id':cfg['next_sample_id'],'offline_prefix_closed':True,'human_approval':False,
           'article_acceptance':False,'remaining_original_calls_ceiling':old['max_new_calls']-closed_calls}
    w.write(root,'Recovery_Provenance.json',proof)
    m.pop('campaign_sha256'); m.pop('connection_recovery_pending')
    m['connection_recovery']={'provenance':c._bound(root/'Recovery_Provenance.json'),'acknowledgment':binding,
                              'child_index':index,'inherited_checkpoint_gates':inherited_gates}
    m['campaign_sha256']=w.digest(m); w.write(root,'campaign.json',m)
    # Initial prepared event cannot certify another manifest; preserve it as
    # preparation history and bind the final manifest explicitly in a new event.
    c.event(root,'investigated_connection_recovery_prepared',campaign_sha256=m['campaign_sha256'],
        provenance=m['connection_recovery']['provenance'],inherited_saved=cfg['expected_saved'],
        inherited_calls=cfg['expected_calls'],new_network_calls=0)
    verify(m,full=True)
    return c._state(root,'prepared_offline_not_started',new_saved=cfg['expected_saved'],new_calls=cfg['expected_calls'],
                    original_plan_saved=m['baseline_saved']+cfg['expected_saved'],remaining=m['remaining_rows']-cfg['expected_saved'])


def verify(m, *, full=False, _ancestors=()):
    w.require(m['root'] not in _ancestors, 'Cyclic recovery provenance')
    ancestors=(*_ancestors,m['root'])
    bound=m['connection_recovery']; c._verify(bound['provenance']); c._verify(bound['acknowledgment'])
    doc=w.load(bound['provenance']['path']); c._verify(doc['config'])
    w.require(doc['schema']==SCHEMA and doc['acknowledgment']==bound['acknowledgment'] and
              doc['child_index']==bound['child_index'] and doc['baseline_saved']==m['baseline_saved'] and
              doc['baseline_calls']==m['baseline_calls'],'Recovery provenance differs from campaign')
    for b in doc['donor_controls']: c._verify(b)
    cfg=w.load(doc['config']['path'])
    donor=c._signed(Path(cfg['donor_root'])/'campaign.json','campaign_sha256')
    w.require(doc.get('inherited_checkpoint_gates',[])==bound.get('inherited_checkpoint_gates',[]),
              'Inherited checkpoint gates differ from recovery provenance')
    donor_events=c.events(cfg['donor_root'])
    inherited=_verified_inherited_gates(donor,donor_events,doc['child_index'],doc['inherited_rows'])
    w.require(inherited==doc.get('inherited_checkpoint_gates',[]),
              'Inherited gates differ from original signed donor events')
    lineage=doc.get('inherited_recovery_lineage')
    w.require(bool(lineage)==bool(donor.get('connection_recovery')), 'Recovery lineage is missing or spurious')
    if lineage:
        c._verify(lineage['campaign'])
        w.require(lineage['campaign']==c._bound(Path(cfg['donor_root'])/'campaign.json') and
                  lineage['connection_recovery']==donor['connection_recovery'] and
                  donor['connection_recovery']['child_index']<doc['child_index'],
                  'Inherited prior recovery binding differs')
        verify(donor,full=False,_ancestors=ancestors)
    c._verify(doc['native_plan_binding'])
    plan=w.load(doc['native_plan_binding']['path'])
    worker.validated_inherited_failure_ack(Path(doc['target_child']),plan,bound['acknowledgment'])
    if full:
        for path,sha in doc['donor_inventory'].items():
            w.require(w.sha_file(path)==sha,'Immutable donor recovery evidence changed: '+path)
    return doc


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--config',required=True,type=Path)
    args=p.parse_args(argv)
    print(json.dumps(prepare(args.config),indent=2))

if __name__=='__main__': main()

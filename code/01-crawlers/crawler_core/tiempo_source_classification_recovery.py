"""Kevin: preserve the exact stopped659 prefix and version the feature policy.

The donor and all native records/plans/checks stay unchanged. The separately
bound classifier explains source gaps by evidence, never by sample-ID whitelist.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys

from . import tiempo_continuous_v5 as w
from . import tiempo_remaining_campaign as c
from . import tiempo_resumable_worker as worker
from . import tiempo_connection_recovery as connection
from . import tiempo_source_gap_recovery as previous
from . import tiempo_source_classification_policy as policy

SCHEMA='tiempo-source-classification-successor-v8'
PRODUCTION={'expected_child_index':65,'expected_saved':659,'expected_calls':661,
    'next_sample_id':'TC5_124998',
    'donor_campaign_sha256':'0d4b461aa1599926b462efd70430f75737f34d7e0ce151ee8972ea0a48cda0b4',
    'donor_master_halt_sha256':'68164edb0ddf37638af77dcefe0266afe123bad1a6b03eabb9b2211fa24a4495',
    'donor_native_halt_sha256':'1874a9a08e2d3297de5b19c936136642c14f05d02010e4982610e6dcb12382d4'}
PRODUCTION_SOURCE_IDS=('TC5_509968','TC5_521168','TC5_73693')

PREFIX_KEYS=('prefix_payload_sha256','prefix_attempts_sha256','prefix_articles_sha256')

# A changed helper cannot validate an old versioned policy in-process. The
# exact donor code is checked before and after this read-only, bytecode-disabled
# subprocess. It only calls read_bound; it never invokes run, inspect or export.
_FROZEN_VERIFY = '''import json, sys
sys.path.insert(0, sys.argv[1])
from crawler_core import tiempo_remaining_campaign as c
m, events = c.read_bound(sys.argv[2], full=True)
assert m['campaign_sha256'] == sys.argv[3]
print(json.dumps({'campaign_sha256':m['campaign_sha256'],
    'source_classification_recovery':m['source_classification_recovery'],
    'network_calls':0,'production_writes':0}))
'''


def _verify_prior_classification(old, code_root):
    if not old.get('source_classification_recovery'):return None
    before=connection._donor_code_binding(code_root,old['program_sha256'])
    result=subprocess.run([sys.executable,'-B','-c',_FROZEN_VERIFY,
        str(Path(code_root).resolve()/'code/01-crawlers'),old['root'],old['campaign_sha256']],
        capture_output=True,text=True,timeout=120,cwd=code_root)
    w.require(result.returncode==0,'Frozen donor classification validation failed: '+result.stderr[-2000:])
    expected={'campaign_sha256':old['campaign_sha256'],
        'source_classification_recovery':old['source_classification_recovery'],
        'network_calls':0,'production_writes':0}
    w.require(json.loads(result.stdout)==expected,'Frozen donor validator identity/result mismatch')
    w.require(connection._donor_code_binding(code_root,old['program_sha256'])==before,
              'Frozen donor code changed during its read-only validation')
    return expected


def _source_review(cfg,child,prefix):
    """Bind the three investigated saved sources; never award gate-reading credit."""
    c._verify(cfg['source_review']);review=w.load(cfg['source_review']['path'])
    w.require(review.get('author')=='Kevin' and review.get('human_approval') is False and
              review.get('article_acceptance') is False and review.get('new_checkpoint_reading_credit')==0,
              'Source investigation cannot assert new checkpoint or human approval')
    entries=review.get('records',[]);ids=[x['sample_id'] for x in entries]
    expected=list(PRODUCTION_SOURCE_IDS) if not cfg.get('synthetic_fixture') else cfg['source_sample_ids']
    w.require(ids==expected and len(ids)==len(set(ids)),'Source investigation does not match the exact fault set')
    saved={x['row']['sample_id']:x for x in prefix['rows']};result=[]
    for item in entries:
        sid=item['sample_id'];w.require(sid in saved,'Investigated source is outside saved prefix')
        native=saved[sid];row=native['row'];batch=child/'batches'/native['batch_id']
        raw=batch/row['snapshot_path'];check=child/'row_checks'/(sid+'.json')
        w.require(item['raw']==c._bound(raw) and item['native_row_check']==c._bound(check) and
                  item['raw']['sha256']==row['snapshot_sha256'],'Source investigation does not bind original raw and diagnostic')
        c._verify(item['reading_evidence']);record=w.load(check)['record']
        w.require(record['sample_id']==sid and record['fields_sha256']==w.fields_digest(row) and
                  record.get('unexplained_flags') and row.get('main_text') and not row.get('error'),
                  'Investigated text source/native flags differ')
        # Payload digest uses the exact stored string rather than reserialization.
        ordinal=[x['row']['sample_id'] for x in prefix['rows']].index(sid)
        result.append({**item,'payload_sha256':hashlib.sha256(prefix['payloads'][ordinal].encode()).hexdigest(),
                       'fields_sha256':record['fields_sha256'],'attempt_id':row['attempt_id']})
    return result


def _read_donor(cfg):
    donor=Path(cfg['donor_root']).resolve()
    w.require(w.sha_file(donor/'campaign.json')==cfg['donor_campaign_sha256'],'Donor campaign changed')
    old=c._signed(donor/'campaign.json','campaign_sha256')
    w.require(old['root']==str(donor) and old['schema']==c.SCHEMA and
              bool(cfg.get('synthetic_fixture'))==old['synthetic_fixture'],'Wrong donor identity/type')
    if not old['synthetic_fixture']:
        w.require(all(cfg.get(k)==v for k,v in PRODUCTION.items()) and old.get('source_classification_recovery'),
                  'Only the authorized659 source-classification recovery is supported')
    code=connection._donor_code_binding(cfg['donor_code_root'],old['program_sha256'])
    for key in ('config_source','preflight','prepared_manifest','source_context','source_ledger','registry','obligations','queue'):
        c._verify(old[key])
    for part in old['parts']:c._verify(part)
    c._verify_old(w.load(old['preflight']['path']))
    if old.get('source_gap_recovery'):previous.verify(old)
    _verify_prior_classification(old,cfg['donor_code_root'])
    events=c.events(donor);stops=[e for e in events if e['kind']=='technical_stop']
    w.require(len(stops)==1 and events[-1]==stops[0] and stops[0]['evidence']==c._bound(donor/'technical_stop.json'),
              'Donor latest event must remain the exact technical stop')
    done,context,closed_saved,closed_calls=c._completed(old,events)
    part=old['parts'][len(done)];index=part['plan_index'];child=c.child_path(old,index)
    plan,_=w.load_plan(child,old['media']);counts=c._counts(child,plan)
    w.require(index==cfg['expected_child_index'] and plan['seed_context']==context and
              counts=={'saved':cfg['expected_saved'],'calls':cfg['expected_calls'],'pending_native_attempts':0,'open_transport':False},
              'Donor continuation/count/open-request evidence differs')
    w.require(w.sha_file(donor/'technical_stop.json')==cfg['donor_master_halt_sha256'] and
              w.sha_file(child/'safety_halt.json')==cfg['donor_native_halt_sha256'],'Donor specific halt changed')
    halt=w.load(child/'safety_halt.json');state=w.load(child/'continuous_state.json');master=w.load(donor/'technical_stop.json')
    queue=w.readcsv(child/'queue.csv')
    expected_reason=('three_unexplained_rows_in_rolling80' if not old['synthetic_fixture'] else
                     cfg.get('expected_halt_reason','unclassified_source_gap' if old.get('source_classification_recovery') else 'two_consecutive_same_family_anomalies'))
    w.require(halt['reason']==expected_reason and
              halt['sample_id']==queue[cfg['expected_saved']-1]['sample_id'] and
              queue[cfg['expected_saved']]['sample_id']==cfg['next_sample_id'] and
              state['status']=='halted_no_automatic_resume' and state['halt_sha256']==cfg['donor_native_halt_sha256'] and
              master['reason']=='native_worker_stopped' and master['native_result']['halt_sha256']==state['halt_sha256'],
              'Donor halt, state or next frozen position differs')
    if not old['synthetic_fixture']:
        w.require(old['baseline_saved']+closed_saved==128000 and old['baseline_calls']+closed_calls==128061 and
                  old['remaining_rows']-closed_saved==2531 and old['parts'][-1]['plan_index']==66 and
                  plan['row_count']==2000,'Frozen recovery scope differs')
    # Validate original exports before any destination or regeneration is created.
    for batch in plan['batches']:
        rows=w._rows(child,batch)
        if not rows:continue
        b=child/'batches'/batch['batch_id'];manifest=w.load(b/'export_manifest.json')
        items,h=w.pilot.load_input(child/batch['input_path']);preview=worker._export_preview(b,items,h)
        w.require(manifest['result_rows']==len(rows) and manifest['files']==preview['files'],'Donor export readback mismatch')
        for name,meta in manifest['files'].items():w.require(w.sha_file(b/name)==meta['sha256'],'Donor export bytes changed')
    prefix=worker.inherited_prefix_evidence(child,plan,cfg['expected_saved'])
    w.require(prefix['total_rows']==cfg['expected_saved'],'Donor prefix count differs')
    connection._verified_inherited_gates(old,events,index,cfg['expected_saved'])
    if not old['synthetic_fixture'] or cfg.get('source_review'):
        _source_review(cfg,child,prefix)
    return old,events,done,context,closed_saved,closed_calls,child,plan,prefix,code


def prepare(config_path):
    config_path=Path(config_path).resolve();cfg=w.load(config_path)
    root=Path(cfg['root']).resolve();donor=Path(cfg['donor_root']).resolve()
    w.require(not c.other_collectors(),'Collector active; offline successor preparation forbidden')
    w.require(not root.exists() and root!=donor and root not in donor.parents and donor not in root.parents,
              'New disjoint source-classification runtime required')
    old,events,done,context,closed_saved,closed_calls,source,plan,prefix,code=_read_donor(cfg)
    index=cfg['expected_child_index'];inherited_gates=connection._verified_inherited_gates(old,events,index,cfg['expected_saved'])
    predecessor=Path(context['history_index']['path']).parent
    inventory={str(p):w.sha_file(p) for p in connection._files(source)}
    controls=[donor/'campaign.json',donor/'status.json',donor/'technical_stop.json',donor/'Inherited_Review_Obligations.json']
    controls+=sorted((donor/'events').glob('*.json'))
    for gate in inherited_gates:controls += [Path(gate[key]['path']) for key in ('selection','coverage')]
    if cfg.get('source_review'):controls.append(Path(cfg['source_review']['path']))
    if old.get('source_gap_recovery'):
        controls += [Path(old['source_gap_recovery'][key]['path']) for key in ('provenance','acknowledgment')]
    prior_decisions=[]
    if old.get('source_classification_recovery'):
        controls += [Path(old['source_classification_recovery'][key]['path']) for key in ('provenance','policy')]
        prior_decisions=[c._bound(p) for p in sorted((source/'source_classifications').glob('*.json'))]
        expected_ids={x['row']['sample_id'] for x in prefix['rows'] if x['row'].get('error')=='missing_body' or
            'missing_body' in w.load(source/'row_checks'/(x['row']['sample_id']+'.json'))['record'].get('automatic_flags',[])}
        w.require({w.load(b['path'])['sample_id'] for b in prior_decisions}==expected_ids and
                  len(prior_decisions)==len(expected_ids),'Prior classification decisions are incomplete or duplicated')
        controls += [Path(b['path']) for b in prior_decisions]
    bound_controls=[c._bound(p) for p in controls]+code
    oldpre=w.load(old['preflight']['path']);obligations=dict(oldpre['review_obligations'])
    obligations['investigated_donor_obligations']=c._bound(donor/'Inherited_Review_Obligations.json')
    if old.get('source_gap_recovery'):
        obligations['inherited_source_gap_recovery']=old['source_gap_recovery']
    if old.get('source_classification_recovery'):
        obligations['inherited_source_classification_recovery']=old['source_classification_recovery']
    pending=list(obligations['native_pending_file_bindings']);seen={b['path'] for b in pending}
    for summary_path in source.glob('checkpoint_*/summary.json'):
        summary=w.load(summary_path);p=summary_path.parent/'pending_source_review_samples.csv'
        w.require(w.sha_file(p)==summary['pending_samples_sha256'] and len(w.readcsv(p))==summary['pending_source_review_sample_count'],
                  'Prior pending-review obligation changed')
        if str(p) not in seen:pending.append({**c._bound(p),'rows':summary['pending_source_review_sample_count'],'summary':c._bound(summary_path)})
    obligations['native_pending_file_bindings']=pending
    obligations['source_classification_policy_change']='Strict UTF-8 representation corrections retain native text, errors and flags and remain separate article candidates, never source gaps; prior actual AI gates are inherited with zero new reading credit. Strict feature-recognized empty article shells receive a separate source_unavailable outcome; native error, original flags and all required actual AI samples remain. Unclassified missing-body candidates stop immediately.'
    pre={**oldpre,'source_runtime':str(predecessor),'review_obligations':obligations,
        'source_bindings':{**oldpre['source_bindings'],'completed_predecessor_context':c._bound(predecessor/'continuation_context.json')},
        'protected_control_bindings':oldpre['protected_control_bindings']+bound_controls,
        'boundary':{'remaining_original_plan_indices':[index,old['parts'][-1]['plan_index']],
                    'reconciled_completed_request_URLs':old['baseline_saved']+closed_saved,
                    'remaining_request_URLs':old['remaining_rows']-closed_saved,
                    'global_identity_records_including_legacy2270':len(w.load_history_index(context['history_index'])),
                    'global_charged_calls':old['baseline_calls']+closed_calls}}
    control=root.parent/(root.name+'_Preparation');w.require(not control.exists(),'Preparation controls already exist')
    control.mkdir();w.write(control,'Source_Preflight.json',pre)
    setup={'root':str(root),'preflight':c._bound(control/'Source_Preflight.json'),
        'max_new_calls':3*pre['boundary']['remaining_request_URLs'],'synthetic_fixture':old['synthetic_fixture'],
        'forecast_growth_multiplier':old['forecast_growth_multiplier'],'historical_ai_receipts':([{'coverage':inherited_gates[-1]['coverage']['path'],'sha256':inherited_gates[-1]['coverage']['sha256']}] if inherited_gates else old['historical_ai_receipts']),
        'source_classification_preparation':True}
    w.require(setup['max_new_calls']<=old['max_new_calls']-closed_calls,'Successor exceeds original request ceiling')
    w.write(control,'Campaign_Config.json',setup);c.prepare(control/'Campaign_Config.json')
    m=c._signed(root/'campaign.json','campaign_sha256');target=c.child_path(m,index);target.mkdir(parents=True)
    allowed={'continuous_plan.json','queue.csv','known_registry.json','transport_calls.jsonl','transport_state.json'};copied={}
    for p in connection._files(source):
        rel=p.relative_to(source)
        if not (rel.parts[0] in {'row_checks','automatic_checks','transport_snapshots'} or
                len(rel.parts)==1 and p.name in allowed or
                rel.parts[0]=='batches' and not any(x in {'backups','review_history'} for x in rel.parts)):continue
        dest=target/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
        w.require(w.sha_file(dest)==inventory[str(p)],'Copied native evidence differs');copied[str(rel)]=inventory[str(p)]
    imported=worker.inherited_prefix_evidence(target,plan,cfg['expected_saved'])
    w.require(all(prefix[k]==imported[k] for k in PREFIX_KEYS),'Copied native SQL/attempt prefix differs')
    bound_policy=policy.create_policy(root,[p['plan_index'] for p in m['parts']],m['synthetic_fixture'])
    closed=worker.close_saved_boundary(target,m['media'],cfg['expected_saved'],
        source_classification_policy=bound_policy,install_signal_handlers=False)
    w.require(closed.get('checkpoint_boundary_reached') and closed['result_rows']==cfg['expected_saved'],
              'Source classification could not safely replay the imported prefix; preserve stopped successor')
    summary=target/'source_classification_summaries'/f"saved_{cfg['expected_saved']:08d}.json"
    proof={'schema':SCHEMA,'author':'Kevin','config':c._bound(config_path),'policy':bound_policy,
        'donor_controls':bound_controls,'donor_inventory':inventory,'copied_native_files':copied,
        'donor_child':str(source),'target_child':str(target),'native_plan':c._bound(target/'continuous_plan.json'),
        'donor_campaign':c._bound(donor/'campaign.json'),'prior_source_gap_recovery':old.get('source_gap_recovery'),
        'prior_source_classification_recovery':old.get('source_classification_recovery'),
        'prior_classification_decisions':prior_decisions,'inherited_checkpoint_gates':inherited_gates,
        'source_review':cfg.get('source_review'),
        'investigated_sources':_source_review(cfg,source,prefix) if cfg.get('source_review') else [],
        'donor_transport_ledger':c._bound(source/'transport_calls.jsonl'),
        'prefix':{k:prefix[k] for k in PREFIX_KEYS},'child_index':index,'inherited_rows':cfg['expected_saved'],
        'inherited_calls':cfg['expected_calls'],'baseline_saved':m['baseline_saved'],'baseline_calls':m['baseline_calls'],
        'first_new_sample_id':cfg['next_sample_id'],'derived_prefix_summary':c._bound(summary),
        'new_network_calls':0,'new_actual_ai_read_count':0,'human_approval':False,'article_acceptance':False}
    w.write(root,'Classification_Recovery_Provenance.json',proof)
    m.pop('campaign_sha256');m.pop('source_classification_pending')
    m['source_classification_recovery']={'provenance':c._bound(root/'Classification_Recovery_Provenance.json'),
                                      'policy':bound_policy,'child_index':index,'inherited_checkpoint_gates':inherited_gates}
    m['campaign_sha256']=w.digest(m);w.write(root,'campaign.json',m)
    c.event(root,'source_classification_recovery_prepared',campaign_sha256=m['campaign_sha256'],
        provenance=m['source_classification_recovery']['provenance'],inherited_saved=cfg['expected_saved'],
        inherited_calls=cfg['expected_calls'],new_network_calls=0,policy_change_explicit=True)
    verify(m,full=True)
    return c._state(root,'prepared_offline_not_started',new_saved=cfg['expected_saved'],new_calls=cfg['expected_calls'],
        original_plan_saved=m['baseline_saved']+cfg['expected_saved'],remaining=m['remaining_rows']-cfg['expected_saved'])


def verify(m,*,full=False):
    bound=m['source_classification_recovery'];c._verify(bound['provenance']);c._verify(bound['policy'])
    doc=w.load(bound['provenance']['path']);c._verify(doc['config']);cfg=w.load(doc['config']['path'])
    w.require(doc['schema']==SCHEMA and doc['policy']==bound['policy'] and doc['child_index']==bound['child_index']==cfg['expected_child_index'] and
              doc['target_child']==str(c.child_path(m,doc['child_index'])) and str(Path(cfg['root']).resolve())==m['root'] and
              m['synthetic_fixture']==bool(cfg.get('synthetic_fixture')) and doc['inherited_rows']==cfg['expected_saved'] and
              doc['inherited_calls']==cfg['expected_calls'] and doc['baseline_saved']==m['baseline_saved'] and
              doc['baseline_calls']==m['baseline_calls'],'Source-classification successor binding differs')
    if not m['synthetic_fixture']:
        w.require(all(cfg.get(k)==v for k,v in PRODUCTION.items()) and m['baseline_saved']==128000 and
                  m['baseline_calls']==128061 and m['remaining_rows']==2531 and
                  [p['plan_index'] for p in m['parts']]==[65,66] and doc['prior_source_classification_recovery'],
                  'Production659 recovery scope differs')
    for binding in doc['donor_controls']:c._verify(binding)
    c._verify(doc['donor_campaign']);donor=c._signed(doc['donor_campaign']['path'],'campaign_sha256')
    w.require(donor.get('source_gap_recovery')==doc['prior_source_gap_recovery'],'Previous recovery lineage changed')
    if donor.get('source_gap_recovery'):previous.verify(donor)
    w.require(donor.get('source_classification_recovery')==doc['prior_source_classification_recovery'],
              'Previous source-classification lineage changed')
    _verify_prior_classification(donor,cfg['donor_code_root'])
    prior_decisions=doc['prior_classification_decisions']
    actual_paths=sorted((Path(doc['donor_child'])/'source_classifications').glob('*.json'))
    w.require([b['path'] for b in prior_decisions]==[str(p) for p in actual_paths],
              'Original classification decisions added, removed or renamed')
    for binding in prior_decisions:c._verify(binding)
    events=c.events(donor['root']);stops=[e for e in events if e['kind']=='technical_stop']
    w.require(len(stops)==1 and events[-1]==stops[0] and
              stops[0]['evidence']==c._bound(Path(donor['root'])/'technical_stop.json'),
              'Donor appended or changed its exact terminal event')
    inherited_gates=connection._verified_inherited_gates(donor,events,doc['child_index'],doc['inherited_rows'])
    w.require(inherited_gates==doc['inherited_checkpoint_gates']==bound['inherited_checkpoint_gates'],'Inherited actual checkpoint evidence changed')
    if doc.get('source_review'):
        w.require(doc['source_review']==cfg['source_review'],'Source investigation binding changed')
        donor_plan=w.load(Path(doc['donor_child'])/'continuous_plan.json')
        donor_prefix=worker.inherited_prefix_evidence(Path(doc['donor_child']),donor_plan,doc['inherited_rows'])
        w.require(_source_review(cfg,Path(doc['donor_child']),donor_prefix)==doc['investigated_sources'],'Investigated source evidence changed')
    c._verify(doc['native_plan']);plan=w.load(doc['native_plan']['path']);target=Path(doc['target_child'])
    w.require(w.sha_file(Path(doc['donor_child'])/'continuous_plan.json')==doc['native_plan']['sha256'],'Imported native plan bytes changed')
    policy.validate_policy(target,plan,bound['policy'])
    current=worker.inherited_prefix_evidence(target,plan,doc['inherited_rows'])
    w.require({k:current[k] for k in PREFIX_KEYS}==doc['prefix'],'Imported native SQL/attempt prefix changed')
    c._verify(doc['donor_transport_ledger']);oldbytes=Path(doc['donor_transport_ledger']['path']).read_bytes()
    with (target/'transport_calls.jsonl').open('rb') as stream:w.require(stream.read(len(oldbytes))==oldbytes,'Imported transport prefix changed')
    c._verify(doc['derived_prefix_summary']);summary=w.load(doc['derived_prefix_summary']['path'])
    native={x['row']['sample_id']:w.load(target/'row_checks'/(x['row']['sample_id']+'.json'))['record'] for x in current['rows']}
    expected_ids=[x['row']['sample_id'] for x in current['rows'] if policy.requires_classification(x['row'],native[x['row']['sample_id']])]
    w.require(summary['policy']==bound['policy'] and summary['native_plan_sha256']==plan['plan_sha256'] and
              summary['native_rows']==doc['inherited_rows'] and
              [item['sample_id'] for item in summary['records']]==expected_ids,
              'Derived prefix summary omits, duplicates or changes a required source classification')
    actual_matched=0;encoding_matched=0
    for item in summary['records']:
        decision=policy.verify_decision(item['binding'],native[item['sample_id']],bound['policy'])
        matched=decision['decision'].get('matched') is True
        w.require(item['effective_outcome']==decision['effective_outcome'] and item['classified_source_gap']==(matched and decision.get('source_gap_kind') is not None) and
                  item.get('classified_encoding_correction',False)==(matched and decision.get('correction_kind') is not None),
                  'Derived summary outcome differs from its bound decision')
        actual_matched+=bool(matched and decision.get('source_gap_kind') is not None)
        encoding_matched+=bool(matched and decision.get('correction_kind') is not None)
    w.require(summary['classified_source_gap_count']==actual_matched,'Derived source-gap count differs')
    w.require(summary.get('classified_encoding_correction_count',0)==encoding_matched,'Derived encoding-correction count differs')
    if full:
        for path,digest in doc['donor_inventory'].items():w.require(w.sha_file(path)==digest,'Immutable donor evidence changed: '+path)
    return doc


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',type=Path,required=True)
    print(json.dumps(prepare(parser.parse_args(argv).config),indent=2))

if __name__=='__main__':main()

"""Kevin: exact paused1600 media-URL recovery with separate effective fields.

Original requests, native rows, plan, diagnostics and blocked reading drafts
remain immutable. This adapter awards no checkpoint reading or article approval.
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
from . import tiempo_comment_space_recovery as prior
from . import tiempo_source_classification_policy as policy

SCHEMA='tiempo-paused-media-url-successor-v1'
PRODUCTION={'expected_child_index':65,'expected_saved':1600,'expected_calls':1602,
    'next_sample_id':'TC5_192913',
    'donor_campaign_sha256':'e3bc8e5f0eaf1139ef848425d9364c341cec11ecf13cc9d6e44e79562c4e5257',
    'donor_status_sha256':'34e63c330efa10b09c43f8e171ef12546361a814a3dc703d85a5995585c33c52',
    'donor_native_state_sha256':'002f2d63868102de36718477b9a25ebb9aaf713b23f6338863e0809abfbf9391',
    'donor_pause_receipt_sha256':'807da675f2fb8aec34691e663800d38163438412b47f4be96d402af32c8297fe',
    'pause_request_token':'3ea7976d-83f1-4ec7-a151-fd272dfb28c0'}
PREFIX_KEYS=prior.PREFIX_KEYS


_FROZEN="import json,sys\nsys.path.insert(0,sys.argv[1])\nfrom crawler_core import tiempo_remaining_campaign as c\nm,e=c.read_bound(sys.argv[2],full=True)\nassert m['campaign_sha256']==sys.argv[3]\nprint(json.dumps({'campaign_sha256':m['campaign_sha256'],'comment_space_recovery':m['comment_space_recovery'],'HTTP_requests':0,'production_writes':0}))\n"

def _donor_code_binding(repo,wanted):
    remaining=dict(wanted);cli=remaining.pop('media_url_recovery_cli',None)
    bindings=prior._code(repo,remaining)
    if cli is not None:
        binding=c._bound(Path(repo)/'code/01-crawlers/scripts/prepare_tiempo_media_url_recovery.py')
        w.require(binding['sha256']==cli,'Original frozen media-URL CLI changed');bindings.append(binding)
    return bindings


def _verify_frozen_donor(old,repo):
    if not old.get('comment_space_recovery'):
        w.require(old['synthetic_fixture'],'Production donor lacks comment/media lineage');return None
    before=_donor_code_binding(repo,old['program_sha256'])
    run=subprocess.run([sys.executable,'-B','-c',_FROZEN,str(Path(repo).resolve()/'code/01-crawlers'),old['root'],old['campaign_sha256']],capture_output=True,text=True,timeout=240,cwd=repo)
    w.require(run.returncode==0,'Frozen N12 donor validation failed: '+run.stderr[-2000:])
    expected={'campaign_sha256':old['campaign_sha256'],'comment_space_recovery':old['comment_space_recovery'],'HTTP_requests':0,'production_writes':0}
    w.require(json.loads(run.stdout)==expected and _donor_code_binding(repo,old['program_sha256'])==before,'Frozen donor verifier identity/code changed');return expected


def _gates(old,events,index,saved):
    """Resolve inherited sealed events; the pending current boundary is excluded."""
    markers=c._checkpoint_gate_events(old,events,index)
    w.require([e['rows'] for e in markers]==list(range(400,saved,400)),
              'Pending boundary was approved or an earlier actual gate is missing')
    gates=[]
    for entry in markers:
        original=(c._inherited_gate(old,index,entry['rows'])
                  if entry['kind']=='checkpoint_gate_inherited' else entry)
        c._verify_gate_event(original);gates.append(original)
    return gates


def _drafts(cfg,child,plan):
    """Verify existing reading notes without approving or rewriting a blocked gate."""
    selection_binding=cfg['pending_selection'];c._verify(selection_binding)
    selection=w.load(selection_binding['path']);unsigned=dict(selection);signature=unsigned.pop('selection_sha256',None)
    w.require(w.digest(unsigned)==signature and selection['human_approval'] is False and
              selection['snapshot']['child']==str(child) and
              selection['snapshot']['checkpoint_rows']==cfg['expected_saved'] and
              selection['snapshot']['plan_sha256']==plan['plan_sha256'], 'Wrong pending source selection')
    for binding in selection['snapshot']['bindings']+selection['history']['bindings']:c._verify(binding)
    c._verify(selection['code_binding']['review_module']);c._verify(selection['inherited_obligations']['binding'])
    expected={r['sample_id']:r for r in selection['selected_records']};seen=set();blockers=[]
    for binding in cfg['draft_receipts']:
        c._verify(binding);doc=w.load(binding['path'])
        w.require(doc.get('schema')==selection['receipt_schema'] and doc.get('selection_sha256')==signature and
                  doc.get('runtime_binding_sha256')==w.digest(selection['snapshot']['bindings']) and
                  doc.get('human_approval') is False and isinstance(doc.get('technical_blockers'),list),
                  'Pending reading draft has a different source/runtime binding')
        records=doc['records'];ids=[r['sample_id'] for r in records]
        w.require(ids==doc['actual_ai_read_ids'] and len(ids)==doc['actual_ai_read_count'] and len(ids)==len(set(ids)),
                  'Pending draft reading count differs')
        blockers.extend(doc['technical_blockers'])
        for record in records:
            sid=record['sample_id'];w.require(sid in expected and sid not in seen,'Duplicate/unselected pending reading')
            seen.add(sid);original=expected[sid]
            w.require(record.get('actual_ai_read') is True and record.get('human_approval') is False and
                      record.get('research_status') in (None,'NEEDS_JOAQUIN_REVIEW') and
                      isinstance(record.get('note'),str) and len(record['note'].strip())>=40 and
                      isinstance(record.get('scope'),str) and record['scope'].strip() and
                      isinstance(record.get('technical_blockers'),list),'Invalid existing source reading')
            for key in ('snapshot_sha256','payload_sha256','row_check_sha256'):
                w.require(record[key]==original[key],'Pending reading source/check changed')
            w.require(w.sha_file(original['snapshot_path'])==original['snapshot_sha256'],'Pending raw source changed')
            c._verify(original['row_check']);blockers.extend(record['technical_blockers'])
    w.require(seen==set(expected),'Existing pending reading set is incomplete')
    if not cfg.get('synthetic_fixture'):
        w.require(len(seen)==38 and bool(blockers) and 'TC5_368888' in seen,
                  'Exact38 source reading/real extraction issue evidence differs')
    return {'selection':selection_binding,'draft_receipts':cfg['draft_receipts'],'actual_read_ids':sorted(seen),
            'actual_read_count':len(seen),'preserved_blockers':blockers,'gate_approved':False,
            'new_actual_ai_read_count':0,'human_approval':False}


def _pause(cfg,old,events,child,plan):
    root=Path(old['root']);state=w.load(root/'status.json');native=w.load(child/'continuous_state.json')
    w.require(w.sha_file(root/'status.json')==cfg['donor_status_sha256'] and
              w.sha_file(child/'continuous_state.json')==cfg['donor_native_state_sha256'] and
              state['status']==native['status']==worker.PAUSED and
              not(root/'technical_stop.json').exists() and not(child/'safety_halt.json').exists(),
              'Donor is not the exact intact normal pause')
    path=Path(native['pause_receipt_path']);c._verify({'path':str(path),'sha256':cfg['donor_pause_receipt_sha256']})
    doc=w.load(path);unsigned=dict(doc);signature=unsigned.pop('receipt_sha256',None)
    w.require(w.digest(unsigned)==signature and path.parent==child/'pause_receipts' and
              native['pause_receipt_sha256']==cfg['donor_pause_receipt_sha256'] and
              doc['plan_sha256']==plan['plan_sha256'] and doc['status']==worker.PAUSED and
              doc['result_rows']==cfg['expected_saved'] and doc['transport_reservations']==cfg['expected_calls'] and
              doc['transport_event_count']==2*cfg['expected_calls'] and
              doc['transport_ledger_sha256']==w.sha_file(child/'transport_calls.jsonl') and
              doc['incomplete_native_attempts']==doc['open_transport_calls']==0,
              'Donor paused boundary/ledger receipt differs')
    w.require(events[-1]['kind']=='safe_pause' and events[-1]['native_pause']==c._bound(path) and
              events[-1]['event_sha256']==state['pause_event'] and
              events[-1]['new_saved']==cfg['expected_saved'] and events[-1]['new_calls']==cfg['expected_calls'] and
              cfg['pause_request_token'] in events[-1]['pause_requests'], 'Wrong terminal safe-pause event')
    for binding in events[-1]['pause_requests'].values():c._verify(binding)
    for summary in doc['batch_checks']:
        c._verify({'path':summary['check_path'],'sha256':summary['check_sha256']})
    w.require(sum(s['rows'] for s in doc['batch_checks'])==cfg['expected_saved'], 'Pause certificate row count differs')
    return c._bound(path)


def _read_donor(cfg):
    root=Path(cfg['donor_root']).resolve();w.require(w.sha_file(root/'campaign.json')==cfg['donor_campaign_sha256'],'Donor campaign changed')
    old=c._signed(root/'campaign.json','campaign_sha256')
    w.require(old['root']==str(root) and old['synthetic_fixture']==bool(cfg.get('synthetic_fixture')), 'Wrong donor namespace/type')
    if not old['synthetic_fixture']:
        w.require(all(cfg.get(k)==v for k,v in PRODUCTION.items()) and old.get('comment_space_recovery'),
                  'Only the explicitly bound paused1600 media recovery is supported')
        c._verify(cfg['independent_pause_check']);w.require(cfg['independent_pause_check']['sha256']=='ca577550b4798e8461bba438f51117728ab0fa501387e4ef07b3a3384d3b9712','Wrong independent paused1600 check')
        c._verify(cfg['source_issue_evidence'])
    code=_donor_code_binding(cfg['donor_code_root'],old['program_sha256'])
    for key in ('config_source','preflight','prepared_manifest','source_context','source_ledger','registry','obligations','queue'):c._verify(old[key])
    for part in old['parts']:c._verify(part)
    c._verify_old(w.load(old['preflight']['path']));_verify_frozen_donor(old,cfg['donor_code_root'])
    events=c.events(root);done,context,closed_saved,closed_calls=c._completed(old,events)
    index=old['parts'][len(done)]['plan_index'];child=c.child_path(old,index);plan,_=w.load_plan(child,old['media'])
    counts=c._counts(child,plan)
    w.require(index==cfg['expected_child_index'] and plan['seed_context']==context and
              counts=={'saved':cfg['expected_saved'],'calls':cfg['expected_calls'],'pending_native_attempts':0,'open_transport':False},
              'Donor count, context or open request differs')
    if not old['synthetic_fixture']:
        w.require(old['baseline_saved']+closed_saved==128000 and old['baseline_calls']+closed_calls==128061 and
                  old['remaining_rows']-closed_saved==2531 and plan['row_count']==2000,'Frozen original scope changed')
    paused=_pause(cfg,old,events,child,plan);gates=_gates(old,events,index,cfg['expected_saved'])
    queue=w.readcsv(child/'queue.csv');w.require(queue[cfg['expected_saved']]['sample_id']==cfg['next_sample_id'],'Wrong next untouched URL')
    # Read-only preexisting export verification, strictly before any copy/export.
    for batch in plan['batches']:
        rows=w._rows(child,batch)
        if not rows:continue
        b=child/'batches'/batch['batch_id'];manifest=w.load(b/'export_manifest.json');items,h=w.pilot.load_input(child/batch['input_path'])
        w.require(manifest['result_rows']==len(rows) and worker._export_preview(b,items,h)['files']==manifest['files'],'Donor export readback mismatch')
        for name,meta in manifest['files'].items():w.require(w.sha_file(b/name)==meta['sha256'],'Donor export changed')
    prefix=worker.inherited_prefix_evidence(child,plan,cfg['expected_saved']);w.require(prefix['total_rows']==cfg['expected_saved'],'Wrong saved prefix')
    drafts=_drafts(cfg,child,plan)
    return old,events,context,closed_saved,closed_calls,child,plan,prefix,code,paused,gates,drafts


def prepare(config_path):
    config_path=Path(config_path).resolve();cfg=w.load(config_path);root=Path(cfg['root']).resolve();donor=Path(cfg['donor_root']).resolve()
    w.require(not c.other_collectors(),'Collector active; offline recovery forbidden')
    w.require(not root.exists() and root!=donor and root not in donor.parents and donor not in root.parents,'New independent namespace required')
    old,events,context,closed_saved,closed_calls,source,plan,prefix,code,paused,gates,drafts=_read_donor(cfg)
    index=cfg['expected_child_index'];predecessor=Path(context['history_index']['path']).parent
    inventory={str(p):w.sha_file(p) for p in connection._files(source)}
    controls=[donor/'campaign.json',donor/'status.json',donor/'Inherited_Review_Obligations.json',source/'continuous_state.json',Path(paused['path'])]
    controls+=sorted((donor/'events').glob('*.json'))
    controls +=[Path(b['path']) for b in events[-1]['pause_requests'].values()]
    controls +=[Path(g[key]['path']) for g in gates for key in ('selection','coverage')]
    controls +=[Path(cfg['pending_selection']['path'])]+[Path(b['path']) for b in cfg['draft_receipts']]
    if cfg.get('independent_pause_check'):controls.append(Path(cfg['independent_pause_check']['path']))
    if cfg.get('source_issue_evidence'):controls.append(Path(cfg['source_issue_evidence']['path']))
    prior_decisions=[c._bound(p) for directory in ('source_classifications','source_classification_summaries','lead_media_checks','lead_media_summaries','effective_media') for p in sorted((source/directory).glob('*.json'))]
    controls +=[Path(b['path']) for b in prior_decisions]
    if old.get('comment_space_recovery'):controls +=[Path(old['comment_space_recovery'][k]['path']) for k in ('provenance','policy')]
    bound_controls=[c._bound(p) for p in controls]+code
    oldpre=w.load(old['preflight']['path']);obligations=dict(oldpre['review_obligations']);pending=list(obligations['native_pending_file_bindings']);seen={b['path'] for b in pending}
    for p in source.glob('checkpoint_*/summary.json'):
        summary=w.load(p);f=p.parent/'pending_source_review_samples.csv';w.require(w.sha_file(f)==summary['pending_samples_sha256'] and len(w.readcsv(f))==summary['pending_source_review_sample_count'],'Old pending duties changed')
        if str(f) not in seen:pending.append({**c._bound(f),'rows':summary['pending_source_review_sample_count'],'summary':c._bound(p)})
    obligations.update(native_pending_file_bindings=pending,inherited_paused_media_url_recovery={'donor':str(donor),'pause':paused,'pending_actual_reading':drafts,'gate_approved':False},inherited_comment_space_recovery=old.get('comment_space_recovery'))
    pre={**oldpre,'source_runtime':str(predecessor),'review_obligations':obligations,
         'source_bindings':{**oldpre['source_bindings'],'completed_predecessor_context':c._bound(predecessor/'continuation_context.json')},
         'protected_control_bindings':oldpre['protected_control_bindings']+bound_controls,
         'boundary':{'remaining_original_plan_indices':[index,old['parts'][-1]['plan_index']],
             'reconciled_completed_request_URLs':old['baseline_saved']+closed_saved,'remaining_request_URLs':old['remaining_rows']-closed_saved,
             'global_identity_records_including_legacy2270':len(w.load_history_index(context['history_index'])),'global_charged_calls':old['baseline_calls']+closed_calls}}
    control=root.parent/(root.name+'_Preparation');w.require(not control.exists(),'Preparation controls exist');control.mkdir();w.write(control,'Media_URL_Preflight.json',pre)
    setup={'root':str(root),'preflight':c._bound(control/'Media_URL_Preflight.json'),'max_new_calls':3*pre['boundary']['remaining_request_URLs'],
           'synthetic_fixture':old['synthetic_fixture'],'forecast_growth_multiplier':old['forecast_growth_multiplier'],
           'historical_ai_receipts':([{'coverage':gates[-1]['coverage']['path'],'sha256':gates[-1]['coverage']['sha256']}] if gates else old['historical_ai_receipts']),
           'media_url_recovery_preparation':True}
    w.require(setup['max_new_calls']<=old['max_new_calls']-closed_calls,'Recovery increases request ceiling')
    w.write(control,'Campaign_Config.json',setup);c.prepare(control/'Campaign_Config.json');m=c._signed(root/'campaign.json','campaign_sha256');target=c.child_path(m,index);target.mkdir(parents=True)
    allowed={'continuous_plan.json','queue.csv','known_registry.json','transport_calls.jsonl','transport_state.json'};copied={}
    for p in connection._files(source):
        rel=p.relative_to(source)
        if not(rel.parts[0] in {'row_checks','automatic_checks','transport_snapshots'} or len(rel.parts)==1 and p.name in allowed or rel.parts[0]=='batches' and not any(x in {'backups','review_history'} for x in rel.parts)):continue
        dest=target/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest);w.require(w.sha_file(dest)==inventory[str(p)],'Copied native file differs');copied[str(rel)]=inventory[str(p)]
    imported=worker.inherited_prefix_evidence(target,plan,cfg['expected_saved']);w.require(all(imported[k]==prefix[k] for k in PREFIX_KEYS),'Copied native prefix differs')
    bound_policy=policy.create_policy(root,[p['plan_index'] for p in m['parts']],m['synthetic_fixture'])
    closed=worker.close_saved_boundary(target,m['media'],cfg['expected_saved'],source_classification_policy=bound_policy,install_signal_handlers=False)
    w.require(closed.get('checkpoint_boundary_reached') and closed['result_rows']==cfg['expected_saved'],'Offline media recovery replay blocked; preserve successor')
    summary=target/'source_classification_summaries'/f"saved_{cfg['expected_saved']:08d}.json"
    proof={'schema':SCHEMA,'author':'Kevin','config':c._bound(config_path),'policy':bound_policy,'donor_controls':bound_controls,'donor_inventory':inventory,
           'copied_native_files':copied,'donor_child':str(source),'target_child':str(target),'native_plan':c._bound(target/'continuous_plan.json'),
           'donor_campaign':c._bound(donor/'campaign.json'),'prior_comment_space_recovery':old.get('comment_space_recovery'),
           'prior_classification_decisions':prior_decisions,'inherited_checkpoint_gates':gates,'pending_actual_reading':drafts,'donor_pause':paused,
           'donor_transport_ledger':c._bound(source/'transport_calls.jsonl'),'prefix':{k:prefix[k] for k in PREFIX_KEYS},
           'child_index':index,'inherited_rows':cfg['expected_saved'],'inherited_calls':cfg['expected_calls'],'baseline_saved':m['baseline_saved'],'baseline_calls':m['baseline_calls'],
           'first_new_sample_id':cfg['next_sample_id'],'derived_prefix_summary':c._bound(summary),'new_network_calls':0,'new_actual_ai_read_count':0,
           'human_approval':False,'article_acceptance':False,'pending_boundary_gate_approved':False}
    w.write(root,'Media_URL_Recovery_Provenance.json',proof);m.pop('campaign_sha256');m.pop('media_url_recovery_pending')
    m['media_url_recovery']={'provenance':c._bound(root/'Media_URL_Recovery_Provenance.json'),'policy':bound_policy,'child_index':index,'inherited_checkpoint_gates':gates}
    m['campaign_sha256']=w.digest(m);w.write(root,'campaign.json',m)
    c.event(root,'media_url_recovery_prepared',campaign_sha256=m['campaign_sha256'],provenance=m['media_url_recovery']['provenance'],inherited_saved=cfg['expected_saved'],inherited_calls=cfg['expected_calls'],new_network_calls=0,pending_boundary_gate_approved=False)
    verify(m,full=True)
    return c._state(root,'prepared_offline_not_started',new_saved=cfg['expected_saved'],new_calls=cfg['expected_calls'],original_plan_saved=m['baseline_saved']+cfg['expected_saved'],remaining=m['remaining_rows']-cfg['expected_saved'])


def verify(m,*,full=False):
    bound=m['media_url_recovery'];c._verify(bound['provenance']);doc=w.load(bound['provenance']['path']);c._verify(doc['config']);cfg=w.load(doc['config']['path'])
    w.require(doc['schema']==SCHEMA and doc['policy']==bound['policy'] and doc['child_index']==bound['child_index']==cfg['expected_child_index'] and
              doc['target_child']==str(c.child_path(m,doc['child_index'])) and str(Path(cfg['root']).resolve())==m['root'] and
              m['synthetic_fixture']==bool(cfg.get('synthetic_fixture')) and doc['inherited_rows']==cfg['expected_saved'] and doc['inherited_calls']==cfg['expected_calls'] and
              doc['baseline_saved']==m['baseline_saved'] and doc['baseline_calls']==m['baseline_calls'] and
              doc['new_network_calls']==doc['new_actual_ai_read_count']==0 and doc['pending_boundary_gate_approved'] is False,'Wrong paused media successor identity')
    if not m['synthetic_fixture']:
        w.require(all(cfg.get(k)==v for k,v in PRODUCTION.items()) and m['baseline_saved']==128000 and m['baseline_calls']==128061 and
                  m['remaining_rows']==2531 and [p['plan_index'] for p in m['parts']]==[65,66],'Production paused1600 scope differs')
    for binding in doc['donor_controls']:c._verify(binding)
    donor=c._signed(doc['donor_campaign']['path'],'campaign_sha256');w.require(donor.get('comment_space_recovery')==doc['prior_comment_space_recovery'],'Original recovery lineage changed')
    _verify_frozen_donor(donor,cfg['donor_code_root']);events=c.events(donor['root']);source=Path(doc['donor_child']);donor_plan=w.load(source/'continuous_plan.json')
    w.require(_pause(cfg,donor,events,source,donor_plan)==doc['donor_pause'],'Original pause changed')
    w.require(_gates(donor,events,doc['child_index'],doc['inherited_rows'])==doc['inherited_checkpoint_gates']==bound['inherited_checkpoint_gates'],'Inherited actual gate changed')
    w.require(_drafts(cfg,source,donor_plan)==doc['pending_actual_reading'],'Pending reading evidence changed')
    w.require([b['path'] for b in doc['prior_classification_decisions']]==[str(p) for directory in ('source_classifications','source_classification_summaries','lead_media_checks','lead_media_summaries','effective_media') for p in sorted((source/directory).glob('*.json'))],'Prior classification set changed')
    c._verify(doc['native_plan']);target=Path(doc['target_child']);plan=w.load(doc['native_plan']['path']);w.require(w.sha_file(source/'continuous_plan.json')==doc['native_plan']['sha256'],'Old native plan changed')
    policy.validate_policy(target,plan,bound['policy']);current=worker.inherited_prefix_evidence(target,plan,doc['inherited_rows']);w.require({k:current[k] for k in PREFIX_KEYS}==doc['prefix'],'Original native SQL/attempt prefix changed')
    c._verify(doc['donor_transport_ledger']);oldbytes=Path(doc['donor_transport_ledger']['path']).read_bytes()
    with (target/'transport_calls.jsonl').open('rb') as f:w.require(f.read(len(oldbytes))==oldbytes,'Original transport prefix changed')
    c._verify(doc['derived_prefix_summary']);summary=w.load(doc['derived_prefix_summary']['path']);w.require(summary['policy']==bound['policy'] and summary['native_rows']==doc['inherited_rows'] and summary['native_rows_modified'] is False,'Wrong derived saved-prefix summary')
    records={x['row']['sample_id']:w.load(target/'row_checks'/(x['row']['sample_id']+'.json'))['record'] for x in current['rows']}
    ids=[item['sample_id'] for item in summary['records']]
    expected=[x['row']['sample_id'] for x in current['rows'] if policy.requires_classification(x['row'],records[x['row']['sample_id']])]
    w.require(ids==expected and len(ids)==len(set(ids)),'Incomplete/duplicate classification summary')
    for item in summary['records']:policy.verify_decision(item['binding'],records[item['sample_id']],bound['policy'])
    # The separately bound media summary is verified by the policy module.
    policy.verify_media_summary(target,plan,summary,bound['policy'])
    if full:
        for path,digest in doc['donor_inventory'].items():w.require(w.sha_file(path)==digest,'Immutable donor evidence changed: '+path)
    return doc


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True)
    print(json.dumps(prepare(p.parse_args(argv).config),indent=2))
if __name__=='__main__':main()

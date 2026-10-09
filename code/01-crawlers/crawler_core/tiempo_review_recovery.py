"""Kevin: offline, exact-fault successor for the child47 review-format stop.

Only the investigated `none` to JSON null serialization correction is accepted.
Existing readings are reused, not repeated or converted into human approval.
"""
from pathlib import Path
import argparse
import copy
import json
import shutil

from . import tiempo_continuous_v5 as w
from . import tiempo_remaining_campaign as c
from . import tiempo_connection_recovery as connection
from . import tiempo_resumable_worker as worker
from . import tiempo_stage_review as review

SCHEMA = 'tiempo-review-format-recovery-v1'
PRODUCTION = {
    'expected_child_index': 47, 'expected_saved': 400, 'expected_calls': 400,
    'corrected_sample_id': 'TC5_209522', 'next_sample_id': 'TC5_325552',
    'donor_campaign_sha256': '7c0677067953d96f6d5cdb50b6f2dff2948aa53f01a6f97220c1fb3c49cb6d29',
    'donor_master_halt_sha256': '84948e9bb6f02e60ae3f85f26106b88f585714f8313e9016b0599fd90d16e469',
    'donor_stop_event_sha256': 'fe2a936f02853192f556f7c735ea5c9a4e90f7819047663a00e451bd7c8f60b3',
    'selection_sha256': '034967fb89c962384c7b83f06e3c25af7f033da1949831eaa6475880e5fd0d13',
    'unaccepted_receipt_sha256': '81b02b0f7a282c853f752822e3ff6866c93c5b1e8a0b18f737d3a2c29a4d44d4',
    'corrected_receipt_sha256': 'e091c717b5db95a210ff94f449ebbb16a2b2a127ff80e73eac4e554c74f1da5c',
}
STOP_DETAIL = "ValueError: Required AI/source gate has technical blockers: ['ValueError: A collection receipt cannot assert research/human PASS']"
PREFIX_KEYS = ('prefix_payload_sha256', 'prefix_attempts_sha256', 'prefix_articles_sha256')


def validate_correction(cfg):
    for key in ('selection', 'unaccepted_receipt', 'corrected_receipt'):
        w.require(w.sha_file(cfg[key]) == cfg[key+'_sha256'], 'Review correction binding changed: '+key)
    old = w.load(cfg['unaccepted_receipt']); fixed = w.load(cfg['corrected_receipt'])
    expected = copy.deepcopy(old)
    matches = [r for r in expected['records'] if r['sample_id'] == cfg['corrected_sample_id']]
    w.require(len(matches) == 1 and matches[0]['research_status'] == 'none', 'Wrong serialization fault')
    matches[0]['research_status'] = None
    metadata = fixed.get('format_correction', {})
    w.require(set(metadata) == {'preserved_unaccepted_receipt','preserved_sha256','reason','author'} and
              metadata['preserved_unaccepted_receipt'] == cfg['unaccepted_receipt'] and
              metadata['preserved_sha256'] == cfg['unaccepted_receipt_sha256'] and
              metadata['author'] == 'Kevin' and isinstance(metadata['reason'], str) and bool(metadata['reason']),
              'Correction must preserve and bind the unaccepted receipt')
    actual = copy.deepcopy(fixed); actual.pop('format_correction', None)
    w.require(actual == expected, 'Correction changed content, source binding or research conclusions')
    paths = [Path(p) for p in cfg['receipt_paths']]
    w.require(Path(cfg['corrected_receipt']) in paths and Path(cfg['unaccepted_receipt']) not in paths,
              'Gate must use the corrected receipt and preserve the old one outside submissions')
    gate = review.require_gate(cfg['selection'], paths)
    return gate


def _read_donor(cfg):
    donor = Path(cfg['donor_root']).resolve()
    w.require(w.sha_file(donor/'campaign.json') == cfg['donor_campaign_sha256'], 'Donor campaign changed')
    old = c._signed(donor/'campaign.json', 'campaign_sha256')
    synthetic = bool(cfg.get('synthetic_fixture'))
    w.require(old['root'] == str(donor) and old['schema'] == c.SCHEMA and
              synthetic == bool(old['synthetic_fixture']), 'Wrong donor namespace/type')
    if not synthetic:
        w.require(all(cfg.get(k) == v for k,v in PRODUCTION.items()), 'Only the investigated review-format stop is authorized')
    code = connection._donor_code_binding(cfg['donor_code_root'], old['program_sha256'])
    for key in ('config_source','preflight','prepared_manifest','source_context','source_ledger','registry','obligations','queue'):
        c._verify(old[key])
    for part in old['parts']: c._verify(part)
    c._verify_old(w.load(old['preflight']['path']))
    if old.get('connection_recovery'): connection.verify(old)
    ev = c.events(donor); stops = [e for e in ev if e['kind'] == 'technical_stop']
    w.require(len(stops) == 1 and stops[0]['evidence'] == c._bound(donor/'technical_stop.json') and
              stops[0]['event_sha256'] == cfg['donor_stop_event_sha256'] and stops[0] == ev[-1],
              'Review-stop event changed or later activity exists')
    halt = w.load(donor/'technical_stop.json')
    w.require(w.sha_file(donor/'technical_stop.json') == cfg['donor_master_halt_sha256'] and
              halt['reason'] == 'supervisor_integrity_or_review_error' and halt['detail'] == STOP_DETAIL,
              'Wrong stop reason; this is not a generic technical-stop override')
    done,context,closed_saved,closed_calls = c._completed(old,ev)
    index = cfg['expected_child_index']; part = old['parts'][len(done)]
    w.require(part['plan_index'] == index, 'Wrong active child')
    child = c.child_path(old,index); plan,_ = w.load_plan(child,old['media'])
    counts = c._counts(child,plan)
    w.require(counts == {'saved':cfg['expected_saved'],'calls':cfg['expected_calls'],
                        'pending_native_attempts':0,'open_transport':False}, 'Donor count/request mismatch')
    w.require(cfg['expected_saved'] == 400 and cfg['expected_calls'] == 400 and
              plan['seed_context'] == context and not (child/'safety_halt.json').exists() and
              not (child/'continuous_state.json').exists(), 'Wrong reviewed prefix or native stop state')
    queue = w.readcsv(child/'queue.csv')
    w.require(queue[400]['sample_id'] == cfg['next_sample_id'], 'Next frozen input changed')
    w.require(not [e for e in c._checkpoint_gate_events(old,ev,index)], 'The failed gate was already accepted')
    # No export or boundary regeneration precedes these original-byte checks.
    rows = []
    for batch in plan['batches']:
        saved = w._rows(child,batch); rows.extend(saved)
        if not saved: continue
        B = child/'batches'/batch['batch_id']; manifest = w.load(B/'export_manifest.json')
        w.require(manifest['result_rows'] == len(saved), 'Donor exports are stale')
        items,h = w.pilot.load_input(child/batch['input_path'])
        w.require(worker._export_preview(B,items,h)['files'] == manifest['files'], 'Original export readback differs')
        for name,binding in manifest['files'].items():
            w.require(w.sha_file(B/name) == binding['sha256'], 'Original export bytes differ')
    w.require([r['sample_id'] for r in rows] == [r['sample_id'] for r in queue[:400]], 'Donor is not exact frozen prefix')
    w._snapshot_reconciliation(child,plan,w._ledger(child,plan))
    selection = review._validate_selection(cfg['selection']); snap = selection['snapshot']
    w.require(snap['child'] == str(child) and snap['plan_sha256'] == plan['plan_sha256'] and
              snap['checkpoint_rows'] == 400, 'Review belongs to another prefix')
    validate_correction(cfg)
    for gate in c._checkpoint_gate_events(old,ev): c._verify_gate_event(gate)
    return old,ev,done,context,closed_saved,closed_calls,child,plan,code


def prepare(config_path):
    config_path = Path(config_path).resolve(); cfg = w.load(config_path)
    root = Path(cfg['root']).resolve(); donor = Path(cfg['donor_root']).resolve()
    w.require(not c.other_collectors(), 'Collector active; offline preparation forbidden')
    w.require(not root.exists() and root != donor and root not in donor.parents and donor not in root.parents,
              'Use a separate empty recovery namespace')
    old,ev,done,context,closed_saved,closed_calls,source,plan,code = _read_donor(cfg)
    index = cfg['expected_child_index']; predecessor = Path(context['history_index']['path']).parent
    inventory = {str(p):w.sha_file(p) for p in connection._files(source)}
    controls = [donor/n for n in ('campaign.json','status.json','technical_stop.json','Inherited_Review_Obligations.json')]
    controls += sorted((donor/'events').glob('*.json'))
    controls += [Path(cfg[k]) for k in ('selection','unaccepted_receipt','corrected_receipt')]
    controls += [Path(p) for p in cfg['receipt_paths']]
    donor_controls = [c._bound(p) for p in controls] + code
    oldpre = w.load(old['preflight']['path']); obligations = copy.deepcopy(oldpre['review_obligations'])
    pending = obligations['native_pending_file_bindings']; seen = {e['path'] for e in pending}
    for p in sorted(source.glob('checkpoint_*/summary.json')):
        summary = w.load(p); csv = p.parent/'pending_source_review_samples.csv'
        w.require(w.sha_file(csv) == summary['pending_samples_sha256'] and
                  len(w.readcsv(csv)) == summary['pending_source_review_sample_count'], 'Native pending obligation changed')
        if str(csv) not in seen:
            pending.append({**c._bound(csv),'rows':summary['pending_source_review_sample_count'],'summary':c._bound(p)})
            seen.add(str(csv))
    gates = c._checkpoint_gate_events(old,ev)
    obligations['investigated_donor_obligations'] = c._bound(donor/'Inherited_Review_Obligations.json')
    obligations['prior_checkpoint_gates'] = [{'selection':e['selection'],'coverage':e['coverage']} for e in gates]
    obligations['prior_completed_children'] = [e['receipt'] for e in done]
    obligations['inherited_recovery_lineage'] = old.get('connection_recovery')
    obligations['format_correction_scope'] = {'sample_id':cfg['corrected_sample_id'],
        'unaccepted_receipt':c._bound(cfg['unaccepted_receipt']), 'corrected_receipt':c._bound(cfg['corrected_receipt']),
        'new_actual_ai_read_count':0,'human_approval':False,'research_conclusions_changed':False}
    pre = {**oldpre,'source_runtime':str(predecessor),'review_obligations':obligations,
           'source_bindings':{**oldpre['source_bindings'],
               'completed_predecessor_context':c._bound(predecessor/'continuation_context.json'),
               'completed_predecessor_receipt':c._bound(predecessor/'remaining_completion_receipt.json') if (predecessor/'remaining_completion_receipt.json').exists() else c._bound(predecessor/'continuous_state.json')},
           'protected_control_bindings':oldpre['protected_control_bindings']+donor_controls,
           'boundary':{'remaining_original_plan_indices':[index,old['parts'][-1]['plan_index']],
                       'reconciled_completed_request_URLs':old['baseline_saved']+closed_saved,
                       'remaining_request_URLs':old['remaining_rows']-closed_saved,
                       'global_identity_records_including_legacy2270':len(w.load_history_index(context['history_index'])),
                       'global_charged_calls':old['baseline_calls']+closed_calls}}
    control = root.parent/(root.name+'_Preparation')
    w.require(not control.exists(), 'Preparation controls exist; inspect interruption before another namespace')
    control.mkdir(); w.write(control,'Source_Preflight.json',pre)
    history = ([{'coverage':gates[-1]['coverage']['path'],'sha256':gates[-1]['coverage']['sha256']}] if gates else old['historical_ai_receipts'])
    setup = {'root':str(root),'preflight':c._bound(control/'Source_Preflight.json'),
             'max_new_calls':3*pre['boundary']['remaining_request_URLs'],
             'synthetic_fixture':bool(cfg.get('synthetic_fixture')),
             'forecast_growth_multiplier':old['forecast_growth_multiplier'],
             'historical_ai_receipts':history,'review_recovery_preparation':True}
    w.require(setup['max_new_calls'] <= old['max_new_calls']-closed_calls, 'Recovery increases request authority')
    w.write(control,'Campaign_Config.json',setup); c.prepare(control/'Campaign_Config.json')
    m = c._signed(root/'campaign.json','campaign_sha256'); target = c.child_path(m,index)
    target.mkdir(parents=True); copied = {}
    allowed_top = {'continuous_plan.json','queue.csv','known_registry.json','transport_calls.jsonl','transport_state.json'}
    for p in connection._files(source):
        rel = p.relative_to(source)
        if not (rel.parts[0] in {'row_checks','automatic_checks','transport_snapshots'} or
                (len(rel.parts)==1 and p.name in allowed_top) or
                (rel.parts[0]=='batches' and not any(x in {'backups','review_history'} for x in rel.parts))): continue
        dest = target/rel; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(p,dest)
        w.require(w.sha_file(dest) == inventory[str(p)], 'Recovery copy differs')
        copied[str(rel)] = inventory[str(p)]
    prefix = worker.inherited_prefix_evidence(source,plan,400)
    compact = {k:prefix[k] for k in PREFIX_KEYS}
    target_prefix = worker.inherited_prefix_evidence(target,plan,400)
    w.require({k:target_prefix[k] for k in PREFIX_KEYS} == compact, 'Copied SQL prefix changed')
    closed = worker.close_saved_boundary(target,m['media'],400,install_signal_handlers=False)
    w.require(closed.get('checkpoint_boundary_reached') and closed['result_rows']==400, 'Offline prefix closure failed')
    folder = root/'reviews'/f'plan_{index:06d}'/'checkpoint_00000400'
    coverage = folder/'coverage.json'
    review.seal_gate(cfg['selection'],cfg['receipt_paths'],coverage)
    proof = {'schema':SCHEMA,'author':'Kevin','config':c._bound(config_path),
             'donor_controls':donor_controls,'donor_inventory':inventory,'copied_native_files':copied,
             'donor_child':str(source),'target_child':str(target),'native_plan_binding':c._bound(target/'continuous_plan.json'),
             'child_index':index,'inherited_rows':400,'inherited_calls':400,'prefix':compact,
             'donor_ledger':c._bound(source/'transport_calls.jsonl'),
             'baseline_saved':m['baseline_saved'],'baseline_calls':m['baseline_calls'],
             'selection':c._bound(cfg['selection']),'coverage':c._bound(coverage),
             'inherited_recovery_lineage':old.get('connection_recovery'),
             'first_new_sample_id':cfg['next_sample_id'],'offline_prefix_closed':True,
             'new_actual_ai_read_count':0,'human_approval':False,'article_acceptance':False}
    w.write(root,'Recovery_Provenance.json',proof)
    m.pop('campaign_sha256'); m.pop('review_recovery_pending')
    m['review_recovery'] = {'provenance':c._bound(root/'Recovery_Provenance.json'),'child_index':index}
    m['campaign_sha256'] = w.digest(m); w.write(root,'campaign.json',m)
    c.event(root,'investigated_review_format_recovery_prepared',campaign_sha256=m['campaign_sha256'],
            provenance=m['review_recovery']['provenance'],inherited_saved=400,inherited_calls=400,new_network_calls=0)
    c.event(root,'checkpoint_gate_satisfied',index=index,rows=400,selection=proof['selection'],coverage=proof['coverage'],
            new_saved=400,new_calls=400,new_actual_ai_read_count=0,reused_existing_reading_records=True,
            recovery_provenance=m['review_recovery']['provenance'])
    verify(m,full=True)
    return c._state(root,'prepared_offline_not_started',new_saved=400,new_calls=400,
                    original_plan_saved=m['baseline_saved']+400,remaining=m['remaining_rows']-400)


def verify(m, *, full=False):
    bound = m['review_recovery']; c._verify(bound['provenance']); doc = w.load(bound['provenance']['path'])
    c._verify(doc['config']); cfg = w.load(doc['config']['path'])
    if not cfg.get('synthetic_fixture'):
        w.require(all(cfg.get(k)==v for k,v in PRODUCTION.items()), 'Recovery is outside the investigated production case')
    w.require(str(Path(cfg['root']).resolve())==m['root'] and bool(cfg.get('synthetic_fixture'))==m['synthetic_fixture'] and
              doc['target_child']==str(c.child_path(m,cfg['expected_child_index'])) and
              doc['selection']==c._bound(cfg['selection']), 'Recovery namespace or selection mismatch')
    w.require(doc['schema']==SCHEMA and doc['child_index']==bound['child_index'] and
              doc['baseline_saved']==m['baseline_saved'] and doc['baseline_calls']==m['baseline_calls'] and
              doc['inherited_rows']==400 and doc['inherited_calls']==400 and doc['new_actual_ai_read_count']==0,
              'Review recovery provenance mismatch')
    for b in doc['donor_controls']: c._verify(b)
    c._verify(doc['native_plan_binding']); c._verify(doc['donor_ledger'])
    donor = c._signed(Path(cfg['donor_root'])/'campaign.json','campaign_sha256')
    w.require(donor.get('connection_recovery')==doc['inherited_recovery_lineage'], 'Prior recovery lineage changed')
    if donor.get('connection_recovery'): connection.verify(donor)
    validate_correction(cfg)
    target = Path(doc['target_child']); plan = w.load(doc['native_plan_binding']['path'])
    prefix = worker.inherited_prefix_evidence(target,plan,400)
    w.require({k:prefix[k] for k in PREFIX_KEYS}==doc['prefix'], 'Inherited SQL results/attempts changed')
    oldbytes = Path(doc['donor_ledger']['path']).read_bytes()
    with (target/'transport_calls.jsonl').open('rb') as f:
        w.require(f.read(len(oldbytes))==oldbytes, 'Inherited request ledger prefix changed')
    gates = [e for e in c.events(m['root']) if e['kind']=='checkpoint_gate_satisfied' and
             e['index']==doc['child_index'] and e['rows']==400]
    w.require(len(gates)==1 and gates[0]['selection']==doc['selection'] and gates[0]['coverage']==doc['coverage'] and
              gates[0].get('new_actual_ai_read_count')==0 and gates[0].get('recovery_provenance')==bound['provenance'],
              'Recovered400 source-reading gate absent or changed')
    c._verify_gate_event(gates[0])
    if full:
        for path,digest in doc['donor_inventory'].items():
            w.require(w.sha_file(path)==digest,'Original donor evidence changed: '+path)
    return doc


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--config',required=True,type=Path)
    print(json.dumps(prepare(parser.parse_args(argv).config),indent=2))

if __name__=='__main__': main()

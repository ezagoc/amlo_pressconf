"""Kevin: evidence-bound recovery of the exact child66/107 source-title-scope stop.

Native data, the original missing27 certificate, and all real prior gates stay
unchanged. The successor recomputes derived policy/media outputs offline only.
"""
from pathlib import Path
import argparse,hashlib,json,shutil,sqlite3,subprocess,sys
from . import tiempo_continuous_v5 as w
from . import tiempo_remaining_campaign as c
from . import tiempo_resumable_worker as worker
from . import tiempo_connection_recovery as connection
from . import tiempo_media_url_recovery as prior
from . import tiempo_source_classification_policy as policy
SCHEMA='tiempo-title-scope-successor-v1'
PRODUCTION={'expected_child_index':66,'expected_saved':107,'expected_calls':107,'next_sample_id':'TC5_138299',
 'donor_campaign_sha256':'89819bb6baae5962e08f106529cdc59a1f6650dd6f64e7b8722e7f0a41dd63d6',
 'donor_master_halt_sha256':'2ac76d1351ebc4bcfe9f6fce039ecdd5227836c2e05903f3a691f9a95b24614b',
 'donor_native_halt_sha256':'340f605a56bf8f0f80d703102e6bbba53dfc134200841b2f07a1d84ea8057a3d'}
SOURCE_IDS=['TC5_548145','TC5_583805','TC5_495503']
PREFIX_KEYS=prior.PREFIX_KEYS
_FROZEN='''import json,sys
sys.path.insert(0,sys.argv[1])
from crawler_core import tiempo_remaining_campaign as c
m,e=c.read_bound(sys.argv[2],full=True)
assert m['campaign_sha256']==sys.argv[3]
print(json.dumps({'campaign_sha256':m['campaign_sha256'],'media_url_recovery':m['media_url_recovery'],'HTTP_requests':0,'production_writes':0}))
'''

def _code(repo,wanted):
 d=dict(wanted);cli=d.pop('title_scope_recovery_cli',None);bindings=prior._donor_code_binding(repo,d)
 if cli is not None:
  b=c._bound(Path(repo)/'code/01-crawlers/scripts/prepare_tiempo_title_scope_recovery.py');w.require(b['sha256']==cli,'Frozen title-recovery CLI changed');bindings.append(b)
 return bindings

def _verify_old(old,repo):
 if not old.get('media_url_recovery'):
  w.require(old['synthetic_fixture'],'Production donor lacks previous effective-media lineage');return None
 before=_code(repo,old['program_sha256'])
 p=subprocess.run([sys.executable,'-B','-c',_FROZEN,str(Path(repo).resolve()/'code/01-crawlers'),old['root'],old['campaign_sha256']],capture_output=True,text=True,timeout=240,cwd=repo)
 w.require(p.returncode==0,'Frozen R13 donor validation failed: '+p.stderr[-2000:])
 expected={'campaign_sha256':old['campaign_sha256'],'media_url_recovery':old['media_url_recovery'],'HTTP_requests':0,'production_writes':0}
 w.require(json.loads(p.stdout)==expected and _code(repo,old['program_sha256'])==before,'Frozen donor verifier identity/code changed');return expected

def _source(cfg,child,prefix):
 c._verify(cfg['source_review']);d=w.load(cfg['source_review']['path'])
 w.require(d.get('author')=='Kevin' and d.get('human_approval') is False and d.get('actual_ai_read') is True and d.get('native_review_state_changed') is False and d.get('network_requests')==0,'Invalid source investigation or approval scope')
 wanted=cfg['source_sample_ids'] if cfg.get('synthetic_fixture') else SOURCE_IDS
 records=d.get('records',[]);w.require([r['sample_id'] for r in records]==wanted,'Wrong investigated source set')
 native={x['row']['sample_id']:x for x in prefix['rows']}
 for item in records:
  sid=item['sample_id'];x=native[sid];row=x['row'];raw=child/'batches'/x['batch_id']/row['snapshot_path'];check=child/'row_checks'/(sid+'.json')
  with sqlite3.connect((child/'batches'/x['batch_id']/'pilot.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True) as db:
   payloads=[v[0] for v in db.execute('SELECT payload_json FROM articles') if json.loads(v[0])['sample_id']==sid]
  w.require(len(payloads)==1 and json.loads(payloads[0])==row,'Source payload identity differs')
  w.require(row['error']=='missing_title' and row.get('title') is None and bool((row.get('main_text') or '').strip()) and item['raw_path']==str(raw) and item['raw_sha256']==w.sha_file(raw) and item['row_check_path']==str(check) and item['row_check_sha256']==w.sha_file(check) and item['payload_sha256']==hashlib.sha256(payloads[0].encode()).hexdigest(),'Investigated title/body/raw/diagnostic differs')
  w.require(item.get('gate_approval') is False and item.get('native_manual_review_status')=='not_reviewed' and bool(item.get('actual_ai_read_note')),'Investigation does not preserve reading scope')
 return records

def _halt(cfg,old,events,child,plan):
 root=Path(old['root']);stops=[e for e in events if e['kind']=='technical_stop'];w.require(len(stops)==1 and events[-1]==stops[0] and stops[0]['evidence']==c._bound(root/'technical_stop.json'),'Latest original technical stop differs')
 master=w.load(root/'technical_stop.json');state=w.load(root/'status.json');native=w.load(child/'continuous_state.json');halt=w.load(child/'safety_halt.json');queue=w.readcsv(child/'queue.csv')
 w.require(w.sha_file(root/'technical_stop.json')==cfg['donor_master_halt_sha256'] and w.sha_file(child/'safety_halt.json')==cfg['donor_native_halt_sha256'],'Original specific halt changed')
 w.require(state['status']=='technical_stop_requires_investigation' and native['status']=='halted_no_automatic_resume' and native['halt_sha256']==cfg['donor_native_halt_sha256'] and master['native_result']['halt_sha256']==native['halt_sha256'] and master['new_saved']==cfg['expected_saved']+sum(w.load(e['receipt']['path'])['saved'] for e in events if e['kind']=='child_complete') and master['new_calls']==cfg['expected_calls']+sum(w.load(e['receipt']['path'])['calls'] for e in events if e['kind']=='child_complete') and master['reason']=='native_worker_stopped','Original stopped counts/state differ')
 w.require(halt['reason']=='three_unexplained_rows_in_rolling80' and halt['sample_id']==queue[cfg['expected_saved']-1]['sample_id'] and queue[cfg['expected_saved']]['sample_id']==cfg['next_sample_id'],'Original source halt/next position differs')
 return {'master':c._bound(root/'technical_stop.json'),'native':c._bound(child/'safety_halt.json'),'state':c._bound(root/'status.json'),'native_state':c._bound(child/'continuous_state.json')}

def _read_donor(cfg):
 root=Path(cfg['donor_root']).resolve();w.require(w.sha_file(root/'campaign.json')==cfg['donor_campaign_sha256'],'Donor campaign changed');old=c._signed(root/'campaign.json','campaign_sha256')
 w.require(old['root']==str(root) and old['synthetic_fixture']==bool(cfg.get('synthetic_fixture')),'Wrong donor namespace/type')
 if not old['synthetic_fixture']:
  w.require(all(cfg.get(k)==v for k,v in PRODUCTION.items()) and old.get('media_url_recovery'),'Only exact child66/107 media-URL successor stop is supported')
  c._verify(cfg['independent_stop_check']);w.require(cfg['independent_stop_check']['sha256']=='9f7e8646ea9451a2b9b2a7985a4ff183db4a46d58a820c4e4c4f7892bc5228fc','Wrong independent stopped107 proof')
 if not old['synthetic_fixture']:w.require(cfg['source_review']['sha256']=='ea75a9f4cd2fdee12a2eb01cf791198ebd1a10224a5dee232306cfd8612b2195','Wrong three-source reading proof')
 code=_code(cfg['donor_code_root'],old['program_sha256'])
 for key in ('config_source','preflight','prepared_manifest','source_context','source_ledger','registry','obligations','queue'):c._verify(old[key])
 for part in old['parts']:c._verify(part)
 c._verify_old(w.load(old['preflight']['path']));_verify_old(old,cfg['donor_code_root'])
 events=c.events(root);done,context,closed_saved,closed_calls=c._completed(old,events);index=old['parts'][len(done)]['plan_index'];child=c.child_path(old,index);plan,_=w.load_plan(child,old['media']);counts=c._counts(child,plan)
 w.require(index==cfg['expected_child_index'] and plan['seed_context']==context and counts=={'saved':cfg['expected_saved'],'calls':cfg['expected_calls'],'pending_native_attempts':0,'open_transport':False},'Donor count/context/open request differs')
 if not old['synthetic_fixture']:w.require(old['baseline_saved']+closed_saved==130000 and old['baseline_calls']+closed_calls==130063 and old['remaining_rows']-closed_saved==531 and plan['row_count']==531,'Frozen original scope differs')
 halt=_halt(cfg,old,events,child,plan);gates=prior._gates(old,events,index,cfg['expected_saved'])
 for batch in plan['batches']:
  rows=w._rows(child,batch)
  if not rows:continue
  b=child/'batches'/batch['batch_id'];manifest=w.load(b/'export_manifest.json');items,h=w.pilot.load_input(child/batch['input_path'])
  w.require(manifest['result_rows']==len(rows) and worker._export_preview(b,items,h)['files']==manifest['files'],'Preexisting donor export readback differs')
  for name,meta in manifest['files'].items():w.require(w.sha_file(b/name)==meta['sha256'],'Preexisting donor export bytes changed')
 prefix=worker.inherited_prefix_evidence(child,plan,cfg['expected_saved']);w.require(prefix['total_rows']==cfg['expected_saved'],'Saved prefix differs');source=_source(cfg,child,prefix)
 last_batch=prefix['rows'][-1]['batch_id'];tailchecks=[c._bound(p) for p in (child/'automatic_checks'/last_batch).glob('*/check.json')]
 if not old['synthetic_fixture']:w.require(not tailchecks,'Original missing27 certificate was unexpectedly generated')
 return old,events,context,closed_saved,closed_calls,child,plan,prefix,code,halt,gates,source,tailchecks

def prepare(config_path):
 config_path=Path(config_path).resolve();cfg=w.load(config_path);root=Path(cfg['root']).resolve();donor=Path(cfg['donor_root']).resolve()
 w.require(not c.other_collectors(),'Collector active; offline recovery forbidden');w.require(not root.exists() and root!=donor and root not in donor.parents and donor not in root.parents,'New disjoint recovery namespace required')
 old,events,context,closed_saved,closed_calls,source,plan,prefix,code,halt,gates,reading,tailchecks=_read_donor(cfg);index=cfg['expected_child_index'];predecessor=Path(context['history_index']['path']).parent
 inventory={str(p):w.sha_file(p) for p in connection._files(source)}
 controls=[donor/'campaign.json',donor/'status.json',donor/'Inherited_Review_Obligations.json',Path(cfg['source_review']['path'])]+[Path(b['path']) for b in halt.values()]+sorted((donor/'events').glob('*.json'))
 completed_events=[e for e in events if e['kind']=='child_complete'];completed_gates=[e for e in events if e['kind'] in ('checkpoint_gate_satisfied','checkpoint_gate_inherited') and e['index']!=index]
 controls +=[Path(e['receipt']['path']) for e in completed_events]+[Path(g[k]['path']) for g in gates+completed_gates for k in ('selection','coverage')]
 if cfg.get('independent_stop_check'):controls.append(Path(cfg['independent_stop_check']['path']))
 if old.get('media_url_recovery'):controls +=[Path(old['media_url_recovery'][k]['path']) for k in ('provenance','policy')]
 artifacts=[c._bound(p) for directory in ('source_classifications','source_classification_summaries','lead_media_checks','lead_media_summaries','effective_media') for p in sorted((source/directory).glob('*.json'))]
 controls +=[Path(b['path']) for b in artifacts];bound_controls=[c._bound(p) for p in controls]+code
 oldpre=w.load(old['preflight']['path']);obligations=dict(oldpre['review_obligations']);pending=list(obligations['native_pending_file_bindings']);seen={b['path'] for b in pending}
 pending_children=[source]+[c.child_path(old,e['index']) for e in completed_events]
 for p in (p for ch in pending_children for p in ch.glob('checkpoint_*/summary.json')):
  summary=w.load(p);f=p.parent/'pending_source_review_samples.csv';w.require(w.sha_file(f)==summary['pending_samples_sha256'] and len(w.readcsv(f))==summary['pending_source_review_sample_count'],'Existing pending duties changed')
  if str(f) not in seen:pending.append({**c._bound(f),'rows':summary['pending_source_review_sample_count'],'summary':c._bound(p)})
 obligations['native_pending_file_bindings']=pending;obligations['investigated_donor_obligations']=c._bound(donor/'Inherited_Review_Obligations.json')
 if old.get('media_url_recovery'):obligations['inherited_media_url_recovery']=old['media_url_recovery']
 obligations['title_scope_recovery']={'source_review':cfg['source_review'],'native_halt':halt,'prior_partial_certificate_present':bool(tailchecks),'new_AI_reading_credit':0,'human_approval':False}
 pre={**oldpre,'source_runtime':str(predecessor),'review_obligations':obligations,'source_bindings':{**oldpre['source_bindings'],'completed_predecessor_context':c._bound(predecessor/'continuation_context.json')},'protected_control_bindings':oldpre['protected_control_bindings']+bound_controls,'boundary':{'remaining_original_plan_indices':[index,old['parts'][-1]['plan_index']],'reconciled_completed_request_URLs':old['baseline_saved']+closed_saved,'remaining_request_URLs':old['remaining_rows']-closed_saved,'global_identity_records_including_legacy2270':len(w.load_history_index(context['history_index'])),'global_charged_calls':old['baseline_calls']+closed_calls}}
 control=root.parent/(root.name+'_Preparation');w.require(not control.exists(),'Preparation controls exist');control.mkdir();w.write(control,'Title_Scope_Preflight.json',pre)
 setup={'root':str(root),'preflight':c._bound(control/'Title_Scope_Preflight.json'),'max_new_calls':3*pre['boundary']['remaining_request_URLs'],'synthetic_fixture':old['synthetic_fixture'],'forecast_growth_multiplier':old['forecast_growth_multiplier'],'historical_ai_receipts':[{'coverage':sorted(gates+completed_gates,key=lambda g:(g['index'],g['rows']))[-1]['coverage']['path'],'sha256':sorted(gates+completed_gates,key=lambda g:(g['index'],g['rows']))[-1]['coverage']['sha256']}] if gates or completed_gates else old['historical_ai_receipts'],'title_scope_recovery_preparation':True}
 w.require(setup['max_new_calls']<=old['max_new_calls']-closed_calls,'Recovery increases request ceiling');w.write(control,'Campaign_Config.json',setup);c.prepare(control/'Campaign_Config.json');m=c._signed(root/'campaign.json','campaign_sha256');target=c.child_path(m,index);target.mkdir(parents=True)
 allowed={'continuous_plan.json','queue.csv','known_registry.json','transport_calls.jsonl','transport_state.json'};copied={}
 for p in connection._files(source):
  rel=p.relative_to(source)
  if not(rel.parts[0] in {'row_checks','automatic_checks','transport_snapshots'} or len(rel.parts)==1 and p.name in allowed or rel.parts[0]=='batches' and not any(x in {'backups','review_history'} for x in rel.parts)):continue
  dest=target/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest);w.require(w.sha_file(dest)==inventory[str(p)],'Copied native file differs');copied[str(rel)]=inventory[str(p)]
 imported=worker.inherited_prefix_evidence(target,plan,cfg['expected_saved']);w.require(all(imported[k]==prefix[k] for k in PREFIX_KEYS),'Copied native prefix differs')
 bound_policy=policy.create_policy(root,[p['plan_index'] for p in m['parts']],m['synthetic_fixture'],title_role_evidence=cfg['source_review']);closed=worker.close_saved_boundary(target,m['media'],cfg['expected_saved'],source_classification_policy=bound_policy,install_signal_handlers=False)
 w.require(closed.get('checkpoint_boundary_reached') and closed['result_rows']==cfg['expected_saved'],'Offline replay blocked; preserve successor')
 for item in reading:
  decision=w.load(target/'source_classifications'/(item['sample_id']+'.json'));w.require(decision['decision']['matched'] and decision['effective_outcome']=='article_candidate' and decision['article_candidate'] is True and decision['source_gap_kind'] is None and decision['correction_kind']=='source_title_channel_scope_correction','Investigated body-bearing title gap was not classified safely')
 summary=target/'source_classification_summaries'/f"saved_{cfg['expected_saved']:08d}.json"
 proof={'schema':SCHEMA,'author':'Kevin','config':c._bound(config_path),'policy':bound_policy,'donor_controls':bound_controls,'donor_inventory':inventory,'copied_native_files':copied,'donor_child':str(source),'target_child':str(target),'native_plan':c._bound(target/'continuous_plan.json'),'donor_campaign':c._bound(donor/'campaign.json'),'prior_media_url_recovery':old.get('media_url_recovery'),'prior_derived_artifacts':artifacts,'inherited_checkpoint_gates':gates,'completed_predecessor_events':completed_events,'completed_predecessor_gates':completed_gates,'source_review':cfg['source_review'],'investigated_source':reading,'donor_halt':halt,'original_partial_certificates':tailchecks,'original_partial_certificate_missing':not tailchecks,'donor_transport_ledger':c._bound(source/'transport_calls.jsonl'),'prefix':{k:prefix[k] for k in PREFIX_KEYS},'child_index':index,'inherited_rows':cfg['expected_saved'],'inherited_calls':cfg['expected_calls'],'baseline_saved':m['baseline_saved'],'baseline_calls':m['baseline_calls'],'first_new_sample_id':cfg['next_sample_id'],'derived_prefix_summary':c._bound(summary),'new_network_calls':0,'new_actual_ai_read_count':0,'human_approval':False,'article_acceptance':False,'next_gate_approved':False}
 w.write(root,'Title_Scope_Recovery_Provenance.json',proof);m.pop('campaign_sha256');m.pop('title_scope_recovery_pending');m['title_scope_recovery']={'provenance':c._bound(root/'Title_Scope_Recovery_Provenance.json'),'policy':bound_policy,'child_index':index,'inherited_checkpoint_gates':gates};m['campaign_sha256']=w.digest(m);w.write(root,'campaign.json',m)
 c.event(root,'title_scope_recovery_prepared',campaign_sha256=m['campaign_sha256'],provenance=m['title_scope_recovery']['provenance'],inherited_saved=cfg['expected_saved'],inherited_calls=cfg['expected_calls'],new_network_calls=0,next_gate_approved=False);verify(m,full=True)
 return c._state(root,'prepared_offline_not_started',new_saved=cfg['expected_saved'],new_calls=cfg['expected_calls'],original_plan_saved=m['baseline_saved']+cfg['expected_saved'],remaining=m['remaining_rows']-cfg['expected_saved'])

def verify(m,*,full=False):
 bound=m['title_scope_recovery'];c._verify(bound['provenance']);doc=w.load(bound['provenance']['path']);c._verify(doc['config']);cfg=w.load(doc['config']['path'])
 w.require(doc['schema']==SCHEMA and doc['policy']==bound['policy'] and doc['child_index']==bound['child_index']==cfg['expected_child_index'] and doc['target_child']==str(c.child_path(m,doc['child_index'])) and str(Path(cfg['root']).resolve())==m['root'] and m['synthetic_fixture']==bool(cfg.get('synthetic_fixture')) and doc['inherited_rows']==cfg['expected_saved'] and doc['inherited_calls']==cfg['expected_calls'] and doc['baseline_saved']==m['baseline_saved'] and doc['baseline_calls']==m['baseline_calls'] and doc['new_network_calls']==doc['new_actual_ai_read_count']==0 and doc['next_gate_approved'] is False,'Wrong title-recovery successor identity')
 if not m['synthetic_fixture']:w.require(all(cfg.get(k)==v for k,v in PRODUCTION.items()) and m['baseline_saved']==130000 and m['baseline_calls']==130063 and m['remaining_rows']==531 and [p['plan_index'] for p in m['parts']]==[66] and doc['original_partial_certificate_missing'],'Production child66/107 scope or original missing certificate differs')
 for b in doc['donor_controls']:c._verify(b)
 donor=c._signed(doc['donor_campaign']['path'],'campaign_sha256');w.require(donor.get('media_url_recovery')==doc['prior_media_url_recovery'],'Prior media lineage changed');_verify_old(donor,cfg['donor_code_root']);events=c.events(donor['root']);source=Path(doc['donor_child']);donor_plan=w.load(source/'continuous_plan.json')
 w.require(_halt(cfg,donor,events,source,donor_plan)==doc['donor_halt'] and prior._gates(donor,events,doc['child_index'],doc['inherited_rows'])==doc['inherited_checkpoint_gates']==bound['inherited_checkpoint_gates'],'Original halt/gates changed')
 w.require([e for e in events if e['kind']=='child_complete']==doc['completed_predecessor_events'] and [e for e in events if e['kind'] in ('checkpoint_gate_satisfied','checkpoint_gate_inherited') and e['index']!=doc['child_index']]==doc['completed_predecessor_gates'],'Completed predecessor gates changed')
 c._verify(doc['native_plan']);target=Path(doc['target_child']);plan=w.load(doc['native_plan']['path']);w.require(w.sha_file(source/'continuous_plan.json')==doc['native_plan']['sha256'],'Native plan changed');policy.validate_policy(target,plan,bound['policy']);current=worker.inherited_prefix_evidence(target,plan,doc['inherited_rows']);w.require({k:current[k] for k in PREFIX_KEYS}==doc['prefix'],'Original native prefix changed')
 c._verify(doc['donor_transport_ledger']);oldbytes=Path(doc['donor_transport_ledger']['path']).read_bytes()
 with (target/'transport_calls.jsonl').open('rb') as f:w.require(f.read(len(oldbytes))==oldbytes,'Original ledger prefix changed')
 donor_prefix=worker.inherited_prefix_evidence(source,donor_plan,doc['inherited_rows']);w.require(_source(cfg,source,donor_prefix)==doc['investigated_source'],'Source investigation changed')
 last_batch=donor_prefix['rows'][-1]['batch_id']
 w.require([c._bound(p) for p in sorted((source/'automatic_checks'/last_batch).glob('*/check.json'))]==doc['original_partial_certificates'],'Original partial certificate inventory changed')
 c._verify(doc['derived_prefix_summary']);summary=w.load(doc['derived_prefix_summary']['path']);w.require(summary['policy']==bound['policy'] and summary['native_rows']==doc['inherited_rows'] and summary['native_rows_modified'] is False,'Wrong new derived prefix summary')
 records={x['row']['sample_id']:w.load(target/'row_checks'/(x['row']['sample_id']+'.json'))['record'] for x in current['rows']};ids=[r['sample_id'] for r in summary['records']];expected=[x['row']['sample_id'] for x in current['rows'] if policy.requires_classification(x['row'],records[x['row']['sample_id']])];w.require(ids==expected and len(ids)==len(set(ids)),'Incomplete classification prefix')
 for item in summary['records']:policy.verify_decision(item['binding'],records[item['sample_id']],bound['policy'])
 policy.verify_media_summary(target,plan,summary,bound['policy'])
 if full:
  for path,sha in doc['donor_inventory'].items():w.require(w.sha_file(path)==sha,'Original donor evidence changed: '+path)
 return doc

def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);print(json.dumps(prepare(p.parse_args(argv).config),indent=2))
if __name__=='__main__':main()

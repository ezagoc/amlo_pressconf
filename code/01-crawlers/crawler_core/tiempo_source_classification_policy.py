"""Kevin: versioned source classification overlay; native evidence stays unchanged.

This explicitly changes the stop policy for strictly recognized empty article
shells. It never turns an empty source into an extracted or accepted article.
"""
from pathlib import Path
import hashlib
import json
import sqlite3

from . import tiempo_continuous_v5 as w
from . import tiempo_empty_shell as classifier
from . import tiempo_source_encoding as encoding
from . import tiempo_lead_media as lead_media

SCHEMA = 'tiempo-source-classification-policy-v5-effective-media'
DECISION_SCHEMA = 'tiempo-bound-source-classification-v4'
EXPLAINED_FLAGS = {'missing_body', 'unexplained_result_error'}
REPRESENTATION_FLAGS = {'source_title_metadata_disagreement', 'visible_title_difference'}


def _source_gap_kind(decision):
    kind=decision.get('classification')
    w.require(decision.get('matched') is True and kind in {
        classifier.CLASSIFICATION, classifier.HEADER_IMAGE_CLASSIFICATION},
        'Matched source classification has an unknown outcome kind')
    return kind


def _explained_flags(decision,record):
    """A matched, recomputed source proof can explain only its own flags."""
    if decision.get('classification')==encoding.CLASSIFICATION:
        extra=decision.get('evidence',{}).get('explained_encoding_flags')
        observed=set(record.get('automatic_flags',[]))
        w.require(decision.get('matched') is True and isinstance(extra,list) and bool(extra) and
                  len(extra)==len(set(extra)) and set(extra)<=encoding.EXPLAINABLE_FLAGS and
                  set(extra)<=observed and not record.get('critical_flags') and
                  set(record.get('unexplained_flags',[]))<=set(extra),
                  'Encoding flags lack a complete observed, source-bound explanation')
        return set(extra)
    extra=decision.get('evidence',{}).get('explained_representation_flags',[])
    observed=set(record.get('automatic_flags',[])) | set(record.get('unexplained_flags',[]))
    w.require(decision.get('matched') is True and isinstance(extra,list) and
              all(isinstance(x,str) for x in extra) and len(extra)==len(set(extra)) and
              set(extra)<=REPRESENTATION_FLAGS and set(extra)<=observed,
              'Representation flags lack an exact observed, feature-bound explanation')
    explained=EXPLAINED_FLAGS | set(extra)
    w.require(not record.get('critical_flags') and set(record.get('unexplained_flags',[]))<=explained,
              'Classified source contains another unresolved anomaly')
    return explained


def _binding(path):
    p=Path(path).resolve()
    return {'path':str(p),'sha256':w.sha_file(p)}


def _verify(bound):
    w.require(w.sha_file(bound['path'])==bound['sha256'],'Source classification evidence changed: '+bound['path'])


def _once(path,doc):
    if path.exists():
        w.require(w.load(path)==doc,'Immutable source classification changed: '+str(path))
    else:
        w.write(path.parent,path.name,doc)


def create_policy(root, indices, synthetic):
    root=Path(root).resolve()
    doc={'schema':SCHEMA,'author':'Kevin','campaign_root':str(root),'child_indices':indices,
         'synthetic_fixture':synthetic,'rule_version':classifier.RULE_VERSION,
         'classifier':_binding(classifier.__file__),'features':_binding(classifier.FEATURE_PATH),'overlay':_binding(__file__),
         'encoding_rule_version':encoding.RULE_VERSION,'encoding_helper':_binding(encoding.__file__),
         'effective_media_code':lead_media.code_bindings(),
         'native_program_sha256':w.program_hashes(),'human_approval':False,'article_acceptance':False,
         'semantics':'Native errors, row checks and full risk history are preserved. Feature-verified missing HTML bodies remain source_unavailable, distinguishing no-media shells and static header-image references. Separately, successful text-bearing article candidates can receive a response-bound UTF-8 diagnostic correction only when the unchanged checker with exact saved-response decoding explains all relevant native mismatch flags and no other technical anomaly remains. Such corrections preserve article_candidate status and are not source gaps, article acceptance or AI/human approval. Only each recomputed decision-specific explained flags are removed from the derived stop assessment. All other anomalies and required actual AI review gates remain effective.'}
    path=root/'Source_Classification_Policy.json';_once(path,doc)
    return _binding(path)


def validate_policy(root,plan,binding):
    if binding is None:return None
    _verify(binding);doc=w.load(binding['path']);root=Path(root).resolve()
    _verify(doc['classifier']);_verify(doc['features']);_verify(doc['overlay']);_verify(doc['encoding_helper'])
    w.require(doc.get('effective_media_code')==lead_media.code_bindings(),'Effective media code binding differs')
    base=Path(doc['campaign_root'])/'Media/data/00-newspaper_data/crawler/pilots/Kevin/tiempo_continuous_v5'
    allowed=[base/f'remaining_plan_{index:06d}' for index in doc['child_indices']]
    w.require(doc['schema']==SCHEMA and doc['rule_version']==classifier.RULE_VERSION and root in allowed and
              type(doc['synthetic_fixture']) is bool and doc['human_approval'] is False and doc['article_acceptance'] is False and
              doc['classifier']==_binding(classifier.__file__) and doc['features']==_binding(classifier.FEATURE_PATH) and
              doc['features']['sha256']==classifier.FEATURE_SHA256 and doc['overlay']==_binding(__file__) and
              doc['encoding_rule_version']==encoding.RULE_VERSION and doc['encoding_helper']==_binding(encoding.__file__) and
              doc['native_program_sha256']==plan['program_sha256']==w.program_hashes(),
              'Source classification policy identity/version/native binding mismatch')
    return doc


def _source(root,batch,row,record):
    raw=Path(batch)/row['snapshot_path'];database=Path(batch)/'pilot.sqlite'
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        saved=db.execute('SELECT payload_json FROM articles WHERE sample_id=?',(row['sample_id'],)).fetchone()
        attempt=db.execute('SELECT * FROM fetch_attempts WHERE attempt_id=?',(row['attempt_id'],)).fetchone()
    w.require(saved is not None and json.loads(saved['payload_json'])==row and attempt is not None and
              attempt['completed_at'] and attempt['sample_id']==row['sample_id'] and attempt['url']==row['url'],
              'Source classification requires the exact closed saved request')
    response=json.loads(attempt['response_json'])
    check=Path(root)/'row_checks'/(row['sample_id']+'.json')
    w.require(w.load(check)['record']==record and w.sha_file(raw)==row['snapshot_sha256'],
              'Source classification raw/native record changed')
    return saved['payload_json'],response,raw,check,database


def requires_classification(row,record):
    return (row.get('error')=='missing_body' or 'missing_body' in record.get('automatic_flags',[]) or
            bool(set(record.get('automatic_flags',[])) & encoding.EXPLAINABLE_FLAGS))


def _classify(row,raw,response,record,batch):
    if row.get('error')=='missing_body' or 'missing_body' in record.get('automatic_flags',[]):
        return classifier.classify_empty_article_shell(row,raw,response,record)
    return encoding.classify_encoding_disagreement(row,raw,response,record,batch)


def _outcomes(decision,record):
    matched=decision.get('matched') is True
    correction=matched and decision.get('classification')==encoding.CLASSIFICATION
    gap=matched and not correction
    return {'effective_outcome':'source_unavailable' if gap else record.get('collection_outcome'),
            'source_gap_kind':_source_gap_kind(decision) if gap else None,
            'correction_kind':encoding.CLASSIFICATION if correction else None,
            'article_candidate':False if gap else record.get('collection_outcome')=='article_candidate',
            'research_status':'NEEDS_JOAQUIN_REVIEW' if matched else None}


def assess(root,plan,batch,row,record,policy_binding):
    """Persist a bound derived source-gap or decoding decision; never native rows."""
    # Every saved row is checked, not just existing native anomaly flags: the
    # frozen native parser and checker shared the original lead-media blind spot.
    lead_media.assess(root,plan,batch,row,record,policy_binding)
    if not requires_classification(row,record):
        return None
    payload,response,raw,check,database=_source(root,batch,row,record)
    decision=_classify(row,raw.read_bytes(),response,record,batch)
    matched=decision.get('matched') is True
    explained=_explained_flags(decision,record) if matched else set()
    doc={'schema':DECISION_SCHEMA,'author':'Kevin','sample_id':row['sample_id'],
         'native_plan_sha256':plan['plan_sha256'],'policy':policy_binding,
         'rule_version':decision['rule_version'],'native_record_sha256':w.digest(record),
         'native_row_check':_binding(check),'raw':_binding(raw),'database':str(database),
         'attempt_id':row['attempt_id'],'payload_sha256':hashlib.sha256(payload.encode()).hexdigest(),
         'fields_sha256':w.fields_digest(row),'response_metadata_sha256':w.digest(response),
         'decision':decision,'effective_explained_flags':sorted(explained),
         **_outcomes(decision,record),
         'native_qa_status':row['qa_status'],'native_error':row.get('error'),
         'manual_review_status':'not_reviewed',
         'human_approval':False,'article_acceptance':False}
    path=Path(root)/'source_classifications'/f"{row['sample_id']}.json";_once(path,doc)
    return _binding(path)


def verify_decision(binding,record,policy_binding,cache=None):
    key=(binding['path'],binding['sha256'],w.digest(record),policy_binding['sha256'])
    if cache is not None and key in cache:return cache[key]
    _verify(binding);doc=w.load(binding['path']);_verify(doc['raw']);_verify(doc['native_row_check'])
    w.require(doc['schema']==DECISION_SCHEMA and doc['policy']==policy_binding and
              doc['rule_version'] in {classifier.RULE_VERSION,encoding.RULE_VERSION} and doc['native_record_sha256']==w.digest(record) and
              doc['sample_id']==record['sample_id'] and doc['human_approval'] is False and
              doc['article_acceptance'] is False and doc['manual_review_status']=='not_reviewed',
              'Inherited classification is not bound to this native history record/policy')
    check=w.load(doc['native_row_check']['path']);w.require(check['record']==record,'Inherited native check changed')
    dbpath=Path(doc['database'])
    with sqlite3.connect(dbpath.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        saved=db.execute('SELECT payload_json FROM articles WHERE sample_id=?',(record['sample_id'],)).fetchone()
        attempt=db.execute('SELECT * FROM fetch_attempts WHERE attempt_id=?',(doc['attempt_id'],)).fetchone()
    w.require(saved is not None and attempt is not None and attempt['completed_at'], 'Inherited source request missing/open')
    payload=saved['payload_json'];row=json.loads(payload);response=json.loads(attempt['response_json'])
    w.require(hashlib.sha256(payload.encode()).hexdigest()==doc['payload_sha256'] and
              w.fields_digest(row)==doc['fields_sha256'] and w.digest(response)==doc['response_metadata_sha256'] and
              attempt['sample_id']==record['sample_id'] and attempt['url']==row['url'] and
              row['snapshot_sha256']==doc['raw']['sha256'], 'Inherited source classification input changed')
    actual=_classify(row,Path(doc['raw']['path']).read_bytes(),response,record,dbpath.parent)
    w.require(actual==doc['decision'] and doc['rule_version']==actual['rule_version'],
              'Inherited classification cannot be an unverified Boolean approval')
    matched=actual.get('matched') is True
    w.require(all(doc.get(k)==v for k,v in _outcomes(actual,record).items()), 'Classification outcome/status changed')
    explained=_explained_flags(actual,record) if matched else set()
    w.require(doc['effective_explained_flags']==sorted(explained),'Effective explanation differs from recomputed source proof')
    if cache is not None:cache[key]=doc
    return doc


def inherited_history(plan,policy_binding):
    originals={r['sample_id']:r for r in plan['seed_context']['source_history']}
    result={}
    for item in plan['seed_context'].get('source_classification_history',[]):
        sid=item['sample_id'];w.require(sid in originals and sid not in result,'Classification history differs or duplicates native history')
        verify_decision(item['binding'],originals[sid],policy_binding);result[sid]=item['binding']
    return result


def trigger(history,bindings,policy_binding,current_row,cache):
    current=history[-1]
    if current.get('critical_flags'):return w._window_trigger(history)
    effective=[];current_doc=None
    for record in history[-80:]:
        item=dict(record)
        if record['sample_id'] in bindings:
            doc=verify_decision(bindings[record['sample_id']],record,policy_binding,cache)
            if record['sample_id']==current['sample_id']:current_doc=doc
            if doc['decision'].get('matched') is True:
                explained=_explained_flags(doc['decision'],record)
                item['unexplained_flags']=[x for x in item['unexplained_flags'] if x not in explained]
                item['unexplained_families']=[]  # All remaining reasons were separately required to be explained.
        effective.append(item)
    if (current_row.get('error')=='missing_body' or 'missing_body' in current.get('automatic_flags',[])) and not current.get('recognized_video_only') and not (
            current_doc and current_doc['decision'].get('matched') is True):
        return 'unclassified_source_gap'
    return w._window_trigger(effective)


def summary(root,plan,bindings,records,policy_binding):
    media_summary=lead_media.summary(root,plan,records,policy_binding)
    docs=[]
    for record in records:
        bound=bindings.get(record['sample_id'])
        if bound:
            doc=verify_decision(bound,record,policy_binding)
            docs.append({'sample_id':record['sample_id'],'binding':bound,'effective_outcome':doc['effective_outcome'],
                         'classified_source_gap':doc['source_gap_kind'] is not None,
                         'classified_encoding_correction':doc['correction_kind'] is not None})
    doc={'schema':SCHEMA,'author':'Kevin','policy':policy_binding,'native_plan_sha256':plan['plan_sha256'],
         'native_rows':len(records),'classified_source_gap_count':sum(x['classified_source_gap'] for x in docs),
         'classified_encoding_correction_count':sum(x['classified_encoding_correction'] for x in docs),
         'records':docs,'native_rows_modified':False,'human_approval':False,'article_acceptance':False}
    doc['effective_media_summary']=media_summary
    path=Path(root)/'source_classification_summaries'/f"saved_{len(records):08d}.json";_once(path,doc)
    return _binding(path)


def verify_media_summary(root,plan,classification_summary_doc,policy_binding):
    result=lead_media.verify_summary(root,plan,classification_summary_doc['effective_media_summary'],policy_binding)
    w.require(result['native_rows']==classification_summary_doc['native_rows'],
              'Classification and effective media prefix counts differ')
    return result

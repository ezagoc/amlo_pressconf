"""Kevin: additive source-bound effective media; never rewrite frozen native rows.

The frozen parser/checker epoch remains intact. Two independently implemented
corrected readers supply only lead media fields; all other fields must agree.
Unknown structures are blockers, not source-absence or encoding exemptions.
"""
import csv
import codecs
import hashlib
import io
import json
import re
import sqlite3
from pathlib import Path

from bs4 import BeautifulSoup
from . import tiempo_continuous_v5 as w
from . import tiempo_effective_media_html as extractor
from . import tiempo_effective_media_source as source

SCHEMA = 'tiempo-bound-effective-lead-media-v1'
MEDIA_FIELDS = ('media_embeds', 'media_evidence', 'article_kind', 'classification_rule_version')


def bound(path):
    p=Path(path).resolve()
    return {'path':str(p),'sha256':w.sha_file(p)}


def code_bindings():
    return {name:bound(module.__file__) for name,module in
            [('helper',__import__(__name__,fromlist=[''])),('extractor',extractor),('independent_source',source)]}


def _once(path,doc):
    path=Path(path)
    if path.exists():w.require(w.load(path)==doc,'Immutable effective media evidence changed: '+str(path))
    else:w.write(path.parent,path.name,doc)


def _list(value):
    result=json.loads(value or '[]') if isinstance(value,str) else (value or [])
    w.require(isinstance(result,list),'Media field is not a list')
    return result


def compute(row,raw,response,record):
    """Pure comparison. It cannot fetch, edit native data, or waive other errors."""
    original={k:row.get(k) for k in MEDIA_FIELDS}
    base={'status':'no_effective_media_change','original':original,'effective':dict(original),
          'changed_fields':[],'added_references':[],'lead_evidence':[],
          'technical_blockers':[],'native_other_fields_unchanged':True}
    if response.get('status') != 200:
        return {**base,'scope':'Native non-200 failure retained; no media correction attempted'}
    if row.get('error')=='soft_error_page':
        return {**base,'scope':'Native website error template retained; not an article or media recovery'}
    def stop(reason):
        return {**base,'status':'blocked_effective_media_review','technical_blockers':[reason]}
    if (record.get('sample_id')!=row.get('sample_id') or record.get('url')!=row.get('url') or
            record.get('snapshot_sha256')!=row.get('snapshot_sha256') or
            record.get('fields_sha256')!=w.fields_digest(row)):
        return stop('effective_media_native_row_check_binding')
    if (hashlib.sha256(raw).hexdigest()!=row.get('snapshot_sha256') or
            response.get('curl_exit_code')!=0 or response.get('body_text_limit_exceeded') or
            response.get('error') is not None or row.get('status')!=response.get('status') or
            row.get('content_type')!=response.get('content_type') or
            'text/html' not in (response.get('content_type') or '').lower() or
            response.get('final_url')!=row.get('final_url')):
        return stop('effective_media_response_binding_or_completeness')
    encoding=response.get('body_encoding')
    if response.get('body_encoding_source')!='http_charset':
        return stop('effective_media_source_encoding_provenance_unknown')
    charsets=re.findall(r'charset\s*=\s*[\"\']?([^\s;\"\']+)',response['content_type'],re.I)
    try:
        if len(charsets)!=1 or codecs.lookup(charsets[0]).name!=codecs.lookup(encoding).name:
            return stop('effective_media_source_charset_conflict')
    except (LookupError,TypeError):return stop('effective_media_source_charset_conflict')
    try:text=raw.decode(encoding,errors='strict')
    except (LookupError,TypeError,UnicodeError):return stop('effective_media_source_decoding_unknown')
    soup=BeautifulSoup(text,'html.parser')
    articles=soup.select('article#article-post')
    if len(articles)!=1:return stop('effective_media_article_identity_ambiguous')
    article=articles[0]
    leads=[x for x in article.select('blockquote') if not x.find_parent(class_='complementos-container')]
    # Nested social quotes do not create a second outer article lead.
    leads=[x for x in leads if x.parent is article or (x.parent.name=='p' and
           set(x.parent.get('class',[]))=={'lead'} and x.parent.parent is article)]
    if len(leads)!=1:return stop('effective_media_lead_identity_ambiguous')
    scope,flags=source.independent_lead_media_scope(article,leads[0])
    refs,ref_flags=source.independent_lead_references(scope,row.get('final_url') or row['url'])
    if flags or ref_flags:return stop('effective_media_unknown_lead_structure:'+','.join(sorted(set(flags+ref_flags))))
    if scope is None:return {**base,'scope':'No lead media; original native body-media fields retained'}
    corrected=extractor.tiempo_fields(text,url=row['url'])
    differences=[k for k,v in corrected.items() if k not in MEDIA_FIELDS and row.get(k)!=v]
    if differences:return stop('effective_media_would_change_nonmedia_fields:'+','.join(sorted(differences)))
    before=_list(row.get('media_embeds'));after=_list(corrected.get('media_embeds'))
    if set(after)!=set(before)|set(refs):return stop('effective_media_independent_reference_mismatch')
    expected_videos=source.recognized_source_videos(scope,row.get('final_url') or row['url'])
    old_evidence=_list(row.get('media_evidence'));new_evidence=_list(corrected.get('media_evidence'))
    old_urls={x['url'] for x in old_evidence};new_urls={x['url'] for x in new_evidence}
    if new_urls!=old_urls|{x['url'] for x in expected_videos}:
        return stop('effective_media_independent_video_evidence_mismatch')
    if not all(x in new_evidence for x in old_evidence):return stop('effective_media_lost_native_evidence')
    expected_kind=('article_with_video' if row.get('main_text') else 'video_only') if new_evidence else 'article'
    if corrected.get('article_kind')!=expected_kind:return stop('effective_media_kind_mismatch')
    effective={k:corrected.get(k) for k in MEDIA_FIELDS}
    substantive=any(original[k]!=effective[k] for k in MEDIA_FIELDS if k!='classification_rule_version')
    if not substantive:return {**base,'scope':'Lead references already retained; no native field override needed'}
    if record.get('critical_flags'):return stop('effective_media_cannot_correct_native_critical_failure')
    return {**base,'status':'effective_media_correction','effective':effective,
            'changed_fields':[k for k in MEDIA_FIELDS if original[k]!=effective[k]],
            'added_references':[x for x in after if x not in before],
            'lead_evidence':expected_videos,'scope':'Unique source-bound article lead before byline plus original body media; no transcript or media HTTP request'}


def _inputs(root,batch,row,record):
    batch=Path(batch);raw=batch/row['snapshot_path'];dbpath=batch/'pilot.sqlite'
    with sqlite3.connect(dbpath.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        saved=db.execute('SELECT payload_json FROM articles WHERE sample_id=?',(row['sample_id'],)).fetchone()
        attempt=db.execute('SELECT * FROM fetch_attempts WHERE attempt_id=?',(row['attempt_id'],)).fetchone()
    w.require(saved and json.loads(saved['payload_json'])==row and attempt and attempt['completed_at'] and
              attempt['sample_id']==row['sample_id'] and attempt['url']==row['url'],'Effective media requires exact closed native request')
    check=Path(root)/'row_checks'/(row['sample_id']+'.json')
    w.require(w.load(check)['record']==record and w.sha_file(raw)==row['snapshot_sha256'],'Effective media source/check binding differs')
    return saved['payload_json'],json.loads(attempt['response_json']),raw,check,dbpath


def assess(root,plan,batch,row,record,policy_binding):
    payload,response,raw,check,database=_inputs(root,batch,row,record)
    result=compute(row,raw.read_bytes(),response,record)
    doc={'schema':SCHEMA,'author':'Kevin','sample_id':row['sample_id'],'policy':policy_binding,
         'code':code_bindings(),'native_plan_sha256':plan['plan_sha256'],
         'raw':bound(raw),'native_check':bound(check),'database':str(database),
         'attempt_id':row['attempt_id'],'payload_sha256':hashlib.sha256(payload.encode()).hexdigest(),
         'response_sha256':w.digest(response),'result':result,'native_rows_modified':False,
         'article_acceptance':False,'human_approval':False,'manual_review_status':'not_reviewed'}
    path=Path(root)/'lead_media_checks'/(row['sample_id']+'.json');_once(path,doc)
    w.require(not result['technical_blockers'],'Effective lead-media check blocked: '+str(result['technical_blockers']))
    return bound(path)


def verify(binding):
    w.require(bound(binding['path'])==binding,'Effective media record binding changed')
    doc=w.load(binding['path'])
    w.require(doc['schema']==SCHEMA and doc['code']==code_bindings() and
              doc['native_rows_modified'] is False and doc['human_approval'] is False and
              doc['article_acceptance'] is False and doc['manual_review_status']=='not_reviewed',
              'Effective media code/identity or approval differs')
    w.require(bound(doc['raw']['path'])==doc['raw'] and bound(doc['native_check']['path'])==doc['native_check'],
              'Effective media raw/native check changed')
    w.require(bound(doc['policy']['path'])==doc['policy'],'Effective media policy changed')
    database=Path(doc['database'])
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
        payload=db.execute('SELECT payload_json FROM articles WHERE sample_id=?',(doc['sample_id'],)).fetchone()
    w.require(payload and hashlib.sha256(payload[0].encode()).hexdigest()==doc['payload_sha256'],'Effective media native payload changed')
    row=json.loads(payload[0]);record=w.load(doc['native_check']['path'])['record']
    _,response,raw,_,_=_inputs(database.parents[2],database.parent,row,record)
    w.require(row['attempt_id']==doc['attempt_id'] and w.digest(response)==doc['response_sha256'],
              'Effective media request changed')
    actual=compute(row,raw.read_bytes(),response,record)
    w.require(actual==doc['result'] and not actual['technical_blockers'],'Effective media correction no longer reproduces')
    return doc


def summary(root,plan,records,policy_binding):
    root=Path(root);items=[];corrections=[]
    for record in records:
        binding=bound(root/'lead_media_checks'/(record['sample_id']+'.json'))
        doc=verify(binding)
        w.require(doc['policy']==policy_binding and doc['native_plan_sha256']==plan['plan_sha256'],
                  'Effective media summary has another policy/plan')
        items.append({'sample_id':record['sample_id'],'binding':binding,'status':doc['result']['status']})
        if doc['result']['status']=='effective_media_correction':
            corrections.append({'sample_id':record['sample_id'],'native_payload_sha256':doc['payload_sha256'],
                                **doc['result']['effective'],'correction_evidence':binding})
    out=root/'effective_media'/f'corrections_saved_{len(records):08d}.json'
    data={'author':'Kevin','schema':SCHEMA,'native_rows':len(records),'corrections':corrections,
          'usage':'Join by sample_id and matching native_payload_sha256; replace only the four explicit media fields in an effective view. Keep native data unchanged. Not article or human acceptance.',
          'native_rows_modified':False,'human_approval':False}
    _once(out,data);w.require(w.load(out)==data,'Effective media export readback differs')
    doc={'author':'Kevin','schema':SCHEMA,'native_rows':len(records),'policy':policy_binding,
         'native_plan_sha256':plan['plan_sha256'],'records':items,'correction_count':len(corrections),
         'effective_media_export':bound(out),'human_approval':False,'native_rows_modified':False}
    path=root/'lead_media_summaries'/f'saved_{len(records):08d}.json';_once(path,doc)
    return bound(path)


def verify_summary(root,plan,binding,policy_binding):
    root=Path(root)
    w.require(bound(binding['path'])==binding,'Effective media summary binding changed')
    doc=w.load(binding['path']);n=doc['native_rows']
    w.require(doc['schema']==SCHEMA and doc['policy']==policy_binding and
              doc['native_plan_sha256']==plan['plan_sha256'] and doc['native_rows_modified'] is False and
              doc['human_approval'] is False and type(n) is int and 0<n<=plan['row_count'],
              'Effective media summary identity differs')
    ids=[sid for batch in plan['batches'] for sid in batch['sample_ids']][:n]
    w.require([r['sample_id'] for r in doc['records']]==ids,'Effective media prefix inventory differs')
    corrected=[]
    for item in doc['records']:
        w.require(item['binding']['path']==str((root/'lead_media_checks'/(item['sample_id']+'.json')).resolve()),
                  'Effective media inventory points outside the expected source prefix')
        proof=verify(item['binding'])
        w.require(proof['policy']==policy_binding and proof['sample_id']==item['sample_id'] and
                  proof['result']['status']==item['status'],'Effective media inventory status differs')
        if item['status']=='effective_media_correction':
            corrected.append({'sample_id':item['sample_id'],'native_payload_sha256':proof['payload_sha256'],
                              **proof['result']['effective'],'correction_evidence':item['binding']})
    w.require(doc['correction_count']==len(corrected),'Effective media correction count differs')
    export=doc['effective_media_export'];w.require(bound(export['path'])==export,'Effective media export changed')
    data=w.load(export['path'])
    w.require(data['schema']==SCHEMA and data['native_rows']==n and data['corrections']==corrected and
              data['native_rows_modified'] is False and data['human_approval'] is False,
              'Effective media export does not reproduce the complete corrected data')
    return doc

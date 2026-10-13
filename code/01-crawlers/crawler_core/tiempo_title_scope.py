"""Kevin: source-bound headline-channel correction, never a title substitution.

DOM shape cannot prove that a heading is prose. A matching, preserved actual AI
source-role reading is required in addition to the narrowly recognized editor
paragraph structure. Unknown headings remain candidates and keep the alarm.
"""
from pathlib import Path
import hashlib
import html
import json
import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from . import tiempo_html as native
from . import tiempo_continuous_source as source
from . import tiempo_source_encoding as encoding

RULE_VERSION = 'tiempo-bound-title-channel-scope-v1'
CLASSIFICATION = 'source_title_channel_scope_correction'
EXPLAINABLE_FLAGS = frozenset({'unexplained_result_error'})


def _binding(path):
    p=Path(path).resolve()
    return {'path':str(p),'sha256':source.sha_file(p)}


def read_role_evidence(binding):
    if binding is None:return None
    if _binding(binding['path'])!=binding:raise ValueError('Title-role reading binding changed')
    doc=json.loads(Path(binding['path']).read_text())
    if not (doc.get('schema')=='tiempo-focused-stopped-source-reading-v1' and
            doc.get('actual_ai_read') is True and doc.get('human_approval') is False and
            doc.get('native_review_state_changed') is False):
        raise ValueError('Title-role evidence is not preserved actual AI source reading')
    ids=[r['sample_id'] for r in doc['records']]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate title-role reading identity')
    return doc


def _editor_paragraph(h,body):
    """Necessary structure only; this function never independently awards a role."""
    if h.attrs!={'dir':'ltr'}:return False
    chain=[];p=h.parent
    while p is not None and p is not body:
        chain.append(p);p=p.parent
    if p is not body or [p.name for p in chain]!=['p','p','div','div']:return False
    if any(p.attrs for p in (chain[0],chain[1],chain[3])):return False
    if set(chain[2].attrs)!={'style'} or re.sub(r'\s+','',chain[2]['style']) not in {
            'font-size:20px;line-height:20px','font-size:20px;line-height:20px;'}:return False
    for tag in h.find_all(True):
        if tag.name not in {'span','strong','b','em','i','u','br'}:return False
        if tag.attrs and not(tag.name=='span' and set(tag.attrs)=={'style'} and
                re.sub(r'\s+','',tag['style']) in {'font-size:13px;','font-size:13px'}):return False
    return True


def title_roles(soup, *, reviewed=None):
    """Keep all non-proven headings; evidence is additionally bound by classify()."""
    article=soup.select_one('article#article-post');body=article.select_one('.complementos-container') if article else None
    headings=article.find_all('h1') if article else []
    body_headings=body.find_all('h1') if body else []
    eligible=(reviewed is not None and body is not None and len(body_headings)>=2 and
              reviewed.get('body_h1_count')==len(body_headings) and
              reviewed.get('body_h1_all_in_preserved_text') is True and
              reviewed.get('normalized_full_jsonld_article_body_equals_native_text') is True and
              all(_editor_paragraph(h,body) for h in body_headings))
    proven={id(h) for h in body_headings} if eligible else set()
    roles=[{'index':i,'text':h.get_text(' ',strip=True),
            'role':'reviewed_body_prose' if id(h) in proven else 'headline_candidate_or_unresolved'}
           for i,h in enumerate(headings)]
    explicit=[{'text':h.get_text(' ',strip=True),'attributes':dict(h.attrs)} for h in article.select(
        '[itemprop~="headline"],[data-headline],.headline,.article-title,.entry-title,.title,[role="heading"],[aria-label],[aria-labelledby]')]
    return {'h1_roles':roles,'explicit_headline_nodes':explicit,
            'unresolved_or_title_h1':[r for r in roles if r['role']!='reviewed_body_prose' and r['text']],
            'reviewed_body_h1_indices':[r['index'] for r in roles if r['role']=='reviewed_body_prose']}


def classify(row,raw,response,record,batch,*,role_evidence=None,payload_sha256=None,row_check_sha256=None):
    reasons=[];evidence={}
    def reject(s):reasons.append(s)
    def result():return {'matched':not reasons,'classification':CLASSIFICATION if not reasons else None,
        'rule_version':RULE_VERSION,'rejection_reasons':sorted(set(reasons)),'evidence':evidence}
    flags=set(record.get('automatic_flags',[]));unknown=set(record.get('unexplained_flags',[]))
    if (row.get('error')!='missing_title' or row.get('title') is not None or row.get('qa_status')!='error' or
            row.get('source_title_status')!='unconfirmed_missing' or record.get('collection_outcome')!='article_candidate' or
            record.get('critical_flags') or unknown!=EXPLAINABLE_FLAGS or
            flags-EXPLAINABLE_FLAGS-encoding.RESEARCH_FLAGS or not EXPLAINABLE_FLAGS<=flags):
        reject('not_an_isolated_missing_title_channel_anomaly')
    if row.get('source_specific_error') or row.get('date_conflict') or not all(row.get(k) for k in
            ('main_text','date_published','canonical_url','publication_date_source')):reject('other_source_gap_or_conflict')
    if (not isinstance(raw,bytes) or hashlib.sha256(raw).hexdigest()!=row.get('snapshot_sha256') or
            record.get('snapshot_sha256')!=row.get('snapshot_sha256') or
            record.get('fields_sha256')!=source.fields_digest(row) or record.get('sample_id')!=row.get('sample_id')):
        reject('source_native_binding_mismatch');return result()
    if (response.get('status')!=200 or row.get('status')!=200 or response.get('curl_exit_code')!=0 or
            response.get('error') is not None or response.get('body_text_limit_exceeded') is not False or
            response.get('final_url')!=row.get('final_url') or
            response.get('content_type')!=row.get('content_type') or
            encoding._charsets(response.get('content_type')) not in (['utf-8'],['UTF-8']) or
            not encoding._utf8(response.get('body_encoding')) or response.get('body_encoding_source')!='http_charset'):
        reject('incomplete_or_unbound_response')
    try:text=raw.decode('utf-8',errors='strict')
    except UnicodeDecodeError:reject('invalid_utf8');return result()
    soup=BeautifulSoup(text,'html.parser')
    if not re.search(r'</body>\s*</html>\s*\Z',text,re.I):reject('incomplete_document')
    if any(len(soup.select(s))!=1 for s in ('html','head','body','article#article-post','article#article-post .complementos-container')):
        reject('ambiguous_document');return result()
    article=soup.select_one('article#article-post');body=article.select_one('.complementos-container')
    if (len(article.select(':scope > header'))!=1 or len(article.select(':scope > header > h1'))!=1 or
            article.select_one(':scope > header > h1').get_text(strip=True)):
        reject('missing_or_nonempty_dedicated_headline_slot')
    if article.select('iframe,video,audio,source,object,embed,canvas,svg,template,noscript'):
        reject('unvalidated_media_or_dynamic_structure')
    for node in body.find_all(True):
        if node.name not in {'div','p','h1','span','strong','b','em','i','u','br','style'}:reject('unknown_body_structure')
        if any(k.startswith('on') or k.startswith('data-') for k in node.attrs):reject('unknown_dynamic_body_attribute')
        if node.name=='style' and re.sub(r'\s+','',node.get_text())!='.video-container{max-width:100%;max-height:600px;margin:0auto;display:block;}':
            reject('unknown_body_style')
    if soup.select('meta[http-equiv="refresh"]'):reject('meta_refresh')
    if any(not encoding._utf8(t.get('charset')) for t in soup.select('meta[charset]')):reject('conflicting_charset')
    fresh=native.tiempo_fields(text,url=row['final_url'])
    for k in ('title','summary','main_text','authors','date_published','date_modified','canonical_url',
              'publication_date_source','date_conflict','source_specific_error','source_title_status','source_title_evidence'):
        if fresh.get(k)!=row.get(k):reject('native_reextraction_difference:'+k)
    try:
        ld=[json.loads(t.get_text(),strict=False) for t in soup.select('script[type="application/ld+json"]')]
        if len(ld)!=1 or not isinstance(ld[0],dict) or ld[0].get('@type') not in {'Article','NewsArticle'}:raise ValueError()
        ld=ld[0];slug=urlsplit(row['canonical_url']).path.strip('/').split('/')[-1]
        if ld.get('mainEntityOfPage')!={'@type':'WebPage','@id':slug}:reject('wrong_article_identity')
        if source.compact(BeautifulSoup(html.unescape(ld.get('articleBody') or ''),'html.parser').get_text(' ',strip=True))!=source.compact(row['main_text']):reject('body_not_fully_corroborated')
        if ld.get('datePublished')!=row['date_published']:reject('publication_evidence_conflict')
    except (ValueError,TypeError,KeyError):reject('unvalidated_jsonld_identity')
    proof=read_role_evidence(role_evidence);reviewed=None
    if proof:
        matches=[r for r in proof['records'] if r['sample_id']==row['sample_id']]
        if len(matches)==1:
            r=matches[0]
            if (r['raw_sha256']==row['snapshot_sha256'] and r['payload_sha256']==payload_sha256 and
                    r['row_check_sha256']==row_check_sha256 and r['request_url']==row['url'] and
                    r['native_title'] is None and r['native_error']=='missing_title' and
                    r.get('research_status')=='NEEDS_JOAQUIN_REVIEW' and r.get('gate_approval') is False and
                    isinstance(r.get('actual_ai_read_note'),str) and len(r['actual_ai_read_note'])>=40):reviewed=r
    if reviewed is None:reject('no_matching_actual_source_role_reading')
    roles=title_roles(soup,reviewed=reviewed);evidence['roles']=roles
    if (not roles['reviewed_body_h1_indices'] or roles['unresolved_or_title_h1'] or
            roles['explicit_headline_nodes']):reject('unresolved_or_informative_headline_role')
    audit=json.loads(row.get('source_title_evidence') or '{}')
    removed={f'current_article.h1[{i}]' for i in roles['reviewed_body_h1_indices']}
    effective_channels=[v for v in audit.get('channels',[]) if v['channel'] not in removed]
    if (not effective_channels or audit.get('recognized_empty_h1') is not True or audit.get('jsonld_parse_errors') or
            any(x.get('status') not in {'absent','empty','observed_meta_title_placeholder'} for x in effective_channels)):
        reject('other_headline_channel_or_conflict')
    evidence.update(role_reading=role_evidence,removed_body_h1_channels=sorted(removed),
        effective_title_channels=effective_channels,native_title_remains_null=True,native_error_preserved='missing_title',
        native_prose_unchanged=True,scope='Exact saved response and actual AI role reading only; no human approval or new reading credit.')
    if reasons:return result()
    corrected=dict(row);ea=dict(audit);ea['channels']=effective_channels;ea['all_title_channels_empty']=True
    corrected['source_title_evidence']=json.dumps(ea,ensure_ascii=False);corrected['source_title_status']='confirmed_source_empty'
    checked=encoding._private_diagnose(corrected,batch,raw)
    if set(checked['automatic_flags'])-encoding.RESEARCH_FLAGS:reject('independent_recheck_retains_anomaly')
    if not checked.get('confirmed_source_empty'):reject('corrected_source_empty_contract_failed')
    evidence.update(explained_title_flags=sorted(EXPLAINABLE_FLAGS),effective_source_title_status='confirmed_source_empty',
                    derived_check_sha256=encoding._digest(checked),original_native_flags_preserved=True)
    return result()

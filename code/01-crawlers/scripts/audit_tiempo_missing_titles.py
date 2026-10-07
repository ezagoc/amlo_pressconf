"""Read-only independent title-channel audit of the frozen 592 missing-title pages.
Only writes new audit evidence. Never imports a production parser.
"""
from pathlib import Path
from collections import Counter
from urllib.parse import urlsplit,urlunsplit,urljoin
from datetime import datetime,timezone
import csv,json,hashlib,re,zipfile,html,argparse,sys
import pandas as pd
from bs4 import BeautifulSoup

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--package',type=Path,required=True)
 ap.add_argument('--output',type=Path,required=True)
 a=ap.parse_args(); package=a.package.resolve(); P=package/'01_Task3'; O=a.output.resolve()
 if O.exists() or O==package or package in O.parents:raise SystemExit('Use a new output directory outside the frozen package.')
 O.mkdir(parents=True)
 def offline(event,args):
  if event in {'socket.connect','socket.connect_ex','socket.getaddrinfo'}:raise RuntimeError('Title audit forbids network')
 sys.addaudithook(offline)
 FILES=[P/'data/all_2670.parquet',P/'sources/source_index.csv',P/'sources/source_pages.zip']
 def sha(b):return hashlib.sha256(b).hexdigest()
 def norm(x):return re.sub(r'\s+',' ',html.unescape(str(x or ''))).strip()
 def key(u):
  v=urlsplit(u);return (v.hostname or '').removeprefix('www.').lower(),v.path.rstrip('/')
 def clean(v):
  if isinstance(v,dict):return {k:clean(x) for k,x in v.items()}
  if isinstance(v,list):return [clean(x) for x in v]
  return None if v is None or isinstance(v,float) and pd.isna(v) else v
 before={str(p):{'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size} for p in FILES}
 (O/'original_files_before.json').write_text(json.dumps(before,indent=2)+'\n')
 f=pd.read_parquet(FILES[0]);missing=f[f.error.eq('missing_title')].copy();assert len(f)==2670 and len(missing)==592 and missing.title.isna().all()
 idx={r['record_id']:r for r in csv.DictReader(FILES[1].open(encoding='utf-8-sig',newline=''))}
 records=[];candidates=[]
 with zipfile.ZipFile(FILES[2]) as z:
  for row in missing.to_dict('records'):
   row=clean(row);rid=row['package_record_id'];ix=idx[rid];member=row['package_snapshot_member'];assert member==ix['html_archive_member'];raw=z.read(member);snapshot=sha(raw);assert snapshot==row['snapshot_sha256']==ix['snapshot_sha256'];mb=z.read(ix['metadata_archive_member']);assert sha(mb)==ix['metadata_sha256']
   meta=json.loads(mb);assert meta['snapshot_sha256']==snapshot
   soup=BeautifulSoup(raw,'html.parser');arts=soup.select('article#article-post');a=arts[0] if len(arts)==1 else None;channels=[]
   def ch(name,value,scope='current',**details):
    val=norm(value);status='empty' if not val else 'observed_meta_name_title_slash_placeholder' if name.startswith('meta.name=title') and val=='/' else 'informative_candidate'
    channels.append({'channel':name,'raw_value':value,'normalized_value':val,'status':status,'scope':scope,**details})
   for i,x in enumerate(soup.find_all('title')):ch(f'document.title[{i}]',x.get_text())
   for i,x in enumerate(soup.find_all('meta')):
    label=(x.get('name') or x.get('property') or x.get('itemprop') or '').lower()
    if label in {'title','og:title','twitter:title','headline','name'}:
     attr='name' if x.get('name') else 'property' if x.get('property') else 'itemprop';ch(f'meta.{attr}={label}[{i}]',x.get('content'),scope='document')
   if a:
    for i,x in enumerate(a.select('header h1,header h2,header h3,header [itemprop="headline"],header [property="headline"]')):
     ch(f'current_header.{x.name}[{i}]',x.get_text(' ',strip=False))
     for attr in ['title','aria-label','content']:
      if x.has_attr(attr):ch(f'current_header.{x.name}[{i}].{attr}',x[attr])
    for i,x in enumerate(a.select('[itemprop="headline"],[property="headline"]')):ch(f'current_article.semantic_headline[{i}]',x.get('content') or x.get_text(' ',strip=False))
   parsed=[];parse_errors=[]
   def scan(obj,path):
    if isinstance(obj,dict):
     t=obj.get('@type',[]);t=[t] if isinstance(t,str) else t
     if isinstance(t,list) and any(x in {'Article','NewsArticle','ReportageNewsArticle','BlogPosting','SocialMediaPosting'} for x in t):parsed.append({'path':path,'object':obj})
     for k,v in obj.items():
      if isinstance(v,(dict,list)):scan(v,path+'.'+k)
    elif isinstance(obj,list):
     for j,v in enumerate(obj):scan(v,path+f'[{j}]')
   for i,x in enumerate(soup.select('script[type="application/ld+json"]')):
    try:scan(json.loads(x.get_text(),strict=False),f'jsonld[{i}]')
    except (ValueError,TypeError) as e:parse_errors.append({'script':i,'error':str(e)})
   identities={key(u) for u in [row['url'],row['final_url'],row['canonical_url']] if u};slugs={v[1].split('/')[-1] for v in identities};scoped=[];unrelated=[];unscoped=[]
   for ent in parsed:
    obj=ent['object'];refs=[]
    for k in ['url','@id','mainEntityOfPage']:
     v=obj.get(k)
     if isinstance(v,str):refs.append(v)
     elif isinstance(v,dict):refs.extend(v[q] for q in ['@id','url'] if isinstance(v.get(q),str))
    matches=any(key(urljoin(row['canonical_url'] or row['url'],v)) in identities or v in slugs for v in refs)
    if matches:scoped.append({**ent,'scope_method':'matched_current_url_or_exact_article_slug','identity_refs':refs})
    elif refs:unrelated.append({**ent,'identity_refs':refs})
    else:unscoped.append(ent)
   if not scoped and len(parsed)==1 and len(unscoped)==1:scoped=[{**unscoped[0],'scope_method':'single_unscoped_article','identity_refs':[]}]
   for ent in scoped:
    for name in ['headline','name','alternativeHeadline']:ch(ent['path']+'.'+name,ent['object'].get(name),scope='current_jsonld',scope_method=ent['scope_method'])
   informative=[c for c in channels if c['status']=='informative_candidate']
   h1=a.select('header h1') if a else [];recognized_empty_h1=len(h1)==1 and not norm(h1[0].get_text())
   blockers=[]
   if len(arts)!=1:blockers.append('primary_article_not_unique')
   if not recognized_empty_h1:blockers.append('recognized_current_h1_not_uniquely_present_and_empty')
   if parse_errors:blockers.append('jsonld_parse_error')
   if len(scoped)!=1:blockers.append('current_jsonld_not_uniquely_identified')
   if informative:classification='available_title_candidate_requires_scope_review'
   elif blockers:classification='unresolved_title_scope_or_structure'
   else:classification='confirmed_source_empty_in_saved_response'
   body=a.select_one('.complementos-container') if a else None
   structure={'primary_articles':len(arts),'all_article_elements':len(soup.select('article')),'body_containers':len(a.select('.complementos-container')) if a else 0,'nested_articles_in_body':len(body.select('article')) if body else 0,'list':bool(body and body.select('ul,ol')),'table':bool(body and body.select('table')),'twitter':bool(body and body.select('.twitter-tweet,.twitter-video')),'instagram':bool(body and body.select('.instagram-media')),'iframe':bool(body and body.select('iframe')),'native_video':bool(body and body.select('video')),'related_link_removed':bool(json.loads(row['related_links'] or '[]'))}
   rec={'record_id':rid,'sample_id':row['sample_id'],'source_group':row['package_source_group'],'url':row['url'],'canonical_url':row['canonical_url'],'publication_month':row['date_published'][:7],'snapshot_archive':str(FILES[2]),'snapshot_member':member,'snapshot_sha256':snapshot,'snapshot_hash_verified':True,'metadata_member':ix['metadata_archive_member'],'metadata_sha256':sha(mb),'classification':classification,'recognized_empty_h1':recognized_empty_h1,'informative_channel_count':len(informative),'channels':channels,'jsonld_parse_errors':parse_errors,'current_jsonld_scope':[{'path':e['path'],'scope_method':e['scope_method'],'identity_refs':e['identity_refs']} for e in scoped],'noncurrent_jsonld_articles':[{'path':e['path'],'identity_refs':e.get('identity_refs'),'headline':e['object'].get('headline')} for e in unrelated],'unresolved_reasons':blockers,'structure':structure,'body_chars':len(row['main_text'] or ''),'prior_package_assistant_read':row['package_assistant_source_read'],'audit_method':'automated_independent_saved_HTML_title_channel_check','actual_full_source_read_this_audit':False,'human_approval':False,'original_title_unchanged':row['title'] is None}
   records.append(rec)
   candidates.append({'record_id':rid,'sample_id':row['sample_id'],'url':row['url'],'snapshot_sha256':snapshot,'official_directory_titles':json.loads(row['package_official_directory_titles_json'] or '[]'),'directory_dates':json.loads(row['package_directory_dates_json'] or '[]'),'directory_refs':json.loads(row['package_directory_refs_json'] or '[]'),'directory_candidate_id':row['package_directory_candidate_id'],'verification':row['package_directory_title_verification'],'not_article_title':True,'filled_original_title':False,'semantic_title_acceptance':False})
 (O/'per_record_title_evidence.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
 (O/'directory_title_candidates_separate.json').write_text(json.dumps(candidates,ensure_ascii=False,indent=2)+'\n')
 flat=[]
 for r in records:
  q={k:v for k,v in r.items() if not isinstance(v,(list,dict))};q.update(channels_json=json.dumps(r['channels'],ensure_ascii=False),structure_json=json.dumps(r['structure'],ensure_ascii=False),unresolved_reasons_json=json.dumps(r['unresolved_reasons']));flat.append(q)
 with (O/'per_record_title_evidence.csv').open('w',encoding='utf-8',newline='') as s:w=csv.DictWriter(s,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
 with (O/'directory_title_candidates_separate.csv').open('w',encoding='utf-8',newline='') as s:
  flatc=[{k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in x.items()} for x in candidates];w=csv.DictWriter(s,fieldnames=list(flatc[0]));w.writeheader();w.writerows(flatc)
 summary={'author':'Kevin','actual_operator':'AI assistant','checked_at':datetime.now(timezone.utc).isoformat(),'frozen_package_rows':2670,'missing_title_records_checked':len(records),'snapshot_hashes_verified':sum(r['snapshot_hash_verified'] for r in records),'classifications':dict(Counter(r['classification'] for r in records)),'months':dict(sorted(Counter(r['publication_month'] for r in records).items())),'source_groups':dict(Counter(r['source_group'] for r in records)),'source_structure_counts':{k:dict(Counter(str(r['structure'][k]) for r in records)) for k in records[0]['structure']},'directory_candidate_records':sum(bool(x['official_directory_titles']) for x in candidates),'directory_nonempty_title_values':sum(sum(bool(norm(v)) for v in x['official_directory_titles']) for x in candidates),'automated_check_is_not_full_source_reading':True,'source_news_values_modified':False,'no_http':True}
 (O/'automated_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 after={str(p):{'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size} for p in FILES};assert after==before;(O/'original_files_after_automated_check.json').write_text(json.dumps(after,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=="__main__":main()

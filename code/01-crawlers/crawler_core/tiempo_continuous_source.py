"""Portable independent source diagnostics and known types from real bound reviews.

Copied from Kevin's independently tested preparation checker, then isolated from
workspace paths. No network, parser oracle, implicit review, or learned risk bypass.
"""
from pathlib import Path
from datetime import datetime,timezone,timedelta
from urllib.parse import urlsplit,urljoin
from collections import Counter
import hashlib,json,re,sqlite3,unicodedata,html
from bs4 import BeautifulSoup,Comment
from .tiempo_review import fields_digest,apply_reviews
from . import tiempo_pilot as pilot
from .tiempo_queue import normalize_url

SCHEMA = 'tiempo-continuous-known-reviewed-v1'
def sha_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while block:=f.read(4*1024*1024):h.update(block)
    return h.hexdigest()
def encoded(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def require(ok,message):
    if not ok:raise ValueError(message)

def norm(s):return re.sub(r'\s+',' ',s or '').strip() or None
def compact(s):return re.sub(r'\s+','',unicodedata.normalize('NFC',s or ''))
def confirmed_empty(p):
 try:e=json.loads(p.get('source_title_evidence') or 'null')
 except (ValueError,TypeError):return False
 return (p.get('qa_status')=='error' and p.get('status')==200 and p.get('error')=='missing_title' and p.get('source_title_status')=='confirmed_source_empty' and isinstance(e,dict) and e.get('recognized_empty_h1') is True and e.get('all_title_channels_empty') is True and not p.get('title') and not p.get('date_conflict') and not p.get('source_specific_error') and all(p.get(k) for k in ['main_text','date_published','canonical_url','publication_date_source']))

def dom_paths(root):
 """Text-free tag paths, ignoring repeated paragraph count but not new nesting."""
 if root is None:return []
 paths=set()
 for node in root.find_all(True):
  if node.name in {'script','style'}:continue
  parts=[];current=node
  while current is not None and current is not root:
   parts.append(current.name);current=current.parent
  if current is root:paths.add('/'.join(reversed(parts)))
 return sorted(paths)

def remove_known_instagram_ui(body):
 """Independently recognize fixed UI leaves; never trust parser removal claims.

 Only mutates the disposable diagnostic DOM. Captions and unmatched leaves
 remain in the expected text, so dropping either still raises a difference.
 """
 removed=[]
 def content(node):return norm(node.get_text(' ',strip=True)) or ''
 def style(node):return re.sub(r'\s+','',node.get('style','').casefold())
 def styles(node):return dict(part.split(':',1) for part in style(node).split(';') if ':' in part)
 def igpath(value):
  try:u=urlsplit(value or '')
  except ValueError:return None
  if u.scheme not in {'http','https'} or u.hostname not in {'www.instagram.com','instagram.com'} or u.username or u.password or u.fragment:return None
  return u.path.rstrip('/')
 def postpath(value):
  path=igpath(value)
  return path if path and re.fullmatch(r'/(?:p|reel|tv)/[A-Za-z0-9_-]+',path) else None
 def remove(node,reason):
  removed.append({'reason':reason,'text':content(node)});node.decompose()
 def valid_clock(node):
  m=re.fullmatch(r'(\d{1,2})(?: de)? (Ene|Feb|Mar|Abr|May|Jun|Jul|Ago|Sep|Oct|Nov|Dic)(?:,| de) (\d{4}) a las (\d{1,2}):(\d{2}) (PDT|PST)',content(node),re.I)
  if not m:return False
  day,month,year,hour,minute,zone=m.groups()
  months={n:i+1 for i,n in enumerate(['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'])}
  try:
   value=datetime.fromisoformat(node.get('datetime','').replace('Z','+00:00'))
   if value.utcoffset() is None:return False
   rendered=value.astimezone(timezone(timedelta(hours=-7 if zone.upper()=='PDT' else -8)))
   # Old embeds also display a 12-hour clock without AM/PM (e.g. 18:06
   # becomes "6:06 PDT"). This identifies UI only, never an article date.
   display_hour=int(hour)
   same_hour=display_hour==rendered.hour or (1<=display_hour<=12 and display_hour==(rendered.hour%12 or 12))
   return same_hour and (rendered.year,rendered.month,rendered.day,rendered.minute)==(int(year),months[month.lower()],int(day),int(minute))
  except (ValueError,TypeError,OverflowError):return False
 for embed in body.select('blockquote.instagram-media[data-instgrm-permalink]'):
  permalink=postpath(embed.get('data-instgrm-permalink'))
  if not permalink:continue
  for node in list(embed.select('div')):
   if (content(node)=='Ver esta publicación en Instagram' and not node.find(['div','p','blockquote'])
       and 'color:#3897f0' in style(node) and 'font-family:arial' in style(node)
       and node.parent and 'padding-top:8px' in style(node.parent)):
    remove(node,'instagram_view_post_ui')
  for node in list(embed.select('p')):
   anchors=node.find_all('a',href=True);css=styles(node)
   if len(anchors)!=1 or node.find(['p','div','blockquote']) or css.get('color')!='#c9c8cd' or css.get('text-overflow')!='ellipsis':continue
   anchor=anchors[0];times=node.find_all('time')
   if not times:
    if (content(node)==content(anchor) and re.fullmatch(r'Una publicación compartida (?:por|de) .+ \(@[^()]+\)',content(node))
        and postpath(anchor['href'])==permalink):remove(node,'instagram_shared_post_ui')
    continue
   if (len(times)!=1 or times[0].parent is not node or anchor.parent is not node
       or any(child.name not in {'a','time'} for child in node.find_all(True,recursive=False))
       or not all(css.get(k)==v for k,v in {'font-family':'arial,sans-serif','font-size':'14px','line-height':'17px','white-space':'nowrap'}.items())):continue
   stamp=times[0];label=content(node)
   suffix=' el '+content(stamp)
   if not label.endswith(suffix) or not valid_clock(stamp):continue
   attribution=label[:-len(suffix)]
   match=re.fullmatch(r'Una publicación compartida (?:por|de) (.+) \(@([A-Za-z0-9._]+)\)',attribution)
   if not match:continue
   display,handle=match.groups();link=igpath(anchor['href'])
   same_post=content(anchor)==attribution and postpath(anchor['href'])==permalink
   same_profile=content(anchor)==display and link is not None and link.lower()==('/'+handle).lower()
   if same_post or same_profile:remove(node,'instagram_timed_shared_post_ui')
 return removed

def remove_contract_main_image_captions(article):
 """Only the standalone lead-image caption container, on a disposable DOM.

 This is a structural scope rule, not a judgment about caption truth. Any
 unexpected child/text, nested body location, or changed placement remains
 unexplained. The caption and image reference are retained as audit evidence.
 """
 removed=[]
 if article is None or article.name!='article' or article.get('id')!='article-post':return removed
 children=[n for n in article.children if getattr(n,'name',None)]
 headers=[n for n in children if n.name=='header']
 leads=[]
 for n in children:
  if n.name=='blockquote':leads.append(n)
  elif n.name=='p' and set(n.get('class',[]))=={'lead'}:
   inner=[x for x in n.children if getattr(x,'name',None)]
   if len(inner)==1 and inner[0].name=='blockquote' and not any(norm(str(x)) for x in n.children if not getattr(x,'name',None) and not isinstance(x,Comment)):
    leads.append(n)
 bodies=[n for n in children if 'complementos-container' in n.get('class',[])]
 if len(headers)!=1 or len(leads)!=1 or len(bodies)!=1:return removed
 lead_block=leads[0] if leads[0].name=='blockquote' else leads[0].find('blockquote',recursive=False)
 actual_leads=[x for x in article.select('blockquote') if not x.find_parent(class_='complementos-container')]
 if actual_leads!=[lead_block]:return removed
 h,l,b=[children.index(n) for n in [headers[0],leads[0],bodies[0]]]
 if not h<l<b:return removed
 candidates=[n for n in children[h+1:l] if n.name=='div' and set(n.get('class',[]))=={'complemento-item','m-t-md'}]
 # This recognized layout has one standalone main image. Multiple candidates
 # are ambiguous and must remain visible to the outside-text check.
 if len(candidates)!=1:return removed
 node=candidates[0];tags=[n for n in node.children if getattr(n,'name',None)]
 if [n.name for n in tags]!=['img','p']:return removed
 img,caption=tags
 if set(img.get('class',[]))!={'img-responsive','complemento-img'} or set(caption.get('class',[]))!={'text-center'}:return removed
 if caption.find(True) is not None or not norm(caption.get_text(' ',strip=True)):return removed
 if any(norm(str(n)) for n in node.children if not getattr(n,'name',None) and not isinstance(n,Comment)):return removed
 src=img.get('src');image=urlsplit(src or '')
 if image.scheme not in {'http','https'} or image.hostname!='static.tiempo.com.mx' or not image.path.startswith('/uploads/imagen/'):return removed
 removed.append({'reason':'standalone_main_image_caption_outside_article_body_contract','caption_text':norm(caption.get_text(' ',strip=True)),'image_src':src,'image_alt':img.get('alt'),'selector':'article#article-post > div.complemento-item.m-t-md > p.text-center','placement':'after_header_before_direct_or_p_lead_wrapped_blockquote_and_body'})
 node.decompose()
 return removed

def diagnose(p,run_dir):
 flags=[];outside_caption_evidence=[]
 qa=p.get('qa_status');has_error=bool(p.get('error'))
 for channel in ['url','final_url','canonical_url']:
  value=urlsplit(p.get(channel) or '')
  if value.scheme not in {'https','http'} or value.hostname not in {'www.tiempo.com.mx','tiempo.com.mx'}:flags.append(channel+'_outside_tiempo_scope')
 if qa not in {'success','error'}:flags.append('unknown_qa_status')
 if (qa=='error' and not has_error) or (qa=='success' and has_error):flags.append('qa_status_error_inconsistency')
 raw=b'';path=None;soup=BeautifulSoup('','html.parser');snapshot=p.get('snapshot_path')
 if snapshot:
  path=(run_dir/snapshot).resolve()
  if not path.is_relative_to(run_dir.resolve()):raise ValueError('Snapshot path escapes batch')
  raw=path.read_bytes()
  if hashlib.sha256(raw).hexdigest()!=p.get('snapshot_sha256'):raise ValueError('Snapshot corruption '+p['sample_id'])
  soup=BeautifulSoup(raw,'html.parser')
 else:flags.append('missing_response_snapshot')
 articles=soup.select('article#article-post');article=articles[0] if articles else None
 bodies=article.select('.complementos-container') if article else []
 leads=[x for x in article.select('blockquote') if not x.find_parent(class_='complementos-container')] if article else []
 body=bodies[0] if bodies else None;lead=leads[0] if leads else None
 if len(soup.select('article'))!=1 or len(articles)!=1 or len(bodies)!=1 or len(leads)!=1:flags.append('ambiguous_article_body_or_lead_containers')
 if article:
  if len(article.select('header h1'))!=1:flags.append('ambiguous_visible_title_structure')
  # A second news body or prose sibling must not disappear through the same
  # select_one blind spot as the parser. Only known non-news channels are ignored.
  outside=BeautifulSoup(str(article),'html.parser')
  outside_caption_evidence=remove_contract_main_image_captions(outside.select_one('article#article-post'))
  for node in outside.select('header,blockquote,.complementos-container,script,style,figure,figcaption,nav,footer'):
   if node.parent:node.decompose()
  for node in outside.find_all(string=lambda v:isinstance(v,Comment)):node.extract()
  if compact(outside.get_text('',strip=False)):flags.append('unexplained_article_text_outside_recognized_containers')
  if lead and len(lead.select('a.m-r-sm'))>1:flags.append('multiple_visible_authors_requires_reading')
 title=norm(article.select_one('header h1').get_text(' ',strip=True)) if article and article.select_one('header h1') else None
 if title!=norm(p.get('title')):flags.append('visible_title_difference')
 if not article or not body or not lead:flags.append('unrecognized_article_body_structure')
 if article and not article.select_one('header h1'):flags.append('missing_expected_visible_h1')
 if not p.get('title'):
  source_titles=[norm(x.get('content')) for x in soup.select('meta[property="og:title"],meta[name="twitter:title"]')]
  source_titles+=[norm(soup.title.get_text()) if soup.title else None]
  source_titles+=[norm(x.get_text()) for x in article.select('header h2,header h3,header [itemprop="headline"]')] if article else []
  if any(source_titles):flags.append('available_title_metadata_while_title_missing')
 if p.get('status')!=200:flags.append('http_or_transport_status')
 if p.get('content_type') and 'html' not in p['content_type'].lower():flags.append('non_html_response')
 if p.get('date_conflict'):flags.append('reported_date_conflict')
 meta=json.loads(p.get('sample_metadata_json') or '{}');day=meta.get('discovery_day') or (meta.get('discovery_publication_date') or '')[:10]
 published=p.get('date_published')
 if published:
  try:datetime.fromisoformat(published.replace('Z','+00:00'))
  except (ValueError,TypeError):flags.append('invalid_article_date')
  if day and published[:10]!=day:flags.append('article_vs_discovery_day_difference')
  if not '2018-01-01'<=published[:10]<='2025-12-31':flags.append('outside_target_publication_date')
 else:flags.append('missing_article_date')
 byline=norm(lead.get_text(' ',strip=True)).split('Por:',1)[-1] if lead else None
 months={'enero':1,'febrero':2,'marzo':3,'abril':4,'mayo':5,'junio':6,'julio':7,'agosto':8,'septiembre':9,'setiembre':9,'octubre':10,'noviembre':11,'diciembre':12}
 visible_date=re.search(r'(\d{1,2})\s+('+'|'.join(months)+r')\s+(\d{4})\s+(\d{1,2}):(\d{2})',byline or '',re.I)
 if not visible_date:flags.append('unrecognized_visible_byline_date')
 elif published:
  dd,mm,yy,hh,mi=visible_date.groups()
  visible_minute=f'{int(yy):04d}-{months[mm.lower()]:02d}-{int(dd):02d}T{int(hh):02d}:{int(mi):02d}'
  if published[:16]!=visible_minute:flags.append('visible_byline_date_difference')
 ld_articles=[]
 def scan_ld(value):
  if isinstance(value,dict):
   types=value.get('@type',[]);types=[types] if isinstance(types,str) else types
   if isinstance(types,list) and set(types)&{'NewsArticle','Article','ReportageNewsArticle'}:ld_articles.append(value)
   for v in value.values():
    if isinstance(v,(dict,list)):scan_ld(v)
  elif isinstance(value,list):
   for v in value:scan_ld(v)
 for script in soup.select('script[type="application/ld+json"]'):
  try:scan_ld(json.loads(script.get_text(),strict=False))
  except (ValueError,TypeError):flags.append('unparseable_jsonld_requires_reading')
 if len(ld_articles)>1:flags.append('multiple_jsonld_articles_requires_reading')
 elif len(ld_articles)==1:
  if published and ld_articles[0].get('datePublished')!=published:flags.append('article_vs_jsonld_date_difference')
  if not p.get('title') and any(norm(ld_articles[0].get(k)) for k in ['headline','name','alternativeHeadline']):flags.append('available_jsonld_title_while_title_missing')
 author=norm(lead.select_one('a.m-r-sm').get_text(' ',strip=True)) if lead and lead.select_one('a.m-r-sm') else None
 if author!=norm(p.get('authors')):flags.append('visible_author_difference')
 og=[x.get('content') for x in soup.select('meta[property="og:article:published_time"],meta[property="article:published_time"]')]
 if published and any(v and v!=published for v in og):flags.append('article_vs_og_date_difference')
 canonical=[x.get('href') for x in soup.select('link[rel="canonical"]')]
 declared=[value.strip() for value in canonical if isinstance(value,str) and value.strip()]
 identities=set()
 for value in declared:
  try:identities.add(normalize_url(urljoin(p.get('final_url') or p.get('url') or '',value)))
  except ValueError:flags.append('invalid_canonical_source_identity')
 if not declared:flags.append('missing_canonical_source_evidence')
 elif len(identities)>1:flags.append('ambiguous_canonical_source_identity')
 elif p.get('canonical_url'):
  try:
   if normalize_url(p['canonical_url']) not in identities:flags.append('canonical_source_difference')
  except ValueError:flags.append('invalid_canonical_output_identity')
 else:flags.append('missing_canonical_output_field')
 bodytext='';known_ui=[]
 media=[]
 if body:
  media=[x.get('src') for x in body.select('iframe[src]')]+[x.get('cite') for x in body.select('blockquote[cite]')]+[x.get('data-instgrm-permalink') for x in body.select('blockquote.instagram-media[data-instgrm-permalink]')]+[x.get('href') for x in body.select('blockquote.twitter-tweet a[href]') if re.search(r'/status/\d+',x.get('href',''))]
  clone=BeautifulSoup(str(body),'html.parser')
  for x in clone(['script','style','iframe']):x.decompose()
  for x in clone.find_all(string=lambda x:isinstance(x,Comment)):x.extract()
  known_ui=remove_known_instagram_ui(clone)
  bodytext=clone.get_text('',strip=False)
 if lead:
  leadtext=lead.get_text('',strip=False).split('Por:',1)[0]
  if compact(leadtext)!=compact(p.get('summary')):flags.append('visible_summary_difference')
  if compact(leadtext+bodytext)!=compact(p.get('main_text')):flags.append('raw_visible_body_difference_requires_reading')
 output_media=p.get('media_embeds') or []
 if isinstance(output_media,str):
  try:output_media=json.loads(output_media)
  except ValueError:output_media=[];flags.append('invalid_media_json')
 if set(media)!=set(output_media):flags.append('source_vs_output_media_difference')
 chars=len(p.get('main_text') or '')
 if chars<200:flags.append('suspicious_very_short_body_review_only')
 if not p.get('main_text'):flags.append('missing_body')
 if p.get('qa_status')=='success' and not all(p.get(k) for k in ['title','main_text','date_published','canonical_url']):flags.append('success_missing_core_fields')
 route=urlsplit(p.get('canonical_url') or '').path.strip('/').split('/')[0] or None
 hosts=sorted({urlsplit(u).hostname for u in media if isinstance(u,str) and urlsplit(u).hostname})
 layout={'article_count':len(articles),'body_count':len(bodies),'lead_count':len(leads),'article_post':bool(article),'lead':bool(lead),'body_container':bool(body),'table':bool(body and body.find('table')),'list':bool(body and body.find(['ul','ol'])),'body_heading':bool(body and body.find(['h1','h2','h3','h4'])),'social_quote':bool(body and body.select('blockquote.twitter-tweet,blockquote.instagram-media')),'body_dom_paths':dom_paths(body),'lead_dom_paths':dom_paths(lead),'header_dom_paths':dom_paths(article.select_one('header') if article else None)}
 types=([f'route:{route}'] if route else [])+['embed_host:'+h for h in hosts]+['layout:'+json.dumps(layout,sort_keys=True,separators=(',',':'))]
 rec={'sample_id':p['sample_id'],'url':p['url'],'article_date':published,'discovery_day':day,'route':route,'chars':chars,'error':p.get('error'),'qa_status':p.get('qa_status'),'confirmed_source_empty':confirmed_empty(p),'automatic_flags':sorted(set(flags)),'observed_types':types,'body_compact_sha256':hashlib.sha256(compact(p.get('main_text')).encode()).hexdigest() if p.get('main_text') else None,'snapshot_sha256':p.get('snapshot_sha256'),'fields_sha256':fields_digest(p),'manual_review_status':'not_reviewed'}
 rec['independently_recognized_template_ui']=known_ui
 rec['outside_body_scope_evidence']=outside_caption_evidence

 if p.get('error') and not confirmed_empty(p):rec['automatic_flags'].append('unexplained_result_error')
 if p.get('source_specific_error'):rec['automatic_flags'].append('source_specific_error')
 if p.get('status') != 200:rec['automatic_flags'].append('non_200_response')
 rec['automatic_flags']=sorted(set(rec['automatic_flags']))

 if p.get('title'):
  heading=norm(html.unescape(p['title']))
  title_channels=[norm(html.unescape(x.get('content') or '')) for x in soup.select('meta[property="og:title"],meta[name="twitter:title"]')]
  title_channels += [norm(html.unescape(soup.title.get_text()))] if soup.title else []
  title_channels += [norm(html.unescape(x.get('headline') or '')) for x in ld_articles]
  if any(v and v!=heading for v in title_channels):rec['automatic_flags'].append('source_title_metadata_disagreement')
 rec['automatic_flags']=sorted(set(rec['automatic_flags']))
 rec['signature']=hashlib.sha256(json.dumps([rec['observed_types'],'source_empty_title' if confirmed_empty(p) else 'present_title'],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
 return rec


def _registry_evidence(review_sources):
    exemplars=[];bindings={};skipped=Counter()
    for directory in sorted({Path(p).resolve() for p in review_sources}):
        manifest_path=directory/'manifest.json';annotation=directory/'review_annotations.json';db_path=directory/'pilot.sqlite'
        manifest=json.loads(manifest_path.read_text());require(manifest.get('source_id')=='tiempo','Registry source is not a bound Tiempo pilot')
        before={str(p):sha_file(p) for p in [manifest_path,annotation,db_path]}
        with sqlite3.connect(db_path.as_uri()+'?mode=ro&immutable=1',uri=True) as db:
            db.row_factory=sqlite3.Row
            pilot.validate_bound_state(db,directory,manifest['items'],manifest['input_sha256'])
            rows=[json.loads(r[0]) for r in db.execute('SELECT payload_json FROM articles ORDER BY ordinal')]
        reviewed,_=apply_reviews(rows,annotation)
        for row in reviewed:
            if row['manual_review_status']!='reviewed' or row['manual_review_result'] not in {'PASS','PASS_SOURCE_GAP_RECORDED'}:
                skipped['not_current_passing_review']+=1;continue
            if row.get('qa_status')!='success' and not confirmed_empty(row):
                skipped['reviewed_error_page_is_not_article_template']+=1;continue
            result=diagnose(row,directory)
            if result['automatic_flags']:
                skipped['reviewed_but_automatic_differences_unresolved']+=1;continue
            exemplars.append({'source_dir':str(directory),'sample_id':row['sample_id'],'url':row['url'],
                'snapshot_path':str((directory/row['snapshot_path']).resolve()),'snapshot_sha256':row['snapshot_sha256'],
                'fields_sha256':fields_digest(row),'signature':result['signature'],'observed_types':result['observed_types'],
                'source_empty_title':confirmed_empty(row),'review_result':row['manual_review_result'],
                'source_quality_issue':row.get('source_quality_issue'),'review_note':row['manual_review_note']})
        require(before=={p:sha_file(p) for p in before},'Registry source changed during read')
        bindings.update(before)
    require(exemplars,'No eligible actually reviewed clean article templates')
    return {'review_sources':sorted({str(Path(p).resolve()) for p in review_sources}),'source_sha256':bindings,
            'exemplars':exemplars,'known_signatures':sorted({e['signature'] for e in exemplars}),'skipped':dict(skipped)}


def build_registry(review_sources,output_path):
    """Offline explicit action, never writes a pilot or upgrades an unreviewed row."""
    path=Path(output_path);require(not path.exists(),'Registry output exists; preserve it and choose a new version')
    evidence=_registry_evidence(review_sources)
    registry={'schema':SCHEMA,'author':'Kevin','created_at':datetime.now(timezone.utc).isoformat(),
        'checker_sha256':sha_file(Path(__file__)),'state':'reviewed_examples_only_not_future_review',**evidence}
    pilot.atomic_bytes(path,encoded(registry))
    return registry


def load_registry(path,expected_sha256):
    path=Path(path);require(sha_file(path)==expected_sha256,'Registry file hash changed')
    data=json.loads(path.read_text());require(data.get('schema')==SCHEMA,'Wrong registry schema')
    require(data.get('checker_sha256')==sha_file(Path(__file__)),'Registry checker version changed')
    actual=_registry_evidence(data['review_sources'])
    require(all(data.get(k)==v for k,v in actual.items()),'Registry exemplars, reviews or known signatures changed')
    return data

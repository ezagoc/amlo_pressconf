"""Reconcile every original flagged case with current rules and actual date rosters."""
import csv,json,re,unicodedata
from collections import defaultdict,Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/flagged-outlets-20261026'
def read(p):
 with open(p) as f:return list(csv.DictReader(f))
norm=lambda s:re.sub('[^a-z0-9]','',unicodedata.normalize('NFKD',str(s or '').lower()).encode('ascii','ignore').decode())
inv=json.loads((OUT/'initial_inventory.json').read_text());cfg=json.loads((OUT/'decisions.json').read_text())
q=read('/tmp/sheinbaum-current-mapped.csv');a=read('/tmp/attendance-current-clean.csv');raw=read('/tmp/attendance-original.csv')
# Display identities restored by correcting overmatches, without losing their
# attendance gaps when they leave the original parent label's counts.
for i,outlet in enumerate(['ap noticias','agora celaya','bloomberg linea','bloomberg'],201):
 inv.append({'outlet':outlet,'roster_row':i,'metadata_names':[],
  'review_origin':'restored identity','introductions':[r for r in q if r['outlet_aux']==outlet]})
bydate=defaultdict(list)
for r in raw:bydate[r['fecha'][:10]].append(r)
att=defaultdict(list)
for r in a:
 if r['attendance_assumed']=='FALSE' and r['outlet_final'] not in ['','NA']:att[(r['fecha'][:10],norm(r['outlet_final']))].append(r)
qbyid={r['record_id']:r for r in q};groupmap={b:g['canonical'] for g in cfg['groups'] for b in g['brands']}
# Match current canonical keys; aliases from earlier approved groupings remain available.
previous={'el politico en las redes':'sin linea','puente libre mx':'tiempo la noticia digital','teleurban':'w radio','frecuencia cad':'jaime farias informa','es ahora am':'jaime farias informa','empuje migrante':'oro solido','hidalgo news':'mexico news world','capital':'capital puebla'}
canon=lambda o:groupmap.get(o,previous.get(o,o))
# Existing source IDs can differ without defining different analysis groups.
attendance_key={'losreporterosmx':'reporteros mx','grupo acir':'acir',
 'laboratorio de periodismo y opinion publica':'poplab'}
def hits_for(day,target):return att.get((day,norm(attendance_key.get(target,target))),[])
# Only pairs inspected in this review may provide date-specific joint links.
# Radio Tepoztlan is Benet's stated primary affiliation on 2025-08-22;
# do not infer links to Mexican parent brands from Heraldo USA/Jornada del Campo.
dated_pairs={('10 am mx','jaime farias informa'),('enlace mesoamerica','diario plaza juarez'),
 ('tv migrante','canal 14 spr'),('sandraaguileracom','grupo larsa comunicaciones'),
 ('miled','perspectivas'),('ecos media','luces del siglo'),('lja','sonora power'),
 ('radio educacion','amarc'),('imer','amarc'),('rompeviento tv','amarc')}
peers=defaultdict(list)
for r in q:peers[(r['date'],r['evidence_text'])].append(r)
prior=read(ROOT/'info_newspapers_gpt/outlet_review_20261016/sheinbaum_date_matches/reviewed_date_crosswalk.csv')
# These prior links are evidence-specific, never a global mapping of attendance labels.
priorlinks=defaultdict(list)
for r in prior:
 if r['usable_without_identity_conflict']=='true':priorlinks[(canon(r['question_outlet_id']),r['event_date'])].append(r)
links=[];events=[];results=[]
for old in inv:
 o=old['outlet'];target=canon(o);g=[r for r in q if r['outlet_aux']==target]
 # For already-grouped manual aliases that aren't in the explicit mapping above.
 if not g:
  targets={qbyid[x['record_id']]['outlet_aux'] for x in old['introductions'] if x['record_id'] in qbyid}
  if len(targets)==1:target=targets.pop();g=[r for r in q if r['outlet_aux']==target]
 ds=sorted({r['date'] for r in g});inside=[d for d in ds if d<='2025-09-30'];missing=[];gaps=[];matches=[];dated=[];labels=set()
 for day in inside:
  intro=[r for r in g if r['date']==day];hits=hits_for(day,target);method='canonical identity'
  if not hits:
   sibling_hits=[]
   for r in intro:
    for sibling in peers[(day,r['evidence_text'])]:
     if (target,sibling['outlet_aux']) in dated_pairs:
      if target=='miled' and r['reporter_aux']!='judith sanchez reyes':continue
      if target in ['radio educacion','imer','rompeviento tv'] and day!='2025-08-22':continue
      for ar in hits_for(day,sibling['outlet_aux']):sibling_hits.append((ar,sibling,r))
   if sibling_hits:
    hits=[x[0] for x in sibling_hits];method='explicit joint introduction on this date';dated.append(day)
    for ar,sib,r in sibling_hits:links.append({'outlet':target,'date':day,'attendance_label':ar['medios'],'attendance_canonical':ar['outlet_final'],'coaffiliation':sib['outlet_aux'],'evidence_text':r['evidence_text'],'source_url':r['source_url'],'method':method})
  if not hits:
   for prior in priorlinks.get((target,day),[]):
    actual=[r for r in bydate[day] if r['medios']==prior['attendance_label'] and r['eligible_role']=='TRUE']
    if actual:
     hits+=actual;method='previously reviewed dated affiliation';dated.append(day)
     links.append({'outlet':target,'date':day,'attendance_label':prior['attendance_label'],'attendance_canonical':'dated link only','coaffiliation':'see evidence','evidence_text':prior['evidence_text'],'source_url':prior['question_source_url'],'method':method})
  if not hits and target=='alianza de medios independientes' and day in ['2024-10-03','2024-10-31']:
   # Both introductions explicitly identify Pie de Pagina. Keep this date-specific.
   actual=[r for r in bydate[day] if 'piedepagina' in norm(r['medios']) and r['eligible_role']=='TRUE']
   if actual and any('piedepagina' in norm(r['evidence_text']) for r in intro):
    hits=actual;method='explicit Pie de Pagina identification on this date';dated.append(day)
    for ar in actual:links.append({'outlet':target,'date':day,'attendance_label':ar['medios'],'attendance_canonical':'dated link only','coaffiliation':'pie de pagina','evidence_text':intro[0]['evidence_text'],'source_url':intro[0]['source_url'],'method':method})
  hitlabels=sorted({r['medios'] for r in hits});labels.update(hitlabels)
  if hits:matches.append(day);status='Matched'
  elif len(bydate[day])<=1:gaps.append(day);status='Roster missing or sparse'
  else:missing.append(day);status='No verified label in available roster'
  events.append({'review_outlet':o,'canonical_id':target,'date':day,'status':status,'method':method if hits else '', 'raw_roster_rows':len(bydate[day]),'attendance_labels':'; '.join(hitlabels),'reporters':'; '.join(sorted({r['reporter_aux'] for r in intro if r['reporter_aux']})),'evidence_text':'\n'.join(dict.fromkeys(r['evidence_text'] for r in intro)),'source_urls':'\n'.join(dict.fromkeys(r['source_url'] for r in intro))})
 note=cfg['notes'].get(o,'')
 group=next((r for r in cfg['groups'] if r['canonical']==target),None)
 if group:note=(group['basis']+' '+note).strip()
 if not inside:status='Outside attendance coverage'
 elif missing:status='Reviewed; unmatched dates remain'
 elif gaps:status='Matched except roster gaps'
 else:status='Resolved'
 if dated:note+=' Dated co-affiliation links used without globally merging the other outlet.'
 if gaps:note+=' Missing/sparse rosters: '+', '.join(gaps)+'.'
 if missing:note+=' No verified label on: '+', '.join(missing)+'. Do not infer absence.'
 if o=='pridemx':note+=' PRIDE is a possible shortened attendance label; identity not independently verified.'
 if o=='asi lo dice la mont' and not group:note+=' ABC RADIO 760 AM is a candidate only; introduction also says 1530. No automatic reassignment.'
 aa=[r for r in a if r['attendance_assumed']=='FALSE' and norm(r['outlet_final'])==norm(attendance_key.get(target,target))]
 result={k:v for k,v in old.items() if k not in ['introductions']};result.update(canonical_id=target,transcript_dates=len(ds),in_period=len(inside),matches=len(matches),unmatched=missing,coverage_gaps=gaps,dated_matches=sorted(set(dated)),status=status,note=note.strip(),reporters=sorted({r['reporter_aux'] for r in g if r['reporter_aux']}),attendance_labels=sorted(labels),recorded_attendance_dates=len({r['fecha'][:10] for r in aa if r['fecha'][:10]>='2024-10-01'}|set(dated)),all_attendance_dates=len({r['fecha'][:10] for r in aa}|set(dated)),after_coverage=len(ds)-len(inside),first_date=min(ds) if ds else None,last_date=max(ds) if ds else None)
 results.append(result)
# One row per outlet/date/raw-label, never interpreted as extra physical attendance.
links=list({(r['outlet'],r['date'],r['attendance_label']):r for r in links}.values())
for link in links:assert any(r['fecha'][:10]==link['date'] and r['medios']==link['attendance_label'] and r['eligible_role']=='TRUE' for r in raw)
for name,rows in [('dated_question_attendance_links.csv',links),('reviewed_question_dates.csv',events)]:
 with (OUT/name).open('w') as f:w=csv.DictWriter(f,rows[0].keys());w.writeheader();w.writerows(rows)
(OUT/'review_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
print('Original flagged status counts',dict(Counter(r['status'] for r in results if r.get('review_origin')!='restored identity')))
print('Validated dated links:',len(links))
for r in results:
 if r['unmatched']:print(r['outlet'],str(r['matches'])+'/'+str(r['in_period']),r['unmatched'])

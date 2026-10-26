"""Apply explicit reviewed decisions, preserving manual rules outside marked blocks."""
import csv,json,re,unicodedata
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];cfg=json.loads((ROOT/'outputs/flagged-outlets-20261026/decisions.json').read_text())
def norm(s):return re.sub(r'[^a-z0-9]+',' ',unicodedata.normalize('NFKD',s.lower()).encode('ascii','ignore').decode()).strip()
for kind in ['attendance','question']:
 p=ROOT/f'info_newspapers_gpt/{kind}_aliases_20261016.tsv'
 with p.open() as f:r=csv.DictReader(f,delimiter='\t');fields=r.fieldnames;rows=list(r)
 for canonical,labels in cfg['aliases'].items():
  basis=next((g['basis'] for g in cfg['groups'] if g['canonical']==canonical),'Reviewed 2026-10-26: exact full/short name or spelling supported by transcript introductions and raw attendance labels. No fuzzy matching.')
  for label in labels:
   hits=[r for r in rows if norm(r['alias'])==norm(label)];assert len(hits)<=1
   row=hits[0] if hits else {'alias':label};row['canonical_id']=canonical
   if kind=='attendance':row.update(status='reviewed',reason=basis,source='Flagged-outlet review 2026-10-26; decisions.json and source introductions in review audit')
   if not hits:rows.append(row)
 assert len({norm(r['alias']) for r in rows})==len(rows)
 with p.open('w') as f:w=csv.DictWriter(f,fields,delimiter='\t');w.writeheader();w.writerows(rows)
# Explicit R cases retain the user's editing format.
p=ROOT/'code/03-cleaning_conf/question_class/sheinbaum/05_deduplicate_outlets_periodistas.R';s=p.read_text()
start='# BEGIN flagged outlet corrections 2026-10-26';end='# END flagged outlet corrections 2026-10-26'
block='''# BEGIN flagged outlet corrections 2026-10-26
# Restore distinct identities before preserving each brand.
df <- df |> mutate(outlet_aux = case_when(
  outlet_aux_before == "ap noticias" ~ "ap noticias",
  outlet_aux_before %in% c("bloomberg linea", "bloomberg news", "bloomberg") ~ outlet_aux_before,
  reporter_aux == "gabriela montejano" & outlet_aux_before == "agora" ~ "agora celaya",
  reporter_aux == "abel cuapa" & outlet_aux_before == "capital" ~ "capital puebla",
  TRUE ~ outlet_aux))
# END flagged outlet corrections 2026-10-26
'''
if start in s:s=re.sub(re.escape(start)+r'.*?'+re.escape(end)+'\n',lambda m:block,s,flags=re.S)
else:s=s.replace('# Keep the brands visible while combining their conference records (2026-10-26).',block+'\n# Keep the brands visible while combining their conference records (2026-10-26).')
start='           # BEGIN approved flagged groups 2026-10-26';end='           # END approved flagged groups 2026-10-26'
lines=[start]
for g in cfg['groups']:
 brands=[b for b in g['brands'] if b!=g['canonical']]
 if brands:lines.append('           outlet_aux %in% c('+', '.join(json.dumps(x) for x in brands)+') ~ '+json.dumps(g['canonical'])+',')
lines.append(end);block='\n'.join(lines)+'\n'
if start in s:s=re.sub(re.escape(start)+r'.*?'+re.escape(end)+'\n',lambda m:block,s,flags=re.S)
else:s=s.replace('           TRUE ~ outlet_aux))\n\nchanged_rows',block+'           TRUE ~ outlet_aux))\n\nchanged_rows')
p.write_text(s)
# Metadata names are independent brand rows; only conference source IDs change.
p=ROOT/'src/metadata_helpers.R';s=p.read_text();start='  # BEGIN approved flagged metadata 2026-10-26';end='  # END approved flagged metadata 2026-10-26';lines=[start]
for g in cfg['groups']:
 names=[unicodedata.normalize('NFKD',x.lower()).encode('ascii','ignore').decode().strip() for x in g['metadata_names']]
 lines+=['  selected <- name %in% c('+', '.join(json.dumps(x) for x in names)+')',
         '  metadata$names.conference[selected] <- '+json.dumps(g['canonical']),
         '  metadata$names.transcripts[selected] <- '+json.dumps(g['canonical'])]
lines.append(end);block='\n'.join(lines)+'\n'
if start in s:s=re.sub(re.escape(start)+r'.*?'+re.escape(end)+'\n',lambda m:block,s,flags=re.S)
else:s=s.replace('  reporteros <-',block+'  reporteros <-')
p.write_text(s)
print('Applied',len(cfg['groups']),'approved groups and',len(cfg['aliases']),'exact alias families.')

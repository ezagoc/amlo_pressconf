"""Apply the user's 2026-10-26 Sin Línea / El Político analysis grouping."""
from pathlib import Path
import csv, json, shutil, hashlib, unicodedata, re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/sin-linea-20261026'
BACK = ROOT / 'recovery/sin-linea-20261026'
OUT.mkdir(parents=True, exist_ok=True)
BACK.mkdir(parents=True, exist_ok=True)
NOTE = ('User approved 2026-10-26: Sin Linea and El Politico en las Redes are one '
        'analysis outlet, sin linea. Original brand records remain as provenance. '
        'This supersedes the previous separate-brand analysis instruction. '
        'Politico.mx, Animal Politico and El Charro Politico remain separate. '
        'Uncertain reporter spellings are not merged.')
ALIASES = ['Sin Línea', 'Sin Línea MX', 'sinlinea', 'sinlineamx.com', 'Grupo Sin Línea',
           'El Político', 'El Político en las Redes', 'Revista El Político', 'revistaelpolitico.com']
FILES = ['info_newspapers_gpt/attendance_aliases_20261016.tsv',
         'info_newspapers_gpt/question_aliases_20261016.tsv',
         'info_newspapers_gpt/outlet_expansion_20261016.json',
         'info_newspapers_gpt/outlet_review_20261016/youtube_extraction_manifest.json',
         'code/03-cleaning_conf/question_class/sheinbaum/05_deduplicate_outlets_periodistas.R',
         'src/metadata_helpers.R', 'tests/test_reviewed_outlet_linkage.R']
if not (BACK/'manifest.json').exists():
    manifest=[]
    for source in [ROOT/f for f in FILES] + [Path('/Users/ezagoc/Dropbox/Media/data/00-newspaper_data')/f for f in ['mexican_newspapers.xlsx','newspaper_metadata.xlsx']]:
        target=BACK / source.name
        shutil.copy2(source,target)
        manifest.append(dict(source=str(source),backup=str(target),sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
    (BACK/'manifest.json').write_text(json.dumps(manifest,indent=2))

def norm(s):
    s=''.join(c for c in unicodedata.normalize('NFD',s.lower()) if unicodedata.category(c)!='Mn')
    return ' '.join(re.sub(r'[^\w\s]',' ',s).split())

for kind in ['attendance','question']:
    path=ROOT/f'info_newspapers_gpt/{kind}_aliases_20261016.tsv'
    with path.open() as f:
        reader=csv.DictReader(f,delimiter='\t'); fields=reader.fieldnames; rows=list(reader)
    for alias in ALIASES:
        matches=[r for r in rows if norm(r['alias'])==norm(alias)]
        assert len(matches)<=1
        row=matches[0] if matches else {'alias':alias}
        row['canonical_id']='sin linea'
        if kind=='attendance':
            row.update(status='reviewed',reason=NOTE,source='User decision 2026-10-26; official introductions, including 2024-10-18')
        if not matches: rows.append(row)
    with path.open('w') as f:
        writer=csv.DictWriter(f,fields,delimiter='\t'); writer.writeheader(); writer.writerows(rows)

for relative in FILES[2:4]:
    path=ROOT/relative; data=json.loads(path.read_text())
    for e in data['entries']:
        if e['id']=='el politico en las redes':
            e.update(linkage_id='sin linea',question_id='sin linea',analysis_merged_into='sin linea',
                     reviewed_at='2026-10-26',review_note=NOTE,youtube_check_status='merged_alias')
            if 'youtube' in e: e['youtube']['status']='merged_alias'
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

path=ROOT/FILES[4]; s=path.read_text()
s=s.replace('c("el politico", "el politico en las redes") ~ "el politico en las redes"',
            'c("el politico", "el politico en las redes", "revista el politico", "revistaelpolitico.com") ~ "sin linea"')
path.write_text(s)
path=ROOT/FILES[5]; s=path.read_text()
if 'sin_linea <-' not in s:
    s=s.replace('  reporteros <-', '  sin_linea <- name %in% "sin linea mx"\n  metadata$names.conference[sin_linea] <- "sin linea"\n  metadata$names.transcripts[sin_linea] <- "sin linea"\n  reporteros <-')
path.write_text(s)
path=ROOT/FILES[6]; s=path.read_text().replace('"revista posdata", "el politico en las redes", "legacy"','"revista posdata", "sin linea", "sin linea"')
path.write_text(s)
print('Backed up originals and updated exact aliases, rules and manifests.')

path=ROOT/'info_newspapers_gpt/outlet_review_20261016/youtube_review.csv'
backup=BACK/'youtube_review.csv'
if not backup.exists(): shutil.copy2(path,backup)
with path.open() as f:
    reader=csv.DictReader(f); fields=reader.fieldnames; rows=list(reader)
for row in rows:
    if row.get('outlet_record_id')=='el politico en las redes':
        for k in ['question_id','attendance_linkage_id']:
            if k in row: row[k]='sin linea'
        for k in ['note']:
            if k in row: row[k]=NOTE
        for k in ['youtube_status']:
            if k in row: row[k]='merged_alias'
        row['checked_at']='2026-10-26'
with path.open('w') as f:
    writer=csv.DictWriter(f,fields);writer.writeheader();writer.writerows(rows)

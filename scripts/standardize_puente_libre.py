"""Retain both brands but share their attendance/question source ID."""
from pathlib import Path
import csv,json,hashlib,shutil,re,unicodedata
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/puente-libre-20261026'; BACK=ROOT/'recovery/puente-libre-20261026'
OUT.mkdir(exist_ok=True);BACK.mkdir(parents=True,exist_ok=True)
(OUT/'staged').mkdir(exist_ok=True)
NOTE=('User approved 2026-10-26: retain Tiempo La Noticia Digital and PuenteLibreMX as separate brands and metadata rows; '
      'share tiempo la noticia digital for attendance and question records. Do not merge legal entities, ownership, '
      'websites or YouTube channels. Count a joint introduction once and never create a second physical attendee. '
      'Panel/report rebuilding is deferred.')
files=['info_newspapers_gpt/attendance_aliases_20261016.tsv','info_newspapers_gpt/question_aliases_20261016.tsv',
       'info_newspapers_gpt/outlet_expansion_20261016.json','info_newspapers_gpt/outlet_review_20261016/youtube_extraction_manifest.json',
       'info_newspapers_gpt/outlet_review_20261016/youtube_review.csv',
       'code/03-cleaning_conf/question_class/sheinbaum/05_deduplicate_outlets_periodistas.R','src/metadata_helpers.R',
       'tests/test_reviewed_outlet_linkage.R']
if not (BACK/'manifest.json').exists():
    manifest=[]
    for source in [ROOT/f for f in files]+[Path('/Users/ezagoc/Dropbox/Media/data/00-newspaper_data')/f for f in ['mexican_newspapers.xlsx','newspaper_metadata.xlsx']]:
        target=BACK/source.name;shutil.copy2(source,target)
        manifest.append(dict(source=str(source),backup=str(target),sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
    (BACK/'manifest.json').write_text(json.dumps(manifest,indent=2))
def norm(s):
    s=''.join(c for c in unicodedata.normalize('NFD',s.lower()) if unicodedata.category(c)!='Mn')
    return ' '.join(re.sub('[^a-z0-9]+',' ',s).split())
aliases=['Puente Libre','Puente Libre MX','PuenteLibreMX','puentelibre.mx','Tiempo La Noticia Digital',
         'Tiempo.com.mx','TIEMPO.COM.MX Y PUENTELIBRE.M']
for kind in ['attendance','question']:
    path=ROOT/f'info_newspapers_gpt/{kind}_aliases_20261016.tsv'
    with path.open() as f:
        r=csv.DictReader(f,delimiter='\t');fields=r.fieldnames;rows=list(r)
    for label in aliases:
        matches=[r for r in rows if norm(r['alias'])==norm(label)];assert len(matches)<=1
        row=matches[0] if matches else {'alias':label};row['canonical_id']='tiempo la noticia digital'
        if kind=='attendance':row.update(status='reviewed',reason=NOTE,source='https://www.tiempo.com.mx/; https://puentelibre.mx/; official joint introductions; user decision 2026-10-26')
        if not matches:rows.append(row)
    with path.open('w') as f:
        w=csv.DictWriter(f,fields,delimiter='\t');w.writeheader();w.writerows(rows)
for relative in files[2:4]:
    path=ROOT/relative;data=json.loads(path.read_text())
    for e in data['entries']:
        if 'puente libre' in e['id']:
            e.update(linkage_id='tiempo la noticia digital',question_id='tiempo la noticia digital',reviewed_at='2026-10-26',review_note=NOTE)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
path=ROOT/files[4]
with path.open() as f:
    r=csv.DictReader(f);fields=r.fieldnames;rows=list(r)
for row in rows:
    if 'puente libre' in row['outlet_record_id']:
        row.update(attendance_linkage_id='tiempo la noticia digital',question_id='tiempo la noticia digital',checked_at='2026-10-26',note=NOTE)
with path.open('w') as f:
    w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rows)
print('Backups and shared source-ID registries saved; brand/channel records retained.')

"""User-approved conference grouping: Empuje Migrante / Oro Solido."""
from pathlib import Path
import csv,json,hashlib,shutil,re,unicodedata
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/empuje-migrante-20261026'; BACK=ROOT/'recovery/empuje-migrante-20261026'
OUT.mkdir(exist_ok=True);BACK.mkdir(parents=True,exist_ok=True);(OUT/'staged').mkdir(exist_ok=True)
NOTE=('User approved 2026-10-26: Empuje Migrante and Oro Solido share oro solido '
      'for conference attendance and question records, retaining separate brands. '
      'Nancy Rodriguez explicitly identifies both on all 13 Sheinbaum dates. '
      'Six of eight dates within attendance coverage match. 2025-03-04 has only one '
      'raw attendance row; 2025-05-06 has no matching label. Do not impute attendance. '
      'Common ownership is not established. Panels/reports deferred.')
files=['info_newspapers_gpt/attendance_aliases_20261016.tsv','info_newspapers_gpt/question_aliases_20261016.tsv',
       'code/03-cleaning_conf/question_class/sheinbaum/05_deduplicate_outlets_periodistas.R',
       'src/metadata_helpers.R','tests/test_reviewed_outlet_linkage.R',
       'info_newspapers_gpt/oro_solido.md','info_newspapers_gpt/outlet_expansion_20261016.json',
       'info_newspapers_gpt/outlet_review_20261016/youtube_extraction_manifest.json',
       'info_newspapers_gpt/outlet_review_20261016/youtube_review.csv']
if not (BACK/'manifest.json').exists():
    manifest=[]
    for source in [ROOT/f for f in files]+[Path('/Users/ezagoc/Dropbox/Media/data/00-newspaper_data')/f for f in ['mexican_newspapers.xlsx','newspaper_metadata.xlsx']]:
        target=BACK/source.name;shutil.copy2(source,target)
        manifest.append(dict(source=str(source),backup=str(target),sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
    (BACK/'manifest.json').write_text(json.dumps(manifest,indent=2))
def norm(s):
    s=''.join(c for c in unicodedata.normalize('NFD',s.lower()) if unicodedata.category(c)!='Mn')
    return ' '.join(re.sub('[^a-z0-9]+',' ',s).split())
for kind in ['attendance','question']:
    path=ROOT/f'info_newspapers_gpt/{kind}_aliases_20261016.tsv'
    with path.open() as f:
        r=csv.DictReader(f,delimiter='\t');fields=r.fieldnames;rows=list(r)
    for label in ['Empuje Migrante','Oro Sólido']:
        matches=[r for r in rows if norm(r['alias'])==norm(label)];assert len(matches)<=1
        row=matches[0] if matches else {'alias':label};row['canonical_id']='oro solido'
        if kind=='attendance':row.update(status='reviewed',reason=NOTE,source='User decision 2026-10-26; official joint introductions; https://www.gob.mx/presidencia/articulos/version-estenografica-conferencia-de-prensa-de-la-presidenta-claudia-sheinbaum-pardo-del-26-de-noviembre-de-2024?idiom=es')
        if not matches:rows.append(row)
    with path.open('w') as f:
        w=csv.DictWriter(f,fields,delimiter='\t');w.writeheader();w.writerows(rows)
print('Backed up originals and saved exact shared conference-ID aliases.')

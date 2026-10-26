"""User-approved conference grouping: Frecuencia CAD / Es Ahora AM / JF Informa."""
from pathlib import Path
import csv,json,hashlib,shutil,re,unicodedata
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/frecuencia-cad-20261026'; BACK=ROOT/'recovery/frecuencia-cad-20261026'
OUT.mkdir(exist_ok=True);BACK.mkdir(parents=True,exist_ok=True);(OUT/'staged').mkdir(exist_ok=True)
NOTE=('User approved 2026-10-26: Frecuencia CAD, Es Ahora AM and JF Informa share '
      'jaime farias informa for attendance and question records. Preserve separate brands, '
      'ownership metadata and channels. Joint introductions support this conference grouping. '
      '2024-11-06 remains unmatched; no attendance imputation. 10 AM MX remains separate. '
      'Panels and reports deferred.')
files=['info_newspapers_gpt/attendance_aliases_20261016.tsv','info_newspapers_gpt/question_aliases_20261016.tsv',
       'code/03-cleaning_conf/question_class/sheinbaum/05_deduplicate_outlets_periodistas.R',
       'src/metadata_helpers.R','tests/test_reviewed_outlet_linkage.R',
       'info_newspapers_gpt/frecuencia_cad.md','info_newspapers_gpt/outlet_expansion_20261016.json',
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
    for label in ['JF Informa','Jaime Farias Informa','JF Informa desde Cancun',
                  'JF Informa desde Cancun y EsAhoraAM de Queretaro',
                  'Es Ahora AM','EsAhoraAM','EsAhoraAM.com','Es Ahora AM Noticias',
                  'Es Ahora AM Informa','Es AhoraAM Informa','EsAhoraAM Informa',
                  'Frecuencia CAD','FrecuenciaCAD','FrecuenciaCAD.com','Frecuencia CAD.com',
                  'frecuenciacadcom','frecuencia cadcom','esahoraamcom','es ahora amcom']:
        matches=[r for r in rows if norm(r['alias'])==norm(label)];assert len(matches)<=1
        row=matches[0] if matches else {'alias':label};row['canonical_id']='jaime farias informa'
        if kind=='attendance':row.update(status='reviewed',reason=NOTE,source='User decision 2026-10-26; official joint introductions; https://frecuenciacad.com/')
        if not matches:rows.append(row)
    with path.open('w') as f:
        w=csv.DictWriter(f,fields,delimiter='\t');w.writeheader();w.writerows(rows)
print('Backed up originals and saved exact shared conference-ID aliases.')

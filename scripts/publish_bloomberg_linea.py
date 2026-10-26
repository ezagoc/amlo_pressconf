"""Publish identity-only review outputs with backups and concurrent edit guards."""
from pathlib import Path
import hashlib,json,shutil,sys
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/flagged-outlets-20261026';STAGE=OUT/'staged'
BACK=ROOT/'recovery/flagged-outlets-20261026/published-bloomberg-linea';LIVE=Path('/Users/ezagoc/Dropbox/Media')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
if sys.argv[1]=='--prepare':
 assert not (BACK/'manifest.json').exists(),'Publication already prepared'
 BACK.mkdir(parents=True,exist_ok=True);files={}
 def add(folder,names):
  for n in names:files[STAGE/n]=LIVE/folder/n
 add('data/00-newspaper_data',['mexican_newspapers.xlsx','newspaper_metadata.xlsx'])
 add('data/02-conferences/raw/attendance/merged',['attendance_clean.parquet','bridge_outlets.xlsx'])
 add('data/02-conferences/auxiliar',['questions_dataset_dedup.parquet'])
 folder='data/02-conferences-sheinbaum/api_extraction/official-through-2026-10-15/auxiliar'
 add(folder,['journalist_media_mapped_records.parquet','periodistas_v2_all_years_dedup.parquet',
  'journalists_and_media_dedup.csv','manual_alias_audit.csv','manual_dedup_counts.csv'])
 files[OUT/'dated_question_attendance_links.csv']=LIVE/folder/'reviewed_dated_attendance_links_20261026.csv'
 files[STAGE/'sheinbaum_outlet_attendance_review.xlsx']=ROOT/'outputs/sheinbaum-roster-20261019/sheinbaum_outlet_attendance_review.xlsx'
 original=json.loads((BACK.parent/'published/manifest.json').read_text())
 for row in original:
  assert sha(Path(row['target']))==row['after_sha256'],'Live file changed since the previous publication'
 manifest=[]
 for source,target in files.items():
  assert source.is_file(),source
  before=sha(target);base=ROOT if target.is_relative_to(ROOT) else LIVE
  backup=BACK/('repo' if base==ROOT else 'media')/target.relative_to(base)
  if before:backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,backup)
  manifest.append(dict(source=str(source),target=str(target),backup=str(backup) if before else None,before_sha256=before,after_sha256=sha(source)))
 (BACK/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print('Prepared',len(manifest),'identity/review files.')
elif sys.argv[1]=='--refresh':
 manifest=json.loads((BACK/'manifest.json').read_text())
 for r in manifest:
  assert sha(Path(r['target']))==r['before_sha256'],f"Concurrent edit: {r['target']}"
  r['after_sha256']=sha(Path(r['source']))
 (BACK/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print('Refreshed staged hashes; original backups preserved.')
elif sys.argv[1]=='--publish':
 manifest=json.loads((BACK/'manifest.json').read_text())
 for r in manifest:
  assert sha(Path(r['target']))==r['before_sha256'],f"Concurrent edit: {r['target']}"
  assert sha(Path(r['source']))==r['after_sha256'],f"Staged file changed: {r['source']}"
 for r in manifest:
  target=Path(r['target']);target.parent.mkdir(parents=True,exist_ok=True)
  temp=target.with_name(target.name+'.flagged-staged');shutil.copy2(r['source'],temp)
  assert sha(temp)==r['after_sha256'];temp.replace(target)
 assert all(sha(Path(r['target']))==r['after_sha256'] for r in manifest)
 print('Published and verified',len(manifest),'files. Panels, processed metadata and reports were not rebuilt.')
else:raise SystemExit('Use --prepare or --publish')

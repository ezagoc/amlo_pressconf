"""Publish verified staged files, backing up originals and rejecting concurrent edits."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
DATA = Path('/Users/ezagoc/Dropbox/Media/data')
STAGE = ROOT / 'outputs/mexico-news-world-20261024/staged'
BACKUP = ROOT / 'recovery/mexico-news-world-20261024/published'
BACKUP.mkdir(exist_ok=True)
destinations = {}
for f in ['mexican_newspapers.xlsx','newspaper_metadata.xlsx']:
    destinations[f] = DATA / '00-newspaper_data' / f
for f in ['newspaper_metadata_geocoded.parquet',
          'newspaper_metadata_panel_weekly_2021_2022.parquet',
          'newspaper_metadata_panel_daily_2021_2022.parquet']:
    destinations[f] = DATA / '00-newspaper_data/processed' / f
for f in ['attendance_clean.parquet','bridge_outlets.xlsx']:
    destinations[f] = DATA / '02-conferences/raw/attendance/merged' / f
destinations['panel_attendance.parquet.gzip'] = DATA / '02-conferences/raw/attendance/panel_attendance.parquet.gzip'
for f in ['journalist_media_mapped_records.parquet','periodistas_v2_all_years_dedup.parquet',
          'journalists_and_media_dedup.csv','manual_alias_audit.csv','manual_dedup_counts.csv']:
    destinations[f] = DATA / '02-conferences-sheinbaum/api_extraction/official-through-2026-10-15/auxiliar' / f

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

initial = json.loads((BACKUP.parent/'manifest.json').read_text())
for r in initial:
    path = Path(r['source'])
    if path.suffix == '.xlsx':
        assert sha(path) == r['sha256'], f'Concurrent edit: {path}'
assert all((STAGE/f).is_file() for f in destinations)
manifest = []
for name,target in destinations.items():
    source = STAGE/name
    before = sha(target) if target.exists() else None
    backup = BACKUP/name
    assert not backup.exists(), f'Backup already exists: {backup}'
    if before:
        shutil.copy2(target,backup)
    manifest.append(dict(source=str(source),target=str(target),backup=str(backup) if before else None,
                         before_sha256=before,after_sha256=sha(source)))
(BACKUP/'manifest.json').write_text(json.dumps(manifest,indent=2))
for r in manifest:
    target=Path(r['target'])
    assert (sha(target) if target.exists() else None)==r['before_sha256']
    temp=target.with_name(target.name+'.olvera-staged')
    shutil.copy2(r['source'],temp)
    assert sha(temp)==r['after_sha256']
    temp.replace(target)
print(f'Published {len(manifest)} files; originals backed up at {BACKUP}')

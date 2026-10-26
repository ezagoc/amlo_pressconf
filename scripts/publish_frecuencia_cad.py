"""Publish staged analysis outputs with backups and concurrent-edit guards."""
from pathlib import Path
import hashlib,json,shutil,sys

ROOT=Path(__file__).resolve().parents[1]
STAGE=ROOT/'outputs/frecuencia-cad-20261026/staged'
BACK=ROOT/'recovery/frecuencia-cad-20261026/published'
LIVE=Path('/Users/ezagoc/Dropbox/Media')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None

if sys.argv[1]=='--prepare':
    assert not (BACK/'manifest.json').exists(),'Publication already prepared'
    BACK.mkdir(parents=True,exist_ok=True)
    files={}
    def add(folder,names):
        for name in names:files[STAGE/name]=LIVE/folder/name
    add('data/00-newspaper_data',['mexican_newspapers.xlsx','newspaper_metadata.xlsx'])
    # User paused panel rebuilding on 2026-10-26. Publish only the identity
    # inputs; keep all live processed metadata, panels and reports unchanged.
    add('data/02-conferences/raw/attendance/merged',['attendance_clean.parquet','bridge_outlets.xlsx'])
    add('data/02-conferences/auxiliar',['questions_dataset_dedup.parquet'])
    add('data/02-conferences-sheinbaum/api_extraction/official-through-2026-10-15/auxiliar',[
        'journalist_media_mapped_records.parquet','periodistas_v2_all_years_dedup.parquet',
        'journalists_and_media_dedup.csv','manual_alias_audit.csv','manual_dedup_counts.csv','frecuencia_cad_unmatched_attendance_dates.csv'])
    originals=json.loads((BACK.parent/'manifest.json').read_text())
    for row in originals:
        if row['source'].endswith('.xlsx'):assert sha(Path(row['source']))==row['sha256'],'Workbook changed during build'
    manifest=[]
    for source,target in files.items():
        assert source.is_file(),source
        before=sha(target)
        backup=BACK/('repo' if target.is_relative_to(ROOT) else 'media')/target.relative_to(ROOT if target.is_relative_to(ROOT) else LIVE)
        if before:
            backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,backup)
        manifest.append(dict(source=str(source),target=str(target),backup=str(backup) if before else None,
                             before_sha256=before,after_sha256=sha(source)))
    (BACK/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print('Prepared and backed up',len(manifest),'outputs')
elif sys.argv[1]=='--publish':
    manifest=json.loads((BACK/'manifest.json').read_text())
    for r in manifest:
        assert sha(Path(r['target']))==r['before_sha256'],f"Concurrent edit: {r['target']}"
        assert sha(Path(r['source']))==r['after_sha256'],f"Staged file changed: {r['source']}"
    for r in manifest:
        target=Path(r['target']);target.parent.mkdir(parents=True,exist_ok=True)
        temp=target.with_name(target.name+'.frecuencia-staged')
        shutil.copy2(r['source'],temp)
        assert sha(temp)==r['after_sha256']
        temp.replace(target)
    assert all(sha(Path(r['target']))==r['after_sha256'] for r in manifest)
    print('Published and verified',len(manifest),'files; backups:',BACK)
else:raise SystemExit('Use --prepare or --publish')

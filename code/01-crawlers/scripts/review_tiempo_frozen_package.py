"""Offline, non-mutating quality replay of a frozen Tiempo interim package.

Creates new sidecars only. It never resumes a campaign, edits input rows, applies
review approvals, or equates request records with distinct accepted articles.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, sys, tempfile, zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
from crawler_core.tiempo_html import tiempo_fields
from crawler_core.tiempo_continuous_source import diagnose
from crawler_core.tiempo_pilot import extract_result, clean
from crawler_core.tiempo_review import fields_digest

CORE=('title','summary','main_text','authors','date','date_published','date_modified','canonical_url','media_embeds')
def sha(b):return hashlib.sha256(b).hexdigest()
def dump(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def normalized(v):
    if v is None or (isinstance(v,float) and pd.isna(v)):return None
    return v

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--package',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();package=a.package.resolve();out=a.output.resolve()
    if out.exists():raise SystemExit('Output must be a new directory; refusing to replace a prior audit.')
    if out==package or package in out.parents:raise SystemExit('Output must be outside the frozen package.')
    def offline(event,args):
        if event in {'socket.connect','socket.connect_ex','socket.getaddrinfo'}:raise RuntimeError('Offline replay forbids network')
    sys.addaudithook(offline)
    root=package/'01_Task3';frame=pd.read_parquet(root/'data/all_2670.parquet');index=pd.read_csv(root/'sources/source_index.csv',keep_default_na=False).set_index('record_id')
    assert frame.package_record_id.is_unique and index.index.is_unique
    code_dir=Path(__file__).resolve().parents[1]/'crawler_core'
    code_hashes={f.name:sha(f.read_bytes()) for f in code_dir.glob('tiempo*.py')}
    out.mkdir(parents=True);rows=[];differences=[];flags=collections.Counter();kinds=collections.Counter()
    with zipfile.ZipFile(root/'sources/source_pages.zip') as z,tempfile.TemporaryDirectory(prefix='tiempo-offline-') as temp:
        temp=Path(temp)
        for n,old in enumerate(frame.to_dict('records')):
            old={k:normalized(v) for k,v in old.items()};src=index.loc[old['package_record_id']]
            raw=z.read(src.html_archive_member);mb=z.read(src.metadata_archive_member)
            assert sha(raw)==old['snapshot_sha256']==src.snapshot_sha256
            assert sha(mb)==src.metadata_sha256
            metadata=json.loads(mb);response={**metadata['response'],'text':raw.decode('utf-8')}
            (temp/'snapshot.html').write_bytes(raw);(temp/'snapshot.json').write_bytes(mb)
            snapshot={**metadata,'snapshot_path':'snapshot.html','snapshot_sha256':sha(raw)}
            row=extract_result({'sample_id':old['sample_id'],'url':old['url'],'ordinal':n,'expected_year':old['expected_year']},response,snapshot,'offline_replay','offline_replay',lambda text,*,url,source_id:tiempo_fields(text,url=url))
            check=diagnose(row,temp)
            changed=[]
            for key in CORE:
                if normalized(row.get(key))!=old.get(key):
                    changed.append(key);differences.append({'record_id':old['package_record_id'],'sample_id':old['sample_id'],'field':key,'original':old.get(key),'replay':normalized(row.get(key))})
            kind=row.get('article_kind');kinds[str(kind)]+=1;flags.update(check['automatic_flags'])
            rows.append({'record_id':old['package_record_id'],'sample_id':old['sample_id'],'url':old['url'],'snapshot_sha256':sha(raw),'snapshot_archive_member':src.html_archive_member,
                'original_title':old['title'],'replayed_title':row.get('title'),'source_title_status':row.get('source_title_status'),
                'directory_title_candidates':old.get('package_official_directory_titles_json'),'directory_source_refs':old.get('package_directory_refs_json'),
                'article_kind':kind,'classification_rule_version':row.get('classification_rule_version'),'media_evidence':row.get('media_evidence'),'media_embeds':row.get('media_embeds'),
                'body_text_available':bool(row.get('main_text')),'body_character_count':len(row.get('main_text') or ''),'publication_date':row.get('date_published'),
                'publication_date_source':row.get('publication_date_source'),'publication_date_evidence':row.get('publication_date_evidence'),
                'replay_error':row.get('error'),'core_fields_changed':json.dumps(changed),'automatic_flags':json.dumps(check['automatic_flags']),
                'source_markup_warnings':json.dumps(check.get('source_markup_warnings',[])),
                'source_content_warnings':json.dumps(check.get('source_content_warnings',[])),
                'historical_review_fields_match':fields_digest(row)==fields_digest(old),'new_human_review':False,'article_acceptance':False,
                'method':'Automated archived-source replay; no new human approval or live refetch.'})
            if (n+1)%500==0:print(f'Replayed {n+1} archived records',flush=True)
    side=pd.DataFrame(rows);side.to_csv(out/'Record_Quality_Sidecar.csv',index=False);side.to_parquet(out/'Record_Quality_Sidecar.parquet',index=False)
    pd.testing.assert_frame_equal(side,pd.read_parquet(out/'Record_Quality_Sidecar.parquet'))
    csv=pd.read_csv(out/'Record_Quality_Sidecar.csv',keep_default_na=False,dtype=str)
    assert len(csv)==len(side) and csv.record_id.tolist()==side.record_id.tolist()
    for c in side:
        assert csv[c].tolist()==side[c].map(lambda v:'' if v is None or (isinstance(v,float) and pd.isna(v)) else str(v)).tolist(),c
    dump(out/'Core_Field_Differences.json',differences)
    assert code_hashes=={f.name:sha(f.read_bytes()) for f in code_dir.glob('tiempo*.py')},'Code changed during replay; preserve this attempt and rerun in a new output directory.'
    summary={'author':'Kevin','scope':'Frozen interim request records only; no campaign migration or acceptance','input_rows':len(frame),'input_parquet_sha256':sha((root/'data/all_2670.parquet').read_bytes()),
        'source_hash_checks':len(rows)*2,'missing_original_titles':int(frame.title.isna().sum()),'missing_replayed_titles':int(side.replayed_title.isna().sum()),
        'core_field_difference_count':len(differences),'core_changed_records':sum(r['core_fields_changed']!='[]' for r in rows),'classification_counts':dict(kinds),'automatic_flag_counts':dict(flags),
        'historical_core_review_fields_match':int(side.historical_review_fields_match.sum()),'network_requests':0,'input_mutations':0,'csv_parquet_full_readback':'PASS',
        'human_reviews_created':0,'article_acceptance':False,'code_hashes':code_hashes}
    dump(out/'Replay_Summary.json',summary);print(json.dumps(summary,indent=2))
if __name__=='__main__':main()

"""Sheinbaum balance inputs: fresh sources, strict physical attendees, frozen histories.
Run from the repository root. Does not alter upstream panels or AMLO results.
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from project_paths import media_path
spec = importlib.util.spec_from_file_location('participation', ROOT/'code/07-final_panel/sheinbaum_participation.py')
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
OUT = ROOT/'output/balance/sheinbaum_12m'
START, END = pd.Timestamp('2023-10-01'), pd.Timestamp('2024-09-30')
POST_FROM, POST_TO = pd.Timestamp('2024-10-01'), pd.Timestamp('2025-06-15')  # User-specified lottery period.
META = ['media_print_any','media_digital','media_social_media','media_radio','media_television',
        'coverage_national','coverage_state','mexico_city','metropolitan_area']
HIST = ['question_attendance_ratio','contract_value','contract_count','videos','views','likes',
        'comments','interactions','views_per_video','likes_per_video','comments_per_video','interactions_per_video']
LABELS = ['Print / newspaper','Digital','Social media','Radio','Television','National coverage',
          'State coverage','Mexico City outlet','Metropolitan-area coverage',
          'Prior AMLO questions / attendance','Contract value (MXN)','Contracts received','YouTube videos',
          'YouTube views','YouTube likes','YouTube comments','YouTube interactions','Views per video',
          'Likes per video','Comments per video','Interactions per video']


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def source(path, columns=None):
    d = pd.read_parquet(path, columns=columns)
    if 'date' in d:
        d['date'] = helpers.dates(d.date)
    return d


def covered(d):
    return d.source_entity_matched.eq(True) & d.source_date_observed.eq(True)


def complete_sum(s):
    return s.sum() if len(s) and s.notna().all() else np.nan


def available_video_history(videos):
    """Observed archive totals; metric means use their own observed videos."""
    row = {'videos': len(videos)}
    metrics = {'views': videos.viewCount, 'likes': videos.likeCount,
               'comments': videos.commentCount,
               'interactions': videos.likeCount + videos.commentCount}
    for name, values in metrics.items():
        n = int(values.notna().sum())
        row[name + '_observed_videos'] = n
        row[name] = float(values.sum()) if n else (0 if not len(videos) else np.nan)
        row[name + '_per_video'] = float(values.mean()) if n else (0 if not len(videos) else np.nan)
    return row


def informative(d):
    counts = d.groupby('date').speaking_identified.nunique()
    return d[d.date.isin(counts[counts.eq(2)].index)].copy()


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    folder=media_path('data/06-outcomes/deduplicated_source_panels')
    paths={name:folder/f'{name}_entity_daily_panel.parquet' for name in ['attendance','questions','contracts','youtube']}
    paths['youtube']=media_path('data/06-outcomes/youtube/extended/youtube_entity_daily_panel.parquet')
    paths['youtube_crosswalk']=media_path('data/06-outcomes/youtube/extended/metadata_youtube_crosswalk.csv')
    paths['youtube_videos']=media_path('data/06-outcomes/youtube/extended/deduplicated_video_metrics.parquet')
    paths.update(metadata=media_path('data/00-newspaper_data/processed/newspaper_metadata_geocoded.parquet'),
      crosswalk=folder/'metadata_outcome_crosswalk.parquet',
      participation=media_path('data/02-conferences-sheinbaum/participation_panel/through-2026-10-15/outlet_conference_daily.parquet'))
    hashes={k:sha(v) for k,v in paths.items()}
    p=source(paths['participation']).rename(columns={'outlet_id':'unit_id','identified':'speaking_identified'})
    m=source(paths['metadata']); m['unit_id']=m['names.conference'].map(helpers.key).combine_first(m['names.transcripts'].map(helpers.key))
    m=m.dropna(subset=['unit_id']).copy()
    m['media_print_any']=m[['media_print','media_periodico']].fillna(0).max(axis=1)
    for c in ['national','state']:
        m[f'coverage_{c}']=m['coverage.scope'].fillna('').str.lower().str.contains(r'\b'+c+r'\b',regex=True).astype(int)
    m['mexico_city']=pd.to_numeric(m['city.headq'],errors='coerce').eq(9).astype(int)
    m['metropolitan_area']=m['coverage.scope'].fillna('').str.lower().str.contains(r'\bmetropolitan\b').astype(int)
    m[META]=m[META].fillna(0)
    assert m[META].isin([0,1]).all().all()
    units=m.groupby('unit_id')[META].max().reset_index()
    meta_links=m[['metadata_id','unit_id','name.page']].drop_duplicates()
    meta_links.to_csv(OUT/'metadata_links.csv',index=False)
    m[['metadata_id','unit_id','name.page','type.media','coverage.scope','city.headq']+META].to_csv(OUT/'metadata_coding.csv',index=False)
    cw=source(paths['crosswalk'])[['metadata_id','outcome','entity_id']].drop_duplicates()
    current_youtube=pd.read_csv(paths['youtube_crosswalk'])[['metadata_id','outcome','entity_id']].dropna().drop_duplicates()
    cw=pd.concat([cw[~cw.outcome.eq('youtube')],current_youtube],ignore_index=True)
    assets=meta_links[['metadata_id','unit_id']].merge(cw,on='metadata_id',validate='many_to_many')[['unit_id','outcome','entity_id']].drop_duplicates()
    assets.to_csv(OUT/'source_links.csv',index=False)
    # Histories use all distinct companies/channels per unit. Shared YouTube
    # entities are not copied into multiple prospective regression units.
    ylinks=assets[assets.outcome.eq('youtube')][['unit_id','entity_id']]
    shared=ylinks.groupby('entity_id').unit_id.nunique()
    ambiguous=set(shared[shared.gt(1)].index)
    ylinks=ylinks.assign(shared_across_conference_units=ylinks.entity_id.isin(ambiguous))
    ylinks.to_csv(OUT/'youtube_mapping_audit.csv',index=False)
    hist=pd.DataFrame({'unit_id':units.unit_id}).set_index('unit_id')

    # Prior access: allow only one-to-one attendance/question mappings. Missing
    # or ambiguous mappings remain missing histories, never zero participation.
    pairs=assets[assets.outcome.isin(['attendance','questions'])].pivot_table(index='unit_id',columns='outcome',values='entity_id',aggfunc=lambda x:tuple(sorted(set(x))))
    rows=[]
    for u,r in pairs.iterrows():
        a,q=r.get('attendance'),r.get('questions')
        if isinstance(a,tuple) and isinstance(q,tuple):
            rows += [{'unit_id':u,'attendance':aa,'questions':qq,'multiple_within_unit':len(a)!=1 or len(q)!=1} for aa in a for qq in q]
    pairs=pd.DataFrame(rows)
    pairs['ambiguous']=pairs.multiple_within_unit | pairs.attendance.map(pairs.groupby('attendance').questions.nunique()).gt(1) | pairs.questions.map(pairs.groupby('questions').attendance.nunique()).gt(1)
    pairs.to_csv(OUT/'prior_access_mapping.csv',index=False)
    ap=source(paths['attendance'],['entity_id','date','source_entity_matched','source_date_observed','attendance_n_journalists_recorded'])
    qp=source(paths['questions'],['entity_id','date','source_entity_matched','source_date_observed','questions_n'])
    ap=ap[ap.date.between(START,END)&covered(ap)].rename(columns={'entity_id':'attendance','attendance_n_journalists_recorded':'records'})
    qp=qp[qp.date.between(START,END)&covered(qp)].rename(columns={'entity_id':'questions'})
    aq=pairs[~pairs.ambiguous].merge(ap[['attendance','date','records']],on='attendance',validate='many_to_many').merge(qp[['questions','date','questions_n']],on=['questions','date'],validate='many_to_one')
    assert not aq.duplicated(['unit_id','date']).any()
    access=aq.groupby('unit_id').agg(prior_questions=('questions_n',complete_sum),prior_records=('records',complete_sum),common_dates=('date','nunique'),first_common=('date','min'),last_common=('date','max'))
    access['question_attendance_ratio']=access.prior_questions.div(access.prior_records.where(access.prior_records.gt(0)))
    access.to_csv(OUT/'prior_access_history.csv')
    hist=hist.join(access[['question_attendance_ratio']])

    # Contracts retain observed zero-award histories; unobserved history is NA.
    cp=source(paths['contracts'],['entity_id','date','source_entity_matched','source_date_observed','contracts_costo','contracts_received_n'])
    cp=cp[cp.date.between(START,END)&covered(cp)]
    cl=assets[assets.outcome.eq('contracts')][['unit_id','entity_id']]
    cd=cl.merge(cp,on='entity_id',validate='many_to_many')
    assert not cd.duplicated(['unit_id','entity_id','date']).any()
    ct=cd.groupby('unit_id').agg(contract_value=('contracts_costo',complete_sum),contract_count=('contracts_received_n',complete_sum),beneficiary_dates=('date','size'),beneficiaries=('entity_id','nunique'))
    ct.to_csv(OUT/'contract_histories.csv');hist=hist.join(ct[['contract_value','contract_count']])

    yc=['youtube_n_videos','youtube_views','youtube_likes','youtube_comments']
    yp=source(paths['youtube'],['entity_id','date','source_entity_matched','source_date_observed']+yc)
    yp['covered']=covered(yp)&yp[yc].notna().all(axis=1)
    yt=ylinks.merge(yp,on='entity_id',validate='many_to_many')
    assert not yt.duplicated(['unit_id','entity_id','date']).any()
    archived=source(paths['youtube_videos'])
    archived=archived[archived.date.between(START,END)].rename(columns={'channel_id':'entity_id'})
    archived=ylinks.merge(archived,on='entity_id',validate='many_to_many')
    assert not archived.duplicated(['unit_id','videoId']).any()
    video_groups={u:g for u,g in archived.groupby('unit_id')}
    empty=archived.iloc[:0]
    yh=[]
    for u,g in yt[yt.date.between(START,END)].groupby('unit_id'):
        expected=g.entity_id.nunique()*((END-START).days+1)
        complete=len(g)==expected and g.covered.all()
        row={'unit_id':u,'linked_entities':g.entity_id.nunique(),'observed_entity_days':int(g.covered.sum()),'expected_entity_days':expected,'complete_grid':bool(complete)}
        v=video_groups.get(u,empty)
        source_complete=len(g)==expected and covered(g).all()
        # User convention: linked channels with no saved videos in the window
        # receive zero activity; missing counters on existing videos stay NA.
        row.update(available_video_history(v))
        row['archived_channels']=v.entity_id.nunique()
        row['archive_source_complete']=bool(source_complete)
        yh.append(row)
    yh=pd.DataFrame(yh).set_index('unit_id');yh.to_csv(OUT/'youtube_histories.csv')
    hist=hist.join(yh[HIST[3:]])
    hist.to_csv(OUT/'histories_raw.csv')
    assert hist[HIST].drop(columns='question_attendance_ratio').stack().dropna().ge(0).all()
    transformed=hist.copy();transformed[HIST[1:]]=np.log1p(hist[HIST[1:]])
    units=units.merge(transformed.reset_index(),on='unit_id',validate='one_to_one')
    units.to_csv(OUT/'unit_covariates.csv',index=False)

    # Prospective YouTube sample: covered complete channel bundle, no ambiguous
    # shared entities; observed zero-video days remain in the sample.
    ypost=yt[yt.date.ge('2024-10-01')].groupby(['unit_id','date']).agg(yt_covered=('covered','all'),shared=('shared_across_conference_units','any'),n_entities=('entity_id','nunique'),videos=('youtube_n_videos','sum'))
    counts=ylinks.groupby('unit_id').entity_id.nunique()
    ypost['yt_eligible']=ypost.yt_covered & ~ypost.shared & ypost.n_entities.eq(ypost.index.get_level_values('unit_id').map(counts))
    ypost.reset_index().to_parquet(OUT/'youtube_date_coverage.parquet',index=False)
    p=p.merge(ypost[['yt_eligible']].reset_index(),how='left',on=['unit_id','date'],validate='one_to_one')
    p['yt_eligible']=p.yt_eligible.eq(True)
    eligible=p[p.date.between(POST_FROM,POST_TO) & p.common_coverage & p.recorded_attendance_n.gt(0)].copy()
    eligible.to_parquet(OUT/'all_recorded_attendees.parquet',index=False)
    no_meta=eligible[~eligible.unit_id.isin(units.unit_id)]
    no_meta.groupby('unit_id').agg(attendance_dates=('date','size'),identified_days=('speaking_identified','sum')).to_csv(OUT/'unmatched_metadata.csv')
    raw=eligible.merge(units,on='unit_id',how='inner',validate='many_to_one')
    flow=[]
    for name,d in [('all_recorded',eligible),('metadata_linked',raw),('full',informative(raw)),('youtube_eligible',raw[raw.yt_eligible]),('youtube_overlap',informative(raw[raw.yt_eligible]))]:
        flow.append(dict(sample=name,n=len(d),units=d.unit_id.nunique(),dates=d.date.nunique(),identified_days=int(d.speaking_identified.sum()),date_from=str(d.date.min().date()),date_to=str(d.date.max().date())))
        if name in ['full','youtube_overlap']:
            assert len(d) and not d.duplicated(['unit_id','date']).any() and d.recorded_attendance_n.gt(0).all()
            d.to_parquet(OUT/f'{name}_sample.parquet',index=False)
    pd.DataFrame(flow).to_csv(OUT/'sample_flow.csv',index=False)
    pd.DataFrame({'metric':META+HIST,'label':LABELS,'family':['Metadata']*9+['Access']+['Contracts']*2+['YouTube']*9,'transformation':['Raw']*10+['log(1+x)']*11}).to_csv(OUT/'spec.csv',index=False)
    assert hashes=={k:sha(v) for k,v in paths.items()}
    audit={'analysis_from':str(POST_FROM.date()),'analysis_through':str(POST_TO.date()),'cutoff_basis':'User specified June 15, 2025 as the lottery stopping date; do not extend the attendance-conditioned sample beyond it.','history_from':str(START.date()),'history_to':str(END.date()),'sample_flow':flow,'youtube_last_observed':str(yp.loc[yp.covered,'date'].max().date()),'ambiguous_youtube_entities':sorted(ambiguous),'metadata_covariates':META,'historical_covariates':HIST,'input_sha256':hashes,'input_paths':{k:str(v) for k,v in paths.items()},'inputs_unchanged':True,'treatment':'explicit outlet identification in transcript; proxy for speaking access, not exhaustive questions','attendance':'direct recorded REPORTERO/YOUTUBER only; dated links and imputed attendance excluded'}
    (OUT/'build_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    print(json.dumps({k:v for k,v in audit.items() if k not in ['input_sha256','input_paths']},indent=2))

if __name__=='__main__':
    main()

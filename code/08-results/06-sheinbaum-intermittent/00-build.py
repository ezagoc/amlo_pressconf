"""Full-calendar FEct inputs: five-weekday exposure spells including the speaking day."""
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from project_paths import media_path
START,END=pd.Timestamp('2024-10-01'),pd.Timestamp('2025-06-15')
OUT=media_path('results/sheinbaum/intermittent_did/five_weekdays_including_question')
OUTCOMES=['videos','interactions','mean_interactions','likes','comments','views']

def spell_status(ask,unknown,days=5):
    """Known positive event dominates unknown event history in the same window."""
    positive=pd.Series(ask).rolling(days,min_periods=1).max().eq(1)
    uncertain=pd.Series(unknown).rolling(days,min_periods=1).max().eq(1)
    return pd.Series(np.where(positive,1,np.where(uncertain,np.nan,0)))

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    base=media_path('data/02-conferences-sheinbaum/participation_panel/through-2026-10-15')
    paths={'youtube':ROOT/'output/balance/sheinbaum_12m/youtube_outlet_daily.parquet',
      'participation':base/'outlet_conference_daily.parquet','coverage':base/'conference_coverage.csv',
      'histories':ROOT/'output/balance/sheinbaum_12m/histories_raw.csv'}
    hashes={k:sha(p) for k,p in paths.items()}
    y=pd.read_parquet(paths['youtube']);y['date']=pd.to_datetime(y.date).dt.normalize()
    y=y[y.date.between(START,END)].rename(columns={'interactions_per_video':'mean_interactions'})
    assert not y.shared.any() and not y.duplicated(['unit_id','date']).any()
    p=pd.read_parquet(paths['participation']);p['date']=pd.to_datetime(p.date).dt.normalize()
    p=p.rename(columns={'outlet_id':'unit_id'})
    p=p[p.date.between(START,END)][['unit_id','date','identified','recorded_attendance_n']]
    cov=pd.read_csv(paths['coverage'],parse_dates=['date']);cov=cov[cov.date.between(START,END)]
    unknown_dates=set(cov.loc[~cov.transcript_observed,'date'])
    d=y.merge(p,on=['unit_id','date'],how='left',validate='one_to_one').sort_values(['unit_id','date']).reset_index(drop=True)
    d['ask']=d.identified.fillna(0).astype(int)
    d['recorded_attendance_n']=d.recorded_attendance_n.fillna(0)
    # Original AMLO full-calendar control: recorded presence OR explicit speaking.
    d['attendance_dummy']=(d.recorded_attendance_n.gt(0)|d.ask.eq(1)).astype(int)
    d['attendance_from_speaking_only']=(d.ask.eq(1)&d.recorded_attendance_n.eq(0))
    d['conference_in_sources']=d.date.isin(cov.date)
    d['unknown_question_day']=d.date.isin(unknown_dates)
    d['weekday']=d.date.dt.dayofweek.lt(5)
    assert not d.loc[~d.weekday,'ask'].any()
    weekday_dates=pd.bdate_range(START,END)
    d['sample_day']=d.date.map({day:i+1 for i,day in enumerate(weekday_dates)})
    d['D']=np.nan
    for _,g in d[d.weekday].groupby('unit_id',sort=False):
        d.loc[g.index,'D']=spell_status(g.ask.to_numpy(),g.unknown_question_day.to_numpy()).to_numpy()
    expected_days=(END-START).days+1
    assert d.groupby('unit_id').size().eq(expected_days).all()
    assert d[OUTCOMES].notna().all().all() and d[OUTCOMES].ge(0).all().all()
    assert (d.loc[d.videos.eq(0),['views','likes','comments','interactions']]==0).all().all()
    h=pd.read_csv(paths['histories'])[['unit_id','question_attendance_ratio']].rename(columns={'question_attendance_ratio':'prior_ratio'})
    d=d.merge(h,on='unit_id',how='left',validate='many_to_one')
    d['missing_ratio']=d.prior_ratio.isna().astype(int);d['ratio_filled']=d.prior_ratio.fillna(0)
    d['quarter']=d.date.dt.to_period('Q').astype(str);controls=[]
    for q in sorted(d.quarter.unique())[1:]:
        for prefix,value in [('history',d.ratio_filled),('missing',d.missing_ratio)]:
            c=prefix+'_'+q;d[c]=value*d.quarter.eq(q);controls.append(c)
    # Known missing transcript implies unknown treatment where no known event
    # already fixes D=1. Never code those cells as untreated; keep full source grid.
    d.to_parquet(OUT/'full_calendar.parquet',index=False)
    missing=d[d.weekday & d.D.isna()];missing[['unit_id','date','unknown_question_day']].to_csv(OUT/'unknown_treatment_cells.csv',index=False)
    model=d[d.weekday & d.D.notna()].copy();model['D']=model.D.astype(int)
    # Date fixed effects cannot be estimated where every known cell is treated.
    unsupported_dates=model.groupby('date').D.min().loc[lambda x:x.eq(1)].index
    unsupported=model[model.date.isin(unsupported_dates)]
    unsupported[['unit_id','date','D']].to_csv(OUT/'no_untreated_date_support.csv',index=False)
    model=model[~model.date.isin(unsupported_dates)].copy()
    cuts=[]
    for o in OUTCOMES:
        # R type-7 / pandas linear quantile, pooled analysis observations.
        upper=float(model[o].quantile(.99,interpolation='linear'))
        model['Y_'+o]=np.arcsinh(np.minimum(model[o],upper))
        cuts.append({'outcome':o,'upper':upper,'n':len(model),'capped':int(model[o].gt(upper).sum())})
    pd.DataFrame(cuts).to_csv(OUT/'winsorization_cutoffs.csv',index=False)
    model.to_parquet(OUT/'analysis_panel.parquet',index=False)
    support=model.groupby('unit_id').agg(n=('D','size'),untreated=('D',lambda s:int(s.eq(0).sum())),
      treated=('D','sum'),question_days=('ask','sum'),zero_video_days=('videos',lambda s:int(s.eq(0).sum())))
    support.to_csv(OUT/'unit_support.csv');assert support.untreated.ge(5).all()
    events=d[d.ask.eq(1)][['unit_id','date','sample_day']].copy()
    events['weekdays_since_previous']=events.groupby('unit_id').sample_day.diff()
    events['untruncated_window_end']=events.date+pd.offsets.BDay(4)
    events['days_inside_period']=(len(weekday_dates)-events.sample_day+1).clip(upper=5)
    events.to_csv(OUT/'speaking_events.csv',index=False)
    events[events.weekdays_since_previous.lt(5)].to_csv(OUT/'overlapping_event_windows.csv',index=False)
    result={'analysis_from':str(START.date()),'analysis_through':str(END.date()),
      'treatment':'D=1 on identified speaking day and next four weekdays; weekends omitted from estimation; repeated windows form their union.',
      'assumption':'One-week ballot exclusion and a five-weekday exposure horizon are assumed, not verified. No extension beyond June 15.',
      'full_rows':len(d),'units':d.unit_id.nunique(),'calendar_days':expected_days,'weekdays':len(weekday_dates),'weekend_cells':int((~d.weekday).sum()),'analysis_rows':len(model),
      'analysis_dates':model.date.nunique(),'treated_cells':int(model.D.sum()),'untreated_cells':int(model.D.eq(0).sum()),
      'identified_speaking_days':int(model.ask.sum()),'ever_treated_outlets':int(support.treated.gt(0).sum()),
      'zero_video_cells':int(model.videos.eq(0).sum()),'unknown_treatment_cells':len(missing),
      'no_untreated_date_support_cells':len(unsupported),'no_untreated_support_dates':[str(t.date()) for t in unsupported_dates],
      'missing_transcript_dates':[str(t.date()) for t in sorted(unknown_dates)],
      'observed_events_within_previous_five_weekday_window':int(events.weekdays_since_previous.lt(5).sum()),
      'right_truncated_event_windows':int(events.days_inside_period.lt(5).sum()),
      'attendance_inferred_from_speaking_cells':int(model.attendance_from_speaking_only.sum()),
      'outcomes':OUTCOMES,'history_controls':controls,'input_paths':{k:str(p) for k,p in paths.items()},'input_sha256':hashes}
    assert hashes=={k:sha(p) for k,p in paths.items()}
    (OUT/'build_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()

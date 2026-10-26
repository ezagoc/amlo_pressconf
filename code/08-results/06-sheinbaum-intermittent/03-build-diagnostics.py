"""Weekday-exact onset/exit holdouts and fixed alignment classification."""
import importlib.util
import json
from pathlib import Path
import numpy as np
import pandas as pd
spec=importlib.util.spec_from_file_location('base',Path(__file__).with_name('00-build.py'))
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
OUT=b.OUT/'diagnostics_heterogeneity'

def event_labels(status):
    """Label known 0->1 onsets and 1->0 exits without bridging unknown days.

    Pre/carry targets must be continuously untreated up to their boundary.
    An overlapping pre/carry cell is held out but not attributed to either.
    """
    z=np.asarray(status,float);n=len(z);pre=np.zeros(n,int);post=np.zeros(n,int)
    onset=np.zeros(n,bool);exit_=np.zeros(n,bool)
    for t in range(1,n):
        if z[t]==1 and z[t-1]==0:
            onset[t]=True
            for k in range(1,6):
                if t-k<0 or z[t-k]!=0:break
                pre[t-k]=-k
        if z[t]==0 and z[t-1]==1:
            exit_[t]=True
            for k in range(5):
                if t+k>=n or z[t+k]!=0:break
                post[t+k]=k+1
    return pre,post,onset,exit_

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    paths={'full':b.OUT/'full_calendar.parquet','analysis':b.OUT/'analysis_panel.parquet',
      'links':b.ROOT/'output/balance/sheinbaum_12m/metadata_links.csv',
      'metadata':b.media_path('data/00-newspaper_data/processed/newspaper_metadata_geocoded.parquet')}
    hashes={k:b.sha(p) for k,p in paths.items()}
    full=pd.read_parquet(paths['full']);full=full[full.weekday].copy().reset_index(drop=True)
    for col in ['pre_day','post_day','onset','exit']:full[col]=0
    for _,g in full.groupby('unit_id',sort=False):
        labels=event_labels(g.D)
        for col,v in zip(['pre_day','post_day','onset','exit'],labels):full.loc[g.index,col]=v.astype(int)
    full['overlap']=full.pre_day.ne(0)&full.post_day.ne(0)
    full['holdout']=full.pre_day.ne(0)|full.post_day.ne(0)
    full[['unit_id','date','sample_day','D','pre_day','post_day','onset','exit','overlap','holdout']].to_parquet(OUT/'weekday_event_labels.parquet',index=False)
    d=pd.read_parquet(paths['analysis']).merge(full[['unit_id','date','pre_day','post_day','onset','exit','overlap','holdout']],on=['unit_id','date'],validate='one_to_one')
    links=pd.read_csv(paths['links']);m=pd.read_parquet(paths['metadata'])[['metadata_id','ideology.4t']]
    members=links.merge(m,on='metadata_id',how='left',validate='many_to_one')
    classes=members.groupby('unit_id')['ideology.4t'].agg(lambda x:' | '.join(sorted(set(x.dropna())))).rename('codes')
    d=d.merge(classes,on='unit_id',how='left',validate='many_to_one');d['codes']=d.codes.fillna('')
    d['group']=d.codes.map({'aligned':'Aligned','opp':'Opp. + Independent','unclear':'Opp. + Independent'})
    d['exclusion_reason']=np.where(d.group.notna(),'',np.where(d.codes.eq(''),'Missing classification','Conflicting linked-brand classifications'))
    d[['unit_id','codes','group','exclusion_reason']].drop_duplicates().to_csv(OUT/'classification_audit.csv',index=False)
    members[members.unit_id.isin(d.unit_id)].to_csv(OUT/'metadata_members.csv',index=False)
    d['clean_train']=d.D.eq(0)&~d.holdout
    support=d.groupby('unit_id').clean_train.sum().rename('clean_untreated_days')
    d['clean_eligible']=d.unit_id.map(support).ge(5)
    support.reset_index().assign(eligible=lambda x:x.clean_untreated_days.ge(5)).to_csv(OUT/'clean_support.csv',index=False)
    d.to_parquet(OUT/'analysis_panel.parquet',index=False)
    counts=[]
    for name,z in [('Pooled',d),('Classified',d[d.group.notna()]),('Diagnostic eligible',d[d.clean_eligible]),('Classified diagnostic eligible',d[d.clean_eligible&d.group.notna()])]:
        for g,v in [('All',z),*list(z.groupby('group'))]:
            counts.append(dict(sample=name,group=g,rows=len(v),units=v.unit_id.nunique(),dates=v.date.nunique(),treated=int(v.D.sum()),clean_train=int(v.clean_train.sum()),overlap=int(v.overlap.sum()),zero_video=int(v.videos.eq(0).sum())))
            if 'eligible' in name:assert v.groupby('unit_id').clean_train.sum().ge(5).all()
            assert v.groupby('date').clean_train.sum().gt(0).all()
    pd.DataFrame(counts).to_csv(OUT/'sample_counts.csv',index=False)
    targets=[]
    for typ,col in [('Pre-treatment','pre_day'),('Carryover','post_day')]:
        for k,z in d[d[col].ne(0)&~d.overlap&d.clean_eligible].groupby(col):targets.append(dict(test=typ,day=int(k),cells=len(z),outlets=z.unit_id.nunique(),dates=z.date.nunique()))
    pd.DataFrame(targets).to_csv(OUT/'target_counts.csv',index=False)
    result={'input_paths':{k:str(p) for k,p in paths.items()},'sha256':hashes,'counts':counts,'targets':targets,
      'heldout_cells':int(d.holdout.sum()),'overlap_cells':int(d.overlap.sum()),'observed_onsets':int(full.onset.sum()),'observed_exits':int(full.exit.sum())}
    assert hashes=={k:b.sha(p) for k,p in paths.items()}
    (OUT/'build_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()

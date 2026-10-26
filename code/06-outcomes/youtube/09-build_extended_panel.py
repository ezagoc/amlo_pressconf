"""Build current all-video YouTube outcomes with explicit channel/date coverage.

Reads existing local archives only. Legacy 2018-2024 panels remain reproducible.
Uploads intervals support zero-video days; curated playlists alone do not prove
all-video coverage. Counters are archived cumulative snapshots, not daily accrual.
"""
import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from project_paths import media_path


def digest(p):
    with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def token(v):
    if pd.isna(v): return None
    v=unicodedata.normalize('NFKD',unquote(str(v)).lower()).encode('ascii','ignore').decode()
    v=re.split('[?#]',v)[0].rstrip('/')
    v=re.sub(r'/(videos|shorts|streams|featured|about)$','',v)
    return re.sub('[^a-z0-9_-]','',v.split('/')[-1].lstrip('@')) or None


def dates(v):
    return pd.to_datetime(v,utc=True,errors='coerce',format='mixed').dt.tz_localize(None).dt.normalize()


def strict_sum(s):
    return s.sum() if s.notna().all() else np.nan


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=media_path('data/06-outcomes/youtube/extended'))
    parser.add_argument('--through',help='Optional last day; defaults to the latest full retrieval day')
    args=parser.parse_args();out=args.output_dir;out.mkdir(parents=True,exist_ok=True)
    base=media_path('data/06-outcomes/youtube');start=pd.Timestamp('2018-01-01')
    originals=base/'mexican_newspapers_youtube.xlsx'; reviewed=base/'reviewed_outlets/youtube_channels.parquet'
    covfile=base/'reviewed_outlets/youtube_outlet_coverage.csv'
    meta_file=media_path('data/00-newspaper_data/processed/newspaper_metadata_geocoded.parquet')
    original=pd.read_excel(originals);review=pd.read_parquet(reviewed);coverage=pd.read_csv(covfile)
    dimension=pd.concat([original,review],ignore_index=True).dropna(subset=['channelId'])
    # Keep every verified URL/handle alias, but only one physical channel row.
    alias=[]
    for _,r in dimension.iterrows():
        # youtube.channel can list several channels for the same outlet; it is
        # not evidence that every listed URL belongs to this particular channelId.
        for field in ['channelId','yt_customUrl','yt_handle']:
            if field in r and pd.notna(r[field]):
                for value in str(r[field]).split(','):
                    t=token(value)
                    if t: alias.append({'token':t,'channel_id':r.channelId,'evidence_field':field})
    aliases=pd.DataFrame(alias).drop_duplicates();aliases.to_csv(out/'channel_aliases.csv',index=False)
    ambiguity=aliases.groupby('token').channel_id.nunique();bad=set(ambiguity[ambiguity.gt(1)].index)
    aliases[aliases.token.isin(bad)].to_csv(out/'ambiguous_aliases.csv',index=False)
    lookup=aliases[~aliases.token.isin(bad)].drop_duplicates('token').set_index('token').channel_id.to_dict()
    dim=dimension.drop_duplicates('channelId',keep='first')[['channelId','name.page','yt_customUrl']].rename(columns={'channelId':'channel_id'})
    meta=pd.read_parquet(meta_file)
    mappings=[]
    for _,r in meta.iterrows():
        if pd.notna(r['youtube.channel']):
            for url in str(r['youtube.channel']).split(','):
                t=token(url)
                mappings.append({'metadata_id':r.metadata_id,'outlet_name':r['name.page'],'source_value':url.strip(),'token':t,'entity_id':lookup.get(t),'outcome':'youtube'})
    cw=pd.DataFrame(mappings).drop_duplicates();cw.to_csv(out/'metadata_youtube_crosswalk.csv',index=False)
    files=[p for folder in ['videos','big_channels','playlists/videos'] for p in sorted((base/folder).glob('*.parquet'))]
    files.append(base/'reviewed_outlets/youtube_videos.parquet')
    paths=files+[originals,reviewed,covfile,meta_file]; hashes={str(p):digest(p) for p in paths}
    chunks=[];audit=[];intervals=[]
    wanted=['videoId','channel_id','channelId','publishedAt_dt','publishedAt','viewCount','likeCount','commentCount','collectedAt','retrieved_at','playlist_position']
    for p in files:
        schema=pq.read_schema(p).names
        if not pq.ParquetFile(p).metadata.num_rows:
            audit.append({'file':str(p),'rows':0,'status':'empty'});continue
        d=pd.read_parquet(p,columns=[c for c in wanted if c in schema])
        assert 'videoId' in d and ('channel_id' in d or 'channelId' in d),p
        if 'channel_id' not in d: d['channel_id']=d.channelId
        if 'channelId' in d: d['channel_id']=d.channel_id.fillna(d.channelId)
        pub=d.get('publishedAt_dt',pd.Series(pd.NaT,index=d.index)).copy()
        if 'publishedAt' in d:pub=pub.fillna(d.publishedAt)
        d['date']=dates(pub)
        d['retrieval']=dates(d.get('collectedAt',d.get('retrieved_at',pd.Series(pd.NaT,index=d.index))))
        for c in ['viewCount','likeCount','commentCount']:
            d[c]=pd.to_numeric(d.get(c,pd.Series(np.nan,index=d.index)),errors='coerce')
        valid=d.videoId.notna()&d.channel_id.notna()&d.date.notna()
        audit.append({'file':str(p),'rows':len(d),'valid_rows':int(valid.sum()),'min_published':str(d.date.min()),'max_published':str(d.date.max()),'status':'loaded'})
        # Unavailable/deleted reviewed videos have no publication date; audited
        # but cannot supply a dated outcome. Do not silently skip malformed IDs.
        assert d.loc[d.date.notna(),'videoId'].notna().all()
        d=d[valid].copy()
        if p.parent==base/'videos':
            for channel,g in d.groupby('channel_id'):
                if 'playlist_position' not in g or not g.playlist_position.notna().any():
                    continue  # No uploads-pagination evidence: supplementary archive only.
                truncated=len(g)>=19900 or ('playlist_position' in g and g.playlist_position.max()>=19900)
                lo=g.date.min()+pd.Timedelta(days=1) if truncated else start
                # Retrieval date is partial; use completed days only. For files
                # without timestamps, stop at the last published date, not mtime.
                hi=g.retrieval.min()-pd.Timedelta(days=1) if g.retrieval.notna().any() else g.date.max()
                intervals.append(dict(channel_id=channel,date_from=lo,date_to=hi,basis='capped_uploads_recent_interval' if truncated else 'uploads_pagination_archive',source=str(p)))
        chunks.append(d[['videoId','channel_id','date','viewCount','likeCount','commentCount','retrieval']])
    # Reviewed cap audits retain the uploads boundary before curated backfills.
    for _,r in review.iterrows():
        if r.coverage_status=='pagination_complete':lo=start;basis='reviewed_uploads_complete'
        else:
            c=coverage[coverage.channel_id.eq(r.channelId)]
            boundary=c.initial_upload_oldest.dropna() if 'initial_upload_oldest' in c else pd.Series(dtype=str)
            if not len(boundary):continue
            lo=pd.to_datetime(boundary.iloc[0],utc=True).tz_localize(None).normalize()+pd.Timedelta(days=1)
            basis='reviewed_capped_uploads_recent_interval'
        hi=pd.to_datetime(r.retrieved_at,utc=True).tz_localize(None).normalize()-pd.Timedelta(days=1)
        intervals.append(dict(channel_id=r.channelId,date_from=lo,date_to=hi,basis=basis,source=str(reviewed)))
    intervals=pd.DataFrame(intervals);intervals=intervals[intervals.date_to.ge(intervals.date_from)]
    end=pd.Timestamp(args.through) if args.through else intervals.date_to.max()
    intervals.to_csv(out/'coverage_intervals.csv',index=False)
    pd.DataFrame(audit).to_csv(out/'raw_file_audit.csv',index=False)
    videos=pd.concat(chunks,ignore_index=True)
    conflicts=videos.groupby('videoId').agg(channels=('channel_id','nunique'),dates=('date','nunique'))
    conflict_ids=conflicts[(conflicts.channels>1)|(conflicts.dates>1)]
    conflict_ids.to_csv(out/'video_identity_conflicts.csv')
    assert not conflicts.channels.gt(1).any(),'Conflicting channel identities require review'
    conflict_rows=videos[videos.videoId.isin(conflict_ids.index)].copy()
    conflict_rows.to_csv(out/'quarantined_video_dates.csv',index=False)
    videos=videos[~videos.videoId.isin(conflict_ids.index)]
    # Same archived video can appear in uploads and several playlists. Count it
    # once and take maximum available counters, as in the existing text workflow.
    videos=videos.groupby('videoId',as_index=False).agg(channel_id=('channel_id','first'),date=('date','first'),viewCount=('viewCount','max'),likeCount=('likeCount','max'),commentCount=('commentCount','max'))
    videos=videos[videos.date.between(start,end)].copy()
    assert not videos.videoId.duplicated().any()
    unknown=videos[~videos.channel_id.isin(dim.channel_id)]
    unknown.groupby('channel_id').size().rename('videos').to_csv(out/'unmapped_raw_channels.csv')
    videos=videos[videos.channel_id.isin(dim.channel_id)]
    videos.to_parquet(out/'deduplicated_video_metrics.parquet',index=False)
    daily=videos.groupby(['channel_id','date']).agg(n_videos=('videoId','size'),viewCount=('viewCount',strict_sum),likeCount=('likeCount',strict_sum),commentCount=('commentCount',strict_sum)).reset_index()
    calendar=pd.date_range(start,end)
    panel=pd.MultiIndex.from_product([dim.channel_id,calendar],names=['channel_id','date']).to_frame(index=False)
    panel=panel.merge(dim,on='channel_id',validate='many_to_one').merge(daily,on=['channel_id','date'],how='left',validate='one_to_one')
    panel['source_date_observed']=False
    for r in intervals.itertuples():
        panel.loc[panel.channel_id.eq(r.channel_id)&panel.date.between(r.date_from,r.date_to),'source_date_observed']=True
    # Conflicting publication dates leave every candidate channel/day unavailable.
    if len(conflict_rows):
        invalid=pd.MultiIndex.from_frame(conflict_rows[['channel_id','date']].drop_duplicates())
        panel.loc[pd.MultiIndex.from_frame(panel[['channel_id','date']]).isin(invalid),'source_date_observed']=False
    # Actual video rows outside supported upload intervals remain in the archive,
    # but neither their partial totals nor unobserved zeros enter regressions.
    present=panel.n_videos.notna()
    for c in ['n_videos','viewCount','likeCount','commentCount']:
        panel.loc[~present&panel.source_date_observed,c]=0
        panel.loc[~panel.source_date_observed,c]=np.nan
    panel['published']=panel.n_videos.gt(0).astype(float).where(panel.source_date_observed)
    for c in ['viewCount','likeCount','commentCount']:
        panel[c+'_per_video']=panel[c].div(panel.n_videos.where(panel.n_videos.gt(0))).mask(panel.n_videos.eq(0),0)
    panel['source_entity_matched']=panel.channel_id.isin(intervals.channel_id)
    panel.to_parquet(out/'panel_daily.parquet',index=False)
    entity=panel.rename(columns={'channel_id':'entity_id','n_videos':'youtube_n_videos','viewCount':'youtube_views','likeCount':'youtube_likes','commentCount':'youtube_comments','published':'youtube_published','viewCount_per_video':'youtube_views_per_video','likeCount_per_video':'youtube_likes_per_video','commentCount_per_video':'youtube_comments_per_video'})
    entity.to_parquet(out/'youtube_entity_daily_panel.parquet',index=False)
    years=videos.assign(year=videos.date.dt.year).groupby('year').agg(videos=('videoId','size'),channels=('channel_id','nunique'))
    years.to_csv(out/'videos_by_year.csv')
    covered_years=panel[panel.source_date_observed].assign(year=lambda d:d.date.dt.year).groupby('year').agg(channel_days=('channel_id','size'),channels=('channel_id','nunique'),videos=('n_videos','sum'))
    covered_years.to_csv(out/'covered_outcomes_by_year.csv')
    assert hashes=={str(p):digest(p) for p in paths},'Source changed during build'
    assert not panel.duplicated(['channel_id','date']).any()
    assert panel.loc[~panel.source_date_observed,['n_videos','viewCount','likeCount','commentCount']].isna().all().all()
    result={'date_from':str(start.date()),'date_to':str(end.date()),'channels':len(dim),'rows':len(panel),'unique_archived_videos':len(videos),'quarantined_conflicting_video_dates':len(conflict_ids),'archived_videos_outside_coverage':int(len(videos)-panel.n_videos.sum()),'metadata_urls':len(cw),'matched_metadata_urls':int(cw.entity_id.notna().sum()),'ambiguous_aliases':sorted(bad),'input_sha256':hashes,'inputs_unchanged':True,'coverage_policy':'Full uploads snapshots support historical zeros. Capped snapshots support only dates strictly after their uploads lower boundary. Retrieval days are excluded. Curated playlists contribute videos but do not establish complete all-video coverage. These are archive coverage flags, not independent proof of API completeness.','engagement_policy':'Maximum archived cumulative counters for each globally unique video ID; unavailable metrics stay NA. Counts belong to publication dates, not dates engagement accrued.'}
    (out/'build_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='input_sha256'},indent=2));print(years.to_string());print(covered_years.to_string())

if __name__=='__main__': main()

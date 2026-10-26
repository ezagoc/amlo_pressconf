"""Backfill capped reviewed channels from their public curated playlists.

Adapts getYB_playlists_download.py to the reviewed identity manifest/checkpoint.
Uses one configured key, stops on quota exhaustion, never attributes another
channel's videos to the playlist owner, and does not claim exhaustive coverage.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

SPEC=importlib.util.spec_from_file_location('reviewed_youtube',Path(__file__).with_name('07-extract_reviewed_outlets.py'))
base=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(base)


def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS backfill_catalog (
      channel_id TEXT PRIMARY KEY, next_token TEXT, complete INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS backfill_playlists (
      channel_id TEXT NOT NULL, playlist_id TEXT NOT NULL, payload TEXT NOT NULL,
      priority INTEGER NOT NULL, next_token TEXT, complete INTEGER DEFAULT 0,
      pages INTEGER DEFAULT 0, error TEXT, PRIMARY KEY(channel_id,playlist_id));
    CREATE TABLE IF NOT EXISTS backfill_playlist_videos (
      channel_id TEXT NOT NULL, playlist_id TEXT NOT NULL, video_id TEXT NOT NULL,
      payload TEXT NOT NULL, decision TEXT NOT NULL,
      PRIMARY KEY(channel_id,playlist_id,video_id));
    ''')


def priority(item):
    snippet=item.get('snippet',{})
    title=snippet.get('title','')
    if re.search(r'\b202[12]\b',title):return 0
    if snippet.get('publishedAt','9999') < '2023-01-01':
        return 1 if item.get('contentDetails',{}).get('itemCount',0) <= 500 else 2
    return 3


def catalog_page(api,db,cid):
    with db:db.execute('INSERT OR IGNORE INTO backfill_catalog(channel_id) VALUES (?)',(cid,))
    token,done=db.execute('SELECT next_token,complete FROM backfill_catalog WHERE channel_id=?',(cid,)).fetchone()
    if done:return True
    params={'part':'snippet,contentDetails,status','channelId':cid,'maxResults':50}
    if token:params['pageToken']=token
    result=api.get('playlists',**params)
    nxt=result.get('nextPageToken')
    if nxt and nxt==token:raise ValueError('Repeated playlist catalog cursor')
    with db:
        for item in result.get('items',[]):
            if item.get('snippet',{}).get('channelId')!=cid:
                raise ValueError('Playlist catalog returned a different channel owner')
            db.execute('INSERT OR IGNORE INTO backfill_playlists(channel_id,playlist_id,payload,priority) VALUES (?,?,?,?)',
                       (cid,item['id'],json.dumps(item),priority(item)))
        db.execute('UPDATE backfill_catalog SET next_token=?,complete=? WHERE channel_id=?',(nxt,int(not nxt),cid))
    return not nxt


def playlist_page(api,db,cid,pid):
    token,done=db.execute('SELECT next_token,complete FROM backfill_playlists WHERE channel_id=? AND playlist_id=?',(cid,pid)).fetchone()
    if done:return
    params={'part':'snippet,contentDetails','playlistId':pid,'maxResults':50}
    if token:params['pageToken']=token
    result=api.get('playlistItems',**params)
    nxt=result.get('nextPageToken')
    if nxt and nxt==token:raise ValueError('Repeated curated playlist cursor')
    items={x['contentDetails']['videoId']:x for x in result.get('items',[]) if x.get('contentDetails',{}).get('videoId')}
    known={vid:db.execute('SELECT channel_id FROM videos WHERE video_id=?',(vid,)).fetchone() for vid in items}
    needed=[vid for vid,item in items.items() if known[vid] is None and item.get('snippet',{}).get('videoOwnerChannelId',cid)==cid]
    details=api.get('videos',part='snippet,statistics,contentDetails,status',id=','.join(needed)).get('items',[]) if needed else []
    returned={v['id']:v for v in details}
    if not set(returned).issubset(needed):raise ValueError('Unexpected video IDs from details request')
    # Commit the page, verified video ownership and cursor together. A quota
    # error in videos.list leaves the page resumable without lost pending IDs.
    with db:
        for vid,item in items.items():
            if known[vid]:
                decision='already_saved' if known[vid][0]==cid else 'excluded_foreign_channel'
            elif vid in returned:
                video=returned[vid]
                if video.get('snippet',{}).get('channelId')!=cid:
                    decision='excluded_foreign_channel'
                else:
                    decision='added_verified_owner'
                    db.execute('INSERT OR IGNORE INTO videos VALUES (?,?,?,?,?)',
                               (vid,cid,json.dumps(video),'public',base.timestamp()))
            elif item.get('snippet',{}).get('videoOwnerChannelId',cid)!=cid:
                decision='excluded_foreign_channel'
            else:
                # Preserve the observation without inventing ownership for an
                # unavailable/private video whose channel cannot be confirmed.
                decision='unavailable_owner_unverified'
            db.execute('INSERT OR REPLACE INTO backfill_playlist_videos VALUES (?,?,?,?,?)',
                       (cid,pid,vid,json.dumps(item),decision))
        db.execute('UPDATE backfill_playlists SET next_token=?,complete=?,pages=pages+1 WHERE channel_id=? AND playlist_id=?',
                   (nxt,int(not nxt),cid,pid))


def report(db,out,selected,before,errors):
    import csv
    rows=[]
    for entry,cid in selected:
        count,oldest,newest,study=db.execute("SELECT count(*),min(json_extract(payload,'$.snippet.publishedAt')),max(json_extract(payload,'$.snippet.publishedAt')),sum(json_extract(payload,'$.snippet.publishedAt') >= '2021-01-01' AND json_extract(payload,'$.snippet.publishedAt') < '2023-01-01') FROM videos WHERE channel_id=?",(cid,)).fetchone()
        catalog=db.execute('SELECT complete FROM backfill_catalog WHERE channel_id=?',(cid,)).fetchone()
        total,done,pages=db.execute('SELECT count(*),coalesce(sum(complete),0),coalesce(sum(pages),0) FROM backfill_playlists WHERE channel_id=?',(cid,)).fetchone()
        rows.append({'outlet_id':entry['id'],'channel_id':cid,'videos_before_this_run':before[cid],
                     'videos_after_this_run':count,'added_this_run':count-before[cid],
                     'oldest_downloaded':oldest,'newest_downloaded':newest,'videos_2021_2022':study or 0,
                     'catalog_complete':bool(catalog and catalog[0]),'playlists_found':total,'playlists_finished':done,'playlist_pages':pages,
                     'coverage_note':'Curated playlists are supplementary; reaching an older date does not prove continuous or exhaustive coverage.'})
    with (out/'playlist_backfill_coverage.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['outlet_id']);w.writeheader();w.writerows(rows)
    (out/'playlist_backfill_status.json').write_text(json.dumps({'retrieved_at':base.timestamp(),'outlets':rows,'errors':errors},indent=2)+'\n')
    for row in rows:print(json.dumps(row),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=base.media_path('data','06-outcomes','youtube','reviewed_outlets'))
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--outlet',action='append')
    parser.add_argument('--max-rounds',type=int,default=10000,help='At most one playlist page per channel per round')
    args=parser.parse_args()
    if args.max_rounds<1:parser.error('max-rounds must be positive')
    entries=json.loads((base.ROOT/'info_newspapers_gpt/outlet_review_20261016/youtube_extraction_manifest.json').read_text())['entries']
    checkpoint=args.output_dir/'checkpoint.sqlite3'
    if not checkpoint.exists():parser.error('Run the reviewed uploads extractor first')
    db=base.open_db(checkpoint) if args.execute else sqlite3.connect(f'file:{checkpoint}?mode=ro',uri=True)
    selected=[]
    for entry in entries:
        row=db.execute('SELECT c.channel_id,c.payload,p.pages,p.complete FROM channels c JOIN progress p USING(channel_id) WHERE c.outlet_id=?',(entry['id'],)).fetchone()
        if not row:continue
        reported=base.number(json.loads(row[1]).get('statistics',{}),'videoCount') or 0
        if (args.outlet and entry['id'] in args.outlet) or (not args.outlet and row[2]==400 and row[3] and reported>20000):selected.append((entry,row[0]))
    if args.outlet and set(args.outlet)-{e['id'] for e,cid in selected}:parser.error('Selected outlet has no saved channel metadata')
    for e,cid in selected:print('SELECTED',e['id'],cid,flush=True)
    if not args.execute:db.close();return 0
    keys=os.environ.get('YOUTUBE_API_KEY') or os.environ.get('YOUTUBE_API_KEYS','')
    key=re.split(r'[,;]',keys)[0].strip()
    if not key:parser.error('No configured API key')
    api=base.API(key);initialize(db);errors=[]
    before={cid:db.execute('SELECT count(*) FROM videos WHERE channel_id=?',(cid,)).fetchone()[0] for e,cid in selected}
    try:
        pending=list(selected)
        while pending:
            pending=[(e,cid) for e,cid in pending if not catalog_page(api,db,cid)]
        for e,cid in selected:
            print(e['id'],'playlists:',db.execute('SELECT count(*) FROM backfill_playlists WHERE channel_id=?',(cid,)).fetchone()[0],flush=True)
        for round_no in range(args.max_rounds):
            progressed=False
            for e,cid in selected:
                row=db.execute("SELECT playlist_id FROM backfill_playlists WHERE channel_id=? AND complete=0 AND error IS NULL ORDER BY priority,json_extract(payload,'$.snippet.publishedAt'),playlist_id LIMIT 1",(cid,)).fetchone()
                if not row:continue
                progressed=True;pid=row[0]
                try:playlist_page(api,db,cid,pid)
                except base.APIError as error:
                    if error.quota:raise
                    # A removed playlist should not prevent other playlists.
                    if error.status==404:
                        with db:db.execute('UPDATE backfill_playlists SET error=? WHERE channel_id=? AND playlist_id=?',(str(error),cid,pid))
                        errors.append({'outlet':e['id'],'playlist_id':pid,'error':str(error)})
                    else:raise
            if not progressed:break
            if (round_no+1)%10==0:
                print('ROUND',round_no+1,'saved videos:',db.execute('SELECT count(*) FROM videos').fetchone()[0],flush=True)
    except (base.APIError,ValueError) as error:
        errors.append({'error':str(error)});print(str(error),file=sys.stderr,flush=True)
    finally:
        base.export(db,args.output_dir,linkage={e['id']:e for e in entries})
        report(db,args.output_dir,selected,before,errors);db.close()
    return int(bool(errors))

if __name__=='__main__':raise SystemExit(main())

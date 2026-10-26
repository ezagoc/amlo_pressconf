"""Extract public channel/video metadata for reviewed outlet identities.

Default is a credential-free dry run. --execute uses the first configured key;
quota exhaustion stops the run. SQLite page transactions support safe resume.
API references: https://developers.google.com/youtube/v3/docs/channels/list
https://developers.google.com/youtube/v3/docs/playlistItems/list
https://developers.google.com/youtube/v3/docs/videos/list
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone, date
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse, unquote
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from project_paths import media_path  # also loads .env without printing credentials


class APIError(RuntimeError):
    def __init__(self, reason, status=None):
        super().__init__(f"YouTube API error: {reason} (HTTP {status})")
        self.reason = reason
        self.quota = reason in {"quotaExceeded", "dailyLimitExceeded", "dailyLimitExceededUnreg"}


def channel_selector(value):
    """Only direct channel IDs, handles and legacy usernames; never fuzzy search."""
    if re.fullmatch(r"UC[\w-]{22}", value):
        return {"id": value}
    if value.startswith("@") and not any(x in value for x in "/?#"):
        return {"forHandle": value}
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        raise ValueError("Expected a direct HTTPS YouTube channel URL")
    parts = unquote(parsed.path).strip("/").split("/")
    if parts[0].startswith("@") and len(parts[0]) > 1:
        return {"forHandle": parts[0]}
    if len(parts) >= 2 and parts[0] == "channel" and re.fullmatch(r"UC[\w-]{22}", parts[1]):
        return {"id": parts[1]}
    if len(parts) >= 2 and parts[0] == "user" and parts[1]:
        return {"forUsername": parts[1]}
    raise ValueError("Legacy /c/ URLs and watch links need a verified handle or channel ID")


class API:
    def __init__(self, key):
        self.key = key

    def get(self, resource, **params):
        url = "https://www.googleapis.com/youtube/v3/" + resource + "?" + urlencode({**params, "key": self.key})
        for attempt in range(4):
            try:
                with urlopen(url, timeout=30) as response:
                    return json.load(response)
            except HTTPError as error:
                try:
                    payload = json.loads(error.read())
                    reason = payload["error"].get("errors", [{}])[0].get("reason", "http_error")
                except (ValueError, KeyError, IndexError):
                    reason = "http_error"
                # Never log the request URL (it contains the key).
                if (error.code == 429 or error.code >= 500) and attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                raise APIError(reason, error.code) from None
            except (URLError, TimeoutError):
                if attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                raise APIError("network_failure") from None


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def open_db(path):
    db = sqlite3.connect(path)
    db.executescript("""
      CREATE TABLE IF NOT EXISTS channels (
        outlet_id TEXT PRIMARY KEY, outlet_name TEXT NOT NULL, source_url TEXT NOT NULL,
        channel_id TEXT NOT NULL, payload TEXT NOT NULL, retrieved_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS progress (
        channel_id TEXT PRIMARY KEY, playlist_id TEXT NOT NULL, next_token TEXT,
        complete INTEGER NOT NULL DEFAULT 0, pages INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS videos (
        video_id TEXT PRIMARY KEY, channel_id TEXT NOT NULL, payload TEXT,
        availability TEXT NOT NULL, retrieved_at TEXT NOT NULL);
    """)
    return db


def extract_entry(api, db, entry, max_pages=10, refresh=False):
    existing = db.execute("SELECT source_url,channel_id,payload FROM channels WHERE outlet_id=?", (entry["id"],)).fetchone()
    source_url = entry["youtube"]["url"]
    if existing and existing[0] != source_url:
        raise ValueError("Reviewed channel URL changed; use a new output directory to avoid mixing identities")
    if existing and not refresh:
        channel_id, channel = existing[1], json.loads(existing[2])
    else:
        result = api.get("channels", part="snippet,statistics,contentDetails,brandingSettings,topicDetails", **channel_selector(source_url))
        if len(result.get("items", [])) != 1:
            raise ValueError("Reviewed channel did not resolve to exactly one public channel")
        channel = result["items"][0]
        channel_id = channel["id"]
        if existing and existing[1] != channel_id:
            raise ValueError("Handle now resolves to a different channel; identity review required")
    playlist_id = channel.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
    if not playlist_id:
        raise ValueError("Channel has no public uploads playlist")
    with db:
        if not existing or refresh:
            db.execute("INSERT OR REPLACE INTO channels VALUES (?,?,?,?,?,?)",
                       (entry["id"], entry["name"], source_url, channel_id, json.dumps(channel), timestamp()))
        db.execute("INSERT OR IGNORE INTO progress(channel_id,playlist_id) VALUES (?,?)", (channel_id, playlist_id))
        if refresh:
            db.execute("UPDATE progress SET next_token=NULL,complete=0,pages=0 WHERE channel_id=?", (channel_id,))
    for _ in range(max_pages):
        token, complete = db.execute("SELECT next_token,complete FROM progress WHERE channel_id=?", (channel_id,)).fetchone()
        if complete:
            break
        params = {"part": "contentDetails", "playlistId": playlist_id, "maxResults": 50}
        if token:
            params["pageToken"] = token
        page = api.get("playlistItems", **params)
        ids = list(dict.fromkeys(x["contentDetails"]["videoId"] for x in page.get("items", []) if x.get("contentDetails", {}).get("videoId")))
        videos = api.get("videos", part="snippet,statistics,contentDetails,status", id=",".join(ids)).get("items", []) if ids else []
        returned = {video["id"]: video for video in videos}
        if not set(returned).issubset(ids):
            raise ValueError("Unexpected video IDs in API response")
        if any(v.get("snippet", {}).get("channelId") != channel_id for v in videos):
            raise ValueError("Uploads response contains a video from another channel")
        next_token = page.get("nextPageToken")
        if next_token and next_token == token:
            raise ValueError("Repeated pagination token; refusing an endless loop")
        # Commit both metadata and the page cursor, or neither. A failed videos
        # request will retry the whole page next run, without duplicate rows.
        with db:
            for video_id in ids:
                payload = returned.get(video_id)
                db.execute("INSERT OR REPLACE INTO videos VALUES (?,?,?,?,?)",
                           (video_id, channel_id, json.dumps(payload) if payload else None,
                            "public" if payload else "unavailable", timestamp()))
            db.execute("UPDATE progress SET next_token=?,complete=?,pages=pages+1 WHERE channel_id=?",
                       (next_token, int(not next_token), channel_id))
    return db.execute("SELECT complete,pages FROM progress WHERE channel_id=?", (channel_id,)).fetchone()


def number(stats, key):
    value = stats.get(key)
    return int(value) if value is not None else None


def export(db, directory, since=None, until=None, parquet=False, linkage=None):
    linkage = linkage or {}
    channels, videos = [], []
    saved_counts = dict(db.execute("SELECT channel_id,COUNT(*) FROM videos GROUP BY channel_id"))
    for outlet_id, name, source, cid, payload, retrieved in db.execute("SELECT * FROM channels ORDER BY outlet_id"):
        c = json.loads(payload);s = c.get("snippet", {});st = c.get("statistics", {})
        complete, pages = db.execute("SELECT complete,pages FROM progress WHERE channel_id=?", (cid,)).fetchone()
        saved = saved_counts.get(cid, 0)
        reported = number(st, "videoCount")
        # Observed API-key scans can end after 400 pages of 50 items even when
        # the channel reports many more uploads. End-of-pagination is not proof
        # of historical completeness. Keep the cursor state, but expose this gap.
        capped = bool(complete and pages == 400 and reported is not None
                      and reported > 20000)
        coverage = "api_limit_suspected" if capped else "pagination_complete" if complete else "in_progress"
        identity = linkage.get(outlet_id, {})
        channels.append({"outlet_id": outlet_id, "name.page": name,
          "names.conference": identity.get("linkage_id"), "names.transcripts": identity.get("question_id"), "youtube.channel": source,
          "channelId": cid, "yt_title": s.get("title"), "yt_customUrl": s.get("customUrl"),
          "yt_country": s.get("country"), "yt_createdAt": s.get("publishedAt"),
          "yt_description": s.get("description"), "yt_subscriberCount": None if st.get("hiddenSubscriberCount") else number(st,"subscriberCount"),
          "yt_hiddenSubs": st.get("hiddenSubscriberCount"), "yt_videoCount": number(st,"videoCount"),
          "yt_viewCount": number(st,"viewCount"), "retrieved_at": retrieved,
          "uploads_complete": bool(complete), "pages_fetched": pages,
          "saved_video_count": saved, "coverage_status": coverage,
          "reported_minus_saved": reported - saved if reported is not None else None})
    for vid, cid, payload, availability, retrieved in db.execute("SELECT * FROM videos ORDER BY channel_id,video_id"):
        v = json.loads(payload) if payload else {};s = v.get("snippet", {});st = v.get("statistics", {})
        published = s.get("publishedAt");day = date.fromisoformat(published[:10]) if published else None
        # Missing/private videos remain in SQLite, but cannot be date-filtered.
        if (since or until) and (day is None or (since and day < since) or (until and day > until)):
            continue
        videos.append({"videoId":vid,"channel_id":cid,"publishedAt_dt":published,
          "title":s.get("title"),"description":s.get("description"),
          "viewCount":number(st,"viewCount"),"likeCount":number(st,"likeCount"),
          "commentCount":number(st,"commentCount"),"availability":availability,"retrieved_at":retrieved})
    for name, rows in [("youtube_channels",channels),("youtube_videos",videos)]:
        target = directory / (name + ".csv");tmp = target.with_suffix(".csv.tmp")
        # Explicit columns prevent empty runs from leaving stale exports.
        fields = list(rows[0]) if rows else (["outlet_id","name.page","names.conference","names.transcripts","youtube.channel","channelId","yt_title","yt_customUrl","yt_country","yt_createdAt","yt_description","yt_subscriberCount","yt_hiddenSubs","yt_videoCount","yt_viewCount","retrieved_at","uploads_complete","pages_fetched","saved_video_count","coverage_status","reported_minus_saved"] if name.endswith("channels") else ["videoId","channel_id","publishedAt_dt","title","description","viewCount","likeCount","commentCount","availability","retrieved_at"])
        with tmp.open("w",encoding="utf-8",newline="") as f:
            writer = csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
        tmp.replace(target)
        if parquet:
            import pandas as pd
            frame = pd.DataFrame(rows, columns=fields)
            if "publishedAt_dt" in frame:
                frame["publishedAt_dt"] = pd.to_datetime(frame["publishedAt_dt"], utc=True)
            target = directory / (name + ".parquet");tmp = target.with_suffix(".parquet.tmp")
            frame.to_parquet(tmp,index=False);tmp.replace(target)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest",type=Path,default=ROOT/"info_newspapers_gpt/outlet_review_20261016/youtube_extraction_manifest.json")
    p.add_argument("--output-dir",type=Path,default=media_path("data","06-outcomes","youtube","reviewed_outlets"))
    p.add_argument("--execute",action="store_true")
    p.add_argument("--channels-only",action="store_true",help="Resolve channels and fetch public channel metadata without enumerating uploads")
    p.add_argument("--outlet",action="append",help="Exact outlet ID; repeat to select several")
    p.add_argument("--max-pages",type=int,default=10,help="Maximum upload pages PER CHANNEL for this run (default 10)")
    p.add_argument("--refresh",action="store_true",help="Start a fresh uploads scan; existing videos remain deduplicated")
    p.add_argument("--since",type=date.fromisoformat)
    p.add_argument("--until",type=date.fromisoformat)
    p.add_argument("--parquet",action="store_true",help="Also export parquet (requires pandas and pyarrow)")
    args = p.parse_args()
    if args.max_pages < 1 or (args.since and args.until and args.since > args.until):
        p.error("max-pages must be positive and since must not exceed until")
    entries = json.loads(args.manifest.read_text())["entries"]
    if len({e["id"] for e in entries}) != len(entries):
        p.error("Manifest record IDs must be unique; shared attendance IDs belong in linkage_id")
    if args.outlet:
        unknown = set(args.outlet)-{e["id"] for e in entries}
        if unknown:p.error("Unknown outlet IDs: " + ", ".join(sorted(unknown)))
        entries = [e for e in entries if e["id"] in args.outlet]
    ready = []
    for e in entries:
        if e.get("youtube",{}).get("status") in {"verified_official_link", "verified_channel_profile", "existing_registry_channel_resolved"}:
            channel_selector(e["youtube"]["url"])
            ready.append(e)
        else:
            print(f"SKIP {e['id']}: channel missing or awaiting identity review")
    for e in ready:print(f"READY {e['id']}: {e['youtube']['url']}")
    if not args.execute:
        print(f"Dry run: {len(ready)} ready; no API requests or data writes. Add --execute to fetch.")
        return 0
    if args.parquet:
        import pandas, pyarrow  # fail before making API requests if unavailable
    keys = os.environ.get("YOUTUBE_API_KEY") or os.environ.get("YOUTUBE_API_KEYS","")
    key = re.split(r"[,;]",keys)[0].strip()
    if not key:p.error("Set YOUTUBE_API_KEY or YOUTUBE_API_KEYS; credentials are never printed")
    args.output_dir.mkdir(parents=True,exist_ok=True)
    db = open_db(args.output_dir / "checkpoint.sqlite3")
    failed = False
    try:
        for e in ready:
            try:
                complete,pages = extract_entry(API(key),db,e,0 if args.channels_only else args.max_pages,args.refresh)
                print(f"{e['id']}: pages={pages}, complete={bool(complete)}")
            except (APIError,ValueError) as error:
                failed = True;print(f"{e['id']}: {error}",file=sys.stderr)
                if isinstance(error,APIError) and error.quota:break
    finally:
        export(db,args.output_dir,args.since,args.until,args.parquet,{e["id"]:e for e in entries})
        db.close()
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())

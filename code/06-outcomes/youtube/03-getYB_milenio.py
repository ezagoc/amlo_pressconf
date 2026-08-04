# =========================
# CONFIG
# =========================

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))
from project_paths import env_list, media_output_path

CHANNEL_ID  = "UCFxHplbcoJK9m70c4VyTIxg"   # Milenio
OUT_FOLDER  = media_output_path("data", "06-outcomes", "youtube", "milenio", ".keep").parent
CKPT_FILE   = media_output_path("data", "06-outcomes", "youtube", "milenio", "checkpoint.json")

API_KEYS = env_list("YOUTUBE_API_KEYS")

# =========================
# Imports
# =========================

import os
import re
import json
import time

sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# =========================
# API key rotation
# =========================

class KeyPool:
    def __init__(self, keys):
        if not keys:
            raise ValueError("No API keys provided.")
        self._keys = keys
        self._idx  = 0
        self.youtube = self._build(self._idx)
        print(f"Using API key [{self._idx + 1}/{len(self._keys)}]")

    def _build(self, idx):
        return build("youtube", "v3", developerKey=self._keys[idx])

    def rotate(self):
        next_idx = self._idx + 1
        if next_idx >= len(self._keys):
            raise RuntimeError("All API keys have exhausted their quota.")
        self._idx = next_idx
        self.youtube = self._build(self._idx)
        print(f"  Rotated to API key [{self._idx + 1}/{len(self._keys)}]")

    def call(self, fn, max_retries=6, base_sleep=1.0):
        while True:
            for attempt in range(max_retries):
                try:
                    return fn(self.youtube)
                except HttpError as e:
                    status = getattr(e.resp, "status", None)
                    msg    = str(e).lower()
                    is_quota = (status == 403 and (
                        "quotaexceeded" in msg or "dailylimitexceeded" in msg or "quota" in msg
                    ))
                    if is_quota:
                        print(f"  Quota exhausted on key [{self._idx + 1}].")
                        self.rotate()
                        break
                    if status in (429, 500, 503):
                        time.sleep(base_sleep * (2 ** attempt))
                        continue
                    raise
            else:
                raise RuntimeError("Max retries exceeded.")

# =========================
# Helpers
# =========================

def chunked(xs, n):
    return [xs[i:i + n] for i in range(0, len(xs), n)]

def safe_json(x):
    if x is None:
        return None
    try:
        return json.dumps(x, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(x)

def parse_duration(duration):
    if not duration or not isinstance(duration, str):
        return None
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not m:
        return None
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)

def iso_to_dt(iso_str):
    if not iso_str:
        return None
    try:
        return pd.to_datetime(iso_str, utc=True)
    except Exception:
        return None

# =========================
# Checkpoint
# =========================

def load_checkpoint():
    if os.path.exists(CKPT_FILE):
        with open(CKPT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"playlists_done": False, "done_playlist_ids": [], "video_ids": []}

def save_checkpoint(state):
    with open(CKPT_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)

# =========================
# Step 1 — Get all playlists
# =========================

def get_all_playlists(pool, channel_id):
    playlists = []
    next_page = None
    while True:
        resp = pool.call(lambda yt, pt=next_page: yt.playlists().list(
            part="id,snippet,contentDetails,status",
            channelId=channel_id,
            maxResults=50,
            pageToken=pt,
        ).execute())
        for item in resp.get("items", []):
            playlists.append({
                "playlist_id":          item.get("id"),
                "playlist_title":       item["snippet"].get("title"),
                "playlist_description": item["snippet"].get("description"),
                "published_at":         item["snippet"].get("publishedAt"),
                "item_count":           item["contentDetails"].get("itemCount"),
                "privacy_status":       item["status"].get("privacyStatus"),
            })
        next_page = resp.get("nextPageToken")
        if not next_page:
            break
    return playlists

# =========================
# Step 2 — Get video IDs from a playlist
# =========================

def get_playlist_video_ids(pool, playlist_id):
    ids = []
    next_page = None
    while True:
        resp = pool.call(lambda yt, pt=next_page: yt.playlistItems().list(
            part="contentDetails",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=pt,
        ).execute())
        for item in resp.get("items", []):
            vid = item.get("contentDetails", {}).get("videoId")
            if vid:
                ids.append(vid)
        next_page = resp.get("nextPageToken")
        if not next_page:
            break
    return ids

# =========================
# Step 3 — Fetch video details
# =========================

def fetch_video_details(pool, video_ids):
    parts = "snippet,statistics,contentDetails,status,liveStreamingDetails,topicDetails,recordingDetails"
    rows = []
    for i, chunk in enumerate(chunked(video_ids, 50)):
        resp = pool.call(lambda yt, ch=chunk: yt.videos().list(
            part=parts,
            id=",".join(ch),
            maxResults=50,
        ).execute())
        for v in resp.get("items", []):
            snip  = v.get("snippet", {}) or {}
            stats = v.get("statistics", {}) or {}
            cd    = v.get("contentDetails", {}) or {}
            st    = v.get("status", {}) or {}
            live  = v.get("liveStreamingDetails", {}) or {}
            topic = v.get("topicDetails", {}) or {}
            rec   = v.get("recordingDetails", {}) or {}
            rows.append({
                "videoId":                  v.get("id"),
                "title":                    snip.get("title"),
                "description":              snip.get("description"),
                "publishedAt":              snip.get("publishedAt"),
                "channelId":                snip.get("channelId"),
                "channelTitle":             snip.get("channelTitle"),
                "categoryId":               snip.get("categoryId"),
                "defaultLanguage":          snip.get("defaultLanguage"),
                "defaultAudioLanguage":     snip.get("defaultAudioLanguage"),
                "tags_json":                safe_json(snip.get("tags")),
                "viewCount":                int(stats["viewCount"])     if stats.get("viewCount")     is not None else None,
                "likeCount":                int(stats["likeCount"])     if stats.get("likeCount")     is not None else None,
                "commentCount":             int(stats["commentCount"])  if stats.get("commentCount")  is not None else None,
                "favoriteCount":            int(stats["favoriteCount"]) if stats.get("favoriteCount") is not None else None,
                "duration_iso":             cd.get("duration"),
                "duration_seconds":         parse_duration(cd.get("duration")),
                "dimension":                cd.get("dimension"),
                "definition":               cd.get("definition"),
                "caption":                  cd.get("caption"),
                "licensedContent":          cd.get("licensedContent"),
                "projection":               cd.get("projection"),
                "regionRestriction_json":   safe_json(cd.get("regionRestriction")),
                "uploadStatus":             st.get("uploadStatus"),
                "privacyStatus":            st.get("privacyStatus"),
                "license":                  st.get("license"),
                "embeddable":               st.get("embeddable"),
                "madeForKids":              st.get("madeForKids"),
                "live_actualStartTime":     live.get("actualStartTime"),
                "live_actualEndTime":       live.get("actualEndTime"),
                "live_scheduledStartTime":  live.get("scheduledStartTime"),
                "live_concurrentViewers":   int(live["concurrentViewers"]) if live.get("concurrentViewers") else None,
                "topicDetails_json":        safe_json(topic if topic else None),
                "recordingDate":            rec.get("recordingDate"),
            })
        if (i + 1) % 20 == 0:
            print(f"    ...details for {len(rows):,} videos fetched")
    return rows

# =========================
# Main
# =========================

os.makedirs(OUT_FOLDER, exist_ok=True)
state = load_checkpoint()
pool  = KeyPool(API_KEYS)

playlists_path = os.path.join(OUT_FOLDER, "playlists.parquet")
videos_path    = os.path.join(OUT_FOLDER, "videos.parquet")

# --- Step 1: fetch playlists ---
if state["playlists_done"] and os.path.exists(playlists_path):
    df_playlists = pd.read_parquet(playlists_path)
    print(f"Playlists already saved ({len(df_playlists):,} playlists) — skipping fetch.")
else:
    print(f"Fetching playlists for channel {CHANNEL_ID} ...")
    playlists = get_all_playlists(pool, CHANNEL_ID)
    df_playlists = pd.DataFrame(playlists)
    df_playlists.to_parquet(playlists_path, index=False)
    print(f"  {len(df_playlists):,} playlists saved: {playlists_path}")
    state["playlists_done"] = True
    save_checkpoint(state)

# --- Step 2: collect video IDs from each playlist ---
done_playlist_ids = set(state.get("done_playlist_ids", []))
all_video_ids     = list(state.get("video_ids", []))
id_set            = set(all_video_ids)

remaining = df_playlists[~df_playlists["playlist_id"].isin(done_playlist_ids)]
print(f"\nCollecting video IDs: {len(remaining):,} playlists remaining "
      f"(of {len(df_playlists):,} total, {len(done_playlist_ids):,} already done)")

for _, row in remaining.iterrows():
    pid   = row["playlist_id"]
    title = row["playlist_title"]
    count = row["item_count"]
    try:
        ids = get_playlist_video_ids(pool, pid)
        new = [v for v in ids if v not in id_set]
        id_set.update(new)
        all_video_ids.extend(new)
        done_playlist_ids.add(pid)
        state["done_playlist_ids"] = list(done_playlist_ids)
        state["video_ids"]         = all_video_ids
        save_checkpoint(state)
        print(f"  [{len(done_playlist_ids)}/{len(df_playlists)}] {title!r}  "
              f"items={count}  new_ids={len(new)}  total={len(all_video_ids):,}")
    except Exception as e:
        print(f"  ERROR on playlist {pid} ({title!r}): {e}")
        raise   # preserve checkpoint, let user re-run

print(f"\nTotal unique video IDs: {len(all_video_ids):,}")

# --- Step 3: fetch video details ---
if os.path.exists(videos_path):
    df_existing = pd.read_parquet(videos_path)
    already_fetched = set(df_existing["videoId"].dropna().unique())
    print(f"Videos file exists ({len(df_existing):,} rows) — fetching only missing IDs.")
else:
    df_existing     = pd.DataFrame()
    already_fetched = set()

to_fetch = [v for v in all_video_ids if v not in already_fetched]
print(f"Fetching details for {len(to_fetch):,} videos ...")

if to_fetch:
    new_rows  = fetch_video_details(pool, to_fetch)
    df_new    = pd.DataFrame(new_rows)
    df_videos = pd.concat([df_existing, df_new], ignore_index=True)
else:
    df_videos = df_existing

for col in ["publishedAt", "live_actualStartTime", "live_actualEndTime"]:
    if col in df_videos.columns:
        df_videos[f"{col}_dt"] = df_videos[col].apply(iso_to_dt)

df_videos["channel_id"] = CHANNEL_ID
if "publishedAt_dt" in df_videos.columns:
    df_videos = df_videos.sort_values("publishedAt_dt").reset_index(drop=True)

df_videos.to_parquet(videos_path, index=False)
print(f"\nDone. Saved {len(df_videos):,} videos to {videos_path}")

# Clear checkpoint on full success
os.remove(CKPT_FILE)
print("Checkpoint cleared.")

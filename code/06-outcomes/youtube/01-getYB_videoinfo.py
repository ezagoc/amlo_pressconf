# =========================
# CONFIG
# =========================

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))
from project_paths import env_list, media_path, media_output_path

IN_EXCEL    = media_path("data", "06-outcomes", "youtube", "mexican_newspapers_youtube.xlsx")
OUT_FOLDER  = media_output_path("data", "06-outcomes", "youtube", "videos", ".keep").parent
MAX_VIDEOS  = 150_000   # skip channels with >= this many videos

API_KEYS = env_list("YOUTUBE_API_KEYS")

# =========================
# Imports
# =========================

import os
import re
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# =========================
# API key rotation
# =========================

class KeyPool:
    """Cycles through API keys when one hits its quota."""

    def __init__(self, keys: List[str]):
        if not keys:
            raise ValueError("No API keys provided.")
        self._keys = keys
        self._idx  = 0
        self.youtube = self._build(self._idx)
        print(f"Using API key [{self._idx + 1}/{len(self._keys)}]")

    def _build(self, idx: int):
        return build("youtube", "v3", developerKey=self._keys[idx])

    def rotate(self):
        """Switch to the next available key. Raises if all are exhausted."""
        next_idx = self._idx + 1
        if next_idx >= len(self._keys):
            raise RuntimeError("All API keys have exhausted their quota.")
        self._idx = next_idx
        self.youtube = self._build(self._idx)
        print(f"  Rotated to API key [{self._idx + 1}/{len(self._keys)}]")

    def call(self, fn, max_retries: int = 6, base_sleep: float = 1.0):
        """Execute fn(youtube) with exponential back-off and key rotation on quota errors."""
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
                    is_transient = status in (429, 500, 503) or (status == 403 and "quota" in msg)
                    if is_quota:
                        print(f"  Quota exhausted on key [{self._idx + 1}].")
                        self.rotate()
                        break   # retry outer while loop with new key
                    if is_transient:
                        time.sleep(base_sleep * (2 ** attempt))
                        continue
                    raise
            else:
                raise RuntimeError("Max retries exceeded.")

# =========================
# Helpers
# =========================

def iso_to_dt(iso_str: Optional[str]) -> Optional[pd.Timestamp]:
    if not iso_str:
        return None
    try:
        return pd.to_datetime(iso_str, utc=True)
    except Exception:
        return None

def chunked(xs: List[str], n: int) -> List[List[str]]:
    return [xs[i:i + n] for i in range(0, len(xs), n)]

def safe_json(x: Any) -> Optional[str]:
    if x is None:
        return None
    try:
        return json.dumps(x, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(x)

def parse_duration(duration: Optional[str]) -> Optional[int]:
    if not duration or not isinstance(duration, str):
        return None
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not m:
        return None
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)

# =========================
# API extractors
# =========================

def fetch_playlist_items(pool: KeyPool, playlist_id: str) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    page_token = None
    page = 0
    while True:
        resp = pool.call(lambda yt, pt=page_token: yt.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=pt,
        ).execute())
        for it in resp.get("items", []):
            snip = it.get("snippet", {}) or {}
            cd   = it.get("contentDetails", {}) or {}
            vid  = cd.get("videoId") or ((snip.get("resourceId") or {}).get("videoId"))
            if not vid:
                continue
            out[vid] = {
                "playlistItemId":            it.get("id"),
                "playlist_position":         snip.get("position"),
                "playlist_addedAt":          snip.get("publishedAt"),
                "playlist_videoPublishedAt": cd.get("videoPublishedAt"),
            }
        page_token = resp.get("nextPageToken")
        page += 1
        if page % 10 == 0:
            print(f"    ...{len(out):,} video IDs fetched")
        if not page_token:
            break
    return out


def fetch_video_details(pool: KeyPool, video_ids: List[str]) -> List[Dict[str, Any]]:
    parts = "snippet,statistics,contentDetails,status,liveStreamingDetails,topicDetails,recordingDetails"
    rows: List[Dict[str, Any]] = []
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
                "viewCount":                int(stats["viewCount"])    if stats.get("viewCount")    is not None else None,
                "likeCount":                int(stats["likeCount"])    if stats.get("likeCount")    is not None else None,
                "commentCount":             int(stats["commentCount"]) if stats.get("commentCount") is not None else None,
                "favoriteCount":            int(stats["favoriteCount"])if stats.get("favoriteCount")is not None else None,
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

print(f"Reading {IN_EXCEL} ...")
df_channels = pd.read_excel(IN_EXCEL)
print(f"  {len(df_channels):,} rows loaded")

# Filter: channels with a known video count under the cap
df_eligible = df_channels[
    df_channels["yt_videoCount"].notna() &
    (df_channels["yt_videoCount"] < MAX_VIDEOS) &
    df_channels["yt_uploadsPlaylist"].notna()
].drop_duplicates(subset=["channelId"]).reset_index(drop=True)

print(f"  {len(df_eligible):,} channels with < {MAX_VIDEOS:,} videos eligible")

# Identify which channels are already saved
os.makedirs(OUT_FOLDER, exist_ok=True)
already_saved = {
    fname.replace(".parquet", "")
    for fname in os.listdir(OUT_FOLDER)
    if fname.endswith(".parquet")
}

df_todo = df_eligible[~df_eligible["channelId"].isin(already_saved)].reset_index(drop=True)
n_skip  = len(df_eligible) - len(df_todo)

print(f"  Already saved (will skip) : {n_skip:,}")
print(f"  Missing — to fetch now    : {len(df_todo):,}")

if df_todo.empty:
    print("\nNothing to do — all eligible channels already have a parquet file.")
    import sys; sys.exit(0)

os.makedirs(OUT_FOLDER, exist_ok=True)

pool = KeyPool(API_KEYS)
collected_at = pd.Timestamp(datetime.now(timezone.utc))

for i, row in df_todo.iterrows():
    channel_id      = row["channelId"]
    handle          = row.get("yt_handle", channel_id)
    playlist_id     = row["yt_uploadsPlaylist"]
    video_count     = int(row["yt_videoCount"])
    name_page       = row.get("name.page", handle)

    out_path = os.path.join(OUT_FOLDER, f"{channel_id}.parquet")

    print(f"[{i+1}/{len(df_todo)}] {name_page} (@{handle})  videos={video_count:,}")

    try:
        # 1) Fetch all video IDs from uploads playlist
        playlist_meta = fetch_playlist_items(pool, playlist_id)
        video_ids = list(playlist_meta.keys())
        print(f"    Playlist items: {len(video_ids):,}")

        # 2) Fetch full video details
        video_rows = fetch_video_details(pool, video_ids)
        df = pd.DataFrame(video_rows)

        # 3) Merge playlist metadata
        pm = (
            pd.DataFrame.from_dict(playlist_meta, orient="index")
            .reset_index()
            .rename(columns={"index": "videoId"})
        )
        df = df.merge(pm, on="videoId", how="left")

        # 4) Normalize dates
        for col in ["publishedAt", "playlist_addedAt", "live_actualStartTime", "live_actualEndTime"]:
            df[f"{col}_dt"] = df[col].apply(iso_to_dt)

        # 5) Add channel identifiers and collection timestamp
        df["channel_id"]   = channel_id
        df["yt_handle"]    = handle
        df["name_page"]    = name_page
        df["collectedAt"]  = collected_at

        # 6) Sort chronologically and save
        df = df.sort_values("publishedAt_dt").reset_index(drop=True)
        df.to_parquet(out_path, index=False)
        print(f"    Saved: {out_path}  ({len(df):,} videos)")

    except Exception as e:
        print(f"  ERROR on {name_page} (@{handle}): {e}")
        continue


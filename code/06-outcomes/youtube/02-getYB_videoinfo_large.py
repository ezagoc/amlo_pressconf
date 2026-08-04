# =========================
# CONFIG
# =========================

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))
from project_paths import env_list, media_path, media_output_path

IN_EXCEL    = media_path("data", "06-outcomes", "youtube", "mexican_newspapers_youtube.xlsx")
OUT_FOLDER  = media_output_path("data", "06-outcomes", "youtube", "big_channels", ".keep").parent
CKPT_FOLDER = media_output_path("data", "06-outcomes", "youtube", "checkpoints", ".keep").parent
MIN_VIDEOS  = 30_000   # process channels with >= this many videos

DATE_FROM   = "2021-04-01"   # inclusive
DATE_TO     = "2024-12-31"   # inclusive (script converts to exclusive end)

API_KEYS = env_list("YOUTUBE_API_KEYS")

# =========================
# Imports
# =========================

import os
import re
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# =========================
# API key rotation
# =========================

class KeyPool:
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
        next_idx = self._idx + 1
        if next_idx >= len(self._keys):
            raise RuntimeError("All API keys have exhausted their quota.")
        self._idx = next_idx
        self.youtube = self._build(self._idx)
        print(f"  Rotated to API key [{self._idx + 1}/{len(self._keys)}]")

    def call(self, fn, max_retries: int = 6, base_sleep: float = 1.0):
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
                        break
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

def to_rfc3339(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")

# =========================
# Date window generators
# =========================

def monthly_windows(date_from: str, date_to: str) -> List[Tuple[datetime, datetime]]:
    """Inclusive [date_from, date_to] split into [month_start, next_month_start) pairs."""
    start = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end   = datetime.strptime(date_to,   "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
    windows = []
    cur = start
    while cur < end:
        # advance one month
        if cur.month == 12:
            nxt = cur.replace(year=cur.year + 1, month=1, day=1)
        else:
            nxt = cur.replace(month=cur.month + 1, day=1)
        nxt = min(nxt, end)
        windows.append((cur, nxt))
        cur = nxt
    return windows

def weekly_windows(month_start: datetime, month_end: datetime) -> List[Tuple[datetime, datetime]]:
    """Split a month into 7-day windows."""
    windows = []
    cur = month_start
    while cur < month_end:
        nxt = min(cur + timedelta(days=7), month_end)
        windows.append((cur, nxt))
        cur = nxt
    return windows

def daily_windows(week_start: datetime, week_end: datetime) -> List[Tuple[datetime, datetime]]:
    """Split a week into 1-day windows."""
    windows = []
    cur = week_start
    while cur < week_end:
        nxt = min(cur + timedelta(days=1), week_end)
        windows.append((cur, nxt))
        cur = nxt
    return windows

# =========================
# Checkpoint helpers
# =========================

def ckpt_path(channel_id: str) -> str:
    return os.path.join(CKPT_FOLDER, f"{channel_id}_search.json")

def load_checkpoint(channel_id: str) -> Dict:
    p = ckpt_path(channel_id)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"done_windows": [], "video_ids": []}

def save_checkpoint(channel_id: str, state: Dict):
    with open(ckpt_path(channel_id), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)

def clear_checkpoint(channel_id: str):
    p = ckpt_path(channel_id)
    if os.path.exists(p):
        os.remove(p)

# =========================
# Search: one window
# =========================

SEARCH_PAGE_LIMIT = 10   # YouTube caps search pagination at ~10 pages (500 results)

def search_window(
    pool: KeyPool,
    channel_id: str,
    after: datetime,
    before: datetime,
) -> Tuple[List[str], bool]:
    """
    Fetch video IDs published in [after, before) for a channel.
    Returns (video_ids, hit_cap).
    hit_cap=True means we reached SEARCH_PAGE_LIMIT pages and may have missed results.
    """
    ids        = []
    page_token = None
    pages      = 0

    while True:
        resp = pool.call(lambda yt, pt=page_token: yt.search().list(
            part="id",
            channelId=channel_id,
            type="video",
            publishedAfter=to_rfc3339(after),
            publishedBefore=to_rfc3339(before),
            maxResults=50,
            pageToken=pt,
        ).execute())

        for item in resp.get("items", []):
            vid = (item.get("id") or {}).get("videoId")
            if vid:
                ids.append(vid)

        page_token = resp.get("nextPageToken")
        pages += 1

        if not page_token or pages >= SEARCH_PAGE_LIMIT:
            break

    hit_cap = (pages >= SEARCH_PAGE_LIMIT and page_token is not None)
    return ids, hit_cap

# =========================
# Adaptive search for a channel
# =========================

def collect_video_ids(
    pool: KeyPool,
    channel_id: str,
    date_from: str,
    date_to: str,
    checkpoint: Dict,
) -> List[str]:
    """
    Iterate monthly windows; if a month hits the 500-result cap, sub-chunk weekly;
    if a week hits the cap, sub-chunk daily.
    Resumes from checkpoint.
    """
    done_windows = set(checkpoint.get("done_windows", []))
    all_ids      = list(checkpoint.get("video_ids", []))
    id_set       = set(all_ids)   # dedup across windows

    months = monthly_windows(date_from, date_to)
    print(f"    {len(months)} monthly windows to scan")

    for m_start, m_end in months:
        win_key = f"{to_rfc3339(m_start)}|{to_rfc3339(m_end)}"
        if win_key in done_windows:
            continue

        ids, hit_cap = search_window(pool, channel_id, m_start, m_end)

        if hit_cap:
            print(f"    {m_start.strftime('%Y-%m')} hit cap ({len(ids)}) — splitting into weeks")
            ids = []
            for w_start, w_end in weekly_windows(m_start, m_end):
                w_key = f"{to_rfc3339(w_start)}|{to_rfc3339(w_end)}"
                if w_key in done_windows:
                    continue
                w_ids, w_hit_cap = search_window(pool, channel_id, w_start, w_end)

                if w_hit_cap:
                    print(f"      {w_start.strftime('%Y-%m-%d')} week hit cap ({len(w_ids)}) — splitting into days")
                    w_ids = []
                    for d_start, d_end in daily_windows(w_start, w_end):
                        d_ids, _ = search_window(pool, channel_id, d_start, d_end)
                        w_ids.extend(d_ids)

                new = [v for v in w_ids if v not in id_set]
                id_set.update(new)
                ids.extend(new)
                done_windows.add(w_key)

            # Save after each sub-chunked month
            all_ids.extend([v for v in ids if v not in set(all_ids)])
            checkpoint = {"done_windows": list(done_windows), "video_ids": all_ids}
            save_checkpoint(channel_id, checkpoint)

        else:
            new = [v for v in ids if v not in id_set]
            id_set.update(new)
            all_ids.extend(new)

        done_windows.add(win_key)

        month_label = m_start.strftime("%Y-%m")
        total = len(ids) if not hit_cap else len([v for v in ids if True])
        print(f"    {month_label}: {len([v for v in (ids if not isinstance(ids, list) else ids)]):>5} new IDs  |  total so far: {len(all_ids):,}")

        # Checkpoint every month
        checkpoint = {"done_windows": list(done_windows), "video_ids": all_ids}
        save_checkpoint(channel_id, checkpoint)

    return all_ids

# =========================
# Video details
# =========================

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

print(f"Reading {IN_EXCEL} ...")
df_channels = pd.read_excel(IN_EXCEL)
print(f"  {len(df_channels):,} rows loaded")

df_todo = df_channels[
    df_channels["yt_videoCount"].notna() &
    (df_channels["yt_videoCount"] >= MIN_VIDEOS) &
    df_channels["yt_uploadsPlaylist"].notna()
].drop_duplicates(subset=["channelId"]).reset_index(drop=True)

print(f"  {len(df_todo):,} channels with >= {MIN_VIDEOS:,} videos to process")

os.makedirs(OUT_FOLDER,  exist_ok=True)
os.makedirs(CKPT_FOLDER, exist_ok=True)

pool = KeyPool(API_KEYS)
collected_at = pd.Timestamp(datetime.now(timezone.utc))

for i, row in df_todo.iterrows():
    channel_id  = row["channelId"]
    handle      = row.get("yt_handle", channel_id)
    video_count = int(row["yt_videoCount"])
    name_page   = row.get("name.page", handle)

    out_path = os.path.join(OUT_FOLDER, f"{handle}.parquet")

    if os.path.exists(out_path):
        print(f"[{i+1}/{len(df_todo)}] SKIP {name_page} (@{handle}) — already saved")
        continue

    print(f"[{i+1}/{len(df_todo)}] {name_page} (@{handle})  total_videos={video_count:,}")

    try:
        # Phase 1 — collect video IDs via search (with checkpoint resume)
        checkpoint = load_checkpoint(channel_id)
        if checkpoint["video_ids"]:
            print(f"    Resuming from checkpoint: {len(checkpoint['video_ids']):,} IDs already collected, "
                  f"{len(checkpoint['done_windows'])} windows done")

        video_ids = collect_video_ids(pool, channel_id, DATE_FROM, DATE_TO, checkpoint)
        video_ids = list(dict.fromkeys(video_ids))   # final dedup preserving order
        print(f"    Total unique video IDs for {DATE_FROM}–{DATE_TO}: {len(video_ids):,}")

        # Phase 2 — fetch full metadata for each ID
        if not video_ids:
            print(f"    No videos found in date range — saving empty file.")
            df = pd.DataFrame()
        else:
            print(f"    Fetching video details ...")
            video_rows = fetch_video_details(pool, video_ids)
            df = pd.DataFrame(video_rows)

        # Phase 3 — normalize dates, add identifiers, save
        for col in ["publishedAt", "live_actualStartTime", "live_actualEndTime"]:
            df[f"{col}_dt"] = df[col].apply(iso_to_dt) if col in df.columns else None

        df["channel_id"]  = channel_id
        df["yt_handle"]   = handle
        df["name_page"]   = name_page
        df["collectedAt"] = collected_at

        if "publishedAt_dt" in df.columns:
            df = df.sort_values("publishedAt_dt").reset_index(drop=True)
        df.to_parquet(out_path, index=False)
        print(f"    Saved: {out_path}  ({len(df):,} videos)")

        clear_checkpoint(channel_id)

    except Exception as e:
        print(f"  ERROR on {name_page} (@{handle}): {e}")
        print(f"  Checkpoint preserved — re-run to resume from where it stopped.")
        continue

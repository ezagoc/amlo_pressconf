# %%
# =========================
# CONFIG (edit these)
# =========================

PLAYLIST_URL = "https://www.youtube.com/playlist?list=PLRnlRGar-_296KTsVL0R6MEbpwJzD8ppA"

# Put your own output path here (Parquet file)
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))
from project_paths import media_output_path, env_list

OUT_PARQUET = media_output_path("data", "02-conferences", "auxiliar", "mananeras_playlist.parquet")

# Optional: also write a CSV next to the parquet
WRITE_CSV_TOO = False

# If True, shows a quick plot at the end
MAKE_PLOT = True


# %%
# =========================
# Dependencies
# =========================
# This cell tries to install missing packages using the current VS Code interpreter.
# If you prefer not to auto-install, set AUTO_INSTALL = False.

AUTO_INSTALL = True

import sys
import subprocess

def ensure_package(pkg: str):
    try:
        __import__(pkg)
    except Exception:
        if not AUTO_INSTALL:
            raise
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", pkg])

# Core deps
ensure_package("pandas")
ensure_package("pyarrow")  # for parquet
ensure_package("googleapiclient")
ensure_package("dotenv")   # python-dotenv
ensure_package("matplotlib")

print("✅ Dependencies ready")


# %%
# =========================
# Imports
# =========================

import os
import re
import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

import pandas as pd
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# %%
# =========================
# Helpers
# =========================

def extract_playlist_id(s: str) -> str:
    m = re.search(r"[?&]list=([A-Za-z0-9_-]+)", s)
    return m.group(1) if m else s.strip()

def iso_to_dt(iso_str: Optional[str]) -> Optional[pd.Timestamp]:
    if not iso_str:
        return None
    try:
        return pd.to_datetime(iso_str, utc=True)
    except Exception:
        return None

def chunked(xs: List[str], n: int) -> List[List[str]]:
    return [xs[i:i+n] for i in range(0, len(xs), n)]

def safe_json(x: Any) -> Optional[str]:
    # Store dict/list fields as JSON strings to keep Parquet simple.
    if x is None:
        return None
    try:
        return json.dumps(x, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(x)

def parse_iso8601_duration_to_seconds(duration: Optional[str]) -> Optional[int]:
    # Example: "PT1H23M45S" -> seconds
    if not duration or not isinstance(duration, str):
        return None
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not m:
        return None
    h = int(m.group(1) or 0)
    mm = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return h * 3600 + mm * 60 + s

def call_with_retries(fn, max_retries: int = 6, base_sleep: float = 1.0):
    # Basic exponential backoff for transient API errors (429/5xx/quota-ish).
    for attempt in range(max_retries):
        try:
            return fn()
        except HttpError as e:
            status = getattr(e.resp, "status", None)
            msg = str(e).lower()
            if status in (429, 500, 503) or (status == 403 and "quota" in msg):
                time.sleep(base_sleep * (2 ** attempt))
                continue
            raise
    raise RuntimeError("Max retries exceeded.")


# %%
# =========================
# YouTube API extractors
# =========================

def fetch_playlist_items(youtube, playlist_id: str) -> Dict[str, Dict[str, Any]]:
    """
    Returns map: videoId -> playlist metadata (position, addedAt, etc.)
    """
    out: Dict[str, Dict[str, Any]] = {}
    page_token = None

    while True:
        resp = call_with_retries(lambda: youtube.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=page_token,
        ).execute())

        for it in resp.get("items", []):
            snip = it.get("snippet", {}) or {}
            cd = it.get("contentDetails", {}) or {}

            vid = cd.get("videoId") or ((snip.get("resourceId") or {}).get("videoId"))
            if not vid:
                continue

            out[vid] = {
                "playlistItemId": it.get("id"),
                "playlist_position": snip.get("position"),
                "playlist_addedAt": snip.get("publishedAt"),  # when added to playlist
                "playlist_itemTitle": snip.get("title"),
                "playlist_itemChannelTitle": snip.get("channelTitle"),
                "playlist_videoPublishedAt": cd.get("videoPublishedAt"),
            }

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return out


def fetch_videos_details(youtube, video_ids: List[str]) -> List[Dict[str, Any]]:
    """
    Fetch per-video public fields.
    Note: watch time, retention, impressions are not public via Data API.
    """
    parts = "snippet,statistics,contentDetails,status,liveStreamingDetails,topicDetails,recordingDetails"
    rows: List[Dict[str, Any]] = []

    for chunk in chunked(video_ids, 50):
        resp = call_with_retries(lambda: youtube.videos().list(
            part=parts,
            id=",".join(chunk),
            maxResults=50,
        ).execute())

        for v in resp.get("items", []):
            snip = v.get("snippet", {}) or {}
            stats = v.get("statistics", {}) or {}
            cd = v.get("contentDetails", {}) or {}
            st = v.get("status", {}) or {}
            live = v.get("liveStreamingDetails", {}) or {}
            topic = v.get("topicDetails", {}) or {}
            rec = v.get("recordingDetails", {}) or {}

            rows.append({
                # IDs
                "videoId": v.get("id"),

                # Snippet
                "title": snip.get("title"),
                "description": snip.get("description"),
                "publishedAt": snip.get("publishedAt"),
                "channelId": snip.get("channelId"),
                "channelTitle": snip.get("channelTitle"),
                "categoryId": snip.get("categoryId"),
                "defaultLanguage": snip.get("defaultLanguage"),
                "defaultAudioLanguage": snip.get("defaultAudioLanguage"),
                "tags_json": safe_json(snip.get("tags")),  # list -> json string

                # Statistics (public)
                "viewCount": int(stats.get("viewCount")) if stats.get("viewCount") is not None else None,
                "likeCount": int(stats.get("likeCount")) if stats.get("likeCount") is not None else None,
                "commentCount": int(stats.get("commentCount")) if stats.get("commentCount") is not None else None,
                "favoriteCount": int(stats.get("favoriteCount")) if stats.get("favoriteCount") is not None else None,

                # Content details
                "duration_iso": cd.get("duration"),
                "duration_seconds": parse_iso8601_duration_to_seconds(cd.get("duration")),
                "dimension": cd.get("dimension"),
                "definition": cd.get("definition"),
                "caption": cd.get("caption"),
                "licensedContent": cd.get("licensedContent"),
                "projection": cd.get("projection"),
                "regionRestriction_json": safe_json(cd.get("regionRestriction")),

                # Status
                "uploadStatus": st.get("uploadStatus"),
                "privacyStatus": st.get("privacyStatus"),
                "license": st.get("license"),
                "embeddable": st.get("embeddable"),
                "publicStatsViewable": st.get("publicStatsViewable"),
                "madeForKids": st.get("madeForKids"),
                "selfDeclaredMadeForKids": st.get("selfDeclaredMadeForKids"),

                # Live streaming details (if applicable)
                "live_actualStartTime": live.get("actualStartTime"),
                "live_actualEndTime": live.get("actualEndTime"),
                "live_scheduledStartTime": live.get("scheduledStartTime"),
                "live_scheduledEndTime": live.get("scheduledEndTime"),
                "live_concurrentViewers": int(live.get("concurrentViewers")) if live.get("concurrentViewers") else None,

                # Topic / Recording (often empty, but keep as json)
                "topicDetails_json": safe_json(topic if topic else None),
                "recordingDate": rec.get("recordingDate"),
                "recordingDetails_json": safe_json(rec if rec else None),
            })

    return rows


def run_playlist_to_parquet(playlist_url: str, out_parquet: str, write_csv_too: bool = True) -> pd.DataFrame:
    # Load API key from .env / environment
    load_dotenv()
    api_key = env_list("YOUTUBE_API_KEYS")[0]
    if not api_key:
        raise RuntimeError("Missing YT_API_KEY. Put it in a .env file or environment variable.")

    playlist_id = extract_playlist_id(playlist_url)
    youtube = build("youtube", "v3", developerKey=api_key)

    # 1) Playlist items
    playlist_meta = fetch_playlist_items(youtube, playlist_id)
    video_ids = list(playlist_meta.keys())
    if not video_ids:
        raise RuntimeError("No videos found in the playlist (check ID/visibility).")

    # 2) Video details
    video_rows = fetch_videos_details(youtube, video_ids)
    df = pd.DataFrame(video_rows)

    # Merge playlist metadata
    pm = (pd.DataFrame.from_dict(playlist_meta, orient="index")
          .reset_index()
          .rename(columns={"index": "videoId"}))
    df = df.merge(pm, on="videoId", how="left")

    # Normalize dates
    df["publishedAt_dt"] = df["publishedAt"].apply(iso_to_dt)
    df["playlist_addedAt_dt"] = df["playlist_addedAt"].apply(iso_to_dt)
    df["live_actualStartTime_dt"] = df["live_actualStartTime"].apply(iso_to_dt)
    df["live_actualEndTime_dt"] = df["live_actualEndTime"].apply(iso_to_dt)

    # Snapshot timestamp (when you collected the stats)
    df["collectedAt_utc"] = pd.Timestamp(datetime.now(timezone.utc))

    # Sort for time series (X axis)
    df = df.sort_values("publishedAt_dt").reset_index(drop=True)

    # Ensure output dir exists
    out_dir = os.path.dirname(out_parquet) or "."
    os.makedirs(out_dir, exist_ok=True)

    # Save Parquet (+ optional CSV)
    df.to_parquet(out_parquet, index=False)
    if write_csv_too:
        csv_path = re.sub(r"\.parquet$", "", out_parquet) + ".csv"
        df.to_csv(csv_path, index=False)

    return df


# %%
# =========================
# RUN (this is the cell you execute)
# =========================

df = run_playlist_to_parquet(
    playlist_url=PLAYLIST_URL,
    out_parquet=OUT_PARQUET,
    write_csv_too=WRITE_CSV_TOO,
)

print(f"✅ Saved: {OUT_PARQUET}")
print(f"Rows: {len(df):,}")
df[["publishedAt_dt", "viewCount", "likeCount", "commentCount", "title"]].tail(5)


# %%
# =========================
# Optional: quick plot (Views over publication date)
# =========================

if MAKE_PLOT:
    dff = df.dropna(subset=["publishedAt_dt", "viewCount"]).copy()
    plt.figure()
    plt.plot(dff["publishedAt_dt"], dff["viewCount"])
    plt.xlabel("publishedAt (UTC)")
    plt.ylabel("views (snapshot)")
    plt.title("Mañaneras playlist: views by publication date")
    plt.tight_layout()
    plt.show()

# %%

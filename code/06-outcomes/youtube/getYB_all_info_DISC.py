# =========================
# CONFIG
# =========================

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))
from project_paths import env_list, media_path, media_output_path

IN_EXCEL   = media_path("data", "00-newspaper_data", "mexican_newspapers.xlsx")
OUT_FOLDER = media_output_path("data", "06-outcomes", "youtube", ".keep").parent
API_KEY    = env_list("YOUTUBE_API_KEYS")[0]

# =========================
# Imports
# =========================

import os
import re
import time

sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# =========================
# Helpers
# =========================

def extract_handle(s: str) -> str:
    """Return bare handle (no @, no URL) from various input formats."""
    if not isinstance(s, str):
        return ""
    m = re.search(r"@([A-Za-z0-9._-]+)", s)
    if m:
        return m.group(1)
    # strip leading @ or URL cruft
    s = s.strip().lstrip("@")
    # remove trailing path segments
    s = s.split("/")[0]
    return s.strip()

def call_with_retries(fn, max_retries: int = 6, base_sleep: float = 1.0):
    """Exponential backoff for transient API errors (429/5xx/quota)."""
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

# =========================
# Step 1 — Load & build name-channel mapping
# =========================

print(f"Reading {IN_EXCEL} ...")
df_news = pd.read_excel(IN_EXCEL)
print(f"  {len(df_news):,} newspapers loaded")

# Build deduplicated mapping: one row per (name.page, yt_handle)
mapping_rows = []
for _, row in df_news.iterrows():
    if pd.isna(row.get("youtube.channel")):
        continue
    handles = [extract_handle(h) for h in str(row["youtube.channel"]).split(",")]
    handles = [h for h in handles if h]
    for h in handles:
        mapping_rows.append({
            "name.page":       row["name.page"],
            "youtube.channel": row["youtube.channel"],
            "yt_handle":       h,
        })

df_map = pd.DataFrame(mapping_rows).drop_duplicates(subset=["name.page", "yt_handle"]).reset_index(drop=True)
print(f"  {len(df_map):,} name-channel pairs ({df_map['yt_handle'].nunique():,} unique handles)")

# Save the mapping file
os.makedirs(OUT_FOLDER, exist_ok=True)
map_path = os.path.join(OUT_FOLDER, "name_youtube_mapping.xlsx")
df_map.to_excel(map_path, index=False)
print(f"  Mapping saved: {map_path}")

# =========================
# Step 2 — Fetch channel info for unique handles
# =========================

youtube = build("youtube", "v3", developerKey=API_KEY)

unique_handles = df_map["yt_handle"].unique().tolist()
print(f"\nFetching info for {len(unique_handles):,} unique handles ...")

channel_rows = []
for i, handle in enumerate(unique_handles, 1):
    if i % 10 == 0:
        print(f"  ...{i}/{len(unique_handles)}")
    try:
        resp = call_with_retries(lambda h=handle: youtube.channels().list(
            part="id,snippet,statistics,contentDetails,brandingSettings,topicDetails",
            forHandle=h,
        ).execute())
        items = resp.get("items", [])
        if items:
            ch    = items[0]
            snip  = ch.get("snippet", {})
            stats = ch.get("statistics", {})
            brand = ch.get("brandingSettings", {}).get("channel", {})
            topic = ch.get("topicDetails", {})
            cd    = ch.get("contentDetails", {}).get("relatedPlaylists", {})
            channel_rows.append({
                "yt_handle":          handle,
                "channelId":          ch.get("id"),
                "yt_title":           snip.get("title"),
                "yt_customUrl":       snip.get("customUrl"),
                "yt_country":         snip.get("country"),
                "yt_createdAt":       snip.get("publishedAt"),
                "yt_description":     snip.get("description"),
                "yt_subscriberCount": int(stats["subscriberCount"]) if stats.get("subscriberCount") else None,
                "yt_hiddenSubs":      stats.get("hiddenSubscriberCount"),
                "yt_videoCount":      int(stats["videoCount"]) if stats.get("videoCount") else None,
                "yt_viewCount":       int(stats["viewCount"]) if stats.get("viewCount") else None,
                "yt_uploadsPlaylist": cd.get("uploads"),
                "yt_keywords":        brand.get("keywords"),
                "yt_topicCategories": ", ".join(topic.get("topicCategories", [])),
            })
        else:
            channel_rows.append({"yt_handle": handle})
    except Exception as e:
        print(f"  WARNING: failed for @{handle}: {e}")
        channel_rows.append({"yt_handle": handle})

df_channels = pd.DataFrame(channel_rows)
print(f"OK: Channel info fetched: {len(df_channels):,} rows")

# =========================
# Step 3 — Merge mapping + channel data and save
# =========================

# One row per (name.page, yt_handle) with channel stats
df_out = df_map.merge(df_channels, on="yt_handle", how="left")

out_path = os.path.join(OUT_FOLDER, "mexican_newspapers_youtube.xlsx")
df_out.to_excel(out_path, index=False)

print(f"\nSaved: {out_path}")
print(f"   Rows: {len(df_out):,}  |  Columns: {len(df_out.columns):,}")
print(df_out[["name.page", "yt_handle", "yt_title", "yt_subscriberCount", "yt_videoCount"]].head(10).to_string())

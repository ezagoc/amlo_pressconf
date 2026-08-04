# =========================
# CONFIG
# =========================

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))
from project_paths import media_path, media_output_path

CHANNEL_EXCEL  = media_path("data", "06-outcomes", "youtube", "mexican_newspapers_youtube.xlsx")
SOURCE_FOLDERS = [
    media_path("data", "06-outcomes", "youtube", "videos"),
    media_path("data", "06-outcomes", "youtube", "big_channels"),
    media_path("data", "06-outcomes", "youtube", "playlists", "videos"),
]
OUT_PANEL  = media_output_path("data", "06-outcomes", "youtube", "panel_daily.parquet")
DATE_FROM  = "2018-01-01"
DATE_TO    = "2024-12-31"

# =========================
# Imports
# =========================

sys.stdout.reconfigure(encoding="utf-8")

import os
import glob
import pandas as pd

# =========================
# Step 1 — Channel dimension
# =========================

df_ch = pd.read_excel(CHANNEL_EXCEL)
df_ch = df_ch.drop_duplicates(subset=["channelId"]).reset_index(drop=True)
keep_cols = [c for c in ["channelId", "yt_handle", "yt_customUrl", "name.page"] if c in df_ch.columns]
df_ch = df_ch[keep_cols]
print(f"Channels in dimension table: {len(df_ch):,}")

# =========================
# Step 2 — Daily panel skeleton
# =========================

dates = pd.date_range(DATE_FROM, DATE_TO, freq="D")
panel = pd.MultiIndex.from_product(
    [df_ch["channelId"], dates], names=["channel_id", "date"]
).to_frame(index=False)
print(f"Panel skeleton: {len(panel):,} rows  ({len(df_ch):,} channels × {len(dates):,} days)")

# =========================
# Step 3 — Load all video parquets
# =========================

COLS = ["videoId", "channel_id", "publishedAt_dt", "viewCount", "likeCount", "commentCount"]

chunks = []
for folder in SOURCE_FOLDERS:
    files = glob.glob(os.path.join(folder, "*.parquet"))
    print(f"  {folder}  →  {len(files):,} parquet file(s)")
    for f in files:
        try:
            tmp = pd.read_parquet(f)
            avail = [c for c in COLS if c in tmp.columns]
            chunks.append(tmp[avail])
        except Exception as e:
            print(f"    WARNING: could not read {f}: {e}")

if not chunks:
    print("ERROR: no video data found — check SOURCE_FOLDERS.")
    sys.exit(1)

df_v = pd.concat(chunks, ignore_index=True)
print(f"\nTotal videos loaded (before dedup): {len(df_v):,}")

# Deduplicate on videoId
df_v = df_v.drop_duplicates(subset=["videoId"]).reset_index(drop=True)
print(f"Total videos after dedup:           {len(df_v):,}")

# Parse date
def to_naive_date(series):
    s = pd.to_datetime(series, utc=True, errors="coerce")
    return s.dt.tz_localize(None).dt.normalize()

if "publishedAt_dt" in df_v.columns:
    col = df_v["publishedAt_dt"]
    # If already datetime, handle tz
    if pd.api.types.is_datetime64_any_dtype(col):
        if hasattr(col.dt, "tz") and col.dt.tz is not None:
            df_v["date"] = col.dt.tz_localize(None).dt.normalize()
        else:
            df_v["date"] = col.dt.normalize()
    else:
        df_v["date"] = to_naive_date(col)
else:
    print("ERROR: publishedAt_dt column missing.")
    sys.exit(1)

# Filter to panel date range
d_from = pd.Timestamp(DATE_FROM)
d_to   = pd.Timestamp(DATE_TO)
df_v = df_v[(df_v["date"] >= d_from) & (df_v["date"] <= d_to)].copy()
print(f"Videos within {DATE_FROM}–{DATE_TO}:  {len(df_v):,}")

# =========================
# Step 4 — Coverage flags
# =========================

first_date = df_v.groupby("channel_id")["date"].min().rename("first_video_date")
flags = first_date.reset_index()
flags["flag_no_2018"] = flags["first_video_date"] > pd.Timestamp("2018-12-31")
flags["flag_no_2021"] = flags["first_video_date"] > pd.Timestamp("2021-12-31")

print(f"\nCoverage flags:")
print(f"  flag_no_2018 (first video after 2018): {flags['flag_no_2018'].sum():,} channels")
print(f"  flag_no_2021 (first video after 2021): {flags['flag_no_2021'].sum():,} channels")

channels_no_data = set(df_ch["channelId"]) - set(flags["channel_id"])
print(f"  Channels with no video data at all:    {len(channels_no_data):,}")

# Drop channels with no video data from both the skeleton and the dimension table
if channels_no_data:
    panel  = panel[~panel["channel_id"].isin(channels_no_data)]
    df_ch  = df_ch[~df_ch["channelId"].isin(channels_no_data)]
    print(f"  Removed {len(channels_no_data):,} channels — panel now {len(panel):,} rows")

# =========================
# Step 5 — Daily aggregation
# =========================

daily = (
    df_v.groupby(["channel_id", "date"])
    .agg(
        n_videos   =("videoId",      "count"),
        viewCount  =("viewCount",    "sum"),
        likeCount  =("likeCount",    "sum"),
        commentCount=("commentCount","sum"),
    )
    .reset_index()
)

# =========================
# Step 6 — Merge and fill
# =========================

panel = panel.merge(
    df_ch.rename(columns={"channelId": "channel_id"}),
    on="channel_id", how="left"
)
panel = panel.merge(
    flags[["channel_id", "flag_no_2018", "flag_no_2021"]],
    on="channel_id", how="left"
)
panel = panel.merge(daily, on=["channel_id", "date"], how="left")

metric_cols = ["n_videos", "viewCount", "likeCount", "commentCount"]
panel[metric_cols] = panel[metric_cols].fillna(0).astype(int)

# Published dummy
panel["published"] = (panel["n_videos"] > 0).astype(int)

# Per-video ratios (0 on days with no videos)
for metric in ["viewCount", "likeCount", "commentCount"]:
    panel[f"{metric}_per_video"] = (
        panel[metric].where(panel["n_videos"] > 0)
        / panel["n_videos"].where(panel["n_videos"] > 0)
    ).fillna(0)

print(f"\nFinal panel shape: {panel.shape}")
print(f"Columns: {list(panel.columns)}")

# =========================
# Step 7 — Save
# =========================

panel.to_parquet(OUT_PANEL, index=False)
print(f"\nSaved: {OUT_PANEL}")

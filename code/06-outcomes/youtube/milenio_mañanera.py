# =========================
# CONFIG
# =========================

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))
from project_paths import media_path, media_output_path

VIDEOS_PATH = media_path("data", "06-outcomes", "youtube", "milenio", "videos.parquet")
OUT_FIG     = media_output_path("data", "06-outcomes", "youtube", "milenio", "milenio_mañanera.png")

# =========================
# Imports
# =========================

import sys
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# =========================
# Load & filter
# =========================

df = pd.read_parquet(VIDEOS_PATH)
print(f"Total videos loaded: {len(df):,}")

mask = df["title"].str.contains("mañanera", case=False, na=False)
df_m = df[mask].copy()
print(f"Mañanera videos matched: {len(df_m):,}")

if df_m.empty:
    print("No videos matched — check the title column.")
    sys.exit(0)

# Ensure datetime column
if "publishedAt_dt" not in df_m.columns:
    df_m["publishedAt_dt"] = pd.to_datetime(df_m["publishedAt"], utc=True, errors="coerce")

df_m = df_m.dropna(subset=["publishedAt_dt"]).sort_values("publishedAt_dt").reset_index(drop=True)
df_m["date"] = df_m["publishedAt_dt"].dt.tz_localize(None)   # strip tz for plotting

# =========================
# Summary stats
# =========================

print(f"\nDate range : {df_m['date'].min().date()} → {df_m['date'].max().date()}")
for col in ["viewCount", "likeCount", "commentCount"]:
    s = df_m[col].dropna()
    print(f"{col:>14}  mean={s.mean():,.0f}  median={s.median():,.0f}  max={s.max():,.0f}")

# =========================
# Rolling means (30-day window)
# =========================

df_m = df_m.set_index("date")
metrics = [
    ("viewCount",    "Views",    "#1f77b4"),
    ("likeCount",    "Likes",    "#2ca02c"),
    ("commentCount", "Comments", "#d62728"),
]

fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
fig.suptitle("Milenio — Mañanera videos over time", fontsize=14, fontweight="bold")

for ax, (col, label, color) in zip(axes, metrics):
    series = df_m[col].dropna()
    rolling = series.rolling("30D").mean()

    ax.scatter(series.index, series.values, s=15, alpha=0.35, color=color, label="Per video")
    ax.plot(rolling.index, rolling.values, color=color, linewidth=1.8, label="30-day rolling mean")

    ax.set_ylabel(label)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(axis="y", linestyle="--", alpha=0.4)

axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
axes[-1].xaxis.set_major_locator(mdates.MonthLocator(interval=3))
fig.autofmt_xdate(rotation=45)

plt.tight_layout()
plt.savefig(OUT_FIG, dpi=150, bbox_inches="tight")
print(f"\nFigure saved: {OUT_FIG}")
plt.show()

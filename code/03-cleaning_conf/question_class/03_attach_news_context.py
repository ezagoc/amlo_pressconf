"""
build_news_context.py
=====================
Attach daily news context to each reporter row in the periodistas dataset.

For each mañanera conference, the relevant news is from the PREVIOUS day(s),
since the conference happens in the morning before that day's papers are out:

  Monday conference     → news from preceding Friday + Saturday + Sunday
  Tuesday–Friday conf.  → news from the previous calendar day

Inputs
------
  daily_summaries.parquet        — one row per calendar day (from article_classification.py)
  periodistas_v2_all_years.parquet — one row per reporter question at a mañanera

Output
------
  periodistas_with_news_context.parquet — periodistas rows + news context columns

Usage
-----
  python build_news_context.py
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[2]))
from project_paths import media_path


# =============================================================================
# Paths
# =============================================================================

DATA_ROOT        = media_path("data")
SUMMARIES_PATH   = DATA_ROOT / "00-newspaper_data/processed/daily_summaries.parquet"
PERIODISTAS_PATH = DATA_ROOT / "02-conferences/auxiliar/periodistas_v2_all_years.parquet"
OUTPUT_PATH      = DATA_ROOT / "02-conferences/auxiliar/periodistas_with_news_context.parquet"


# =============================================================================
# Context date logic
# =============================================================================

def get_context_dates(conf_date: pd.Timestamp) -> list[pd.Timestamp]:
    """
    Return the list of calendar dates whose news provides context for conf_date.

    Monday  → [preceding Friday, Saturday, Sunday]
    Tue–Fri → [previous calendar day]
    """
    dow = conf_date.weekday()  # 0=Mon … 6=Sun
    if dow == 0:  # Monday
        return [
            conf_date - pd.Timedelta(days=3),  # Friday
            conf_date - pd.Timedelta(days=2),  # Saturday
            conf_date - pd.Timedelta(days=1),  # Sunday
        ]
    else:  # Tuesday–Friday
        return [conf_date - pd.Timedelta(days=1)]


# =============================================================================
# Build context table
# =============================================================================

def build_context_table(
    summaries: pd.DataFrame,
    conf_dates: pd.Series,
) -> pd.DataFrame:
    """
    For each unique conference date, fetch and concatenate the relevant
    daily summaries into a single news_context string.

    Returns a DataFrame with one row per unique conference date.
    """
    summaries_idx = summaries.set_index("date")

    records = []
    for conf_date in conf_dates:
        cdates = get_context_dates(conf_date)
        rows   = [summaries_idx.loc[d] for d in cdates if d in summaries_idx.index]

        if not rows:
            records.append({
                "date":             conf_date,
                "news_context":     None,
                "n_context_days":   0,
                "n_articles_total": 0,
                "context_dates":    [],
            })
            continue

        parts = []
        for r in rows:
            label = r.name.strftime("%A %Y-%m-%d")  # e.g. "Friday 2018-01-05"
            parts.append(f"[{label}]\n{r['daily_summary']}")

        records.append({
            "date":             conf_date,
            "news_context":     "\n\n".join(parts),
            "n_context_days":   len(rows),
            "n_articles_total": int(sum(r["n_articles"] for r in rows)),
            "context_dates":    [r.name.date() for r in rows],
        })

    return pd.DataFrame(records)


# =============================================================================
# Main
# =============================================================================

def main() -> None:
    # --- Load inputs ---
    print("Loading daily summaries...")
    summaries = pd.read_parquet(SUMMARIES_PATH)
    summaries["date"] = pd.to_datetime(summaries["date"])
    summaries = summaries.sort_values("date").reset_index(drop=True)
    print(f"  {len(summaries):,} daily summaries  "
          f"({summaries['date'].min().date()} → {summaries['date'].max().date()})")

    print("Loading periodistas...")
    periodistas = pd.read_parquet(PERIODISTAS_PATH)
    periodistas["date"] = pd.to_datetime(periodistas["date"])
    print(f"  {len(periodistas):,} rows  "
          f"({periodistas['date'].min().date()} → {periodistas['date'].max().date()})")

    # --- Build context table ---
    print("\nBuilding context table...")
    conf_dates = periodistas["date"].drop_duplicates().sort_values()
    context    = build_context_table(summaries, conf_dates)
    print(f"  {len(context):,} unique conference dates")
    n_with = context["news_context"].notna().sum()
    print(f"  {n_with:,} have at least one context day  "
          f"({100 * n_with / len(context):.1f}%)")

    # --- Merge ---
    print("\nMerging with periodistas...")
    merged = periodistas.merge(context, on="date", how="left")
    assert len(merged) == len(periodistas), "Row count changed after merge!"

    n_ctx = merged["news_context"].notna().sum()
    print(f"  Merged shape: {merged.shape}")
    print(f"  Rows with news context: {n_ctx:,} / {len(merged):,} "
          f"({100 * n_ctx / len(merged):.1f}%)")

    # --- Spot-check ---
    monday = merged[merged["date"].dt.weekday == 0].dropna(subset=["news_context"]).iloc[0]
    print(f"\nSpot-check Monday {monday['date'].date()}:")
    print(f"  context_dates:    {monday['context_dates']}")
    print(f"  n_context_days:   {monday['n_context_days']}")
    print(f"  n_articles_total: {monday['n_articles_total']}")
    print(f"  news_context preview:\n    "
          + monday["news_context"][:300].replace("\n", "\n    "))

    tuesday = merged[merged["date"].dt.weekday == 1].dropna(subset=["news_context"]).iloc[0]
    print(f"\nSpot-check Tuesday {tuesday['date'].date()}:")
    print(f"  context_dates: {tuesday['context_dates']}")

    # --- Save ---
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(OUTPUT_PATH, index=False)
    print(f"\nSaved → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

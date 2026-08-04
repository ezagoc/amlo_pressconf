# =========================
# CONFIG
# =========================

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))
from project_paths import media_path, media_output_path

IN_EXCEL      = media_path("data", "00-newspaper_data", "mexican_newspapers.xlsx")
IN_MAPPING    = media_path("data", "06-outcomes", "gtrends", "name_gtrends_mapping.xlsx")
CKPT_IOT      = media_path("data", "06-outcomes", "gtrends", "checkpoints", "iot")
CKPT_IBR      = media_path("data", "06-outcomes", "gtrends", "checkpoints", "ibr")
ANCHOR_IOT    = media_path("data", "06-outcomes", "gtrends", "checkpoints", "anchor_solo_iot.parquet")
OUT_WEEKLY    = media_output_path("data", "06-outcomes", "gtrends", "panel_weekly.parquet")
OUT_REGIONAL  = media_output_path("data", "06-outcomes", "gtrends", "panel_by_region.parquet")

# =========================
# Imports
# =========================

sys.stdout.reconfigure(encoding="utf-8")

import os
import glob
import pandas as pd

# =========================
# Step 1 — Load source data
# =========================

print(f"Reading {IN_EXCEL} ...")
df_news = pd.read_excel(IN_EXCEL)
print(f"  {len(df_news):,} newspapers in source Excel")

print(f"Reading {IN_MAPPING} ...")
df_map = pd.read_excel(IN_MAPPING)
# Non-anchor rows only for joining
df_map_terms = df_map[~df_map["is_anchor"]][["batch_id", "search_term", "name.page"]].drop_duplicates()
print(f"  {len(df_map_terms):,} newspaper–term pairs in mapping")

# =========================
# Step 2 — Assemble IOT panel
# =========================

print(f"\n--- Interest Over Time ---")
iot_files = sorted(glob.glob(os.path.join(CKPT_IOT, "batch_*.parquet")))
print(f"  Found {len(iot_files):,} batch parquet files in {CKPT_IOT}")

if iot_files:
    chunks = []
    for f in iot_files:
        try:
            tmp = pd.read_parquet(f)
            if not tmp.empty:
                chunks.append(tmp)
        except Exception as e:
            print(f"  WARNING: could not read {f}: {e}")

    if chunks:
        df_iot = pd.concat(chunks, ignore_index=True)
        print(f"  Loaded {len(df_iot):,} rows before dedup")

        # Deduplicate (in case of partial overlaps)
        df_iot = df_iot.drop_duplicates(subset=["date", "search_term"]).reset_index(drop=True)
        print(f"  {len(df_iot):,} rows after dedup")

        # Ensure date is datetime
        df_iot["date"] = pd.to_datetime(df_iot["date"])

        # Join name.page via mapping
        df_iot = df_iot.merge(df_map_terms, on=["search_term", "batch_id"], how="left")

        unmatched = df_iot["name.page"].isna().sum()
        if unmatched > 0:
            print(f"  WARNING: {unmatched:,} rows could not be matched to name.page")

        # Merge newspaper metadata
        df_iot = df_iot.merge(df_news, on="name.page", how="left")

        # Sort
        df_iot = df_iot.sort_values(["name.page", "date"]).reset_index(drop=True)

        # Save
        df_iot.to_parquet(OUT_WEEKLY, index=False)
        print(f"\n  Saved: {OUT_WEEKLY}")
        print(f"  Shape: {df_iot.shape}")
        print(f"  Columns: {list(df_iot.columns)}")
        print(f"  Newspapers: {df_iot['name.page'].nunique():,}")
        print(f"  Weeks: {df_iot['date'].nunique():,}  ({df_iot['date'].min().date()} – {df_iot['date'].max().date()})")

        # Sanity check: Reforma's normalized score vs anchor solo
        reforma_rows = df_iot[df_iot["search_term"] == "Reforma"]
        if not reforma_rows.empty and os.path.exists(ANCHOR_IOT):
            df_anchor = pd.read_parquet(ANCHOR_IOT)
            anchor_mean = df_anchor["Reforma"].mean()
            reforma_norm_mean = reforma_rows["interest_normalized"].mean()
            print(f"\n  Sanity check — Reforma:")
            print(f"    anchor_solo mean:       {anchor_mean:.2f}")
            print(f"    normalized score mean:  {reforma_norm_mean:.2f}  (should be ~equal)")

        # Coverage report
        expected_papers = df_map_terms["name.page"].nunique()
        actual_papers   = df_iot["name.page"].nunique()
        missing = set(df_map_terms["name.page"].unique()) - set(df_iot["name.page"].dropna().unique())
        print(f"\n  Coverage: {actual_papers}/{expected_papers} newspapers have data")
        if missing:
            print(f"  Missing newspapers ({len(missing)}):")
            for m in sorted(missing):
                print(f"    - {m}")
    else:
        print("  No non-empty IOT batch files found — skipping IOT panel.")
else:
    print(f"  No IOT batch files found in {CKPT_IOT}")
    print("  Run 01-getGT_interest_over_time.py first.")

# =========================
# Step 3 — Assemble IBR panel
# =========================

print(f"\n--- Interest By Region ---")
ibr_files = sorted(glob.glob(os.path.join(CKPT_IBR, "batch_*.parquet")))
print(f"  Found {len(ibr_files):,} batch parquet files in {CKPT_IBR}")

if ibr_files:
    chunks = []
    for f in ibr_files:
        try:
            tmp = pd.read_parquet(f)
            if not tmp.empty:
                chunks.append(tmp)
        except Exception as e:
            print(f"  WARNING: could not read {f}: {e}")

    if chunks:
        df_ibr = pd.concat(chunks, ignore_index=True)
        print(f"  Loaded {len(df_ibr):,} rows before dedup")

        df_ibr = df_ibr.drop_duplicates(subset=["geoName", "search_term"]).reset_index(drop=True)
        print(f"  {len(df_ibr):,} rows after dedup")

        # Join name.page via mapping
        df_ibr = df_ibr.merge(df_map_terms, on=["search_term", "batch_id"], how="left")

        unmatched = df_ibr["name.page"].isna().sum()
        if unmatched > 0:
            print(f"  WARNING: {unmatched:,} rows could not be matched to name.page")

        # Merge newspaper metadata
        df_ibr = df_ibr.merge(df_news, on="name.page", how="left")

        # Sort
        df_ibr = df_ibr.sort_values(["name.page", "geoName"]).reset_index(drop=True)

        # Save
        df_ibr.to_parquet(OUT_REGIONAL, index=False)
        print(f"\n  Saved: {OUT_REGIONAL}")
        print(f"  Shape: {df_ibr.shape}")
        print(f"  Newspapers: {df_ibr['name.page'].nunique():,}")
        print(f"  States: {df_ibr['geoName'].nunique():,}")
        if "geoCode" in df_ibr.columns:
            print(f"  State codes sample: {list(df_ibr['geoCode'].dropna().unique()[:5])}")
    else:
        print("  No non-empty IBR batch files found — skipping IBR panel.")
else:
    print(f"  No IBR batch files found in {CKPT_IBR}")
    print("  Run 02-getGT_interest_by_region.py first.")

# =========================
# Step 4 — Final summary
# =========================

print(f"\n{'='*50}")
print("Panel build complete.")
if os.path.exists(OUT_WEEKLY):
    size_mb = os.path.getsize(OUT_WEEKLY) / 1e6
    print(f"  panel_weekly.parquet:    {size_mb:.1f} MB  →  {OUT_WEEKLY}")
if os.path.exists(OUT_REGIONAL):
    size_mb = os.path.getsize(OUT_REGIONAL) / 1e6
    print(f"  panel_by_region.parquet: {size_mb:.1f} MB  →  {OUT_REGIONAL}")

# =========================
# CONFIG
# =========================

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))
from project_paths import media_path, media_output_path

IN_MAPPING   = media_path("data", "06-outcomes", "gtrends", "name_gtrends_mapping.xlsx")
OUT_FOLDER   = media_output_path("data", "06-outcomes", "gtrends", ".keep").parent
CKPT_FOLDER  = media_output_path("data", "06-outcomes", "gtrends", "checkpoints", "ibr", ".keep").parent
CKPT_FILE    = media_output_path("data", "06-outcomes", "gtrends", "checkpoints", "progress_ibr.json")
ANCHOR_FILE  = media_output_path("data", "06-outcomes", "gtrends", "checkpoints", "anchor_solo_ibr.parquet")

ANCHOR_TERM  = "Reforma"
DATE_FROM    = "2021-01-01"
DATE_TO      = "2024-12-31"
GEO          = "MX"
SLEEP_SEC    = 65     # seconds between batch requests
MAX_RETRIES  = 5

# =========================
# Imports
# =========================

sys.stdout.reconfigure(encoding="utf-8")

import os
import json
import time
import numpy as np
import pandas as pd
from pytrends.request import TrendReq
from pytrends.exceptions import ResponseError

# =========================
# Helpers
# =========================

def build_session() -> TrendReq:
    return TrendReq(
        hl="es-MX",
        tz=360,
        timeout=(10, 25),
        retries=2,
        backoff_factor=0.5,
        requests_args={
            "headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            }
        },
    )

def fetch_ibr(pytrends: TrendReq, kw_list: list, timeframe: str, geo: str) -> tuple:
    """Fetch interest_by_region with exponential backoff. Returns (DataFrame, pytrends)."""
    for attempt in range(MAX_RETRIES):
        try:
            if attempt > 0:
                pytrends = build_session()
            pytrends.build_payload(
                kw_list=kw_list, cat=0, timeframe=timeframe, geo=geo, gprop=""
            )
            df = pytrends.interest_by_region(
                resolution="REGION",
                inc_low_vol=True,
                inc_geo_code=True,
            )
            # Filter to Mexican states only
            if "geoCode" in df.columns:
                df = df[df["geoCode"].str.startswith("MX-", na=False)].copy()
            return df, pytrends
        except ResponseError as e:
            wait = 300 * (2 ** attempt)
            print(f"    ResponseError (attempt {attempt+1}/{MAX_RETRIES}): {e}")
            print(f"    Sleeping {wait}s ...")
            time.sleep(wait)
        except Exception as e:
            wait = 60 * (2 ** attempt)
            print(f"    Error (attempt {attempt+1}/{MAX_RETRIES}): {e}")
            time.sleep(wait)
    raise RuntimeError(f"Max retries exceeded for kw_list={kw_list}")

def normalize_ibr_batch(df_batch: pd.DataFrame, df_anchor_solo: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize IBR batch scores using anchor term.
    df_batch: index = geoName (state), columns = [ANCHOR_TERM, term1, ...]
    df_anchor_solo: index = geoName (state), column = ANCHOR_TERM
    Returns DataFrame with newspaper columns only, values = normalized scores.
    """
    # Work on keyword columns only (drop geoCode if present)
    df_b = df_batch.drop(columns=["geoCode"], errors="ignore").copy()

    # Align on geoName index
    df_a = df_anchor_solo[ANCHOR_TERM].reindex(df_b.index)
    anchor_in_batch = df_b[ANCHOR_TERM].astype(float)
    newspaper_cols  = [c for c in df_b.columns if c != ANCHOR_TERM]

    result = {}
    for col in newspaper_cols:
        raw     = df_b[col].astype(float)
        anchor_s = df_a.astype(float)
        norm = np.where(anchor_in_batch > 0, (raw / anchor_in_batch) * anchor_s, np.nan)
        result[col] = norm

    return pd.DataFrame(result, index=df_b.index)

def load_checkpoint() -> set:
    if os.path.exists(CKPT_FILE):
        with open(CKPT_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f).get("done_batches", []))
    return set()

def save_checkpoint(done: set) -> None:
    with open(CKPT_FILE, "w", encoding="utf-8") as f:
        json.dump({"done_batches": sorted(done)}, f)

# =========================
# Step 0 — Setup
# =========================

os.makedirs(CKPT_FOLDER, exist_ok=True)
os.makedirs(os.path.dirname(CKPT_FILE), exist_ok=True)

TIMEFRAME = f"{DATE_FROM} {DATE_TO}"

print(f"Loading mapping: {IN_MAPPING}")
df_map = pd.read_excel(IN_MAPPING)
batches_grouped = df_map.groupby("batch_id")
total_batches = df_map["batch_id"].nunique()
print(f"  {total_batches:,} batches, {df_map[~df_map['is_anchor']]['search_term'].nunique():,} newspapers")

pytrends = build_session()

# =========================
# Step 1 — Anchor-only IBR query
# =========================

if os.path.exists(ANCHOR_FILE):
    print(f"\nAnchor solo (IBR) already fetched — loading from cache: {ANCHOR_FILE}")
    df_anchor_solo = pd.read_parquet(ANCHOR_FILE)
else:
    print(f"\nFetching anchor-only IBR query: [{ANCHOR_TERM}] for {TIMEFRAME} geo={GEO} ...")
    pytrends.build_payload(
        kw_list=[ANCHOR_TERM], cat=0, timeframe=TIMEFRAME, geo=GEO, gprop=""
    )
    df_anchor_raw = pytrends.interest_by_region(
        resolution="REGION", inc_low_vol=True, inc_geo_code=True
    )
    if "geoCode" in df_anchor_raw.columns:
        df_anchor_raw = df_anchor_raw[df_anchor_raw["geoCode"].str.startswith("MX-", na=False)].copy()

    if df_anchor_raw.empty:
        raise RuntimeError(f"Anchor-only IBR query returned empty DataFrame for '{ANCHOR_TERM}'")

    df_anchor_solo = df_anchor_raw[[ANCHOR_TERM]].copy()
    df_anchor_solo.to_parquet(ANCHOR_FILE)
    print(f"  Anchor solo (IBR) saved: {ANCHOR_FILE}  ({len(df_anchor_solo):,} states)")
    time.sleep(SLEEP_SEC)

print(f"  States in anchor: {len(df_anchor_solo):,}")
print(f"  Index sample: {list(df_anchor_solo.index[:5])}")

# =========================
# Step 2 — Batch loop
# =========================

done = load_checkpoint()
print(f"\nStarting batch loop. Already done: {len(done)}/{total_batches} batches.")

for batch_id, group in batches_grouped:
    if batch_id in done:
        print(f"  Batch {batch_id:>3}/{total_batches-1}  SKIP (already done)")
        continue

    kw_list = group.sort_values("position")["search_term"].tolist()
    newspaper_terms = [k for k in kw_list if k != ANCHOR_TERM]
    print(f"\n  Batch {batch_id:>3}/{total_batches-1}  keywords: {kw_list}")

    try:
        df_raw, pytrends = fetch_ibr(pytrends, kw_list, TIMEFRAME, GEO)

        if df_raw.empty:
            print(f"    WARNING: empty response — saving empty parquet and marking done")
            df_long = pd.DataFrame(columns=["geoName", "geoCode", "search_term", "interest_normalized", "batch_id"])
            out_path = os.path.join(CKPT_FOLDER, f"batch_{batch_id:03d}.parquet")
            df_long.to_parquet(out_path, index=False)
            done.add(batch_id)
            save_checkpoint(done)
            time.sleep(SLEEP_SEC)
            continue

        # Preserve geoCode before normalization
        geo_code_map = {}
        if "geoCode" in df_raw.columns:
            geo_code_map = df_raw["geoCode"].to_dict()

        # Ensure anchor column is present
        if ANCHOR_TERM not in df_raw.columns:
            raise ValueError(f"Anchor '{ANCHOR_TERM}' missing from response columns: {list(df_raw.columns)}")

        # Normalize
        df_norm = normalize_ibr_batch(df_raw, df_anchor_solo)

        # Reshape to long format
        df_long = (
            df_norm
            .reset_index()
            .rename(columns={"index": "geoName", "geoName": "geoName"})
            .melt(id_vars=["geoName"], var_name="search_term", value_name="interest_normalized")
        )
        df_long["batch_id"] = batch_id

        # Re-attach geoCode
        if geo_code_map:
            df_long["geoCode"] = df_long["geoName"].map(geo_code_map)

        # Save
        out_path = os.path.join(CKPT_FOLDER, f"batch_{batch_id:03d}.parquet")
        df_long.to_parquet(out_path, index=False)

        done.add(batch_id)
        save_checkpoint(done)

        print(f"    Saved {len(df_long):,} rows ({df_long['geoName'].nunique():,} states × {len(newspaper_terms):,} newspapers) → {out_path}")

    except Exception as e:
        print(f"    ERROR: {e}")
        print(f"    Batch {batch_id} NOT marked done — will retry on next run.")
        print(f"    Sleeping 5 min before continuing ...")
        time.sleep(300)
        continue

    time.sleep(SLEEP_SEC)

# =========================
# Step 3 — Summary
# =========================

done_final = load_checkpoint()
remaining  = total_batches - len(done_final)
print(f"\n{'='*50}")
print(f"Done:      {len(done_final):>3}/{total_batches} batches")
print(f"Remaining: {remaining:>3} batches")
if remaining == 0:
    print("All batches complete. Run 03-build_panel.py next.")
else:
    print(f"Re-run this script to fetch remaining {remaining} batches.")

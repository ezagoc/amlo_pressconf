# =========================
# CONFIG
# =========================

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))
from project_paths import media_path, media_output_path

IN_EXCEL    = media_path("data", "00-newspaper_data", "mexican_newspapers.xlsx")
OUT_FOLDER  = media_output_path("data", "06-outcomes", "gtrends", ".keep").parent
ANCHOR_TERM = "Reforma"
BATCH_SIZE  = 4   # newspapers per batch (anchor fills the 5th slot)

# =========================
# Imports
# =========================

sys.stdout.reconfigure(encoding="utf-8")

import os
import pandas as pd

# =========================
# Step 1 — Load newspapers
# =========================

print(f"Reading {IN_EXCEL} ...")
df_news = pd.read_excel(IN_EXCEL)
print(f"  {len(df_news):,} rows loaded")

terms_raw = df_news["name.page"].dropna().unique().tolist()
print(f"  {len(terms_raw):,} unique name.page values")

# =========================
# Step 2 — Clean & validate terms
# =========================

issues = []
terms_clean = []

for t in terms_raw:
    t = str(t).strip()
    if not t:
        continue

    # Check if this is the anchor itself
    if t.lower() == ANCHOR_TERM.lower():
        issues.append({"term": t, "issue": "IS_ANCHOR — excluded from newspaper list"})
        print(f"  INFO: '{t}' matches anchor term — will be excluded (anchor is always included automatically)")
        continue

    # Check length limit (Google Trends rejects > 100 chars)
    if len(t) > 100:
        truncated = t[:100]
        issues.append({"term": t, "issue": f"TRUNCATED to 100 chars → '{truncated}'"})
        print(f"  WARNING: '{t[:40]}...' exceeds 100 chars — truncating")
        t = truncated

    terms_clean.append(t)

# Check for duplicates after cleaning
seen = {}
terms_dedup = []
for t in terms_clean:
    key = t.lower()
    if key in seen:
        issues.append({"term": t, "issue": f"DUPLICATE of '{seen[key]}' — removed"})
        print(f"  WARNING: duplicate term '{t}' — removing")
    else:
        seen[key] = t
        terms_dedup.append(t)

print(f"\nTerms after cleaning: {len(terms_dedup):,}")
if issues:
    df_issues = pd.DataFrame(issues)
    print(f"Issues found ({len(df_issues)}):")
    print(df_issues.to_string(index=False))

# =========================
# Step 3 — Build batches
# =========================

def make_batches(terms: list, anchor: str, batch_size: int = 4) -> list:
    """Split terms into batches of batch_size; anchor prepended to each."""
    batches = []
    for i in range(0, len(terms), batch_size):
        chunk = terms[i:i + batch_size]
        batches.append([anchor] + chunk)
    return batches

batches = make_batches(terms_dedup, ANCHOR_TERM, BATCH_SIZE)
print(f"\nBatches created: {len(batches):,}  (each has {ANCHOR_TERM} + up to {BATCH_SIZE} newspapers)")

# =========================
# Step 4 — Build mapping DataFrame
# =========================

rows = []
for batch_id, batch in enumerate(batches):
    for pos, term in enumerate(batch):
        rows.append({
            "batch_id":        batch_id,
            "position":        pos,
            "is_anchor":       (term == ANCHOR_TERM),
            "search_term":     term,
            "name.page":       term if term != ANCHOR_TERM else ANCHOR_TERM,
        })

df_map = pd.DataFrame(rows)

# Merge original name.page back (search_term == name.page for non-anchor rows after clean/dedup)
# Flag rows that are anchor
print(f"\nMapping rows: {len(df_map):,}  (includes anchor row in each batch)")
print(f"  Non-anchor rows: {(~df_map['is_anchor']).sum():,}")
print(f"  Unique newspapers in mapping: {df_map[~df_map['is_anchor']]['search_term'].nunique():,}")

# =========================
# Step 5 — Save mapping
# =========================

os.makedirs(OUT_FOLDER, exist_ok=True)
out_path = os.path.join(OUT_FOLDER, "name_gtrends_mapping.xlsx")
df_map.to_excel(out_path, index=False)
print(f"\nMapping saved: {out_path}")

# =========================
# Step 6 — Preview
# =========================

print("\n--- Batch 0 preview ---")
print(df_map[df_map["batch_id"] == 0].to_string(index=False))

print(f"\n--- Last batch (batch {len(batches)-1}) preview ---")
print(df_map[df_map["batch_id"] == len(batches) - 1].to_string(index=False))

print(f"\nDone. Run 01-getGT_interest_over_time.py next.")
print(f"Estimated requests for IOT:  1 (anchor-only) + {len(batches)} (batches) = {len(batches)+1}")
print(f"Estimated requests for IBR:  1 (anchor-only) + {len(batches)} (batches) = {len(batches)+1}")
print(f"Minimum wall time at 65s/req: ~{(len(batches)+1)*2*65//60} minutes total across both scripts")

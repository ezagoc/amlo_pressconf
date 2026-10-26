"""Read-only validation of a completed rebuild and its pre-run snapshots."""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from project_paths import media_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--apply-current-role-filter", action="store_true",
                        help="Validate an intentional role restriction against the backed-up rows.")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    assert manifest["complete"] and manifest["inputs_unchanged"]
    backup = Path(manifest["backup_dir"])
    meta_path = "data/00-newspaper_data/processed/newspaper_metadata_geocoded.parquet"
    old = pd.read_parquet(backup / meta_path)
    new = pd.read_parquet(media_path(meta_path))
    assert not new.metadata_id.duplicated().any()
    stable = old[["metadata_id", "name.page"]].merge(new[["metadata_id", "name.page"]],
               on="metadata_id", how="left", suffixes=("_old", "_new"), validate="one_to_one")
    same_name = stable["name.page_old"].eq(stable["name.page_new"])
    both_missing = stable["name.page_old"].isna() & stable["name.page_new"].isna()
    assert (same_name | both_missing).all()
    att_path = "data/02-conferences/raw/attendance/merged/attendance_clean.parquet"
    before = pd.read_parquet(backup / att_path)
    after = pd.read_parquet(media_path(att_path))
    expected = before
    removed_counts = []
    if args.apply_current_role_filter:
        # Reapply the actual R policy to old physical rows, then regenerate only
        # the separately flagged co-affiliation assumptions. Do not reproduce
        # the eligibility policy in Python or assume imputed rows stay constant.
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "expected.parquet"
            subprocess.run(["Rscript", "-e", '''
source("src/attendance_roles.R")
source("src/attendance_coaffiliation.R")
args <- commandArgs(trailingOnly = TRUE)
old <- arrow::read_parquet(args[1])
physical <- old[!old$attendance_assumed, ]
expected <- add_mexico_news_coattendance(physical[keep_attendance_role(physical$cargo), ])
arrow::write_parquet(expected, args[2])
''', str(backup / att_path), str(target)], cwd=ROOT, check=True)
            expected = pd.read_parquet(target)
        removed = before.loc[~before.attendance_assumed &
                             ~before.cargo.isin(expected.cargo.dropna())].copy()
        removed["period"] = pd.to_datetime(removed.fecha, utc=True).ge(pd.Timestamp("2024-10-01", tz="UTC")).map(
            {True: "Sheinbaum", False: "Earlier"})
        removed_counts = removed.groupby(["period", "cargo"]).size().rename("rows").reset_index().to_dict("records")
        removed.to_csv(args.manifest.parent / "excluded_attendance_rows.csv", index=False)
    physical_columns = ["source_file", "cargo", "medios", "fecha", "sede", "attendance_assumed",
                        "outlet_final", "attendance_basis", "attendance_source_outlet"]
    pd.testing.assert_frame_equal(expected[physical_columns].reset_index(drop=True),
                                  after[physical_columns].reset_index(drop=True))
    final_path = media_path("data/06-outcomes/final_panel/final_daily_panel_2012_2025.parquet")
    keys = pd.read_parquet(final_path, columns=["metadata_id", "date"])
    assert not keys.duplicated().any()
    assert len(keys) == len(new) * len(pd.date_range("2012-01-01", "2025-12-31"))
    assert set(keys.metadata_id) == set(new.metadata_id)
    panels = {}
    folder = media_path("data/06-outcomes/deduplicated_source_panels")
    for name in ["attendance", "questions", "contracts", "youtube"]:
        path = folder / f"{name}_entity_daily_panel.parquet"
        schema = pq.ParquetFile(path).schema_arrow
        count = {"attendance": "attendance_n_journalists", "questions": "question_items_n",
                 "contracts": "contracts_n", "youtube": "youtube_n_videos"}[name]
        data = pd.read_parquet(path, columns=["entity_id", "date", "source_date_observed", count])
        assert not data.duplicated(["entity_id", "date"]).any()
        assert data.loc[~data.source_date_observed, count].isna().all()
        assert data.loc[data.source_date_observed, count].notna().all()
        assert data[count].dropna().ge(0).all()
        panels[name] = {"entities": data.entity_id.nunique(), "rows": len(data), "columns": len(schema)}
    audit = {"passed": True, "metadata_rows_before": len(old), "metadata_rows_after": len(new),
             "existing_metadata_ids_preserved": True,
             "attendance_matches_expected_policy": True,
             "role_filter_reapplied": args.apply_current_role_filter,
             "physical_attendance_before": int((~before.attendance_assumed).sum()),
             "physical_attendance_after": int((~after.attendance_assumed).sum()),
             "excluded_role_rows": removed_counts,
             "reviewed_attendance_labels_preserved": True, "final_panel_rows": len(keys),
             "final_panel_columns": len(pq.ParquetFile(final_path).schema_arrow),
             "entity_panels": panels, "missing_source_dates_remain_na_in_entity_panels": True,
             "legacy_final_panel_note": "Metadata-day export retains legacy zero filling; use source coverage flags from entity panels for inference."}
    (args.manifest.parent / "validation.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()

"""Rebuild reviewed metadata and legacy panels, preserving pre-run snapshots.

Run from the repository root. This does not rerun extraction or estimation.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from project_paths import media_path

STEPS = [
    "code/02-cleaning_comsoc/03-base_panel_creation_metadata.R",
    "code/05-press_conferences/00-preprocessing_attendance.R",
    "code/07-final_panel/00-build_final_daily_panel.R",
    "code/07-final_panel/05-build_deduplicated_outcome_panels.R",
]
OUTPUTS = [
    "data/00-newspaper_data/processed/newspaper_metadata_geocoded.parquet",
    "data/00-newspaper_data/processed/newspaper_metadata_panel_daily_2021_2022.parquet",
    "data/00-newspaper_data/processed/newspaper_metadata_panel_weekly_2021_2022.parquet",
    "data/00-newspaper_data/processed/nominatim_office_geocodes_v3.csv",
    "data/02-conferences/raw/attendance/merged/attendance_clean.parquet",
    "data/02-conferences/raw/attendance/merged/bridge_outlets.xlsx",
    "data/02-conferences/raw/attendance/panel_attendance.parquet.gzip",
] + ["data/06-outcomes/final_panel/" + name for name in [
    "final_daily_panel_2012_2025.parquet", "final_panel_match_report.csv",
    "final_panel_match_summary.csv", "contract_bene_final_match_report.csv",
]] + ["data/06-outcomes/deduplicated_source_panels/" + name for name in [
    "contracts_entity_daily_panel.parquet", "attendance_entity_daily_panel.parquet",
    "questions_entity_daily_panel.parquet", "youtube_entity_daily_panel.parquet",
    "metadata_outcome_crosswalk.parquet", "outcome_entity_metadata.parquet",
    "panel_build_summary.csv",
]]
INPUTS = [
    "data/00-newspaper_data/newspaper_metadata.xlsx",
    "data/00-newspaper_data/mexican_newspapers.xlsx",
    "data/02-conferences/raw/attendance/merged/attendance_merged_dedup.xlsx",
    "data/02-conferences/auxiliar/questions_dataset_dedup.parquet",
    "data/06-outcomes/comsoc/contracts_2012_2024_clean.parquet",
    "data/06-outcomes/youtube/panel_daily.parquet",
]


def digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print("Steps:\n" + "\n".join(STEPS))
        print("Pass --execute to back up and rebuild the listed panels.")
        return
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = ROOT / "recovery" / ("panel-rebuild-" + run_id)
    logs = ROOT / "outputs" / ("panel-rebuild-" + run_id)
    backup.mkdir(parents=True)
    logs.mkdir(parents=True)
    manifest = {
        "started_utc": run_id, "backup_dir": str(backup), "complete": False,
        "input_sha256": {p: digest(media_path(p)) for p in INPUTS},
        "code_sha256": {p: digest(ROOT / p) for p in STEPS + ["src/attendance_roles.R", "src/attendance_coaffiliation.R",
                                                  "src/reviewed_outlet_linkage.R"]},
        "before": {}, "steps": [],
    }
    for relative in OUTPUTS:
        source = media_path(relative)
        if source.exists():
            dest = backup / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            manifest["before"][relative] = digest(source)
    path = logs / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Progress and backup manifest: {path}", flush=True)
    for i, script in enumerate(STEPS, 1):
        log = logs / f"{i:02d}-{Path(script).stem}.log"
        print(f"Starting {script}", flush=True)
        with log.open("w") as handle:
            result = subprocess.run(["Rscript", script], cwd=ROOT,
                                    stdout=handle, stderr=subprocess.STDOUT)
        manifest["steps"].append({"script": script, "exit_code": result.returncode,
                                  "log": str(log)})
        path.write_text(json.dumps(manifest, indent=2) + "\n")
        if result.returncode:
            print(log.read_text()[-3500:], flush=True)
            raise SystemExit(f"Build stopped; original outputs remain in {backup}")
        print(f"Completed {script}", flush=True)
    manifest["after"] = {p: digest(media_path(p)) for p in OUTPUTS}
    manifest["inputs_unchanged"] = all(
        digest(media_path(p)) == value for p, value in manifest["input_sha256"].items())
    manifest["complete"] = manifest["inputs_unchanged"]
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    assert manifest["inputs_unchanged"], "Unexpected source-input change"
    print(f"Rebuild complete: {path}", flush=True)


if __name__ == "__main__":
    main()

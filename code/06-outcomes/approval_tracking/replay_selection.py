#!/usr/bin/env python3
"""Optionally replay the audited source-selection stage from frozen OCR inputs."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

from paths import INPUT_ROOT

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "source_workflow"))
import build_approval_series as workflow  # noqa: E402; requires Pillow


def main() -> None:
    expected = json.loads((ROOT / "MANIFEST.json").read_text())["selected_source_sha256"]
    with tempfile.TemporaryDirectory(prefix="amlo_source_selection_") as temporary:
        work = Path(temporary)
        for stored, workflow_name in (
            ("source_manifest.jsonl", "source_manifest.jsonl"),
            ("primary_extractions.jsonl", "extraction_checkpoint.jsonl"),
            ("recovered_observations.jsonl", "supplemental_observations.jsonl"),
        ):
            shutil.copy2(INPUT_ROOT / stored, work / workflow_name)
        sources = workflow.read_source_manifest(work / "source_manifest.jsonl")
        primary = [workflow.SeriesObservation(**json.loads(line)) for line in (work / "extraction_checkpoint.jsonl").read_text().splitlines()]
        workflow.export_series(work, sources, primary, 0)
        actual = hashlib.sha256((work / "approval_series_daily.csv").read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f"Selected source records differ: {actual} != {expected}")
    print(f"Audited selection reproduced exactly: {actual}")


if __name__ == "__main__":
    main()

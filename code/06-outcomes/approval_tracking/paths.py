"""Shared locations for the AMLO approval replication workflow."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from project_paths import media_path  # noqa: E402


DATA_ROOT = media_path("data", "06-outcomes", "approval_tracking")
INPUT_ROOT = DATA_ROOT / "inputs"
EVIDENCE_ROOT = DATA_ROOT / "evidence"
OUTPUT_ROOT = DATA_ROOT / "output"
WORK_ROOT = DATA_ROOT / "source_workflow"

#!/usr/bin/env python3
"""Rebuild the single daily analysis dataset from accepted source readings."""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
from collections import Counter
from datetime import date, timedelta

from paths import DATA_ROOT, INPUT_ROOT, OUTPUT_ROOT

INPUT = INPUT_ROOT / "accepted_observations.csv"
OUTPUT = OUTPUT_ROOT / "amlo_tracking_poll_daily.csv"
FIELDS = [
    "date", "approval_original_pct", "disapproval_original_pct",
    "approval_filled_pct", "disapproval_filled_pct", "original_day_missing",
    "approval_imputed", "disapproval_imputed", "approval_status", "disapproval_status",
    "source_type", "source_url", "source_image_url", "archive_url", "evidence_file",
    "publication_date", "date_assignment", "anchor_before", "anchor_after",
    "gap_length_days",
]


def load_accepted() -> dict[str, dict[str, str]]:
    with INPUT.open(newline="", encoding="utf-8") as handle:
        observations = list(csv.DictReader(handle))
    by_date: dict[str, dict[str, str]] = {}
    for row in observations:
        day = row["date"]
        date.fromisoformat(day)
        if day in by_date:
            raise ValueError(f"Duplicate accepted date: {day}")
        if not row["source_url"] or not row["approval_pct"]:
            raise ValueError(f"Incomplete accepted source: {day}")
        approval = float(row["approval_pct"])
        if not 0 <= approval <= 100:
            raise ValueError(f"Invalid approval percentage: {day}")
        if row["disapproval_pct_observed"] and not 0 <= float(row["disapproval_pct_observed"]) <= 100:
            raise ValueError(f"Invalid disapproval percentage: {day}")
        if row["source_type"] not in {"article_graphic", "recovered_public_source"}:
            raise ValueError(f"Invalid source type: {day}")
        by_date[day] = row
    if not by_date:
        raise ValueError("No accepted readings")
    return by_date


def build() -> list[dict[str, object]]:
    accepted = load_accepted()
    anchors = sorted(accepted)
    current, end = date.fromisoformat(anchors[0]), date.fromisoformat(anchors[-1])
    rows: list[dict[str, object]] = []
    while current <= end:
        day = current.isoformat()
        if day in accepted:
            source = accepted[day]
            approval = float(source["approval_pct"])
            printed_disapproval = source["disapproval_pct_observed"]
            if printed_disapproval:
                disapproval = float(printed_disapproval)
                disapproval_status = "observed"
                disapproval_imputed = 0
            else:
                disapproval = round(100 - approval, 1)
                disapproval_status = "derived_complement"
                disapproval_imputed = 1
            row = {
                "date": day,
                "approval_original_pct": approval,
                "disapproval_original_pct": float(printed_disapproval) if printed_disapproval else "",
                "approval_filled_pct": approval, "disapproval_filled_pct": disapproval,
                "original_day_missing": 0,
                "approval_status": "observed", "disapproval_status": disapproval_status,
                "approval_imputed": 0, "disapproval_imputed": disapproval_imputed,
                "source_type": source["source_type"], "source_url": source["source_url"],
                "source_image_url": source["source_image_url"],
                "archive_url": source["archive_url"],
                "evidence_file": source["evidence_file"],
                "publication_date": source["publication_date"],
                "date_assignment": source["date_assignment"],
                "anchor_before": "", "anchor_after": "", "gap_length_days": 0,
            }
        else:
            index = bisect.bisect_left(anchors, day)
            if not 0 < index < len(anchors):
                raise ValueError(f"Cannot interpolate boundary date {day}")
            left, right = anchors[index - 1], anchors[index]
            span = (date.fromisoformat(right) - date.fromisoformat(left)).days
            weight = (current - date.fromisoformat(left)).days / span
            a_left, a_right = float(accepted[left]["approval_pct"]), float(accepted[right]["approval_pct"])
            d_left = float(accepted[left]["disapproval_pct_observed"]) if accepted[left]["disapproval_pct_observed"] else round(100 - a_left, 1)
            d_right = float(accepted[right]["disapproval_pct_observed"]) if accepted[right]["disapproval_pct_observed"] else round(100 - a_right, 1)
            row = {
                "date": day,
                "approval_original_pct": "", "disapproval_original_pct": "",
                "approval_filled_pct": round(a_left * (1 - weight) + a_right * weight, 3),
                "disapproval_filled_pct": round(d_left * (1 - weight) + d_right * weight, 3),
                "original_day_missing": 1,
                "approval_status": "linear_interpolation",
                "disapproval_status": "linear_interpolation",
                "approval_imputed": 1, "disapproval_imputed": 1,
                "source_type": "interpolated", "source_url": "", "source_image_url": "", "archive_url": "",
                "evidence_file": "", "publication_date": "", "date_assignment": "",
                "anchor_before": left, "anchor_after": right, "gap_length_days": span - 1,
            }
        rows.append(row)
        current += timedelta(days=1)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Compare regenerated bytes to the existing Media output without changing it")
    parser.add_argument("--verify-evidence", action="store_true", help="Check the cached source files against their SHA-256 manifest")
    args = parser.parse_args()
    rows = build()
    from io import StringIO

    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    result = buffer.getvalue().encode("utf-8")
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_bytes() != result:
            raise SystemExit("Rebuild differs from output/amlo_tracking_poll_daily.csv")
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_bytes(result)
    if args.verify_evidence:
        with (INPUT_ROOT / "evidence_manifest.csv").open(newline="", encoding="utf-8") as handle:
            evidence = list(csv.DictReader(handle))
        for item in evidence:
            path = DATA_ROOT / item["evidence_file"]
            if not path.is_file() or path.stat().st_size != int(item["bytes"]):
                raise SystemExit(f"Missing or wrong-sized source image: {path}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != item["sha256"]:
                raise SystemExit(f"Source image hash mismatch: {path}")
        print(f"Verified {len(evidence)} cached source images")
    counts = Counter(row["disapproval_status"] for row in rows)
    print(f"{len(rows)} daily rows; {sum(row['approval_imputed'] == 0 for row in rows)} original approvals; "
          f"{sum(row['approval_imputed'] == 1 for row in rows)} interpolated approvals; "
          f"disapproval: {dict(counts)}")


if __name__ == "__main__":
    main()

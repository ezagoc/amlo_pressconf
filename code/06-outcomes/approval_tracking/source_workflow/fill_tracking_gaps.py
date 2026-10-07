#!/usr/bin/env python3
"""Validate recovered originals, merge them, and optionally export marked estimates."""
from __future__ import annotations

import argparse
import bisect
import csv
from collections import defaultdict
from dataclasses import asdict
from datetime import date, timedelta
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import WORK_ROOT  # noqa: E402

import build_approval_series as b

ROOT = WORK_ROOT
BASELINE = ROOT / "before_gap_recovery_20260928"
RECOVERY = ROOT / "recovery"


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.is_file() else []


def reviewed_cover_candidates():
    path = RECOVERY / "verified_cover_values.csv"
    if not path.is_file():
        return []
    index = {r["date"]: r for r in read_jsonl(RECOVERY / "economista_cover_index.jsonl") if r["cover_found"]}
    candidates = []
    for values in csv.DictReader(path.open()):
        source = index[values["source_date"]]
        for day_key, approval_key, disapproval_key in (("historical_date", "historical_approval", "historical_disapproval"),
                                                       ("current_date", "approval", "disapproval")):
            if not values[day_key]:
                continue
            candidates.append({"measurement_date": values[day_key], "approval": float(values[approval_key]),
                "disapproval": float(values[disapproval_key]) if values[disapproval_key] else None,
                "confidence": None, "article_url": source["url"]+"#page="+str(source["page"]),
                "image_url": source["url"]+"#page="+str(source["page"]), "image_path": source["image_path"],
                "publication_date": source["date"], "archive_url": source["url"],
                "source_measurement_date": source["date"], "kind": "newspaper_cover_explicit_date", "manual_verified": True,
                "evidence": {"verification_note": "Visually verified printed date and gold approval/red disapproval endpoint.",
                             "reviewed_values_file": "recovery/verified_cover_values.csv", "notes": values["notes"]}})
    return candidates


def calibrate_periods(candidates, baseline):
    comparisons = defaultdict(lambda: [0, 0])
    for candidate in candidates:
        old = baseline.get(candidate["measurement_date"])
        if candidate.get("confidence", 0) < 75 or not old or old["review_status"] == "needs_review" or not old["approval"]:
            continue
        comparison = comparisons[candidate["kind"]]
        comparison[0] += 1
        comparison[1] += abs(float(old["approval"]) - candidate["approval"]) < .11
    accepted = set()
    for kind, (count, agreements) in comparisons.items():
        if kind.startswith(("month_label_", "fortnight_label_")) and count >= 50 and agreements / count >= .95:
            accepted.add(kind)
    report = {kind: {"comparisons": count, "agreements": agreements,
                     "agreement_rate": agreements / count, "accepted_period_interpretation": kind in accepted}
              for kind, (count, agreements) in comparisons.items()}
    return accepted, report


def select_recoveries(candidates, baseline, calibrated):
    grouped, audit = defaultdict(list), []
    # A visually verified dated endpoint can extend the historical archive.
    # Other earlier OCR candidates still need the normal corroboration checks.
    verified_dates = [r["measurement_date"] for r in candidates if r.get("manual_verified")]
    first, last = min([min(baseline), *verified_dates]), max(baseline)
    for candidate in candidates:
        day, kind = candidate["measurement_date"], candidate["kind"]
        if not first <= day <= last or candidate.get("approval") is None:
            continue
        if kind.startswith(("month_label_", "fortnight_label_")) and kind not in calibrated:
            continue
        grouped[day].append(candidate)
    chosen = []
    for day, records in sorted(grouped.items()):
        verified = [r for r in records if r.get("manual_verified")]
        if verified:
            verified.sort(key=lambda r: (r["measurement_date"] == r["source_measurement_date"],
                                         r["disapproval"] is not None, "newspaper" in r["kind"]), reverse=True)
            best = verified[0]
            old = baseline.get(day)
            if old and old["review_status"] != "needs_review" and day != best["source_measurement_date"]:
                conflicts = abs(float(old["approval"]) - best["approval"]) > .11
                if old["disapproval"] and best["disapproval"] is not None:
                    conflicts |= abs(float(old["disapproval"]) - best["disapproval"]) > .11
                if conflicts:
                    audit.append({"date": day, "status": "historical_print_conflicts_with_existing_source", "candidate": best,
                                  "existing_approval": old["approval"], "existing_disapproval": old["disapproval"]})
                    continue
            chosen.append(best)
            continue
        clusters = defaultdict(list)
        for record in records:
            clusters[(record["approval"], record["disapproval"])].append(record)
        eligible = []
        for values, supporting in clusters.items():
            a, d = values
            best = max(supporting, key=lambda r: r.get("confidence") or 0)
            references = {r["image_path"] or r["article_url"] for r in supporting if (r.get("confidence") or 0) >= 60}
            strong = (best.get("confidence") or 0) >= 80
            corroborated = len(references) >= 2 and (best.get("confidence") or 0) >= 65
            # Crowded axis dates can attach to the preceding percentage even
            # with high OCR confidence, including the source's current date.
            # Require another chart or a visual review for every axis reading.
            if best["kind"] == "printed_chart_axis_date":
                strong = False
            if (strong or corroborated) and (d is None or 97 <= a + d <= 101):
                eligible.append({**best, "supporting_sources": sorted(references), "corroborated": corroborated})
        if not eligible:
            continue
        eligible.sort(key=lambda r: (len(r["supporting_sources"]), r["disapproval"] is not None, r["confidence"]), reverse=True)
        best = eligible[0]
        conflicts = [r for r in eligible[1:] if abs(r["approval"] - best["approval"]) > .11
                     or (r["disapproval"] is not None and best["disapproval"] is not None
                         and abs(r["disapproval"] - best["disapproval"]) > .11)]
        if conflicts:
            audit.append({"date": day, "status": "conflicting_recovered_sources", "candidates": eligible})
            continue
        old = baseline.get(day)
        if old and old["review_status"] != "needs_review":
            if abs(float(old["approval"]) - best["approval"]) > .11:
                audit.append({"date": day, "status": "conflict_with_existing_accepted_value", "candidate": best,
                              "existing_approval": old["approval"]})
                continue
            # Retain accepted originals; a recovered printed second percentage
            # can upgrade an approval-only record without inventing a complement.
            if old["review_status"] == "validated_pair" or best["disapproval"] is None:
                continue
        chosen.append(best)
    return chosen, audit


def as_observation(candidate):
    a, d = candidate["approval"], candidate["disapproval"]
    complement = round(100 - a, 1)
    kind = candidate["kind"]
    date_source = "graphic_historical_date"
    if "comparison" in kind or "label_" in kind:
        date_source = "graphic_relative_day"
    if "pdf" in kind or "newspaper" in kind:
        date_source = "pdf_printed_date"
    elif "transcript" in kind:
        date_source = "transcript_explicit_date"
    elif "social_post" in kind:
        date_source = "social_post_context_date"
    elif "video_printed" in kind:
        date_source = "video_printed_date"
    elif "news_reported" in kind:
        date_source = "news_reported_date"
    elif kind == "printed_current_chart":
        date_source = "image_ocr"
    flags = ["recovered_original"]
    if candidate.get("manual_verified"):
        flags.append("manual_verified")
    if candidate.get("corroborated"):
        flags.append("independent_chart_agreement")
    if kind.startswith(("month_label_", "fortnight_label_")):
        flags.append("period_label_calibrated")
    evidence = {"kind": kind, "source_measurement_date": candidate["source_measurement_date"],
                "supporting_sources": candidate.get("supporting_sources", []), "evidence": candidate["evidence"]}
    return b.SeriesObservation(
        measurement_date=candidate["measurement_date"], approval=a, disapproval=d,
        disapproval_complement=complement, disapproval_effective=d if d is not None else complement,
        disapproval_source="observed" if d is not None else "complement_derived",
        publication_date=candidate["publication_date"], date_source=date_source,
        article_url=candidate["article_url"], image_url=candidate["image_url"],
        archive_url=candidate.get("archive_url", ""), image_path=candidate.get("image_path", ""),
        discovery_sources="historical_chart_recovery" if "graphic" in date_source else "supplemental_public_source",
        extraction_method="recovered_original_v1", ocr_text=json.dumps(evidence, ensure_ascii=False),
        approval_confidence=candidate.get("confidence"), disapproval_confidence=candidate.get("confidence") if d is not None else None,
        sum_percent=round(a + d, 1) if d is not None else None,
        review_status="validated_pair" if d is not None else "validated_approval_only",
        review_flags=";".join(flags))


def complete_calendar(daily):
    """Interpolate accepted values only; keep each estimate and its anchors explicit."""
    accepted = {r["measurement_date"]: r for r in daily if r["review_status"] != "needs_review" and r["approval"]}
    anchors = sorted(accepted)
    rows = []
    current, end = date.fromisoformat(daily[0]["measurement_date"]), date.fromisoformat(daily[-1]["measurement_date"])
    by_date = {r["measurement_date"]: r for r in daily}
    while current <= end:
        day = current.isoformat()
        if day in accepted:
            original = accepted[day]
            row = {"date": day, "approval": float(original["approval"]),
                   "disapproval_effective": float(original["disapproval_effective"]),
                   "approval_origin": "observed_recovered" if original["extraction_method"] == "recovered_original_v1" else "observed_article",
                   "disapproval_origin": "observed" if original["disapproval"] else "complement_derived",
                   "estimation_method": "", "anchor_before": "", "anchor_after": "", "gap_length_days": 0,
                   "article_url": original["article_url"]}
        else:
            index = bisect.bisect_left(anchors, day)
            left, right = anchors[max(0, index - 1)], anchors[min(len(anchors) - 1, index)]
            span = (date.fromisoformat(right) - date.fromisoformat(left)).days
            weight = (current - date.fromisoformat(left)).days / span if span else 0
            left_row, right_row = accepted[left], accepted[right]
            a = float(left_row["approval"]) * (1 - weight) + float(right_row["approval"]) * weight
            d = float(left_row["disapproval_effective"]) * (1 - weight) + float(right_row["disapproval_effective"]) * weight
            row = {"date": day, "approval": round(a, 3), "disapproval_effective": round(d, 3),
                   "approval_origin": "estimated", "disapproval_origin": "estimated_effective",
                   "estimation_method": "linear_interpolation" if span else "nearest_boundary_value",
                   "anchor_before": left, "anchor_after": right, "gap_length_days": max(0, span - 1),
                   "article_url": ""}
        original = by_date.get(day, {})
        row.update({"original_review_status": original.get("review_status", "no_observation_found"),
                    "original_approval": original.get("approval", ""), "original_disapproval": original.get("disapproval", "")})
        rows.append(row)
        current += timedelta(days=1)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--complete", action="store_true", help="Write a separate complete calendar with explicitly marked estimates.")
    args = parser.parse_args()
    baseline = {r["measurement_date"]: r for r in csv.DictReader((BASELINE / "approval_series_daily.csv").open())}
    candidates = read_jsonl(RECOVERY / "chart_candidates.jsonl") + read_jsonl(RECOVERY / "pdf_candidates.jsonl")
    calibrated, calibration = calibrate_periods(candidates, baseline)
    (RECOVERY / "period_calibration.json").write_text(json.dumps(calibration, indent=2) + "\n")
    selected, audit = select_recoveries(candidates + read_jsonl(RECOVERY / "manual_observations.jsonl")
                                       + read_jsonl(RECOVERY / "social" / "verified_observations.jsonl")
                                       + reviewed_cover_candidates(), baseline, calibrated)
    b.write_jsonl(RECOVERY / "accepted_recovery_evidence.jsonl", selected)
    b.write_jsonl(RECOVERY / "recovery_conflicts.jsonl", audit)
    supplements = [as_observation(r) for r in selected]
    b.write_jsonl(ROOT / "supplemental_observations.jsonl", (asdict(r) for r in supplements))
    primary = [b.SeriesObservation(**r) for r in read_jsonl(ROOT / "extraction_checkpoint.jsonl")]
    b.export_series(ROOT, b.read_source_manifest(ROOT / "source_manifest.jsonl"), primary,
                    sum(bool(r.image_path) and (ROOT / r.image_path).is_file() for r in primary))
    after = list(csv.DictReader((ROOT / "approval_series_daily.csv").open()))
    changes = []
    for row in after:
        old = baseline.get(row["measurement_date"])
        if not old or any(old[k] != row[k] for k in ("approval", "disapproval", "review_status")):
            changes.append({"date": row["measurement_date"], "change": "filled_missing_date" if not old else "updated_existing_date",
                            "previous_approval": old["approval"] if old else "", "approval": row["approval"],
                            "previous_disapproval": old["disapproval"] if old else "", "disapproval": row["disapproval"],
                            "previous_status": old["review_status"] if old else "no_observation_found",
                            "status": row["review_status"], "article_url": row["article_url"], "image_path": row["image_path"]})
    b.write_csv(ROOT / "gap_recovery_changes.csv", changes, list(changes[0]) if changes else ["date", "change"])
    summary = json.loads((ROOT / "series_summary.json").read_text())
    report = {"before": json.loads((BASELINE / "series_summary.json").read_text()), "after": summary,
              "new_original_dates": sum(r["change"] == "filled_missing_date" for r in changes),
              "updated_existing_dates": sum(r["change"] == "updated_existing_date" for r in changes),
              "unresolved_source_conflicts": len(audit), "accepted_period_interpretations": sorted(calibrated)}
    if args.complete:
        complete = complete_calendar(after)
        b.write_csv(ROOT / "approval_series_daily_complete.csv", complete, list(complete[0]))
        unresolved = [r for r in complete if r["approval_origin"] == "estimated"]
        b.write_csv(ROOT / "remaining_original_gaps.csv", unresolved, list(complete[0]))
        report["complete_calendar"] = {"days": len(complete), "observed": sum(r["approval_origin"] != "estimated" for r in complete),
                                       "estimated": sum(r["approval_origin"] == "estimated" for r in complete),
                                       "estimate_max_gap_days": max(r["gap_length_days"] for r in complete)}
    (ROOT / "gap_recovery_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

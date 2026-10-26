"""Build an auditable Sheinbaum outlet/conference-date participation panel.

Identification days are not individual question counts. Dated affiliation links
never add physical attendance records. Missing source dates remain unavailable.
"""
import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from project_paths import media_path


def key(value):
    if pd.isna(value):
        return None
    value = unicodedata.normalize("NFKD", str(value).lower()).encode("ascii", "ignore").decode()
    value = re.sub(r"[^a-z0-9]+", " ", value).strip()
    return {"sdpnoticias": "sdp noticias", "unomasuno": "uno mas uno",
            "tiempo la noticial digital": "tiempo la noticia digital"}.get(value, value) or None


def dates(values):
    return pd.to_datetime(values, utc=True).dt.tz_localize(None).dt.normalize()


def category(values):
    values = sorted({str(v).strip().lower() for v in values.dropna()
                     if str(v).strip().lower() not in {"", "unclear"}})
    return values[0] if len(values) == 1 else ("conflict" if values else "unclear")


def metadata_links(metadata):
    m = metadata.copy()
    m["q_key"] = m["names.transcripts"].map(key)
    m["a_key"] = m["names.conference"].map(key)
    pairs = m[["q_key", "a_key"]].dropna().drop_duplicates()
    if (pairs.groupby("q_key").a_key.nunique() > 1).any():
        raise ValueError("A transcript key maps to several attendance IDs; review before joining")
    return m, dict(zip(pairs.q_key, pairs.a_key))


def verified_dated_links(links, physical, q_to_a):
    """Require a real eligible roster label/date; produce flags, never counts."""
    links = links.copy()
    links["date"] = dates(links.date)
    roster = physical[["date", "medios", "outlet_id"]].drop_duplicates()
    checked = links.merge(roster, left_on=["date", "attendance_label"],
                          right_on=["date", "medios"], how="left", validate="many_to_one")
    expected = checked.attendance_canonical.map(key)
    # Some approved joint labels deliberately have no global canonical outlet.
    # Their physical row still verifies the dated affiliation, not a global merge.
    canonical_required = expected.ne("dated link only")
    if checked.medios.isna().any() or not checked.loc[canonical_required, "outlet_id"].eq(expected[canonical_required]).all():
        raise ValueError("Dated link lacks the approved physical roster label/date")
    checked["linked_attendance_outlet_id"] = checked.outlet_id
    checked["outlet_id"] = checked.outlet.map(key).map(lambda x: q_to_a.get(x, x))
    return checked.drop(columns="medios")


def assemble_panel(identities, physical, assumed, transcript_dates, dated_links):
    ids = sorted(set(identities.outlet_id.dropna()) | set(physical.outlet_id.dropna()))
    calendar = pd.DatetimeIndex(sorted(set(transcript_dates) | set(physical.date)))
    p = pd.MultiIndex.from_product([ids, calendar], names=["outlet_id", "date"]).to_frame(index=False)
    # Names can identify a reporter, but missing-name records cannot identify people.
    q = identities.dropna(subset=["outlet_id"]).drop_duplicates(["outlet_id", "date", "reporter_aux"])
    qdaily = q.groupby(["outlet_id", "date"]).agg(
        identification_records=("outlet_id", "size"),
        named_reporters=("reporter_aux", "nunique")).reset_index()
    adaily = physical.groupby(["outlet_id", "date"]).size().rename("recorded_attendance_n").reset_index()
    assumed_daily = assumed.groupby(["outlet_id", "date"]).size().rename("assumed_attendance_n").reset_index()
    roster = physical.groupby("date").size().rename("roster_records").reset_index()
    p = p.merge(qdaily, how="left", validate="one_to_one").merge(adaily, how="left", validate="one_to_one")
    p = p.merge(assumed_daily, how="left", validate="one_to_one").merge(roster, how="left", validate="many_to_one")
    p["transcript_observed"] = p.date.isin(transcript_dates)
    p["attendance_roster_observed"] = p.roster_records.notna()
    p["sparse_roster"] = p.roster_records.lt(5) & p.attendance_roster_observed
    for column in ["identification_records", "named_reporters"]:
        p[column] = p[column].fillna(0).where(p.transcript_observed)
    for column in ["recorded_attendance_n", "assumed_attendance_n"]:
        p[column] = p[column].fillna(0).where(p.attendance_roster_observed)
    flags = dated_links[["outlet_id", "date"]].drop_duplicates().assign(verified_dated_affiliation=True)
    p = p.merge(flags, how="left", validate="one_to_one")
    p["verified_dated_affiliation"] = p.verified_dated_affiliation.eq(True)
    p["identified"] = p.identification_records.gt(0).astype("Int64").where(p.transcript_observed)
    p["recorded_present"] = p.recorded_attendance_n.gt(0).astype("Int64").where(p.attendance_roster_observed)
    p["attendance_supported"] = (p.recorded_attendance_n.gt(0) | p.verified_dated_affiliation).astype("Int64").where(p.attendance_roster_observed)
    p["common_coverage"] = p.transcript_observed & p.attendance_roster_observed & ~p.sparse_roster
    assert not p.duplicated(["outlet_id", "date"]).any()
    assert p.recorded_attendance_n.sum() == len(physical.dropna(subset=["outlet_id"]))
    return p


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--through", default="2026-10-15")
    args = parser.parse_args()
    base = media_path("data/02-conferences-sheinbaum")
    paths = {
        "identities": base / f"api_extraction/official-through-{args.through}/auxiliar/periodistas_v2_all_years_dedup.parquet",
        "progress": base / f"api_extraction/official-through-{args.through}/run_progress.json",
        "transcripts": base / f"official_source/through-{args.through}/auxiliar/transcript_rows.parquet",
        "attendance": media_path("data/02-conferences/raw/attendance/merged/attendance_clean.parquet"),
        "metadata": media_path("data/00-newspaper_data/processed/newspaper_metadata_geocoded.parquet"),
        "dated_links": ROOT / "info_newspapers_gpt/outlet_review_20261026/dated_question_attendance_links.csv",
    }
    progress = json.loads(paths["progress"].read_text())
    assert progress["complete"], "Only complete identity runs may define source coverage"
    transcript_dates = pd.DatetimeIndex(dates(pd.read_parquet(paths["transcripts"], columns=["date"]).date).unique()).sort_values()
    assert len(transcript_dates) == progress["n_completed"]
    q = pd.read_parquet(paths["identities"])
    q["date"] = dates(q.date)
    assert q.date.isin(transcript_dates).all()
    assert not q.duplicated(["date", "reporter_aux", "outlet_aux"]).any()
    a = pd.read_parquet(paths["attendance"])
    a["date"] = dates(a.fecha)
    a = a[a.date.between(transcript_dates.min(), transcript_dates.max())].copy()
    a["outlet_id"] = a.outlet_final.map(key)
    physical, assumed = a[~a.attendance_assumed].copy(), a[a.attendance_assumed].copy()
    m, mapping = metadata_links(pd.read_parquet(paths["metadata"]))
    q["q_key"] = q.outlet_aux.map(key)
    q["outlet_id"] = q.q_key.map(lambda x: mapping.get(x, x))
    q["link_method"] = np.where(q.q_key.isin(mapping), "metadata crosswalk", "normalized source key")
    links = verified_dated_links(pd.read_csv(paths["dated_links"]), physical, mapping)
    p = assemble_panel(q, physical, assumed, transcript_dates, links)
    m["outlet_id"] = m.a_key.combine_first(m.q_key)
    registry = m.dropna(subset=["outlet_id"]).groupby("outlet_id").agg(
        metadata_brands=("name.page", lambda v: " | ".join(sorted(set(v.dropna())))),
        n_metadata_brands=("metadata_id", "nunique"),
        ideology_4t=("ideology.4t", category)).reset_index()
    p = p.merge(registry, how="left", validate="many_to_one")
    p["ideology_4t"] = p.ideology_4t.fillna("unmatched")
    out = base / f"participation_panel/through-{args.through}"
    out.mkdir(parents=True, exist_ok=True)
    p.to_parquet(out / "outlet_conference_daily.parquet", index=False)
    q.to_parquet(out / "identification_crosswalk.parquet", index=False)
    links.to_csv(out / "validated_dated_links.csv", index=False)
    registry.to_csv(out / "outlet_metadata.csv", index=False)
    coverage = p[["date", "transcript_observed", "attendance_roster_observed", "roster_records", "sparse_roster", "common_coverage"]].drop_duplicates()
    coverage.to_csv(out / "conference_coverage.csv", index=False)
    unresolved = p[p.identified.eq(1) & p.attendance_roster_observed & p.attendance_supported.eq(0)]
    unresolved.to_csv(out / "identified_without_attendance_match.csv", index=False)
    audit = {
        "date_from": str(transcript_dates.min().date()), "date_to": str(transcript_dates.max().date()),
        "panel_rows": len(p), "outlets": p.outlet_id.nunique(), "conference_dates_union": len(coverage),
        "transcript_dates": len(transcript_dates), "attendance_dates": physical.date.nunique(),
        "common_coverage_dates_excluding_sparse": int(coverage.common_coverage.sum()),
        "sparse_roster_dates": coverage.loc[coverage.sparse_roster, "date"].dt.strftime("%Y-%m-%d").tolist(),
        "physical_attendance_records": len(physical), "unassigned_physical_records": int(physical.outlet_id.isna().sum()),
        "identification_records_input": len(q), "identification_records_without_outlet": int(q.outlet_id.isna().sum()),
        "identified_outlet_days": int(p.identified.sum()), "validated_dated_links": len(links),
        "unit": "canonical outlet by observed conference date; identification presence, not question count",
        "missingness": "Unavailable source dates are NA; zero means no record in that observed source",
        "dated_link_policy": "Presence support only; no physical attendance or global affiliation imputation",
        "input_sha256": {k: hashlib.sha256(v.read_bytes()).hexdigest() for k, v in paths.items()},
    }
    (out / "build_audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps({k: v for k, v in audit.items() if k != "input_sha256"}, indent=2))
    print(out)


if __name__ == "__main__":
    main()

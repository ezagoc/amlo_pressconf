"""Audit same-date attendance cargos of transcript-identified Sheinbaum outlets.

Matches are outlet/date associations, never a person-level cargo assignment.
This audit does not modify attendance eligibility or the participation panel.
"""
import hashlib
import html
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from project_paths import media_path

spec = importlib.util.spec_from_file_location("participation", ROOT / "code/07-final_panel/sheinbaum_participation.py")
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


def classify(roles):
    roles = set(roles)
    reporter = bool(roles & {"REPORTERO", "REPORTETO", "REPORTERA"})
    support = bool(roles & {"FOTOGRAFO", "FOTOGRAFA", "CAMAROGRAFO", "CAMAROGRAFA"})
    if reporter:
        return "REPORTERO + support roles" if support else "REPORTERO only"
    if "YOUTUBER" in roles:
        return "YOUTUBER; no REPORTERO"
    if roles and roles <= {"FOTOGRAFO", "FOTOGRAFA", "CAMAROGRAFO", "CAMAROGRAFA"}:
        return "Only excluded support roles"
    return "Other cargo; inspect" if roles else "No matched roster entry"


def unique_text(values):
    return " | ".join(sorted(set(values.dropna().astype(str))))


def main():
    out = ROOT / "outputs/sheinbaum-cargo-audit-20261026"
    source = media_path("data/02-conferences-sheinbaum/participation_panel/through-2026-10-15")
    paths = {"raw_roles": out / "raw_attendance_all_roles.parquet",
             "panel": source / "outlet_conference_daily.parquet",
             "identities": source / "identification_crosswalk.parquet",
             "dated_links": source / "validated_dated_links.csv",
             "clean_attendance": media_path("data/02-conferences/raw/attendance/merged/attendance_clean.parquet")}
    before_hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    a = pd.read_parquet(paths["raw_roles"])
    a["date"] = helpers.dates(a.date).astype("datetime64[ns]")
    a["outlet_id"] = a.outlet_final.map(helpers.key)
    clean = pd.read_parquet(paths["clean_attendance"])
    clean["date"] = helpers.dates(clean.fecha).astype("datetime64[ns]")
    clean = clean[~clean.attendance_assumed & clean.date.between(a.date.min(), a.date.max())]
    physical_key = ["source_file", "cargo", "medios", "date"]
    pd.testing.assert_series_equal(a.loc[a.role_kept, physical_key].value_counts().sort_index(),
                                   clean[physical_key].value_counts().sort_index())
    p = pd.read_parquet(paths["panel"])
    q = pd.read_parquet(paths["identities"])
    events = p[p.identified.eq(1)].copy()
    event_keys = events[["outlet_id", "date"]]
    direct = event_keys.merge(a.dropna(subset=["outlet_id"]), on=["outlet_id", "date"], validate="one_to_many")
    direct["match_method"] = "canonical outlet/date"
    links = pd.read_csv(paths["dated_links"], parse_dates=["date"])
    linked = event_keys.merge(links[["outlet_id", "date", "attendance_label"]].drop_duplicates(),
                             on=["outlet_id", "date"], validate="one_to_many")
    linked = linked.merge(a.drop(columns="outlet_id"), left_on=["date", "attendance_label"],
                          right_on=["date", "medios"], validate="many_to_many")
    linked["match_method"] = "approved dated affiliation"
    matches = pd.concat([direct, linked], ignore_index=True).drop_duplicates(["outlet_id", "date", "raw_row_id"])
    grouped = matches.groupby(["outlet_id", "date"])
    cargo = grouped.agg(cargos=("role_normalized", unique_text), raw_labels=("medios", unique_text),
                        matched_role_rows=("raw_row_id", "nunique"), eligible_role_rows=("role_kept", "sum"),
                        match_methods=("match_method", unique_text)).reset_index()
    cargo["classification"] = cargo.cargos.map(lambda x: classify(x.split(" | ")))
    events = events.merge(cargo, how="left", on=["outlet_id", "date"], validate="one_to_one")
    events["classification"] = events.classification.fillna("No matched roster entry")
    events.loc[~events.attendance_roster_observed, "classification"] = "No roster for this date"
    intros = q.groupby(["outlet_id", "date"]).agg(reporters=("reporter_aux", unique_text),
        introduction_evidence=("evidence_text", unique_text), source_urls=("source_url", unique_text)).reset_index()
    events = events.merge(intros, how="left", on=["outlet_id", "date"], validate="one_to_one")
    common = events[events.common_coverage].copy()
    counts = common.groupby("classification").agg(outlet_days=("outlet_id", "size"),
                                                   outlets=("outlet_id", "nunique")).reset_index()
    counts["percent_of_identified_outlet_days"] = 100 * counts.outlet_days / len(common)
    counts = counts.sort_values("outlet_days", ascending=False)
    # Each original roster row is counted once in the physical-role distribution.
    common_keys = common[["outlet_id", "date"]]
    match_common = matches.merge(common_keys, validate="many_to_one")
    physical_matches = match_common.drop_duplicates("raw_row_id")
    role_rows = physical_matches.groupby(["role_normalized", "role_kept"]).size().rename("matched_original_rows").reset_index()
    raw_counts = a.groupby(["role_normalized", "role_kept"]).size().rename("all_original_rows").reset_index()
    risk = common[common.classification.isin(["YOUTUBER; no REPORTERO", "Only excluded support roles", "Other cargo; inspect"])].copy()
    # A role excluded by the production filter must not enter recorded attendance.
    support_only = common[common.classification.eq("Only excluded support roles")]
    assert support_only.recorded_attendance_n.eq(0).all()
    assert support_only.attendance_supported.eq(0).all()
    assert not events.duplicated(["outlet_id", "date"]).any()
    assert len(common) == 1608  # pinned 503-date snapshot and current 239-date comparison
    reporter_cases = common.classification.str.startswith("REPORTERO").sum()
    youtuber_cases = common.classification.eq("YOUTUBER; no REPORTERO").sum()
    profiles = common.groupby("outlet_id").agg(identified_days=("date", "size"),
        classifications=("classification", unique_text), cargos=("cargos", unique_text),
        reporters=("reporters", unique_text)).reset_index()
    exported = {"outlet_date_cargos": events, "same_date_role_matches": matches,
                "common_sample_classification": counts, "raw_role_distribution": raw_counts,
                "matched_physical_role_distribution": role_rows, "non_reportero_cases": risk,
                "outlet_cargo_profiles": profiles}
    for name, frame in exported.items(): frame.to_csv(out / f"{name}.csv", index=False)
    after_hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    assert before_hashes == after_hashes
    audit = {"common_dates": int(p.loc[p.common_coverage, "date"].nunique()),
        "identified_outlet_days_common": len(common), "reportero_supported_outlet_days": int(reporter_cases),
        "youtuber_without_reportero_outlet_days": int(youtuber_cases),
        "only_excluded_support_outlet_days": len(support_only),
        "no_matched_cargo_outlet_days": int(common.classification.eq("No matched roster entry").sum()),
        "production_inputs_unchanged": True, "person_level_role_assignment": False,
        "input_sha256": before_hashes}
    (out / "audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    def table(df):
        return df.to_html(index=False, border=0, escape=True, na_rep="—", float_format=lambda x: f"{x:,.1f}")
    shown = risk[["outlet_id", "date", "reporters", "cargos", "classification", "raw_labels"]].copy()
    shown["date"] = shown.date.dt.strftime("%Y-%m-%d")
    report = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Sheinbaum cargo audit</title>
<style>body{{font:16px/1.5 system-ui;max-width:1150px;margin:35px auto;padding:0 22px;color:#223340}}h2{{margin-top:32px}}table{{border-collapse:collapse;font-size:13px;width:100%;margin:18px 0}}td,th{{padding:8px;border-bottom:1px solid #ddd;text-align:left}}th{{background:#eaf1f5}}.scroll{{overflow:auto}}.note{{background:#eaf1f5;padding:18px}}</style>
<h1>Which cargos are recorded for outlets identified in Sheinbaum transcripts?</h1>
<p>Same-date comparison on the {audit['common_dates']} common usable conference dates. Outcome: an outlet explicitly identified in the transcript, not the count of individual questions.</p>
<div class="note">The attendance source contains outlet names and cargos, but no journalist names. This audit establishes the roles registered for that outlet on that date. It cannot establish an individual speaker's cargo where several employees or roles share an outlet.</div>
<h2>Original roster roles in the Sheinbaum period</h2>{table(raw_counts)}
<p>The current filter retains REPORTERO and YOUTUBER in this period. All 42 YOUTUBER rows refer to Lord Molécula Oficial in October–December 2024. FOTÓGRAFO and CAMARÓGRAFO rows are excluded from physical attendance in the analysis. The shared filter now allows only REPORTERO and YOUTUBER (plus clear spelling/gender/plural variants). COLUMNISTA, CORRESPONSAL, AUDIO and all other cargos are excluded in every period. This stricter rule leaves Sheinbaum counts unchanged.</p>
<h2>Roles on identified outlet-days</h2>{table(counts)}
<p>Categories are mutually exclusive by outlet/date. A reporter plus a photographer at the same outlet does not classify the questioner as a photographer. Approved date-specific affiliations are included, with matching original labels preserved in the detailed CSV.</p>
<p>The approved REPORTERO/YOUTUBER pool supports {reporter_cases+youtuber_cases:,} identified outlet-days: {reporter_cases:,} have REPORTERO and {youtuber_cases} have YOUTUBER but no REPORTERO. Both categories remain eligible. There are {len(support_only)} identified outlet-days with only excluded support roles in the matched roster.</p>
<h2>Non-REPORTERO cases to inspect</h2><div class="scroll">{table(shown)}</div>
<p><b>El Financiero, June 3, 2025:</b> the archived official transcript explicitly records Angélica Guerrero introducing herself with El Financiero Bloomberg Televisión, then asking about the decline in remittances (source rows 374–375). This is a genuine question. The original roster has an El Financiero photographer entry but no matched reporter entry. It does not establish that the photographer was Angélica Guerrero. Keep the transcript participation and the roster-role discrepancy separate.</p>
<p>Excluded-role-only matches remain outside recorded attendance in the current panel. Their transcript identifications are not removed: a cargo mismatch at outlet level does not invalidate a recorded speaking turn. The {audit['no_matched_cargo_outlet_days']} remaining unmatched outlet-days have no established cargo link.</p>
<h2>Physical roster rows associated with these appearances</h2>{table(role_rows)}
<p>This table counts each original merged-roster row once, even if it supports several affiliations. It is not a count of speakers or questions. The source merge may already collapse identical roster rows; this audit preserves that established input.</p>
<h2>Files</h2><p>Detailed evidence, same-date roles, per-outlet profiles, and category counts are saved alongside this report in <code>{html.escape(str(out))}</code>. This audit reads the current production eligibility rule and datasets without modifying them. Historical regressions have not been refit.</p></html>'''
    (out / "index.html").write_text(report)
    print(counts.to_string(index=False))
    print("NON-REPORTERO CASES\n" + shown.to_string(index=False))
    print(json.dumps({k: v for k, v in audit.items() if k != "input_sha256"}, indent=2))
    print(out / "index.html")


if __name__ == "__main__":
    main()

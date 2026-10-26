"""Descriptive outlet participation and attendance analysis; no causal models."""
import argparse
import hashlib
import html
import io
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from project_paths import media_path


def ratio(n, d):
    return n.div(d.where(d.gt(0)))


def outlet_summary(p):
    p = p.copy()
    p["identified_recorded"] = p.identified.eq(1) & p.recorded_present.eq(1)
    p["identified_supported"] = p.identified.eq(1) & p.attendance_supported.eq(1)
    z = p.groupby("outlet_id").agg(
        identified_days=("identified", "sum"), recorded_attendance_days=("recorded_present", "sum"),
        supported_attendance_days=("attendance_supported", "sum"),
        identified_on_recorded_days=("identified_recorded", "sum"),
        identified_on_supported_days=("identified_supported", "sum"),
        ideology_4t=("ideology_4t", "first"), metadata_brands=("metadata_brands", "first"))
    z["identification_rate_on_recorded_days"] = ratio(z.identified_on_recorded_days, z.recorded_attendance_days)
    z["identification_rate_on_supported_days"] = ratio(z.identified_on_supported_days, z.supported_attendance_days)
    return z.reset_index().sort_values(["identified_days", "outlet_id"], ascending=[False, True])


def table(frame):
    return frame.to_html(index=False, border=0, classes="data", float_format=lambda v: f"{v:,.3f}", na_rep="—", escape=True)


def plot_svg(fig):
    stream = io.StringIO()
    fig.savefig(stream, format="svg", bbox_inches="tight")
    plt.close(fig)
    return "<svg" + stream.getvalue().split("<svg", 1)[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--through", default="2026-10-15")
    args = parser.parse_args()
    source = media_path(f"data/02-conferences-sheinbaum/participation_panel/through-{args.through}")
    out = media_path(f"results/sheinbaum/participation/through-{args.through}")
    out.mkdir(parents=True, exist_ok=True)
    p = pd.read_parquet(source / "outlet_conference_daily.parquet")
    coverage = pd.read_csv(source / "conference_coverage.csv", parse_dates=["date"])
    audit = json.loads((source / "build_audit.json").read_text())
    full = outlet_summary(p)
    common = outlet_summary(p[p.common_coverage])
    full.to_csv(out / "outlet_summary_all_dates.csv", index=False)
    common.to_csv(out / "outlet_summary_common_dates.csv", index=False)
    periods = []
    for name, mask in [("First year in office", p.date.lt("2025-10-01")),
                       ("After first year", p.date.ge("2025-10-01"))]:
        z = p[mask]
        periods.append({"period": name, "transcript_dates": z.loc[z.transcript_observed, "date"].nunique(),
                        "attendance_dates": z.loc[z.attendance_roster_observed, "date"].nunique(),
                        "identified_outlet_days": int(z.identified.sum()),
                        "outlets_identified": z.loc[z.identified.eq(1), "outlet_id"].nunique()})
    periods = pd.DataFrame(periods)
    periods.to_csv(out / "period_summary.csv", index=False)
    daily = p[p.transcript_observed].groupby("date").agg(
        identified_outlets=("identified", "sum"), identity_records=("identification_records", "sum")).reset_index()
    daily["month"] = daily.date.dt.to_period("M").astype(str)
    monthly = daily.groupby("month").agg(transcript_dates=("date", "size"),
                mean_identified_outlets=("identified_outlets", "mean"),
                identified_outlet_days=("identified_outlets", "sum")).reset_index()
    cv = coverage.copy()
    cv["month"] = cv.date.dt.to_period("M").astype(str)
    am = cv[cv.attendance_roster_observed].groupby("month").agg(
        roster_dates=("date", "size"), mean_physical_roster_records=("roster_records", "mean"))
    monthly = monthly.merge(am, on="month", how="outer").sort_values("month")
    monthly.to_csv(out / "monthly_summary.csv", index=False)
    groups = common.groupby("ideology_4t").agg(
        outlets=("outlet_id", "size"), outlets_with_recorded_attendance=("recorded_attendance_days", lambda x: x.gt(0).sum()),
        recorded_outlet_days=("recorded_attendance_days", "sum"),
        identified_on_recorded_days=("identified_on_recorded_days", "sum"))
    groups["identification_rate_on_recorded_days"] = ratio(groups.identified_on_recorded_days, groups.recorded_outlet_days)
    groups.reset_index().to_csv(out / "alignment_descriptives.csv", index=False)
    identified_common = int(p.loc[p.common_coverage, "identified"].sum())
    matched_common = int(common.identified_on_supported_days.sum())
    distinct_identified = int(full.identified_days.gt(0).sum())
    concentration = float(full.identified_days.head(10).sum() / full.identified_days.sum())
    summary = {"identified_outlets": distinct_identified,
               "identified_outlet_days": int(full.identified_days.sum()),
               "top10_share_of_identified_outlet_days": concentration,
               "common_date_identified_outlet_days": identified_common,
               "common_date_attendance_supported_identified_days": matched_common,
               "common_date_identified_days_without_verified_attendance": identified_common - matched_common,
               "panel_sha256": hashlib.sha256((source / "outlet_conference_daily.parquet").read_bytes()).hexdigest(),
               "analysis_unit": "outlet-date identification, not number of questions",
               "models_estimated": False}
    (out / "analysis_audit.json").write_text(json.dumps(summary, indent=2) + "\n")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, ax = plt.subplots(figsize=(10, 5))
    top = full.head(10).iloc[::-1]
    ax.barh(top.outlet_id, top.identified_days, color="#2d617a")
    for i, v in enumerate(top.identified_days): ax.text(v + .5, i, str(int(v)), va="center")
    ax.set(xlabel="Conference dates with an explicit identification", title="Top 10 outlets · all 503 transcript dates")
    ax.set_xlim(0, max(top.identified_days) * 1.12)
    fig.savefig(out / "top10_identification_days.png", dpi=150, bbox_inches="tight")
    top_plot = plot_svg(fig)
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    x = pd.to_datetime(monthly.month)
    axes[0].plot(x, monthly.mean_identified_outlets, color="#2d617a", marker="o", ms=3)
    axes[0].set(ylabel="Mean identified outlets", title="Monthly participation and source coverage")
    axes[1].plot(x, monthly.transcript_dates, label="Transcript dates", color="#2d617a")
    axes[1].plot(x, monthly.roster_dates.fillna(0), label="Attendance roster dates", color="#ac6545")
    axes[1].set(ylabel="Dates observed")
    axes[1].legend(frameon=False)
    fig.autofmt_xdate()
    fig.savefig(out / "monthly_participation_coverage.png", dpi=150, bbox_inches="tight")
    monthly_plot = plot_svg(fig)
    display = common[common.recorded_attendance_days.ge(10)].sort_values(
        ["identification_rate_on_recorded_days", "recorded_attendance_days"], ascending=False).head(10)
    report = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<title>Sheinbaum participation · initial analysis</title>
<style>body{{font:16px/1.55 system-ui,sans-serif;max-width:1120px;margin:38px auto;padding:0 24px;color:#21313c;background:#fafbfc}}h1,h2{{line-height:1.2}}h2{{margin-top:38px}}.note{{background:#eaf1f5;padding:16px;border-left:4px solid #2d617a}}table{{border-collapse:collapse;width:100%;font-size:13px;margin:18px 0}}th,td{{padding:8px;text-align:left;border-bottom:1px solid #d4dee4}}th{{background:#eaf1f5}}svg{{width:100%;height:auto}}.scroll{{overflow:auto}}</style>
<h1>Sheinbaum participation: initial analysis</h1>
<p>Official transcripts: <b>{audit['date_from']}–{audit['date_to']}</b>. The rebuilt panel contains
{audit['outlets']:,} source outlet IDs across {audit['conference_dates_union']:,} observed conference dates.</p>
<div class="note">The outcome is an outlet being explicitly identified in the transcript. It is not the number of questions asked. An absent identification can mean an unstated affiliation. Attendance comes from recorded rosters; verified date-specific affiliations are separate evidence and never create another physical attendee.</div>
<p><b>{distinct_identified}</b> outlets appear in <b>{summary['identified_outlet_days']:,}</b> identified outlet-days.
The top ten account for <b>{concentration:.1%}</b> of those outlet-days. Raw outlet IDs can still contain unresolved variants.</p>
<h2>Coverage and periods</h2>{table(periods)}
<p>There are {audit['attendance_dates']} roster dates and {audit['common_coverage_dates_excluding_sparse']} dates with both sources after excluding rosters with fewer than five records. The only flagged sparse date is March 4, 2025 (one record). There are {audit['physical_attendance_records']:,} physical attendance records in the Sheinbaum window; {audit['unassigned_physical_records']} have no canonical outlet and remain in roster totals. Seven identity records lack an outlet and are retained in the source audit.</p>
{monthly_plot}
<p>Monthly means use observed transcript dates. October 2026 is partial. Missing roster dates are unavailable, not zero attendance. One roster date has no transcript in the archived corpus.</p>
<h2>Most frequently identified outlets</h2>{top_plot}
{table(full.head(10)[['outlet_id','identified_days']])}
<h2>Participation conditional on recorded attendance</h2>
<p>On the {audit['common_coverage_dates_excluding_sparse']} comparable dates, {matched_common:,} of {identified_common:,} identified outlet-days have either a matching recorded outlet or a verified dated affiliation. The remaining {identified_common-matched_common:,} are unmatched, not established absences.</p>
<p>The table ranks outlets with at least ten recorded attendance days. The numerator counts dates when both an identification and direct recorded attendance exist; the denominator is recorded attendance dates on the common-source sample. Date-only affiliation links are available as a separate sensitivity column in the downloadable summary.</p>
<div class="scroll">{table(display[['outlet_id','recorded_attendance_days','identified_on_recorded_days','identification_rate_on_recorded_days']])}</div>
<h2>Descriptive comparison by existing outlet alignment</h2>
<p>These are the existing metadata categories, not question-tone classifications. The rate pools outlet-days within each category on the same common-source dates. This is descriptive and does not adjust for composition or selection into attendance; unknown, conflicting, and unmatched categories remain visible.</p>
<div class="scroll">{table(groups.reset_index())}</div>
<h2>Data and next analysis</h2>
<p>CSV exports alongside this report contain all outlet summaries, monthly coverage, period summaries, and alignment comparisons. The panel and audit files are under <code>{html.escape(str(source))}</code>.</p>
<p>Next: review the unmatched attendance dates and metadata gaps, then choose the participation model. Counts of individual questions, presidential response behavior, and preparation/coordination require completion and review of the separate question–answer extraction.</p>
</html>'''
    (out / "index.html").write_text(report)
    print(json.dumps(summary, indent=2))
    print(full.head(10)[["outlet_id", "identified_days"]].to_string(index=False))
    print(out / "index.html")


if __name__ == "__main__":
    main()

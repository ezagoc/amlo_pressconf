"""Export the completed first-pass estimates to a PDF and compact LaTeX tables.

Usage: bundled-python 03-export-report.py [--data-dir PATH]
Tables have no captions or notes; the report explains the design separately.
"""
import argparse
import csv
import os
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

ROOT = Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser()
parser.add_argument("--data-dir", type=Path)
args = parser.parse_args()
if args.data_dir:
    DATA = args.data_dir
else:
    env = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("'\"")
    DATA = Path(os.getenv("MEDIA_ROOT", env["MEDIA_ROOT"])) / "results/effect_of_asking"

def read(name):
    with (DATA / name).open(newline="") as f:
        return list(csv.DictReader(f))

def num(row, key):
    return float(row[key])

def f3(v):
    return f"{float(v):.3f}"

def pv(v):
    return "<0.001" if float(v) < 0.001 else f"{float(v):.3f}"

def one(rows, **keys):
    matches = [r for r in rows if all(r[k] == v for k, v in keys.items())]
    assert len(matches) == 1, keys
    return matches[0]

reg = read("regression_results.csv")
fect = read("fect_1000/results.csv")
legacy = read("legacy_fect_reference.csv")
assert len(fect) == 12 and all(int(float(r["valid_bootstraps"])) == 1000
                              for r in fect if r["estimator"] == "FEct")
outcomes = ["likes", "comments", "views"]
models = ["Baseline", "History adjusted"]
pdf_path = ROOT / "output/pdf/effect_of_asking_youtube_first_results.pdf"
pdf_path.parent.mkdir(parents=True, exist_ok=True)
table_dir = ROOT / "overleaf/tables/effect_of_asking"
table_dir.mkdir(parents=True, exist_ok=True)

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="BodyCompact", fontName="Helvetica", fontSize=9,
                          leading=13, spaceAfter=8, textColor=colors.HexColor("#253445")))
styles.add(ParagraphStyle(name="CellCompact", fontName="Helvetica", fontSize=8,
                          leading=11, alignment=TA_LEFT))
styles["Title"].fontName = "Helvetica-Bold"
styles["Title"].fontSize = 19
styles["Title"].leading = 23
styles["Title"].alignment = TA_LEFT
styles["Title"].textColor = colors.HexColor("#18354A")
styles["Heading2"].textColor = colors.HexColor("#18354A")

def p(text, style="BodyCompact"):
    return Paragraph(text, styles[style])

def table(headers, rows, widths):
    content = [[p(escape(str(v)), "CellCompact") for v in headers]]
    content += [[p(str(v), "CellCompact") for v in row] for row in rows]
    t = Table(content, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEABOVE", (0, 0), (-1, 0), .8, colors.HexColor("#18354A")),
        ("LINEBELOW", (0, 0), (-1, 0), .5, colors.HexColor("#18354A")),
        ("LINEBELOW", (0, -1), (-1, -1), .8, colors.HexColor("#18354A")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFF3F6")),
    ]))
    return t

def cell(r):
    p_text = "p &lt; 0.001" if float(r["p_value"]) < .001 else f'p = {pv(r["p_value"])}'
    return f'<b>{f3(r["estimate"])}</b><br/>[{f3(r["ci_low"])}, {f3(r["ci_high"])}]<br/>{p_text}'

def latex(rows, path, selectors):
    lines = [r"\begingroup", r"\centering\scriptsize", r"\setlength{\tabcolsep}{5pt}",
             r"\renewcommand{\arraystretch}{1.15}", r"\begin{tabular}{@{}lccc@{}}",
             r"\toprule", r" & Likes & Comments & Views \\", r"\midrule"]
    for label, keys in selectors:
        rr = [one(rows, outcome=o, **keys) for o in outcomes]
        lines.append(label + " & " + " & ".join(
            r"\shortstack{$" + f3(r["estimate"]) + r"$\\$[" + f3(r["ci_low"]) + r",\,"
            + f3(r["ci_high"]) + r"]$\\$p" + ("<0.001" if float(r["p_value"]) < .001
            else "=" + pv(r["p_value"])) + "$}" for r in rr) + r" \\[5pt]")
    sample = one(rows, outcome="likes", **selectors[0][1])
    lines += [r"\midrule",
              "Outlet-days & " + " & ".join([f'{int(sample["n"]):,}'] * 3) + r" \\",
              "Outlets & " + " & ".join([str(sample["units"])] * 3) + r" \\",
              "Conference dates & " + " & ".join([str(sample["dates"])] * 3) + r" \\",
              r"Outlet and conference-date FE & Yes & Yes & Yes \\",
              r"\bottomrule", r"\end{tabular}\par", r"\endgroup"]
    path.write_text("\n".join(lines) + "\n")

latex(reg, table_dir / "main_results.tex",
      [(m, {"model": m, "inference": "Outlet clustered"}) for m in models])
latex(fect, table_dir / "fect_robustness.tex",
      [(e + ": " + m.lower(), {"model": m, "estimator": e})
       for e in ["Paired-sample TWFE", "FEct"] for m in models])

base = one(reg, outcome="likes", model="Baseline", inference="Outlet clustered")
adj = one(reg, outcome="views", model="History adjusted", inference="Outlet clustered")
story = [
    p("Asking a question and YouTube engagement", "Title"),
    p("FIRST-PASS RESULTS  |  Recorded attendees  |  12 October 2026"),
    p("1. Main specification", "Heading2"),
    p("Outcomes are log(1 + total likes), log(1 + total comments), and log(1 + total views) "
      "for videos published on the conference date. Engagement is measured at the saved "
      "YouTube snapshot, not as engagement accumulated on that date. No winsorization "
      "is applied to the main models."),
    p("Both models include outlet and conference-date fixed effects. The adjusted model "
      "adds the prior-year questions / recorded-journalist-attendance ratio interacted "
      "with calendar quarter, plus missing-history-by-quarter indicators. The reference "
      "quarter is 2022 Q2. Standard errors cluster by outlet."),
    table(["Model", "Likes", "Comments", "Views"],
          [[m] + [cell(one(reg, outcome=o, model=m, inference="Outlet clustered")) for o in outcomes]
           for m in models], [138, 112, 112, 112]),
    Spacer(1, 10),
    p(f'N = {int(base["n"]):,} outlet-days; {base["units"]} outlets; {base["dates"]} conference dates; '
      f'{int(float(base["asking"]))} asking outlet-days. April 19, 2022 - September 27, 2024. '
      "All displayed intervals are 95% confidence intervals; p-values are unadjusted."),
    p("Reading the estimates", "Heading2"),
    p("The adjusted point estimates are positive, but none rejects zero at the 5% level "
      f'(views: p = {pv(adj["p_value"])}). These are log1p-scale coefficients, not automatically '
      "percentage changes in raw engagement. The design estimates a conditional asking "
      "contrast, not the lottery-assignment ITT."),
    p("2. How the sample was formed", "Heading2"),
    table(["Stage", "Outlet units", "Outlet-days"],
          [[r["stage"], r["units"], f'{int(r["n"]):,}'] for r in read("sample_flow.csv")] +
          [["Outlet-FE singleton removal", base["units"], f'{int(base["n"]):,}']],
          [340, 67, 67]),
    Spacer(1, 6),
    p("Before this funnel, 111 recorded attendance units become 99 with unambiguous question "
      "links, then 82 with jointly observed sources, and 81 on informative dates. "
      "Outlet units are deduplicated attendance/question IDs. Distinct linked YouTube entities "
      "are summed once per unit-date; metadata subsidiaries are never expanded into duplicate "
      "outcomes. Missing source coverage is not coded as zero."),
    PageBreak(),
    p("FEct robustness and sensitivity checks", "Title"),
    p("3. Comparable-sample FEct", "Heading2"),
    p("FEct estimates untreated counterfactuals from nonasking, recorded-attendee observations. "
      "It uses the same raw log1p outcomes, outlet/date fixed effects, and optional history "
      "controls. Each fit uses 1,000 outlet bootstrap replications. Nonattendance is missing "
      "from this estimation sample, not an untreated observation."),
    table(["Estimator / model", "Likes", "Comments", "Views"],
          [[e + "<br/>" + m] + [cell(one(fect, outcome=o, model=m, estimator=e)) for o in outcomes]
           for e in ["Paired-sample TWFE", "FEct"] for m in models],
          [138, 112, 112, 112]),
    Spacer(1, 8),
    p("FEct uses 5,256 outlet-days, 50 outlets, 256 dates, and 311 treated cells. It requires "
      "at least five untreated attendance observations per retained outlet and untreated "
      "support for each missing-history-by-quarter cell. "
      "The paired TWFE estimates above use the same supported rows and control basis. "
      "The FEct point estimates were independently verified using untreated-only fixed-effects "
      "regression and average prediction errors on treated observations."),
    p("4. Additional regression sensitivities", "Heading2"),
    table(["Specification", "Likes", "Comments", "Views"],
          [[label] + [cell(one(reg, outcome=o, model=m, inference=inf)) for o in outcomes]
           for label, m, inf in [
               ("Two-way clustered SEs", "History adjusted", "Outlet + date clustered"),
               ("Winsorized, then log1p", "Winsorized history adjusted", "Outlet clustered"),
               ("Observed histories only", "Observed-history adjusted", "Outlet clustered"),
               ("Date FE only", "Date FE only", "Outlet clustered")]],
          [138, 112, 112, 112]),
    Spacer(1, 8),
    p("Winsorization uses the 1st and 99th percentiles of each raw outcome in the common input "
      "sample, before log1p. The observed-history sensitivity changes the sample. Two-way "
      "clustered covariance matrices required fixest's non-positive-definite repair in "
      "some models; see the saved inference warnings. They are supplementary, not primary."),
    PageBreak(),
    p("Scope, comparability, and next steps", "Title"),
    p("5. Earlier FEct estimates: reference only", "Heading2"),
    table(["Legacy pooled FEct", "Likes", "Comments", "Views"],
          [["Raw log1p"] + [cell(one(legacy, outcome=o)) for o in outcomes]],
          [138, 112, 112, 112]),
    Spacer(1, 10),
    p("These saved estimates use a broader full-calendar, channel-level panel and an attendance "
      "dummy. They do not share the new attendee-only sample, unit aggregation, or historical "
      "adjustment and must not be interpreted as a like-for-like estimator comparison."),
    p("6. Important limitations", "Heading2"),
    p("<b>Selection:</b> asking, rather than the actual randomized seating assignment, is observed. "
      "Balance tests found persistent participation differences. Outlet FE and history-by-quarter "
      "controls address specific observable patterns, not all time-varying selection."),
    p("<b>Repeated treatment:</b> the new FEct estimates are static, same-day ATTs. They do not "
      "exclude recent question days from the untreated counterfactual fit. Carryover, anticipatory "
      "behavior, and feedback into future attendance remain limitations to test; no new event "
      "study or lottery permutation test is reported."),
    p("<b>Publication timing:</b> a same-day video may precede the press conference. Views, likes, "
      "and comments are snapshot totals on videos published that day, not daily increments. "
      "Use future publication windows or upload timestamps for stronger temporal ordering."),
    p("<b>Coverage:</b> complete coverage of all linked channels is required. Grupo Canton and "
      "Sonora Power have usable channels but also an unmatched linked entity; this rule excludes "
      "both units. IMER, El Pais, Sin Embargo, The Mexico News, and Rompeviento have no matched "
      "YouTube entities in the current mapping. Test an explicitly labeled observed-channel "
      "sample separately, rather than silently zero-filling unmatched channels."),
    p("<b>History:</b> the ratio uses April 18, 2021 - April 17, 2022, on dates jointly covered "
      "by attendance and questions, excluding November 2021. It is total questions divided "
      "by recorded journalist attendance records, not question days / attendance days."),
    p("<b>Inference:</b> three outcomes and several sensitivities are exploratory; p-values are "
      "not adjusted for multiple testing. FEct's automatic long event-time F diagnostic can "
      "be singular on this sparse sample and is not a usable pretrend test here."),
    p("Next session", "Heading2"),
    p("Start from code/08-results/01-effect-of-asking/HANDOFF.md. Prioritize the channel-coverage "
      "sensitivity, next-day / next-seven-day publication windows, and explicit treatment-history "
      "or carryover diagnostics before extending to ideology subgroups."),
]

def footer(canvas, doc):
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#627383"))
    canvas.drawString(0.95 * inch, 0.45 * inch, "Effect of asking | first-pass analysis")
    canvas.drawRightString(7.55 * inch, 0.45 * inch, str(doc.page))

SimpleDocTemplate(str(pdf_path), pagesize=(612, 792), rightMargin=.95*inch,
                  leftMargin=.95*inch, topMargin=.7*inch, bottomMargin=.7*inch).build(
                      story, onFirstPage=footer, onLaterPages=footer)
print(pdf_path)

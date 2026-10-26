"""Separate subgroup report and caption-free LaTeX; never overwrite pooled results."""
import argparse
import csv
import os
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

ROOT = Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser()
parser.add_argument("--data-dir", type=Path)
args = parser.parse_args()
env = {}
for line in (ROOT / ".env").read_text().splitlines():
    if line.strip() and not line.lstrip().startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("'\"")
DATA = args.data_dir or Path(os.getenv("MEDIA_ROOT", env["MEDIA_ROOT"])) / "results/effect_of_asking/heterogeneity"
GROUPS = ["Opposition", "Aligned", "Independent"]
OUTCOMES = ["likes", "comments", "views"]
MODELS = ["Baseline", "History adjusted"]

def read(name):
    with (DATA / name).open(newline="") as f:
        return list(csv.DictReader(f))

def one(rows, **keys):
    found = [r for r in rows if all(r[k] == v for k, v in keys.items())]
    assert len(found) == 1, keys
    return found[0]

def f3(v):
    return f"{float(v):.3f}"

def pv(v):
    return "<0.001" if float(v) < .001 else f3(v)

reg = read("regression_results.csv")
contrasts = read("effect_difference_tests.csv")
fect = []
for g in GROUPS:
    rr = read(f"{g.lower()}/fect_1000/results.csv")
    assert len(rr) == 12
    for r in rr:
        r["group"] = g
        if r["estimator"] == "FEct":
            assert int(r["bootstrap_replications"]) == int(r["valid_bootstraps"]) == 1000
    fect.extend(rr)
assert len(reg) == 18 and len(contrasts) == 24

PDF = ROOT / "output/pdf/effect_of_asking_youtube_heterogeneity.pdf"
TEX = ROOT / "overleaf/tables/effect_of_asking"
TEX.mkdir(parents=True, exist_ok=True)
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="BodySmall", fontName="Helvetica", fontSize=9, leading=12, spaceAfter=7))
styles.add(ParagraphStyle(name="CellSmall", fontName="Helvetica", fontSize=8, leading=10))
styles["Title"].fontName = "Helvetica-Bold"
styles["Title"].fontSize = 19
styles["Title"].leading = 23
styles["Title"].alignment = 0
styles["Title"].textColor = colors.HexColor("#18354A")
styles["Heading2"].textColor = colors.HexColor("#18354A")

def p(s, style="BodySmall"):
    return Paragraph(s, styles[style])

def table(headers, rows, widths=(138, 112, 112, 112)):
    content = [[p(escape(str(h)), "CellSmall") for h in headers]]
    content += [[p(str(c), "CellSmall") for c in row] for row in rows]
    t = Table(content, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LINEABOVE", (0,0), (-1,0), .8, colors.HexColor("#18354A")),
        ("LINEBELOW", (0,0), (-1,0), .5, colors.HexColor("#18354A")),
        ("LINEBELOW", (0,-1), (-1,-1), .8, colors.HexColor("#18354A")),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING", (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#EFF3F6")),
    ]))
    return t

def cell(r):
    pp = "p &lt; 0.001" if float(r["p_value"]) < .001 else f'p = {pv(r["p_value"])}'
    return f'<b>{f3(r["estimate"])}</b><br/>[{f3(r["ci_low"])}, {f3(r["ci_high"])}]<br/>{pp}'

def results_table(rows, **keys):
    return table(["Group / model", "Likes", "Comments", "Views"],
        [[g + "<br/>" + m] + [cell(one(rows, group=g, model=m, outcome=o, **keys)) for o in OUTCOMES]
         for g in GROUPS for m in MODELS])

def sample_table(rows, **keys):
    return table(["Group", "Outlet-days", "Outlets / dates", "Asking outlet-days"],
        [[g, f'{int(one(rows, group=g, model="History adjusted", outcome="likes", **keys)["n"]):,}',
          one(rows, group=g, model="History adjusted", outcome="likes", **keys)["units"] + " / " +
          one(rows, group=g, model="History adjusted", outcome="likes", **keys)["dates"],
          one(rows, group=g, model="History adjusted", outcome="likes", **keys)["asking"]] for g in GROUPS])

def latex(rows, filename, **keys):
    lines = [r"\begingroup", r"\centering\scriptsize", r"\setlength{\tabcolsep}{5pt}",
             r"\renewcommand{\arraystretch}{1.12}", r"\begin{tabular}{@{}lccc@{}}", r"\toprule",
             r" & Likes & Comments & Views \\", r"\midrule"]
    for g in GROUPS:
        lines.append(r"\multicolumn{4}{@{}l}{\textit{" + g + r"}} \\")
        for m in MODELS:
            rr = [one(rows, group=g, outcome=o, model=m, **keys) for o in OUTCOMES]
            lines.append(m + " & " + " & ".join(r"\shortstack{$" + f3(r["estimate"]) +
                r"$\\$[" + f3(r["ci_low"]) + r",\," + f3(r["ci_high"]) + r"]$\\$p" +
                ("<0.001" if float(r["p_value"]) < .001 else "=" + pv(r["p_value"])) + "$}" for r in rr) + r" \\[4pt]")
        r = rr[0]
        lines.append(r"\multicolumn{4}{@{}l}{" + f'{int(r["n"]):,} outlet-days; {r["units"]} outlets; {r["dates"]} dates' + r"} \\")
        lines.append(r"\midrule" if g != GROUPS[-1] else r"\bottomrule")
    lines += [r"\end{tabular}\par", r"\endgroup"]
    (TEX / filename).write_text("\n".join(lines) + "\n")

latex(reg, "heterogeneity_main.tex")
latex(fect, "heterogeneity_fect.tex", estimator="FEct")
latex(fect, "heterogeneity_paired_twfe.tex", estimator="Paired-sample TWFE")
ll = [r"\begingroup\centering\scriptsize", r"\setlength{\tabcolsep}{5pt}",
      r"\begin{tabular}{@{}lccc@{}}\toprule", r" & Likes & Comments & Views \\", r"\midrule"]
for test in ["Opposition - Aligned", "Opposition - Independent", "Aligned - Independent", "All three effects equal"]:
    ll.append(test + " & " + " & ".join("$" + pv(one(contrasts, outcome=o, model="History adjusted", test=test)["p_value"]) + "$" for o in OUTCOMES) + r" \\")
ll += [r"\bottomrule\end{tabular}\par\endgroup"]
(TEX / "heterogeneity_difference_pvalues.tex").write_text("\n".join(ll) + "\n")

story = [p("Effect of asking: ideology heterogeneity", "Title"),
    p("RECORDED ATTENDEES  |  YouTube metrics  |  12 October 2026"),
    p("Separate opposition, aligned and independent estimates. Outcomes are raw log(1 + y) "
      "likes, comments and views on videos published on each conference date. Both models "
      "include outlet and date fixed effects; adjusted models add prior participation history "
      "by calendar quarter. No winsorization. Intervals are 95%; SEs cluster by outlet."),
    results_table(reg), Spacer(1, 8), sample_table(reg),
    p("Equality of effects across the three groups", "Heading2"),
    table(["Joint-test p-value", "Likes", "Comments", "Views"],
          [[m] + [pv(one(contrasts, outcome=o, model=m, test="All three effects equal")["p_value"]) for o in OUTCOMES] for m in MODELS]),
    Spacer(1, 6),
    p("No adjusted within-group coefficient rejects zero at 5%, and neither specification "
      "rejects equality across groups. These are imprecise estimates, not evidence that effects "
      "are zero or identical. Opposition inference rests on only 8 outlet clusters (6 ever asking)."),
    PageBreak(),
    p("FEct robustness", "Title"),
    p("Untreated-counterfactual imputation with outlet/date fixed effects; baseline and "
      "history-adjusted specifications. Each fit uses 1,000 outlet bootstrap replications. "
      "These are recorded-attendee observations, not the legacy full-calendar/channel panel."),
    results_table(fect, estimator="FEct"), Spacer(1, 8), sample_table(fect, estimator="FEct"),
    p("Support and interpretation", "Heading2"),
    p("Both FEct specifications use a common supported sample within each group: at least "
      "five untreated attendance dates per outlet, asking/nonasking variation on each retained "
      "date, and estimable adjusted counterfactuals from the untreated design. Unsupported "
      "history cells and disconnected fixed-effect predictions are excluded, not extrapolated."),
    p("All 18 point estimates are checked against independent untreated-only FE regressions, "
      "and all fits have 1,000 finite bootstrap draws. Small cluster counts, especially opposition, "
      "make bootstrap inference fragile; some resamples drop collinear controls. See the next "
      "page for TWFE on these exact supported samples."),
    PageBreak(),
    p("Paired-sample regressions and design", "Title"),
    p("TWFE on the corresponding FEct sample, with the same control basis. Differences from "
      "page 1 reflect support restrictions; comparisons with page 2 isolate the estimator."),
    results_table(fect, estimator="Paired-sample TWFE"),
    p("Design details", "Heading2"),
    p("The target window is April 18, 2022-September 27, 2024. Each subgroup retains dates "
      "with at least one asking and one nonasking recorded attendee from that same group; "
      "usable date ranges therefore differ. Outlet-FE singletons are removed. No assumed "
      "co-affiliation or question-implied attendance is added, and incomplete YouTube coverage "
      "is not coded as zero."),
    p("History is the April 18, 2021-April 17, 2022 ratio of total questions to recorded "
      "journalist-attendance records, on jointly covered dates, excluding November 2021. "
      "Interactions with quarter include missing-history indicators; 2022 Q2 is the reference."),
    p("Groups use consensus nonmissing metadata ideology codes across subsidiaries sharing "
      "a source unit. Independent denotes the existing unclear code, not verified ideological "
      "neutrality. La Jornada's shared ID mixes aligned and unclear codes and is excluded "
      "from these subgroup models; the pooled models are unchanged."),
    p("Between-group tests use a stacked model with group-by-date FE and group-specific "
      "history slopes, reproducing separate point estimates. Covariance clusters by outlet; "
      "t/F reference degrees of freedom conservatively use the smallest compared group minus "
      "one. Tests are exploratory and unadjusted for multiple comparisons."),
    p("The treatment is asking at least one question, conditional on recorded attendance; "
      "it is not observed randomized seat assignment. Engagement is a saved cumulative "
      "snapshot, not daily increments, and same-day videos may precede the question. "
      "Log1p coefficients are not automatically percentage effects."),
]

def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#687781"))
    canvas.drawString(54, 30, "Effect of asking | Ideology heterogeneity")
    canvas.drawRightString(558, 30, str(doc.page))
    canvas.restoreState()

SimpleDocTemplate(str(PDF), pagesize=(612, 792), rightMargin=54, leftMargin=54,
                  topMargin=42, bottomMargin=48).build(story, onFirstPage=footer, onLaterPages=footer)
print(PDF)

"""Compare conventional outlet-clustered and null-imposed wild-bootstrap p-values."""
import csv
import os
import argparse
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser()
parser.add_argument("--weekly", action="store_true")
weekly = parser.parse_args().weekly
env = {}
for line in (ROOT / ".env").read_text().splitlines():
    if line.strip() and not line.lstrip().startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("'\"")
DATA = Path(os.getenv("MEDIA_ROOT", env["MEDIA_ROOT"])) / "results/effect_of_asking" / (
    "weekly_interactions_combined" if weekly else "pooled_interactions_combined") / "wild_cluster_9999"
with (DATA / "results.csv").open(newline="") as f:
    rows = list(csv.DictReader(f))
assert len(rows) == 18 and all(int(r["valid_draws"]) == int(r["B"]) == 9999 for r in rows)
N, G, T = (int(rows[0][k]) for k in ["n", "clusters", "dates"])
assert all(r["impose_null"] == "TRUE" and int(r["clusters"]) == G and int(r["n"]) == N
           and int(r["dates"]) == T for r in rows)
assert all(float(r["wild_p"]) > .05 for r in rows)
OUTCOMES = ["likes", "comments", "views"]
LABELS = ["Opp. + Independent", "Aligned", "Aligned - (Opp. + Independent)"]
MODELS = ["History adjusted", "Baseline"]

def one(m, o, label):
    rr = [r for r in rows if (r["model"], r["outcome"], r["label"]) == (m,o,label)]
    assert len(rr) == 1
    return rr[0]

def fmt(v):
    return f"{float(v):.3f}"

TEX = ROOT / "overleaf/tables/effect_of_asking" / ("weekly_wild_bootstrap.tex" if weekly else "combined_wild_bootstrap.tex")
lines = [r"\begingroup\centering\scriptsize", r"\setlength{\tabcolsep}{5pt}",
         r"\renewcommand{\arraystretch}{1.1}", r"\begin{tabular}{@{}llrrr@{}}\toprule",
         r"Outcome & Effect tested & Estimate & Clustered $p$ & Wild bootstrap $p$ \\"]
for m in MODELS:
    lines += [r"\midrule", r"\multicolumn{5}{@{}l}{\textit{" + m + r"}} \\"]
    for o in OUTCOMES:
        for i, label in enumerate(LABELS):
            r = one(m,o,label)
            lines.append(" & ".join([o.capitalize() if i == 0 else "", label,
                fmt(r["estimate"]), fmt(r["conventional_p"]), fmt(r["wild_p"])]) + r" \\")
lines += [r"\midrule", r"\multicolumn{5}{@{}l}{" +
          f'{N:,} outlet-{"weeks" if weekly else "days"}; {G} outlets; {T} {"weeks" if weekly else "dates"}; 9,999 bootstrap draws' + r"} \\",
          r"\bottomrule\end{tabular}\par\endgroup"]
TEX.write_text("\n".join(lines) + "\n")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="BodySmall", fontName="Helvetica", fontSize=9, leading=12, spaceAfter=6))
styles.add(ParagraphStyle(name="CellSmall", fontName="Helvetica", fontSize=8, leading=10))
styles["Title"].fontSize = 19
styles["Title"].leading = 23
styles["Title"].alignment = 0
styles["Title"].textColor = styles["Heading2"].textColor = colors.HexColor("#18354A")

def p(s, style="BodySmall"):
    return Paragraph(s, styles[style])

def table(m):
    body = [["Outcome", "Effect tested", "Estimate", "Clustered p", "Wild p"]]
    for o in OUTCOMES:
        for i, label in enumerate(LABELS):
            r = one(m,o,label)
            body.append([o.capitalize() if i == 0 else "", label, fmt(r["estimate"]),
                         fmt(r["conventional_p"]), "<b>" + fmt(r["wild_p"]) + "</b>"])
    t = Table([[p(c,"CellSmall") for c in row] for row in body],
              colWidths=[55, 215, 70, 82, 82], repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#EFF3F6")),
        ("LINEABOVE", (0,0), (-1,0), .8, colors.HexColor("#18354A")),
        ("LINEBELOW", (0,0), (-1,0), .5, colors.HexColor("#18354A")),
        ("LINEBELOW", (0,-1), (-1,-1), .8, colors.HexColor("#18354A")),
        ("TOPPADDING", (0,0), (-1,-1), 3), ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LEFTPADDING", (0,0), (-1,-1), 4), ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("LINEABOVE", (0,4), (-1,4), .25, colors.HexColor("#CED6DC")),
        ("LINEABOVE", (0,7), (-1,7), .25, colors.HexColor("#CED6DC")),
    ]))
    return t

mc = max(float(r["monte_carlo_se"]) for r in rows)
story = [p("Wild cluster bootstrap: inference check", "Title"),
    p("OPP. + INDEPENDENT VERSUS ALIGNED | Recorded attendees | 12 October 2026"),
    p("Same coefficients and sample: <b>4,979 outlet-days, 54 outlets, 253 dates</b>, "
      "April 19, 2022-September 27, 2024. Outcomes are raw log(1 + likes/comments/views), "
      "without winsorization. Outlet and shared date fixed effects remain in every model."),
    p("History-adjusted model", "Heading2"), table("History adjusted"),
    p("Baseline model", "Heading2"), table("Baseline"), Spacer(1,8),
    p("<b>Result:</b> the adjusted between-group p-values rise from 0.782 to 0.791 (likes), "
      "0.816 to 0.841 (comments), and 0.617 to 0.639 (views). No group effect or difference "
      "rejects zero at 5% under either inference method. This check does not uncover a "
      "significant contrast hidden by conventional inference; it does not rule out low power."),
    p("<b>Bootstrap:</b> 9,999 draws per test; null imposed separately for each effect or "
      "contrast; Rademacher weights common within outlet; studentized, two-sided WCR11 "
      "tests using fwildclusterboot 0.14.3 (fnw11). Outlet FE are projected out and shared "
      "date FE retained as dummies. The bootstrap does not resample individual outlet-days. "
      "Both random generators use seed 20261012."),
    p("<b>Validation:</b> all six refits reproduce the original coefficients and clustered "
      "covariances. All 179,982 bootstrap t-statistics are finite, and all 18 p-values are "
      "reproduced from their saved tail frequencies. Bootstrap p-values are reported, not "
      f'bootstrap standard errors or intervals. Maximum approximate Monte Carlo SE: {mc:.3f}. '
      "P-values are not adjusted for multiple comparisons."),
    p("History controls remain the prior-year questions/recorded-journalist-attendance ratio "
      "by quarter plus missing-history interactions. Independent uses unclear; La Jornada's "
      "conflicting source ID remains excluded. Snapshot engagement and observed asking do "
      "not by themselves identify a randomized-seat effect."),
    p('Implementation reference: <link href="https://s3alfisc.github.io/fwildclusterboot/reference/boottest.fixest.html" '
      'color="#245477">Fischer and Roodman, fwildclusterboot: boottest.fixest documentation</link>.'),
]

def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica",8)
    canvas.setFillColor(colors.HexColor("#687781"))
    canvas.drawString(54,30,("Weekly effect of asking" if weekly else "Effect of asking") + " | Null-imposed wild cluster bootstrap")
    canvas.drawRightString(558,30,str(doc.page))
    canvas.restoreState()

if weekly:
    with (DATA.parent / "estimation_week_coverage.csv").open(newline="") as f:
        coverage = list(csv.DictReader(f))
    with (DATA.parent / "sample_flow.csv").open(newline="") as f:
        flow = list(csv.DictReader(f))
    partial = sum(r["complete_conference_coverage"] == "FALSE" for r in coverage)
    p_difference = [fmt(one("History adjusted",o,LABELS[-1])["wild_p"]) for o in OUTCOMES]
    story = [p("Weekly asking: wild cluster bootstrap", "Title"),
        p("OPP. + INDEPENDENT VERSUS ALIGNED | All usable weeks | 12 October 2026"),
        p(f'<b>{N:,} outlet-weeks, {G} outlets, {T} weeks</b>, April 18, 2022-September 27, 2024. '
          "Same outlet roster as the daily analysis. Treatment is at least one <b>observed</b> "
          "question in the week, conditional on recorded attendance at least once that week."),
        p("History-adjusted model", "Heading2"), table("History adjusted"),
        p("Baseline model", "Heading2"), table("Baseline"), Spacer(1,7),
        p("<b>Result:</b> weekly group effects and aligned-minus-combined differences do not "
          "reject zero at 5%. Adjusted wild-bootstrap difference p-values: " + ", ".join(p_difference) +
          " for likes, comments and views. This does not establish zero or identical effects."),
        p("<b>Weekly construction:</b> Monday-Sunday totals across all linked channels and all "
          "publication days, including nonattendance days and weekends. Sum raw metrics first, "
          "then apply log(1 + total); no winsorization. The final Sep 23-27 week has five "
          "in-window days. All included channel-days have usable YouTube coverage."),
        p(f'<b>Partial conference coverage retained:</b> {partial} of {T} estimation weeks have '
          "incomplete attendance/question source overlap. Zero treatment means no question "
          "in available records, not verified absence all week. Of 128 candidate weeks, six "
          "have no question coverage and remain missing; 12 more have no pooled asking/nonasking "
          "variation. The model does not condition on attendance on every question day."),
        p("<b>Model and inference:</b> outlet and shared week FE; original pre-lottery "
          "participation history and missingness by calendar quarter (quarter of the Monday). "
          "9,999 null-imposed WCR11 bootstrap-t draws by outlet, Rademacher weights, two-sided "
          "tests, seed 20261012. All 18 tests and 179,982 draws validated; maximum Monte Carlo "
          f'SE approximately {mc:.3f}. P-values are unadjusted for multiple testing.'),
        p("Engagement is cumulative snapshot engagement on videos published in the week, "
          "not engagement received during that week. Videos may precede the question; this "
          "is not a seven-day post-question or carryover estimate. Partial question coverage "
          "can misclassify treatment. Daily results are preserved; no FEct fit was rerun."),
    ]

PDF = ROOT / "output/pdf" / ("effect_of_asking_weekly_wild_bootstrap.pdf" if weekly else "effect_of_asking_combined_wild_bootstrap.pdf")
SimpleDocTemplate(str(PDF), pagesize=(612,792), leftMargin=54, rightMargin=54,
                  topMargin=40, bottomMargin=48).build(story, onFirstPage=footer, onLaterPages=footer)
print(PDF)

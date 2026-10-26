"""Export the common-date-FE interaction specification; preserve subgroup reports."""
import csv
import os
import argparse
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

ROOT = Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser()
parser.add_argument("--combine", action="store_true", help="Opp. + Independent versus Aligned")
combine = parser.parse_args().combine
env = {}
for line in (ROOT / ".env").read_text().splitlines():
    if line.strip() and not line.lstrip().startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("'\"")
DATA = Path(os.getenv("MEDIA_ROOT", env["MEDIA_ROOT"])) / "results/effect_of_asking" / (
    "pooled_interactions_combined" if combine else "pooled_interactions")

def read(name):
    with (DATA / name).open(newline="") as f:
        return list(csv.DictReader(f))

def one(rows, **keys):
    found = [r for r in rows if all(r[k] == v for k, v in keys.items())]
    assert len(found) == 1, keys
    return found[0]

def fmt(v):
    return f"{float(v):.3f}"

def pv(v):
    return "<0.001" if float(v) < .001 else fmt(v)

effects = read("group_effects.csv")
diffs = read("pairwise_differences.csv")
joint = read("joint_tests.csv")
samples = read("model_samples.csv")
groups = read("group_sample_sizes.csv")
flow = read("sample_flow.csv")
assert len(effects) == (12 if combine else 18) and len(diffs) == (6 if combine else 18)
assert len(joint) == len(samples) == 6
assert len({(r["n"], r["units"], r["dates"]) for r in samples}) == 1
S = samples[0]
OUTCOMES = ["likes", "comments", "views"]
GROUPS = ["Opposition", "Aligned", "Independent"]
MODELS = ["Baseline", "History adjusted"]
PAIRS = ["Aligned - Opposition", "Independent - Opposition", "Aligned - Independent"]
if combine:
    GROUPS = ["Opp. + Independent", "Aligned"]
    PAIRS = ["Aligned - (Opp. + Independent)"]
DF_NUM = joint[0]["df_num"]
TAG = "pooled_interaction_combined" if combine else "pooled_interaction"
TEX = ROOT / "overleaf/tables/effect_of_asking"
TEX.mkdir(parents=True, exist_ok=True)
PDF = ROOT / "output/pdf" / ("effect_of_asking_pooled_interactions_combined.pdf" if combine
                             else "effect_of_asking_pooled_interactions.pdf")

def texcell(r):
    return (r"\shortstack{$" + fmt(r["estimate"]) + r"$\\$[" + fmt(r["ci_low"]) +
            r",\," + fmt(r["ci_high"]) + r"]$\\$p" +
            ("<0.001" if float(r["p_value"]) < .001 else "=" + pv(r["p_value"])) + "$}")

def latex(rows, labels, name):
    lines = [r"\begingroup\centering\scriptsize", r"\setlength{\tabcolsep}{5pt}",
             r"\renewcommand{\arraystretch}{1.12}", r"\begin{tabular}{@{}lccc@{}}\toprule",
             r" & Likes & Comments & Views \\"]
    for m in MODELS:
        lines += [r"\midrule", r"\multicolumn{4}{@{}l}{\textit{" + m + r"}} \\"]
        for label in labels:
            lines.append(label + " & " + " & ".join(texcell(one(rows, model=m, label=label, outcome=o)) for o in OUTCOMES) + r" \\[4pt]")
        rr = [one(joint, model=m, outcome=o) for o in OUTCOMES]
        lines.append(f'Heterogeneity $F({DF_NUM},{S["df"]})$' + " & " + " & ".join(fmt(r["F"]) for r in rr) + r" \\")
        lines.append("Joint-test $p$-value & " + " & ".join("$" + pv(r["p_value"]) + "$" for r in rr) + r" \\")
    lines += [r"\midrule", "Outlet-days & " + " & ".join([f'{int(S["n"]):,}']*3) + r" \\",
              "Outlets & " + " & ".join([S["units"]]*3) + r" \\",
              "Conference dates & " + " & ".join([S["dates"]]*3) + r" \\",
              r"Outlet and shared date FE & Yes & Yes & Yes \\",
              r"\bottomrule\end{tabular}\par\endgroup"]
    (TEX / name).write_text("\n".join(lines) + "\n")

latex(effects, GROUPS, TAG + "_effects.tex")
latex(diffs, PAIRS, TAG + "_differences.tex")
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="BodySmall", fontName="Helvetica", fontSize=9, leading=12,
                          spaceAfter=5 if combine else 7))
styles.add(ParagraphStyle(name="CellSmall", fontName="Helvetica", fontSize=8, leading=10))
styles["Title"].fontSize = 19
styles["Title"].leading = 23
styles["Title"].alignment = 0
styles["Title"].textColor = styles["Heading2"].textColor = colors.HexColor("#18354A")

def p(s, style="BodySmall"):
    return Paragraph(s, styles[style])

def table(headers, rows, widths=(162,114,114,114)):
    t = Table([[p(str(c), "CellSmall") for c in row] for row in [headers]+rows],
              colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LINEABOVE", (0,0), (-1,0), .8, colors.HexColor("#18354A")),
        ("LINEBELOW", (0,0), (-1,0), .5, colors.HexColor("#18354A")),
        ("LINEBELOW", (0,-1), (-1,-1), .8, colors.HexColor("#18354A")),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#EFF3F6")),
        ("TOPPADDING", (0,0), (-1,-1), 3.5 if combine else 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3.5 if combine else 5),
        ("LEFTPADDING", (0,0), (-1,-1), 4), ("RIGHTPADDING", (0,0), (-1,-1), 4)]))
    return t

def cell(r):
    pp = "p &lt; 0.001" if float(r["p_value"]) < .001 else "p = " + pv(r["p_value"])
    return f'<b>{fmt(r["estimate"])}</b><br/>[{fmt(r["ci_low"])}, {fmt(r["ci_high"])}]<br/>{pp}'

def result_table(rows, labels, model):
    return table(["Group" if rows is effects else "Effect difference", "Likes", "Comments", "Views"],
                 [[label] + [cell(one(rows, model=model, label=label, outcome=o)) for o in OUTCOMES] for label in labels])

story = [p("Asking a question: pooled interactions", "Title"),
    p("MAIN HETEROGENEITY SPECIFICATION | Recorded attendees | 12 October 2026"),
    p("One pooled regression per outcome, with asking interacted with opposition, aligned "
      "and independent status. Outlet and <b>shared date fixed effects</b> are included. "
      "History-adjusted models retain the original pooled history controls, with common "
      "slopes across groups. Outcomes are raw log(1 + likes/comments/views), without winsorization."),
    p("History-adjusted effects by group", "Heading2"), result_table(effects, GROUPS, "History adjusted"),
    Spacer(1,8),
    table(["Joint heterogeneity test", "Likes", "Comments", "Views"],
          [[f'F(2, {S["df"]})'] + [fmt(one(joint, model="History adjusted", outcome=o)["F"]) for o in OUTCOMES],
           ["p-value"] + [pv(one(joint, model="History adjusted", outcome=o)["p_value"]) for o in OUTCOMES]]),
    Spacer(1,8),
    p(f'All models: <b>{int(S["n"]):,} outlet-days, {S["units"]} outlets, {S["dates"]} dates</b>, '
      f'{S["from"]} to {S["to"]}. Intervals are 95%; standard errors cluster by outlet. '
      f'Tests use {S["df"]} denominator degrees of freedom. P-values are not multiplicity-adjusted.'),
    table(["Group", "Outlet-days", "Outlets", "Asking outlet-days"],
          [[g] + [one(groups, group=g)[k] for k in ["n","units","asking"]] for g in GROUPS]),
    p("Baseline effects (without history adjustment)", "Heading2"), result_table(effects, GROUPS, "Baseline"),
    Spacer(1,6),
    p("The adjusted joint tests do not reject equal effects at 5%. None of the adjusted "
      "group effects rejects zero at 5%. Small group counts and wide intervals limit the "
      "evidence; lack of significance does not establish equal or absent effects."),
    PageBreak(), p("Interaction contrasts and specification", "Title"),
    p("Adjusted differences between group effects", "Heading2"), result_table(diffs, PAIRS, "History adjusted"),
    Spacer(1,6),
    p("Independent versus opposition differs for likes (difference 0.418; unadjusted "
      "p = 0.045). This isolated pairwise result is exploratory: nine adjusted pairwise "
      "comparisons are displayed, and the joint likes test has p = 0.100."),
    p("How the model is parameterized", "Heading2"),
    p("The model includes Q, Q x Aligned, and Q x Independent; Q indicates at least one "
      "question that day. Opposition is the reference effect; other group effects add "
      "the relevant interaction. Their intervals include coefficient covariance. The joint "
      "test sets both interaction coefficients to zero. Outlet FE absorb group indicators. "
      "Date effects and history slopes are shared, unlike in the separate regressions."),
    p("Sample and controls", "Heading2"),
    table(["Step", "Outlet-days", "Outlets", "Dates"],
          [[r["stage"], r["n"], r["units"], r["dates"]] for r in flow]), Spacer(1,8),
    p("Only directly recorded attendees are used, requiring pooled rather than within-group "
      "asking/nonasking variation. Source-unit/date rows are unique. Independent maps to "
      "unclear. La Jornada's shared ID mixes aligned and unclear subsidiary codes and remains "
      "excluded from heterogeneity; the original pooled results are unchanged."),
    p("History is total questions divided by recorded journalist-attendance records in "
      "April 18, 2021-April 17, 2022, on jointly observed dates, excluding November 2021. "
      "Its interactions with calendar quarter, including missing-history indicators, are "
      "unchanged from the pooled specification. The reference quarter is 2022 Q2."),
    p("Interpretation and retained sensitivity checks", "Heading2"),
    p("Effects are on log1p outcomes, not automatically percentage changes. YouTube metrics "
      "are cumulative snapshot engagement on videos published that day, not daily engagement "
      "increments. Videos may precede the question. Asking is observed; lottery seat assignment "
      "is not. Causal interpretation requires additional assumptions beyond attendance conditioning."),
    p("Earlier subgroup regressions and FEct fits remain sensitivity analyses with different "
      "date-effect restrictions and support. They are not relabeled as pooled-interaction "
      "estimates; no new FEct bootstrap was run."),
]

if combine:
    story = [p("Asking a question: combined comparison", "Title"),
        p("OPP. + INDEPENDENT VERSUS ALIGNED | Recorded attendees | 12 October 2026"),
        p("Opposition and independent outlets are combined and the pooled interaction model "
          "is re-estimated. Outlet and shared date fixed effects, common history controls, "
          "outlet-clustered SEs and raw log(1 + outcome) transformations are unchanged. "
          "No winsorization. Displayed intervals are 95%; p-values are unadjusted."),
        p("History-adjusted group effects", "Heading2"),
        result_table(effects, GROUPS, "History adjusted"),
        p("Difference between group effects", "Heading2"),
        result_table(diffs, PAIRS, "History adjusted"), Spacer(1,6),
        p("The interaction tests whether aligned and Opp. + Independent effects differ. "
          "None of these differences, or the group effects above, is significant at 5%. "
          "Wide intervals do not establish that the effects are identical or zero."),
        p(f'Exact same sample as the three-category model: <b>{int(S["n"]):,} outlet-days, '
          f'{S["units"]} outlets, {S["dates"]} dates</b>, {S["from"]} to {S["to"]}. '
          f'Inference uses {S["df"]} denominator degrees of freedom.'),
        table(["Group", "Outlet-days", "Outlets", "Asking outlet-days"],
              [[g] + [one(groups, group=g)[k] for k in ["n","units","asking"]] for g in GROUPS]),
        p("Baseline effects (without history adjustment)", "Heading2"),
        result_table(effects, GROUPS, "Baseline"), Spacer(1,6),
        p("Specification: Y = outlet FE + date FE + beta Q + theta (Q x Aligned) + history "
          "controls. Q means at least one question that day. Beta is the combined-group "
          "effect; beta + theta is the aligned effect. This re-estimation imposes a common "
          "asking effect for opposition and independent; it is not a simple average of their "
          "previous coefficients."),
        p("History controls remain prior-year questions / recorded journalist-attendance "
          "records (April 18, 2021-April 17, 2022; excluding November 2021), interacted with "
          "quarter, plus missing-history interactions. Independent uses the unclear code. "
          "La Jornada remains excluded because its source ID mixes aligned and unclear codes."),
        p("Engagement is cumulative snapshot engagement on videos published that day, not "
          "daily engagement increments. These log1p coefficients are not automatically "
          "percentage changes. Observed asking is not randomized seat assignment. "
          "Previous three-group estimates and FEct fits are preserved; no new FEct fit was run."),
    ]

def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#687781"))
    canvas.drawString(54,30,"Effect of asking | Pooled interactions")
    canvas.drawRightString(558,30,str(doc.page))
    canvas.restoreState()

SimpleDocTemplate(str(PDF), pagesize=(612,792), leftMargin=54, rightMargin=54,
                  topMargin=40, bottomMargin=48).build(story, onFirstPage=footer, onLaterPages=footer)
print(PDF)

"""Export saved balance estimates; does not fit models or modify source data."""
from pathlib import Path
import csv
import html

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "output/balance"
DEST = ROOT / "output/pdf/balance_results.pdf"
DEST.parent.mkdir(parents=True, exist_ok=True)


def read(name):
    with (SOURCE / name).open(newline="") as f:
        return list(csv.DictReader(f))


def num(x, digits=3):
    if x in ("", "NA", None):
        return "--"
    return f"{float(x):,.{digits}f}"


def pval(x):
    return "<0.001" if float(x) < .001 else num(x)


core = read("individual_balance_core.csv")
joint = read("joint_regression.csv")
tests = read("joint_tests.csv")
flow = read("sample_flow.csv")
summary = read("model_summary.csv")[0]
by_term = {r["term"]: r for r in joint}
labels = {
    "ideology_4t_aligned": "Aligned",
    "ideology_4t_unclear": "Neutral / unclear",
    "ideology_4t_opposition": "Opposition",
    "media_radio": "Radio",
    "media_television": "Television",
    "media_print_any": "Print / newspaper",
    "media_digital": "Digital",
    "media_social_media": "Social media",
    "media_personal": "Personal",
    "coverage_national": "National coverage",
    "age_at_lottery": "Outlet age (years)",
    "subscription_binary": "Subscription",
    "distance_palacio_nacional_km": "Distance to Palacio Nacional (km)",
    "log_pre_attendance": "Prior attendance: log(1 + records)",
    "log_pre_questions": "Prior questions: log(1 + count)",
    "pre_questions_per_recorded_attendance_last_year": "Prior questions / recorded attendance",
    "log_pre_money": "Prior contract value: log(1 + MXN)",
    "log_pre_contracts": "Prior contracts: log(1 + count)",
}
NAVY = colors.HexColor("#243C50")
TEAL = colors.HexColor("#365F68")
INK = colors.HexColor("#26313B")
MUTED = colors.HexColor("#586571")
LINE = colors.HexColor("#D7DEE3")
PALE = colors.HexColor("#F2F5F7")
W, H = A4
MARGIN = 42
WIDTH = W - 2 * MARGIN
styles = {
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=NAVY, spaceAfter=10),
    "sub": ParagraphStyle("sub", fontName="Helvetica", fontSize=10, leading=14, textColor=MUTED, spaceAfter=12),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9, leading=13, textColor=INK, spaceAfter=8),
    "note": ParagraphStyle("note", fontName="Helvetica", fontSize=8, leading=11, textColor=MUTED, spaceAfter=7),
    "section": ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=12, leading=16, textColor=NAVY, spaceBefore=12, spaceAfter=8),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.3, leading=11, textColor=INK),
    "number": ParagraphStyle("number", fontName="Helvetica", fontSize=8.2, leading=11, textColor=INK, alignment=TA_RIGHT),
    "head": ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.white),
}


def para(text, kind="body"):
    return Paragraph(text, styles[kind])


def table(headers, rows, widths, font_size=None):
    content = [[para(html.escape(h), "head") for h in headers]]
    for row in rows:
        content.append([para(html.escape(str(v)), "cell" if j == 0 else "number")
                        for j, v in enumerate(row)])
    t = Table(content, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("LINEBELOW", (0, -1), (-1, -1), .6, LINE),
    ]))
    return t


def page(canvas, doc):
    canvas.setTitle("Post-lottery balance - day fixed effects")
    canvas.setAuthor("AMLO press conference research project")
    canvas.setStrokeColor(LINE)
    canvas.line(MARGIN, 39, W-MARGIN, 39)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, 26, "BALANCE TESTS  |  PROVISIONAL ESTIMATES  |  11 OCT 2026")
    canvas.drawRightString(W-MARGIN, 26, str(doc.page))


story = [
    para("Post-lottery balance", "title"),
    para("Conditional on prior questions per recorded attendance", "sub"),
    para("<b>April 18, 2022 - September 27, 2024</b><br/>"
         f'Conditional sample: {num(summary["conditional_n"], 0)} outlet-days, '
         f'{summary["conditional_units"]} source units, {summary["conditional_dates"]} conference dates. '
         'Recorded attendees with an observed prior ratio only.'),
    para("<b>Adjusted specification:</b> covariate = day fixed effects + coefficient x asked-question "
         "+ prior questions/recorded attendance + error. SEs cluster by source unit."),
    para("Both columns on each row use <b>exactly the same observations</b>. "
         "The only difference is the added ratio control. Prior question and attendance counts are removed."),
]
rows = []
for r in core:
    rows.append([labels[r["covariate"]], num(r["unadjusted_estimate"]),
                 num(r["estimate"]), f'[{num(r["ci_low"])}, {num(r["ci_high"])}]',
                 pval(r["p_value"]), num(r["n"], 0)])
story += [table(["Covariate", "Day FE only", "+ Prior ratio", "Adjusted 95% CI", "Adjusted p", "N"],
                rows, [179, 67, 67, 102, 51, WIDTH-466]),
          Spacer(1, 12),
          para("Binary variables are on a 0-1 scale; multiply differences by 100 for percentage points. "
               "Other differences use the displayed covariate units. All 'prior' measures use "
               "April 18, 2021 - April 17, 2022. The ratio is a control, not an outcome regressed on itself.", "note"),
          para("National coverage, media and subscription flags use missing = 0; a shared unit has a feature if any metadata "
               "member has it. Absent contract histories use 0 before log transformation. "
               "Unknown covariates or undefined ratios are omitted from individual tests, so N can differ.", "note"),
          para("Unadjusted p-values; no multiple-testing correction. No winsorization. "
               "Question-attribution corrections are pending. Sample definitions and missing-data treatment "
               "are detailed on page 3.", "note"),
          PageBreak(),
          para("Joint regression", "title"),
          para("Which characteristics jointly predict asking a question?", "sub"),
          para(f'<b>Specification:</b> asked-question = day fixed effects + {summary["covariates"]} core predictors '
               "+ missingness indicators + error. Outcome: at least one question that day."),
          para("The ratio remains a jointly tested predictor; the joint test is not redefined as a partial "
               "test conditional on it. Standalone prior-question and attendance counts are removed."),
          para("<b>Coefficients below are percentage points.</b> Continuous covariates are measured "
               "per one observed-sample standard deviation; binary covariates compare 1 with 0. "
               "Ideology reference: neutral / unclear, where classification is observed. "
               "Neutral / unclear is shown below but is not an additional estimated coefficient.")]
rows = []
for term in labels:
    if term == "ideology_4t_unclear":
        rows.append(["Neutral / unclear", "Reference", "--", "--"])
        continue
    if term not in by_term:
        continue
    j = by_term[term]
    label = labels[term] + (" [1 SD]" if float(j["scale"]) != 1 else "")
    rows.append([label, num(100*float(j["estimate"])),
                 f'[{num(100*float(j["ci_low"]))}, {num(100*float(j["ci_high"]))}]',
                 pval(j["p_value"])])
story += [table(["Covariate", "Difference (pp)", "95% CI (pp)", "p-value"], rows,
                [246, 85, 119, WIDTH-450]),
          para("Joint tests and model fit", "section"),
          para(f'<b>Core covariates:</b> F({tests[0]["df1"]}, {tests[0]["df2"]}) = {num(tests[0]["F"])}; '
               f'p = {float(tests[0]["p"]):.3g}.<br/>'
               f'<b>Covariates plus missingness:</b> F({tests[1]["df1"]}, {tests[1]["df2"]}) = '
               f'{num(tests[1]["F"])}; p = {float(tests[1]["p"]):.3g}.<br/>'
               f'<b>N:</b> {num(summary["n"], 0)}. <b>Clusters:</b> {summary["units"]}. '
               f'<b>Within R-squared:</b> {num(summary["within_r2"], 4)}.'),
          para("Observable characteristics jointly predict access in this sample. These are conditional "
               "associations, not causal effects or a direct test of the seating draws. "
               "Uncertainty uses outlet/source-unit clustered standard errors.", "note"),
          PageBreak(),
          para("Sample and estimation notes", "title"),
          para("Definitions, exclusions, and remaining uncertainty", "sub"),
          para("Sample construction", "section")]
flow_labels = [
    "Unambiguous linked source pairs, calendar-day panel",
    "Recorded attendees; attendance and questions matched and observed",
    "Dates with both asking and non-asking outlets",
    "Observed prior ratio: eligible for individual conditional tests",
]
story += [table(["Stage", "Outlet-days", "Units", "Dates"],
                [[flow_labels[i], num(r["n"], 0), r["units"], r["days"]] for i, r in enumerate(flow)],
                [300, 83, 64, WIDTH-447]),
          Spacer(1, 10),
          para("<b>Recorded attendance.</b> The main sample excludes assumed co-affiliations and attendance "
               "inferred only from asking. Camera/technical roles were filtered upstream. A source/date "
               "without coverage is not treated as an observed zero."),
          para("<b>Deduplication.</b> Shared source pairs count once. Five ambiguous attendance-to-question "
               "mappings are excluded: bajo palabra, jaime farias informa, lord molecula oficial, "
               "mmm otros, and oem otros. Units without a matched question source are also excluded."),
          para("<b>Why N differs.</b> Format/coverage, subscription and absent contract histories use zero. "
               "Individual models omit undefined ratios and unknown age, distance or conflicting ideology. "
               "The joint model retains those outlet-days using zero imputation "
               "plus missingness indicators. N counts outlet-days, not distinct outlets."),
          para("Missingness coefficients in the joint model", "section")]
miss = [j for j in joint if j["term"].endswith("_missing")]
story += [table(["Missing covariate indicator", "Difference (pp)", "95% CI (pp)", "p-value"],
                [[labels[j["term"].removesuffix("_missing")], num(100*float(j["estimate"])),
                  f'[{num(100*float(j["ci_low"]))}, {num(100*float(j["ci_high"]))}]', pval(j["p_value"])]
                 for j in miss], [246, 85, 119, WIDTH-450]),
          Spacer(1, 10),
          para("All three political categories appear in the individual table; neutral / unclear is the joint "
               "reference. Conflicting political classifications are not recoded as neutral. "
               "Redundant missingness indicators are omitted automatically. Current metadata may not describe "
               "the pre-lottery period; age uses only unambiguous four-digit founding years.", "note"),
          para("Contract histories sum each distinct beneficiary once per unit/window, in nominal MXN. "
               "Absent histories count as zero by the requested convention; an unmatched history does not "
               "prove no contracts existed. Shared companies are not added repeatedly for subsidiaries. "
               "Negative totals are missing in the log specification. November 2021 remains excluded "
               "from recorded attendance histories but is retained in question and contract totals.", "note"),
          para("Questions/recorded attendance = prior-year question count divided by journalist attendance "
               "records, using dates observed in both sources. It is not a probability and can exceed 1. "
               "A zero denominator is undefined, not zero. The individual regressions control for this ratio "
               "linearly; they do not impose exact matching on the ratio.", "note"),
          para(f'Source: saved estimates in output/balance. This PDF exports {len(core)} core balance comparisons '
               "and the complete joint model; supplementary individual tests for all historical windows "
               "remain in individual_balance_all_windows.csv. No models were rerun for this export.", "note")]

doc = SimpleDocTemplate(str(DEST), pagesize=A4, rightMargin=MARGIN, leftMargin=MARGIN,
                        topMargin=39, bottomMargin=52)
doc.build(story, onFirstPage=page, onLaterPages=page)
print(DEST)

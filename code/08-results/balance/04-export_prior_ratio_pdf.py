"""Render the saved ratio-only analysis; no estimation."""
from pathlib import Path
import csv
from html import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "output/balance/prior_ratios"
DEST = ROOT / "output/pdf/balance_prior_ratios.pdf"
DEST.parent.mkdir(parents=True, exist_ok=True)


def read(name):
    with (SOURCE / name).open(newline="") as f:
        return list(csv.DictReader(f))


def f(x, digits=3):
    return f"{float(x):,.{digits}f}"


def p(x):
    return "<0.001" if float(x) < .001 else f(x)


balance = read("individual_balance.csv")
joint = read("joint_regression.csv")
test = read("joint_test.csv")[0]
support = read("window_support.csv")
sample = read("sample_flow.csv")[-1]
NAVY = colors.HexColor("#243C50")
GRAY = colors.HexColor("#586571")
PALE = colors.HexColor("#F2F5F7")
W, H = A4
WIDTH = W - 84
styles = {
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=21, leading=25, textColor=NAVY, spaceAfter=10),
    "h": ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=12, leading=16, textColor=NAVY, spaceBefore=13, spaceAfter=8),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.3, leading=14, spaceAfter=9),
    "note": ParagraphStyle("note", fontName="Helvetica", fontSize=8.2, leading=12, textColor=GRAY, spaceAfter=9),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.4, leading=12),
    "number": ParagraphStyle("number", fontName="Helvetica", fontSize=8.4, leading=12, alignment=2),
    "head": ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=8.2, leading=11, textColor=colors.white),
}


def para(text, kind="body"):
    return Paragraph(text, styles[kind])


def table(headers, rows, widths):
    cells = [[para(escape(h), "head") for h in headers]]
    cells += [[para(escape(str(c)), "cell" if i == 0 else "number") for i, c in enumerate(row)] for row in rows]
    t = Table(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def footer(canvas, doc):
    canvas.setTitle("Balance of historical question-to-attendance ratios")
    canvas.setAuthor("AMLO press conference research project")
    canvas.setStrokeColor(colors.HexColor("#D7DEE3"))
    canvas.line(42, 39, W-42, 39)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GRAY)
    canvas.drawString(42, 26, "PRIOR RATIOS ONLY  |  PROVISIONAL  |  11 OCT 2026")
    canvas.drawRightString(W-42, 26, str(doc.page))


story = [
    para("Historical access ratios", "title"),
    para("12 months, 18 months, 24 months, and full available pre-lottery history", "note"),
    para("<b>Prior ratio = total questions / recorded journalist attendance records.</b><br/>"
         "Both counts use the same dates observed in both sources. This is a ratio of totals, "
         "not an average daily ratio or the share of attended days with a question."),
    para("The earlier control used only the <b>12 months before April 18, 2022</b>. "
         "This analysis tests the alternative historical ratios themselves, with day fixed effects. "
         "No metadata, contracts, or standalone question/attendance counts enter the regressions."),
    para("Historical windows", "h"),
    table(["Window", "Calendar start", "Calendar end"],
          [[r["label"], r["from"], r["to"]] for r in balance], [190, 161, WIDTH-351]),
    Spacer(1, 10),
    para(f'<b>Post-lottery sample:</b> April 18, 2022 - September 27, 2024. '
         f'{f(sample["n"], 0)} outlet-days, {sample["units"]} source units, {sample["dates"]} conference dates. '
         "All four ratios are observed for every unit in this common sample."),
    para("Individual balance tests", "h"),
    para("<b>Each row is a separate regression:</b> historical ratio = day fixed effects "
         "+ coefficient x asked-question + error. Standard errors cluster by source unit."),
    table(["Prior window", "Asking mean", "Not asking mean", "Day-FE difference", "95% CI", "p-value"],
          [[r["label"], f(r["asking_mean"]), f(r["nonasking_mean"]), f(r["estimate"]),
            f'[{f(r["ci_low"])}, {f(r["ci_high"])}]', p(r["p_value"])] for r in balance],
          [115, 70, 76, 82, 112, WIDTH-455]),
    Spacer(1, 12),
    para("Differences are measured in <b>questions per attendance record</b>, not percentage points. "
         "A positive difference means post-lottery askers had a higher historical ratio than non-askers "
         "attending the same conference. Ratios can exceed 1."),
    para("The same observations are used for every window. Missing or zero historical denominators "
         "remain undefined and are excluded, not imputed to zero. November 2021 is excluded "
         "from both counts in every ratio. Individual p-values are not adjusted for multiple testing.", "note"),
    PageBreak(),
    para("Joint test and coverage", "title"),
    para("Ratio-only model; no metadata covariates", "note"),
    para("<b>Joint specification:</b> asked-question = day fixed effects + the four prior ratios + error. "
         "All four ratios enter together, each divided by its sample standard deviation. "
         "The sample and source-unit clustering are identical to the individual tests."),
    table(["Prior window", "Coefficient (pp / SD)", "95% CI (pp)", "p-value"],
          [[r["label"], f(100*float(r["estimate"])),
            f'[{f(100*float(r["ci_low"]))}, {f(100*float(r["ci_high"]))}]', p(r["p_value"])] for r in joint],
          [180, 121, 140, WIDTH-441]),
    Spacer(1, 12),
    para(f'<b>Joint Wald test:</b> F({test["df1"]}, {test["df2"]}) = {f(test["F"])}; p = {p(test["p"])}.<br/>'
         f'<b>N:</b> {f(test["n"], 0)}; <b>units:</b> {test["units"]}; <b>dates:</b> {test["dates"]}. '
         f'<b>Within R-squared:</b> {f(test["within_r2"], 4)}.'),
    para("These windows overlap heavily. The joint coefficients compare one ratio while holding the other "
         "three fixed, so they can be imprecise. This joint test is different from each separate balance "
         "regression on page 1; its p-value is not a test of which window is best."),
    para("Actual historical coverage", "h"),
    table(["Prior window", "First covered date", "Last covered date", "Common dates"],
          [[r["label"], r["first_common"], r["last_common"],
            r["min_covered_dates"] if r["min_covered_dates"] == r["max_covered_dates"]
            else f'{r["min_covered_dates"]}-{r["max_covered_dates"]}'] for r in support],
          [155, 125, 125, WIDTH-405]),
    Spacer(1, 12),
    para("Calendar bounds do not imply complete coverage. The full-history window nominally starts "
         "December 1, 2018, but its first common-covered date is March 1, 2019. Only observed common "
         "dates contribute to either count. Dates with a known question but no attendance record can "
         "contribute to the numerator when both sources are covered; no attendance is inferred."),
    para("The post-lottery sample contains recorded attendees and dates with both asking and non-asking "
         "outlets. Shared source IDs are deduplicated; the five previously ambiguous cross-source mappings "
         "remain excluded. Metadata is used only as an identifier crosswalk.", "note"),
    para("Provisional: pending transcript speaker-attribution corrections remain unapplied. "
         "These are observed-access diagnostics, not proof of random speaking opportunities. "
         "Results, coverage audits, models and source mappings are saved in output/balance/prior_ratios. "
         "The earlier metadata analyses are preserved.", "note"),
]
SimpleDocTemplate(str(DEST), pagesize=A4, leftMargin=42, rightMargin=42, topMargin=39,
                  bottomMargin=52).build(story, onFirstPage=footer, onLaterPages=footer)
print(DEST)

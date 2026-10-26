"""Report the saved four all-measure joint balance tests; no re-estimation."""
import csv
from pathlib import Path
from html import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "output/balance/joint_by_window"
DEST = ROOT / "output/pdf/balance_joint_by_window.pdf"
DEST.parent.mkdir(parents=True, exist_ok=True)


def read(name):
    with (SOURCE / name).open(newline="") as f:
        return list(csv.DictReader(f))


tests = read("joint_tests.csv")
audits = read("missingness_audit.csv")
diagnostics = read("diagnostics.csv")
primary = [r for r in tests if r["test"] == "histories"]
broader = [r for r in tests if r["test"] == "histories_and_missingness"]
W, H = A4
WIDTH = W - 84
NAVY = colors.HexColor("#243C50")
GRAY = colors.HexColor("#586571")
styles = {
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=21, leading=25, textColor=NAVY, spaceAfter=12),
    "section": ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=NAVY, spaceBefore=12, spaceAfter=7),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=14, spaceAfter=9),
    "note": ParagraphStyle("note", fontName="Helvetica", fontSize=8.3, leading=12, textColor=GRAY, spaceAfter=8),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=9, leading=12),
    "head": ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=colors.white),
}


def p(text, style="body"):
    return Paragraph(text, styles[style])


def number(x):
    return f"{float(x):.3f}"


def pval(x):
    x = float(x)
    return f"{x:.2e}" if x < .001 else f"{x:.4f}"


def table(headers, rows, widths):
    data = [[p(escape(h), "head") for h in headers]]
    data += [[p(escape(str(x)), "cell") for x in row] for row in rows]
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F5F7")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def result_table(rows):
    return table(["Historical window", "F (df1, df2)", "p-value", "Holm p-value"],
                 [[r["label"], f'{number(r["F"])} ({r["df1"]}, {r["df2"]})',
                   pval(r["p_value"]), pval(r["p_holm_four_windows"])] for r in rows],
                 [151, 130, 110, WIDTH - 391])


def footer(canvas, doc):
    canvas.setTitle("Joint balance by historical window")
    canvas.setAuthor("AMLO press conference research project")
    canvas.setStrokeColor(colors.HexColor("#D7DEE3"))
    canvas.line(42, 39, W - 42, 39)
    canvas.setFillColor(GRAY); canvas.setFont("Helvetica", 8)
    canvas.drawString(42, 26, "JOINT BALANCE  |  PROVISIONAL  |  11 OCT 2026")
    canvas.drawRightString(W - 42, 26, str(doc.page))


r = primary[0]
story = [
    p("Joint balance by historical window", "title"),
    p("All 12 historical measures in each model, with missingness indicators", "note"),
    p("<b>Model:</b> asked-question indicator = day fixed effects + 12 historical measures "
      "+ 3 missingness indicators + error. Standard errors cluster by outlet source unit. "
      "No metadata predictors or standalone prior attendance/question counts."),
    p(f'<b>Common sample:</b> {int(r["n"]):,} recorded-attendee outlet-days; {r["units"]} outlet units; '
      f'{r["dates"]} informative conference dates; {r["asking_unit_days"]} asking outlet-days. '
      'Post period: April 18, 2022 - September 27, 2024.'),
    p("A. Historical measures jointly", "section"),
    p("Primary null: all 12 history coefficients equal zero, allowing the three missingness "
      "coefficients to be unrestricted. This tests histories conditional on missingness."),
    result_table(primary),
    Spacer(1, 7),
    p("The 18- and 24-month tests reject at 5%, including after Holm adjustment across the four "
      "primary tests. The 12-month and full-history tests do not reject at 5%. "
      "Nonrejection does not establish equivalence or random access."),
    p("B. Histories and missingness jointly", "section"),
    p("Broader null: all 15 coefficients equal zero. Rejection can reflect associations with "
      "missing-data status as well as observed histories; it is a different null from panel A."),
    result_table(broader),
    Spacer(1, 9),
    p("Holm adjustments are calculated separately for the four tests in A and the four in B. "
      "These are exploratory cluster-robust Wald tests, not randomization-inference tests. "
      "The four windows overlap; they are alternative specifications, not independent replications.", "note"),
    p("YouTube engagement is a saved snapshot for videos published in each historical window, "
      "not verified engagement measured before the lottery. Therefore these combined tests "
      "are descriptive diagnostics, not clean tests of strictly pre-treatment covariates.", "note"),
    PageBreak(), p("Definitions, missingness and checks", "title"),
    p("Historical measures", "section"),
    p("<b>Access (1):</b> questions / recorded journalist attendance records. "
      "<b>Contracts (2):</b> value in nominal MXN and number of contracts. "
      "<b>YouTube (9):</b> videos, views, likes, comments, interactions, and views, likes, "
      "comments and interactions per video. Interactions = likes + comments; per-video "
      "averages are window totals divided by window videos."),
    p("The access ratio is raw; contract and YouTube measures use log(1+x), without winsorization. "
      "Each history is divided by its SD among observed outlet-days. Source entities are "
      "deduplicated within outlet units before aggregation. All histories are frozen at April 17, 2022."),
    table(["Window", "First date", "Last date"],
          [[x["label"], x["from"], x["to"]] for x in primary], [201, 155, WIDTH - 356]),
    p("Missingness is not an observed zero", "section"),
    p("Raw unavailable histories remain NA. Only the regression matrix replaces missing values "
      "with zero and adds an indicator. Three distinct indicators capture missing access ratios, "
      "contract histories and YouTube histories; duplicate indicator patterns are included once. "
      "No indicators from other windows are added."),
    table(["Window", "Missing access: units / days", "Missing contracts: units / days", "Missing YouTube: units / days"],
          [[r["label"]] + [
              f'{a["missing_units"]} / {int(a["missing_unit_days"]):,}'
              for metric in ["question_attendance_ratio", "contract_value", "videos"]
              for a in audits if a["window"] == r["window"] and a["metric"] == metric
          ] for r in primary], [137, 124, 124, WIDTH - 385]),
    p("An observed beneficiary with no awards retains zero; no matched/observed contract history "
      "remains missing. Matching does not identify contract eligibility. YouTube no-post zeros "
      "follow the archived channel calendar; calendar coverage does not guarantee complete scraping. "
      "November 2021 is excluded only from the access ratio.", "note"),
    p("Numerical checks and limitations", "section"),
    p("Each model retains all 15 regressors with full-rank clustered covariance. Coefficients were "
      "independently recovered after removing date means; all eight Wald statistics were checked "
      "directly. Re-centering observed histories preserves fitted values and both joint tests."),
    p(f'The measures remain highly correlated: covariance-correlation condition numbers range from '
      f'{min(float(x["covariance_correlation_condition"]) for x in diagnostics):.1e} to '
      f'{max(float(x["covariance_correlation_condition"]) for x in diagnostics):.1e}. '
      'These checks passed, but separate coefficient interpretation is fragile and results should remain exploratory. '
      'The earlier five ambiguous source mappings remain excluded; pending transcript corrections are not applied.', "note"),
    p("Reproduce: 07-joint_balance_by_window.R, then 08-export_joint_window_pdf.py. "
      "Saved coefficients, sample, audits, diagnostics and models: output/balance/joint_by_window. "
      "Previous analyses are preserved.", "note"),
]
SimpleDocTemplate(str(DEST), pagesize=A4, leftMargin=42, rightMargin=42,
                  topMargin=39, bottomMargin=52).build(story, onFirstPage=footer, onLaterPages=footer)
print(DEST)

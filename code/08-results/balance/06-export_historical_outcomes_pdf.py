"""Export saved access, contract, and YouTube historical-balance results."""
from pathlib import Path
import csv
from html import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "output/balance/historical_outcomes"
DEST = ROOT / "output/pdf/balance_historical_outcomes.pdf"
DEST.parent.mkdir(parents=True, exist_ok=True)


def read(name):
    with (SOURCE / name).open(newline="") as f:
        return list(csv.DictReader(f))


def fmt(x, digits=3):
    return f"{float(x):,.{digits}f}"


def pval(x):
    return "<0.001" if float(x) < .001 else fmt(x)


results = read("individual_balance.csv")
tests = read("joint_tests.csv")
W, H = A4
WIDTH = W - 84
NAVY = colors.HexColor("#243C50")
GRAY = colors.HexColor("#586571")
PALE = colors.HexColor("#F2F5F7")
styles = {
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=21, leading=25, textColor=NAVY, spaceAfter=9),
    "section": ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=NAVY, spaceBefore=12, spaceAfter=4),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9, leading=13, spaceAfter=8),
    "note": ParagraphStyle("note", fontName="Helvetica", fontSize=8, leading=11, textColor=GRAY, spaceAfter=7),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.4, leading=11),
    "number": ParagraphStyle("number", fontName="Helvetica", fontSize=8.4, leading=11, alignment=2),
    "head": ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=8, leading=10.5, textColor=colors.white),
}


def para(s, style="body"):
    return Paragraph(s, styles[style])


def table(headers, rows, widths):
    data = [[para(escape(h), "head") for h in headers]]
    data += [[para(escape(str(x)), "cell" if j == 0 else "number") for j, x in enumerate(row)] for row in rows]
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def metric_section(metric):
    rr = [r for r in results if r["metric"] == metric]
    r = rr[0]
    return [
        para(escape(r["label"]), "section"),
        para(f'{escape(r["transformation"])} | N = {fmt(r["n"], 0)} outlet-days; '
             f'{r["units"]} units; {r["dates"]} dates. Same sample for all windows.', "note"),
        table(["Prior window", "Asking mean", "Not asking mean", "Day-FE difference", "95% CI", "p-value"],
              [[x["window_label"], fmt(x["asking_mean"]), fmt(x["nonasking_mean"]), fmt(x["estimate"]),
                f'[{fmt(x["ci_low"])}, {fmt(x["ci_high"])}]', pval(x["p_value"])] for x in rr],
              [104, 75, 76, 80, 116, WIDTH-451]),
    ]


def footer(canvas, doc):
    canvas.setTitle("Historical balance: access, contracts and YouTube")
    canvas.setAuthor("AMLO press conference research project")
    canvas.setStrokeColor(colors.HexColor("#D7DEE3"))
    canvas.line(42, 39, W-42, 39)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GRAY)
    canvas.drawString(42, 26, "HISTORICAL BALANCE  |  PROVISIONAL  |  11 OCT 2026")
    canvas.drawRightString(W-42, 26, str(doc.page))


story = [
    para("Access and contract histories", "title"),
    para("12, 18 and 24 months, plus full available pre-lottery history", "note"),
    para("<b>Each row:</b> historical measure = day fixed effects + coefficient x asked-question + error. "
         "Recorded attendees, April 18, 2022 - September 27, 2024; source-unit clustered SEs. "
         "No metadata covariates or standalone attendance/question counts."),
]
for m in ["question_attendance_ratio", "contract_value", "contract_count"]:
    story += metric_section(m)
story += [
    Spacer(1, 10),
    para("Ratio = questions / recorded journalist attendance records on common-covered dates; November 2021 "
         "is excluded. Contracts use contract/order dates and nominal MXN; each beneficiary counts once "
         "per outlet unit/window. No matched, observed contract history is NA and excluded; "
         "observed beneficiaries with no awards in a window retain zero.", "note"),
    para("Contract variables use log(1 + x), not raw MXN/count units. No winsorization. Differences in logged "
         "histories are not causal percentage effects. The source-unit sample differs by measure.", "note"),
]
groups = [
    ("YouTube: publishing and reach", ["videos", "views", "likes"]),
    ("YouTube: engagement", ["comments", "interactions", "views_per_video"]),
    ("YouTube: per-video averages", ["likes_per_video", "comments_per_video", "interactions_per_video"]),
]
for title, metrics in groups:
    story += [
        PageBreak(), para(title, "title"),
        para("Descriptive balance of videos published before the lottery", "note"),
        para("<b>Timing caveat:</b> views, likes and comments are saved engagement snapshots, not verified "
             "counts measured before April 18, 2022. They are exploratory descriptors, not established "
             "pre-treatment covariates. Publication counts are dated activity."),
    ]
    for m in metrics:
        story += metric_section(m)
    story += [
        Spacer(1, 10),
        para("All measures use log(1 + x), without winsorization. Interactions = likes + comments. "
             "Per-video means = total metric / total videos over the window, not the average of daily means. "
             "Known channel grids with no videos use zero; unknown/incomplete linked-channel grids remain missing.", "note"),
        para("URL-token channel IDs count once per outlet unit. Archived calendar coverage does not prove a "
             "complete historical scrape. Same sample across windows within each measure; "
             "individual p-values are unadjusted for multiple testing.", "note"),
    ]
story += [
    PageBreak(), para("Joint tests and definitions", "title"),
    para("One joint test per measure, across its four historical windows", "note"),
    para("<b>Each row:</b> asked-question = day fixed effects + the four windows of the listed measure + error. "
         "The null sets all four coefficients to zero. Ratios/metrics are divided by their sample SD "
         "for estimation; source-unit clustered inference. These are not one combined regression."),
    table(["Measure", "F", "p-value", "N", "Units"],
          [[r["label"], fmt(r["F"]), pval(r["p_value"]), fmt(r["n"], 0), r["units"]] for r in tests],
          [219, 75, 75, 85, WIDTH-454]),
    Spacer(1, 12),
    para("Overlapping windows are correlated, so coefficients conditional on the other windows can be "
         "imprecise. A nonsignificant joint test is not proof of random access or equivalence. "
         "Joint coefficients and confidence intervals are retained in joint_coefficients.csv."),
    para("Window boundaries and coverage", "section"),
    para("All windows end <b>April 17, 2022</b>. Starts: 12 months = April 18, 2021; "
         "18 months = October 18, 2020; 24 months = April 18, 2020; "
         "full history = December 1, 2018."),
    para("Only common-covered dates contribute to the access ratio; actual coverage is incomplete "
         "(145, 221, 276 and 365 dates respectively). Contracts and YouTube retain November 2021. "
         "The full period is the available pre-lottery presidency window, not all contracts since 2012."),
    para("Contracts restore the original missingness rule: unavailable history stays NA. "
         "Multi-beneficiary sums use available observed histories. Matching does not establish eligibility to compete. "
         "YouTube zeros for matched grids are archive conventions, while no channel match or missing linked "
         "channels stays NA. Missing engagement values were handled upstream; this run does not repair the "
         "underlying scrape or recover contemporaneous historical engagement.", "note"),
    para("The earlier five ambiguous attendance/question mappings remain excluded. Pending transcript "
         "speaker-attribution corrections have not been applied. All results remain provisional. "
         "Code: 05-historical_outcome_balance.R. Tables, audits and model objects: "
         "output/balance/historical_outcomes. Previous analyses are preserved.", "note"),
]
SimpleDocTemplate(str(DEST), pagesize=A4, leftMargin=42, rightMargin=42, topMargin=39,
                  bottomMargin=52).build(story, onFirstPage=footer, onLaterPages=footer)
print(DEST)

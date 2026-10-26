"""Two separate balance tables, without founding age or a combined joint test."""
from pathlib import Path
import csv
import argparse
from datetime import date
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak

ROOT = Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser()
parser.add_argument("--months", type=int, choices=(12, 18), default=12)
MONTHS = parser.parse_args().months
DATA = ROOT / f"output/balance/separate_{MONTHS}m_no_age"
TEX = ROOT / f"overleaf/tables/balance/separate_{MONTHS}m_no_age"
TEX.mkdir(parents=True, exist_ok=True)
OUT = ROOT / f"output/pdf/balance_separate_{MONTHS}m_no_age.pdf"
def read(name):
    with (DATA / f"{name}.csv").open() as f:
        return list(csv.DictReader(f))
rows = read("individual")
window = read("window")[0]
window_from = date.fromisoformat(window["from"]).strftime("%B %d, %Y")
window_to = date.fromisoformat(window["to"]).strftime("%B %d, %Y")
joints = {r["test"]: r for r in read("joint")}
assert len(rows) == 21 and set(joints) == {"metadata", "histories"}
def num(x): return f"{float(x):.3f}"
def pv(x): return "<0.0001" if float(x) < .0001 else f"{float(x):.4f}"
def ft(r): return f"F({r['df1']}, {r['df2']}) = {num(r['F'])}; p = {pv(r['p_value'])}"
def label(r): return r["label"] + (" [log(1+x)]" if r["transformation"] == "log(1 + x)" else "")
styles = getSampleStyleSheet()
styles.add(ParagraphStyle("BodyCustom", fontName="Helvetica", fontSize=10, leading=15,
                          textColor=colors.HexColor("#253247"), spaceAfter=10))
styles.add(ParagraphStyle("TitleCustom", parent=styles["BodyCustom"], fontName="Helvetica-Bold",
                          fontSize=17, leading=21, spaceAfter=15))
styles.add(ParagraphStyle("HeadCustom", parent=styles["BodyCustom"], fontName="Helvetica-Bold",
                          fontSize=11, spaceBefore=10))
styles.add(ParagraphStyle("CellCustom", fontName="Helvetica", fontSize=9, leading=12))
def p(text, style="BodyCustom"): return Paragraph(text, styles[style])

def table(key):
    selected = [r for r in rows if (r["family"] == "Metadata") == (key == "metadata")]
    data = [["Covariate", "Difference", "95% CI", "p-value", "N"]]
    latex = [r"\begin{tabular}{lrrrr}", r"\toprule",
             r"Covariate & Difference & 95\% CI & $p$-value & $N$ \\", r"\midrule"]
    for r in selected:
        ci = f"[{num(r['ci_low'])}, {num(r['ci_high'])}]"
        n = f"{int(r['n']):,}"
        data.append([p(escape(label(r)), "CellCustom"), num(r["estimate"]), ci, pv(r["p_value"]), n])
        name = label(r).replace("&", r"\&")
        pp = pv(r["p_value"]).replace("<", "$<$")
        latex.append(f"{name} & {num(r['estimate'])} & {ci} & {pp} & {n} " + r"\\")
    footer = "Joint test of all " + ("metadata covariates: " if key == "metadata" else "historical covariates: ") + ft(joints[key])
    data.append([p(escape(footer), "CellCustom"), "", "", "", ""])
    latex += [r"\midrule", r"\multicolumn{5}{l}{" + footer.replace("<", "$<$") + r"} \\",
              r"\bottomrule", r"\end{tabular}"]
    (TEX / f"balance_{key}.tex").write_text("\n".join(latex) + "\n")
    t = Table(data, colWidths=[198, 66, 108, 63, 57], repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), "Helvetica"), ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9), ("TEXTCOLOR", (0,0), (-1,-1), colors.black),
        ("ALIGN", (1,0), (-1,-1), "RIGHT"), ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (0,-1), 0), ("RIGHTPADDING", (-1,0), (-1,-1), 0),
        ("TOPPADDING", (0,0), (-1,-1), 7), ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ("LINEABOVE", (0,0), (-1,0), .8, colors.HexColor("#243b53")),
        ("LINEBELOW", (0,0), (-1,0), .5, colors.grey),
        ("LINEABOVE", (0,-1), (-1,-1), .6, colors.HexColor("#243b53")),
        ("SPAN", (0,-1), (-1,-1))]))
    return t

story = [p("Balance among recorded attendees", "TitleCustom"),
    p("Full post-lottery sample - Two separate analyses", "HeadCustom"),
    p("The estimation sample runs from April 19, 2022 to September 27, 2024: "
      "7,976 outlet-days, 81 deduplicated outlet units and 318 conference dates. "
      "Only directly recorded attendees on dates with both asking and non-asking outlets are compared. "
      "Asking equals one if an outlet asked at least one question that day."),
    p("Metadata, excluding founding age", "HeadCustom"),
    p("Nine binary characteristics, with a separate joint test: <b>" + ft(joints["metadata"]) + "</b>. "
      "Every individual metadata regression and the metadata joint regression use all 7,976 observations. "
      "There is no age variable, age-missingness dummy, or historical control in this model."),
    p("Historical measures", "HeadCustom"),
    p(f"Twelve measures from {window_from}-{window_to} ({MONTHS} months before the lottery), "
      "with their own joint test: <b>" + ft(joints["histories"]) + "</b>. "
      "The historical joint model retains the three existing missingness controls for the participation "
      "ratio, contract history and YouTube history. Their coefficients are unrestricted and are not part "
      "of the reported F-test. No metadata controls enter this model."),
    p("Specifications and interpretation", "HeadCustom"),
    p("Individual tests regress each characteristic on the question indicator and date fixed effects. "
      "Positive differences indicate a higher value among asking attendees on the same dates. "
      "Binary differences are in proportion units: 0.10 is 10 percentage points. Joint tests instead "
      "regress the question indicator on all characteristics in the relevant block, with date fixed effects. "
      "Both use outlet-clustered inference. P-values are unadjusted; intervals are pointwise 95% intervals."),
    p("These tests do not establish random assignment or identify willingness to ask. The historical "
      "joint covariance is ill-conditioned because of highly correlated YouTube measures; interpret its "
      "Wald inference cautiously. Founding years are set aside until corrected, as requested."),
    PageBreak(), p("Metadata balance", "TitleCustom"),
    p("Asking minus non-asking attendees, conditional on conference-day fixed effects."), table("metadata"),
    Spacer(1, 14), p("Coding", "HeadCustom"),
    p("Formats and coverage indicators may overlap. A shared source unit receives one if any linked "
      "metadata outlet has the attribute. Missing binary flags are zero under the existing convention; "
      "therefore no missingness dummies enter the metadata model. National and state use whole-word "
      "coverage labels, excluding 'international' or 'multistate' alone."),
    p("Geographic definitions remain provisional: Mexico City means headquarters-state code 9. "
      "Metropolitan area means an explicit 'metropolitan' coverage label for any metropolitan area, "
      "not specifically the Mexico City metro area. The two indicators are not nested location categories."),
    p("Metadata rows are collapsed to the resolved attendance-question source ID before merging. "
      "This preserves one observation per source unit and date. Current metadata classifications "
      "are not independently verified as the outlet's status at the lottery."),
    PageBreak(), p("Historical balance", "TitleCustom"),
    p(f"{MONTHS}-month pre-lottery histories. Asking minus non-asking attendees, with date fixed effects."),
    table("histories"), Spacer(1, 12),
    p("The participation ratio divides total questions by recorded journalist-attendance records "
      "on common covered dates, not question-days by attendance-days. November 2021 is excluded "
      "from both numerator and denominator because attendance is unreliable."),
    p("Contract and YouTube measures use log(1+x), without winsorization. Individual regressions use "
      "the established observed-data cohorts common across historical windows. The joint model retains "
      "all attendees using zero placeholders with missingness indicators. Unmatched contract histories "
      "remain missing in the data; observed beneficiaries with no awards have genuine zeros."),
    p("YouTube engagement is the saved snapshot for videos published during the historical window, "
      "not verified engagement measured before the lottery. Per-video measures divide window totals "
      "by videos published. These engagement measures are not verified strictly pre-treatment covariates.")]
def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#65758b"))
    canvas.drawString(54, 30, "All outlets | Full post-lottery sample | Age excluded")
    canvas.drawRightString(558, 30, str(doc.page))
    canvas.restoreState()
SimpleDocTemplate(str(OUT), pagesize=(612,792), leftMargin=54, rightMargin=54,
                  topMargin=48, bottomMargin=50).build(story, onFirstPage=footer, onLaterPages=footer)
print(OUT)

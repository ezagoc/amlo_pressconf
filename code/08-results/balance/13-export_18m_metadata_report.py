"""Export the full post-lottery, 18-month-history balance report and LaTeX tables."""
from pathlib import Path
import csv
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "output/balance/full_post_18m_metadata"
TEX = ROOT / "overleaf/tables/balance/full_post_18m_metadata"
TEX.mkdir(parents=True, exist_ok=True)
OUT = ROOT / "output/pdf/balance_full_post_18m_metadata.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)

def read(name):
    with (DATA / f"{name}.csv").open() as f:
        return list(csv.DictReader(f))

rows, joints, units = read("individual"), read("joint"), read("units")
joint = {r["test"]: r for r in joints}
def num(x): return f"{float(x):.3f}"
def pval(x): return "<0.001" if float(x) < .001 else f"{float(x):.3f}"
def integer(x): return f"{int(x):,}"
def ftext(r): return f"F({r['df1']}, {r['df2']}) = {num(r['F'])}; p = {pval(r['p_value'])}"
def label(r):
    return r["label"] + (" [log(1+x)]" if r["transformation"] == "log(1 + x)" else "")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle("BodyCustom", fontName="Helvetica", fontSize=10, leading=15,
                          textColor=colors.HexColor("#253247"), spaceAfter=9))
styles.add(ParagraphStyle("HeadingCustom", fontName="Helvetica-Bold", fontSize=17, leading=21,
                          textColor=colors.HexColor("#243b53"), spaceAfter=14))
styles.add(ParagraphStyle("SectionCustom", parent=styles["BodyCustom"], fontName="Helvetica-Bold",
                          fontSize=11, spaceBefore=12, spaceAfter=8))
styles.add(ParagraphStyle("CellCustom", fontName="Helvetica", fontSize=9, leading=12))
styles.add(ParagraphStyle("RightCustom", parent=styles["CellCustom"], alignment=TA_RIGHT))
def para(text, style="BodyCustom"): return Paragraph(text, styles[style])

def table(selected, footer):
    data = [[para("Covariate", "CellCustom"), "Difference", "95% CI", "p-value", "N"]]
    for r in selected:
        data.append([para(escape(label(r)), "CellCustom"), num(r["estimate"]),
                     f"[{num(r['ci_low'])}, {num(r['ci_high'])}]", pval(r["p_value"]), integer(r["n"])])
    data.append([para(escape(footer), "CellCustom"), "", "", "", ""])
    t = Table(data, colWidths=[204, 66, 108, 57, 57], repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 9),
        ("ALIGN", (1,0), (-1,-1), "RIGHT"), ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (0,-1), 0), ("RIGHTPADDING", (-1,0), (-1,-1), 0),
        ("TOPPADDING", (0,0), (-1,-1), 7), ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ("LINEABOVE", (0,0), (-1,0), .9, colors.HexColor("#243b53")),
        ("LINEBELOW", (0,0), (-1,0), .5, colors.HexColor("#8794a3")),
        ("LINEABOVE", (0,-1), (-1,-1), .6, colors.HexColor("#243b53")),
        ("SPAN", (0,-1), (-1,-1)),
    ]))
    return t

story = [para("Balance among recorded attendees", "HeadingCustom")]
story += [para("All outlets - Full post-lottery period", "SectionCustom"),
          para("<b>Provisional metadata report.</b> The workbook at the pipeline path has unchanged "
               "founding-year values relative to the processed snapshot; the user's newly added years "
               "have not been located. Geographic definitions also await confirmation (page 4)."),
          para("Post-lottery window: April 18, 2022 through the end of AMLO's tenure. "
               "The usable estimation sample runs from April 19, 2022 to September 27, 2024. "
               "All historical measures use October 18, 2020-April 17, 2022, the 18 months before the lottery."),
          para(f"The joint-test sample contains <b>{integer(joint['combined']['n'])} outlet-days</b>, "
               f"<b>{joint['combined']['units']} deduplicated outlet units</b>, and "
               f"<b>{joint['combined']['dates']} conference dates</b>. Only directly recorded attendees "
               "on dates with both asking and non-asking outlets are compared. The question indicator equals "
               "one if the outlet asked at least one question that day."),
          para("Joint balance tests", "SectionCustom")]
for key, title in [("histories", "Historical measures only"), ("metadata", "Metadata only"),
                   ("combined", "Historical measures and metadata")]:
    story.append(para(f"<b>{title}:</b> {escape(ftext(joint[key]))}."))
story += [para("How to read the results", "SectionCustom"),
          para("Individual tests regress each covariate on the same-day question indicator with date fixed "
               "effects. A positive difference means that asking outlets have more of that characteristic "
               "than non-asking attendees on the same dates. These are associations, not treatment effects. "
               "Binary differences are in proportion units (0.10 = 10 percentage points); age is in years."),
          para("Joint tests regress the question indicator on the full set of covariates and date fixed "
               "effects. The null sets all substantive coefficients in that model to zero. Missingness "
               "indicators are included but left unrestricted. All inference clusters by outlet unit; "
               "p-values are unadjusted and confidence intervals are pointwise."),
          para("Balance does not establish random assignment. Rejection indicates predictable selection "
               "among recorded attendees, but these records do not distinguish motivation to ask from other "
               "persistent outlet characteristics. The many correlated YouTube measures can also make joint "
               "Wald inference sensitive in a sample of 81 clusters."), PageBreak(),
          para("Historical measures", "HeadingCustom"),
          para("18 months before the lottery. Same-day asking minus non-asking attendees."),
          table([r for r in rows if r["family"] != "Metadata"],
                "Joint test of all historical covariates: " + ftext(joint["histories"])),
          Spacer(1, 14),
          para("The participation ratio is total questions divided by total recorded journalist-attendance "
               "records on common covered dates, not the fraction of attendance days with a question. "
               "November 2021 is excluded from both parts of this historical ratio because attendance is unreliable."),
          para("Contract and YouTube measures use log(1+x), without winsorization. Unmatched or unobserved "
               "contract histories remain missing; observed beneficiaries with no awards retain zero. "
               "Per-video measures divide window totals by videos published, not by days."),
          para("YouTube views, likes and comments are saved engagement snapshots for videos published "
               "during the historical window. They are not verified as engagement measured before the lottery "
               "and should not be treated as strictly pre-treatment outcomes."), PageBreak(),
          para("Outlet characteristics", "HeadingCustom"),
          para("Metadata read directly from the workbook at the pipeline path. Age uses 2022 as the reference year."),
          table([r for r in rows if r["family"] == "Metadata"],
                "Joint test of metadata covariates: " + ftext(joint["metadata"])),
          Spacer(1, 12),
          para("Combined joint test", "SectionCustom"),
          para("All 12 historical measures and all 10 metadata characteristics: <b>" +
               escape(ftext(joint["combined"])) + "</b>. Missingness coefficients are not tested."),
          para("Coding and missing values", "SectionCustom"),
          para("Format and coverage indicators may overlap. A deduplicated unit receives a one if any "
               "linked metadata outlet has that attribute; missing flags are zero under the existing coding "
               "convention. National and state coverage use whole-word labels, so 'international' alone "
               "does not count as national and 'multistate' alone does not count as state."),
          para("Age equals 2022 minus an unambiguous four-digit founding year. Entries with competing "
               "dates, post-2022 founding years, or conflicting years across a shared source unit are missing. "
               f"Age is observed for {sum(r['age_2022'] != 'NA' for r in units)} of {len(units)} units. "
               "The current metadata snapshot is not independently verified as the outlet's status at the lottery."),
          PageBreak(), para("Definitions and sample audit", "HeadingCustom")]
geo_path = DATA / "geography_definition.txt"
story.append(para(escape(geo_path.read_text())))
story += [para("Why the individual sample sizes differ", "SectionCustom"),
          para("Individual historical regressions retain the established observed-data cohorts shared across "
               "the 12-, 18-, 24-month and full-history windows. Metadata regressions use the observed "
               "characteristic and then require both asking and non-asking attendees within each date. "
               "The joint models retain the full attendee sample using separate missingness indicators. "
               "Thus individual and joint tests are not the same regression or always the same sample."),
          para("Shared outlet identities", "SectionCustom"),
          para("Metadata rows are collapsed to the existing, resolved attendance-question source ID before "
               "the daily merge. Shared companies and subsidiaries do not create duplicate outlet-days. "
               "Ambiguous attendance-question mappings remain excluded under the established pipeline. "
               "Raw missing histories are preserved; zeros used with missingness indicators exist only in "
               "the joint-model design matrix."),
          para("Data refresh", "SectionCustom"),
          para(f"The workbook at the pipeline path contains {len(read('changes'))} founding-year entries that differ "
               "from the processed metadata snapshot. Row names and metadata IDs were verified against "
               "the saved crosswalk before merging. Historical outcomes and the recorded-attendance sample "
               "are reused from the existing balance pipeline; this run does not re-extract source records."),
          para("The source metadata workbook's last-modified timestamp is " +
               escape(read("source_info")[0]["modified"]) +
               ". The copy found in Downloads also has the same founding-year values. "
               "A revised workbook must be supplied or saved to the pipeline path before this report "
               "can claim to include the newly added founding dates."),
          para("Sources", "SectionCustom"),
          para("newspaper_metadata.xlsx (Hoja1); mexican_newspapers.xlsx (Periodicos); "
               "the metadata-outcome crosswalk; saved 18-month attendance, question, contract and YouTube "
               "histories. Source checksums, full-precision estimates, sample data and models accompany "
               "the report in the analysis output directory.")]

def footer(canvas, doc):
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#65758b"))
    canvas.drawString(54, 30, "Post-lottery balance | All outlets | 18-month histories")
    canvas.drawRightString(558, 30, str(doc.page))

doc = SimpleDocTemplate(str(OUT), pagesize=(612, 792), leftMargin=54, rightMargin=54,
                        topMargin=48, bottomMargin=50)
doc.build(story, onFirstPage=footer, onLaterPages=footer)

def latex(selected, joint_row):
    lines = [r"\begin{tabular}{lrrrr}", r"\toprule",
             r"Covariate & Difference & 95\% CI & $p$-value & $N$ \\", r"\midrule"]
    for r in selected:
        name = label(r).replace("&", r"\&")
        p = "$<0.001$" if float(r["p_value"]) < .001 else pval(r["p_value"])
        lines.append(f"{name} & {num(r['estimate'])} & [{num(r['ci_low'])}, {num(r['ci_high'])}] & {p} & {integer(r['n'])} " + r"\\")
    ft = ftext(joint_row).replace("<", "$<$")
    lines += [r"\midrule", r"\multicolumn{5}{l}{Joint test: " + ft + r"} \\",
              r"\bottomrule", r"\end{tabular}"]
    return "\n".join(lines) + "\n"
for key in ("histories", "metadata", "combined"):
    chosen = rows if key == "combined" else [r for r in rows if (r["family"] == "Metadata") == (key == "metadata")]
    (TEX / f"balance_{key}.tex").write_text(latex(chosen, joint[key]))
print(OUT)

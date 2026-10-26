"""Readable PDF/HTML balance tables from the saved, validated estimates."""
import csv
import html
import json
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak

ROOT=Path(__file__).resolve().parents[3]
DATA=ROOT/'output/balance/sheinbaum_12m'
OUT=ROOT/'output/pdf/sheinbaum_balance_12m.pdf'

def read(name):
    with (DATA/f'{name}.csv').open() as f:return list(csv.DictReader(f))

rows=read('individual');joints=read('joint');flow={r['sample']:r for r in read('sample_flow')}
audit=json.loads((DATA/'build_audit.json').read_text())
assert len(rows)==42 and len(joints)==4 and all(r['status']=='Estimated' for r in rows)
fontdir=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/poppler/fonts'
pdfmetrics.registerFont(TTFont('BalanceSans',str(fontdir/'Ubuntu-R.ttf')))
pdfmetrics.registerFont(TTFont('BalanceSans-Bold',str(fontdir/'Ubuntu-B.ttf')))
pdfmetrics.registerFontFamily('BalanceSans',normal='BalanceSans',bold='BalanceSans-Bold')
styles=getSampleStyleSheet()
styles.add(ParagraphStyle('TitleLocal',fontName='BalanceSans-Bold',fontSize=20,leading=24,textColor=colors.HexColor('#18344c'),spaceAfter=15))
styles.add(ParagraphStyle('BodyLocal',fontName='BalanceSans',fontSize=10,leading=14,spaceAfter=10,textColor=colors.HexColor('#253247')))
styles.add(ParagraphStyle('HeadLocal',parent=styles['BodyLocal'],fontName='BalanceSans-Bold',fontSize=12,spaceBefore=8,spaceAfter=10))
styles.add(ParagraphStyle('SmallLocal',parent=styles['BodyLocal'],fontSize=8.5,leading=12))
styles.add(ParagraphStyle('CellLocal',fontName='BalanceSans',fontSize=8.5,leading=11))

def p(text,style='BodyLocal'):return Paragraph(text,styles[style])
def num(x):return f'{float(x):.3f}'
def pv(x):
    x=float(x)
    return '<0.0001' if x<.0001 else f'{x:.4f}'
def test(sample,block):return next(r for r in joints if r['sample']==sample and r['block']==block)
def ftest(r):
    value=pv(r["p_value"]); comparison=value if value.startswith("<") else "= "+value
    return f"F({r['df1']}, {r['df2']}) = {num(r['F'])}; p {comparison}"
def count(x):return f'{int(x):,}'
def table(data,widths):
    t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('FONTNAME',(0,0),(-1,-1),'BalanceSans'),('FONTNAME',(0,0),(-1,0),'BalanceSans-Bold'),
      ('FONTSIZE',(0,0),(-1,-1),8.5),('TEXTCOLOR',(0,0),(-1,0),colors.HexColor('#18344c')),
      ('ALIGN',(1,0),(-1,-1),'RIGHT'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
      ('LEFTPADDING',(0,0),(0,-1),0),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),
      ('LINEABOVE',(0,0),(-1,0),.8,colors.HexColor('#18344c')),('LINEBELOW',(0,0),(-1,0),.5,colors.grey),
      ('LINEBELOW',(0,-1),(-1,-1),.6,colors.HexColor('#18344c'))]))
    return t

story=[p('Sheinbaum: balance of speaking access','TitleLocal'),p('Recorded attendees | 12-month histories | October 26, 2026','HeadLocal'),
 p('This repeats the latest AMLO balance specification: nine metadata characteristics (excluding founding age) and twelve historical measures, tested as separate blocks. Individual regressions compare identified speakers with other attendees at the same conference; standard errors cluster by outlet.'),
 p('<b>Exposure:</b> an explicit outlet identification in the transcript. This is a proxy for speaking access, not an exhaustive indicator or count of questions. The completed full-corpus identity extraction is used; the separate question-answer extraction remains incomplete.'),
 p('<b>Attendance:</b> directly recorded REPORTERO/YOUTUBER entries only. No imputed presence or dated-affiliation-only links enter the main roster. Each canonical outlet contributes at most one observation per conference.'),
 p('Analysis window: October 1, 2024-June 15, 2025, using the user-specified lottery stopping date. Later attendance records are excluded from these estimates.','SmallLocal'),
 p('Samples','HeadLocal')]
sdata=[['Sample','Outlet-days','Outlets','Dates','Identified']]
for key,title in [('all_recorded','All recorded attendees'),('full','Metadata-linked balance'),('youtube_overlap','YouTube regression coverage')]:
    r=flow[key];sdata.append([p(title,'CellLocal'),count(r['n']),r['units'],r['dates'],count(r['identified_days'])])
story += [table(sdata,[208,85,65,60,86]),Spacer(1,12),p('Joint balance tests','HeadLocal')]
jdata=[['Sample / block','F statistic','p-value']]
for s,title in [('full','Full'),('youtube_overlap','YouTube coverage')]:
    for b in ['metadata','histories']:
        r=test(s,b);jdata.append([title+' / '+b,num(r['F']),pv(r['p_value'])])
story += [table(jdata,[285,110,109]),Spacer(1,12),
 p(f"The full balance sample spans {flow['full']['date_from']} to {flow['full']['date_to']}; the YouTube sample spans {flow['youtube_overlap']['date_from']} to {flow['youtube_overlap']['date_to']}. Both exclude dates with no identified/non-identified contrast in the applicable sample.",'SmallLocal'),
 p('Joint tests indicate observable differences; they do not establish a causal effect or test an observed seat assignment. Historical-block covariance is poorly conditioned because several YouTube totals and per-video measures are closely related. Those joint p-values should be read cautiously.','SmallLocal')]

html_parts=['<!doctype html><html lang="en"><meta charset="utf-8"><title>Sheinbaum balance</title><style>body{max-width:1100px;margin:40px auto;font:16px/1.5 system-ui;color:#253247}table{border-collapse:collapse;width:100%;margin:20px 0}th,td{text-align:right;padding:9px;border-bottom:1px solid #ddd}td:first-child,th:first-child{text-align:left}.note{background:#eef4f8;padding:18px}h1,h2{color:#18344c}</style>',
 '<h1>Sheinbaum: balance of speaking access</h1><p>Same nine metadata and twelve history measures as the latest AMLO balance; date fixed effects and outlet-clustered inference.</p>',
 '<div class="note">Explicit transcript identification is the speaking proxy, not an exhaustive question indicator. Only directly recorded REPORTERO/YOUTUBER attendees enter. YouTube outcomes now use the extended archives through 2026; the user-specified lottery-period cutoff limits this balance exercise to June 15, 2025.</div>',
 '<p><a href="../../pdf/sheinbaum_balance_12m.pdf">PDF tables</a></p>']
for s,title in [('full','Full attendance-period sample'),('youtube_overlap','YouTube outcome-coverage sample')]:
    r=flow[s]
    html_parts.append(f"<h2>{title}</h2><p>{count(r['n'])} outlet-days, {r['units']} outlets, {r['dates']} conferences, {count(r['identified_days'])} identified speaking days; {r['date_from']} through {r['date_to']}.</p>")
    for block in ['metadata','histories']:
        selected=[r for r in rows if r['sample']==s and (r['family']=='Metadata')==(block=='metadata')]
        jt=test(s,block)
        story += [PageBreak(),p(title,'TitleLocal'),p(('Metadata balance' if block=='metadata' else 'Historical balance'),'HeadLocal'),
          p(f"{count(flow[s]['n'])} outlet-days; {flow[s]['units']} outlets; {flow[s]['dates']} dates. Joint test: <b>{escape(ftest(jt))}</b>.")]
        data=[['Characteristic','Difference','95% CI','p-value','N','Outlets']]
        html_parts.append(f'<h3>{block.capitalize()}</h3><p>{html.escape(ftest(jt))}</p><table><tr>'+''.join(f'<th>{v}</th>' for v in data[0])+'</tr>')
        for r in selected:
            ci=f"[{num(r['ci_low'])}, {num(r['ci_high'])}]"
            label=r['label']+(' [log]' if r['transformation']=='log(1+x)' else '')
            vals=[label,num(r['estimate']),ci,pv(r['p_value']),count(r['n']),r['units']]
            data.append([p(escape(vals[0]),'CellLocal')]+vals[1:])
            html_parts.append('<tr>'+''.join(f'<td>{html.escape(v)}</td>' for v in vals)+'</tr>')
        html_parts.append('</table>')
        story += [table(data,[181,61,106,56,58,42]),Spacer(1,14),
          p('Individual regressions: characteristic = conference-date effects + coefficient x speaking identification. A positive difference means a higher characteristic among identified speakers. Individual p-values are unadjusted for multiple testing. Individual histories use available observations and informative dates; each row reports its own N.','SmallLocal')]
        if block=='metadata':
            story += [p('Binary coefficients are in proportion units: 0.10 means 10 percentage points. Format indicators can overlap. At the canonical outlet level a flag equals one if any linked metadata brand has it. Missing flags are zero under the existing AMLO convention; outlets with no metadata match are excluded entirely.','SmallLocal'),
            p('Geographic definitions repeat the earlier provisional coding: Mexico City means headquarters-state code 9; metropolitan-area coverage means an explicit metropolitan label for any metropolitan area. It is not specifically a Mexico City metro indicator. Metadata describe the current registry, not verified historical status. No age or history control enters this metadata model.','SmallLocal')]
        else:
            story += [p('All histories cover October 1, 2023-September 30, 2024. Prior access uses AMLO question counts divided by recorded attendance entries on dates covered by both sources. Ambiguous prior source pairs remain missing. It is a ratio of totals, not a speaking probability.','SmallLocal'),
            p('Contract and YouTube measures use log(1+x), without winsorization. Per-video histories divide window totals by the number of videos. Unknown histories remain missing. Joint models use zero placeholders plus distinct missingness indicators; the reported null excludes these indicators. No metadata covariates enter the history model.','SmallLocal'),
            p(f"Covariance correlation condition number: {float(jt['covariance_condition']):,.0f}. The joint history test is numerically sensitive to highly correlated predictors, despite independent calculation and centering checks. Missingness controls: {jt['missingness_controls']}.",'SmallLocal'),
            p('YouTube counters are archived cumulative engagement for videos published in the historical window, not engagement verified as measured before October 2024. Full uploads snapshots support archive zeros; capped uploads support only their recent interval. Curated playlists alone do not establish all-video coverage. Engagement balance is descriptive.','SmallLocal')]
html_parts += ['<p>Historical covariates: October 2023-September 2024. Log(1+x) for contracts and YouTube; raw prior-access ratio. Joint history tests use missingness indicators and have highly correlated predictors. Engagement snapshots were collected later, so they are not verified pre-treatment outcomes.</p>',
 '<p>CSV tables, source linkage, coverage, and missingness audits are saved alongside this report. No YouTube effect regression has yet been estimated.</p></html>']
(DATA/'index.html').write_text('\n'.join(html_parts))
OUT.parent.mkdir(parents=True,exist_ok=True)
def footer(canvas,doc):
    canvas.setFont('BalanceSans',8);canvas.setFillColor(colors.HexColor('#60778b'))
    canvas.drawString(54,28,'Sheinbaum balance | Identification proxy | Direct attendance')
    canvas.drawRightString(558,28,str(doc.page))
SimpleDocTemplate(str(OUT),pagesize=(612,792),leftMargin=54,rightMargin=54,topMargin=42,bottomMargin=45).build(story,onFirstPage=footer,onLaterPages=footer)
print(OUT)

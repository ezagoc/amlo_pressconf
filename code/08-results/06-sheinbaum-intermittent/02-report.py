"""Publish weekday FEct estimates and sample/assumption notes."""
import csv
import json
import sys
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from project_paths import media_path
DATA=media_path('results/sheinbaum/intermittent_did/five_weekdays_including_question')
OUT=ROOT/'output/pdf/sheinbaum_intermittent_did.pdf'
rows=[]
for path in sorted((DATA/'fect_1000').glob('results_*.csv')):
    with path.open() as f:rows.extend(csv.DictReader(f))
assert len(rows)==12 and all(int(r['valid_bootstraps'])==1000 for r in rows)
with (DATA/'fect_1000/results.csv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
a=json.loads((DATA/'build_audit.json').read_text())
fonts=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/poppler/fonts'
for name,file in [('FectSans','Ubuntu-R.ttf'),('FectSans-Bold','Ubuntu-B.ttf')]:pdfmetrics.registerFont(TTFont(name,str(fonts/file)))
pdfmetrics.registerFontFamily('FectSans',normal='FectSans',bold='FectSans-Bold')
styles=getSampleStyleSheet()
for name,font,size,leading in [('TitleF','FectSans-Bold',20,24),('BodyF','FectSans',10,14),('SmallF','FectSans',9,12),('CellF','FectSans',9,12)]:
    styles.add(ParagraphStyle(name,fontName=font,fontSize=size,leading=leading,spaceAfter=10 if name!='CellF' else 0,textColor=colors.HexColor('#253247')))
def p(t,s='BodyF'):return Paragraph(t,styles[s])
def f(v):return f'{float(v):.3f}'
def pv(v):return '&lt;0.001' if float(v)<.001 else f(v)
def table(data,widths):
    t=Table([[p(c,'CellF') for c in row] for row in data],colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),9),('LEFTPADDING',(0,0),(0,-1),0),('LINEABOVE',(0,0),(-1,0),.8,colors.HexColor('#18344c')),('LINEBELOW',(0,0),(-1,0),.5,colors.grey),('LINEBELOW',(0,-1),(-1,-1),.6,colors.HexColor('#18344c'))]))
    return t
labels={'videos':'Videos','interactions':'Total interactions','mean_interactions':'Interactions per video','likes':'Likes','comments':'Comments','views':'Views'}
story=[];html=['<!doctype html><html lang="en"><meta charset="utf-8"><title>Sheinbaum intermittent DiD</title><style>body{max-width:1000px;margin:40px auto;font:16px/1.5 system-ui;color:#253247}table{border-collapse:collapse;width:100%;margin:20px 0}td,th{text-align:left;padding:12px;border-bottom:1px solid #ccc}</style><h1>Sheinbaum: intermittent DiD</h1>']
summary=f"{a['analysis_rows']:,} outlet-days | {a['units']} outlets | {a['analysis_dates']} weekdays | {a['treated_cells']:,} treated cells. October 1, 2024-June 15, 2025 (last weekday: June 13)."
for model in ['History adjusted','Baseline']:
    if story:story.append(PageBreak())
    story += [p('Sheinbaum: intermittent DiD','TitleF'),p(f'<b>{model}</b> | Five weekdays including the speaking day'),p(summary,'SmallF')]
    html += [f'<h2>{model}</h2><p>{summary}</p>']
    data=[['<b>Outcome</b>','<b>ATT</b>','<b>Bootstrap SE</b>','<b>95% CI</b>','<b>p-value</b>']]
    for o,label in labels.items():
        r=next(r for r in rows if r['outcome']==o and r['model']==model)
        data.append([label,f(r['estimate']),f(r['se']),f"[{f(r['ci_low'])}, {f(r['ci_high'])}]",pv(r['p_value'])])
    story += [table(data,[160,65,85,130,64]),Spacer(1,15)]
    html += ['<table>'+''.join('<tr>'+''.join('<td>'+v+'</td>' for v in row)+'</tr>' for row in data)+'</table>']
    notes=[
      'Treatment equals one on the identified speaking day and the next four weekdays: Wednesday, Thursday, Friday, Monday, Tuesday. Weekends are omitted, and weekday holidays count. Overlapping windows form their union. ATT averages across treated outlet-days.',
      'FEct fits an outlet-and-date fixed-effects outcome model on untreated cells only, then imputes treated counterfactuals. Both models control for attendance (recorded presence OR identified speaking). The adjusted model adds prior AMLO question/attendance ratio and missingness interacted with quarter; all 125 outlets remain.',
      'Outcomes use asinh after pooled upper-p99 capping. Interactions = likes + comments; interactions per video uses all recovered videos, with zero when none. Coefficients are transformed-outcome differences, not direct percentages.',
      'Inference: 1,000 ordinary outlet-bootstrap draws per model; package normal-approximation 95% intervals and two-sided p-values using bootstrap SEs. These are not wild-bootstrap p-values. No adjustment for the six outcome tests.',
      'The ballot exclusion rule and five-weekday horizon are assumptions. This first specification does not yet establish parallel untreated outcomes, no anticipation, or no effects continuing after day five. Attendance conditioning can also alter the total-effect interpretation if treatment changes attendance.'
    ]
    for note in notes:story.append(p(note,'SmallF'));html.append('<p>'+note+'</p>')
story += [PageBreak(),p('Sample and validation','TitleF')];html.append('<h2>Sample and validation</h2>')
notes=[
 f"The source grid contains {a['full_rows']:,} daily observations (125 outlets x 258 calendar days). Removing {a['weekend_cells']:,} weekend cells leaves 23,000 weekday cells. Five unsupported weekdays remove another 625 cells, yielding {a['analysis_rows']:,}. All {a['zero_video_cells']:,} zero-video observations in this sample are retained.",
 'The May 2, 2025 transcript is missing. Exposure is therefore unknown for 547 cells on May 2, 5, 6, 7 and 8. The other 78 cells on those dates are known treated, but there are no known untreated controls to estimate their date fixed effects. All five dates are excluded. Treatment windows are constructed first, so these omissions never shorten the five-weekday clock.',
 'There are 736 identified speaking events in the source period (717 on estimation dates), 78 ever-treated outlets, and 47 never-treated outlets. Seventy outlets have a measured prior AMLO question/attendance ratio. Missing histories retain their outlets through explicit missingness controls.',
 'Forty-nine events occur before a previous five-weekday window ends. They remain in the data, extending the union of treatment windows. Their dated audit is saved for later checking of the ballot rule. Twenty-two windows reach the cutoff before five weekdays elapse; no post-lottery observations are added.',
 'YouTube outcomes reproduce the original daily construction. No day is dropped because there are no recovered videos or likes. Saved engagement counters are cumulative snapshots attached to video publication dates; they do not measure engagement accrued that day. Speaking is the current transcript-identification proxy.',
 'Validation: the treatment indicator is checked against an independent expansion of event dates; source outcome sums are unchanged. Each of the twelve FEct fits matches an independent untreated-only regression imputation and attendance coefficient, uses the exact intended sample, and has 1,000 finite bootstrap draws. Checkpoints save exact inputs and source hashes.',
 'Next identification checks: event-time patterns, held-out placebo tests, persistence beyond the five-weekday window, and the repeated-speaking exceptions. The present output is the initial pooled specification, before those checks.',
 'Method reference: <link href="https://yiqingxu.org/packages/fect/02-fect.html" color="#1565a0">Official FEct manual</link>. Code follows the existing AMLO full-calendar FEct pipeline. Generated October 26, 2026.'
]
for note in notes:story.append(p(note,'BodyF'));html.append('<p>'+note+'</p>')
(DATA/'index.html').write_text('\n'.join(html)+'</html>')
def footer(canvas,doc):
    canvas.setFont('FectSans',8);canvas.setFillColor(colors.HexColor('#60778b'))
    canvas.drawString(54,28,'Sheinbaum | FEct | Five-weekday exposure | 1,000 outlet bootstrap draws')
    canvas.drawRightString(558,28,str(doc.page))
OUT.parent.mkdir(parents=True,exist_ok=True)
SimpleDocTemplate(str(OUT),pagesize=(612,792),leftMargin=54,rightMargin=54,topMargin=42,bottomMargin=45).build(story,onFirstPage=footer,onLaterPages=footer)
print(OUT)

"""Export verified Sheinbaum pooled regressions, preserving model-specific inference."""
import csv
import html
import sys
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from project_paths import media_path
DATA=media_path('results/sheinbaum/main_results/lottery-through-2025-06-15')
OUT=ROOT/'output/pdf/sheinbaum_main_results.pdf'
def read(name):
    with (DATA/f'{name}.csv').open() as f:return list(csv.DictReader(f))
rows=read('regression_results');sample=read('sample_summary')[0];cuts=read('winsorization_cutoffs')
assert len(rows)==24 and len(read('wild_bootstrap_audit'))==12
fonts=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/poppler/fonts'
for name,file in [('MainSans','Ubuntu-R.ttf'),('MainSans-Bold','Ubuntu-B.ttf')]:
    pdfmetrics.registerFont(TTFont(name,str(fonts/file)))
pdfmetrics.registerFontFamily('MainSans',normal='MainSans',bold='MainSans-Bold')
styles=getSampleStyleSheet()
styles.add(ParagraphStyle('TitleMain',fontName='MainSans-Bold',fontSize=20,leading=24,spaceAfter=14,textColor=colors.HexColor('#18344c')))
styles.add(ParagraphStyle('BodyMain',fontName='MainSans',fontSize=10,leading=14,spaceAfter=11,textColor=colors.HexColor('#253247')))
styles.add(ParagraphStyle('SmallMain',parent=styles['BodyMain'],fontSize=8.5,leading=12,spaceAfter=9))
styles.add(ParagraphStyle('CellMain',parent=styles['SmallMain'],spaceAfter=0,fontSize=8,leading=11))
styles.add(ParagraphStyle('CenterMain',parent=styles['CellMain'],alignment=1))
def p(t,style='BodyMain'):return Paragraph(t,styles[style])
def fmt(v):return f'{float(v):.3f}'
def pv(v):return '&lt;0.001' if float(v)<.001 else f'{float(v):.3f}'
def find(variant,outcome,model):return next(r for r in rows if r['variant']==variant and r['outcome']==outcome and r['model']==model)
labels={'videos':'Videos','interactions':'Total interactions','mean_interactions':'Interactions per video','likes':'Likes','comments':'Comments','views':'Views'}
def table(data,widths):
    t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10),
      ('LEFTPADDING',(0,0),(0,-1),0),('LINEABOVE',(0,0),(-1,0),.8,colors.HexColor('#18344c')),
      ('LINEBELOW',(0,0),(-1,0),.5,colors.grey),('LINEBELOW',(0,-1),(-1,-1),.6,colors.HexColor('#18344c'))]))
    return t
story=[]
htmlparts=['<!doctype html><html lang="en"><meta charset="utf-8"><title>Sheinbaum main results</title><style>body{max-width:1100px;margin:40px auto;font:16px/1.5 system-ui;color:#253247}table{border-collapse:collapse;width:100%;margin:20px 0}th,td{padding:12px;text-align:right;border-bottom:1px solid #ddd}th:first-child,td:first-child{text-align:left}h1,h2{color:#18344c}</style><h1>Sheinbaum: daily YouTube outcomes</h1>']
for variant,title in [('winsor99_log1p','Main results'),('raw_log1p','Sensitivity: no winsorization')]:
    if story:story.append(PageBreak())
    story+=[p('Sheinbaum: daily YouTube outcomes','TitleMain'),p(f'<b>{title}</b> | Identified speaking days | October 26, 2026')]
    summary=f"{int(sample['n']):,} recorded-attendee outlet-days; {sample['units']} outlets; {sample['dates']} conference dates. {sample['speaking_days']} identified speaking days and {int(sample['zero_video_days']):,} zero-video days retained. Dates: {sample['date_from']} to {sample['date_to']}."
    story.append(p(summary,'SmallMain'));htmlparts.append(f'<h2>{title}</h2><p>{summary}</p>')
    if variant=='winsor99_log1p':
        story.append(p('All six estimates are positive. None of the history-adjusted tests rejects zero at 5%. Views are the closest: adjusted coefficient 0.194, clustered p = 0.058, wild-bootstrap p = 0.063. The baseline views result is marginal (wild p = 0.049).'))
        headers=['Outcome','Baseline<br/>coef. (SE)','Cluster<br/>p','Wild<br/>p','Adjusted<br/>coef. (SE)','Cluster<br/>p','Wild<br/>p']
        widths=[120,82,42,42,82,42,42]
    else:
        story.append(p('Removing the upper-p99 caps leaves the estimates and inference almost unchanged. This sensitivity reports outlet-clustered inference; wild-bootstrap tests were run for the main capped specification only.'))
        headers=['Outcome','Baseline<br/>coefficient [95% CI]','Cluster p','Adjusted<br/>coefficient [95% CI]','Cluster p']
        widths=[110,151,45,151,45]
    data=[[p('<b>'+h+'</b>','CellMain' if i==0 else 'CenterMain') for i,h in enumerate(headers)]]
    htmlparts.append('<table><tr>'+''.join('<th>'+h+'</th>' for h in headers)+'</tr>')
    for outcome,label in labels.items():
        b=find(variant,outcome,'Baseline');a=find(variant,outcome,'History adjusted')
        if variant=='winsor99_log1p':
            values=[label,f"{fmt(b['estimate'])}<br/>({fmt(b['se'])})",pv(b['p_value']),pv(b['wild_p']),f"{fmt(a['estimate'])}<br/>({fmt(a['se'])})",pv(a['p_value']),pv(a['wild_p'])]
        else:
            values=[label,f"{fmt(b['estimate'])} [{fmt(b['ci_low'])}, {fmt(b['ci_high'])}]",pv(b['p_value']),f"{fmt(a['estimate'])} [{fmt(a['ci_low'])}, {fmt(a['ci_high'])}]",pv(a['p_value'])]
        data.append([p(v,'CellMain' if i==0 else 'CenterMain') for i,v in enumerate(values)])
        htmlparts.append('<tr>'+''.join('<td>'+v+'</td>' for v in values)+'</tr>')
    story += [table(data,widths),Spacer(1,14)]
    htmlparts.append('</table>')
    notes=[
      'Both models include outlet and conference-date fixed effects. Adjusted models additionally interact the October 2023-September 2024 AMLO question/attendance ratio and its missingness indicator with calendar quarters, omitting 2024Q4. These are the same history controls as the AMLO main specification.',
      'Outcomes cover all recovered videos published on that date. Interactions = likes + comments; mean interactions = interactions / videos, zero on no-video days. The original balanced daily sum-and-zero-fill construction is retained.',
      ('Each raw outcome is capped at the pooled estimation-sample 99th percentile (R type 7), then log(1+x). SEs cluster by outlet. Wild p-values use 9,999 null-imposed outlet Rademacher bootstrap draws, matching the AMLO settings.' if variant=='winsor99_log1p' else 'Outcomes use log(1+x), without caps. All baseline, adjusted, capped and uncapped models use exactly the same observations. Two singleton outlets (two rows) are removed by the fixed-effect estimator; no row is removed because it has zero videos.'),
      'Exposure is explicit outlet identification in the transcript, a proxy for speaking access, not exhaustive question coding. These are conditional associations; the balance tests found observable selection. Engagement is cumulative archived engagement attached to publication dates, not engagement accrued that day. Coefficients are in transformed-outcome units, not automatically percentage changes. P-values are unadjusted across six outcomes.'
    ]
    for note in notes:story.append(p(note,'SmallMain'));htmlparts.append('<p>'+note+'</p>')
    if variant=='raw_log1p':
        caps='; '.join(f"{labels[r['outcome']]}: {float(r['upper']):,.2f}" for r in cuts)
        story.append(p('<b>Main-model upper-p99 caps:</b> '+caps+'.','SmallMain'))
htmlparts.append('</html>')
(DATA/'index.html').write_text('\n'.join(htmlparts))
OUT.parent.mkdir(parents=True,exist_ok=True)
def footer(canvas,doc):
    canvas.setFont('MainSans',8);canvas.setFillColor(colors.HexColor('#60778b'))
    canvas.drawString(54,28,'Sheinbaum | Daily recorded attendees | Pooled same-day models')
    canvas.drawRightString(558,28,str(doc.page))
SimpleDocTemplate(str(OUT),pagesize=(612,792),leftMargin=54,rightMargin=54,topMargin=42,bottomMargin=45).build(story,onFirstPage=footer,onLaterPages=footer)
print(OUT)

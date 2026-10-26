"""Alignment interaction results, direct gap tests and classification exclusions."""
import csv
import sys
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from project_paths import media_path
DATA=media_path('results/sheinbaum/main_results/lottery-through-2025-06-15/pooled_interactions_combined')
OUT=ROOT/'output/pdf/sheinbaum_heterogeneity.pdf'
def read(n):
    with (DATA/f'{n}.csv').open() as f:return list(csv.DictReader(f))
rows=read('results');groups=read('group_sample_sizes');flow=read('sample_flow');audit=read('classification_audit')
assert len(rows)==36 and len(read('wild_bootstrap_audit'))==36
fonts=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/poppler/fonts'
for name,file in [('HetSans','Ubuntu-R.ttf'),('HetSans-Bold','Ubuntu-B.ttf')]:pdfmetrics.registerFont(TTFont(name,str(fonts/file)))
pdfmetrics.registerFontFamily('HetSans',normal='HetSans',bold='HetSans-Bold')
styles=getSampleStyleSheet()
for name,font,size,leading in [('HTitle','HetSans-Bold',20,24),('HBody','HetSans',10,14),('HSmall','HetSans',8.5,12),('HCell','HetSans',8,11)]:
    styles.add(ParagraphStyle(name,fontName=font,fontSize=size,leading=leading,spaceAfter=10 if name!='HCell' else 0,textColor=colors.HexColor('#253247')))
styles.add(ParagraphStyle('HCenter',parent=styles['HCell'],alignment=1))
def p(t,s='HBody'):return Paragraph(t,styles[s])
def f(v):return f'{float(v):.3f}'
def pv(v):return '&lt;0.001' if float(v)<.001 else f(v)
def table(data,widths,padding=9):
    t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(0,-1),0),
      ('TOPPADDING',(0,0),(-1,-1),padding),('BOTTOMPADDING',(0,0),(-1,-1),padding),
      ('LINEABOVE',(0,0),(-1,0),.8,colors.HexColor('#18344c')),('LINEBELOW',(0,0),(-1,0),.5,colors.grey),
      ('LINEBELOW',(0,-1),(-1,-1),.6,colors.HexColor('#18344c'))]))
    return t
labels={'videos':'Videos','interactions':'Total interactions','mean_interactions':'Interactions per video','likes':'Likes','comments':'Comments','views':'Views'}
last=flow[-1];story=[]
html=['<!doctype html><html lang="en"><meta charset="utf-8"><title>Sheinbaum alignment heterogeneity</title><style>body{max-width:1150px;margin:40px auto;font:16px/1.5 system-ui;color:#253247}table{border-collapse:collapse;width:100%;margin:20px 0}th,td{padding:10px;text-align:right;border-bottom:1px solid #ddd}th:first-child,td:first-child{text-align:left}</style><h1>Sheinbaum: alignment heterogeneity</h1>']
for model in ['History adjusted','Baseline']:
    if story:story.append(PageBreak())
    story += [p('Sheinbaum: alignment heterogeneity','HTitle'),p(f'<b>{model}</b> | Pooled speaking-by-alignment interactions | October 26, 2026')]
    summary=f"{int(last['n']):,} outlet-days; {last['units']} outlets; {last['dates']} conference dates. Aligned: 30 outlets / 296 speaking days. Opposition + independent: 50 outlets / 287 speaking days. All {int(last['zero_video_days']):,} zero-video days in this sample are retained."
    story.append(p(summary,'HSmall'));html.append(f'<h2>{model}</h2><p>{summary}</p>')
    if model=='History adjusted':
        gap=[r for r in rows if r['model']==model and r['label'].startswith('Aligned -')]
        min_p=min(float(r['wild_p']) for r in gap)
        story.append(p(f'There is no statistically detectable difference between the groups for any outcome (smallest wild-bootstrap p = {min_p:.3f}). This is not evidence that their effects are identical; the estimates are imprecise.'))
    headers=['Outcome','Opp. + Indep.<br/>coef. (SE)','Wild p','Aligned<br/>coef. (SE)','Wild p','Aligned minus<br/>Opp. + Indep.','Wild p']
    data=[[p('<b>'+h+'</b>','HCell' if i==0 else 'HCenter') for i,h in enumerate(headers)]]
    html.append('<table><tr>'+''.join('<th>'+h+'</th>' for h in headers)+'</tr>')
    for outcome,label in labels.items():
        vals=[label]
        for group in ['Opp. + Independent','Aligned','Aligned - (Opp. + Independent)']:
            r=next(r for r in rows if r['outcome']==outcome and r['model']==model and r['label']==group)
            vals += [f"{f(r['estimate'])}<br/>({f(r['se'])})",pv(r['wild_p'])]
        data.append([p(v,'HCell' if i==0 else 'HCenter') for i,v in enumerate(vals)])
        html.append('<tr>'+''.join('<td>'+v+'</td>' for v in vals)+'</tr>')
    story += [table(data,[110,85,40,85,40,90,40]),Spacer(1,14)];html.append('</table>')
    notes=[
      'One pooled model per outcome, with speaking identification and speaking x aligned. Both groups share conference-date effects and history slopes; outlet fixed effects are included. The first two effects are the group slopes, and the last is their directly tested difference. Group significance alone is not a heterogeneity test.',
      'History adjustment follows AMLO: prior-year AMLO questions / recorded attendance and its missingness indicator interacted with 2025Q1 and 2025Q2, omitting 2024Q4. The baseline omits those controls. All twelve fits use identical rows.',
      'All six raw daily outcomes use the same pooled-main-sample upper-p99 caps, then log(1+x). Interactions = likes + comments; mean interactions divides by all recovered videos, zero on no-video days. Archive completeness does not filter observations. These are transformed-outcome coefficients, not direct percentages.',
      'SEs cluster by outlet. Wild p-values use 9,999 null-imposed outlet Rademacher draws per group effect and difference, matching AMLO. Tests are two-sided and unadjusted across outcomes. All group effects and SEs were checked against equivalent direct-slope models.',
      'Alignment uses the existing 4T registry classification. The original AMLO label Independent corresponds to the registry code unclear; it does not establish political neutrality. Missing or conflicting linked-brand codes are excluded (see classification audit). Exposure is a transcript-identification proxy, and engagement is later cumulative snapshots. Interpret as conditional associations.'
    ]
    for note in notes:story.append(p(note,'HSmall'));html.append('<p>'+note+'</p>')
story += [PageBreak(),p('Classification and sample audit','HTitle'),p('Analysis window: October 1, 2024-June 15, 2025. Current registry classifications are fixed across the period; they have not been re-estimated for Sheinbaum.','HSmall')]
fd=[[p('<b>'+v+'</b>','HCell') for v in ['Stage','Rows','Outlets','Dates']]]
for r in flow:fd.append([p(r['stage'],'HCell'),p(f"{int(r['n']):,}",'HCenter'),p(r['units'],'HCenter'),p(r['dates'],'HCenter')])
story += [table(fd,[290,80,65,65],padding=6),Spacer(1,13),p('<b>Excluded classifications</b>')]
ex=[r for r in audit if r['group'] in ('','NA')]
assert len(ex)==14
data=[[p('<b>'+v+'</b>','HCell') for v in ['Canonical outlet','Linked-brand codes','Reason']]]
html.append('<h2>Excluded classifications</h2><table><tr><th>Outlet</th><th>Codes</th><th>Reason</th></tr>')
for r in ex:
    code=r['codes'] if r['codes'] not in ('','NA') else 'Missing'
    reason='Missing' if code=='Missing' else 'Conflict'
    vals=[r['unit_id'],code,reason]
    data.append([p(escape(v),'HCell') for v in vals]);html.append('<tr>'+''.join('<td>'+escape(v)+'</td>' for v in vals)+'</tr>')
story += [table(data,[250,160,90],padding=5),Spacer(1,12),p('Eight outlets lack a classification and six have conflicting linked-brand codes. After their exclusion, two dates lack within-date speaking variation and are omitted (67 rows); no additional singleton outlets are removed. No exclusions depend on positive video output. Brand assignments were not changed.','HSmall')]
html.append('</table></html>');(DATA/'index.html').write_text('\n'.join(html))
def footer(canvas,doc):
    canvas.setFont('HetSans',8);canvas.setFillColor(colors.HexColor('#60778b'))
    canvas.drawString(54,28,'Sheinbaum | Pooled alignment interactions | Daily recorded attendees')
    canvas.drawRightString(558,28,str(doc.page))
SimpleDocTemplate(str(OUT),pagesize=(612,792),leftMargin=54,rightMargin=54,topMargin=42,bottomMargin=45).build(story,onFirstPage=footer,onLaterPages=footer)
print(OUT)

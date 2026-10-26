"""Research report: held-out pre-treatment/carryover and paired FEct heterogeneity."""
import csv,json,sys
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from project_paths import media_path
DATA=media_path('results/sheinbaum/intermittent_did/five_weekdays_including_question/diagnostics_heterogeneity')
OUT=ROOT/'output/pdf/sheinbaum_intermittent_diagnostics_heterogeneity.pdf'
def read(name):
    with (DATA/(name+'.csv')).open() as f:return list(csv.DictReader(f))
diag=read('diagnostics_results_1000');het=read('heterogeneity_results_1000');joint=read('diagnostics_joint_tests_1000');bands=read('diagnostics_bands_1000')
audit=json.loads((DATA/'build_audit.json').read_text());targets=read('target_counts');classes=read('classification_audit')
assert len(diag)==90 and len(het)==72 and len(joint)==12
assert all(int(x['valid_draws'])==1000 for x in diag+het)
labels={'videos':'Videos','interactions':'Total interactions','mean_interactions':'Interactions per video','likes':'Likes','comments':'Comments','views':'Views'}
fonts=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/poppler/fonts'
for n,f in [('DSans','Ubuntu-R.ttf'),('DSans-Bold','Ubuntu-B.ttf')]:pdfmetrics.registerFont(TTFont(n,str(fonts/f)))
pdfmetrics.registerFontFamily('DSans',normal='DSans',bold='DSans-Bold')
styles=getSampleStyleSheet()
for name,font,size,lead in [('T','DSans-Bold',19,23),('B','DSans',10,14),('S','DSans',9,12),('C','DSans',8.5,11)]:styles.add(ParagraphStyle(name,fontName=font,fontSize=size,leading=lead,spaceAfter=9 if name!='C' else 0,textColor=colors.HexColor('#253247')))
def p(t,s='B'):return Paragraph(t,styles[s])
def num(v):return f'{float(v):.3f}'
def pv(v):return '&lt;0.001' if float(v)<.001 else num(v)
def get(rows,stat,o):return next(r for r in rows if r['statistic']==stat and r['outcome']==o)
def table(data,widths):
    t=Table([[p(v,'C') for v in row] for row in data],colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(0,-1),0),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),('LINEABOVE',(0,0),(-1,0),.8,colors.HexColor('#18344c')),('LINEBELOW',(0,0),(-1,0),.5,colors.grey),('LINEBELOW',(0,-1),(-1,-1),.6,colors.HexColor('#18344c'))]))
    return t
html=['<!doctype html><html lang="en"><meta charset="utf-8"><title>Sheinbaum diagnostics and heterogeneity</title><style>body{max-width:1100px;margin:40px auto;font:16px/1.5 system-ui;color:#253247}table{border-collapse:collapse;width:100%;margin:20px 0}td{padding:10px;border-bottom:1px solid #ddd}img{width:100%}</style><h1>Sheinbaum: diagnostics and heterogeneity</h1>']
story=[]
def text(t,s='B'):story.append(p(t,s));html.append('<p>'+t+'</p>')
def addtable(data,widths):story.append(table(data,widths));html.append('<table>'+''.join('<tr>'+''.join('<td>'+v+'</td>' for v in row)+'</tr>' for row in data)+'</table>')
text('Pre-treatment and carryover','T')
text('Five-weekday treatment | October 1, 2024-June 15, 2025 | History-adjusted diagnostics','S')
pre_reject=sum(float(r['joint_p'])<.05 for r in joint if r['test']=='pre');post_reject=sum(float(r['joint_p'])<.05 for r in joint if r['test']=='post')
text(f'The joint five-day tests reject zero pre-treatment deviations for {pre_reject} of six outcomes and zero carryover deviations for {post_reject} of six. These checks do not establish the assumptions of the original causal interpretation; a non-rejection is not evidence of equivalence.')
data=[['<b>Outcome</b>','<b>Pre<br/>average</b>','<b>Avg. p</b>','<b>Joint p</b>','<b>Post<br/>average</b>','<b>Avg. p</b>','<b>Joint p</b>']]
for o,label in labels.items():
    a=get(diag,'pre_average',o);b=get(diag,'post_average',o);jp=next(r for r in joint if r['test']=='pre' and r['outcome']==o);jc=next(r for r in joint if r['test']=='post' and r['outcome']==o)
    data.append([label,num(a['estimate']),pv(a['p_value']),pv(jp['joint_p']),num(b['estimate']),pv(b['p_value']),pv(jc['joint_p'])])
addtable(data,[128,58,45,55,58,45,55]);story.append(Spacer(1,14))
for t in [
 'Pre = weekdays -5 through -1 before a known 0-to-1 treatment transition. Post = the first five untreated weekdays after a known 1-to-0 transition. Extended or overlapping treatment windows are treated as one spell. Time uses the original weekday index; the May transcript gap is never compressed.',
 'The outcome model is fitted on untreated observations outside BOTH diagnostic windows. Tested observations never fit their own counterfactual. Days belonging to both windows are excluded from diagnostic targets as ambiguous, but remain held out of fitting. All six transformed outcomes retain the original pooled p99 caps.',
 'Diagnostic sample: 122 outlets, 21,838 weekday cells, 14,531 training cells. Avan Noticias, Healy and NX Noticias lack five clean untreated observations and are excluded here. The original heterogeneity analysis retains them. Pre targets cover 1,667 cells; carryover targets cover 1,557 cells. Counts and outlet composition vary by event time.',
 'Inference uses 1,000 ordinary outlet bootstrap draws, refitting the outcome model each time. Average p-values use bootstrap SEs and a normal approximation. Joint p-values use a centered bootstrap maximum-t statistic across the five days of each outcome. Plotted simultaneous bands control across those five days; there is no correction across six outcomes.',
 'Positive pre-treatment gaps can reflect anticipation, selection into speaking or misspecified counterfactual outcomes. Positive post-treatment gaps can reflect persistence or the same misspecification. The two diagnostics cannot distinguish these explanations. The ballot exclusion rule alone does not resolve them.'
]:text(t,'S')
figdir=DATA/'figures'
for typ,title in [('pre','Pre-treatment: held-out prediction errors'),('post','Carryover: held-out prediction errors')]:
    path=figdir/f'{typ}.png'
    assert path.exists(), 'Run 05-plot-diagnostics.py first'
    story += [PageBreak(),p(title,'T'),p('History adjusted | Entire pre/post window held out of model fitting','S'),Image(str(path),width=504,height=529),Spacer(1,9)]
    text('Shaded bands are simultaneous across the five displayed days for each outcome; vertical bars are pointwise 95% intervals. The zero line is the no-deviation benchmark. Event-time composition is not balanced across days.','S')
    html.append(f'<h2>{title}</h2><img src="figures/{typ}.png">')
story.append(PageBreak());text('Alignment heterogeneity','T')
text('Original five-weekday specification | 106 classified outlets: 33 aligned, 73 opposition + independent','S')
for model,title in [('adjusted','History adjusted'),('baseline','Baseline')]:
    text('<b>'+title+'</b>','S');data=[['<b>Outcome</b>','<b>Aligned<br/>ATT (SE)</b>','<b>Opp. + Indep.<br/>ATT (SE)</b>','<b>Difference<br/>95% CI</b>','<b>Gap p</b>']]
    for o,label in labels.items():
        a=get(het,f'{model}:original:aligned',o);b=get(het,f'{model}:original:comparison',o);g=get(het,f'{model}:original:difference',o)
        data.append([label,f"{num(a['estimate'])} ({num(a['se'])})",f"{num(b['estimate'])} ({num(b['se'])})",f"{num(g['estimate'])}<br/>[{num(g['ci_low'])}, {num(g['ci_high'])}]",pv(g['p_value'])])
    addtable(data,[122,92,102,132,50]);story.append(Spacer(1,12))
text('The two groups share an untreated-only outlet/date FE model and attendance control; adjustment adds the prior-AMLO histories. Effects are group-specific means of treated prediction errors. The gap is directly recomputed in every paired bootstrap draw. Resampling is by outlet within alignment group, preserving group sizes.','S')
text('Nineteen missing or conflicting classifications are excluded. Independent retains the original registry meaning (unclear), not verified political neutrality. Coefficients are transformed differences, not percentages. Heterogeneity does not repair the diagnostic failures.','S')
story.append(PageBreak());text('Sensitivity to the untreated training sample','T')
text('The alternative holds out both diagnostic windows. It is a sensitivity exercise, not a correction that establishes causality.','S')
text('<b>Pooled, history adjusted: same 122-outlet sample</b>','S')
data=[['<b>Outcome</b>','<b>Original<br/>training ATT</b>','<b>Held-out<br/>training ATT</b>','<b>Change<br/>95% CI</b>','<b>Change p</b>']]
for o,label in labels.items():
    a=get(diag,'att_original_matched',o);b=get(diag,'att_clean',o);g=get(diag,'att_clean_minus_original',o)
    data.append([label,num(a['estimate']),num(b['estimate']),f"{num(g['estimate'])}<br/>[{num(g['ci_low'])}, {num(g['ci_high'])}]",pv(g['p_value'])])
addtable(data,[122,92,102,132,50]);story.append(Spacer(1,14))
text('<b>Held-out training: adjusted heterogeneity, 103 outlets</b>','S')
data=[['<b>Outcome</b>','<b>Aligned<br/>ATT (SE)</b>','<b>Opp. + Indep.<br/>ATT (SE)</b>','<b>Difference<br/>95% CI</b>','<b>Gap p</b>']]
for o,label in labels.items():
    a=get(het,'adjusted:clean:aligned',o);b=get(het,'adjusted:clean:comparison',o);g=get(het,'adjusted:clean:difference',o)
    data.append([label,f"{num(a['estimate'])} ({num(a['se'])})",f"{num(b['estimate'])} ({num(b['se'])})",f"{num(g['estimate'])}<br/>[{num(g['ci_low'])}, {num(g['ci_high'])}]",pv(g['p_value'])])
addtable(data,[122,92,102,132,50]);story.append(Spacer(1,12))
text('The sensitivity group sample is 32 aligned and 71 comparison outlets. Its composition differs from the original 106-outlet heterogeneity sample. The pooled comparison above holds the 122-outlet sample fixed. No-video days remain in every sample. Engagement uses saved cumulative counters for videos published that day, not engagement accrued that day.','S')
text('Validation: all original adjusted FEct points reproduced independently; 1,000 finite paired draws per analysis; group gaps verified draw by draw; explicit cluster replication matches frequency-weighted resampling. The weekday labels preserve unknown dates and overlapping spells. <link href="https://yiqingxu.org/packages/fect/02-fect.html" color="#1565a0">Method reference: FEct manual</link>. Generated October 26, 2026.','S')
def footer(c,doc):
    c.setFont('DSans',8);c.setFillColor(colors.HexColor('#60778b'));c.drawString(54,27,'Sheinbaum | Held-out diagnostics and alignment heterogeneity | Five weekdays');c.drawRightString(558,27,str(doc.page))
SimpleDocTemplate(str(OUT),pagesize=(612,792),leftMargin=54,rightMargin=54,topMargin=40,bottomMargin=43).build(story,onFirstPage=footer,onLaterPages=footer)
(DATA/'index.html').write_text('\n'.join(html)+'</html>');print(OUT)

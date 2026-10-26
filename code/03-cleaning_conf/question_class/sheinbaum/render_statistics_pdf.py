"""Render report_statistics.py outputs with ReportLab (no external services)."""
from pathlib import Path
import json
from html import escape
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor, white
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader

ROOT=Path('tmp/pdfs/sheinbaum'); S=json.loads((ROOT/'statistics.json').read_text())
OUT=Path('output/pdf/sheinbaum_questions_journalists_statistics.pdf');OUT.parent.mkdir(parents=True,exist_ok=True)
F=Path('/Users/ezagoc/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/libreoffice-headless/libreoffice/LibreOfficeDev.app/Contents/Resources/fonts/truetype')
pdfmetrics.registerFont(TTFont('DejaVu',str(F/'DejaVuSans.ttf')))
pdfmetrics.registerFont(TTFont('DejaVu-Bold',str(F/'DejaVuSans-Bold.ttf')))
pdfmetrics.registerFontFamily('DejaVu',normal='DejaVu',bold='DejaVu-Bold')
NAVY=HexColor('#173347');TEAL=HexColor('#008577');MUTED=HexColor('#617583');LIGHT=HexColor('#EAF2F3');GOLD=HexColor('#D49937')
c=canvas.Canvas(str(OUT),pagesize=(612,792));c.setTitle('Sheinbaum mañaneras | Questions, journalists and media');c.setAuthor('Analysis of NOSTRODATA transcripts')
style=ParagraphStyle('body',fontName='DejaVu',fontSize=10,leading=15,textColor=NAVY)
small=ParagraphStyle('small',parent=style,fontSize=8.6,leading=12)

def para(text,y,x=42,w=528,sty=style):
 p=Paragraph(text,sty);_,h=p.wrap(w,700);p.drawOn(c,x,y-h);return y-h

def title(num,kicker,heading,sub):
 c.setFillColor(TEAL);c.rect(0,782,612,10,fill=1,stroke=0)
 c.setFont('DejaVu-Bold',9);c.drawString(42,746,kicker.upper())
 c.setFillColor(NAVY);c.setFont('DejaVu-Bold',23);c.drawString(42,710,heading)
 para(sub,691,sty=small)
 c.setStrokeColor(LIGHT);c.line(42,44,570,44)
 c.setFont('DejaVu',8);c.setFillColor(MUTED);c.drawString(42,28,'SHEINBAUM MAÑANERAS  |  02 OCT 2024 - 22 AUG 2025')
 c.drawRightString(570,28,f'{num} / 7')

def section(text,y):
 c.setFillColor(NAVY);c.setFont('DejaVu-Bold',12);c.drawString(42,y,text)

def image(name,x,y,w,h):
 im=ImageReader(str(ROOT/f'{name}.png'));iw,ih=im.getSize();scale=min(w/iw,h/ih)
 c.drawImage(im,x+(w-iw*scale)/2,y+(h-ih*scale)/2,width=iw*scale,height=ih*scale,mask='auto')

def table(rows,y,widths,fontsize=9):
 cell=ParagraphStyle('cell',parent=small,fontSize=fontsize,leading=fontsize+3)
 data=[[Paragraph(escape(str(v)),cell) for v in row] for row in rows]
 t=Table(data,colWidths=widths,hAlign='LEFT')
 t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),LIGHT),('FONTNAME',(0,0),(-1,0),'DejaVu-Bold'),
 ('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),
 ('LINEBELOW',(0,0),(-1,0),1,TEAL),('LINEBELOW',(0,1),(-1,-1),.35,LIGHT)]))
 _,h=t.wrap(528,700);t.drawOn(c,42,y-h);return y-h

def callout(text,y,height=64):
 c.setFillColor(LIGHT);c.roundRect(42,y-height,528,height,6,fill=1,stroke=0)
 para(text,y-12,x=55,w=502)

def end():c.showPage()

# 1: compact overview, with measurement caveat before any question statistics.
title(1,'Descriptive report','Who speaks at the mañaneras?','Question-speaker text, self-identified journalists, and media affiliations. Prepared 11 October 2026.')
for x,value,label in [(42,'221','Source conferences'),(222,'15,139','Question-speaker paragraphs'),(402,'149','Dates with an identification')]:
 c.setFillColor(LIGHT);c.roundRect(x,564,168,87,6,fill=1,stroke=0)
 c.setFillColor(TEAL);c.setFont('DejaVu-Bold',28);c.drawString(x+12,608,value)
 para(label,591,x=x+12,w=145,sty=small)
callout('<b>What this report measures.</b> Text statistics use transcript paragraphs labeled as question speakers. Journalist and outlet rankings use reviewed self-identifications. Neither measure is a count of individual questions.',541,78)
section('Question-speaker text by month',435)
image('monthly',38,192,540,230)
para('<b>262 named journalist-days</b> across 137 name forms; <b>596 outlet-days</b> across 203 outlet labels. Journalists are counted once per conference date, regardless of how many outlets they name.',174)
para('The repository snapshot ends on 22 August 2025 and does not cover a full year. Monthly totals reflect both the number of available conferences and transcript formatting; they are not measures of speaking access or attention.',109,sty=small)
end()

# 2: distributions and explicit proxy definitions.
title(2,'Question-speaker text','How much question text?','Units: source paragraphs and whitespace-separated words, without question segmentation or speaker attribution.')
image('questions',38,410,540,233)
rows=[['Statistic','Per conference: paragraphs','Per paragraph: words'],
 ['Mean',f"{S['daily_stats']['mean']:.1f}",f"{S['word_stats']['mean']:.1f}"],
 ['Median',str(int(S['daily_stats']['50%'])),str(int(S['word_stats']['50%']))],
 ['Middle 50%',f"{S['daily_stats']['25%']:.0f} - {S['daily_stats']['75%']:.0f}",f"{S['word_stats']['25%']:.0f} - {S['word_stats']['75%']:.0f}"],
 ['Range',f"0 - {S['daily_stats']['max']:.0f}",f"1 - {S['word_stats']['max']:.0f}"]]
y=table(rows,389,[138,195,195])
y=para(f"The corpus contains <b>{S['words']:,} words</b> in these paragraphs. <b>{S['punctuated_paragraphs']:,} paragraphs ({100*S['punctuated_paragraphs']/S['paragraphs']:.1f}%)</b> contain a closing question mark. A paragraph may contain several questions, an introduction, a statement, or quoted material.",y-16)
section('Five dates with the most question-speaker paragraphs',y-29)
para('  |  '.join(f"{r['date']}: <b>{r['paragraphs']}</b>" for r in S['top_paragraph_days']),y-42,sty=small)
para('The five zero-count conferences remain in the per-conference distribution. Source speaker labels can include narration and replayed material, so these counts should not be called live questions.',88,sty=small)
end()

# 3: top people, no multi-outlet inflation.
title(3,'Who identifies themselves','Top 10 journalist name forms','Ranked by distinct dates with an explicit name identification; multiple media affiliations count once per date.')
image('reporters',38,344,540,309)
share=sum(r['days'] for r in S['top_reporters'])/S['reporter_days']*100
section('How to read this ranking',317)
y=para(f"<b>{escape(S['top_reporters'][0]['reporter'])}</b> has the most observed identification days ({S['top_reporters'][0]['days']}). The displayed top 10 account for <b>{share:.1f}%</b> of the 262 named journalist-days. This measures observed introductions, not the number of questions asked.",299)
y=para('Names are available on <b>105 of 221 conference dates (47.5%)</b>. A familiar journalist who does not state their name can be missing here. Repeated name variants have not been fully reconciled into unique people.',y-17)
callout('<b>Counting rule:</b> date + normalized name. Accents, case and punctuation are normalized. Partial names and differing full-name forms remain separate. Ties are ordered alphabetically by normalized name.',y-20,77)
para('Several name forms tie at the tenth-place threshold. Exactly 10 are shown for readability; this ordering does not imply that the last displayed name appeared more often than other names tied on four days.',81,sty=small)
end()

# 4: top outlets with anonymous contributions visible.
title(4,'Which media are represented','Top 10 outlet labels','Ranked by distinct dates with a stated affiliation, including introductions that do not state a journalist name.')
image('outlets',38,313,540,340)
section('Outlet-only introductions contribute to the ranking',286)
y=para(f"<b>{escape(S['top_outlets'][0]['outlet'])}</b> is observed on the most dates ({S['top_outlets'][0]['days']}). Across all outlets there are <b>596 distinct outlet-days</b>. The top 10 shown account for <b>{100*sum(r['days'] for r in S['top_outlets'])/S['outlet_days']:.1f}%</b> of those outlet-days.",268)
y=para('Teal counts dates on which at least one journalist was named for that outlet. Gold counts dates with only unnamed identifications for that outlet. Each outlet-day appears in one segment, even if the evidence includes both named and unnamed speakers.',y-17)
y=para('Parent groups and individual titles are kept as separate labels when both are stated. Thus these labels are not consolidated media companies, and their totals must not be interpreted as market shares.',y-17)
para('Ties are ordered alphabetically by normalized outlet label. The tenth-place threshold is eight observed days, shared by other outlets not displayed.',82,sty=small)
end()

# 5: missing identities + participation frequency.
title(5,'Completeness and recurrence','Identification and recurrence','Missing names are preserved; no journalist is inferred from an outlet or from another conference date.')
rows=[['Identification in the main export','Records','Share of 602'],
 ['Journalist and outlet both stated',S['both'],f"{S['both']/602:.1%}"],
 ['Outlet stated; journalist name missing',S['outlet_only'],f"{S['outlet_only']/602:.1%}"],
 ['Journalist stated; outlet missing',S['name_only'],f"{S['name_only']/602:.1%}"]]
y=table(rows,649,[350,75,103])
section('Distribution of observed conference days',y-33)
image('recurrence',38,227,540,235)
y=para(f"<b>{S['single_day_names']} of 137 name forms ({S['single_day_names']/137:.1%})</b> occur on only one observed day. The same is true for <b>{S['single_day_outlets']} of 203 outlet labels ({S['single_day_outlets']/203:.1%})</b>. Sparse identification limits conclusions about concentration of actual participation.",209)
y=para('<b>Deduplication:</b> 606 evidence records become 602 daily name-outlet combinations. Named and unnamed entries for the same outlet/day remain separate; they could refer to the same person. An outlet-only record is not necessarily a distinct unnamed journalist.',y-18)
end()

# 6: full period comparability audit.
title(6,'Coverage over time','Monthly coverage and identification','Identification means at least one reviewed journalist name or media affiliation was found on that date.')
rows=[['Month','Confs.','Q-speaker\nparagraphs','Identified\ndates','Coverage','Named\ndates']]
for r in S['monthly']:
 rows.append([r['month'],r['conferences'],f"{r['paragraphs']:,}",r['identified_dates'],f"{r['identified_dates']/r['conferences']:.0%}",r['named_dates']])
rows.append(['Total',221,'15,139',149,'67.4%',105])
y=table(rows,650,[74,57,105,101,86,105],fontsize=9)
section('Coverage changes affect every ranking',y-33)
y=para('Across the full period, <b>72 conferences have no extracted identification</b>. This is missing identification evidence, not evidence that no journalist attended or asked a question. Monthly changes may reflect introductions, transcript practices, or extraction coverage.',y-49)
y=para('Five files have no recognized question-speaker paragraphs: <b>'+', '.join(S['zero_dates'])+'</b>. These are source-coverage review cases rather than confirmed conferences without questions.',y-17)
para('October begins on the 2nd and August ends on the 22nd. All available main transcripts in the pinned repository snapshot are included; participant-specific duplicate exports are excluded.',81,sty=small)
end()

# 7: reproducibility and explicit estimand boundaries.
title(7,'Methods and provenance','Definitions, sources and limits','These descriptive results summarize the available transcripts and reviewed introductions, without model/API classification.')
sections=[
 ('Question-speaker paragraphs','Nonempty source rows labeled PREGUNTA, PREGUNTAS, PREGUNTA (VIDEOLLAMADA), INTERLOCUTOR, INTERLOCUTORA, or the observed INTERLOCUTIR typo. Paragraph boundaries follow the source CSV. Some labels also cover narrated or replayed material. Individual questions, speaking turns and topics have not been classified.'),
 ('Journalist and outlet identifications','Reviewed self-introductions and explicit affiliation statements. Exact supporting text, source path and source row are retained. Inclusion decisions are stored in two review ledgers; evidence hashes are checked on export. Ordinary or third-party mentions of a media outlet are not affiliation evidence.'),
 ('Units and normalization','The main export is long by date, normalized name and normalized outlet. Journalist rankings collapse multiple outlets to one name/date. Outlet rankings collapse multiple journalists to one outlet/date. Normalization removes accents, case and punctuation; substantive aliases are not fully merged. Ties use normalized alphabetical order.'),
 ('Interpretation','The rankings describe observed self-identification, not all attendance, questions asked, speaking time, access, influence or media ownership. Question text has not been reliably assigned to each journalist, so this report does not produce questions-per-journalist rankings. No names are guessed for the 239 outlet-only records.'),
 ('Source and reproducibility','NOSTRODATA, conferencias_matutinas_sheinbaum, snapshot 5cf67b3aaf08ceb24db34df4dd8d94d69f3a8d39. Coverage: 2 October 2024 through 22 August 2025; 221 main conference CSVs and 84,547 total transcript rows. Derived data retain the source attribution under CC BY-SA 4.0.')]
y=651
for head,body in sections:
 section(head,y);y=para(body,y-14,sty=small)-22
para('<link href="https://github.com/NOSTRODATA/conferencias_matutinas_sheinbaum" color="#008577">Source repository</link>  |  <link href="https://creativecommons.org/licenses/by-sa/4.0/" color="#008577">CC BY-SA 4.0 license</link>',y,sty=small)
para('Inputs: question_rows.parquet, conference_manifest.csv, periodistas_v2_all_years.parquet, and journalist_media_evidence.parquet in the Sheinbaum auxiliar directory. Reproduction: report_statistics.py, then render_statistics_pdf.py in code/03-cleaning_conf/question_class/sheinbaum/.',93,sty=small)
end();c.save();print(OUT.resolve())

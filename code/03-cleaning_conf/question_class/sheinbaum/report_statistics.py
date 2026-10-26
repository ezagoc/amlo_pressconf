"""Compute auditable statistics and figures for the reviewed Sheinbaum report.

Run with the repository .venv; then run render_statistics_pdf.py with reportlab.
"""
import json
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from prepare import DEFAULT_ROOT

OUT = Path('tmp/pdfs/sheinbaum')
OUT.mkdir(parents=True, exist_ok=True)
p = DEFAULT_ROOT / 'auxiliar'
d = pd.read_parquet(p/'periodistas_v2_all_years.parquet')
q = pd.read_parquet(p/'question_rows.parquet')
m = pd.read_csv(p/'conference_manifest.csv', parse_dates=['date'])
n = d.dropna(subset=['reporter_aux']).drop_duplicates(['date','reporter_aux'])
o = d.dropna(subset=['outlet_aux']).drop_duplicates(['date','outlet_aux'])
assert len(q) == m.n_question_rows.sum()
assert not d.duplicated(['date','reporter_aux','outlet_aux']).any()

NAVY='#173347'; TEAL='#008577'; GOLD='#D49937'; GRAY='#697C88'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
 'axes.spines.right':False,'axes.labelcolor':NAVY,'text.color':NAVY,
 'xtick.color':GRAY,'ytick.color':NAVY,'axes.edgecolor':'#D4DFE4',
 'savefig.facecolor':'white','figure.facecolor':'white'})

def save(fig,name):
 fig.savefig(OUT/f'{name}.png',dpi=180,bbox_inches='tight')
 plt.close(fig)

def ranking(frame,key,label):
 names=frame.groupby(key)[label].agg(lambda x:x.value_counts().index[0])
 counts=frame.groupby(key).date.nunique().rename('days').to_frame().join(names)
 return counts.reset_index().sort_values(['days',key],ascending=[False,True])

nr=ranking(n,'reporter_aux','reporter'); orn=ranking(o,'outlet_aux','outlet')
monthly=[]
for period, frame in m.groupby(m.date.dt.to_period('M')):
 dates=set(frame.date); sub=d[d.date.isin(dates)]
 monthly.append({'month':str(period),'conferences':len(frame),'paragraphs':int(frame.n_question_rows.sum()),
 'median':float(frame.n_question_rows.median()),'identified_dates':sub.date.nunique(),
 'named_dates':sub.dropna(subset=['reporter']).date.nunique(),
 'reporter_days':len(n[n.date.isin(dates)]),'outlet_days':len(o[o.date.isin(dates)])})
mon=pd.DataFrame(monthly)
fig, ax=plt.subplots(figsize=(8,2.7)); ax.bar(mon.month,mon.paragraphs,color=TEAL,width=.66)
ax.set_ylabel('Question-speaker paragraphs'); ax.tick_params(axis='x',rotation=35)
for i,v in enumerate(mon.paragraphs):ax.text(i,v+22,f'{v:,}',ha='center',fontsize=8)
ax.set_ylim(0,2200); ax.grid(axis='y',alpha=.15); ax.set_axisbelow(True)
save(fig,'monthly')

fig,axs=plt.subplots(1,2,figsize=(8,2.8))
axs[0].hist(m.n_question_rows,bins=np.arange(0,181,15),color=TEAL,edgecolor='white')
axs[0].set(xlabel='Paragraphs per conference',ylabel='Conferences')
axs[1].hist(q.word_count,bins=np.arange(0,181,15),color=NAVY,edgecolor='white')
axs[1].set(xlabel='Words per paragraph',ylabel='Paragraphs')
fig.tight_layout(w_pad=2);save(fig,'questions')

top=nr.head(10).iloc[::-1]
fig,ax=plt.subplots(figsize=(8,3.7)); ax.barh(top.reporter,top.days,color=TEAL,height=.62)
for i,v in enumerate(top.days):ax.text(v+.1,i,str(v),va='center',fontsize=10)
ax.set_xlim(0,8);ax.set_xticks(range(0,9,2));ax.set_xlabel('Conference days with an explicit name identification')
ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True);fig.tight_layout();save(fig,'reporters')

od=d.dropna(subset=['outlet_aux']).groupby(['outlet_aux','date']).reporter.apply(lambda s:s.notna().any()).rename('named').reset_index()
top=orn.head(10).iloc[::-1].copy()
top['named']=top.outlet_aux.map(od.groupby('outlet_aux').named.sum()).astype(int)
fig,ax=plt.subplots(figsize=(8,3.7)); ax.barh(top.outlet,top.named,color=TEAL,height=.62,label='At least one named journalist')
ax.barh(top.outlet,top.days-top.named,left=top.named,color=GOLD,height=.62,label='Outlet only on that day')
for i,v in enumerate(top.days):ax.text(v+.15,i,str(v),va='center',fontsize=10)
ax.set_xlim(0,15);ax.set_xticks(range(0,16,3));ax.set_xlabel('Conference days with an explicit outlet identification')
ax.legend(loc='lower right',fontsize=8,frameon=False);ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
fig.tight_layout();save(fig,'outlets')

fig,axs=plt.subplots(1,2,figsize=(8,2.8))
for ax, rank, color, ylabel in [(axs[0],nr,TEAL,'Reporter name forms'),(axs[1],orn,NAVY,'Outlet labels')]:
 freq=rank.days.value_counts().sort_index();ax.bar(freq.index,freq.values,color=color,width=.72)
 ax.set(xlabel='Observed conference days',ylabel=ylabel);ax.set_xticks(range(1,int(freq.index.max())+1,1 if len(freq)<8 else 2))
 ax.set_ylim(0,105);ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
 for x,y in freq.items():ax.text(x,y+2,str(y),ha='center',fontsize=8)
fig.tight_layout(w_pad=2);save(fig,'recurrence')

# Save exact plotting/statistical inputs alongside the reproducible scripts.
stats={'records':len(d),'evidence_records':len(pd.read_parquet(p/'journalist_media_evidence.parquet')),
 'reporter_days':len(n),'outlet_days':len(o),'name_forms':len(nr),'outlet_labels':len(orn),
 'identified_dates':d.date.nunique(),'named_dates':n.date.nunique(),'source_conferences':len(m),
 'paragraphs':len(q),'words':int(q.word_count.sum()),'punctuated_paragraphs':int(q.text.str.contains(r'\?').sum()),
 'daily_stats':m.n_question_rows.describe().to_dict(),'word_stats':q.word_count.describe().to_dict(),
 'monthly':monthly,'top_reporters':nr.head(10).to_dict('records'),'top_outlets':orn.head(10).to_dict('records'),
 'single_day_names':int(nr.days.eq(1).sum()),'single_day_outlets':int(orn.days.eq(1).sum()),
 'outlet_only':int(d.no_reporter_flag.sum()),'name_only':int(d.no_outlet_flag.sum()),
 'both':int((~d.no_reporter_flag & ~d.no_outlet_flag).sum()),
 'top_paragraph_days':[{'date':r.date.strftime('%Y-%m-%d'),'paragraphs':r.n_question_rows} for r in m.nlargest(5,'n_question_rows').itertuples()],
 'zero_dates':[v.strftime('%Y-%m-%d') for v in m.loc[m.n_question_rows.eq(0),'date']],
 'source_root':str(DEFAULT_ROOT)}
(OUT/'statistics.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in stats.items() if k not in ['monthly','top_reporters','top_outlets','daily_stats','word_stats']},indent=2))

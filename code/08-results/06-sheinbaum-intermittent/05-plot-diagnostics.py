"""Render scientific event-time figures using the repository plotting runtime."""
import csv,sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from project_paths import media_path
DATA=media_path('results/sheinbaum/intermittent_did/five_weekdays_including_question/diagnostics_heterogeneity')
with (DATA/'diagnostics_bands_1000.csv').open() as f:bands=list(csv.DictReader(f))
labels={'videos':'Videos','interactions':'Total interactions','mean_interactions':'Interactions per video','likes':'Likes','comments':'Comments','views':'Views'}
figdir=DATA/'figures';figdir.mkdir(exist_ok=True)
for typ,title,xlabel in [('pre','Pre-treatment: held-out prediction errors','Weekdays before the treatment spell begins'),('post','Carryover: held-out prediction errors','Untreated weekdays after the treatment spell ends')]:
    fig,axs=plt.subplots(3,2,figsize=(8,8.4),layout='constrained')
    for ax,(o,label) in zip(axs.flat,labels.items()):
        b=sorted([r for r in bands if r['test']==typ and r['outcome']==o],key=lambda r:int(r['day']))
        xx=np.array([int(r['day']) for r in b]);yy=np.array([float(r['estimate']) for r in b]);se=np.array([float(r['se']) for r in b])
        ax.fill_between(xx,[float(r['simultaneous_low']) for r in b],[float(r['simultaneous_high']) for r in b],color='#c8d8e8',alpha=.75,label='95% simultaneous band')
        ax.errorbar(xx,yy,yerr=1.96*se,color='#224e73',fmt='o-',capsize=3,lw=1.2,label='Pointwise 95% interval')
        ax.axhline(0,color='#444',lw=.8,ls='--');ax.set_xticks(xx);ax.set_title(label,fontsize=11,loc='left');ax.tick_params(labelsize=9);ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.15)
    fig.supxlabel(xlabel,fontsize=11);fig.supylabel('asinh-outcome prediction error',fontsize=11)
    fig.legend(*axs.flat[0].get_legend_handles_labels(),loc='outside upper center',ncol=2,frameon=False,fontsize=9)
    path=figdir/f'{typ}.png';fig.savefig(path,dpi=190);plt.close(fig)

print(figdir)

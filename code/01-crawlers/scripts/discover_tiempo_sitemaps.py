"""Explicit, resumable discovery from a previously frozen Tiempo sitemap index."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawler_core.tiempo_discovery import freeze, run_discovery, summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['freeze','run','status'])
    p.add_argument('--run-dir',type=Path,required=True)
    p.add_argument('--index-file',type=Path)
    p.add_argument('--recon-dir',type=Path)
    p.add_argument('--limit',type=int,default=100)
    p.add_argument('--priority-from',type=int,default=500)
    p.add_argument('--pause-seconds',type=float,default=1)
    p.add_argument('--retry-failed',action='store_true')
    a=p.parse_args()
    if a.mode=='freeze':
        if not a.index_file:p.error('--index-file is required')
        result=freeze(a.index_file,a.run_dir)
        result={'frozen_sitemaps':len(result['sitemaps'])}
    elif a.mode=='run':
        result=run_discovery(a.run_dir,limit=a.limit,pause_seconds=a.pause_seconds,priority_from=a.priority_from,recon_dir=a.recon_dir,retry_failed=a.retry_failed)
    else:result=summary(a.run_dir)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

"""New explicitly authorized pending-review collection; never adopts old protocols."""
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crawler_core import tiempo_continuous as controller
from crawler_core.tiempo_continuous_source import build_registry,sha_file

def main(argv=None):
    a=argparse.ArgumentParser(description=__doc__);sub=a.add_subparsers(dest='command',required=True)
    r=sub.add_parser('registry',help='Offline: only current real reviewed article examples')
    r.add_argument('--review-source',type=Path,action='append',required=True);r.add_argument('--output',type=Path,required=True)
    f=sub.add_parser('freeze',help='Offline: new dedicated plan; not launch permission')
    f.add_argument('--input',type=Path,required=True);f.add_argument('--run-dir',type=Path,required=True);f.add_argument('--media-root',type=Path,required=True);f.add_argument('--registry',type=Path,required=True);f.add_argument('--registry-sha256',required=True)
    f.add_argument('--queue-db',type=Path,required=True);f.add_argument('--queue-db-sha256',required=True)
    f.add_argument('--exclusions',type=Path,required=True,help='JSON list of role,path,sha256; all original four protocols required')
    f.add_argument('--start',required=True);f.add_argument('--end-exclusive',required=True);f.add_argument('--max-fetch-calls',type=int,required=True);f.add_argument('--pause-seconds',type=float,default=1);f.add_argument('--timeout',type=float,default=45);f.add_argument('--min-free-bytes',type=int,default=10*1024**3)
    r=sub.add_parser('run',help='Explicit bounded collection; may stop permanently on a safety risk')
    r.add_argument('--run-dir',type=Path,required=True);r.add_argument('--media-root',type=Path,required=True);r.add_argument('--max-batches',type=int,required=True);r.add_argument('--allow-network',action='store_true',help='Only after separate root/operator execution authorization')
    args=a.parse_args(argv)
    if args.command=='registry':
        value=build_registry(args.review_source,args.output);print(json.dumps({'path':str(args.output),'sha256':sha_file(args.output),'exemplars':len(value['exemplars']),'known_signatures':len(value['known_signatures'])}));return 0
    if args.command=='freeze':value=controller.freeze(args.input,args.run_dir,args.media_root,args.registry,args.registry_sha256,json.loads(args.exclusions.read_text()),queue_db_path=args.queue_db,queue_db_sha256=args.queue_db_sha256,start=args.start,end=args.end_exclusive,max_fetch_calls=args.max_fetch_calls,pause_seconds=args.pause_seconds,timeout=args.timeout,min_free_bytes=args.min_free_bytes)
    else:value=controller.run(args.run_dir,args.media_root,max_batches=args.max_batches,allow_network=args.allow_network)
    print(json.dumps(value,ensure_ascii=False,indent=2));return 2 if value.get('status','').startswith('halted') else 0

if __name__=='__main__':raise SystemExit(main())

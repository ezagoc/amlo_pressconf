"""Resumable journalist/outlet extraction from the archived official corpus.

Uses the established model, prompt and evidence validator. No question,
sentiment or response-link model stages are run here.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import html
import json
from pathlib import Path
import re

import pandas as pd
from openai import OpenAI, AuthenticationError, PermissionDeniedError, RateLimitError
from prepare import DEFAULT_ROOT, atomic_json
from run_models import (call, DEFAULT_MODEL, JOURNALISTS_PROMPT, JOURNALISTS_SCHEMA,
                        validate_journalists, normalize)


def sha(text):return hashlib.sha256(text.encode()).hexdigest()

def transcript(day):
    return [{'row':int(r.source_row),'label':r.participant_raw,'text':r.text} for r in day.itertuples()]

def eligible_rows(day):
    mask=day.is_question_speaker | day.participant.str.match(r'^(?:INTERVENCION|REPORTER[OA]|PERIODISTA)(?:\b|$)')
    return day.loc[mask & day.row_kind.eq('transcript'),'source_row'].tolist()

def pilot_seeds(base, days, model):
    seeds={}
    for path in (base/'transcript_analysis/official-pilot-10/checkpoints/journalists').glob('*.json'):
        checkpoint=json.loads(path.read_text());request=checkpoint['request']
        user=json.loads(request['user']);date=user['date']
        if date not in days:continue
        if (request['model']!=model or request['system']!=JOURNALISTS_PROMPT or
            request['schema']!=JOURNALISTS_SCHEMA):continue
        if user['transcript']!=transcript(days[date]):
            raise ValueError(f'Pilot and full official transcript differ: {date}')
        validate_journalists(checkpoint['result'],set(user['eligible_source_rows']),
                            days[date].set_index('source_row').text.to_dict(), allow_joint_introductions=True)
        seeds[date]=(path,checkpoint,user['eligible_source_rows'])
    return seeds

def process(date, day, root, model, seed=None):
    eligible=seed[2] if seed else eligible_rows(day)
    texts=day.set_index('source_row').text.to_dict()
    user=json.dumps({'date':date,'eligible_source_rows':eligible,'transcript':transcript(day)},ensure_ascii=False)
    if seed:
        atomic_json(root/'checkpoints/journalists'/seed[0].name,seed[1])
    def validate(result):validate_journalists(result,set(eligible),texts,allow_joint_introductions=True)
    result=(call(OpenAI(max_retries=0),root,'journalists',model,JOURNALISTS_PROMPT,user,
                 validate,tokens=16000,schema=JOURNALISTS_SCHEMA) if eligible else {'periodistas':[]})
    validate(result)
    payload={'date':date,'model':model,'input_sha256':sha(user),'source_url':day.source_url.iloc[0],
             'source_sha256':day.source_sha256.iloc[0], 'eligible_rows':eligible,
             'eligibility_basis':'pilot_live_press_structure' if seed else 'official_press_or_generic_intervention_headings',
             'reused_pilot':bool(seed),'result':result}
    atomic_json(root/'results'/f'{date}.json',payload)
    print(f'{date}: {len(result["periodistas"])} introductions'+(' [pilot reused]' if seed else ''),flush=True)
    return payload

def export(base, source, root, data, dates, destination=None, comparison_source=None):
    # An extended corpus can retain comparison mappings from its unchanged seed
    # subset. New dates do not acquire invented GitHub comparison records.
    comparison_source = comparison_source or source
    records=[];coverage=[]
    for date in dates:
        day=data[data.date==date].set_index('source_row')
        result=json.loads((root/'results'/f'{date}.json').read_text())
        assert day.source_sha256.eq(result['source_sha256']).all()
        validate_journalists(result['result'],set(result['eligible_rows']),day.text.to_dict(),allow_joint_introductions=True)
        payload=json.dumps({'date':date,'eligible_source_rows':result['eligible_rows'],
            'transcript':transcript(day.reset_index())},ensure_ascii=False)
        assert sha(payload)==result['input_sha256'],'Stale extraction input'
        people=result['result']['periodistas']
        coverage.append({'date':date,'n_question_rows':len(result['eligible_rows']),
            'n_introductions':len(people),'status':('existing_reused' if result.get('reused_existing_from')
                else 'pilot_reused' if result['reused_pilot'] else 'processed'),
            'source_url':result['source_url'],'source_sha256':result['source_sha256'],
            'eligibility_basis':result['eligibility_basis']})
        for index, person in enumerate(people):
            ids=sorted(person['evidence_rows']);evidence='\n'.join(day.loc[ids,'text'])
            for outlet in list(dict.fromkeys(person['outlets'])) or [None]:
                name=person['name']
                records.append({'date':pd.Timestamp(date),'reporter':name,'reporter_aux':normalize(name) if name else None,
                    'outlet':outlet,'outlet_aux':normalize(outlet,True) if outlet else None,
                    'turn_index':index,'intro_row':person['intro_row'],'source_row':person['intro_row'],
                    'source_rows':';'.join(map(str,ids)), 'evidence_text':evidence,'evidence_sha256':sha(evidence),
                    'source_path':day.source_path.iloc[0], 'source_url':result['source_url'],
                    'source_sha256':result['source_sha256'],'no_reporter_flag':name is None,
                    'no_outlet_flag':outlet is None,'model':result['model'],
                    'extraction_method':'api_explicit_identification_official_html',
                    'reused_pilot':result['reused_pilot']})
    out=(destination or root)/'auxiliar';out.mkdir(parents=True,exist_ok=True)
    evidence=pd.DataFrame(records).sort_values(['date','source_row','outlet'],na_position='last').reset_index(drop=True)
    daily=evidence.drop_duplicates(['date','reporter_aux','outlet_aux'])
    for name,df in [('journalist_media_evidence',evidence),('periodistas_v2_all_years',daily)]:
        df.to_parquet(out/f'{name}.parquet',index=False);df.to_csv(out/f'{name}.csv',index=False)
    daily.to_csv(out/'journalists_and_media.csv',index=False)
    daily[daily.no_reporter_flag|daily.no_outlet_flag].to_csv(out/'missing_identifications_review.csv',index=False)
    cov=pd.DataFrame(coverage);cov.to_csv(out/'journalist_media_coverage.csv',index=False)
    assert set(cov.date)==set(dates) and cov.date.is_unique
    assert not daily.duplicated(['date','reporter_aux','outlet_aux']).any()
    assert not (daily.no_reporter_flag & daily.no_outlet_flag).any()
    original=pd.read_parquet(base/'api_extraction/full/auxiliar/periodistas_v2_all_years.parquet')
    old_cov=pd.read_csv(base/'api_extraction/full/auxiliar/journalist_media_coverage.csv')
    comparison=old_cov[['date','n_introductions']].merge(cov[['date','n_introductions']],on='date',suffixes=('_github','_official'),validate='one_to_one')
    comparison['change']=comparison.n_introductions_official-comparison.n_introductions_github
    comparison.to_csv(out/'official_vs_github_coverage.csv',index=False)
    # Compare only confidently aligned old evidence; never reuse old row IDs.
    bridge=pd.read_parquet(comparison_source/'auxiliar/journalist_media_evidence.parquet')
    bridge=bridge[bridge.date.dt.strftime('%Y-%m-%d').isin(dates)]
    covered={(r.date,int(n)) for r in evidence.itertuples() for n in r.source_rows.split(';')}
    missing=bridge[[not all((r.date,int(n)) in covered for n in r.source_rows.split(';')) for r in bridge.itertuples()]]
    missing.to_csv(out/'aligned_old_evidence_missing_review.csv',index=False)
    # Retain prior semantic-review leads only after mapping their source rows.
    alignment=pd.read_parquet(comparison_source/'auxiliar/paragraph_alignment.parquet')
    prior_notes=pd.read_csv(Path(__file__).with_name('full_run_review_notes.csv'))
    flags=[]
    for note in prior_notes.itertuples():
        if note.date not in dates:continue
        match=alignment[(alignment.date==note.date)&alignment.github_row.eq(note.source_row)]
        if len(match)!=1:continue
        n=int(match.iloc[0].official_row);day=data[data.date==note.date].set_index('source_row')
        extracted=evidence[(evidence.date==note.date)&evidence.source_row.eq(n)]
        flags.append({'date':note.date,'source_row':n,'github_source_row':note.source_row,
            'in_api_extraction':not extracted.empty,'reporter':' | '.join(extracted.reporter.dropna().unique()),
            'outlets':' | '.join(extracted.outlet.dropna().unique()),'review_status':'recheck_on_official_source',
            'note':note.note,'source_text':day.loc[n,'text'],
            'nearby_context':'\n'.join(day.loc[max(0,n-2):n+2,'text'])})
    pd.DataFrame(flags).to_csv(out/'full_run_review_flags.csv',index=False)
    usage=[]
    for path in (root/'checkpoints/journalists').glob('*.json'):
        x=json.loads(path.read_text());date=json.loads(x['request']['user'])['date']
        usage.append((date,x['usage']))
    reused=set(cov.loc[cov.status.eq('pilot_reused'),'date'])
    reused_existing=set(cov.loc[cov.status.eq('existing_reused'),'date'])
    requested_dates=set(data.date.dt.strftime('%Y-%m-%d'))
    complete=set(dates)==requested_dates
    report={'model':DEFAULT_MODEL,'complete':complete,'n_requested_conferences':len(requested_dates),
        'n_remaining_conferences':len(requested_dates-set(dates)),
        'n_conferences':len(cov),'n_reused_pilot_conferences':len(reused),
        'n_reused_existing_conferences':len(reused_existing),
        'n_new_conferences':len(cov)-len(reused)-len(reused_existing),'n_records':len(daily),'n_evidence_records':len(evidence),
        'n_introduction_passages':len(evidence[['date','source_row']].drop_duplicates()),
        'n_outlet_only_records':int(daily.no_reporter_flag.sum()),'n_named_records_without_outlet':int(daily.no_outlet_flag.sum()),
        'n_dates_with_identification':int(daily.date.nunique()),'n_reporter_name_forms':int(daily.reporter_aux.nunique()),
        'n_outlet_labels':int(daily.outlet_aux.nunique()),'previous_github_records':len(original),
        'previous_github_introduction_passages':int(old_cov.n_introductions.sum()),
        'previous_github_records_same_dates':int(original.date.dt.strftime('%Y-%m-%d').isin(dates).sum()),
        'previous_github_introduction_passages_same_dates':int(old_cov.loc[old_cov.date.isin(dates),'n_introductions'].sum()),
        'n_aligned_old_evidence_records_requiring_review':len(missing),'n_prior_review_leads_mapped':len(flags),
        'successful_checkpoint_count':len(usage),
        'github_comparison_source':str(comparison_source),
        'new_successful_input_tokens':sum(u['input_tokens'] for d,u in usage if d not in reused),
        'new_successful_output_tokens':sum(u['output_tokens'] for d,u in usage if d not in reused),
        'checks':'PASS: all selected completed dates represented; source-supported names/outlets; exact evidence text/hashes; input/source fingerprints; unique daily normalized keys.',
        'limitations':['Counts describe explicit introductions, not questions or a complete attendance census.',
            'Daily normalized-key deduplication is applied; alias harmonization remains a separate reviewed step.',
            'Unstated names and outlets are not inferred. Missing introductions require semantic review.',
            'Pilot eligibility uses its live-press annotations; other dates use official press/generic intervention labels with full transcript context.',
            'Integrity validation is not a gold-standard accuracy or recall estimate.']}
    atomic_json(out/'api_run_audit.json',report)
    atomic_json(out/'journalist_extraction_report.json',report)
    review=(destination or root)/'review';review.mkdir(exist_ok=True)
    text=['<!doctype html><meta charset="utf-8"><title>Official journalist/outlet extraction</title>',
          '<style>body{font:16px/1.5 system-ui;max-width:1200px;margin:40px auto;padding:0 20px}td,th{border:1px solid #ddd;padding:7px}table{border-collapse:collapse;font-size:13px}pre{white-space:pre-wrap;font:inherit}summary{cursor:pointer}details{padding:10px;border-top:1px solid #ddd}</style>',
          '<h1>Sheinbaum: official-source journalist and outlet extraction</h1>',
          f'<p>{len(cov)} of {len(requested_dates)} requested dates processed. '+('Complete.' if complete else 'PARTIAL EXPORT: remaining dates have not completed extraction.')+' Exact introduction evidence retained. Counts are explicit identifications; labels still need manual alias review. Original extraction preserved.</p>',
          '<p><a href="../auxiliar/journalists_and_media.csv">Daily records</a> · <a href="../auxiliar/journalist_media_evidence.csv">All evidence</a> · <a href="../auxiliar/official_vs_github_coverage.csv">Coverage comparison</a></p>',
          '<pre>'+html.escape(json.dumps(report,ensure_ascii=False,indent=2))+'</pre>',
          comparison.to_html(index=False),'<h2>Introduction passages</h2>']
    for (date,n),g in evidence.groupby(['date','source_row']):
        title=f'{date.date()} · row {n} · '+ ' | '.join(g.reporter.dropna().unique())+' · '+ ' | '.join(g.outlet.dropna().unique())
        text.append(f'<details id="{date.date()}-{n}"><summary>{html.escape(title)}</summary><pre>{html.escape(g.evidence_text.iloc[0])}</pre><a href="{html.escape(g.source_url.iloc[0])}">Official source</a></details>')
    (review/'index.html').write_text('\n'.join(text))
    print(json.dumps(report,ensure_ascii=False,indent=2))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',type=Path,default=DEFAULT_ROOT)
    p.add_argument('--output',type=Path)
    p.add_argument('--workers',type=int,default=3)
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--export-only',action='store_true')
    p.add_argument('--export-partial',action='store_true',help='Export completed checkpoints to partial/ without API calls')
    args=p.parse_args();source=args.base/'official_source/full';root=args.output or args.base/'api_extraction/official-full'
    manifest=json.loads((source/'manifest.json').read_text());assert manifest['complete']
    data=pd.read_parquet(source/'auxiliar/transcript_rows.parquet')
    dates=manifest['dates'];days={str(date.date()):day.sort_values('source_row') for date,day in data.groupby('date')}
    assert set(dates)==set(days) and root.resolve()!=source.resolve()
    for rec in manifest['pages']:
        assert hashlib.sha256(Path(rec['raw_path']).read_bytes()).hexdigest()==rec['sha256']
        assert days[rec['date']].source_sha256.eq(rec['sha256']).all()
    seeds=pilot_seeds(args.base,days,DEFAULT_MODEL)
    if args.dry_run:
        print(json.dumps({'conferences':len(dates),'pilot_reusable':len(seeds),'new_conferences':len(dates)-len(seeds),
                         'model':DEFAULT_MODEL,'output':str(root),'api_calls':0},indent=2));return
    if args.export_partial:
        completed=[d for d in dates if (root/'results'/f'{d}.json').exists()]
        if not completed:raise ValueError('No completed dates to export')
        export(args.base,source,root,data,completed,destination=root/'partial');return
    if not args.export_only:
        errors=[]
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures={pool.submit(process,date,days[date],root,DEFAULT_MODEL,seeds.get(date)):date for date in dates}
            for f in as_completed(futures):
                try:f.result()
                except Exception as exc:
                    errors.append({'date':futures[f],'error_type':type(exc).__name__,'error':str(exc)})
                    print(f'{futures[f]}: FAILED {type(exc).__name__}: {exc}',flush=True)
                    fatal=(isinstance(exc,(AuthenticationError,PermissionDeniedError)) or
                           isinstance(exc,RateLimitError) and exc.code in
                           {'credit_balance_exhausted','insufficient_quota','billing_hard_limit_reached'})
                    if fatal:
                        for pending in futures:pending.cancel()
        atomic_json(root/'run_errors.json',errors)
        if errors:raise RuntimeError(f'{len(errors)} dates failed; cached successes preserved. See run_errors.json')
    export(args.base,source,root,data,dates)

if __name__=='__main__':main()

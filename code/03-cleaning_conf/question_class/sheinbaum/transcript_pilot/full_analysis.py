"""Extend the validated official pilot to the existing 221-date source subset.

Reuses compatible pilot checkpoints and the completed official introduction
extraction. All new model calls are speaker/section or question/response passes.
"""
from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import hashlib
import json
from pathlib import Path

import pandas as pd
from openai import AuthenticationError, PermissionDeniedError, RateLimitError
from pipeline import (DEFAULT_ROOT, DEFAULT_MODEL, atomic_json, export,
                      process_day, require, validate_journalists)
from official_journalists import transcript
from audit_pilot import audit


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_introduction(path, day, model):
    saved = json.loads(path.read_text())
    require(saved['model'] == model, 'Introduction model differs from requested model')
    require(day.source_sha256.eq(saved['source_sha256']).all(), 'Stale introduction source')
    require(day.source_url.eq(saved['source_url']).all(), 'Introduction source URL mismatch')
    payload = json.dumps({'date': saved['date'], 'eligible_source_rows': saved['eligible_rows'],
                          'transcript': transcript(day)}, ensure_ascii=False)
    require(hashlib.sha256(payload.encode()).hexdigest() == saved['input_sha256'],
            'Stale introduction transcript/input fingerprint')
    validate_journalists(saved['result'], set(saved['eligible_rows']),
                         day.set_index('source_row').text.to_dict())
    return saved['result']


def compatible_pilot_checkpoints(pilot, days, model):
    """Return exact-transcript checkpoints; call() still checks full request keys."""
    found = []
    for stage in ['structure', 'qa']:
        for path in sorted((pilot / 'checkpoints' / stage).glob('*.json')):
            saved = json.loads(path.read_text())
            request = saved['request']; user = json.loads(request['user'])
            date = user['date']
            if date not in days or request['model'] != model:
                continue
            require(user['transcript'] == transcript(days[date]),
                    f'Pilot/full transcript mismatch on {date}')
            key = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            require(path.stem == key, f'Pilot checkpoint key mismatch: {path.name}')
            found.append((stage, path, date))
    return found


def is_fatal(exc):
    return (isinstance(exc, (AuthenticationError, PermissionDeniedError)) or
            isinstance(exc, RateLimitError) and exc.code in
            {'credit_balance_exhausted', 'insufficient_quota', 'billing_hard_limit_reached'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--model', default=DEFAULT_MODEL)
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--dates', nargs='+')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--export-only', action='store_true')
    args = parser.parse_args()
    require(args.workers > 0, 'Workers must be positive')
    source = args.base / 'official_source/full'
    pilot = args.base / 'transcript_analysis/official-pilot-10'
    identities = args.base / 'api_extraction/official-full'
    root = args.output or args.base / 'transcript_analysis/official-full'
    require(root.resolve() not in {source.resolve(), pilot.resolve(), identities.resolve()},
            'Output must be separate from source, pilot, and identity extraction')
    manifest = json.loads((source / 'manifest.json').read_text())
    require(manifest['complete'], 'Official source collection is incomplete')
    identity_audit = json.loads((identities / 'auxiliar/api_run_audit.json').read_text())
    require(identity_audit['complete'], 'Finish official identity extraction first')
    data = pd.read_parquet(source / 'auxiliar/transcript_rows.parquet')
    days = {str(date.date()): day.sort_values('source_row') for date, day in data.groupby('date')}
    dates = manifest['dates']
    require(set(dates) == set(days), 'Source manifest/table dates mismatch')
    for page in manifest['pages']:
        require(digest(Path(page['raw_path'])) == page['sha256'], 'Archived HTML hash mismatch')
        require(days[page['date']].source_sha256.eq(page['sha256']).all(), 'Parsed source hash mismatch')
    for date, day in days.items():
        require(not day.source_row.duplicated().any(), f'Duplicate source row on {date}')
        require(day.source_row.tolist() == list(range(int(day.source_row.min()), int(day.source_row.max())+1)),
                f'Non-contiguous source rows on {date}')
    if args.dates:
        require(set(args.dates) <= set(dates), 'Requested date outside source subset')
        dates = [d for d in dates if d in args.dates]
    introductions = {date: checked_introduction(identities / 'results' / f'{date}.json',
                                                days[date], args.model) for date in dates}
    seeds = compatible_pilot_checkpoints(pilot, {d: days[d] for d in dates}, args.model)
    seeded_dates = {d for _, _, d in seeds}
    plan = {'requested_dates': dates, 'n_requested_dates': len(dates), 'model': args.model,
            'source_root': str(source), 'source_table_sha256': digest(source / 'auxiliar/transcript_rows.parquet'),
            'journalist_extraction_root': str(identities), 'output': str(root),
            'n_compatible_pilot_checkpoints': len(seeds), 'n_pilot_dates': len(seeded_dates),
            'journalist_api_calls': 0, 'new_model_stages': ['structure', 'qa']}
    if args.dry_run:
        print(json.dumps({**plan, 'api_calls': 0}, indent=2)); return
    atomic_json(root / 'run_plan.json', plan)
    for stage, path, _ in seeds:
        dest = root / 'checkpoints' / stage / path.name
        if dest.exists():
            require(digest(dest) == digest(path), f'Existing checkpoint conflicts with pilot: {path.name}')
        else:
            atomic_json(dest, json.loads(path.read_text()))
    completed = []; errors = []
    if not args.export_only:
        # Pilot dates first give a no-charge end-to-end check. Keep only workers
        # requests in flight so billing/auth failures stop further submissions.
        pending_dates = iter(sorted(dates, key=lambda d: (d not in seeded_dates, d)))
        stopped = False
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            running = {}
            def submit():
                date = next(pending_dates, None)
                if date is not None:
                    running[pool.submit(process_day, date, days[date], root, args.model,
                                        'all', introductions[date])] = date
            for _ in range(args.workers): submit()
            while running:
                finished, _ = wait(running, return_when=FIRST_COMPLETED)
                for future in finished:
                    date = running.pop(future)
                    try:
                        future.result(); completed.append(date)
                    except Exception as exc:
                        errors.append({'date': date, 'error_type': type(exc).__name__, 'error': str(exc)})
                        print(f'{date}: FAILED {type(exc).__name__}: {exc}', flush=True)
                        stopped |= is_fatal(exc)
                atomic_json(root / 'run_progress.json', {'complete': len(completed) == len(dates),
                    'n_requested': len(dates), 'n_completed_this_run': len(completed),
                    'completed_this_run': sorted(completed), 'stopped_on_fatal_error': stopped,
                    'errors': errors})
                if not stopped:
                    for _ in finished: submit()
        atomic_json(root / 'run_errors.json', errors)
        require(len(completed) == len(dates),
                f'Only {len(completed)}/{len(dates)} requested dates completed; checkpoints preserved. See run_errors.json')
    # export validates every partition and question/answer reference again.
    export(root, source, dates, args.model, official=True)
    audit(root, source)
    summary = json.loads((root / 'auxiliar/pilot_report.json').read_text())
    summary.update({'scope': 'full_existing_official_subset' if set(dates) == set(days) else 'selected_dates',
                    'complete': set(dates) == set(days), 'n_requested_corpus_dates': len(days),
                    'n_exported_dates': len(dates), 'journalist_extraction_root': str(identities),
                    'identity_policy': 'Reuse existing explicit introductions; attach only to a single live press speaker, flag other cases.',
                    'pilot_checkpoint_reuse': len(seeds),
                    'usage_note': 'Successful checkpoint totals include reused pilot structure/QA calls; identity calls are excluded. Failed attempts are not included.'})
    atomic_json(root / 'auxiliar/corpus_report.json', summary)


if __name__ == '__main__':
    main()

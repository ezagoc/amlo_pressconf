"""Extend official journalist/outlet extraction, preserving manual alias rules.

Reuses source/input-verified results, runs the established GPT extraction only
for missing dates, and prepares review inputs without harmonizing name variants.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path

import pandas as pd
from openai import AuthenticationError, PermissionDeniedError, RateLimitError
from official_journalists import (DEFAULT_ROOT, DEFAULT_MODEL, atomic_json,
    eligible_rows, export, pilot_seeds, process, sha, transcript, validate_journalists)


def verified_result(path, date, day, eligible):
    result = json.loads(path.read_text())
    user = json.dumps({'date': date, 'eligible_source_rows': eligible,
                      'transcript': transcript(day)}, ensure_ascii=False)
    assert result['date'] == date and result['model'] == DEFAULT_MODEL, 'Different date/model'
    assert result['input_sha256'] == sha(user), f'Stale extraction input: {date}'
    assert day.source_sha256.eq(result['source_sha256']).all(), f'Stale source: {date}'
    assert result['eligible_rows'] == eligible, f'Changed eligible rows: {date}'
    validate_journalists(result['result'], set(eligible), day.set_index('source_row').text.to_dict(),
                        allow_joint_introductions=True)
    return result


def review_labels(destination, previous):
    out = destination/'auxiliar'
    current = pd.read_parquet(out/'periodistas_v2_all_years.parquet')
    old = pd.read_parquet(previous/'auxiliar/periodistas_v2_all_years.parquet')
    rows = []
    for kind in ['reporter', 'outlet']:
        key = kind + '_aux'; known = set(old[key].dropna())
        for label, group in current.dropna(subset=[key]).groupby(key):
            rows.append({'type': kind, 'label': label, 'new_since_previous_extraction': label not in known,
                'literal_spellings': ' | '.join(sorted(group[kind].dropna().unique())),
                'n_dates': group.date.nunique(), 'n_records': len(group),
                'first_date': group.date.min().date(), 'last_date': group.date.max().date(),
                'example_evidence': group.evidence_text.iloc[0], 'example_source_url': group.source_url.iloc[0]})
    table = pd.DataFrame(rows).sort_values(['type', 'new_since_previous_extraction', 'n_dates', 'label'],
                                          ascending=[True, False, False, True])
    table.to_csv(out/'deduplication_label_inventory.csv', index=False)
    table[table.new_since_previous_extraction].to_csv(out/'new_labels_for_manual_review.csv', index=False)


def fatal_error(exc):
    return isinstance(exc, (AuthenticationError, PermissionDeniedError)) or (
        isinstance(exc, RateLimitError) and exc.code in
        {'credit_balance_exhausted', 'insufficient_quota', 'billing_hard_limit_reached'})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--through', required=True)
    p.add_argument('--base', type=Path, default=DEFAULT_ROOT)
    p.add_argument('--workers', type=int, default=3)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--export-only', action='store_true')
    args = p.parse_args()
    if args.workers < 1: raise ValueError('workers must be positive')
    end = pd.Timestamp(args.through).strftime('%Y-%m-%d')
    source = args.base/'official_source'/f'through-{end}'
    root = args.base/'api_extraction'/f'official-through-{end}'
    previous = args.base/'api_extraction/official-full'
    comparison_source = args.base/'official_source/full'
    manifest = json.loads((source/'manifest.json').read_text())
    assert manifest['complete'] and manifest['discovery_complete'], 'Incomplete official source collection'
    data = pd.read_parquet(source/'auxiliar/transcript_rows.parquet')
    days = {str(d.date()): g.sort_values('source_row') for d, g in data.groupby('date')}
    dates = manifest['dates']; assert set(dates) == set(days)
    for rec in manifest['pages']:
        assert hashlib.sha256(Path(rec['raw_path']).read_bytes()).hexdigest() == rec['sha256']
        assert days[rec['date']].source_sha256.eq(rec['sha256']).all()
    # Old row mappings are valid only for the source versions they describe.
    for rec in json.loads((comparison_source/'manifest.json').read_text())['pages']:
        if rec['date'] in days: assert days[rec['date']].source_sha256.eq(rec['sha256']).all()
    seeds = pilot_seeds(args.base, days, DEFAULT_MODEL)
    completed = {}; pending = []; reused = []
    for date in dates:
        day = days[date]; eligible = seeds[date][2] if date in seeds else eligible_rows(day)
        local, prior = root/'results'/f'{date}.json', previous/'results'/f'{date}.json'
        if local.exists():
            completed[date] = verified_result(local, date, day, eligible)
        elif prior.exists():
            result = verified_result(prior, date, day, eligible)
            result['reused_existing_from'] = str(prior)
            completed[date] = result; reused.append(date)
            if not args.dry_run: atomic_json(local, result)
        else: pending.append(date)
    print(json.dumps({'conferences': len(dates), 'verified_completed': len(completed),
        'remaining': len(pending), 'newly_reused': len(reused), 'model': DEFAULT_MODEL,
        'source': str(source), 'output': str(root)}, indent=2), flush=True)
    if args.dry_run: return
    errors = []; stopped = False
    def progress():
        atomic_json(root/'run_progress.json', {'model': DEFAULT_MODEL, 'requested_through': end,
            'n_requested': len(dates), 'n_completed': len(completed),
            'complete': len(completed) == len(dates), 'stopped_on_fatal_error': stopped,
            'remaining_dates': sorted(set(dates) - set(completed)), 'errors': errors})
    def attempt(date):
        nonlocal stopped
        try:
            completed[date] = process(date, days[date], root, DEFAULT_MODEL, seeds.get(date))
        except Exception as exc:
            errors.append({'date': date, 'error_type': type(exc).__name__, 'error': str(exc)})
            if fatal_error(exc): stopped = True
            print(f'{date}: FAILED {type(exc).__name__}: {exc}', flush=True)
    progress()
    if pending and not args.export_only:
        # One actual extraction first detects exhausted billing before launching
        # concurrent requests. The successful output is retained, not a probe.
        attempt(pending[0]); progress()
        for start in range(1, len(pending), args.workers):
            if stopped: break
            batch = pending[start:start + args.workers]
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                futures = [pool.submit(attempt, date) for date in batch]
                for future in as_completed(futures): future.result()
            progress()
    progress()
    atomic_json(root/'run_errors.json', errors)
    complete = len(completed) == len(dates)
    if completed:
        destination = root if complete else root/'partial'
        export(args.base, source, root, data, sorted(completed),
               destination=destination, comparison_source=comparison_source)
        review_labels(destination, previous)
    if not complete:
        raise RuntimeError(f'Extraction incomplete: {len(completed)}/{len(dates)} dates. '
                           'Validated results retained; incomplete review export is in partial/.')


if __name__ == '__main__': main()

"""Discover and archive all available official Sheinbaum conferences as of a date."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
import pandas as pd
from official_source import DEFAULT_ROOT, parse, validate_page, atomic_json, digest

spec = importlib.util.spec_from_file_location('amlo_archive_helpers', Path(__file__).resolve().parents[3]/'official_amlo/scrape.py')
helpers = importlib.util.module_from_spec(spec); spec.loader.exec_module(helpers)
START = '2024-10-02'
# Reviewed against the correctly titled, full transcript for the same date.
# This provisional page stops at "Ahora sí vamos a las preguntas. (CONTINÚA…)".
EXCLUDED_INDEX_PATHS = {
    '/presidencia/articulos/version-estenografica-conferencia-de-prensa-de-la-presidenta-claudia-sheinbaum-pardo-del-30-de-marzo-de-202':
        'Provisional opening-only version with truncated year; superseded by the full 2026-03-30 transcript.'
}


def index_page(root, section, page, end):
    path = root/'indexes'/f'{section}-{page:04d}.html'
    meta = path.with_suffix('.json')
    if path.exists() and meta.exists():
        body = path.read_bytes(); assert digest(body) == json.loads(meta.read_text())['sha256']
    else:
        r = helpers.fetch(f'https://www.gob.mx/presidencia/archivo/{section}?order=DESC&page={page}')
        body = r.content; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(body)
        atomic_json(meta, {'url': r.url, 'sha256': digest(body), 'retrieved_at': datetime.now(timezone.utc).isoformat()})
    soup = BeautifulSoup(helpers.decode_index(body.decode('utf-8')), 'html.parser')
    articles = soup.select('article'); assert articles, f'No archive entries: {section}/{page}'
    entries = []
    for article in articles:
        a, title, stamp = article.select_one('a[href]'), article.select_one('h2'), article.select_one('time')
        if not (a and title and stamp): continue
        title = helpers.compact(title.get_text(' ', strip=True)); n = helpers.norm(title)
        publication = (stamp.get('date') or stamp.get('datetime') or '')[:10]
        if not ('VERSION ESTENOGRAFICA' in n and 'CONFERENCIA' in n and
                ('SHEINBAUM' in n or 'MATUTINA' in n or 'MANANERA' in n)): continue
        dates = helpers.dates_in_title(title.replace('º', '').replace('°', ''))
        date = dates[0] if len(dates) == 1 else publication
        if START <= date <= end:
            entries.append({'date': date, 'title': title, 'published_date': publication,
                            'url': urljoin('https://www.gob.mx', a['href']), 'archive_section': section,
                            'archive_page': page, 'date_basis': 'title' if len(dates)==1 else 'publication_review'})
    pages = [int(m.group(1)) for a in soup.select('a[href]') if (m := re.search(r'[?&]page=(\d+)', a['href']))]
    assert pages or page > 1, 'First index lacks pagination; cannot establish discovery coverage'
    return entries, max(pages or [page])


def collect_page(root, entry):
    date, url = entry['date'], entry['url']
    key = digest(urlsplit(url).path.replace('/presidencia/es/', '/presidencia/').encode())[:12]
    raw = root/'raw'/f'{date}-{key}.html'; meta = raw.with_suffix('.json')
    if raw.exists() and meta.exists():
        record = json.loads(meta.read_text()); assert digest(raw.read_bytes()) == record['sha256']
    else:
        response = helpers.fetch(url)
        _, _, title = validate_page(response.content, date)
        raw.parent.mkdir(parents=True, exist_ok=True); raw.write_bytes(response.content)
        record = {**entry, 'title': title, 'url': response.url, 'requested_url': url,
                  'raw_path': str(raw), 'sha256': digest(response.content), 'bytes': len(response.content),
                  'retrieved_at': datetime.now(timezone.utc).isoformat(), 'http_status': response.status_code}
        atomic_json(meta, record)
    rows, headings = parse(raw.read_bytes(), date, record)
    return record, rows, headings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--through', required=True)
    parser.add_argument('--base', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--workers', type=int, default=6)
    parser.add_argument('--discover-only', action='store_true')
    args = parser.parse_args(); end = pd.Timestamp(args.through).strftime('%Y-%m-%d')
    root = args.base/'official_source'/f'through-{end}'
    records = []; jobs = []; errors = []
    for section in ['articulos', 'prensa']:
        entries, last = index_page(root, section, 1, end); records.extend(entries)
        jobs.extend((section, page) for page in range(2, last+1))
        print(f'{section}: {last} index pages', flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(index_page, root, sec, page, end):(sec,page) for sec,page in jobs}
        for i, future in enumerate(as_completed(futures), 1):
            try: records.extend(future.result()[0])
            except Exception as exc: errors.append({'index': futures[future], 'error': str(exc)})
            if i % 25 == 0: print(f'Indexes: {i}/{len(jobs)}', flush=True)
    unique = {}
    for r in records:
        key = urlsplit(r['url']).path.replace('/presidencia/es/', '/presidencia/')
        unique.setdefault(key, r)
    records = sorted(unique.values(), key=lambda x:(x['date'], x['url']))
    atomic_json(root/'discovery.json', {'complete': not errors, 'through': end, 'entries': records, 'errors': errors})
    if errors: raise RuntimeError(f'{len(errors)} index errors; rerun to resume')
    excluded = [{**r, 'exclusion_reason': EXCLUDED_INDEX_PATHS[urlsplit(r['url']).path]}
                for r in records if urlsplit(r['url']).path in EXCLUDED_INDEX_PATHS]
    records = [r for r in records if urlsplit(r['url']).path not in EXCLUDED_INDEX_PATHS]
    assert all(any(r['date'] == e['date'] and r['date_basis'] == 'title' for r in records) for e in excluded)
    atomic_json(root/'excluded_provisional_pages.json', excluded)
    print(f'Discovered {len(records)} transcript URLs on {len({r["date"] for r in records})} dates', flush=True)
    if args.discover_only: return
    old_root = args.base/'official_source/full'
    old = json.loads((old_root/'manifest.json').read_text())
    old_rows = pd.read_parquet(old_root/'auxiliar/transcript_rows.parquet')
    old_headings = pd.read_parquet(old_root/'auxiliar/speaker_headings.parquet')
    selected = {}; candidates = []; failures = []
    for page in old['pages']:
        date = page['date']
        if not START <= date <= end: continue
        assert digest(Path(page['raw_path']).read_bytes()) == page['sha256']
        day = old_rows[old_rows.date.eq(date)]; assert day.source_sha256.eq(page['sha256']).all()
        selected[date] = (page, day.to_dict('records'), old_headings[old_headings.date.eq(date)].to_dict('records'))
    pending = [r for r in records if r['date'] not in selected]
    atomic_json(root/'indexed_variants_of_existing_dates.json', [r for r in records if r['date'] in selected])
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(collect_page, root, r):r for r in pending}
        for future in as_completed(futures):
            entry = futures[future]
            try:
                page, day, headings = future.result(); date = page['date']
                candidates.append({'date': date, 'url': page['url'], 'sha256': page['sha256'],
                                   'raw_path': page['raw_path'], 'words': sum(r['word_count'] for r in day)})
                prior = selected.get(date)
                if not prior or sum(r['word_count'] for r in day) > sum(r['word_count'] for r in prior[1]):
                    selected[date] = (page, day, headings)
                print(f'{date}: parsed {len(day)} rows', flush=True)
            except Exception as exc:
                failures.append({'entry': entry, 'error': str(exc)}); print(f'{entry["date"]}: FAILED {exc}', flush=True)
    dates = sorted(selected); pages = [selected[d][0] for d in dates]
    rows = pd.DataFrame([r for d in dates for r in selected[d][1]])
    headings = pd.DataFrame([r for d in dates for r in selected[d][2]])
    assert not rows.duplicated(['date','source_row']).any()
    assert set(rows.date.dt.strftime('%Y-%m-%d')) == set(dates)
    out = root/'auxiliar'; out.mkdir(exist_ok=True)
    for name, df in [('transcript_rows', rows), ('speaker_headings', headings)]:
        df.to_parquet(out/f'{name}.parquet', index=False)
        df.to_csv(out/f'{name}.csv', index=False)
    pd.DataFrame(candidates).to_csv(out/'new_page_inventory.csv', index=False)
    missing = sorted({r['date'] for r in records} - set(dates))
    weekdays = sorted(set(pd.bdate_range(START, end).strftime('%Y-%m-%d')) - set(dates))
    pd.DataFrame({'date': weekdays, 'status': 'No collected transcript; may be holiday, no conference, or discovery gap'}).to_csv(out/'weekday_coverage_review.csv', index=False)
    atomic_json(root/'manifest.json', {'complete': not failures, 'discovery_complete': True,
        'requested_through': end, 'start_date': dates[0], 'end_date': dates[-1], 'dates': dates,
        'pages': pages, 'failures': failures, 'missing_indexed_dates': missing,
        'excluded_provisional_pages': excluded,
        'n_reused_dates': sum(d in old['dates'] for d in dates), 'n_new_dates': sum(d not in old['dates'] for d in dates),
        'n_rows': len(rows), 'n_words': int(rows.word_count.sum()),
        'limitations': ['Coverage is all matching indexed transcripts plus the preserved existing subset; weekday gaps are review leads, not proven missing conferences.',
                       'Existing source versions are preserved without refreshing. Additional URLs for existing dates are logged.',
                       'Raw HTML and text are preserved; longest successfully parsed version is selected for a new date with multiple pages.']})
    print(f'Collected {len(dates)} dates through {dates[-1]}; {len(failures)} page errors', flush=True)
    if failures: raise RuntimeError('Some official pages failed; see manifest and rerun to resume')


if __name__ == '__main__': main()

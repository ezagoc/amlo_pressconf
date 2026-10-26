"""Archive AMLO's official press transcripts without model/API calls.

Discovers both government archive sections, preserves HTML and provenance,
parses all article text, and compares available dates with the local CSVs.
"""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from difflib import SequenceMatcher
import hashlib
import html
import json
from pathlib import Path
import re
import sys
import time
import unicodedata
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode

from bs4 import BeautifulSoup, NavigableString
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from project_paths import media_path

BASE = 'https://www.gob.mx'
MONTHS = 'enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre'.split()
START, END = '2018-12-03', '2024-09-30'
VERSION = 'amlo-official-html-v1'
DATE_CORRECTIONS = {
    '/amlo/articulos/version-estenografica-conferencia-de-prensa-del-presidente-andres-manuel-lopez-obrador-del-17-de-diciembre-de-2023': {
        'date': '2023-12-18',
        'sha256': '32253f73096bac1280cca414b548cc431c2623eb6b142caaa7472fda56173517',
        'note': 'Official title says December 17 but publication date is December 18. The archived body exactly matches 363 of the 370 paragraphs in the December 18 CSV. Original title retained.'},
    '/amlo/prensa/conferencia-de-prensa-del-presidente-andres-manuel-lopez-obrador-17-de-enero-de-2019-187387': {
        'date': '2019-01-18',
        'sha256': '748dd7ccf6ea8bd31d3c39225ffca2eec9717fe9da06610a6aa88cdf1c78c1c9',
        'note': 'Official title says January 17 but publication date is January 18. The archived body matches 214 paragraphs of the January 18 CSV and only four of January 17; keep the original title and flag the correction.'},
}


def compact(s): return ' '.join(unicodedata.normalize('NFC', str(s)).split())
def norm(s): return ''.join(c for c in unicodedata.normalize('NFD', compact(s).upper()) if not unicodedata.combining(c))
def digest(b): return hashlib.sha256(b).hexdigest()
def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2)); tmp.replace(path)


def fetch(url):
    parts = urlsplit(url); query = dict(parse_qsl(parts.query))
    variants = [url]
    if '/archivo/' in parts.path:
        query.pop('order', None)  # Default archive ordering is DESC.
        variants.append(urlunsplit(parts._replace(query=urlencode(query))))
        query['idiom'] = 'es'
        variants.append(urlunsplit(parts._replace(query=urlencode(query))))
        variants.append(urlunsplit(parts._replace(query=urlencode(list(reversed(parse_qsl(parts.query)))))))
    else:
        if 'idiom' in query: query.pop('idiom')
        else: query['idiom'] = 'es'
        variants.append(urlunsplit(parts._replace(query=urlencode(query))))
        variants.append(url)
    for attempt in range(len(variants)):
        try:
            r = requests.get(variants[attempt], timeout=30)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == len(variants) - 1: raise
            time.sleep(2 ** attempt)


def decode_index(text):
    # Public archive endpoints return a Rails JS fragment containing HTML.
    return text.replace('\\"', '"').replace('\\/', '/').replace('\\n', '\n').replace("\\'", "'")


def archive_page(root, section, page):
    path = root / 'indexes' / f'{section}-desc-{page:04d}.html'
    meta = path.with_suffix('.json')
    url = f'{BASE}/amlo/archivo/{section}?order=DESC&page={page}'
    if path.exists() and meta.exists():
        b = path.read_bytes()
        assert digest(b) == json.loads(meta.read_text())['sha256']
    else:
        r = fetch(url); b = r.content
        soup = BeautifulSoup(decode_index(r.text), 'html.parser')
        if not soup.select('article'): raise ValueError(f'No archive entries: {url}')
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b)
        save(meta, {'url': r.url, 'sha256': digest(b), 'retrieved_at': datetime.now(timezone.utc).isoformat()})
        time.sleep(.15)
    soup = BeautifulSoup(decode_index(b.decode('utf-8')), 'html.parser')
    entries = []
    for item in soup.select('article'):
        a, heading, stamp = item.select_one('a[href]'), item.select_one('h2'), item.select_one('time')
        if not (a and heading and stamp): continue
        date = (stamp.get('date') or stamp.get('datetime') or '')[:10]
        title = compact(heading.get_text(' ', strip=True))
        n = norm(title)
        if START <= date <= END and 'CONFERENCIA' in n and any(t in n for t in ('PRENSA', 'MATUTINA', 'PRESIDENTE')):
            entries.append({'published_date': date, 'title': title, 'url': urljoin(BASE, a['href']),
                            'published_at': stamp.get('date') or stamp.get('datetime'),
                            'archive_section': section, 'archive_page': page})
    pages = [int(m.group(1)) for a in soup.select('a[href]') if (m := re.search(r'[?&]page=(\d+)', a['href']))]
    return entries, max(pages or [page])


def discover(root, workers):
    entries, jobs = [], []
    for section in ('articulos', 'prensa'):
        e, last = archive_page(root, section, 1); entries.extend(e)
        jobs.extend((section, page) for page in range(2, last + 1))
        print(f'{section}: {last} archive pages', flush=True)
    errors = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(archive_page, root, section, page): (section, page) for section, page in jobs}
        for count, future in enumerate(as_completed(futures), 1):
            try: entries.extend(future.result()[0])
            except Exception as exc: errors.append({'archive': futures[future], 'error': str(exc)})
            if count % 25 == 0: print(f'Archive pages: {count + 2}/{len(jobs) + 2}', flush=True)
    unique = {e['url']: e for e in entries}
    records = sorted(unique.values(), key=lambda x: (x['published_date'], x['url']))
    save(root / 'discovery.json', {'complete': not errors, 'entries': records, 'errors': errors})
    if errors: raise RuntimeError(f'{len(errors)} archive pages failed; rerun to resume')
    print(f'Discovered {len(records)} conference-page candidates', flush=True)
    return records


def dates_in_title(title):
    n = norm(title).lower()
    result = []
    for m in re.finditer(r'\b(\d{1,2})\s+de\s+(' + '|'.join(MONTHS) + r')(?:\s+de|,)?\s+(20\d{2})\b', n):
        day, month, year = m.groups()
        result.append(f'{int(year):04d}-{MONTHS.index(month)+1:02d}-{int(day):02d}')
    return result


def blocks(body):
    """Every visible text node appears exactly once; preserve inline spacing."""
    for bad in body.select('script,style,noscript'): bad.decompose()
    for br in body.select('br'): br.replace_with('\n')
    groups = []
    tags = {'p', 'li', 'div', 'td', 'th', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'pre'}
    for node in body.descendants:
        if not isinstance(node, NavigableString): continue
        parent = node.parent
        while parent != body and parent.name not in tags: parent = parent.parent
        if not groups or groups[-1][0] is not parent: groups.append((parent, []))
        groups[-1][1].append(str(node))
    raw = [''.join(parts) for _, parts in groups]
    assert compact(''.join(raw)) == compact(body.get_text()), 'Article text coverage mismatch'
    # Native line breaks also separate speakers sharing an HTML paragraph.
    return [compact(line) for block in raw for line in block.split('\n') if compact(line)]


def parse_page(data, entry, record):
    soup = BeautifulSoup(data, 'html.parser'); body = soup.select_one('.article-body')
    if body is None: raise ValueError('Missing article body')
    title = compact(soup.h1.get_text(' ', strip=True)) if soup.h1 else ''
    n = norm(title)
    header = norm(title + ' ' + (soup.h2.get_text(' ', strip=True) if soup.h2 else ''))
    if 'VESPERTINA' in header and 'MATUTINA' not in header:
        raise ValueError('Explicitly afternoon conference; retained outside morning subset')
    if 'CONFERENCIA' not in n or not any(t in n for t in ('PRENSA', 'MATUTINA', 'PRESIDENTE')): raise ValueError('Not a conference page')
    texts = blocks(body)
    if sum(len(x.split()) for x in texts) < 100: raise ValueError('Short/non-transcript page')
    dates = dates_in_title(title)
    if len(set(dates)) > 1: raise ValueError('Ambiguous conference title date')
    date = dates[0] if dates else entry['published_date']
    correction = DATE_CORRECTIONS.get(urlsplit(record['url']).path)
    if correction:
        if record['sha256'] != correction['sha256']: raise ValueError('Reviewed date-correction source hash changed')
        date = correction['date']
    if not START <= date <= END: raise ValueError('Outside AMLO conference period')
    label, heading, rows = 'SIN ETIQUETA', -1, []
    for i, text in enumerate(texts):
        m = re.match(r'^\s*[-–—¿¡]*\s*([^:]{2,250}):\s*(.*)$', text)
        content, kind = text, 'transcript'
        if m:
            prefix, rest = m.groups(); letters = ''.join(c for c in prefix if c.isalpha())
            if letters and letters.isupper():
                label = prefix.strip(); heading += 1; content = rest
                if not content: kind = 'speaker_heading'
        if label == 'SIN ETIQUETA': kind = 'unlabeled_opening'
        rows.append({'date': date, 'source_row': i, 'participant_raw': label, 'participant': norm(label),
                     'row_kind': kind, 'text': content, 'raw_text': text, 'word_count': len(content.split()),
                     'heading_index': heading, 'is_question_speaker': bool(re.match(r'^(PREGUNTA|INTERLOCUTOR|REPORTER|PERIODISTA)', norm(label))),
                     'source_url': record['url'], 'source_path': record['raw_path'], 'source_sha256': record['sha256'],
                     'parser_version': VERSION})
    if heading < 1: raise ValueError('No repeated explicit speaker labels; review as non-transcript')
    return rows, {'date': date, 'title': title, 'published_date': entry['published_date'],
                  'date_basis': 'reviewed_title_date_correction' if correction else ('title' if dates else 'archive_publication_date_review'),
                  'date_correction_note': correction['note'] if correction else None,
                  'publication_date_differs': date != entry['published_date'],
                  'n_rows': len(rows), 'n_words': sum(r['word_count'] for r in rows),
                  'n_unlabeled_rows': sum(r['row_kind'] == 'unlabeled_opening' for r in rows)}


def download(root, entry):
    key = digest(entry['url'].encode())[:16]
    name = f'{entry["published_date"]}-{key}'
    raw = root / 'raw' / f'{name}.html'; meta = raw.with_suffix('.json')
    if raw.exists() and meta.exists():
        record = json.loads(meta.read_text()); b = raw.read_bytes()
        assert digest(b) == record['sha256'], 'Archived HTML hash mismatch'
    else:
        r = fetch(entry['url']); b = r.content
        if BeautifulSoup(b, 'html.parser').select_one('.article-body') is None: raise ValueError('Missing article body')
        raw.parent.mkdir(parents=True, exist_ok=True); raw.write_bytes(b)
        record = {'requested_url': entry['url'], 'url': r.url, 'raw_path': str(raw),
                  'sha256': digest(b), 'retrieved_at': datetime.now(timezone.utc).isoformat(), 'bytes': len(b)}
        save(meta, record); time.sleep(.15)
    try:
        rows, audit = parse_page(b, entry, record)
        if entry.get('expected_date') and audit['date'] != entry['expected_date']:
            raise ValueError(f"Date differs from requested gap date: {audit['date']}")
    except ValueError as exc:
        return {'status': 'review_or_non_transcript', **entry, **record, 'reason': str(exc)}, []
    return {'status': 'parsed', **entry, **record, **audit}, rows


def local_inventory():
    result = []
    for path in sorted(media_path('data', '02-conferences', 'raw').glob('20*/**/mananera_*.csv')):
        m = re.fullmatch(r'mananera_(\d+)_(\d+)_(\d+)\.csv', path.name)
        if not m: raise ValueError(f'Unexpected filename: {path}')
        d, month, year = map(int, m.groups())
        date = f'{year:04d}-{month:02d}-{d:02d}'
        folder = re.fullmatch(r'([a-z]+) (\d+), (\d+)', norm(path.parent.name).lower())
        folder_date = None
        if folder and folder[1] in MONTHS:
            folder_date = f'{int(folder[3]):04d}-{MONTHS.index(folder[1])+1:02d}-{int(folder[2]):02d}'
        result.append({'date': date, 'folder_date': folder_date,
                       'folder_filename_date_conflict': bool(folder_date and date != folder_date),
                       'path': str(path), 'sha256': digest(path.read_bytes())})
    return result


def export(root, records, all_rows, errors, inventory):
    out = root / 'auxiliar'; out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(inventory).to_csv(out / 'original_csv_inventory.csv', index=False)
    pd.DataFrame([r for r in inventory if r['folder_filename_date_conflict']]).to_csv(out / 'original_date_conflicts.csv', index=False)
    pd.DataFrame(records).to_csv(out / 'official_page_inventory.csv', index=False)
    if not all_rows: raise ValueError('No transcripts parsed')
    # Keep every parsed page; use longest transcript per date for comparison only.
    frame = pd.DataFrame(all_rows).sort_values(['date', 'source_url', 'source_row'])
    frame.to_parquet(out / 'all_page_rows.parquet', index=False)
    parsed = [r for r in records if r['status'] == 'parsed']
    selected = {}
    for rec in sorted(parsed, key=lambda r: (-r['n_words'], r['url'])): selected.setdefault(rec['date'], rec)
    canonical = frame[frame.source_url.isin([r['url'] for r in selected.values()])].copy()
    canonical.to_parquet(out / 'transcript_rows.parquet', index=False)
    # Comparisons are descriptive: paragraph boundaries and punctuation can differ.
    comparisons = []
    for old in inventory:
        date = old['date']; item = {'date': date, 'csv_path': old['path'], 'official_available': date in selected}
        if date in selected:
            prior = pd.read_csv(old['path']).fillna(''); new = canonical[canonical.date == date]
            a = [compact(t) for t in prior.Texto if compact(t)]
            b = [compact(t) for t in new.text if compact(t)]
            matches = sum(m.size for m in SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks())
            item.update({'csv_rows': len(a), 'official_rows_with_text': len(b), 'exact_aligned_paragraphs': matches,
                         'csv_words': sum(len(t.split()) for t in a), 'official_words': int(new.word_count.sum()),
                         'official_url': selected[date]['url']})
        comparisons.append(item)
    cmp = pd.DataFrame(comparisons); cmp.to_csv(out / 'source_comparison.csv', index=False)
    local_dates = {r['date'] for r in inventory}; official_dates = set(selected)
    missing = sorted(local_dates - official_dates); extra = sorted(official_dates - local_dates)
    duplicates = {d: n for d, n in Counter(r['date'] for r in parsed).items() if n > 1}
    review = [r for r in records if r['status'] != 'parsed' or r.get('n_unlabeled_rows', 0)
              or r.get('date_basis') != 'title' or r.get('publication_date_differs')]
    pd.DataFrame(review).to_csv(out / 'page_review.csv', index=False)
    pd.DataFrame({'date': missing}).to_csv(out / 'missing_official_dates.csv', index=False)
    pd.DataFrame({'date': extra}).to_csv(out / 'additional_official_dates.csv', index=False)
    report = {'archive_download_complete': not errors,
              'indexed_archive_download_complete': not any(e['entry'].get('archive_section') != 'gap_lookup' for e in errors),
              'all_existing_dates_matched': not missing,
              'original_csv_files': len(inventory), 'original_distinct_dates': len(local_dates),
              'original_folder_filename_date_conflicts': sum(r['folder_filename_date_conflict'] for r in inventory),
              'official_parsed_pages': len(parsed), 'official_distinct_dates': len(official_dates),
              'official_rows': len(canonical), 'official_words': int(canonical.word_count.sum()),
              'missing_existing_dates': missing, 'additional_official_dates': extra,
              'multiple_official_pages_per_date': duplicates, 'download_errors': errors,
              'review_page_count': len(review), 'start_date': min(official_dates), 'end_date': max(official_dates),
              'parser_version': VERSION,
              'limitations': ['Official text may itself contain transcription or speaker-label errors.',
                              'Unlabeled opening text is preserved and flagged, not assigned to a speaker.',
                              'Longest parsed page per date is used for comparison; all page versions are retained.',
                              'No journalist/outlet, sentiment or question model extraction has been rerun.',
                              'Paragraph differences can reflect formatting, speaker labels or substantive omissions.']}
    save(root / 'manifest.json', {'report': report, 'pages': records})
    save(out / 'preparation_audit.json', report)
    review_dir = root / 'review'; review_dir.mkdir(exist_ok=True)
    (review_dir / 'index.html').write_text('<!doctype html><meta charset="utf-8"><title>AMLO official source audit</title>'
        '<style>body{font:15px/1.5 system-ui;margin:40px}pre{white-space:pre-wrap}table{border-collapse:collapse}td,th{padding:5px;border:1px solid #ddd}</style>'
        '<h1>AMLO official-source transcript archive</h1><p>Existing data preserved. Differences are review leads, not a count of omitted questions.</p>'
        '<p><a href="../auxiliar/source_comparison.csv">CSV comparison</a> · <a href="../auxiliar/page_review.csv">Page review</a></p>'
        '<pre>' + html.escape(json.dumps(report, ensure_ascii=False, indent=2)) + '</pre>' + cmp.to_html(index=False))
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=media_path('data', '02-conferences', 'official_source', 'full'))
    p.add_argument('--workers', type=int, default=3)
    p.add_argument('--discover-only', action='store_true')
    p.add_argument('--skip-discovery', action='store_true')
    p.add_argument('--rebuild-only', action='store_true', help='Reparse saved manifest pages and rebuild exports without network requests')
    args = p.parse_args(); root = args.output
    if args.rebuild_only:
        prior = json.loads((root / 'manifest.json').read_text())
        records, rows = [], []
        for rec in prior['pages']:
            b = Path(rec['raw_path']).read_bytes(); assert digest(b) == rec['sha256']
            rec = {k: v for k, v in rec.items() if k not in ('reason', 'date_correction_note')}
            try:
                parsed, details = parse_page(b, rec, rec)
                records.append({**rec, **details, 'status': 'parsed'}); rows.extend(parsed)
            except ValueError as exc:
                records.append({**rec, 'status': 'review_or_non_transcript', 'reason': str(exc)})
        recovered = {r['date'] for r in records if r['status'] == 'parsed'}
        errors = [e for e in prior['report']['download_errors'] if e['entry'].get('expected_date') not in recovered]
        export(root, records, rows, errors, local_inventory()); return
    if args.skip_discovery:
        discovery = json.loads((root / 'discovery.json').read_text()); assert discovery['complete']
        entries = discovery['entries']
    else: entries = discover(root, args.workers)
    if args.discover_only: return
    inventory = local_inventory()
    excluded = [e for e in entries if not any(t in norm(e['title']) for t in ('PRESIDENTE', 'MATUTINA'))]
    save(root / 'excluded_archive_entries.json', excluded)
    entries = [e for e in entries if any(t in norm(e['title']) for t in ('PRESIDENTE', 'MATUTINA'))]
    covered = {DATE_CORRECTIONS.get(urlsplit(e['url']).path, {}).get('date') or
               (dates_in_title(e['title']) or [e['published_date']])[0] for e in entries}
    for date in sorted({r['date'] for r in inventory} - covered):
        year, month, day = map(int, date.split('-'))
        stem = f'version-estenografica-conferencia-de-prensa-del-presidente-andres-manuel-lopez-obrador-del-{day}-de-{MONTHS[month-1]}-de-{year}'
        entries.append({'published_date': date, 'expected_date': date,
                        'title': 'Gap lookup: official presidential transcript URL pattern',
                        'url': f'{BASE}/amlo/articulos/{stem}?idiom=es', 'archive_section': 'gap_lookup'})
    print(f'Mañanera candidates including date-gap lookups: {len(entries)}; unrelated archive entries excluded: {len(excluded)}', flush=True)
    records, rows, errors = [], [], []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(download, root, entry): entry for entry in entries}
        for count, future in enumerate(as_completed(futures), 1):
            try:
                rec, parsed = future.result(); records.append(rec); rows.extend(parsed)
            except Exception as exc: errors.append({'entry': futures[future], 'error': str(exc)})
            if count % 25 == 0: print(f'Conference pages: {count}/{len(entries)}; errors: {len(errors)}', flush=True)
    export(root, records, rows, errors, inventory)
    if errors: raise RuntimeError(f'{len(errors)} downloads failed; rerun to resume')


if __name__ == '__main__': main()

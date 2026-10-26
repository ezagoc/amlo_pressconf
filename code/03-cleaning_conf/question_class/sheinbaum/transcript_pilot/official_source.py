"""Archive official stenographic pages for the pilot or existing 221-date subset."""
from __future__ import annotations
import argparse
from difflib import SequenceMatcher
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import time
import unicodedata

from bs4 import BeautifulSoup
import pandas as pd
import requests

from pipeline import DEFAULT_ROOT, require
from prepare import atomic_json, normalize, is_question_speaker

VERSION = 'official-html-v1'
MONTHS = ['', 'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
          'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
# The official October 28 title/date is correct; its URL slug says October 26.
URL_OVERRIDES = {
    '2024-10-28':'https://www.gob.mx/presidencia/es/articulos/version-estenografica-conferencia-de-prensa-de-la-presidenta-claudia-sheinbaum-pardo-del-26-de-octubre-de-2024?idiom=es',
    '2025-01-09':'https://www.gob.mx/presidencia/articulos/version-estenografica-conferencia-de-prensa-de-la-presidenta-claudia-sheinbaum-pardo-del-9-de-enero-de-2025-387640',
    '2025-04-23':'https://www.gob.mx/presidencia/es/articulos/version-estenografica-conferencia-de-prensa-de-la-presidenta-claudia-sheinbaum-pardo-del-23-de-abril-de-2025-396092?idiom=es',
    '2025-05-19':'https://www.gob.mx/presidencia/articulos/version-estenografica-conferencia-de-prensa-de-la-presidenta-claudia-sheinbaum-pardo-del-19-de-mayo-de-2025-398121',
}

def digest(data):
    return hashlib.sha256(data).hexdigest()

def compact(text):
    return ' '.join(unicodedata.normalize('NFC', text).split())

def candidates(date):
    if date in URL_OVERRIDES:
        yield URL_OVERRIDES[date]
    d = pd.Timestamp(date)
    phrase = f'{d.day}-de-{MONTHS[d.month]}-de-{d.year}'
    stems = [f'version-estenografica-conferencia-de-prensa-de-la-presidenta-claudia-sheinbaum-pardo-del-{phrase}',
             f'version-estenografica-conferencia-de-prensa-la-presidenta-claudia-sheinbaum-pardo-del-{phrase}',
             f'version-estenografica-conferencia-de-prensa-matutina-del-{phrase}',
             f'version-estenografica-conferencia-de-prensa-de-la-presidenta-claudia-sheinbaum-pardo-del-dia-{phrase}']
    for stem in stems:
        yield f'https://www.gob.mx/presidencia/articulos/{stem}?idiom=es'
    if d.day<10:
        yield f'https://www.gob.mx/presidencia/articulos/{stems[0].replace(f"del-{d.day}-",f"del-{d.day:02d}-")}?idiom=es'

def validate_page(data, date):
    soup = BeautifulSoup(data, 'html.parser')
    body = soup.select_one('.article-body')
    title = compact(soup.h1.get_text(' ', strip=True)) if soup.h1 else ''
    d = pd.Timestamp(date)
    title_normal = normalize(title)
    require(body is not None and len(body.get_text()) > 1000, 'Missing/short article body')
    require('VERSION ESTENOGRAFICA' in title_normal, f'Not a transcript: {title}')
    require(re.search(rf'\b0?{d.day}(?:º|°)? DE {MONTHS[d.month].upper()} DE {d.year}\b',title_normal),
            f'Transcript date mismatch: {title}')
    return soup, body, title

def download(date, root):
    raw = root/'raw'/f'{date}.html'
    meta = root/'raw'/f'{date}.json'
    if raw.exists() and meta.exists():
        record = json.loads(meta.read_text())
        require(digest(raw.read_bytes()) == record['sha256'], 'Archive hash mismatch')
        validate_page(raw.read_bytes(), date)
        return record
    failures = []
    for url in candidates(date):
        try:
            r = requests.get(url, timeout=45)
            r.raise_for_status()
            _, _, title = validate_page(r.content, date)
        except (requests.RequestException, ValueError) as exc:
            failures.append(f'{url}: {type(exc).__name__}: {exc}')
            continue
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_bytes(r.content)
        record = {'date':date, 'requested_url':url, 'url':r.url, 'title':title,
                  'retrieved_at':datetime.now(timezone.utc).isoformat(),
                  'sha256':digest(r.content), 'bytes':len(r.content), 'raw_path':str(raw),
                  'content_type':r.headers.get('content-type'), 'http_status':r.status_code}
        atomic_json(meta, record)
        return record
    raise RuntimeError(f'No official page found for {date}: ' + '\n'.join(failures))

def speaker_prefix(text):
    """Only explicit uppercase label before a colon; bold alone is not a label."""
    m = re.match(r'^([^:]{2,250}):\s*(.*)$', text, re.S)
    if not m:
        return None, text
    prefix, remainder = m.groups()
    letters = ''.join(c for c in prefix if c.isalpha())
    if letters and letters.isupper():
        return prefix.strip(), remainder
    return None, text

def parse(data, date, record):
    _, body, _ = validate_page(data, date)
    # Some official openings use a leaf div instead of a paragraph.
    block_tags=['p','li','div']
    blocks = [el for el in body.find_all(block_tags) if not el.find(block_tags)]
    all_strings = [compact(str(s)) for s in body.find_all(string=True) if compact(str(s))]
    selected_strings = [compact(str(s)) for el in blocks for s in el.find_all(string=True) if compact(str(s))]
    require(all_strings == selected_strings, 'Unparsed or duplicated text in article body')
    rows, headings = [], []
    label = 'SIN ETIQUETA'
    heading_index = -1
    for block_index, block in enumerate(blocks):
        # Inline <em>/<strong> can split a word. Preserve native text-node
        # spacing; only HTML line breaks introduce an extra separator.
        for br in block.find_all('br'):
            br.replace_with('\n')
        text = compact(block.get_text())
        if not text:
            continue
        metadata = label=='SIN ETIQUETA' and bool(re.fullmatch(
            r'VE-\d+|Versión estenográfica|Palacio Nacional, a .+|Conferencia de Prensa', text, re.I))
        new_label, content = speaker_prefix(text)
        if new_label:
            label = new_label
            heading_index += 1
            headings.append({'date':date, 'heading_index':heading_index,
                             'html_block':block_index, 'label':label,
                             'first_source_row':len(rows)})
        if content:
            rows.append({'date':pd.Timestamp(date), 'source_row':len(rows),
                         'participant_raw':'METADATOS DEL DOCUMENTO (NO HABLA)' if metadata else label,
                         'participant':normalize('METADATOS DEL DOCUMENTO (NO HABLA)' if metadata else label),
                         'row_kind':'document_metadata' if metadata else 'transcript',
                         'text':content, 'source_path':record['raw_path'],
                         'source_url':record['url'], 'source_sha256':record['sha256'],
                         'html_block':block_index, 'heading_index':heading_index,
                         'is_question_speaker':is_question_speaker(label),
                         'word_count':len(content.split()), 'parser_version':VERSION})
    require(len(rows)>10 and len(headings)>0, 'Unexpectedly sparse parsed transcript')
    require(all(r['participant_raw']!='SIN ETIQUETA' for r in rows), 'Unlabeled opening content')
    return rows, headings

def compare_and_bridge(source, root, official):
    """Ordered exact-text alignment; never reuse old numeric row IDs directly."""
    old = pd.read_parquet(source/'auxiliar/transcript_rows.parquet')
    summaries, alignment, differences, bridges, omitted = [], [], [], [], []
    evidence = pd.read_parquet(source/'api_extraction/full/auxiliar/journalist_media_evidence.parquet')
    for date, new in official.groupby('date'):
        prior=old[old.date==date].sort_values('source_row')
        new=new.sort_values('source_row')
        a=[compact(t) for t in prior.text]; b=[compact(t) for t in new.text]
        mapping={}
        for tag, i, j, k, l in SequenceMatcher(None,a,b,autojunk=False).get_opcodes():
            if tag=='equal':
                mapping.update(zip(range(i,j), range(k,l)))
            else:
                differences.append({'date':str(date.date()), 'operation':tag,
                    'github_rows':';'.join(map(str,range(i,j))),
                    'official_rows':';'.join(map(str,range(k,l))),
                    'github_text':'\n'.join(a[i:j]), 'official_text':'\n'.join(b[k:l]),
                    'official_labels':' | '.join(new.iloc[k:l].participant_raw.unique()),
                    'interpretation':'Unmatched block; inspect for additions, formatting, splits/merges, or revisions.'})
        for i,k in mapping.items():
            alignment.append({'date':str(date.date()), 'github_row':i, 'official_row':k,
                'github_label':prior.iloc[i].participant_raw, 'official_label':new.iloc[k].participant_raw,
                'normalized_label_changed':prior.iloc[i].participant!=new.iloc[k].participant})
        summaries.append({'date':str(date.date()), 'github_rows':len(prior), 'official_rows':len(new),
            'exact_aligned_paragraphs':len(mapping), 'github_unmatched_paragraphs':len(prior)-len(mapping),
            'official_unmatched_paragraphs':len(new)-len(mapping),
            'github_words':int(prior.word_count.sum()), 'official_words':int(new.word_count.sum()),
            'official_question_labeled_paragraphs':int(new.is_question_speaker.sum()),
            'source_url':new.source_url.iloc[0]})
        for ev in evidence[evidence.date==date].to_dict('records'):
            ids=[int(n) for n in ev['source_rows'].split(';')]
            if not all(n in mapping for n in ids):
                omitted.append({'date':str(date.date()), 'github_source_rows':ev['source_rows'],
                                'reason':'Introduction not fully matched by ordered exact-text alignment'})
                continue
            ns=[mapping[n] for n in ids]
            require(all(a[i]==b[k] for i,k in zip(ids,ns)), 'Evidence bridge mismatch')
            ev.update(github_source_rows=ev['source_rows'], source_rows=';'.join(map(str,ns)),
                      source_row=ns[0], intro_row=ns[0], source_path=new.source_path.iloc[0],
                      evidence_text='\n'.join(new.iloc[n].text for n in ns),
                      alignment_basis='ordered_exact_text_after_whitespace_normalization')
            bridges.append(ev)
    out=root/'auxiliar'
    for name, values in [('source_comparison',summaries),('paragraph_alignment',alignment),
                         ('source_differences',differences),('journalist_media_evidence',bridges)]:
        df=pd.DataFrame(values);df.to_csv(out/f'{name}.csv',index=False)
        df.to_parquet(out/f'{name}.parquet',index=False)
    pd.DataFrame(omitted,columns=['date','github_source_rows','reason']).to_csv(out/'unmapped_introductions.csv',index=False)
    metadata=official[official.row_kind=='document_metadata'].copy()
    def date_conflict(r):
        m=re.search(r'\b(\d{1,2}) de (\w+) de (\d{4})\b',r.text,re.I)
        if not m or m[2].lower() not in MONTHS:return False
        return pd.Timestamp(int(m[3]),MONTHS.index(m[2].lower()),int(m[1]))!=r.date
    metadata['internal_date_conflicts_with_page_title']=[date_conflict(r) for r in metadata.itertuples()]
    metadata.to_csv(out/'document_metadata.csv',index=False)
    atomic_json(out/'preparation_audit.json', {'parser_version':VERSION,
        'article_text_coverage':'All nonempty article-body text nodes covered exactly once, in order.',
        'n_conferences':len(summaries), 'n_official_rows':len(official),
        'n_bridged_introduction_records':len(bridges), 'n_unmapped_introduction_records':len(omitted),
        'n_document_metadata_rows':len(metadata),
        'internal_date_conflict_dates':metadata.loc[metadata.internal_date_conflicts_with_page_title.astype(bool),'date'].dt.strftime('%Y-%m-%d').tolist(),
        'comparison_note':'Unmatched paragraphs are not automatically omissions; inspect difference blocks.'})
    review=root/'review';review.mkdir(exist_ok=True)
    parts=['<!doctype html><meta charset="utf-8"><title>Official source comparison</title>',
        '<style>body{font:16px/1.5 system-ui;max-width:1250px;margin:40px auto;padding:0 20px}table{border-collapse:collapse;font-size:13px}td,th{border:1px solid #ddd;padding:6px}pre{white-space:pre-wrap;font:inherit}details{border-top:1px solid #ccc;padding:12px}summary{cursor:pointer}</style>',
        '<h1>Official transcripts versus GitHub CSVs: ten-conference pilot</h1>',
        '<p>All official article-body text is retained in source order. Matching uses exact text after Unicode and whitespace normalization. Unmatched blocks can represent missing content, partial paragraphs, or punctuation changes; they are not automatically classified as omissions. Speaker-label changes also include harmless expansions of titles and names.</p>',
        pd.DataFrame(summaries).drop(columns='source_url').rename(columns=lambda c:c.replace('_',' ')).to_html(index=False),
        '<h2>Official sources</h2>']
    for s in summaries:
        parts.append(f'<p><a href="{html.escape(s["source_url"])}">{s["date"]}</a> · <a href="../raw/{s["date"]}.html">archived HTML</a></p>')
    parts.append('<h2>Text differences</h2>')
    for r in differences:
        parts.append(f'<details><summary>{r["date"]}: {r["operation"]}; GitHub rows {r["github_rows"] or "none"}; official rows {r["official_rows"] or "none"}</summary><h3>GitHub text</h3><pre>{html.escape(r["github_text"])}</pre><h3>Official text</h3><p>{html.escape(r["official_labels"])}</p><pre>{html.escape(r["official_text"])}</pre></details>')
    (review/'index.html').write_text('\n'.join(parts))

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, default=DEFAULT_ROOT)
    p.add_argument('--output', type=Path, default=DEFAULT_ROOT/'official_source/pilot-10')
    p.add_argument('--download-only', action='store_true')
    p.add_argument('--scope', choices=['pilot','full'], default='pilot', help='full collects existing source dates only; no model calls')
    args = p.parse_args()
    if args.scope=='full':
        dates=sorted(pd.read_parquet(args.source/'auxiliar/transcript_rows.parquet').date.dt.strftime('%Y-%m-%d').unique())
        if args.output==DEFAULT_ROOT/'official_source/pilot-10':args.output=DEFAULT_ROOT/'official_source/full'
    else:
        dates = pd.read_csv(args.source/'api_extraction/pilot-10/auxiliar/journalist_media_coverage.csv').date.tolist()
    records, rows, headings = [], [], []
    failures=[]
    for date in dates:
        was_cached=(args.output/'raw'/f'{date}.html').exists()
        try:
            record = download(date, args.output)
            if not args.download_only:
                day, labels = parse(Path(record['raw_path']).read_bytes(), date, record)
        except Exception as exc:
            failures.append({'date':date,'error':str(exc)})
            print(f'{date}: FAILED {exc}',flush=True)
            if args.scope=='pilot':raise
            continue
        records.append(record)
        print(f'{date}: archived {record["bytes"]:,} bytes', flush=True)
        if not args.download_only:
            rows.extend(day); headings.extend(labels)
            print(f'  {len(day)} paragraphs; {len(labels)} explicit headings', flush=True)
        if args.scope=='full' and not was_cached:time.sleep(.3)
    atomic_json(args.output/'manifest.json', {'parser_version':VERSION, 'requested_dates':dates,
        'dates':[r['date'] for r in records], 'pages':records, 'failures':failures,
        'complete':not failures})
    if not args.download_only:
        out=args.output/'auxiliar';out.mkdir(exist_ok=True)
        for name, values in [('transcript_rows', rows), ('speaker_headings', headings)]:
            df=pd.DataFrame(values)
            df.to_parquet(out/f'{name}.parquet', index=False)
            df.to_csv(out/f'{name}.csv', index=False)
        compare_and_bridge(args.source,args.output,pd.DataFrame(rows))

if __name__ == '__main__':
    main()

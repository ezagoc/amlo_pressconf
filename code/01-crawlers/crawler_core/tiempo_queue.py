"""Read-only comparison of frozen sitemap candidates, old evidence and pilots.

Outputs are an audit/queue, not article extraction. Sitemap news dates/titles
remain discovery evidence. No fetch, slug-only equivalence, political filter,
old-record deletion, or implicit batch execution is provided here.
"""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
import re
import sqlite3
import uuid
from collections import Counter, defaultdict
from contextlib import ExitStack, contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from crawler_core import tiempo_pilot as pilot
from crawler_core.tiempo_discovery import validate as validate_discovery
from crawler_core.tiempo_review import fields_digest

SEED = 'Kevin-Task3-Expanded-Validation-20260926-v1'
ROUTES = frozenset({'noticia', 'local', 'nacional', 'espectaculos', 'deportes', 'internacional',
                    'crealo', 'tecnologia', 'cultura', 'economia', 'opinion', 'cronos', 'videos', 'seguridad'})
MONTHS = tuple([f'2024-{m:02}' for m in range(5, 13)] + [f'2025-{m:02}' for m in range(1, 13)])
CANDIDATE_COLUMNS = {
    'candidate_id': 'INTEGER', 'url_key': 'TEXT', 'url': 'TEXT', 'route': 'TEXT', 'url_issue': 'TEXT',
    'occurrence_count': 'INTEGER', 'raw_urls_json': 'TEXT', 'discovery_dates_json': 'TEXT',
    'discovery_days_json': 'TEXT', 'discovery_titles_json': 'TEXT', 'discovery_refs_json': 'TEXT',
    'discovery_day': 'TEXT', 'discovery_date_status': 'TEXT', 'discovery_scope': 'TEXT',
    'identity_class': 'TEXT', 'queue_class': 'TEXT', 'baseline_protected': 'INTEGER',
    'baseline_classes_json': 'TEXT', 'baseline_record_ids_json': 'TEXT', 'pilot_refs_json': 'TEXT',
    'source_quality_issues_json': 'TEXT', 'matching_notes_json': 'TEXT',
}


class QueueError(ValueError):
    """Changed/incomplete evidence; a final queue must not be published."""


def j(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


@contextmanager
def read_only(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise QueueError(f'Missing input database: {path}')
    if path.with_name(path.name + '-wal').exists() and path.with_name(path.name + '-wal').stat().st_size:
        raise QueueError('Freeze/checkpoint the input database before queue construction; WAL is nonempty.')
    con = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA query_only=ON')
    try:
        yield con
    finally:
        con.close()


def normalize_url(value):
    if not isinstance(value, str) or not value.strip():
        raise QueueError('Missing URL')
    try:
        p = urlsplit(value.strip())
        port = p.port
    except ValueError as exc:
        raise QueueError('Malformed URL') from exc
    if (p.scheme.lower() not in {'http', 'https'} or p.hostname not in {'tiempo.com.mx', 'www.tiempo.com.mx'}
            or p.username or p.password or port not in {None, 80, 443}):
        raise QueueError('URL has an unexpected origin, credential or port')
    # Exactly the old baseline's light normalization. Keep query and path case.
    return urlunsplit(('https', p.netloc.lower().removeprefix('www.'), p.path.rstrip('/') or '/', p.query, ''))


def url_evidence(value):
    try:
        key = normalize_url(value)
        p = urlsplit(value.strip())
        parts = [s for s in p.path.split('/') if s]
        if '//' in p.path or len(parts) != 2 or not parts[-1]:
            return key, parts[0] if parts else None, 'unrecognized_article_path'
        if parts[0] not in ROUTES:
            return key, parts[0], 'unknown_route_review'
        if p.query:
            return key, parts[0], 'query_url_review'
        return key, parts[0], None
    except QueueError:
        return None, None, 'invalid_url_review'


def valid_identity(value):
    key, _, issue = url_evidence(value)
    return key if issue is None else None


def date_evidence(raw_values):
    """Compare every advertised date at common precision, never pick a winner."""
    values = sorted(set(v.strip() if isinstance(v, str) else '' for v in raw_values))
    parsed, issues = [], []
    for value in values:
        try:
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                parsed.append(date.fromisoformat(value))
            elif re.fullmatch(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?', value):
                parsed.append(datetime.fromisoformat(value.replace('Z', '+00:00')))
            else:
                raise ValueError('missing or malformed')
        except ValueError:
            issues.append('missing' if not value else 'invalid')
    days = sorted({p.date().isoformat() if isinstance(p, datetime) else p.isoformat() for p in parsed})
    conflict = len(days) > 1
    timed = [p for p in parsed if isinstance(p, datetime)]
    for a, b in itertools.combinations(timed, 2):
        if (a.tzinfo is None) != (b.tzinfo is None) or a != b:
            conflict = True
    status = 'conflict' if conflict else 'invalid' if 'invalid' in issues else 'missing' if issues else 'consistent'
    return {'discovery_day': days[0] if len(days) == 1 and status == 'consistent' else None,
            'discovery_date_status': status, 'discovery_days_json': j(days), 'discovery_dates_json': j(values)}


def discovery_scope(day):
    if not day:
        return 'undetermined'
    if '2018-01-01' <= day <= '2025-12-31':
        return 'target_2018_2025'
    if '2015-01-01' <= day <= '2017-12-31':
        return 'deferred_2015_2017'
    if day.startswith('2026-'):
        return 'outside_2026'
    return 'outside_target_other'


def classify(row, old_classes=(), protected=False, reviews=()):
    """Keep identity evidence independent of the discovery-based priority scope."""
    classes = set(old_classes)
    warnings = sorted({r['source_quality_issue'] for r in reviews if r.get('source_quality_issue')})
    if reviews:
        signatures = {r.get('fields_sha256') for r in reviews}
        states = {r.get('qa_status') for r in reviews}
        if (any(r.get('manual_review_status') != 'reviewed' or r.get('manual_review_result') in {'FAIL', 'REQUIRES_REVIEW', None} for r in reviews)
                or len(signatures) > 1 or len(states) > 1):
            identity = 'known_pilot_review_required'
        elif 'error' in states:
            identity = 'known_reviewed_pilot_error'
        elif warnings:
            identity = 'reuse_reviewed_pilot_with_source_warning'
        else:
            identity = 'reuse_reviewed_pilot'
    elif 'old_structural_pass_unreviewed' in classes:
        identity = 'old_structural_pass_retained'
    elif 'old_missing_required_field' in classes:
        identity = 'old_missing_fields_review'
    elif 'old_short_no_error' in classes:
        identity = 'old_short_review'
    elif 'old_error' in classes:
        identity = 'old_error_review'
    elif classes or protected:
        identity = 'old_other_review'
    else:
        identity = 'new_urls'
    if row.get('url_issue'):
        queue = row['url_issue']
    elif row['discovery_date_status'] == 'conflict':
        queue = 'discovery_date_conflict'
    elif row['discovery_date_status'] != 'consistent':
        queue = 'discovery_date_unresolved'
    elif row['discovery_scope'] != 'target_2018_2025':
        queue = row['discovery_scope']
    else:
        queue = identity
    return {'identity_class': identity, 'queue_class': queue, 'baseline_protected': int(protected),
            'baseline_classes_json': j(sorted(classes)), 'source_quality_issues_json': j(warnings)}


def rank_value(month, key, seed=SEED):
    return hashlib.sha256((seed + '\n' + month + '\n' + key).encode('utf-8')).hexdigest()


def select_validation(rows, seed=SEED):
    groups = defaultdict(list)
    seen = set()
    for row in rows:
        if row['url_key'] in seen:
            raise QueueError('Duplicate normalized candidate in validation input')
        seen.add(row['url_key'])
        day = row.get('discovery_day') or ''
        if row['queue_class'] == 'new_urls' and '2024-05-28' <= day <= '2025-12-31':
            groups[day[:7]].append(row)
    selected, shortages = [], []
    for month in MONTHS:
        ranked = sorted(groups[month], key=lambda r: (rank_value(month, r['url_key'], seed), r['url_key']))
        shortages.append({'month': month, 'eligible': len(ranked), 'selected': min(20, len(ranked)), 'shortfall': max(0, 20-len(ranked))})
        for position, row in enumerate(ranked[:20], 1):
            selected.append({**row, 'month_rank': position, 'rank_sha256': rank_value(month, row['url_key'], seed),
                             'validation_batch': (position-1)//4 + 1})
    selected.sort(key=lambda r: (r['validation_batch'], r['discovery_day'][:7], r['month_rank']))
    for n, row in enumerate(selected, 1):
        row['sample_id'] = f'T3V{n:04d}'
        row['expected_year'] = row['discovery_day'][:4]
        row['expected_kind'] = 'article_candidate'
        row['selection_reason'] = f"Fixed SHA256 rank {row['month_rank']} within {row['discovery_day'][:7]}; seed={seed}; sitemap date is unverified discovery evidence, not article metadata"
    return selected, shortages


def pilot_reuse(pilot_dirs):
    by_key, evidence, hashes = defaultdict(list), [], {}
    for directory in pilot_dirs:
        directory = Path(directory).resolve()
        manifest_path = pilot.safe_path(directory, 'manifest.json')
        manifest = json.loads(manifest_path.read_text())
        inputs = pilot.safe_path(directory, Path('inputs') / manifest['input_name'])
        if not inputs.is_file():
            raise QueueError('Pilot input copy is missing; restore the bound input before reuse')
        items, input_hash = pilot.load_input(inputs)
        if input_hash != manifest['input_sha256'] or items != manifest['items']:
            raise QueueError('Pilot input/manifest mismatch; cannot reuse reviews')
        db = directory / 'pilot.sqlite'
        with read_only(db) as con:
            pilot.validate_bound_state(con, directory, items, input_hash)
            if con.execute('SELECT count(*) FROM fetch_attempts WHERE completed_at IS NULL').fetchone()[0]:
                raise QueueError('Pilot still has unfinished attempts')
            rows = [json.loads(r[0]) for r in con.execute('SELECT payload_json FROM articles ORDER BY ordinal')]
        if len(rows) != len(items):
            raise QueueError('Pilot is incomplete')
        context = pilot.review_context(directory, persist=False)
        reviewed, _ = pilot.reviewed_rows(rows, directory, context)
        for row in reviewed:
            if row.get('manual_review_status') != 'reviewed':
                raise QueueError('Pilot review is missing/stale; do not silently issue another request')
            reference = {'run': str(directory), 'sample_id': row['sample_id'], 'url': row['url'],
                         'snapshot_sha256': row['snapshot_sha256'], 'fields_sha256': fields_digest(row),
                         'snapshot_path': row['snapshot_path'], 'qa_status': row['qa_status'], 'error': row.get('error'),
                         'manual_review_status': row['manual_review_status'], 'manual_review_result': row['manual_review_result'],
                         'source_quality_issue': row.get('source_quality_issue'), 'review_note': row.get('manual_review_note')}
            keys = {normalize_url(row['url'])}
            keys.update(k for value in [row.get('canonical_url'), row.get('final_url')] if (k := valid_identity(value)))
            for key in keys:
                by_key[key].append(reference)
            evidence.append({'run': str(directory), 'sample_id': row['sample_id'], 'row_json': j(row)})
            snap = pilot.safe_path(directory, row['snapshot_path'])
            hashes[str(snap)] = sha_file(snap)
            hashes[str(snap.with_suffix('.json'))] = sha_file(snap.with_suffix('.json'))
        for path in [db, manifest_path, inputs, directory/'review_annotations.json', directory/'export_manifest.json', *context['paths']]:
            hashes[str(path)] = sha_file(path)
    return dict(by_key), evidence, hashes


def _export_candidates(con, output):
    import pyarrow as pa
    import pyarrow.parquet as pq
    schema = pa.schema([(k, pa.int64() if typ == 'INTEGER' else pa.string()) for k, typ in CANDIDATE_COLUMNS.items()])
    writers, parquet = {}, {}
    with ExitStack() as stack:
        def writer(name):
            if name not in writers:
                folder = output if name == 'candidates' else output/'classes'
                folder.mkdir(exist_ok=True)
                stream = stack.enter_context((folder/(name+'.csv')).open('w', encoding='utf-8-sig', newline=''))
                writers[name] = csv.DictWriter(stream, fieldnames=list(CANDIDATE_COLUMNS))
                writers[name].writeheader()
                parquet[name] = pq.ParquetWriter(folder/(name+'.parquet'), schema, compression='gzip')
            return writers[name], parquet[name]
        writer('candidates')
        try:
            cursor = con.execute('SELECT * FROM candidates ORDER BY candidate_id')
            for batch in iter(lambda: cursor.fetchmany(8192), []):
                rows = [dict(r) for r in batch]
                cw, pw = writer('candidates'); cw.writerows(rows); pw.write_table(pa.Table.from_pylist(rows, schema=schema))
                groups = defaultdict(list)
                for row in rows:
                    groups[row['queue_class']].append(row)
                for name, group in groups.items():
                    cw, pw = writer(name); cw.writerows(group); pw.write_table(pa.Table.from_pylist(group, schema=schema))
        finally:
            for pw in parquet.values():
                pw.close()


def _write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')


def _export_unmatched_baseline(con, output):
    """Keep old records absent from current discovery visible, never queued anew."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    schema = pa.schema([(name, pa.int64() if name in {'baseline_record_id', 'file_id'} else pa.string())
                        for name in ['baseline_record_id', 'file_id', 'kind', 'old_class', 'url', 'url_key']])
    with (output/'baseline_unmatched_records.csv').open('w', encoding='utf-8-sig', newline='') as stream, \
            pq.ParquetWriter(output/'baseline_unmatched_records.parquet', schema, compression='gzip') as parquet:
        writer = csv.DictWriter(stream, fieldnames=schema.names)
        writer.writeheader()
        cursor = con.execute('SELECT * FROM baseline_unmatched_records ORDER BY baseline_record_id')
        for batch in iter(lambda: cursor.fetchmany(8192), []):
            rows = [dict(row) for row in batch]
            writer.writerows(rows)
            parquet.write_table(pa.Table.from_pylist(rows, schema=schema))


def build_queue(discovery_dir, baseline_index, pilot_dirs, output_dir, *, expected_maps=652, seed=SEED):
    """Publish a new audit directory only after discovery closes and inputs verify."""
    discovery_dir, baseline_index, output_dir = map(lambda p: Path(p).resolve(), [discovery_dir, baseline_index, output_dir])
    pilot_dirs = [Path(p).resolve() for p in pilot_dirs]
    repo = Path(__file__).resolve().parents[3]
    if output_dir.exists() or output_dir.is_relative_to(repo) or any(output_dir.is_relative_to(p) for p in [discovery_dir, *pilot_dirs]) or output_dir == baseline_index:
        raise QueueError('Output must be a new independent audit directory outside repository/input runs')
    with read_only(baseline_index) as baseline:
        if baseline.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise QueueError('Baseline integrity check failed')
    source_hashes = {str(baseline_index): sha_file(baseline_index)}
    # A queue is reproducible only with the discovery/review validation code
    # that accepted it. Reject concurrent edits just like changed data inputs.
    for name in ['tiempo_queue.py', 'tiempo_discovery.py', 'tiempo_pilot.py', 'tiempo_review.py']:
        path = Path(__file__).resolve().with_name(name)
        source_hashes[str(path)] = sha_file(path)
    freeze_file = baseline_index.with_name('frozen_index_manifest.json')
    if freeze_file.exists():
        frozen = json.loads(freeze_file.read_text())
        expected = next((r['sha256'] for r in frozen['frozen_artifacts'] if r['file'] == baseline_index.name), None)
        if expected != source_hashes[str(baseline_index)]:
            raise QueueError('Frozen baseline index changed')
        source_hashes[str(freeze_file)] = sha_file(freeze_file)
    db = discovery_dir/'discovery.sqlite'
    with read_only(db) as discovery:
        states = dict(discovery.execute('SELECT state,count(*) FROM maps GROUP BY state'))
        if states != {'complete': expected_maps}:
            raise QueueError(f'Discovery has not closed: {states}; require {expected_maps} complete maps')
        for row in discovery.execute('SELECT snapshot_path FROM maps'):
            if not isinstance(row[0], str) or not (discovery_dir/row[0]).resolve().is_relative_to(discovery_dir):
                raise QueueError('Discovery snapshot escapes its input directory')
        manifest = validate_discovery(discovery_dir, discovery)
        if len(manifest['sitemaps']) != expected_maps:
            raise QueueError('Discovery manifest count mismatch')
        for path in [db, discovery_dir/'manifest.json', discovery_dir/'index.xml']:
            source_hashes[str(path)] = sha_file(path)
        for row in discovery.execute('SELECT snapshot_path,snapshot_sha256 FROM maps'):
            path = (discovery_dir/row[0]).resolve()
            if not path.is_relative_to(discovery_dir):
                raise QueueError('Discovery snapshot escapes its input directory')
            source_hashes[str(path)] = row[1]
        reviews, pilot_rows, pilot_hashes = pilot_reuse(pilot_dirs)
        source_hashes.update(pilot_hashes)
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        stage = output_dir.with_name('.'+output_dir.name+'.incomplete-'+uuid.uuid4().hex)
        stage.mkdir()
        con = None
        try:
            con = sqlite3.connect(stage/'queue.sqlite', uri=True)
            con.row_factory = sqlite3.Row
            con.execute('PRAGMA synchronous=FULL')
            con.execute('ATTACH DATABASE ? AS old', (baseline_index.as_uri()+'?mode=ro&immutable=1',))
            con.executescript('''
              CREATE TABLE discovery_occurrences(sitemap_url TEXT,ordinal INTEGER,url TEXT,url_key TEXT,
                discovery_publication_date TEXT,discovery_day TEXT,discovery_title TEXT,sitemap_lastmod TEXT,
                route TEXT,candidate_article INTEGER,discovery_issue TEXT,url_issue TEXT,PRIMARY KEY(sitemap_url,ordinal));
              CREATE TABLE baseline_matches(candidate_id INTEGER,baseline_record_id INTEGER,relation_bits INTEGER,
                PRIMARY KEY(candidate_id,baseline_record_id));
              CREATE TABLE pilot_evidence(run TEXT,sample_id TEXT,row_json TEXT,PRIMARY KEY(run,sample_id));
            ''')
            definitions = ','.join(k+' '+typ+(' PRIMARY KEY' if k=='candidate_id' else ' UNIQUE' if k=='url_key' else '') for k,typ in CANDIDATE_COLUMNS.items())
            con.execute('CREATE TABLE candidates('+definitions+')')
            con.executemany('INSERT INTO pilot_evidence VALUES(:run,:sample_id,:row_json)', pilot_rows)
            cursor = discovery.execute('SELECT * FROM entries ORDER BY sitemap_url,ordinal')
            for batch in iter(lambda: cursor.fetchmany(8192), []):
                inserts = []
                for raw in batch:
                    row = dict(raw)
                    key, route, issue = url_evidence(row['url'])
                    key = key or 'invalid:' + hashlib.sha256((row['sitemap_url']+'\n'+str(row['ordinal'])).encode()).hexdigest()
                    inserts.append((row['sitemap_url'],row['ordinal'],row['url'],key,row['discovery_publication_date'],row['discovery_day'],
                                    row['discovery_title'],row['sitemap_lastmod'],route,row['candidate_article'],row['discovery_issue'],issue))
                con.executemany('INSERT INTO discovery_occurrences VALUES('+','.join('?' for _ in range(12))+')', inserts)
                con.commit()
            con.execute('CREATE INDEX occurrences_key ON discovery_occurrences(url_key)')
            # Sorting by the identity key makes grouping and IDs deterministic.
            cursor = con.execute('SELECT * FROM discovery_occurrences ORDER BY url_key,sitemap_url,ordinal')
            for n, (key, records) in enumerate(itertools.groupby(cursor, lambda r:r['url_key']), 1):
                group = [dict(r) for r in records]
                raw_urls = sorted({r['url'] for r in group if r['url']})
                representative = min(raw_urls, key=lambda u: (not u.startswith('https://'), u)) if raw_urls else None
                dates = date_evidence([r['discovery_publication_date'] for r in group])
                row = {'candidate_id':n,'url_key':key,'url':representative,'route':group[0]['route'],
                       'url_issue':next((r['url_issue'] for r in group if r['url_issue']),None),
                       'occurrence_count':len(group),'raw_urls_json':j(raw_urls),**dates,
                       'discovery_titles_json':j(sorted({r['discovery_title'] for r in group if r['discovery_title']})),
                       'discovery_refs_json':j([[r['sitemap_url'],r['ordinal']] for r in group]),
                       'discovery_scope':discovery_scope(dates['discovery_day'])}
                values = [row.get(k) for k in CANDIDATE_COLUMNS]
                con.execute('INSERT INTO candidates VALUES('+','.join('?' for _ in values)+')', values)
            con.commit()
            for column, bit in [('url_id',1),('canonical_id',2),('final_id',4)]:
                extra = '' if bit==1 else "AND u.host='tiempo.com.mx' AND u.slug_candidate IS NOT NULL AND instr(u.url_key,'?')=0"
                con.execute(f'''INSERT INTO baseline_matches SELECT c.candidate_id,r.record_id,{bit}
                  FROM candidates c JOIN old.urls u ON u.url_key=c.url_key JOIN old.records r ON r.{column}=u.url_id
                  WHERE c.url_key NOT LIKE 'invalid:%' {extra}
                  ON CONFLICT(candidate_id,baseline_record_id) DO UPDATE SET relation_bits=relation_bits | excluded.relation_bits''')
            con.executescript('''
              CREATE INDEX matches_record ON baseline_matches(baseline_record_id);
              CREATE TABLE baseline_unmatched_records AS
                SELECT r.record_id baseline_record_id,r.file_id,f.kind,r.old_class,u.url,u.url_key
                FROM old.records r JOIN old.files f USING(file_id) LEFT JOIN old.urls u ON u.url_id=r.url_id
                WHERE NOT EXISTS(SELECT 1 FROM baseline_matches m WHERE m.baseline_record_id=r.record_id);
              CREATE TABLE baseline_flags AS SELECT m.candidate_id,max(f.kind='export') protected,
                group_concat(DISTINCT r.old_class) classes,group_concat(DISTINCT r.record_id) record_ids
                FROM baseline_matches m JOIN old.records r ON r.record_id=m.baseline_record_id JOIN old.files f USING(file_id)
                GROUP BY m.candidate_id;
              CREATE UNIQUE INDEX flags_candidate ON baseline_flags(candidate_id);
            ''')
            cursor = con.execute('SELECT c.*,b.protected,b.classes,b.record_ids FROM candidates c LEFT JOIN baseline_flags b USING(candidate_id) ORDER BY candidate_id')
            for raw in cursor:
                row = dict(raw)
                evidence = reviews.get(row['url_key'], [])
                decision = classify(row, (row['classes'] or '').split(',') if row['classes'] else [], bool(row['protected']), evidence)
                decision.update(baseline_record_ids_json=j(sorted(int(s) for s in row['record_ids'].split(',')) if row['record_ids'] else []),
                                pilot_refs_json=j(evidence), matching_notes_json=j(['Old fields are structurally checked, not manually certified. No slug-only merge.']))
                con.execute('UPDATE candidates SET '+','.join(k+'=?' for k in decision)+' WHERE candidate_id=?', [*decision.values(),row['candidate_id']])
            con.commit()
            con.execute('CREATE INDEX queue_class_idx ON candidates(queue_class,discovery_day)')
            selected, shortages = select_validation((dict(r) for r in con.execute("SELECT * FROM candidates WHERE queue_class='new_urls'")), seed=seed)
            sample_headers = ['sample_id','url','expected_year','selection_reason','expected_kind','candidate_id','url_key','discovery_day','month_rank','rank_sha256','validation_batch']
            for name, rows in [('validation_400.csv',selected), *[(f'validation_batch_{b:02}.csv',[r for r in selected if r['validation_batch']==b]) for b in range(1,6)]]:
                with (stage/name).open('w',encoding='utf-8-sig',newline='') as stream:
                    writer=csv.DictWriter(stream,fieldnames=sample_headers,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
            con.execute('CREATE TABLE validation_selection(candidate_id INTEGER PRIMARY KEY,sample_id TEXT,month_rank INTEGER,rank_sha256 TEXT,batch INTEGER)')
            con.executemany('INSERT INTO validation_selection VALUES(?,?,?,?,?)',[(r['candidate_id'],r['sample_id'],r['month_rank'],r['rank_sha256'],r['validation_batch']) for r in selected])
            con.commit()
            _export_candidates(con,stage)
            _export_unmatched_baseline(con,stage)
            counts = lambda field: dict(con.execute(f'SELECT {field},count(*) FROM candidates GROUP BY {field}'))
            baseline_coverage = {}
            for kind, total in con.execute('SELECT f.kind,count(*) FROM old.records r JOIN old.files f USING(file_id) GROUP BY f.kind'):
                unmatched = con.execute('SELECT count(*) FROM baseline_unmatched_records WHERE kind=?',(kind,)).fetchone()[0]
                baseline_coverage[kind] = {'records':total,'matched_records':total-unmatched,'unmatched_records_preserved':unmatched}
            summary={'author':'Kevin','candidate_urls':con.execute('SELECT count(*) FROM candidates').fetchone()[0],
                     'discovery_occurrences':con.execute('SELECT count(*) FROM discovery_occurrences').fetchone()[0],
                     'closed_sitemaps':expected_maps,'queue_classes':counts('queue_class'),'identity_classes':counts('identity_class'),
                     'discovery_scopes':counts('discovery_scope'),'pilot_requested_rows_verified':len(pilot_rows),
                     'validation_selected':len(selected),'validation_batches':dict(Counter(r['validation_batch'] for r in selected)),
                     'monthly_selection':shortages,'seed':seed,'baseline_index':str(baseline_index),
                     'baseline_record_coverage_by_container':baseline_coverage,
                     'baseline_coverage_note':'Database and export contain overlapping records; do not add them as unique articles. Unmatched old records remain protected in their original files; absence from current sitemaps does not imply deletion.',
                     'matching_relation_bits':{'1':'requested URL','2':'stored canonical','4':'stored final URL'},
                     'scope_note':'Discovery dates/titles only; no article fields filled. Preserve old records; current pilot warnings remain. No political-section filter, no requests made.'}
            _write_json(stage/'summary.json',summary)
            if con.execute('PRAGMA quick_check').fetchone()[0]!='ok':
                raise QueueError('Output SQLite integrity check failed')
            con.close()
            for path, sha in source_hashes.items():
                wal = Path(path).with_name(Path(path).name + '-wal')
                if path.endswith('.sqlite') and wal.exists() and wal.stat().st_size:
                    raise QueueError('An input database acquired a WAL during queue construction')
                if sha_file(path)!=sha:
                    raise QueueError(f'Input changed during queue construction: {path}')
            artifacts=[{'path':str(p.relative_to(stage)),'bytes':p.stat().st_size,'sha256':sha_file(p)} for p in sorted(stage.rglob('*')) if p.is_file()]
            _write_json(stage/'queue_manifest.json',{'format_version':1,'author':'Kevin','created_at':datetime.now(timezone.utc).isoformat(),
                       'source_sha256':source_hashes,'program_sha256':sha_file(Path(__file__)),'allowed_routes':sorted(ROUTES),
                       'seed':seed,'sample_rule':'20/month then four/month in each of five batches; shortage never replaced; no outcome-based reselection.',
                       'artifacts':artifacts,'network_requests':0,'status':'PASS'})
            stage.rename(output_dir)
            return summary
        except BaseException as exc:
            if con is not None:
                con.close()
            _write_json(stage/'INCOMPLETE.json',{'status':'INCOMPLETE','error_type':type(exc).__name__,'error':str(exc),'not_a_final_queue':True})
            raise

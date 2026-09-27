"""Frozen Tiempo sitemap discovery, retaining news dates as discovery evidence.

No publication dates or titles here replace article-page extraction. Each
advertised URL is retained, including unknown routes and duplicate occurrences.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import time
import uuid
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit

from crawler_core.capabilities import fetch
from crawler_core.tiempo_pilot import atomic_bytes, clean, digest, exclusive_run, json_bytes, now, append_note

SM = "http://www.sitemaps.org/schemas/sitemap/0.9"
NEWS = "http://www.google.com/schemas/sitemap-news/0.9"
INDEX_URL = "https://www.tiempo.com.mx/sitemap.xml"
ILLEGAL_XML_CONTROLS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def sitemap_number(url):
    p = urlsplit(url)
    m = re.fullmatch(r"/sitemaps/sitemap_(\d+)\.xml", p.path)
    if p.scheme not in {"http", "https"} or p.hostname not in {"www.tiempo.com.mx", "tiempo.com.mx"} or p.port not in {None,80,443} or p.username or p.password or p.query or p.fragment or not m:
        raise ValueError(f"Unrecognized advertised sitemap: {url}")
    return int(m[1])


def parse_index(text):
    root = ET.fromstring(text)
    if root.tag != f"{{{SM}}}sitemapindex":
        raise ValueError("Expected a sitemap index, not an HTML response or article urlset")
    urls = [x.findtext(f"{{{SM}}}loc") for x in root.findall(f"{{{SM}}}sitemap")]
    if not urls or len(set(urls)) != len(urls):
        raise ValueError("Empty or duplicate sitemap index")
    numbers=[sitemap_number(u) for u in urls]
    if len(set(numbers)) != len(numbers):
        raise ValueError('Duplicate numbered sitemap aliases in index; inspect before freezing')
    return urls


def _urlset_tree(text):
    """Strict XML, with one explicit repair for literal C0 noise in news:title.

    The input is never modified. Temporarily replace each illegal character by
    a unique valid token, strictly parse the whole document, and accept removal
    only if *every* token occurs in the direct text/CDATA of the correct
    namespace's news:title under url/news:news. Controls in loc, dates, tails,
    attributes, comments, processing instructions or XML syntax are rejected.
    Other malformed XML and numeric references to invalid characters stay errors.
    DTD/entity declarations are deliberately excluded from this repair path.
    """
    try:
        return ET.fromstring(text), {}
    except ET.ParseError as original_error:
        if not ILLEGAL_XML_CONTROLS.search(text):
            raise
        if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.IGNORECASE):
            raise ValueError("Illegal XML controls in a document with a DTD/entity declaration; repair refused") from original_error
        prefix = "TIEMPO_XML_CONTROL_" + uuid.uuid4().hex + "_"
        while prefix in text:
            prefix = "TIEMPO_XML_CONTROL_" + uuid.uuid4().hex + "_"
        tokens = {}

        def replace(match):
            token = prefix + str(len(tokens)) + "__"
            tokens[token] = ord(match.group())
            return token

        candidate = ILLEGAL_XML_CONTROLS.sub(replace, text)
        try:
            root = ET.fromstring(candidate)
        except ET.ParseError:
            # Preserve the original raw-document error position, not a column
            # offset shifted by temporary tokens in this rejected candidate.
            raise original_error
        if root.tag != f"{{{SM}}}urlset":
            raise ValueError("Expected urlset XML")
        repaired, seen = {}, set()
        token_pattern = re.compile(re.escape(prefix) + r"\d+__")
        for ordinal, item in enumerate(root.findall(f"{{{SM}}}url")):
            codepoints = Counter()
            for news in item.findall(f"{{{NEWS}}}news"):
                for title in news.findall(f"{{{NEWS}}}title"):
                    def remove(match):
                        token = match.group()
                        if token not in tokens or token in seen:
                            raise ValueError("Ambiguous illegal XML control repair; refused")
                        seen.add(token)
                        codepoints[tokens[token]] += 1
                        return ""
                    if title.text:
                        title.text = token_pattern.sub(remove, title.text)
            if codepoints:
                repaired[ordinal] = "illegal_xml_controls_removed_from_news_title:" + ",".join(
                    f"U+{codepoint:04X}={count}" for codepoint, count in sorted(codepoints.items()))
        if seen != set(tokens):
            raise ValueError("Illegal XML controls outside direct news:title text; repair refused") from original_error
        return root, repaired


def parse_urlset(text):
    root, title_repairs = _urlset_tree(text)
    if root.tag != f"{{{SM}}}urlset":
        raise ValueError("Expected urlset XML")
    rows = []
    for ordinal, item in enumerate(root.findall(f"{{{SM}}}url")):
        url = item.findtext(f"{{{SM}}}loc")
        news = item.find(f"{{{NEWS}}}news")
        nd = news.findtext(f"{{{NEWS}}}publication_date") if news is not None else None
        nt = news.findtext(f"{{{NEWS}}}title") if news is not None else None
        lm = item.findtext(f"{{{SM}}}lastmod")
        day, issue = None, None
        if nd:
            try:
                if re.fullmatch(r'\d{4}-\d{2}-\d{2}',nd):
                    day = date.fromisoformat(nd).isoformat()
                elif re.fullmatch(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?',nd):
                    day = datetime.fromisoformat(nd.replace('Z','+00:00')).date().isoformat()
                else:
                    raise ValueError('Malformed full news publication_date')
            except (ValueError, TypeError):
                issue = "invalid_news_publication_date"
        else:
            issue = "missing_news_publication_date"
        p = urlsplit(url or "")
        parts = [x for x in p.path.split("/") if x]
        accepted = p.scheme in {"https", "http"} and p.hostname in {"www.tiempo.com.mx", "tiempo.com.mx"} and len(parts) >= 2 and not p.username and not p.password
        issue = issue if accepted else "unrecognized_article_url"
        if ordinal in title_repairs:
            issue = ";".join(filter(None, (issue, title_repairs[ordinal])))
        rows.append({"ordinal": ordinal, "url": url, "discovery_publication_date": nd,
                     "discovery_day": day, "discovery_title": nt, "sitemap_lastmod": lm,
                     "route": parts[0] if parts else None, "candidate_article": accepted,
                     "discovery_issue": issue})
    if not rows:
        raise ValueError("Empty urlset; needs explicit investigation")
    return rows


def connect(run):
    c = sqlite3.connect(run / "discovery.sqlite")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA synchronous=FULL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def freeze(index_file: Path, run: Path, capture_metadata=None):
    if run.exists() and any(run.iterdir()):
        raise ValueError("Discovery freeze requires a new directory")
    content = index_file.read_bytes()
    urls = parse_index(content.decode("utf-8"))
    run.mkdir(parents=True, exist_ok=True)
    atomic_bytes(run / "index.xml", content)
    manifest = {"format_version": 1, "author": "Kevin", "created_at": now(),
                "index_url": INDEX_URL, "index_sha256": digest(content), "sitemaps": urls,
                "capture_metadata": capture_metadata, "publication_date_policy": "news date is discovery evidence only; article page decides final publication date"}
    atomic_bytes(run / "manifest.json", json_bytes(manifest))
    c = connect(run)
    c.executescript('''
      CREATE TABLE maps(url TEXT PRIMARY KEY, number INTEGER NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, snapshot_path TEXT, snapshot_sha256 TEXT, row_count INTEGER);
      CREATE TABLE entries(sitemap_url TEXT NOT NULL REFERENCES maps(url), ordinal INTEGER NOT NULL, url TEXT, discovery_publication_date TEXT, discovery_day TEXT, discovery_title TEXT, sitemap_lastmod TEXT, route TEXT, candidate_article INTEGER NOT NULL, discovery_issue TEXT, PRIMARY KEY(sitemap_url,ordinal));
      CREATE INDEX entry_url ON entries(url);
      CREATE INDEX entry_day ON entries(discovery_day);
      CREATE TABLE attempts(sitemap_url TEXT, attempt INTEGER, captured_at TEXT, status INTEGER, error TEXT, snapshot_path TEXT, snapshot_sha256 TEXT, reused_recon INTEGER, PRIMARY KEY(sitemap_url,attempt));
    ''')
    with c:
        c.executemany("INSERT INTO maps(url,number,state) VALUES (?,?,'pending')", [(u, sitemap_number(u)) for u in urls])
    c.close()
    append_note(run, f"Froze {len(urls)} sitemap entrances from the saved official index. Preserve every URL occurrence; news publication_date is only discovery evidence. No shared outputs changed.")
    return manifest


def validate(run, c):
    m = json.loads((run / "manifest.json").read_text())
    raw = (run / "index.xml").read_bytes()
    if digest(raw) != m['index_sha256'] or parse_index(raw.decode()) != m['sitemaps']:
        raise ValueError("Frozen sitemap index no longer matches its manifest")
    if {x[0] for x in c.execute('SELECT url FROM maps')} != set(m['sitemaps']):
        raise ValueError("Discovery database does not match frozen index")
    for row in c.execute('SELECT url,number,state FROM maps'):
        if row['number'] != sitemap_number(row['url']) or row['state'] not in {'pending','failed','complete'}:
            raise ValueError('Sitemap number/state is inconsistent with frozen identity')
    for row in c.execute("SELECT * FROM maps WHERE state='complete'"):
        p = run / row['snapshot_path']
        if not p.is_file() or digest(p.read_bytes()) != row['snapshot_sha256']:
            raise ValueError(f"Saved completed sitemap missing/changed: {row['url']}")
        count = c.execute('SELECT COUNT(*) FROM entries WHERE sitemap_url=?', (row['url'],)).fetchone()[0]
        if count != row['row_count']:
            raise ValueError(f"Entry count changed: {row['url']}")
        expected=parse_urlset(p.read_text())
        columns=('ordinal','url','discovery_publication_date','discovery_day','discovery_title','sitemap_lastmod','route','candidate_article','discovery_issue')
        actual=[tuple(x) for x in c.execute('SELECT '+','.join(columns)+' FROM entries WHERE sitemap_url=? ORDER BY ordinal',(row['url'],))]
        if actual != [tuple(r[k] for k in columns) for r in expected]:
            raise ValueError(f"Discovery entries changed from captured sitemap: {row['url']}")
    return m


def summary(run):
    database = (run / "discovery.sqlite").resolve()
    if not database.is_file():
        raise ValueError("Missing discovery database; status must not create an empty replacement")
    c = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
    state = {x[0]: x[1] for x in c.execute('SELECT state,COUNT(*) FROM maps GROUP BY state')}
    result = {"author": "Kevin", "updated_at": now(), "map_states": state,
              "index_entrances_processed": not (state.get('pending', 0) or state.get('failed', 0)),
              "url_occurrences": c.execute('SELECT COUNT(*) FROM entries').fetchone()[0],
              "unique_urls": c.execute('SELECT COUNT(DISTINCT url) FROM entries').fetchone()[0],
              "by_discovery_year": {str(x[0]): x[1] for x in c.execute("SELECT substr(discovery_day,1,4), COUNT(DISTINCT url) FROM entries GROUP BY 1")},
              "discovery_issues": {str(x[0]): x[1] for x in c.execute('SELECT discovery_issue,COUNT(*) FROM entries GROUP BY 1')},
              "not_a_claim": "Processing all advertised sitemap entrances does not prove all historical website articles are advertised or recoverable."}
    c.close()
    atomic_bytes(run / 'discovery_summary.json', json_bytes(result))
    return result


def run_discovery(run, *, limit=100, pause_seconds=1.0, timeout=45.0, priority_from=500,
                  retry_failed=False, recon_dir=None, fetcher=None, min_free_bytes=10*1024**3):
    if not 1 <= limit <= 1000 or pause_seconds < 1 or timeout <= 0:
        raise ValueError('Explicit 1–1000 entrance limit and >=1 second pause required')
    if not (run / 'discovery.sqlite').is_file():
        raise ValueError('Missing discovery database; restore the bound state')
    fetcher = fetcher or fetch
    cache = {}
    if recon_dir:
        for line in (recon_dir / 'requests.jsonl').read_text().splitlines():
            r = json.loads(line)
            if r.get('status') == 200 and not r.get('error'):
                p = recon_dir / r['snapshot']
                if digest(p.read_bytes()) != r['snapshot_sha256']:
                    raise ValueError('Recon snapshot hash mismatch')
                try:
                    number = sitemap_number(r['url'])
                except ValueError:
                    continue
                cache[number] = (r, p)
    with exclusive_run(run):
        c = connect(run)
        validate(run, c)
        backup_dir = run / 'backups' / now().replace(':','').replace('+','_')
        backup_dir.mkdir(parents=True)
        with sqlite3.connect(backup_dir / 'discovery.sqlite') as b:
            c.backup(b)
        for name in ('manifest.json','Kevin_NOTE.md','discovery_summary.json'):
            if (run / name).is_file(): shutil.copy2(run / name, backup_dir / name)
        append_note(run, f"Discovery step: at most {limit} frozen entrances; pause={pause_seconds}s; retries={retry_failed}. Database backed up before step.")
        states = "('pending','failed')" if retry_failed else "('pending')"
        todo = list(c.execute(f"SELECT * FROM maps WHERE state IN {states} ORDER BY CASE WHEN number>=? THEN 0 ELSE 1 END, number LIMIT ?", (priority_from,limit)))
        completed = 0
        for item in todo:
            did_fetch = False
            if shutil.disk_usage(run).free < min_free_bytes:
                append_note(run, 'Stopped before request: disk space below threshold.')
                break
            number, attempt = item['number'], item['attempts']+1
            # The live index advertises legacy HTTP/non-www locations. Preserve
            # them as source evidence while using the already verified HTTPS
            # same-site endpoint for transport; never silently relabel the index.
            request_url = f'https://www.tiempo.com.mx/sitemaps/sitemap_{number}.xml'
            stem = f"snapshots/map_{number:04d}_attempt_{attempt:02d}"
            meta_path, body_path = run / (stem+'.json'), run / (stem+'.xml')
            if meta_path.exists():
                meta = json.loads(meta_path.read_text())
                if meta['url'] != item['url'] or not body_path.exists() or digest(body_path.read_bytes()) != meta['snapshot_sha256']:
                    raise ValueError('Interrupted discovery snapshot identity mismatch')
                text = body_path.read_bytes().decode('utf-8')
            else:
                captured = now()
                network_id = None
                if number in cache:
                    cached, path = cache[number]
                    response = {**cached, 'text': path.read_bytes().decode('utf-8')}
                    reused = True
                    # Cached HTTP responses are not new downloads. Keep their
                    # original capture time (or explicitly unknown), and record
                    # the current processing time separately below.
                    captured = cached.get('captured_at') or cached.get('started_at')
                    capture_time_source = 'cached.captured_at' if cached.get('captured_at') else 'cached.started_at' if cached.get('started_at') else 'unknown_cached_capture_time'
                else:
                    network_id = uuid.uuid4().hex
                    atomic_bytes(run / f'network_calls/{network_id}_started.json',
                                 json_bytes({'request_url':request_url,'advertised_url':item['url'],'started_at':captured,'attempt':attempt}))
                    response = clean(fetcher(request_url, timeout))
                    reused = False
                    did_fetch = True
                text = response.get('text') or ''
                content = text.encode('utf-8')
                meta = {k:v for k,v in clean(response).items() if k!='text'}
                meta.update(url=item['url'], request_url=request_url, captured_at=captured, reused_recon=reused, network_request_id=network_id,
                            snapshot_sha256=digest(content), snapshot_path=str(body_path.relative_to(run)), processed_at=now())
                if reused:
                    meta.update(cache_snapshot=str(path), capture_time_source=capture_time_source,
                                source_capture={'url':cached.get('url'), 'captured_at':captured,
                                                'snapshot':cached.get('snapshot'), 'snapshot_sha256':cached.get('snapshot_sha256')})
                atomic_bytes(body_path, content)
                atomic_bytes(meta_path, json_bytes(meta))
                if network_id:
                    atomic_bytes(run / f'network_calls/{network_id}_saved.json',json_bytes(meta))
            error, rows = meta.get('error'), []
            status = meta.get('status')
            if status != 200:
                error = error or f'http_status_{status}'
            if not error:
                try:
                    rows = parse_urlset(text)
                except (ValueError, ET.ParseError) as exc:
                    error = f'{type(exc).__name__}: {exc}'
            with c:
                c.execute('INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?)',
                          (item['url'], attempt, meta['captured_at'], status, error, meta['snapshot_path'],meta['snapshot_sha256'],int(meta['reused_recon'])))
                if not error:
                    c.executemany('INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?)',
                        [(item['url'],r['ordinal'],r['url'],r['discovery_publication_date'],r['discovery_day'],r['discovery_title'],r['sitemap_lastmod'],r['route'],int(r['candidate_article']),r['discovery_issue']) for r in rows])
                c.execute('UPDATE maps SET state=?,attempts=?,last_error=?,snapshot_path=?,snapshot_sha256=?,row_count=? WHERE url=?',
                          ('failed' if error else 'complete', attempt,error,meta['snapshot_path'],meta['snapshot_sha256'],len(rows),item['url']))
            completed += 1
            print(json.dumps({'sitemap':number,'rows':len(rows),'error':error,'step_processed':completed},ensure_ascii=False),flush=True)
            if completed % 10 == 0:
                summary(run)
            if error and (status in {403,429} or isinstance(status,int) and status>=500):
                append_note(run, f'Stopped after saving response: {error}; review before retry.')
                break
            if did_fetch:
                time.sleep(pause_seconds)
        c.close()
        result = summary(run)
        append_note(run, f"Discovery step finished with {completed} entrances processed; map states {result['map_states']}.")
        return result

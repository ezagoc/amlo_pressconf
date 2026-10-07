"""Resumable discovery for the Milenio and Grupo Reforma news sitemaps."""

from __future__ import annotations

import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pandas as pd

from crawler_core.capabilities import fetch, markdown_table
from crawler_core.category_pagination import infer_topic_from_url
from crawler_core.sitemaps import parse_sitemap_xml


SOURCE_CONFIGS = {
    "reforma": {
        "source_name": "Reforma",
        "source_url": "https://www.reforma.com/",
        "sitemap_url": "https://www.reforma.com/sitemap_index.xml",
    },
    "elnorte": {
        "source_name": "El Norte",
        "source_url": "https://www.elnorte.com/",
        "sitemap_url": "https://www.elnorte.com/sitemap_index.xml",
    },
    "milenio": {
        "source_name": "Milenio",
        "source_url": "https://www.milenio.com/",
        "sitemap_url": "https://www.milenio.com/sitemap/sitemap-articles-index.xml",
    },
}

GRUPO_REFORMA_IDS = {"reforma", "elnorte"}
GRUPO_REFORMA_ARTICLE_RE = re.compile(r"/ar\d+/?$", flags=re.I)
STATIC_EXTENSIONS = (
    ".css",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".svg",
    ".webp",
    ".xml",
)


@dataclass(frozen=True)
class NewsSitemapOutputs:
    """Paths written for one source."""

    discovered_csv: Path
    discovered_parquet: Path | None
    report_path: Path
    parquet_error: str | None = None


def configured_sources(source_ids: list[str] | None = None) -> list[dict[str, str]]:
    """Return validated source configurations in requested order."""
    selected = source_ids or list(SOURCE_CONFIGS)
    unknown = [source_id for source_id in selected if source_id not in SOURCE_CONFIGS]
    if unknown:
        raise ValueError(f"Unsupported source IDs: {', '.join(unknown)}")
    return [dict(SOURCE_CONFIGS[source_id], source_id=source_id) for source_id in selected]


def initialize_state_db(path: Path) -> None:
    """Create discovery tables if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS discovered_urls (
                source_id TEXT NOT NULL,
                source_name TEXT,
                source_url TEXT,
                url TEXT NOT NULL,
                canonical_url TEXT,
                date_published TEXT,
                lastmod TEXT,
                topic TEXT,
                discovery_strategy TEXT,
                sitemap_url TEXT,
                sitemap_status INTEGER,
                discovered_at TEXT,
                status INTEGER,
                error TEXT,
                PRIMARY KEY (source_id, url)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sitemap_state (
                source_id TEXT NOT NULL,
                sitemap_url TEXT NOT NULL,
                status INTEGER,
                sitemap_kind TEXT,
                urls_seen INTEGER NOT NULL DEFAULT 0,
                urls_kept INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                completed INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (source_id, sitemap_url)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS source_state (
                source_id TEXT PRIMARY KEY,
                complete INTEGER NOT NULL DEFAULT 0,
                stop_reason TEXT,
                sitemap_count INTEGER NOT NULL DEFAULT 0,
                url_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )


def discover_news_sitemaps(
    *,
    source_ids: list[str] | None,
    state_db_path: Path,
    resume: bool,
    max_sitemaps_per_source: int | None,
    max_urls_per_source: int | None,
    timeout: float,
    pause_seconds: float,
    request_retries: int,
    retry_backoff_seconds: float,
    workers: int,
) -> dict[str, dict[str, object]]:
    """Discover configured sources and persist every completed sitemap."""
    initialize_state_db(state_db_path)
    summaries: dict[str, dict[str, object]] = {}
    for source in configured_sources(source_ids):
        source_id = source["source_id"]
        if not resume:
            clear_source_state(state_db_path, source_id)
        summaries[source_id] = discover_one_source(
            source,
            state_db_path=state_db_path,
            max_sitemaps=max_sitemaps_per_source,
            max_urls=max_urls_per_source,
            timeout=timeout,
            pause_seconds=pause_seconds,
            request_retries=request_retries,
            retry_backoff_seconds=retry_backoff_seconds,
            workers=max(1, workers),
        )
    return summaries


def discover_one_source(
    source: dict[str, str],
    *,
    state_db_path: Path,
    max_sitemaps: int | None,
    max_urls: int | None,
    timeout: float,
    pause_seconds: float,
    request_retries: int,
    retry_backoff_seconds: float,
    workers: int,
) -> dict[str, object]:
    """Discover one source from its official sitemap index."""
    source_id = source["source_id"]
    print(f"\n=== Official sitemap source: {source_id} ===")
    root_result = fetch_and_parse_sitemap(
        source["sitemap_url"],
        timeout=timeout,
        request_retries=request_retries,
        retry_backoff_seconds=retry_backoff_seconds,
    )
    if root_result["error"]:
        upsert_sitemap_state(state_db_path, source_id, root_result, completed=False)
        summary = finish_source_state(
            state_db_path,
            source_id,
            complete=False,
            stop_reason=f"root_sitemap_error: {root_result['error']}",
        )
        print(f"!!! {source_id}: {summary['stop_reason']}")
        return summary

    initial_children = list(root_result["sitemaps"])
    queue = initial_children or [source["sitemap_url"]]
    seen_sitemaps: set[str] = set()
    completed_sitemaps = completed_sitemap_urls(state_db_path, source_id)
    processed = 0
    errors = 0
    capped = False

    print(
        f"  root children={len(initial_children):,}, "
        f"completed={len(completed_sitemaps):,}, workers={workers}"
    )
    while queue:
        batch: list[str] = []
        while queue and len(batch) < workers:
            sitemap_url = queue.pop(0)
            if sitemap_url in seen_sitemaps:
                continue
            seen_sitemaps.add(sitemap_url)
            if sitemap_url in completed_sitemaps:
                continue
            if max_sitemaps is not None and processed + len(batch) >= max_sitemaps:
                capped = True
                queue.clear()
                break
            batch.append(sitemap_url)
        if not batch:
            continue

        with ThreadPoolExecutor(max_workers=min(workers, len(batch))) as executor:
            futures = {
                executor.submit(
                    fetch_and_parse_sitemap,
                    sitemap_url,
                    timeout=timeout,
                    request_retries=request_retries,
                    retry_backoff_seconds=retry_backoff_seconds,
                ): sitemap_url
                for sitemap_url in batch
            }
            for future in as_completed(futures):
                result = future.result()
                processed += 1
                if result["error"]:
                    errors += 1
                    upsert_sitemap_state(state_db_path, source_id, result, completed=False)
                    print(
                        f"  {source_id}: sitemap {processed:,} failed "
                        f"{result['sitemap_url']} ({result['error']})"
                    )
                    continue

                child_sitemaps = list(result["sitemaps"])
                if child_sitemaps:
                    queue.extend(child_sitemaps)
                    upsert_sitemap_state(state_db_path, source_id, result, completed=True)
                    completed_sitemaps.add(str(result["sitemap_url"]))
                    print(
                        f"  {source_id}: sitemap {processed:,} index_children="
                        f"{len(child_sitemaps):,}, queued={len(queue):,}"
                    )
                    continue

                candidate_rows = sitemap_article_rows(source, result)
                rows = filter_new_rows(state_db_path, source_id, candidate_rows)
                new_candidate_count = len(rows)
                url_capped = False
                if max_urls is not None:
                    remaining = max(0, max_urls - source_url_count(state_db_path, source_id))
                    rows = rows[:remaining]
                    if len(rows) < new_candidate_count:
                        url_capped = True
                        capped = True
                added = save_discovered_rows(state_db_path, rows)
                upsert_sitemap_state(
                    state_db_path,
                    source_id,
                    result,
                    completed=not url_capped,
                    urls_kept=len(rows),
                )
                if not url_capped:
                    completed_sitemaps.add(str(result["sitemap_url"]))
                total = source_url_count(state_db_path, source_id)
                print(
                    f"  {source_id}: sitemap {processed:,} urls={len(result['urls']):,}, "
                    f"article_urls={len(candidate_rows):,}, kept={len(rows):,}, "
                    f"new={added:,}, total={total:,}"
                )
                if capped:
                    queue.clear()
                if pause_seconds:
                    time.sleep(pause_seconds)

    complete = not capped and errors == 0
    if capped:
        stop_reason = "max_limit_reached"
    elif errors:
        stop_reason = f"sitemap_errors_{errors}"
    else:
        stop_reason = "official_sitemaps_complete"
    summary = finish_source_state(
        state_db_path,
        source_id,
        complete=complete,
        stop_reason=stop_reason,
    )
    print(
        f"=== Finished {source_id}: urls={summary['url_count']:,}, "
        f"complete={summary['complete']}, stop={summary['stop_reason']} ==="
    )
    return summary


def fetch_and_parse_sitemap(
    sitemap_url: str,
    *,
    timeout: float,
    request_retries: int,
    retry_backoff_seconds: float,
) -> dict[str, object]:
    """Fetch and parse one sitemap, retrying transient failures."""
    last_error: object = "unknown_error"
    last_status: object = pd.NA
    for attempt in range(request_retries + 1):
        response = fetch(sitemap_url, timeout, body_text_limit=100_000_000, profile="browser")
        last_status = response.get("status")
        status = response.get("status")
        if isinstance(status, int) and 200 <= status < 300:
            parsed = parse_sitemap_xml(response.get("text") or "")
            if not parsed["error"]:
                return {
                    "sitemap_url": sitemap_url,
                    "status": status,
                    "sitemaps": parsed["sitemaps"],
                    "urls": parsed["urls"],
                    "error": None,
                }
            last_error = parsed["error"]
        else:
            last_error = response.get("error")
            if is_blank(last_error):
                last_error = f"http_status_{status}"
        if attempt < request_retries:
            time.sleep(max(0.0, retry_backoff_seconds) * (attempt + 1))
    return {
        "sitemap_url": sitemap_url,
        "status": last_status,
        "sitemaps": [],
        "urls": [],
        "error": str(last_error),
    }


def sitemap_article_rows(
    source: dict[str, str], result: dict[str, object]
) -> list[dict[str, object]]:
    """Convert a parsed URL set into normalized article discovery rows."""
    now = pd.Timestamp.now("UTC").isoformat()
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in result["urls"]:
        canonical_url = canonicalize_article_url(item.get("loc"), source["source_url"])
        if not is_source_article_url(canonical_url, source["source_id"]):
            continue
        if canonical_url in seen:
            continue
        seen.add(canonical_url)
        rows.append(
            {
                "source_id": source["source_id"],
                "source_name": source["source_name"],
                "source_url": source["source_url"],
                "url": canonical_url,
                "canonical_url": canonical_url,
                "date_published": pd.NA,
                "lastmod": item.get("lastmod"),
                "topic": infer_source_topic(canonical_url, source["source_id"]),
                "discovery_strategy": "official_sitemap",
                "sitemap_url": result["sitemap_url"],
                "sitemap_status": result["status"],
                "discovered_at": now,
                "status": result["status"],
                "error": pd.NA,
            }
        )
    return rows


def canonicalize_article_url(url: object, source_url: str) -> str:
    """Return a query-free HTTPS URL or an empty string."""
    if is_blank(url):
        return ""
    parsed = urlparse(str(url).strip())
    if not parsed.netloc:
        return ""
    base_host = urlparse(source_url).netloc.lower().removeprefix("www.")
    host = parsed.netloc.lower().removeprefix("www.")
    if host != base_host:
        return ""
    path = re.sub(r"/{2,}", "/", parsed.path)
    return urlunparse(("https", f"www.{base_host}", path, "", "", ""))


def is_source_article_url(url: object, source_id: str) -> bool:
    """Return True for article URLs in a configured source sitemap."""
    if is_blank(url):
        return False
    parsed = urlparse(str(url))
    path = parsed.path
    lowered = path.lower()
    if lowered.endswith(STATIC_EXTENSIONS):
        return False
    if source_id in GRUPO_REFORMA_IDS:
        return bool(GRUPO_REFORMA_ARTICLE_RE.search(path))
    segments = [segment for segment in path.strip("/").split("/") if segment]
    if len(segments) < 2:
        return False
    return not any(
        marker in lowered
        for marker in ("/autores/", "/autor/", "/tags/", "/tag/", "/buscar/", "/sitemap/")
    )


def infer_source_topic(url: str, source_id: str) -> object:
    """Infer a useful first path section when the URL provides one."""
    if source_id in GRUPO_REFORMA_IDS:
        return pd.NA
    segments = [segment for segment in urlparse(url).path.strip("/").split("/") if segment]
    return segments[0] if segments else infer_topic_from_url(url)


def save_discovered_rows(path: Path, rows: list[dict[str, object]]) -> int:
    """Insert new discovery rows and return the number added."""
    if not rows:
        return 0
    columns = list(rows[0])
    placeholders = ", ".join("?" for _ in columns)
    with sqlite3.connect(path) as conn:
        before = conn.total_changes
        conn.executemany(
            f"INSERT OR IGNORE INTO discovered_urls ({', '.join(columns)}) VALUES ({placeholders})",
            [tuple(sqlite_value(row[column]) for column in columns) for row in rows],
        )
        conn.commit()
        return conn.total_changes - before


def filter_new_rows(
    path: Path, source_id: str, rows: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Remove URLs already persisted without loading the full archive into memory."""
    if not rows:
        return []
    urls = [str(row["url"]) for row in rows]
    existing: set[str] = set()
    with sqlite3.connect(path) as conn:
        for start in range(0, len(urls), 800):
            chunk = urls[start : start + 800]
            placeholders = ", ".join("?" for _ in chunk)
            existing.update(
                row[0]
                for row in conn.execute(
                    f"SELECT url FROM discovered_urls WHERE source_id=? AND url IN ({placeholders})",
                    (source_id, *chunk),
                )
            )
    return [row for row in rows if str(row["url"]) not in existing]


def upsert_sitemap_state(
    path: Path,
    source_id: str,
    result: dict[str, object],
    *,
    completed: bool,
    urls_kept: int = 0,
) -> None:
    """Persist one sitemap result."""
    kind = "index" if result.get("sitemaps") else "urlset"
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO sitemap_state (
                source_id, sitemap_url, status, sitemap_kind, urls_seen,
                urls_kept, error, completed, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, sitemap_url) DO UPDATE SET
                status=excluded.status,
                sitemap_kind=excluded.sitemap_kind,
                urls_seen=excluded.urls_seen,
                urls_kept=excluded.urls_kept,
                error=excluded.error,
                completed=excluded.completed,
                updated_at=excluded.updated_at
            """,
            (
                source_id,
                result["sitemap_url"],
                sqlite_value(result.get("status")),
                kind,
                len(result.get("urls") or []),
                urls_kept,
                sqlite_value(result.get("error")),
                int(completed),
                pd.Timestamp.now("UTC").isoformat(),
            ),
        )
        conn.commit()


def completed_sitemap_urls(path: Path, source_id: str) -> set[str]:
    """Return completed sitemap URLs for one source."""
    with sqlite3.connect(path) as conn:
        return {
            row[0]
            for row in conn.execute(
                "SELECT sitemap_url FROM sitemap_state WHERE source_id=? AND completed=1",
                (source_id,),
            )
        }


def source_url_count(path: Path, source_id: str) -> int:
    """Return persisted unique URL count for one source."""
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM discovered_urls WHERE source_id=?", (source_id,)
        ).fetchone()
    return int(row[0])


def finish_source_state(
    path: Path, source_id: str, *, complete: bool, stop_reason: str
) -> dict[str, object]:
    """Persist and return aggregate state for one source."""
    with sqlite3.connect(path) as conn:
        sitemap_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM sitemap_state WHERE source_id=? AND completed=1",
                (source_id,),
            ).fetchone()[0]
        )
        url_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM discovered_urls WHERE source_id=?", (source_id,)
            ).fetchone()[0]
        )
        updated_at = pd.Timestamp.now("UTC").isoformat()
        conn.execute(
            """
            INSERT INTO source_state (
                source_id, complete, stop_reason, sitemap_count, url_count, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                complete=excluded.complete,
                stop_reason=excluded.stop_reason,
                sitemap_count=excluded.sitemap_count,
                url_count=excluded.url_count,
                updated_at=excluded.updated_at
            """,
            (source_id, int(complete), stop_reason, sitemap_count, url_count, updated_at),
        )
        conn.commit()
    return {
        "source_id": source_id,
        "complete": bool(complete),
        "stop_reason": stop_reason,
        "sitemap_count": sitemap_count,
        "url_count": url_count,
        "updated_at": updated_at,
    }


def clear_source_state(path: Path, source_id: str) -> None:
    """Clear one source when resume is disabled."""
    with sqlite3.connect(path) as conn:
        conn.execute("DELETE FROM discovered_urls WHERE source_id=?", (source_id,))
        conn.execute("DELETE FROM sitemap_state WHERE source_id=?", (source_id,))
        conn.execute("DELETE FROM source_state WHERE source_id=?", (source_id,))
        conn.commit()


def load_discovered_urls(path: Path, source_id: str) -> pd.DataFrame:
    """Load one source's discovery rows from SQLite."""
    with sqlite3.connect(path) as conn:
        return pd.read_sql_query(
            "SELECT * FROM discovered_urls WHERE source_id=? ORDER BY lastmod, url",
            conn,
            params=(source_id,),
        )


def load_source_state(path: Path, source_id: str) -> dict[str, object]:
    """Load source completion state."""
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT complete, stop_reason, sitemap_count, url_count, updated_at "
            "FROM source_state WHERE source_id=?",
            (source_id,),
        ).fetchone()
    if not row:
        return {
            "source_id": source_id,
            "complete": False,
            "stop_reason": "not_started",
            "sitemap_count": 0,
            "url_count": 0,
            "updated_at": pd.NA,
        }
    return {
        "source_id": source_id,
        "complete": bool(row[0]),
        "stop_reason": row[1],
        "sitemap_count": int(row[2]),
        "url_count": int(row[3]),
        "updated_at": row[4],
    }


def write_news_sitemap_outputs(
    *,
    state_db_path: Path,
    source_id: str,
    discovery_dir: Path,
    reports_dir: Path,
) -> NewsSitemapOutputs:
    """Write one source's completed discovery data and report."""
    discovery_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    discovered = load_discovered_urls(state_db_path, source_id)
    state = load_source_state(state_db_path, source_id)
    csv_path = discovery_dir / f"discovered_urls_{source_id}.csv"
    parquet_path = discovery_dir / f"discovered_urls_{source_id}.parquet"
    report_path = reports_dir / f"{source_id}_discovery_report.md"
    discovered.to_csv(csv_path, index=False, encoding="utf-8")
    parquet_error = None
    try:
        discovered.to_parquet(parquet_path, index=False)
    except Exception as exc:
        parquet_error = str(exc).splitlines()[0]
        parquet_path = None
    report_path.write_text(build_news_sitemap_report(discovered, state), encoding="utf-8")
    return NewsSitemapOutputs(csv_path, parquet_path, report_path, parquet_error)


def build_news_sitemap_report(
    discovered: pd.DataFrame, state: dict[str, object]
) -> str:
    """Build a compact per-source discovery report."""
    source_id = state["source_id"]
    dates = pd.to_datetime(discovered.get("lastmod"), errors="coerce", utc=True)
    valid_dates = dates[(dates.dt.year >= 1990) & (dates.dt.year <= 2100)].dropna()
    lines = [
        f"# {source_id} Official Sitemap Discovery",
        "",
        f"- Complete: {state['complete']}",
        f"- Stop reason: {state['stop_reason']}",
        f"- Completed sitemaps: {state['sitemap_count']:,}",
        f"- Unique article URLs: {len(discovered):,}",
        f"- Earliest sitemap date: {valid_dates.min().isoformat() if not valid_dates.empty else 'unavailable'}",
        f"- Latest sitemap date: {valid_dates.max().isoformat() if not valid_dates.empty else 'unavailable'}",
        "",
    ]
    if not valid_dates.empty:
        by_year = (
            valid_dates.dt.year.value_counts().sort_index().rename_axis("year").reset_index(name="urls")
        )
        lines.extend(["## URLs By Year", "", markdown_table(by_year), ""])
    if source_id in GRUPO_REFORMA_IDS:
        lines.extend(
            [
                "## Coverage Note",
                "",
                "Grupo Reforma's official sitemap is a rolling recent window. Use Common Crawl "
                "and Wayback discovery to supplement historical /arNNNNNN URLs.",
                "",
            ]
        )
    return "\n".join(lines)


def sqlite_value(value: object) -> object:
    """Convert pandas missing values to SQLite NULL."""
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def is_blank(value: object) -> bool:
    """Return True for missing or whitespace-only scalar values."""
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return value is None or str(value).strip() == ""

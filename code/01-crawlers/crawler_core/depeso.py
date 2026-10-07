"""Resumable full-archive crawler for the De Peso WordPress sites."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlencode, urljoin

import pandas as pd

from crawler_core.capabilities import fetch
from crawler_core.wordpress import WP_POSTS_ENDPOINT, join_ids
from crawler_core.wordpress_articles import (
    ARTICLE_API_BODY_TEXT_LIMIT,
    WORDPRESS_ARTICLE_FIELDS,
    article_fields_from_post,
)


DEPESO_SOURCES = {
    "depeso": {
        "source_id": "depeso",
        "source_name": "De Peso Cancún",
        "source_url": "https://depeso.com/",
    },
    "depesoyucatan": {
        "source_id": "depesoyucatan",
        "source_name": "De Peso Yucatán",
        "source_url": "https://depesoyucatan.com/",
    },
}

ARTICLE_COLUMNS = [
    "source_id",
    "source_name",
    "source_url",
    "url",
    "canonical_url",
    "wp_post_id",
    "slug",
    "title",
    "summary",
    "main_text",
    "authors",
    "date",
    "date_published",
    "date_modified",
    "topic",
    "section",
    "tags",
    "category_ids",
    "tag_ids",
    "language",
    "discovery_strategy",
    "extractor_strategy",
    "article_api_url",
    "scrape_timestamp",
    "status",
    "error",
    "category_names",
    "tag_names",
]


@dataclass(frozen=True)
class CrawlResult:
    """Result summary for one source crawl."""

    source_id: str
    pages_processed: int
    rows_saved: int
    next_page: int
    complete: bool
    stop_reason: str


def build_archive_page_url(source_url: str, page: int, per_page: int) -> str:
    """Build the stable ID-ascending WordPress archive request."""
    base = urljoin(source_url, WP_POSTS_ENDPOINT)
    query = urlencode(
        {
            "per_page": per_page,
            "page": page,
            "orderby": "id",
            "order": "asc",
            "_embed": "author,wp:term",
            "_fields": ",".join(WORDPRESS_ARTICLE_FIELDS),
        }
    )
    return f"{base}?{query}"


def initialize_depeso_db(path: Path) -> None:
    """Create the durable article, state, and page-log tables."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS articles (
                source_id TEXT NOT NULL,
                source_name TEXT,
                source_url TEXT,
                url TEXT,
                canonical_url TEXT,
                wp_post_id INTEGER NOT NULL,
                slug TEXT,
                title TEXT,
                summary TEXT,
                main_text TEXT,
                authors TEXT,
                date TEXT,
                date_published TEXT,
                date_modified TEXT,
                topic TEXT,
                section TEXT,
                tags TEXT,
                category_ids TEXT,
                tag_ids TEXT,
                language TEXT,
                discovery_strategy TEXT,
                extractor_strategy TEXT,
                article_api_url TEXT,
                scrape_timestamp TEXT,
                status INTEGER,
                error TEXT,
                category_names TEXT,
                tag_names TEXT,
                PRIMARY KEY (source_id, wp_post_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS crawl_state (
                source_id TEXT PRIMARY KEY,
                source_name TEXT NOT NULL,
                source_url TEXT NOT NULL,
                per_page INTEGER,
                next_page INTEGER NOT NULL DEFAULT 1,
                complete INTEGER NOT NULL DEFAULT 0,
                stop_reason TEXT,
                last_status INTEGER,
                last_error TEXT,
                rows_saved INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )
        state_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(crawl_state)").fetchall()
        }
        if "per_page" not in state_columns:
            connection.execute("ALTER TABLE crawl_state ADD COLUMN per_page INTEGER")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS page_log (
                source_id TEXT NOT NULL,
                page INTEGER NOT NULL,
                status INTEGER,
                rows_received INTEGER NOT NULL DEFAULT 0,
                min_post_id INTEGER,
                max_post_id INTEGER,
                min_date TEXT,
                max_date TEXT,
                error TEXT,
                requested_at TEXT NOT NULL,
                PRIMARY KEY (source_id, page)
            )
            """
        )
        connection.commit()


def crawl_depeso_sources(
    source_ids: Iterable[str],
    *,
    state_db_path: Path,
    per_page: int = 100,
    timeout: float = 90.0,
    pause_seconds: float = 0.15,
    request_retries: int = 3,
    retry_backoff_seconds: float = 3.0,
    fetch_profile: str = "browser",
    max_pages_per_run: int | None = None,
    progress_every_pages: int = 10,
    fetcher: Callable[..., dict[str, object]] = fetch,
) -> list[CrawlResult]:
    """Crawl selected De Peso sources, checkpointing every API page."""
    initialize_depeso_db(state_db_path)
    results = []
    for source_id in source_ids:
        if source_id not in DEPESO_SOURCES:
            raise ValueError(f"Unknown De Peso source_id: {source_id}")
        results.append(
            crawl_depeso_source(
                DEPESO_SOURCES[source_id],
                state_db_path=state_db_path,
                per_page=per_page,
                timeout=timeout,
                pause_seconds=pause_seconds,
                request_retries=request_retries,
                retry_backoff_seconds=retry_backoff_seconds,
                fetch_profile=fetch_profile,
                max_pages_per_run=max_pages_per_run,
                progress_every_pages=progress_every_pages,
                fetcher=fetcher,
            )
        )
    return results


def crawl_depeso_source(
    source: dict[str, str],
    *,
    state_db_path: Path,
    per_page: int,
    timeout: float,
    pause_seconds: float,
    request_retries: int,
    retry_backoff_seconds: float,
    fetch_profile: str,
    max_pages_per_run: int | None,
    progress_every_pages: int,
    fetcher: Callable[..., dict[str, object]],
) -> CrawlResult:
    """Crawl one source from its durable next-page marker."""
    source_id = source["source_id"]
    ensure_source_state(state_db_path, source, per_page)
    state = load_source_state(state_db_path, source_id)
    if bool(state["complete"]):
        print(
            f"{source_id}: already complete at page {int(state['next_page']):,}; "
            f"rows={int(state['rows_saved']):,}"
        )
        return CrawlResult(
            source_id=source_id,
            pages_processed=0,
            rows_saved=int(state["rows_saved"]),
            next_page=int(state["next_page"]),
            complete=True,
            stop_reason=str(state["stop_reason"] or "complete"),
        )

    page = int(state["next_page"])
    pages_processed = 0
    stop_reason = "run_page_cap"
    complete = False
    started_at = time.monotonic()
    print(f"\n=== {source_id}: resuming at page {page:,}, {per_page} posts/page ===")

    while max_pages_per_run is None or pages_processed < max_pages_per_run:
        api_url = build_archive_page_url(source["source_url"], page, per_page)
        response = fetch_page_with_retries(
            api_url,
            timeout=timeout,
            request_retries=request_retries,
            retry_backoff_seconds=retry_backoff_seconds,
            fetch_profile=fetch_profile,
            fetcher=fetcher,
        )
        status = response.get("status")
        text = str(response.get("text") or "")

        if status in {400, 404} and "rest_post_invalid_page_number" in text:
            complete = True
            stop_reason = "invalid_page_number"
            save_terminal_page(state_db_path, source, page, status, stop_reason)
            break
        if not isinstance(status, int) or status < 200 or status >= 300:
            error = nonmissing(response.get("error")) or f"http_status_{status}"
            save_failed_page(state_db_path, source, page, status, str(error))
            raise RuntimeError(f"{source_id} page {page:,} failed: {error}")

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            error = f"JSONDecodeError: {exc}"
            save_failed_page(state_db_path, source, page, status, error)
            raise RuntimeError(f"{source_id} page {page:,} failed: {error}") from exc

        if not isinstance(payload, list):
            error = "unexpected_json_shape"
            save_failed_page(state_db_path, source, page, status, error)
            raise RuntimeError(f"{source_id} page {page:,} failed: {error}")
        if not payload:
            complete = True
            stop_reason = "empty_page"
            save_terminal_page(state_db_path, source, page, status, stop_reason)
            break

        rows = [post_to_article_row(source, post, api_url, status) for post in payload]
        complete = len(payload) < per_page
        stop_reason = "short_final_page" if complete else "running"
        save_successful_page(
            state_db_path,
            source,
            page=page,
            status=status,
            rows=rows,
            next_page=page + 1,
            complete=complete,
            stop_reason=stop_reason,
        )
        pages_processed += 1
        page += 1

        if progress_every_pages and (pages_processed % progress_every_pages == 0 or complete):
            rows_saved = count_source_rows(state_db_path, source_id)
            elapsed = max(time.monotonic() - started_at, 0.001)
            rate = pages_processed / elapsed * 60
            print(
                f"  {source_id}: pages_this_run={pages_processed:,}, next_page={page:,}, "
                f"rows_saved={rows_saved:,}, rate={rate:.1f} pages/min"
            )
        if complete:
            break
        if pause_seconds:
            time.sleep(pause_seconds)

    state = load_source_state(state_db_path, source_id)
    return CrawlResult(
        source_id=source_id,
        pages_processed=pages_processed,
        rows_saved=int(state["rows_saved"]),
        next_page=int(state["next_page"]),
        complete=bool(state["complete"]),
        stop_reason=str(state["stop_reason"] or stop_reason),
    )


def fetch_page_with_retries(
    url: str,
    *,
    timeout: float,
    request_retries: int,
    retry_backoff_seconds: float,
    fetch_profile: str,
    fetcher: Callable[..., dict[str, object]],
) -> dict[str, object]:
    """Fetch one page with bounded retries for transient failures."""
    attempts = max(1, int(request_retries) + 1)
    response: dict[str, object] = {}
    for attempt in range(1, attempts + 1):
        response = fetcher(
            url,
            timeout,
            body_text_limit=ARTICLE_API_BODY_TEXT_LIMIT,
            profile=fetch_profile,
        )
        status = response.get("status")
        if isinstance(status, int) and (200 <= status < 300 or status in {400, 404}):
            return response
        if attempt < attempts:
            delay = retry_backoff_seconds * attempt
            print(f"  retry {attempt}/{attempts - 1} after status={status}; sleeping {delay:.1f}s")
            if delay:
                time.sleep(delay)
    return response


def post_to_article_row(
    source: dict[str, str],
    post: dict[str, object],
    api_url: str,
    status: int,
) -> dict[str, object]:
    """Convert one WordPress post payload to the standard article schema."""
    if not isinstance(post, dict) or not str(post.get("id", "")).isdigit():
        raise ValueError("WordPress post is missing a numeric id")
    fields = article_fields_from_post(post)
    row = {column: None for column in ARTICLE_COLUMNS}
    row.update(
        {
            "source_id": source["source_id"],
            "source_name": source["source_name"],
            "source_url": source["source_url"],
            "wp_post_id": int(post["id"]),
            "category_ids": join_ids(post.get("categories")),
            "tag_ids": join_ids(post.get("tags")),
            "language": "es",
            "discovery_strategy": "depeso_wordpress_archive",
            "extractor_strategy": "wordpress_api",
            "article_api_url": api_url,
            "scrape_timestamp": pd.Timestamp.utcnow().isoformat(),
            "status": status,
            "error": None,
        }
    )
    row.update(fields)
    row["canonical_url"] = row.get("canonical_url") or row.get("url")
    return row


def ensure_source_state(path: Path, source: dict[str, str], per_page: int) -> None:
    """Insert an initial state row without disturbing an existing checkpoint."""
    now = pd.Timestamp.utcnow().isoformat()
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO crawl_state (
                source_id, source_name, source_url, per_page, next_page, complete,
                stop_reason, rows_saved, updated_at
            ) VALUES (?, ?, ?, ?, 1, 0, 'not_started', 0, ?)
            """,
            (
                source["source_id"],
                source["source_name"],
                source["source_url"],
                per_page,
                now,
            ),
        )
        stored = connection.execute(
            "SELECT per_page FROM crawl_state WHERE source_id = ?", (source["source_id"],)
        ).fetchone()[0]
        if stored is None:
            connection.execute(
                "UPDATE crawl_state SET per_page = ? WHERE source_id = ?",
                (per_page, source["source_id"]),
            )
        elif int(stored) != int(per_page):
            raise ValueError(
                f"{source['source_id']} checkpoint uses per_page={stored}; "
                f"resume with --per-page {stored} to avoid gaps or duplicates"
            )
        connection.commit()


def load_source_state(path: Path, source_id: str) -> sqlite3.Row:
    """Load one durable source state row."""
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM crawl_state WHERE source_id = ?", (source_id,)
        ).fetchone()
    if row is None:
        raise ValueError(f"Missing crawl state for {source_id}")
    return row


def save_successful_page(
    path: Path,
    source: dict[str, str],
    *,
    page: int,
    status: int,
    rows: list[dict[str, object]],
    next_page: int,
    complete: bool,
    stop_reason: str,
) -> None:
    """Atomically upsert one page and advance its checkpoint."""
    now = pd.Timestamp.utcnow().isoformat()
    placeholders = ", ".join("?" for _ in ARTICLE_COLUMNS)
    updates = ", ".join(
        f"{column}=excluded.{column}"
        for column in ARTICLE_COLUMNS
        if column not in {"source_id", "wp_post_id"}
    )
    ids = [int(row["wp_post_id"]) for row in rows]
    dates = [str(row["date_published"]) for row in rows if nonmissing(row.get("date_published"))]
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA busy_timeout=30000")
        connection.executemany(
            f"""
            INSERT INTO articles ({', '.join(ARTICLE_COLUMNS)})
            VALUES ({placeholders})
            ON CONFLICT(source_id, wp_post_id) DO UPDATE SET {updates}
            """,
            [[sqlite_value(row.get(column)) for column in ARTICLE_COLUMNS] for row in rows],
        )
        rows_saved = connection.execute(
            "SELECT COUNT(*) FROM articles WHERE source_id = ?", (source["source_id"],)
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO page_log (
                source_id, page, status, rows_received, min_post_id, max_post_id,
                min_date, max_date, error, requested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
            ON CONFLICT(source_id, page) DO UPDATE SET
                status=excluded.status,
                rows_received=excluded.rows_received,
                min_post_id=excluded.min_post_id,
                max_post_id=excluded.max_post_id,
                min_date=excluded.min_date,
                max_date=excluded.max_date,
                error=NULL,
                requested_at=excluded.requested_at
            """,
            (
                source["source_id"],
                page,
                status,
                len(rows),
                min(ids),
                max(ids),
                min(dates) if dates else None,
                max(dates) if dates else None,
                now,
            ),
        )
        connection.execute(
            """
            UPDATE crawl_state SET
                next_page = ?, complete = ?, stop_reason = ?, last_status = ?,
                last_error = NULL, rows_saved = ?, updated_at = ?
            WHERE source_id = ?
            """,
            (next_page, int(complete), stop_reason, status, rows_saved, now, source["source_id"]),
        )
        connection.commit()


def save_failed_page(
    path: Path,
    source: dict[str, str],
    page: int,
    status: object,
    error: str,
) -> None:
    """Persist a failed request without advancing the page marker."""
    now = pd.Timestamp.utcnow().isoformat()
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO page_log (source_id, page, status, rows_received, error, requested_at)
            VALUES (?, ?, ?, 0, ?, ?)
            ON CONFLICT(source_id, page) DO UPDATE SET
                status=excluded.status, rows_received=0, error=excluded.error,
                requested_at=excluded.requested_at
            """,
            (source["source_id"], page, sqlite_value(status), error, now),
        )
        connection.execute(
            """
            UPDATE crawl_state SET complete=0, stop_reason='request_error',
                last_status=?, last_error=?, updated_at=? WHERE source_id=?
            """,
            (sqlite_value(status), error, now, source["source_id"]),
        )
        connection.commit()


def save_terminal_page(
    path: Path,
    source: dict[str, str],
    page: int,
    status: object,
    stop_reason: str,
) -> None:
    """Mark a source complete after the archive terminates."""
    now = pd.Timestamp.utcnow().isoformat()
    with sqlite3.connect(path) as connection:
        rows_saved = connection.execute(
            "SELECT COUNT(*) FROM articles WHERE source_id = ?", (source["source_id"],)
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO page_log (source_id, page, status, rows_received, requested_at)
            VALUES (?, ?, ?, 0, ?)
            ON CONFLICT(source_id, page) DO UPDATE SET
                status=excluded.status, rows_received=0, error=NULL,
                requested_at=excluded.requested_at
            """,
            (source["source_id"], page, sqlite_value(status), now),
        )
        connection.execute(
            """
            UPDATE crawl_state SET complete=1, stop_reason=?, last_status=?,
                last_error=NULL, rows_saved=?, updated_at=? WHERE source_id=?
            """,
            (stop_reason, sqlite_value(status), rows_saved, now, source["source_id"]),
        )
        connection.commit()


def count_source_rows(path: Path, source_id: str) -> int:
    """Count unique saved posts for one source."""
    with sqlite3.connect(path) as connection:
        return int(
            connection.execute(
                "SELECT COUNT(*) FROM articles WHERE source_id = ?", (source_id,)
            ).fetchone()[0]
        )


def export_completed_depeso_sources(
    state_db_path: Path,
    source_ids: Iterable[str],
    *,
    articles_dir: Path,
    reports_dir: Path,
    allow_partial: bool = False,
) -> list[Path]:
    """Write standard per-source Parquet outputs and reports from SQLite."""
    outputs = []
    reports_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(state_db_path) as connection:
        for source_id in source_ids:
            state = load_source_state(state_db_path, source_id)
            if not bool(state["complete"]) and not allow_partial:
                print(f"Skipping export for incomplete source {source_id}; next_page={state['next_page']}")
                continue
            articles = pd.read_sql_query(
                "SELECT * FROM articles WHERE source_id = ? ORDER BY wp_post_id",
                connection,
                params=(source_id,),
            )
            if articles.empty:
                print(f"Skipping empty source {source_id}")
                continue
            source_dir = articles_dir / source_id
            source_dir.mkdir(parents=True, exist_ok=True)
            output_path = source_dir / "articles_part_000001.parquet.gzip"
            temporary = source_dir / "articles_part_000001.tmp.parquet.gzip"
            articles.to_parquet(temporary, index=False, compression="gzip")
            temporary.replace(output_path)
            report_path = reports_dir / f"{source_id}_articles.md"
            report_path.write_text(build_depeso_report(articles, state), encoding="utf-8")
            outputs.append(output_path)
            print(f"Exported {source_id}: {len(articles):,} rows -> {output_path}")
    return outputs


def build_depeso_report(articles: pd.DataFrame, state: sqlite3.Row) -> str:
    """Build a compact completion report for one De Peso source."""
    dates = pd.to_datetime(articles["date_published"], errors="coerce")
    empty_text = int(articles["main_text"].fillna("").astype(str).str.strip().eq("").sum())
    errors = int(articles["error"].notna().sum())
    return "\n".join(
        [
            f"# {articles.iloc[0]['source_id']} article crawl",
            "",
            f"Updated: {pd.Timestamp.utcnow().isoformat()}",
            "",
            f"- Archive traversal complete: {bool(state['complete'])}",
            f"- Stop reason: {state['stop_reason']}",
            f"- Next API page: {int(state['next_page']):,}",
            f"- Unique articles: {len(articles):,}",
            f"- Publication range: {dates.min()} to {dates.max()}",
            f"- Empty text: {empty_text:,}",
            f"- Error rows: {errors:,}",
            "",
            "Completion describes traversal to the public WordPress API archive terminus.",
            "Rows are deduplicated by source_id and WordPress post ID.",
            "",
        ]
    )


def sqlite_value(value: object) -> object:
    """Convert pandas/numpy missing and scalar values to SQLite-safe values."""
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except (AttributeError, ValueError):
            pass
    return value


def nonmissing(value: object) -> object | None:
    """Return a scalar only when it is not pandas-missing."""
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        return value
    return value

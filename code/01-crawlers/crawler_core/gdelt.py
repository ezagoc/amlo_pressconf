"""Checkpointed GDELT DOC API discovery for newspaper domains."""

from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlunparse

import pandas as pd
import requests
import urllib3

from crawler_core.capabilities import BROWSER_USER_AGENT


GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_SOURCES = {
    "reforma": {
        "source_name": "Reforma",
        "source_url": "https://www.reforma.com/",
        "domain": "reforma.com",
    },
    "elnorte": {
        "source_name": "El Norte",
        "source_url": "https://www.elnorte.com/",
        "domain": "elnorte.com",
    },
}
ARTICLE_RE = re.compile(r"/(?:ar|op)\d+/?$", flags=re.I)


@dataclass(frozen=True)
class GdeltDiscoveryOutput:
    source_id: str
    csv_path: Path
    parquet_path: Path | None
    report_path: Path
    rows: int
    parquet_error: str | None = None


def initialize_gdelt_db(path: Path) -> None:
    """Create durable URL and interval state tables."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            create table if not exists gdelt_urls (
                source_id text not null,
                url text not null,
                source_name text,
                source_url text,
                title text,
                seendate text,
                socialimage text,
                domain text,
                language text,
                sourcecountry text,
                discovered_at text,
                primary key (source_id, url)
            );
            create table if not exists gdelt_windows (
                source_id text not null,
                window_start text not null,
                window_end text not null,
                completed integer not null default 0,
                rows_found integer not null default 0,
                requests_made integer not null default 0,
                error text,
                updated_at text not null,
                primary key (source_id, window_start, window_end)
            );
            """
        )


def weekly_windows(from_date: date, to_date: date, days: int = 7) -> list[tuple[date, date]]:
    """Return inclusive date windows."""
    windows: list[tuple[date, date]] = []
    current = from_date
    while current <= to_date:
        end = min(current + timedelta(days=max(1, days) - 1), to_date)
        windows.append((current, end))
        current = end + timedelta(days=1)
    return windows


def discover_gdelt_urls(
    source_ids: list[str],
    *,
    from_date: date,
    to_date: date,
    state_db: Path,
    window_days: int = 7,
    max_records: int = 250,
    timeout: float = 90.0,
    request_interval_seconds: float = 5.2,
    request_retries: int = 3,
    retry_backoff_seconds: float = 10.0,
    resume: bool = True,
) -> None:
    """Discover URLs by source and date window into SQLite."""
    initialize_gdelt_db(state_db)
    windows = weekly_windows(from_date, to_date, window_days)
    total = len(source_ids) * len(windows)
    completed = 0
    started = time.monotonic()
    for source_id in source_ids:
        source = GDELT_SOURCES[source_id]
        for window_start, window_end in windows:
            if resume and gdelt_window_completed(state_db, source_id, window_start, window_end):
                completed += 1
                continue
            try:
                rows, requests_made = discover_gdelt_interval(
                    source_id,
                    source,
                    datetime.combine(window_start, datetime_time.min, tzinfo=timezone.utc),
                    datetime.combine(window_end, datetime_time.max, tzinfo=timezone.utc),
                    max_records=max_records,
                    timeout=timeout,
                    request_interval_seconds=request_interval_seconds,
                    request_retries=request_retries,
                    retry_backoff_seconds=retry_backoff_seconds,
                )
            except Exception as exc:
                save_gdelt_window(
                    state_db,
                    source_id,
                    window_start,
                    window_end,
                    [],
                    completed=False,
                    requests_made=0,
                    error=f"{type(exc).__name__}: {exc}",
                )
                print(f"  {source_id} {window_start}..{window_end}: ERROR {type(exc).__name__}: {exc}")
                continue
            save_gdelt_window(
                state_db,
                source_id,
                window_start,
                window_end,
                rows,
                completed=True,
                requests_made=requests_made,
                error=None,
            )
            completed += 1
            elapsed_minutes = max((time.monotonic() - started) / 60, 1e-6)
            rate = completed / elapsed_minutes
            remaining = total - completed
            eta_minutes = remaining / rate if rate else 0
            print(
                f"  {source_id} {window_start}..{window_end}: urls={len(rows):,}, "
                f"requests={requests_made} | windows={completed:,}/{total:,} "
                f"rate={rate:.1f}/min eta={eta_minutes:.0f}m"
            )


def gdelt_window_completed(path: Path, source_id: str, start: date, end: date) -> bool:
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "select completed from gdelt_windows where source_id=? and window_start=? and window_end=?",
            (source_id, start.isoformat(), end.isoformat()),
        ).fetchone()
    return bool(row and row[0])


def discover_gdelt_interval(
    source_id: str,
    source: dict[str, str],
    start: datetime,
    end: datetime,
    *,
    max_records: int,
    timeout: float,
    request_interval_seconds: float,
    request_retries: int,
    retry_backoff_seconds: float,
) -> tuple[list[dict[str, object]], int]:
    """Query one interval, splitting capped responses until they are complete."""
    pending = [(start, end)]
    rows: list[dict[str, object]] = []
    requests_made = 0
    while pending:
        interval_start, interval_end = pending.pop(0)
        payload = fetch_gdelt(
            source["domain"],
            interval_start,
            interval_end,
            max_records=max_records,
            timeout=timeout,
            request_interval_seconds=request_interval_seconds,
            request_retries=request_retries,
            retry_backoff_seconds=retry_backoff_seconds,
        )
        requests_made += 1
        articles = payload.get("articles", [])
        if not isinstance(articles, list):
            raise ValueError("GDELT response has no article list")
        if len(articles) >= max_records and interval_end - interval_start > timedelta(hours=1):
            midpoint = interval_start + (interval_end - interval_start) / 2
            pending[0:0] = [
                (interval_start, midpoint),
                (midpoint + timedelta(seconds=1), interval_end),
            ]
            continue
        if len(articles) >= max_records:
            raise RuntimeError(
                f"GDELT result cap reached within one hour: {interval_start.isoformat()}"
            )
        rows.extend(gdelt_article_row(source_id, source, article) for article in articles)
    deduped = {
        str(row["url"]): row
        for row in rows
        if not pd.isna(row.get("url"))
    }
    return list(deduped.values()), requests_made


def fetch_gdelt(
    domain: str,
    start: datetime,
    end: datetime,
    *,
    max_records: int,
    timeout: float,
    request_interval_seconds: float,
    request_retries: int,
    retry_backoff_seconds: float,
) -> dict[str, object]:
    """Fetch one rate-limited GDELT DOC API response."""
    params = {
        "query": f"domain:{domain}",
        "mode": "artlist",
        "maxrecords": str(max_records),
        "format": "json",
        "startdatetime": start.strftime("%Y%m%d%H%M%S"),
        "enddatetime": end.strftime("%Y%m%d%H%M%S"),
        "sort": "datedesc",
    }
    url = f"{GDELT_DOC_URL}?{urlencode(params)}"
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    last_error: Exception | None = None
    for attempt in range(request_retries + 1):
        request_started = time.monotonic()
        response: requests.Response | None = None
        try:
            response = requests.get(
                url,
                headers={"User-Agent": BROWSER_USER_AGENT},
                timeout=timeout,
                verify=False,
            )
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.HTTPError(f"HTTP {response.status_code}", response=response)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("GDELT returned a non-object JSON response")
            return payload
        except (requests.RequestException, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt >= request_retries:
                raise
            retry_delay = retry_backoff_seconds * (attempt + 1)
            if response is not None and response.status_code == 429:
                retry_delay = max(retry_delay, 65.0)
            time.sleep(retry_delay)
        finally:
            elapsed = time.monotonic() - request_started
            if elapsed < request_interval_seconds:
                time.sleep(request_interval_seconds - elapsed)
    raise RuntimeError(str(last_error))


def gdelt_article_row(
    source_id: str, source: dict[str, str], article: object
) -> dict[str, object]:
    """Normalize one GDELT result into discovery columns."""
    if not isinstance(article, dict):
        return {"source_id": source_id, "url": pd.NA}
    url = canonical_gdelt_url(article.get("url"), source["domain"])
    if pd.isna(url) or not ARTICLE_RE.search(urlparse(str(url)).path):
        url = pd.NA
    seen = pd.to_datetime(article.get("seendate"), format="%Y%m%dT%H%M%SZ", errors="coerce", utc=True)
    return {
        "source_id": source_id,
        "source_name": source["source_name"],
        "source_url": source["source_url"],
        "url": url,
        "canonical_url": url,
        "date_published": pd.NA,
        "lastmod": pd.NA,
        "topic": pd.NA,
        "discovery_strategy": "gdelt",
        "gdelt_title": article.get("title") or pd.NA,
        "gdelt_seen_at": seen.isoformat() if pd.notna(seen) else pd.NA,
        "gdelt_socialimage": article.get("socialimage") or pd.NA,
        "gdelt_domain": article.get("domain") or pd.NA,
        "gdelt_language": article.get("language") or pd.NA,
        "gdelt_sourcecountry": article.get("sourcecountry") or pd.NA,
        "status": 200,
        "error": pd.NA,
        "discovered_at": datetime.now(timezone.utc).isoformat(),
    }


def canonical_gdelt_url(url: object, domain: str) -> object:
    if pd.isna(url):
        return pd.NA
    parsed = urlparse(str(url).strip())
    hostname = (parsed.hostname or "").lower().removeprefix("www.")
    if hostname != domain:
        return pd.NA
    return urlunparse(("https", f"www.{domain}", parsed.path.rstrip("/"), "", "", ""))


def save_gdelt_window(
    path: Path,
    source_id: str,
    start: date,
    end: date,
    rows: list[dict[str, object]],
    *,
    completed: bool,
    requests_made: int,
    error: str | None,
) -> None:
    """Atomically save one interval's URLs and status."""
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(path) as connection:
        for row in rows:
            if pd.isna(row.get("url")):
                continue
            connection.execute(
                """
                insert into gdelt_urls (
                    source_id, url, source_name, source_url, title, seendate,
                    socialimage, domain, language, sourcecountry, discovered_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(source_id, url) do update set
                    title=excluded.title, seendate=excluded.seendate,
                    socialimage=excluded.socialimage, discovered_at=excluded.discovered_at
                """,
                (
                    source_id,
                    row["url"],
                    row.get("source_name"),
                    row.get("source_url"),
                    none_if_missing(row.get("gdelt_title")),
                    none_if_missing(row.get("gdelt_seen_at")),
                    none_if_missing(row.get("gdelt_socialimage")),
                    none_if_missing(row.get("gdelt_domain")),
                    none_if_missing(row.get("gdelt_language")),
                    none_if_missing(row.get("gdelt_sourcecountry")),
                    now,
                ),
            )
        connection.execute(
            """
            insert into gdelt_windows (
                source_id, window_start, window_end, completed, rows_found,
                requests_made, error, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(source_id, window_start, window_end) do update set
                completed=excluded.completed, rows_found=excluded.rows_found,
                requests_made=excluded.requests_made, error=excluded.error,
                updated_at=excluded.updated_at
            """,
            (
                source_id,
                start.isoformat(),
                end.isoformat(),
                int(completed),
                len(rows),
                requests_made,
                error,
                now,
            ),
        )


def none_if_missing(value: object) -> object:
    return None if pd.isna(value) else value


def load_gdelt_urls(path: Path) -> pd.DataFrame:
    """Load discovery rows from SQLite in extractor-compatible form."""
    with sqlite3.connect(path) as connection:
        frame = pd.read_sql_query("select * from gdelt_urls", connection)
    if frame.empty:
        return frame
    frame = frame.rename(
        columns={
            "title": "gdelt_title",
            "seendate": "gdelt_seen_at",
            "socialimage": "gdelt_socialimage",
            "domain": "gdelt_domain",
            "language": "gdelt_language",
            "sourcecountry": "gdelt_sourcecountry",
        }
    )
    frame["canonical_url"] = frame["url"]
    frame["date_published"] = pd.NA
    frame["lastmod"] = pd.NA
    frame["topic"] = pd.NA
    frame["discovery_strategy"] = "gdelt"
    frame["status"] = 200
    frame["error"] = pd.NA
    return frame


def write_gdelt_outputs(
    discovered: pd.DataFrame, output_dir: Path, reports_dir: Path
) -> list[GdeltDiscoveryOutput]:
    """Write per-source GDELT discovery artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[GdeltDiscoveryOutput] = []
    for source_id, frame in discovered.groupby("source_id", sort=True):
        source_id = str(source_id)
        frame = frame.sort_values("url").reset_index(drop=True)
        csv_path = output_dir / f"discovered_urls_{source_id}_gdelt.csv"
        parquet_path = output_dir / f"discovered_urls_{source_id}_gdelt.parquet"
        report_path = reports_dir / f"{source_id}_gdelt_discovery_report.md"
        frame.to_csv(csv_path, index=False, encoding="utf-8")
        parquet_error = None
        try:
            frame.to_parquet(parquet_path, index=False)
        except Exception as exc:
            parquet_error = str(exc)
            parquet_path = None
        years = frame["gdelt_seen_at"].astype("string").str[:4].value_counts().sort_index()
        report = [f"# {source_id} GDELT discovery report", "", f"- Unique URLs: {len(frame):,}", ""]
        report.extend(f"- {year}: {count:,}" for year, count in years.items())
        report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
        outputs.append(
            GdeltDiscoveryOutput(
                source_id, csv_path, parquet_path, report_path, len(frame), parquet_error
            )
        )
    return outputs

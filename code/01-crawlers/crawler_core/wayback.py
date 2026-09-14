"""Internet Archive Wayback CDX URL discovery for newspaper sources."""

from __future__ import annotations

import calendar
import json
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import pandas as pd

from crawler_core.capabilities import fetch, markdown_table
from crawler_core.commoncrawl import article_path_candidates
from crawler_core.category_pagination import infer_topic_from_url
from crawler_core.sitemaps import likely_article_url


WAYBACK_CDX_URL = "https://web.archive.org/cdx/search/cdx"
DEFAULT_BODY_TEXT_LIMIT = 80_000_000


@dataclass(frozen=True)
class WaybackDiscoveryOutputs:
    """Paths written by Wayback discovery."""

    discovered_csv: Path
    discovered_parquet: Path | None
    report_path: Path
    parquet_error: str | None = None


def load_wayback_sources(
    capabilities_path: Path,
    *,
    strategies: set[str] | None = None,
) -> pd.DataFrame:
    """Load sources for Wayback discovery."""
    capabilities = pd.read_csv(capabilities_path)
    if strategies:
        capabilities = capabilities[capabilities["recommended_strategy"].isin(strategies)].copy()
    return capabilities.reset_index(drop=True)


def discover_wayback_urls(
    sources: pd.DataFrame,
    *,
    source_ids: list[str] | None = None,
    limit_sources: int | None = None,
    from_timestamp: str | None = None,
    to_timestamp: str | None = None,
    date_window: str = "none",
    path_patterns: list[str] | None = None,
    include_broad_domain: bool = False,
    limit_per_page: int = 1_000,
    max_pages_per_query: int = 10,
    max_urls_per_source: int | None = None,
    timeout: float = 120.0,
    pause_seconds: float = 1.0,
    body_text_limit: int = DEFAULT_BODY_TEXT_LIMIT,
) -> pd.DataFrame:
    """Discover likely article URLs from the Wayback CDX index."""
    if source_ids:
        sources = sources[sources["source_id"].isin(source_ids)].reset_index(drop=True)
    if limit_sources is not None:
        sources = sources.head(limit_sources)

    rows: list[dict[str, object]] = []
    total_sources = len(sources)
    for source_number, source in sources.iterrows():
        source_id = source.get("source_id")
        patterns = wayback_url_patterns(
            source,
            path_patterns=path_patterns,
            include_broad_domain=include_broad_domain,
        )
        print(f"\n=== Wayback source {source_number + 1}/{total_sources}: {source_id} ===")
        if not patterns:
            rows.append(error_row(source, pd.NA, pd.NA, pd.NA, "no_wayback_url_pattern"))
            continue

        seen_source_originals: set[str] = set()
        for pattern in patterns:
            if max_urls_per_source is not None and len(seen_source_originals) >= max_urls_per_source:
                print(f"  {source_id}: hit max_urls_per_source={max_urls_per_source}; stopping source")
                break
            windows = date_windows(from_timestamp, to_timestamp, date_window)
            print(f"  {source_id}: pattern={pattern} windows={len(windows):,}")
            for window_number, (window_from, window_to) in enumerate(windows, start=1):
                if max_urls_per_source is not None and len(seen_source_originals) >= max_urls_per_source:
                    print(f"    hit max_urls_per_source={max_urls_per_source}; stopping pattern")
                    break
                print(f"    window {window_number}/{len(windows)} from={window_from or '-'} to={window_to or '-'}")
                try:
                    query_rows = discover_wayback_query(
                        source,
                        url_pattern=pattern,
                        seen_source_originals=seen_source_originals,
                        from_timestamp=window_from,
                        to_timestamp=window_to,
                        limit_per_page=limit_per_page,
                        max_pages=max_pages_per_query,
                        max_urls_per_source=max_urls_per_source,
                        timeout=timeout,
                        pause_seconds=pause_seconds,
                        body_text_limit=body_text_limit,
                    )
                except Exception as exc:
                    print(f"!!! {source_id}: unexpected Wayback query failure: {type(exc).__name__}: {exc}")
                    query_rows = [error_row(source, pattern, pd.NA, pd.NA, f"{type(exc).__name__}: {exc}")]
                rows.extend(query_rows)
                urls = sum(1 for row in query_rows if pd.notna(row.get("url")))
                errors = sum(1 for row in query_rows if pd.notna(row.get("error")))
                print(
                    f"      rows={len(query_rows):,}, new_urls={urls:,}, "
                    f"errors={errors:,}, source_total={len(seen_source_originals):,}"
                )
                if pause_seconds:
                    time.sleep(pause_seconds)

        if not seen_source_originals:
            rows.append(error_row(source, "; ".join(patterns), pd.NA, pd.NA, "no_likely_article_urls_found"))
        print(f"=== Finished {source_id}: source_urls={len(seen_source_originals):,} ===")

    discovered = pd.DataFrame(rows)
    return dedupe_wayback_discovery(discovered)


def discover_wayback_query(
    source: pd.Series,
    *,
    url_pattern: str,
    seen_source_originals: set[str],
    from_timestamp: str | None,
    to_timestamp: str | None,
    limit_per_page: int,
    max_pages: int,
    max_urls_per_source: int | None,
    timeout: float,
    pause_seconds: float,
    body_text_limit: int,
) -> list[dict[str, object]]:
    """Run one paged Wayback CDX query."""
    rows: list[dict[str, object]] = []
    resume_key: str | None = None
    for page_number in range(1, max_pages + 1):
        query_url = wayback_query_url(
            url_pattern=url_pattern,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
            limit=limit_per_page,
            resume_key=resume_key,
        )
        response = fetch(query_url, timeout, body_text_limit=body_text_limit, profile="browser")
        status = response.get("status")
        if status == 404:
            return rows
        if not isinstance(status, int) or status < 200 or status >= 300:
            error = response.get("error")
            if pd.isna(error):
                error = f"http_status_{status}"
            rows.append(error_row(source, url_pattern, status, page_number, error))
            return rows

        records, resume_key, parse_error = parse_wayback_json(response.get("text") or "")
        if parse_error:
            rows.append(error_row(source, url_pattern, status, page_number, parse_error))
            return rows
        new_count = 0
        for record in records:
            original_url = clean_original_url(record.get("original"))
            if pd.isna(original_url):
                continue
            if original_url in seen_source_originals:
                continue
            if not likely_article_url(original_url):
                continue
            seen_source_originals.add(str(original_url))
            rows.append(url_row(source, record, str(original_url), url_pattern, status))
            new_count += 1
            if max_urls_per_source is not None and len(seen_source_originals) >= max_urls_per_source:
                print(f"    page {page_number}: hit max_urls_per_source={max_urls_per_source}")
                return rows

        print(
            f"    page {page_number}: records={len(records):,}, "
            f"new_article_urls={new_count:,}, resume={'yes' if resume_key else 'no'}"
        )
        if not resume_key:
            return rows
        if pause_seconds:
            time.sleep(pause_seconds)
    return rows


def wayback_query_url(
    *,
    url_pattern: str,
    from_timestamp: str | None,
    to_timestamp: str | None,
    limit: int,
    resume_key: str | None,
) -> str:
    """Build a Wayback CDX query URL."""
    params: list[tuple[str, str]] = [
        ("url", url_pattern),
        ("output", "json"),
        ("fl", "urlkey,timestamp,original,mimetype,statuscode,digest,length"),
        ("filter", "statuscode:200"),
        ("filter", "mimetype:text/html"),
        ("collapse", "urlkey"),
        ("limit", str(limit)),
        ("showResumeKey", "true"),
    ]
    if from_timestamp:
        params.append(("from", from_timestamp))
    if to_timestamp:
        params.append(("to", to_timestamp))
    if resume_key:
        params.append(("resumeKey", resume_key))
    return f"{WAYBACK_CDX_URL}?{urlencode(params)}"


def date_windows(
    from_timestamp: str | None,
    to_timestamp: str | None,
    date_window: str,
) -> list[tuple[str | None, str | None]]:
    """Split a Wayback date range into smaller query windows."""
    if date_window == "none" or not from_timestamp or not to_timestamp:
        return [(from_timestamp, to_timestamp)]

    start_year = int(str(from_timestamp)[:4])
    end_year = int(str(to_timestamp)[:4])
    if date_window == "year":
        windows = []
        for year in range(start_year, end_year + 1):
            window_from = max(str(from_timestamp), f"{year}0101") if year == start_year else f"{year}0101"
            window_to = min(str(to_timestamp), f"{year}1231") if year == end_year else f"{year}1231"
            windows.append((window_from, window_to))
        return windows

    if date_window == "month":
        windows = []
        for year in range(start_year, end_year + 1):
            first_month = int(str(from_timestamp)[4:6]) if year == start_year and len(str(from_timestamp)) >= 6 else 1
            last_month = int(str(to_timestamp)[4:6]) if year == end_year and len(str(to_timestamp)) >= 6 else 12
            for month in range(first_month, last_month + 1):
                last_day = calendar.monthrange(year, month)[1]
                window_from = f"{year}{month:02d}01"
                window_to = f"{year}{month:02d}{last_day:02d}"
                if year == start_year:
                    window_from = max(str(from_timestamp), window_from)
                if year == end_year:
                    window_to = min(str(to_timestamp), window_to)
                windows.append((window_from, window_to))
        return windows

    raise ValueError(f"Unsupported date_window: {date_window}")


def parse_wayback_json(text: str) -> tuple[list[dict[str, object]], str | None, str | None]:
    """Parse Wayback CDX JSON output into dictionaries plus an optional resume key."""
    if not text.strip():
        return [], None, None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return [], None, f"JSONDecodeError: {exc}"
    if not isinstance(payload, list) or not payload:
        return [], None, None
    header = payload[0]
    if not isinstance(header, list):
        return [], None, "missing_cdx_header"

    records: list[dict[str, object]] = []
    resume_key = None
    for row in payload[1:]:
        if not row:
            continue
        if len(row) == 1 and isinstance(row[0], str):
            resume_key = row[0]
            continue
        if not isinstance(row, list):
            continue
        if len(row) < len(header):
            continue
        records.append(dict(zip(header, row)))
    return records, resume_key, None


def wayback_url_patterns(
    source: pd.Series,
    *,
    path_patterns: list[str] | None = None,
    include_broad_domain: bool = False,
) -> list[str]:
    """Return Wayback URL patterns for a source."""
    canonical_url = source.get("canonical_url")
    if pd.isna(canonical_url):
        return []
    parsed = urlparse(str(canonical_url))
    if not parsed.netloc:
        return []
    host = parsed.netloc.lower()
    path = parsed.path.strip("/")
    base_path = f"{path}/" if path else ""
    hosts = [host]
    if host.startswith("www."):
        hosts.append(host[4:])
    else:
        hosts.append(f"www.{host}")

    article_paths = article_path_candidates(source, path_patterns=path_patterns)
    patterns = []
    for candidate_host in hosts:
        for article_path in article_paths:
            if base_path and not article_path.startswith(base_path):
                patterns.append(f"{candidate_host}/{base_path}{article_path}/*")
            patterns.append(f"{candidate_host}/{article_path}/*")
        if include_broad_domain:
            patterns.append(f"{candidate_host}/{base_path}*")
    return dedupe_preserve_order(patterns)


def clean_original_url(url: object) -> object:
    """Normalize an original Wayback URL enough for dedupe/extraction metadata."""
    if pd.isna(url):
        return pd.NA
    parsed = urlparse(str(url).strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return pd.NA
    kept_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}
    ]
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", urlencode(kept_query), ""))


def wayback_playback_url(timestamp: object, original_url: str) -> str:
    """Return a no-toolbar Wayback playback URL for an archived page."""
    return f"https://web.archive.org/web/{timestamp}id_/{original_url}"


def url_row(
    source: pd.Series,
    record: dict[str, object],
    original_url: str,
    url_pattern: str,
    status: object,
) -> dict[str, object]:
    """Return a Wayback discovery row compatible with the HTML extractor."""
    timestamp = record.get("timestamp")
    playback_url = wayback_playback_url(timestamp, original_url)
    return {
        "source_id": source.get("source_id"),
        "source_name": source.get("source_name"),
        "source_url": source.get("canonical_url"),
        "url": playback_url,
        "canonical_url": original_url,
        "original_url": original_url,
        "wayback_url": playback_url,
        "date_published": pd.NA,
        "lastmod": pd.NA,
        "topic": infer_topic_from_url(original_url),
        "discovery_strategy": "wayback",
        "wayback_query": url_pattern,
        "wayback_urlkey": record.get("urlkey"),
        "wayback_timestamp": timestamp,
        "wayback_mimetype": record.get("mimetype"),
        "wayback_statuscode": record.get("statuscode"),
        "wayback_digest": record.get("digest"),
        "wayback_length": record.get("length"),
        "status": status,
        "error": pd.NA,
        "discovered_at": pd.Timestamp.utcnow().isoformat(),
    }


def error_row(
    source: pd.Series,
    url_pattern: object,
    status: object,
    page_number: object,
    error: object,
) -> dict[str, object]:
    """Return a Wayback discovery error row."""
    return {
        "source_id": source.get("source_id"),
        "source_name": source.get("source_name"),
        "source_url": source.get("canonical_url"),
        "url": pd.NA,
        "canonical_url": pd.NA,
        "original_url": pd.NA,
        "wayback_url": pd.NA,
        "date_published": pd.NA,
        "lastmod": pd.NA,
        "topic": pd.NA,
        "discovery_strategy": "wayback",
        "wayback_query": url_pattern,
        "wayback_urlkey": pd.NA,
        "wayback_timestamp": pd.NA,
        "wayback_mimetype": pd.NA,
        "wayback_statuscode": pd.NA,
        "wayback_digest": pd.NA,
        "wayback_length": pd.NA,
        "status": status,
        "page_number": page_number,
        "error": error,
        "discovered_at": pd.Timestamp.utcnow().isoformat(),
    }


def dedupe_wayback_discovery(discovered: pd.DataFrame) -> pd.DataFrame:
    """Dedupe Wayback discoveries by original/canonical URL, preserving errors."""
    if discovered.empty:
        return discovered
    if {"source_id", "canonical_url"}.issubset(discovered.columns):
        url_rows = discovered[discovered["canonical_url"].notna()].drop_duplicates(
            ["source_id", "canonical_url"],
            keep="last",
        )
        error_rows = discovered[discovered["canonical_url"].isna()]
        discovered = pd.concat([url_rows, error_rows], ignore_index=True)
    return discovered.reset_index(drop=True)


def build_wayback_report(discovered: pd.DataFrame) -> str:
    """Create a markdown report for Wayback discovery."""
    lines = [
        "# Wayback Discovery Report",
        "",
        f"- Rows: {len(discovered):,}",
        f"- Sources: {discovered['source_id'].nunique() if not discovered.empty else 0:,}",
        f"- URLs: {discovered['url'].notna().sum() if 'url' in discovered else 0:,}",
        f"- Errors: {discovered['error'].notna().sum() if 'error' in discovered else 0:,}",
        "",
    ]
    if not discovered.empty:
        summary = (
            discovered.groupby("source_id", dropna=False)
            .agg(
                rows=("source_id", "size"),
                urls=("url", lambda value: value.notna().sum()),
                errors=("error", lambda value: value.notna().sum()),
                queries=("wayback_query", lambda value: value.dropna().nunique()),
            )
            .reset_index()
            .sort_values(["urls", "rows"], ascending=False)
        )
        lines.extend(["## By Source", "", markdown_table(summary), ""])
    return "\n".join(lines)


def write_wayback_outputs(
    discovered: pd.DataFrame,
    report: str,
    discovery_dir: Path,
    reports_dir: Path,
) -> WaybackDiscoveryOutputs:
    """Write Wayback discovery CSV/parquet and report files."""
    discovery_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    discovered_csv = discovery_dir / "discovered_urls_wayback.csv"
    discovered_parquet = discovery_dir / "discovered_urls_wayback.parquet"
    report_path = reports_dir / "wayback_discovery_report.md"
    discovered.to_csv(discovered_csv, index=False, encoding="utf-8")
    parquet_error = None
    try:
        discovered.to_parquet(discovered_parquet, index=False)
    except ImportError as exc:
        discovered_parquet = None
        parquet_error = str(exc).splitlines()[0]
    report_path.write_text(report, encoding="utf-8")
    return WaybackDiscoveryOutputs(discovered_csv, discovered_parquet, report_path, parquet_error)


def dedupe_preserve_order(values: list[str]) -> list[str]:
    """Dedupe while preserving order."""
    seen = set()
    output = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output

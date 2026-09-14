"""Google Programmable Search discovery for date-in-URL newspaper articles."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pandas as pd
import requests

from crawler_core.capabilities import markdown_table


GOOGLE_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"
RESULTS_PER_PAGE = 10


@dataclass(frozen=True)
class GoogleDiscoveryOutputs:
    """Paths written by Google search discovery."""

    discovered_csv: Path
    discovered_parquet: Path | None
    report_path: Path
    parquet_error: str | None = None


def load_google_sources(
    capabilities_path: Path,
    *,
    source_ids: list[str] | None = None,
    strategies: set[str] | None = None,
) -> pd.DataFrame:
    """Load sources eligible for Google search URL discovery."""
    sources = pd.read_csv(capabilities_path)
    if strategies and "recommended_strategy" in sources.columns:
        sources = sources[sources["recommended_strategy"].isin(strategies)].copy()
    if source_ids:
        sources = sources[sources["source_id"].isin(source_ids)].copy()
        missing = sorted(set(source_ids) - set(sources["source_id"]))
        if missing:
            raise ValueError("Requested source_id not found: " + ", ".join(missing))
    return sources.reset_index(drop=True)


def discover_google_urls(
    sources: pd.DataFrame,
    *,
    api_key: str,
    cse_id: str,
    source_ids: list[str] | None = None,
    limit_sources: int | None = None,
    from_date: date,
    to_date: date,
    section_paths: list[str] | None = None,
    query_modes: list[str] | None = None,
    topic_terms: list[str] | None = None,
    include_domain_query: bool = True,
    shard_sections: bool = True,
    saturation_threshold: int = 90,
    max_results_per_query: int = 100,
    max_urls_per_source: int | None = None,
    timeout: float = 60.0,
    pause_seconds: float = 1.0,
) -> pd.DataFrame:
    """Discover URLs with day-level Google API queries."""
    query_modes = normalize_query_modes(query_modes)
    if source_ids:
        sources = sources[sources["source_id"].isin(source_ids)].reset_index(drop=True)
    if limit_sources is not None:
        sources = sources.head(limit_sources).reset_index(drop=True)

    rows: list[dict[str, object]] = []
    for source_number, source in sources.iterrows():
        source_id = source.get("source_id")
        domain = source_domain(source)
        if not domain:
            rows.append(error_row(source, pd.NA, pd.NA, "missing_domain"))
            continue

        print(f"\n=== Google source {source_number + 1}/{len(sources)}: {source_id} ({domain}) ===", flush=True)
        seen_source_urls: set[str] = set()
        for current_day in iter_dates(from_date, to_date):
            if max_urls_per_source is not None and len(seen_source_urls) >= max_urls_per_source:
                print(f"  {source_id}: hit max_urls_per_source={max_urls_per_source}", flush=True)
                break

            daily_rows = []
            if include_domain_query:
                for query, query_mode, topic_term in build_queries(
                    domain,
                    current_day,
                    query_modes=query_modes,
                    topic_terms=topic_terms,
                ):
                    query_rows = query_google(
                        source,
                        query,
                        current_day=current_day,
                        shard="domain",
                        query_mode=query_mode,
                        topic_term=topic_term,
                        api_key=api_key,
                        cse_id=cse_id,
                        max_results=max_results_per_query,
                        timeout=timeout,
                        seen_source_urls=seen_source_urls,
                    )
                    daily_rows.extend(query_rows)
                    rows.extend(query_rows)
                    print(
                        f"  {source_id}: {current_day.isoformat()} domain {query_mode}"
                        f"{topic_suffix(topic_term)} rows={count_urls(query_rows):,} "
                        f"total={len(seen_source_urls):,}",
                        flush=True,
                    )
                    if pause_seconds:
                        time.sleep(pause_seconds)

            should_shard = shard_sections and section_paths and (
                not include_domain_query or count_urls(daily_rows) >= saturation_threshold
            )
            if should_shard:
                for section_path in section_paths or []:
                    if max_urls_per_source is not None and len(seen_source_urls) >= max_urls_per_source:
                        break
                    for query, query_mode, topic_term in build_queries(
                        domain,
                        current_day,
                        section_path=section_path,
                        query_modes=query_modes,
                        topic_terms=topic_terms,
                    ):
                        section_rows = query_google(
                            source,
                            query,
                            current_day=current_day,
                            shard=normalize_section_path(section_path),
                            query_mode=query_mode,
                            topic_term=topic_term,
                            api_key=api_key,
                            cse_id=cse_id,
                            max_results=max_results_per_query,
                            timeout=timeout,
                            seen_source_urls=seen_source_urls,
                        )
                        rows.extend(section_rows)
                        print(
                            f"    shard {normalize_section_path(section_path)} {query_mode}"
                            f"{topic_suffix(topic_term)} rows={count_urls(section_rows):,} "
                            f"total={len(seen_source_urls):,}",
                            flush=True,
                        )
                        if pause_seconds:
                            time.sleep(pause_seconds)
        print(f"=== Finished {source_id}: source_urls={len(seen_source_urls):,} ===", flush=True)

    return dedupe_google_discovery(pd.DataFrame(rows))


def query_google(
    source: pd.Series,
    query: str,
    *,
    current_day: date,
    shard: str,
    query_mode: str,
    topic_term: str | None,
    api_key: str,
    cse_id: str,
    max_results: int,
    timeout: float,
    seen_source_urls: set[str],
) -> list[dict[str, object]]:
    """Run one Google API query and return discovery rows."""
    rows: list[dict[str, object]] = []
    pages = max(1, min(max_results, 100) // RESULTS_PER_PAGE)
    for page_number in range(pages):
        start = 1 + page_number * RESULTS_PER_PAGE
        params = {
            "key": api_key,
            "cx": cse_id,
            "q": query,
            "num": RESULTS_PER_PAGE,
            "start": start,
            "safe": "off",
        }
        try:
            response = requests.get(GOOGLE_SEARCH_URL, params=params, timeout=timeout)
            data = response.json()
        except requests.RequestException as exc:
            rows.append(error_row(source, query, current_day, str(exc), shard=shard, query_mode=query_mode, topic_term=topic_term, start=start))
            break
        except ValueError as exc:
            rows.append(error_row(source, query, current_day, f"json_decode_error: {exc}", shard=shard, query_mode=query_mode, topic_term=topic_term, start=start))
            break

        if response.status_code != 200:
            message = data.get("error", {}).get("message") if isinstance(data, dict) else response.text[:300]
            rows.append(error_row(source, query, current_day, f"http_{response.status_code}: {message}", shard=shard, query_mode=query_mode, topic_term=topic_term, start=start))
            break

        items = data.get("items") or []
        total_results = data.get("searchInformation", {}).get("totalResults", pd.NA)
        search_time = data.get("searchInformation", {}).get("searchTime", pd.NA)
        if not items:
            break
        for item in items:
            url = canonical_url(item.get("link"))
            if not url or url in seen_source_urls:
                continue
            if not likely_source_url(source, url):
                continue
            seen_source_urls.add(url)
            rows.append(
                url_row(
                    source,
                    url,
                    query=query,
                    current_day=current_day,
                    shard=shard,
                    query_mode=query_mode,
                    topic_term=topic_term,
                    start=start,
                    total_results=total_results,
                    search_time=search_time,
                    item=item,
                )
            )
        if len(items) < RESULTS_PER_PAGE:
            break
    return rows


def build_queries(
    domain: str,
    day: date,
    *,
    section_path: str | None = None,
    query_modes: list[str],
    topic_terms: list[str] | None = None,
) -> list[tuple[str, str, str | None]]:
    """Build Google queries for one source/day/section."""
    queries: list[tuple[str, str, str | None]] = []
    terms = [None] + [term for term in topic_terms or [] if str(term).strip()]
    for query_mode in query_modes:
        for topic_term in terms:
            queries.append((build_query(domain, day, section_path=section_path, query_mode=query_mode, topic_term=topic_term), query_mode, topic_term))
    return queries


def build_query(
    domain: str,
    day: date,
    *,
    section_path: str | None = None,
    query_mode: str = "date_inurl",
    topic_term: str | None = None,
) -> str:
    """Build one day-level Google query for a source/day/section."""
    target = domain
    if section_path:
        target = f"{domain}/{normalize_section_path(section_path).strip('/')}"
    if query_mode == "date_range":
        previous_day = day - timedelta(days=1)
        next_day = day + timedelta(days=1)
        query = f"site:{target} after:{previous_day.isoformat()} before:{next_day.isoformat()}"
    else:
        date_path = f"/{day.year}/{day.month}/{day.day}/"
        query = f"site:{target} inurl:{date_path}"
    if topic_term and str(topic_term).strip():
        query = f"{query} {quote_query_term(str(topic_term).strip())}"
    return query


def iter_dates(from_date: date, to_date: date):
    """Yield each date in an inclusive range."""
    current = from_date
    while current <= to_date:
        yield current
        current += timedelta(days=1)


def source_domain(source: pd.Series) -> str:
    """Return a normalized source domain."""
    domain = source.get("domain")
    if pd.notna(domain) and str(domain).strip():
        return normalized_host(str(domain).strip())
    canonical = source.get("canonical_url")
    if pd.isna(canonical):
        return ""
    return normalized_host(urlparse(str(canonical)).netloc)


def likely_source_url(source: pd.Series, url: str) -> bool:
    """Keep only URLs on the requested source domain."""
    domain = source_domain(source)
    return normalized_host(urlparse(url).netloc) == domain


def url_row(
    source: pd.Series,
    url: str,
    *,
    query: str,
    current_day: date,
    shard: str,
    query_mode: str,
    topic_term: str | None,
    start: int,
    total_results: object,
    search_time: object,
    item: dict[str, object],
) -> dict[str, object]:
    """Return one Google discovery row."""
    return {
        "source_id": source.get("source_id"),
        "source_name": source.get("source_name"),
        "source_url": source.get("canonical_url"),
        "url": url,
        "canonical_url": url,
        "date_published": current_day.isoformat(),
        "lastmod": pd.NA,
        "topic": pd.NA,
        "discovery_strategy": "google_date_inurl",
        "category_url": pd.NA,
        "listing_url": pd.NA,
        "listing_page": pd.NA,
        "status": 200,
        "error": pd.NA,
        "google_query": query,
        "google_query_mode": query_mode,
        "google_topic_term": topic_term or pd.NA,
        "google_shard": shard,
        "google_start": start,
        "google_total_results": total_results,
        "google_search_time": search_time,
        "google_title": item.get("title", pd.NA),
        "google_snippet": item.get("snippet", pd.NA),
        "google_display_link": item.get("displayLink", pd.NA),
        "discovered_at": datetime.now(timezone.utc).isoformat(),
    }


def error_row(
    source: pd.Series,
    query: object,
    current_day: object,
    error: object,
    *,
    shard: object = pd.NA,
    query_mode: object = pd.NA,
    topic_term: object = pd.NA,
    start: object = pd.NA,
) -> dict[str, object]:
    """Return one Google discovery error row."""
    return {
        "source_id": source.get("source_id"),
        "source_name": source.get("source_name"),
        "source_url": source.get("canonical_url"),
        "url": pd.NA,
        "canonical_url": pd.NA,
        "date_published": current_day.isoformat() if isinstance(current_day, date) else pd.NA,
        "lastmod": pd.NA,
        "topic": pd.NA,
        "discovery_strategy": "google_date_inurl",
        "category_url": pd.NA,
        "listing_url": pd.NA,
        "listing_page": pd.NA,
        "status": pd.NA,
        "error": error,
        "google_query": query,
        "google_query_mode": query_mode,
        "google_topic_term": topic_term,
        "google_shard": shard,
        "google_start": start,
        "google_total_results": pd.NA,
        "google_search_time": pd.NA,
        "google_title": pd.NA,
        "google_snippet": pd.NA,
        "google_display_link": pd.NA,
        "discovered_at": datetime.now(timezone.utc).isoformat(),
    }


def dedupe_google_discovery(discovered: pd.DataFrame) -> pd.DataFrame:
    """Dedupe Google discovery while preserving error rows."""
    if discovered.empty or not {"source_id", "url"}.issubset(discovered.columns):
        return discovered.reset_index(drop=True)
    url_rows = discovered[discovered["url"].notna()].drop_duplicates(["source_id", "url"], keep="last")
    error_rows = discovered[discovered["url"].isna()]
    return pd.concat([url_rows, error_rows], ignore_index=True).reset_index(drop=True)


def build_google_report(discovered: pd.DataFrame) -> str:
    """Create a compact report for Google discovery."""
    lines = [
        "# Google Search Discovery Report",
        "",
        f"- Rows: {len(discovered):,}",
        f"- Sources: {discovered['source_id'].nunique() if not discovered.empty else 0:,}",
        f"- URLs: {discovered['url'].notna().sum() if 'url' in discovered else 0:,}",
        f"- Errors: {discovered['error'].notna().sum() if 'error' in discovered else 0:,}",
        "",
    ]
    if discovered.empty:
        return "\n".join(lines)

    by_source = (
        discovered.groupby(["source_id", "source_name"], dropna=False)
        .agg(
            rows=("source_id", "size"),
            urls=("url", lambda value: value.notna().sum()),
            errors=("error", lambda value: value.notna().sum()),
            days=("date_published", lambda value: value.dropna().nunique()),
            min_date=("date_published", "min"),
            max_date=("date_published", "max"),
        )
        .reset_index()
        .sort_values(["urls", "rows"], ascending=False)
    )
    by_day = (
        discovered[discovered["url"].notna()]
        .groupby(["source_id", "date_published"], dropna=False)
        .size()
        .rename("urls")
        .reset_index()
        .sort_values("urls", ascending=False)
        .head(30)
    )
    by_shard = (
        discovered.groupby(["source_id", "google_query_mode", "google_shard"], dropna=False)
        .agg(rows=("source_id", "size"), urls=("url", lambda value: value.notna().sum()))
        .reset_index()
        .sort_values(["source_id", "urls"], ascending=[True, False])
    )
    lines.extend(
        [
            "## By Source",
            "",
            markdown_table(by_source),
            "",
            "## Top Source-Days",
            "",
            markdown_table(by_day),
            "",
            "## By Shard",
            "",
            markdown_table(by_shard),
            "",
        ]
    )
    return "\n".join(lines)


def write_google_outputs(
    discovered: pd.DataFrame,
    report: str,
    discovery_dir: Path,
    reports_dir: Path,
) -> GoogleDiscoveryOutputs:
    """Write Google discovery outputs."""
    discovery_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    csv_path = discovery_dir / "discovered_urls_google.csv"
    parquet_path = discovery_dir / "discovered_urls_google.parquet"
    report_path = reports_dir / "google_discovery_report.md"

    discovered.to_csv(csv_path, index=False, encoding="utf-8")
    parquet_error = None
    try:
        discovered.to_parquet(parquet_path, index=False)
    except ImportError as exc:
        parquet_error = str(exc).splitlines()[0]
        parquet_path = None
    report_path.write_text(report, encoding="utf-8")
    return GoogleDiscoveryOutputs(csv_path, parquet_path, report_path, parquet_error)


def google_credentials(api_key: str | None = None, cse_id: str | None = None) -> tuple[str, str]:
    """Resolve Google API credentials from args or environment variables."""
    key = api_key or os.environ.get("GOOGLE_CUSTOM_SEARCH_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    cx = cse_id or os.environ.get("GOOGLE_CUSTOM_SEARCH_CX") or os.environ.get("GOOGLE_CSE_ID")
    if not key:
        raise ValueError("Missing Google API key. Set GOOGLE_CUSTOM_SEARCH_API_KEY or pass --google-api-key.")
    if not cx:
        raise ValueError("Missing Google CSE id. Set GOOGLE_CUSTOM_SEARCH_CX or pass --google-cse-id.")
    return key, cx


def parse_date(value: str) -> date:
    """Parse YYYY-MM-DD dates."""
    return datetime.strptime(value, "%Y-%m-%d").date()


def normalize_query_modes(query_modes: list[str] | None) -> list[str]:
    """Normalize query mode spellings from CLI/user input."""
    values = query_modes or ["date_inurl"]
    normalized = []
    for value in values:
        mode = str(value).strip().lower().replace("-", "_")
        if mode not in {"date_inurl", "date_range"}:
            raise ValueError(f"Unsupported Google query mode: {value}")
        if mode not in normalized:
            normalized.append(mode)
    return normalized


def quote_query_term(value: str) -> str:
    """Quote multi-word query terms for Google."""
    if re.search(r"\s", value) and not (value.startswith('"') and value.endswith('"')):
        return f'"{value}"'
    return value


def topic_suffix(topic_term: str | None) -> str:
    """Return a compact log suffix for topic shards."""
    return f" topic={topic_term}" if topic_term else ""


def normalize_section_path(section_path: str) -> str:
    """Normalize a section path for site: queries."""
    parsed = urlparse(section_path)
    path = parsed.path if parsed.netloc else section_path
    return path.strip("/")


def normalized_host(host: str) -> str:
    """Normalize a host for comparisons."""
    host = host.lower().strip()
    return host[4:] if host.startswith("www.") else host


def canonical_url(value: object) -> str:
    """Strip fragments and normalize a result URL."""
    if pd.isna(value):
        return ""
    parsed = urlparse(str(value).strip())
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, ""))


def count_urls(rows: list[dict[str, object]]) -> int:
    """Count URL rows in an in-memory row list."""
    return sum(1 for row in rows if pd.notna(row.get("url")))

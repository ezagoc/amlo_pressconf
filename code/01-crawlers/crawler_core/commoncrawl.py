"""Common Crawl CDX URL discovery for newspaper sources."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import pandas as pd

from crawler_core.capabilities import fetch, markdown_table
from crawler_core.category_pagination import infer_topic_from_url
from crawler_core.sitemaps import likely_article_url


COLLINFO_URL = "https://index.commoncrawl.org/collinfo.json"
DEFAULT_BODY_TEXT_LIMIT = 80_000_000
DEFAULT_RECENT_INDEXES = (
    "CC-MAIN-2026-34",
    "CC-MAIN-2026-30",
    "CC-MAIN-2026-25",
    "CC-MAIN-2026-21",
    "CC-MAIN-2026-18",
    "CC-MAIN-2026-13",
)
DEFAULT_ARTICLE_PATHS = (
    "noticias",
    "local",
    "nacional",
    "mexico",
    "politica",
    "opinion",
    "columnas",
    "estado",
    "estados",
    "mundo",
    "economia",
    "seguridad",
    "policiaca",
    "deportes",
    "salud",
    "cultura",
    "espectaculos",
    "juarez",
    "el-paso",
    "estados-unidos",
)
YEAR_RE = re.compile(r"CC-MAIN-(20\d{2})-\d+")
MONTH_WORDS = {
    "jan",
    "feb",
    "mar",
    "apr",
    "may",
    "jun",
    "jul",
    "aug",
    "sep",
    "oct",
    "nov",
    "dec",
    "ene",
    "abr",
    "ago",
    "dic",
}


@dataclass(frozen=True)
class CommonCrawlDiscoveryOutputs:
    """Paths written by Common Crawl discovery."""

    discovered_csv: Path
    discovered_parquet: Path | None
    report_path: Path
    parquet_error: str | None = None


def load_commoncrawl_sources(
    capabilities_path: Path,
    *,
    strategies: set[str] | None = None,
) -> pd.DataFrame:
    """Load sources for Common Crawl discovery."""
    capabilities = pd.read_csv(capabilities_path)
    if strategies:
        capabilities = capabilities[capabilities["recommended_strategy"].isin(strategies)].copy()
    return capabilities.reset_index(drop=True)


def load_commoncrawl_indexes(
    *,
    index_ids: list[str] | None = None,
    years: set[int] | None = None,
    limit_indexes: int | None = None,
    timeout: float = 45.0,
) -> list[str]:
    """Return selected Common Crawl index IDs."""
    if index_ids:
        selected = [normalize_index_id(index_id) for index_id in index_ids]
    else:
        response = fetch(COLLINFO_URL, timeout, body_text_limit=5_000_000, profile="browser")
        selected = parse_collinfo_indexes(response.get("text") or "")
        if not selected:
            selected = list(DEFAULT_RECENT_INDEXES)
    if years:
        selected = [index_id for index_id in selected if index_year(index_id) in years]
    if limit_indexes is not None:
        selected = selected[:limit_indexes]
    return selected


def discover_commoncrawl_urls(
    sources: pd.DataFrame,
    *,
    index_ids: list[str],
    source_ids: list[str] | None = None,
    limit_sources: int | None = None,
    path_patterns: list[str] | None = None,
    include_broad_domain: bool = False,
    limit_per_query: int | None = 50_000,
    max_urls_per_source: int | None = None,
    page_size: int | None = None,
    timeout: float = 90.0,
    pause_seconds: float = 1.0,
    body_text_limit: int = DEFAULT_BODY_TEXT_LIMIT,
) -> pd.DataFrame:
    """Discover likely article URLs from Common Crawl CDX indexes."""
    if source_ids:
        sources = sources[sources["source_id"].isin(source_ids)].reset_index(drop=True)
    if limit_sources is not None:
        sources = sources.head(limit_sources)

    rows: list[dict[str, object]] = []
    total_sources = len(sources)
    for source_number, source in sources.iterrows():
        source_id = source.get("source_id")
        patterns = commoncrawl_url_patterns(
            source,
            path_patterns=path_patterns,
            include_broad_domain=include_broad_domain,
        )
        print(f"\n=== Common Crawl source {source_number + 1}/{total_sources}: {source_id} ===")
        if not patterns:
            rows.append(error_row(source, pd.NA, pd.NA, pd.NA, "no_commoncrawl_url_pattern"))
            continue
        seen_source_urls: set[str] = set()
        for index_number, index_id in enumerate(index_ids, start=1):
            for pattern in patterns:
                if max_urls_per_source is not None and len(seen_source_urls) >= max_urls_per_source:
                    print(f"  {source_id}: hit max_urls_per_source={max_urls_per_source}; stopping source")
                    break
                print(
                    f"  {source_id}: index {index_number}/{len(index_ids)} "
                    f"{index_id} pattern={pattern}"
                )
                try:
                    query_rows = discover_commoncrawl_query(
                        source,
                        index_id=index_id,
                        url_pattern=pattern,
                        seen_source_urls=seen_source_urls,
                        limit_per_query=limit_per_query,
                        page_size=page_size,
                        timeout=timeout,
                        body_text_limit=body_text_limit,
                    )
                except Exception as exc:
                    print(f"!!! {source_id}: {index_id} unexpected query failure: {type(exc).__name__}: {exc}")
                    query_rows = [error_row(source, index_id, pattern, pd.NA, f"{type(exc).__name__}: {exc}")]
                rows.extend(query_rows)
                urls = sum(1 for row in query_rows if pd.notna(row.get("url")))
                errors = sum(1 for row in query_rows if pd.notna(row.get("error")))
                print(
                    f"    rows={len(query_rows):,}, new_urls={urls:,}, "
                    f"errors={errors:,}, source_total={len(seen_source_urls):,}"
                )
                if pause_seconds:
                    time.sleep(pause_seconds)
            else:
                continue
            break
        if not seen_source_urls:
            rows.append(error_row(source, pd.NA, "; ".join(patterns), pd.NA, "no_likely_article_urls_found"))
        print(f"=== Finished {source_id}: source_urls={len(seen_source_urls):,} ===")

    discovered = pd.DataFrame(rows)
    if not discovered.empty and {"source_id", "url"}.issubset(discovered.columns):
        url_rows = discovered[discovered["url"].notna()].drop_duplicates(["source_id", "url"], keep="last")
        error_rows = discovered[discovered["url"].isna()]
        discovered = pd.concat([url_rows, error_rows], ignore_index=True)
    return discovered.reset_index(drop=True)


def discover_commoncrawl_query(
    source: pd.Series,
    *,
    index_id: str,
    url_pattern: str,
    seen_source_urls: set[str],
    limit_per_query: int | None,
    page_size: int | None,
    timeout: float,
    body_text_limit: int,
) -> list[dict[str, object]]:
    """Run one Common Crawl CDX query and return discovery rows."""
    query_url = commoncrawl_query_url(
        index_id=index_id,
        url_pattern=url_pattern,
        limit=limit_per_query,
        page_size=page_size,
    )
    response = fetch(query_url, timeout, body_text_limit=body_text_limit, profile="browser")
    status = response.get("status")
    if status == 404:
        return []
    if not isinstance(status, int) or status < 200 or status >= 300:
        error = response.get("error")
        if pd.isna(error):
            error = f"http_status_{status}"
        return [error_row(source, index_id, url_pattern, status, error)]

    text = response.get("text") or ""
    records, parse_errors = parse_cdx_json_lines(str(text))
    rows: list[dict[str, object]] = []
    for record in records:
        url = clean_commoncrawl_url(record.get("url"))
        if pd.isna(url):
            continue
        if url in seen_source_urls:
            continue
        if not likely_commoncrawl_article_url(url):
            continue
        seen_source_urls.add(str(url))
        rows.append(url_row(source, record, str(url), index_id, url_pattern, status))
    if parse_errors:
        rows.append(error_row(source, index_id, url_pattern, status, f"json_parse_errors_{parse_errors}"))
    return rows


def parse_collinfo_indexes(text: str) -> list[str]:
    """Parse Common Crawl collinfo JSON into newest-first index IDs."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    indexes: list[str] = []
    for item in payload:
        index_id = item.get("id")
        if not index_id:
            continue
        indexes.append(normalize_index_id(str(index_id)))
    return indexes


def parse_cdx_json_lines(text: str) -> tuple[list[dict[str, object]], int]:
    """Parse newline-delimited CDX JSON, ignoring malformed trailing fragments."""
    records: list[dict[str, object]] = []
    errors = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            errors += 1
            continue
        if isinstance(item, dict):
            records.append(item)
    return records, errors


def commoncrawl_query_url(
    *,
    index_id: str,
    url_pattern: str,
    limit: int | None,
    page_size: int | None,
) -> str:
    """Build a Common Crawl CDX query URL."""
    cdx_url = url_pattern
    match_type = None
    if url_pattern.endswith("/*"):
        cdx_url = url_pattern[:-1]
        match_type = "prefix"
    params: list[tuple[str, str]] = [
        ("url", cdx_url),
        ("output", "json"),
        ("fl", "url,timestamp,status,mime,mime-detected,digest,length,offset,filename,languages"),
        ("filter", "status:200"),
        ("filter", "mime:text/html"),
        ("collapse", "urlkey"),
    ]
    if match_type:
        params.append(("matchType", match_type))
    if limit is not None:
        params.append(("limit", str(limit)))
    if page_size is not None:
        params.append(("pageSize", str(page_size)))
    return f"https://index.commoncrawl.org/{normalize_index_id(index_id)}-index?{urlencode(params)}"


def commoncrawl_url_patterns(
    source: pd.Series,
    *,
    path_patterns: list[str] | None = None,
    include_broad_domain: bool = False,
) -> list[str]:
    """Return conservative CDX URL patterns for a source."""
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
    elif host.count(".") >= 1:
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


def article_path_candidates(source: pd.Series, *, path_patterns: list[str] | None) -> list[str]:
    """Return likely article path prefixes for a source."""
    candidates: list[str] = []
    if path_patterns:
        candidates.extend(clean_path_pattern(pattern) for pattern in path_patterns)
        return [value for value in dedupe_preserve_order(candidates) if value]

    hints = source.get("category_hints")
    if pd.notna(hints):
        for raw_hint in str(hints).split(";"):
            parsed = urlparse(raw_hint.strip())
            segments = [segment for segment in parsed.path.strip("/").split("/") if segment]
            if not segments:
                continue
            if segments[0].lower() in {"seccion", "secciones", "category", "categoria"} and len(segments) >= 2:
                candidates.append(clean_path_pattern("/".join(segments[1:])))
            if segments[0].lower() not in {"tag", "tags", "feed", "rss"}:
                candidates.append(clean_path_pattern("/".join(segments)))

    candidates.extend(DEFAULT_ARTICLE_PATHS)
    return [value for value in dedupe_preserve_order(candidates) if value]


def clean_path_pattern(value: str) -> str:
    """Normalize a user or registry path pattern for CDX queries."""
    cleaned = value.strip().strip("/")
    if cleaned.endswith("*"):
        cleaned = cleaned[:-1].strip("/")
    return cleaned


def likely_commoncrawl_article_url(url: object) -> bool:
    """Return True when a CDX URL is likely to be a newspaper article."""
    if pd.isna(url):
        return False
    text = str(url)
    parsed = urlparse(text)
    segments = [segment for segment in parsed.path.strip("/").split("/") if segment]
    if len(segments) < 2:
        return False
    lowered = text.lower()
    if any(token in lowered for token in ["/tag/", "/tags/", "/author/", "/search/", "/feed/", "/rss/"]):
        return False
    if likely_article_url(text):
        return True
    return has_article_date_path(segments) and slug_word_count(segments[-1]) >= 3


def has_article_date_path(segments: list[str]) -> bool:
    """Return True when URL path segments contain a likely article date."""
    lowered = [segment.lower() for segment in segments]
    for i, segment in enumerate(lowered):
        if re.fullmatch(r"20[0-3][0-9]", segment):
            return True
        if segment in MONTH_WORDS and i > 0:
            return True
    return False


def clean_commoncrawl_url(url: object) -> object:
    """Normalize a CDX URL enough for dedupe/extraction."""
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


def url_row(
    source: pd.Series,
    record: dict[str, object],
    url: str,
    index_id: str,
    url_pattern: str,
    status: object,
) -> dict[str, object]:
    """Return a Common Crawl discovery row compatible with the HTML extractor."""
    return {
        "source_id": source.get("source_id"),
        "source_name": source.get("source_name"),
        "source_url": source.get("canonical_url"),
        "url": url,
        "canonical_url": url,
        "date_published": pd.NA,
        "lastmod": pd.NA,
        "topic": infer_topic_from_url(url),
        "discovery_strategy": "commoncrawl",
        "commoncrawl_index": index_id,
        "commoncrawl_query": url_pattern,
        "commoncrawl_timestamp": record.get("timestamp"),
        "commoncrawl_mime": record.get("mime"),
        "commoncrawl_mime_detected": record.get("mime-detected"),
        "commoncrawl_status": record.get("status"),
        "commoncrawl_digest": record.get("digest"),
        "commoncrawl_length": record.get("length"),
        "commoncrawl_offset": record.get("offset"),
        "commoncrawl_filename": record.get("filename"),
        "commoncrawl_languages": record.get("languages"),
        "status": status,
        "error": pd.NA,
        "discovered_at": pd.Timestamp.utcnow().isoformat(),
    }


def error_row(
    source: pd.Series,
    index_id: object,
    url_pattern: object,
    status: object,
    error: object,
) -> dict[str, object]:
    """Return a Common Crawl discovery error row."""
    return {
        "source_id": source.get("source_id"),
        "source_name": source.get("source_name"),
        "source_url": source.get("canonical_url"),
        "url": pd.NA,
        "canonical_url": pd.NA,
        "date_published": pd.NA,
        "lastmod": pd.NA,
        "topic": pd.NA,
        "discovery_strategy": "commoncrawl",
        "commoncrawl_index": index_id,
        "commoncrawl_query": url_pattern,
        "commoncrawl_timestamp": pd.NA,
        "commoncrawl_mime": pd.NA,
        "commoncrawl_mime_detected": pd.NA,
        "commoncrawl_status": pd.NA,
        "commoncrawl_digest": pd.NA,
        "commoncrawl_length": pd.NA,
        "commoncrawl_offset": pd.NA,
        "commoncrawl_filename": pd.NA,
        "commoncrawl_languages": pd.NA,
        "status": status,
        "error": error,
        "discovered_at": pd.Timestamp.utcnow().isoformat(),
    }


def build_commoncrawl_report(discovered: pd.DataFrame) -> str:
    """Create a markdown report for Common Crawl discovery."""
    lines = [
        "# Common Crawl Discovery Report",
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
                indexes=("commoncrawl_index", lambda value: value.dropna().nunique()),
            )
            .reset_index()
            .sort_values(["urls", "rows"], ascending=False)
        )
        lines.extend(["## By Source", "", markdown_table(summary), ""])
        by_index = (
            discovered[discovered["url"].notna()]
            .groupby(["source_id", "commoncrawl_index"], dropna=False)
            .size()
            .reset_index(name="urls")
            .sort_values(["source_id", "commoncrawl_index"])
        )
        lines.extend(["## By Source And Index", "", markdown_table(by_index.head(300)), ""])
    return "\n".join(lines)


def write_commoncrawl_outputs(
    discovered: pd.DataFrame,
    report: str,
    discovery_dir: Path,
    reports_dir: Path,
) -> CommonCrawlDiscoveryOutputs:
    """Write Common Crawl discovery CSV/parquet and report files."""
    discovery_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    discovered_csv = discovery_dir / "discovered_urls_commoncrawl.csv"
    discovered_parquet = discovery_dir / "discovered_urls_commoncrawl.parquet"
    report_path = reports_dir / "commoncrawl_discovery_report.md"
    discovered.to_csv(discovered_csv, index=False, encoding="utf-8")
    parquet_error = None
    try:
        discovered.to_parquet(discovered_parquet, index=False)
    except ImportError as exc:
        discovered_parquet = None
        parquet_error = str(exc).splitlines()[0]
    report_path.write_text(report, encoding="utf-8")
    return CommonCrawlDiscoveryOutputs(discovered_csv, discovered_parquet, report_path, parquet_error)


def normalize_index_id(index_id: str) -> str:
    """Return an index ID without a trailing '-index' suffix."""
    return index_id.removesuffix("-index")


def index_year(index_id: str) -> int | None:
    """Return the year in a Common Crawl index ID."""
    match = YEAR_RE.search(index_id)
    return int(match.group(1)) if match else None


def slug_word_count(segment: str) -> int:
    """Return a rough count of slug words in a path segment."""
    return len([part for part in re.split(r"[-_]+", segment.strip("-_")) if len(part) >= 2])


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

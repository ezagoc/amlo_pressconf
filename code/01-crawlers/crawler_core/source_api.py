"""Source-specific API/listing discovery adapters."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import pandas as pd
from bs4 import BeautifulSoup, FeatureNotFound

from crawler_core.capabilities import fetch, markdown_table
from crawler_core.category_pagination import infer_topic_from_url
from crawler_core.sitemaps import likely_article_url


DIARIO_SECTIONS = (
    "juarez",
    "el-paso",
    "nacional",
    "estado",
    "estados-unidos",
    "internacional",
    "economia",
    "deportes",
    "espectaculos",
    "opinion",
    "viral",
    "vamos",
    "salud",
    "tecnologia",
    "cartones",
)
DIARIO_MORE_ENDPOINT = "https://diario.mx/com/snr/dmx/show-more-section.jsp"
ARTICLE_URL_RE = re.compile(r"https?://(?:www\.)?diario\.mx/[^\s\"'<>]+?\.html", flags=re.I)
DIARIO_AJAX_HEADERS = [
    "Origin: https://diario.mx",
]


@dataclass(frozen=True)
class SourceApiDiscoveryOutputs:
    """Paths written by source-specific API discovery."""

    discovered_csv: Path
    discovered_parquet: Path | None
    report_path: Path
    parquet_error: str | None = None


def load_source_api_sources(
    capabilities_path: Path,
    *,
    source_ids: list[str] | None = None,
) -> pd.DataFrame:
    """Load source rows for source-specific adapters."""
    capabilities = pd.read_csv(capabilities_path)
    if source_ids:
        capabilities = capabilities[capabilities["source_id"].isin(source_ids)].copy()
    return capabilities.reset_index(drop=True)


def discover_source_api_urls(
    sources: pd.DataFrame,
    *,
    source_ids: list[str] | None = None,
    limit_sources: int | None = None,
    max_pages_per_section: int = 100,
    max_urls_per_source: int | None = None,
    sections: list[str] | None = None,
    timeout: float = 45.0,
    pause_seconds: float = 0.2,
    fetch_profile: str = "browser",
) -> pd.DataFrame:
    """Run source-specific URL discovery adapters."""
    if source_ids:
        sources = sources[sources["source_id"].isin(source_ids)].reset_index(drop=True)
    if limit_sources is not None:
        sources = sources.head(limit_sources)

    rows: list[dict[str, object]] = []
    total_sources = len(sources)
    for source_number, source in sources.iterrows():
        source_id = str(source.get("source_id"))
        print(f"\n=== Source API {source_number + 1}/{total_sources}: {source_id} ===")
        if source_id == "diario":
            source_rows = discover_diario_load_more_urls(
                source,
                sections=sections,
                max_pages_per_section=max_pages_per_section,
                max_urls_per_source=max_urls_per_source,
                timeout=timeout,
                pause_seconds=pause_seconds,
                fetch_profile=fetch_profile,
            )
        else:
            source_rows = [error_row(source, pd.NA, pd.NA, pd.NA, "unsupported_source_api_adapter")]
        rows.extend(source_rows)
        urls = sum(1 for row in source_rows if pd.notna(row.get("url")))
        errors = sum(1 for row in source_rows if pd.notna(row.get("error")))
        print(f"=== Finished {source_id}: rows={len(source_rows):,}, urls={urls:,}, errors={errors:,} ===")
    discovered = pd.DataFrame(rows)
    return dedupe_source_api_discovery(discovered)


def discover_diario_load_more_urls(
    source: pd.Series,
    *,
    sections: list[str] | None,
    max_pages_per_section: int,
    max_urls_per_source: int | None,
    timeout: float,
    pause_seconds: float,
    fetch_profile: str,
) -> list[dict[str, object]]:
    """Discover Diario URLs through its show-more-section.jsp endpoint."""
    selected_sections = sections or list(DIARIO_SECTIONS)
    rows: list[dict[str, object]] = []
    seen_urls: set[str] = set()

    for section_number, section in enumerate(selected_sections, start=1):
        if max_urls_per_source is not None and len(seen_urls) >= max_urls_per_source:
            print(f"  diario: hit max_urls_per_source={max_urls_per_source}; stopping source")
            break
        section = section.strip().strip("/")
        if not section:
            continue
        initial_url = f"https://diario.mx/seccion/{section}/"
        print(f"  diario: section {section_number}/{len(selected_sections)} {section}")

        first_page = fetch(initial_url, timeout, profile=fetch_profile)
        first_status = first_page.get("status")
        if not is_ok(first_status):
            rows.append(error_row(source, section, initial_url, first_status, status_error(first_page)))
            print(f"    page 1 failed status={first_status}, error={status_error(first_page)}")
            continue

        button = diario_button_config(first_page.get("text") or "", section)
        endpoint = str(button.get("more") or DIARIO_MORE_ENDPOINT)
        page_size = int_or_default(button.get("long"), 15)
        article_urls = diario_article_urls(first_page.get("text") or "")
        new_count = append_url_rows(
            rows,
            source,
            article_urls,
            seen_urls,
            section=section,
            listing_url=initial_url,
            page_number=1,
            endpoint_url=pd.NA,
            status=first_status,
        )
        print(f"    page 1: links={len(article_urls):,}, new={new_count:,}, total={len(seen_urls):,}")

        empty_pages = 0
        first_endpoint_page = int_or_default(button.get("page"), 2)
        last_endpoint_page = first_endpoint_page + max_pages_per_section - 2
        for page_number in range(first_endpoint_page, last_endpoint_page + 1):
            if max_urls_per_source is not None and len(seen_urls) >= max_urls_per_source:
                print(f"    hit max_urls_per_source={max_urls_per_source}; stopping section")
                break
            endpoint_url = diario_more_url(
                endpoint=endpoint,
                section=section,
                page_number=page_number,
                page_size=page_size,
                content_type=int_or_default(button.get("type"), 1),
            )
            response = fetch(
                endpoint_url,
                timeout,
                profile="ajax" if fetch_profile == "browser" else fetch_profile,
                headers=DIARIO_AJAX_HEADERS,
                referer=initial_url,
            )
            status = response.get("status")
            if not is_ok(status):
                rows.append(error_row(source, section, endpoint_url, status, status_error(response)))
                print(f"    page {page_number}: failed status={status}, error={status_error(response)}")
                break
            text = response.get("text") or ""
            article_urls = diario_article_urls(text)
            new_count = append_url_rows(
                rows,
                source,
                article_urls,
                seen_urls,
                section=section,
                listing_url=initial_url,
                page_number=page_number,
                endpoint_url=endpoint_url,
                status=status,
            )
            print(
                f"    page {page_number}: links={len(article_urls):,}, "
                f"new={new_count:,}, total={len(seen_urls):,}"
            )
            if not article_urls or new_count == 0:
                empty_pages += 1
            else:
                empty_pages = 0
            if empty_pages >= 2:
                print("    stopping section: two empty/repeated endpoint pages")
                break
            if pause_seconds:
                time.sleep(pause_seconds)

        archive_empty_pages = 0
        for archive_page_number in range(1, max_pages_per_section + 1):
            if max_urls_per_source is not None and len(seen_urls) >= max_urls_per_source:
                print(f"    hit max_urls_per_source={max_urls_per_source}; stopping section archive")
                break
            archive_url = diario_section_archive_url(section, archive_page_number)
            response = fetch(archive_url, timeout, profile=fetch_profile)
            status = response.get("status")
            if not is_ok(status):
                rows.append(error_row(source, section, archive_url, status, status_error(response)))
                print(f"    archive {archive_page_number}: failed status={status}, error={status_error(response)}")
                break
            text = response.get("text") or ""
            article_urls = diario_article_urls(text)
            new_count = append_url_rows(
                rows,
                source,
                article_urls,
                seen_urls,
                section=section,
                listing_url=archive_url,
                page_number=archive_page_number,
                endpoint_url=archive_url,
                status=status,
            )
            print(
                f"    archive {archive_page_number}: links={len(article_urls):,}, "
                f"new={new_count:,}, total={len(seen_urls):,}"
            )
            if not article_urls or new_count == 0:
                archive_empty_pages += 1
            else:
                archive_empty_pages = 0
            if archive_empty_pages >= 2:
                print("    stopping section archive: two empty/repeated pages")
                break
            if pause_seconds:
                time.sleep(pause_seconds)

    if not seen_urls:
        rows.append(error_row(source, "diario", pd.NA, pd.NA, "no_source_api_urls_found"))
    return rows


def diario_more_url(
    *,
    endpoint: str,
    section: str,
    page_number: int,
    page_size: int,
    content_type: int,
) -> str:
    """Build a Diario load-more endpoint URL."""
    params = {
        "page": str(page_number),
        "section": section,
        "long": str(page_size),
        "type": str(content_type),
    }
    return f"{endpoint}?{urlencode(params)}"


def diario_section_archive_url(section: str, archive_page_number: int) -> str:
    """Build a Diario section archive URL exposed by the live listing page."""
    return f"https://diario.mx/seccion/{section}/?{urlencode({'ch': str(archive_page_number)})}"


def diario_button_config(html: str, section: str) -> dict[str, object]:
    """Extract Diario load-more configuration from the section page."""
    soup = parse_html(html)
    button = soup.select_one("button.btn-more[data-more]")
    if button is None:
        return {"more": DIARIO_MORE_ENDPOINT, "page": 2, "long": 15, "section": section, "type": 1}
    return {
        "more": button.get("data-more") or DIARIO_MORE_ENDPOINT,
        "page": button.get("data-page") or 2,
        "long": button.get("data-long") or 15,
        "section": button.get("data-section") or section,
        "type": button.get("data-type") or 1,
    }


def diario_article_urls(html: str) -> list[str]:
    """Extract Diario article URLs from HTML or JSON-like fragments."""
    urls: list[str] = []
    soup = parse_html(html)
    for link in soup.find_all("a", href=True):
        href = urljoin("https://diario.mx/", str(link.get("href")).strip())
        if is_diario_article_url(href):
            urls.append(clean_url(href))
    for match in ARTICLE_URL_RE.finditer(html):
        url = match.group(0).replace("\\/", "/")
        if is_diario_article_url(url):
            urls.append(clean_url(url))
    return dedupe_preserve_order(urls)


def is_diario_article_url(url: object) -> bool:
    """Return True for Diario article URLs."""
    if pd.isna(url):
        return False
    text = str(url)
    parsed = urlparse(text)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host != "diario.mx":
        return False
    if not text.lower().endswith(".html"):
        return False
    return likely_article_url(text)


def append_url_rows(
    rows: list[dict[str, object]],
    source: pd.Series,
    article_urls: list[str],
    seen_urls: set[str],
    *,
    section: str,
    listing_url: str,
    page_number: int,
    endpoint_url: object,
    status: object,
) -> int:
    """Append unseen URL rows and return the new count."""
    new_count = 0
    for article_url in article_urls:
        if article_url in seen_urls:
            continue
        seen_urls.add(article_url)
        new_count += 1
        rows.append(
            {
                "source_id": source.get("source_id"),
                "source_name": source.get("source_name"),
                "source_url": source.get("canonical_url"),
                "url": article_url,
                "canonical_url": article_url,
                "date_published": pd.NA,
                "lastmod": pd.NA,
                "topic": infer_topic_from_url(article_url),
                "discovery_strategy": "source_api_load_more",
                "source_api_adapter": "diario_show_more_section",
                "section": section,
                "listing_url": listing_url,
                "listing_page": page_number,
                "endpoint_url": endpoint_url,
                "status": status,
                "error": pd.NA,
                "discovered_at": pd.Timestamp.utcnow().isoformat(),
            }
        )
    return new_count


def error_row(
    source: pd.Series,
    section: object,
    endpoint_url: object,
    status: object,
    error: object,
) -> dict[str, object]:
    """Return a source-API discovery error row."""
    return {
        "source_id": source.get("source_id"),
        "source_name": source.get("source_name"),
        "source_url": source.get("canonical_url"),
        "url": pd.NA,
        "canonical_url": pd.NA,
        "date_published": pd.NA,
        "lastmod": pd.NA,
        "topic": pd.NA,
        "discovery_strategy": "source_api_load_more",
        "source_api_adapter": "diario_show_more_section",
        "section": section,
        "listing_url": pd.NA,
        "listing_page": pd.NA,
        "endpoint_url": endpoint_url,
        "status": status,
        "error": error,
        "discovered_at": pd.Timestamp.utcnow().isoformat(),
    }


def dedupe_source_api_discovery(discovered: pd.DataFrame) -> pd.DataFrame:
    """Dedupe source API discoveries, preserving error rows."""
    if discovered.empty:
        return discovered
    if {"source_id", "url"}.issubset(discovered.columns):
        url_rows = discovered[discovered["url"].notna()].drop_duplicates(["source_id", "url"], keep="last")
        error_rows = discovered[discovered["url"].isna()]
        discovered = pd.concat([url_rows, error_rows], ignore_index=True)
    return discovered.reset_index(drop=True)


def build_source_api_report(discovered: pd.DataFrame) -> str:
    """Create a markdown report for source-specific API discovery."""
    lines = [
        "# Source API Discovery Report",
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
                sections=("section", lambda value: value.dropna().nunique()),
                max_listing_page=("listing_page", "max"),
            )
            .reset_index()
            .sort_values(["urls", "rows"], ascending=False)
        )
        lines.extend(["## By Source", "", markdown_table(summary), ""])
        by_section = (
            discovered[discovered["url"].notna()]
            .groupby(["source_id", "section"], dropna=False)
            .agg(urls=("url", "size"), max_listing_page=("listing_page", "max"))
            .reset_index()
            .sort_values(["source_id", "urls"], ascending=[True, False])
        )
        lines.extend(["## By Section", "", markdown_table(by_section.head(300)), ""])
    return "\n".join(lines)


def write_source_api_outputs(
    discovered: pd.DataFrame,
    report: str,
    discovery_dir: Path,
    reports_dir: Path,
) -> SourceApiDiscoveryOutputs:
    """Write source API discovery CSV/parquet and report files."""
    discovery_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    discovered_csv = discovery_dir / "discovered_urls_source_api.csv"
    discovered_parquet = discovery_dir / "discovered_urls_source_api.parquet"
    report_path = reports_dir / "source_api_discovery_report.md"
    discovered.to_csv(discovered_csv, index=False, encoding="utf-8")
    parquet_error = None
    try:
        discovered.to_parquet(discovered_parquet, index=False)
    except ImportError as exc:
        discovered_parquet = None
        parquet_error = str(exc).splitlines()[0]
    report_path.write_text(report, encoding="utf-8")
    return SourceApiDiscoveryOutputs(discovered_csv, discovered_parquet, report_path, parquet_error)


def is_ok(status: object) -> bool:
    """Return True for HTTP success statuses."""
    return isinstance(status, int) and 200 <= status < 300


def status_error(response: dict[str, object]) -> object:
    """Return a compact fetch error string."""
    error = response.get("error")
    if pd.isna(error):
        return f"http_status_{response.get('status')}"
    return error


def int_or_default(value: object, default: int) -> int:
    """Parse an integer or return a default."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def clean_url(url: str) -> str:
    """Drop fragments and common tracking params."""
    parsed = urlparse(url)
    kept_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}
    ]
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", urlencode(kept_query), ""))


def parse_html(html: str) -> BeautifulSoup:
    """Parse HTML with lxml when available, otherwise use the built-in parser."""
    try:
        return BeautifulSoup(html, "lxml")
    except FeatureNotFound:
        return BeautifulSoup(html, "html.parser")


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

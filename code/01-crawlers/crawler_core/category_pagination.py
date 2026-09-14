"""Category/listing-page URL discovery for newspaper sources."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import pandas as pd
from bs4 import BeautifulSoup, FeatureNotFound

from crawler_core.capabilities import fetch, markdown_table
from crawler_core.sitemaps import likely_article_url


DEFAULT_CATEGORY_PATHS = (
    "noticias",
    "nacional",
    "mexico",
    "politica",
    "opinion",
    "local",
    "estados",
    "mundo",
    "economia",
    "seguridad",
    "deportes",
)
NON_ARTICLE_SEGMENTS = {
    "author",
    "authors",
    "autor",
    "autores",
    "buscar",
    "categoria",
    "categorias",
    "category",
    "feed",
    "login",
    "page",
    "rss",
    "search",
    "seccion",
    "tag",
    "tags",
}
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
NEXT_TEXT_RE = re.compile(r"\b(siguiente|next|más|mas|older|anteriores|ver m[aá]s)\b", flags=re.I)
PAGINATION_PATH_RE = re.compile(r"(^|/)(page|pagina|p)/\d+/?$", flags=re.I)


@dataclass(frozen=True)
class CategoryDiscoveryOutputs:
    """Paths written by category discovery."""

    discovered_csv: Path
    discovered_parquet: Path | None
    report_path: Path
    parquet_error: str | None = None


def load_category_sources(
    capabilities_path: Path,
    *,
    strategy: str = "category_pagination",
    include_custom_html: bool = False,
) -> pd.DataFrame:
    """Load sources for category/listing-page discovery."""
    capabilities = pd.read_csv(capabilities_path)
    strategies = {strategy}
    if include_custom_html:
        strategies.add("custom_html_probe")
    return capabilities[capabilities["recommended_strategy"].isin(strategies)].reset_index(drop=True)


def discover_category_urls(
    sources: pd.DataFrame,
    *,
    source_ids: list[str] | None = None,
    limit_sources: int | None = None,
    max_pages_per_category: int = 25,
    max_categories_per_source: int | None = None,
    max_urls_per_source: int | None = None,
    pagination_style: str = "auto",
    timeout: float = 30.0,
    pause_seconds: float = 0.2,
    fetch_profile: str = "browser",
) -> pd.DataFrame:
    """Discover article URLs by crawling source category/listing pages."""
    if source_ids:
        sources = sources[sources["source_id"].isin(source_ids)].reset_index(drop=True)
    if limit_sources is not None:
        sources = sources.head(limit_sources)

    rows: list[dict[str, object]] = []
    total_sources = len(sources)
    for i, source in sources.iterrows():
        source_id = source.get("source_id")
        print(f"\n=== Category source {i + 1}/{total_sources}: {source_id} ===")
        try:
            source_rows = discover_one_source_categories(
                source,
                max_pages_per_category=max_pages_per_category,
                max_categories=max_categories_per_source,
                max_urls=max_urls_per_source,
                pagination_style=pagination_style,
                timeout=timeout,
                pause_seconds=pause_seconds,
                fetch_profile=fetch_profile,
            )
        except Exception as exc:
            print(f"!!! {source_id}: unexpected source failure: {type(exc).__name__}: {exc}")
            source_rows = [error_row(source, pd.NA, pd.NA, pd.NA, f"{type(exc).__name__}: {exc}")]
        rows.extend(source_rows)
        urls = sum(1 for row in source_rows if pd.notna(row.get("url")))
        errors = sum(1 for row in source_rows if pd.notna(row.get("error")))
        print(f"=== Finished {source_id}: rows={len(source_rows):,}, urls={urls:,}, errors={errors:,} ===")
        if pause_seconds:
            time.sleep(pause_seconds)

    discovered = pd.DataFrame(rows)
    if not discovered.empty and {"source_id", "url"}.issubset(discovered.columns):
        discovered = discovered.drop_duplicates(["source_id", "url"], keep="last").reset_index(drop=True)
    return discovered


def discover_one_source_categories(
    source: pd.Series,
    *,
    max_pages_per_category: int,
    max_categories: int | None,
    max_urls: int | None,
    pagination_style: str,
    timeout: float,
    pause_seconds: float,
    fetch_profile: str,
) -> list[dict[str, object]]:
    """Discover one source's article URLs from listing/category pages."""
    seeds = category_seed_urls(source)
    if max_categories is not None:
        seeds = seeds[:max_categories]
    if not seeds:
        return [error_row(source, pd.NA, pd.NA, pd.NA, "no_category_seeds")]

    source_id = source.get("source_id")
    rows: list[dict[str, object]] = []
    seen_articles: set[str] = set()
    seen_listing_pages: set[str] = set()

    category_index = 0
    while category_index < len(seeds):
        category_url = seeds[category_index]
        category_index += 1
        print(f"  {source_id}: category {category_index}/{len(seeds)} {category_url}")
        current_url = category_url
        chosen_style: str | None = None
        previous_articles: set[str] = set()

        for page_number in range(1, max_pages_per_category + 1):
            if max_urls is not None and len(seen_articles) >= max_urls:
                print(f"  {source_id}: hit max_urls={max_urls}; stopping source")
                return rows
            if current_url in seen_listing_pages:
                print(f"    stopping category: already visited listing page {current_url}")
                break
            seen_listing_pages.add(current_url)

            response = fetch(current_url, timeout, profile=fetch_profile)
            status = response["status"]
            if not isinstance(status, int) or status < 200 or status >= 300:
                error = response["error"]
                if pd.isna(error):
                    error = f"http_status_{status}"
                rows.append(error_row(source, category_url, current_url, status, error))
                print(f"    stopping category: listing page failed status={status}, error={error}")
                break

            page = parse_listing_page(response.get("text") or "", current_url, source)
            for listing_url in page["listing_urls"]:
                if listing_url in seeds or listing_url in seen_listing_pages:
                    continue
                if max_categories is not None and len(seeds) >= max_categories:
                    break
                seeds.append(listing_url)
            new_articles = [url for url in page["article_urls"] if url not in seen_articles]
            for article_url in new_articles:
                seen_articles.add(article_url)
                rows.append(url_row(source, article_url, category_url, current_url, page_number, status))

            print(
                f"    page {page_number}: links={len(page['article_urls']):,}, "
                f"new={len(new_articles):,}, total_source_urls={len(seen_articles):,}"
            )

            if page_number >= max_pages_per_category:
                print(f"    stopping category: hit max_pages_per_category={max_pages_per_category}")
                break
            next_url = next_listing_url(
                category_url=category_url,
                current_url=current_url,
                page=page,
                next_page_number=page_number + 1,
                pagination_style=pagination_style,
                chosen_style=chosen_style,
                previous_articles=previous_articles,
            )
            previous_articles = set(page["article_urls"])
            if not next_url:
                print("    stopping category: no next listing page found")
                break
            if isinstance(next_url, tuple):
                current_url, chosen_style = next_url
            else:
                current_url = next_url
            if pause_seconds:
                time.sleep(pause_seconds)

    if not rows:
        rows.append(error_row(source, pd.NA, pd.NA, pd.NA, "no_article_urls_found"))
    return rows


def category_seed_urls(source: pd.Series) -> list[str]:
    """Build starting category URLs from probe hints and conservative defaults."""
    canonical_url = source.get("canonical_url")
    if pd.isna(canonical_url):
        return []
    base_url = str(canonical_url)
    base_domain = normalized_domain(base_url)
    seeds: list[str] = []

    hints = source.get("category_hints")
    if pd.notna(hints):
        for raw in str(hints).split(";"):
            url = canonicalize_url(raw.strip(), base_url)
            if is_listing_seed(url, base_domain):
                seeds.append(url)

    if should_include_canonical_seed(source):
        seeds.append(strip_fragment(base_url))

    for path in DEFAULT_CATEGORY_PATHS:
        seeds.append(urljoin(base_url.rstrip("/") + "/", path.strip("/") + "/"))

    return dedupe_preserve_order(seeds)


def should_include_canonical_seed(source: pd.Series) -> bool:
    """Return True when the canonical URL itself is likely a listing entry point."""
    canonical_url = source.get("canonical_url")
    if pd.isna(canonical_url):
        return False
    parsed = urlparse(str(canonical_url))
    path = parsed.path.strip("/")
    return bool(path) or str(source.get("recommended_strategy")) == "custom_html_probe"


def is_listing_seed(url: object, base_domain: str) -> bool:
    """Return True for same-site category/listing seed URLs."""
    if pd.isna(url):
        return False
    text = str(url)
    parsed = urlparse(text)
    if not parsed.scheme or not parsed.netloc:
        return False
    if normalized_domain(text) != base_domain:
        return False
    lowered = text.lower()
    if any(lowered.endswith(ext) for ext in STATIC_EXTENSIONS):
        return False
    if any(marker in lowered for marker in ["/feed", "/rss", "outboundfeeds", "securepubads"]):
        return False
    return True


def parse_listing_page(html: str, listing_url: str, source: pd.Series) -> dict[str, object]:
    """Parse listing-page HTML into article links and pagination candidates."""
    soup = parse_html(html)
    article_urls: list[str] = []
    listing_urls: list[str] = []
    next_urls: list[str] = []
    base_domain = normalized_domain(source.get("canonical_url"))
    for link in soup.find_all("a", href=True):
        href = canonicalize_url(link.get("href"), listing_url)
        text = link.get_text(" ", strip=True)
        if is_article_link(href, text, base_domain):
            article_urls.append(strip_tracking_query(href))
        elif is_listing_link(href, text, base_domain):
            listing_urls.append(strip_fragment(href))
        if is_next_link(link, href, base_domain):
            next_urls.append(strip_fragment(href))
    return {
        "article_urls": dedupe_preserve_order(article_urls),
        "listing_urls": dedupe_preserve_order(listing_urls),
        "next_urls": dedupe_preserve_order(next_urls),
    }


def next_listing_url(
    *,
    category_url: str,
    current_url: str,
    page: dict[str, object],
    next_page_number: int,
    pagination_style: str,
    chosen_style: str | None,
    previous_articles: set[str],
) -> str | tuple[str, str] | None:
    """Choose the next listing page URL to try."""
    next_urls = page.get("next_urls") or []
    if next_urls:
        return str(next_urls[0])
    current_articles = set(page.get("article_urls") or [])
    if previous_articles and current_articles and current_articles == previous_articles:
        return None
    if pagination_style == "none":
        return None
    if chosen_style:
        return generated_page_url(category_url, next_page_number, chosen_style)
    if pagination_style != "auto":
        return generated_page_url(category_url, next_page_number, pagination_style)
    return generated_page_url(category_url, next_page_number, "path_page"), "path_page"


def generated_page_url(category_url: str, page_number: int, style: str) -> str | None:
    """Generate a category pagination URL for simple common styles."""
    clean_url = strip_fragment(category_url)
    parsed = urlparse(clean_url)
    if style == "path_page":
        path = parsed.path.rstrip("/") + f"/page/{page_number}/"
        return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))
    if style == "path_number":
        path = parsed.path.rstrip("/") + f"/{page_number}/"
        return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))
    if style in {"query_page", "query_pagina"}:
        key = "page" if style == "query_page" else "pagina"
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query[key] = str(page_number)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", urlencode(query), ""))
    return None


def is_article_link(url: object, anchor_text: str, base_domain: str) -> bool:
    """Return True when a listing-page link looks like an article URL."""
    if pd.isna(url):
        return False
    text = str(url)
    if normalized_domain(text) != base_domain:
        return False
    parsed = urlparse(text)
    segments = [segment for segment in parsed.path.strip("/").split("/") if segment]
    if not segments:
        return False
    if len(segments) == 1:
        return False
    query_keys = {key.lower() for key, _value in parse_qsl(parsed.query, keep_blank_values=True)}
    if PAGINATION_PATH_RE.search(parsed.path) or query_keys.intersection({"page", "paged", "pagina", "p"}):
        return False
    lowered = text.lower()
    if any(lowered.endswith(ext) for ext in STATIC_EXTENSIONS):
        return False
    if any(marker in lowered for marker in ["/feed", "/rss", "/login", "/registro", "/newsletter"]):
        return False
    if segments[0].lower() in NON_ARTICLE_SEGMENTS:
        return False
    last = segments[-1].lower()
    if last.isdigit() and len(segments) <= 2:
        return False
    if likely_article_url(text):
        return True
    if len(anchor_text.strip()) >= 35 and slug_word_count(last) >= 4:
        return True
    return len(segments) >= 2 and slug_word_count(last) >= 5


def is_listing_link(url: object, anchor_text: str, base_domain: str) -> bool:
    """Return True when a link looks like another section/listing page."""
    if pd.isna(url):
        return False
    text = str(url)
    if normalized_domain(text) != base_domain:
        return False
    parsed = urlparse(text)
    segments = [segment.lower() for segment in parsed.path.strip("/").split("/") if segment]
    if not segments:
        return False
    query_keys = {key.lower() for key, _value in parse_qsl(parsed.query, keep_blank_values=True)}
    if PAGINATION_PATH_RE.search(parsed.path) or query_keys.intersection({"page", "paged", "pagina", "p"}):
        return False
    lowered = text.lower()
    if any(lowered.endswith(ext) for ext in STATIC_EXTENSIONS):
        return False
    if any(marker in lowered for marker in ["/feed", "/rss", "/login", "/registro", "/newsletter"]):
        return False
    if is_article_link(url, anchor_text, base_domain):
        return False
    first = segments[0]
    if first in {"seccion", "secciones", "category", "categoria", "categorias"}:
        return len(segments) <= 4
    if first in {"tag", "tags", "tema", "temas"}:
        return len(segments) <= 3
    if first in DEFAULT_CATEGORY_PATHS:
        return len(segments) <= 3
    clean_anchor = anchor_text.strip()
    if len(segments) <= 2 and len(clean_anchor) <= 60 and slug_word_count(segments[-1]) <= 4:
        return True
    return False


def is_next_link(link, url: object, base_domain: str) -> bool:
    """Return True for pagination links."""
    if pd.isna(url) or normalized_domain(url) != base_domain:
        return False
    if is_article_link(url, link.get_text(" ", strip=True), base_domain):
        return False
    rel = " ".join(link.get("rel") or [])
    text = link.get_text(" ", strip=True)
    aria = link.get("aria-label") or ""
    classes = " ".join(link.get("class") or [])
    haystack = " ".join([rel, text, aria, classes])
    parsed = urlparse(str(url))
    query_keys = {key.lower() for key, _value in parse_qsl(parsed.query, keep_blank_values=True)}
    has_pagination_url = bool(PAGINATION_PATH_RE.search(parsed.path)) or bool(
        query_keys.intersection({"page", "paged", "pagina", "p"})
    )
    rel_is_next = "next" in rel.lower()
    short_text = len(text.strip()) <= 30
    return rel_is_next or (has_pagination_url and short_text and bool(NEXT_TEXT_RE.search(haystack)))


def url_row(
    source: pd.Series,
    article_url: str,
    category_url: str,
    listing_url: str,
    page_number: int,
    status: object,
) -> dict[str, object]:
    """Return a discovered category-pagination article URL row."""
    return {
        "source_id": source.get("source_id"),
        "source_name": source.get("source_name"),
        "source_url": source.get("canonical_url"),
        "url": article_url,
        "canonical_url": article_url,
        "date_published": pd.NA,
        "lastmod": pd.NA,
        "topic": infer_topic_from_url(category_url),
        "discovery_strategy": "category_pagination",
        "category_url": category_url,
        "listing_url": listing_url,
        "listing_page": page_number,
        "status": status,
        "error": pd.NA,
        "discovered_at": pd.Timestamp.utcnow().isoformat(),
    }


def error_row(
    source: pd.Series,
    category_url: object,
    listing_url: object,
    status: object,
    error: object,
) -> dict[str, object]:
    """Return a category discovery error row."""
    return {
        "source_id": source.get("source_id"),
        "source_name": source.get("source_name"),
        "source_url": source.get("canonical_url"),
        "url": pd.NA,
        "canonical_url": pd.NA,
        "date_published": pd.NA,
        "lastmod": pd.NA,
        "topic": pd.NA,
        "discovery_strategy": "category_pagination",
        "category_url": category_url,
        "listing_url": listing_url,
        "listing_page": pd.NA,
        "status": status,
        "error": error,
        "discovered_at": pd.Timestamp.utcnow().isoformat(),
    }


def build_category_report(discovered: pd.DataFrame) -> str:
    """Create a markdown report for category discovery."""
    lines = [
        "# Category Discovery Report",
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
                categories=("category_url", lambda value: value.dropna().nunique()),
            )
            .reset_index()
            .sort_values(["urls", "rows"], ascending=False)
        )
        lines.extend(["## By Source", "", markdown_table(summary), ""])
    return "\n".join(lines)


def write_category_outputs(
    discovered: pd.DataFrame,
    report: str,
    discovery_dir: Path,
    reports_dir: Path,
) -> CategoryDiscoveryOutputs:
    """Write category discovery CSV/parquet and report files."""
    discovery_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    discovered_csv = discovery_dir / "discovered_urls_category.csv"
    discovered_parquet = discovery_dir / "discovered_urls_category.parquet"
    report_path = reports_dir / "category_discovery_report.md"
    discovered.to_csv(discovered_csv, index=False, encoding="utf-8")
    parquet_error = None
    try:
        discovered.to_parquet(discovered_parquet, index=False)
    except ImportError as exc:
        discovered_parquet = None
        parquet_error = str(exc).splitlines()[0]
    report_path.write_text(report, encoding="utf-8")
    return CategoryDiscoveryOutputs(discovered_csv, discovered_parquet, report_path, parquet_error)


def parse_html(html: str) -> BeautifulSoup:
    """Parse HTML with lxml when available, otherwise use the built-in parser."""
    try:
        return BeautifulSoup(html, "lxml")
    except FeatureNotFound:
        return BeautifulSoup(html, "html.parser")


def canonicalize_url(value: object, base_url: str) -> object:
    """Resolve a link and remove fragments."""
    if value is None or pd.isna(value):
        return pd.NA
    raw = str(value).strip()
    if not raw or raw.startswith(("javascript:", "mailto:", "tel:")):
        return pd.NA
    return strip_fragment(urljoin(base_url, raw))


def strip_fragment(url: object) -> str:
    """Return a URL without fragment."""
    parsed = urlparse(str(url))
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, ""))


def strip_tracking_query(url: str) -> str:
    """Drop common tracking query parameters from article URLs."""
    parsed = urlparse(url)
    kept = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}
    ]
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", urlencode(kept), ""))


def normalized_domain(url: object) -> str:
    """Return a URL's hostname without leading www."""
    if pd.isna(url):
        return ""
    host = urlparse(str(url)).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def slug_word_count(segment: str) -> int:
    """Return a rough count of slug words in a path segment."""
    return len([part for part in re.split(r"[-_]+", segment.strip("-_")) if len(part) >= 2])


def infer_topic_from_url(url: object) -> object:
    """Infer a simple category/topic from a seed URL path."""
    if pd.isna(url):
        return pd.NA
    segments = [segment for segment in urlparse(str(url)).path.strip("/").split("/") if segment]
    for segment in segments:
        lowered = segment.lower()
        if lowered not in {"seccion", "noticias", "category", "categoria", "page"} and not lowered.isdigit():
            return lowered
    return pd.NA


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

"""MVS Noticias URL discovery helpers."""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import pandas as pd
import requests
import urllib3
from bs4 import BeautifulSoup, FeatureNotFound

if not hasattr(pd, "NA"):
    pd.NA = None

from crawler_core.capabilities import BROWSER_USER_AGENT, markdown_table


SOURCE_ID = "mvsnoticias"
SOURCE_NAME = "MVS Noticias"
BASE_URL = "https://mvsnoticias.com/"
ARTICLE_RE = re.compile(r"/.+?/\d{4}/\d{1,2}/\d{1,2}/[^/?#]+-\d+\.html$", re.I)
TOPIC_RE = re.compile(r"^/temas/[^/?#]+-\d+\.html/?$", re.I)
PAGE_RE = re.compile(r"/pagina/\d+/?$", re.I)

SECTION_SEEDS = (
    "noticias/",
    "nacional/",
    "nacional/cdmx/",
    "nacional/estados/",
    "nacional/policiaca/",
    "mundo/",
    "economia/",
    "opinion.html",
    "entretenimiento/",
    "deportes.html",
)

BROWSER_HEADERS = {
    "User-Agent": BROWSER_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "es-MX,es;q=0.9,en-US;q=0.7,en;q=0.6",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}


@dataclass(frozen=True)
class MvsDiscoveryOutputs:
    """Paths written by MVS discovery."""

    discovered_csv: object
    discovered_parquet: object | None
    report_path: object
    parquet_error: str | None = None


@dataclass
class CheckpointState:
    """Track periodic discovery checkpoint writes."""

    path: Path | None = None
    every: int = 5_000
    last_rows: int = 0


def discover_mvs_urls(
    *,
    max_section_pages: int = 10,
    max_topic_pages: int = 50,
    max_article_pages_to_probe: int = 500,
    max_topics: int | None = None,
    max_urls: int | None = None,
    timeout: float = 45.0,
    pause_seconds: float = 0.1,
    fetch_profile: str = "browser",
    workers: int = 1,
    checkpoint_path: Path | None = None,
    checkpoint_every: int = 5_000,
) -> pd.DataFrame:
    """Discover MVS article URLs by expanding sections, articles, and topic archives."""
    rows: list[dict[str, object]] = []
    seen_articles: set[str] = set()
    seen_listings: set[str] = set()
    seen_topics: set[str] = set()
    article_probe_queue: deque[str] = deque()
    topic_queue: deque[str] = deque()
    checkpoint = CheckpointState(checkpoint_path, checkpoint_every)

    for seed in SECTION_SEEDS:
        listing_url = canonical_url(seed)
        discover_listing_chain(
            listing_url,
            seed_url=listing_url,
            listing_kind="mvs_section",
            max_pages=max_section_pages,
            seen_listings=seen_listings,
            seen_articles=seen_articles,
            article_probe_queue=article_probe_queue,
            topic_queue=topic_queue,
            rows=rows,
            timeout=timeout,
            pause_seconds=pause_seconds,
            fetch_profile=fetch_profile,
            max_urls=max_urls,
        )
        maybe_write_checkpoint(rows, checkpoint)
        if max_urls is not None and len(seen_articles) >= max_urls:
            return finalize_discovered(rows, checkpoint)

    probed_articles = 0
    print(
        f"  mvs_article_probe: queued={len(article_probe_queue):,}, "
        f"limit={max_article_pages_to_probe:,}",
        flush=True,
    )
    workers = max(1, int(workers or 1))
    if workers == 1:
        while article_probe_queue and probed_articles < max_article_pages_to_probe:
            article_url = article_probe_queue.popleft()
            probed_articles += 1
            log_article_probe(probed_articles, max_article_pages_to_probe, seen_topics, article_probe_queue, seen_articles)
            result = probe_article(article_url, timeout, fetch_profile)
            apply_article_probe_result(
                result,
                seen_topics=seen_topics,
                topic_queue=topic_queue,
                seen_articles=seen_articles,
                article_probe_queue=article_probe_queue,
                rows=rows,
            )
            if pause_seconds:
                time.sleep(pause_seconds)
            if max_topics is not None and len(seen_topics) >= max_topics:
                break
            if max_urls is not None and len(seen_articles) >= max_urls:
                return finalize_discovered(rows, checkpoint)
            maybe_write_checkpoint(rows, checkpoint)
    else:
        batch_size = max(25, workers * 8)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            while article_probe_queue and probed_articles < max_article_pages_to_probe:
                remaining = max_article_pages_to_probe - probed_articles
                current_batch_size = min(batch_size, remaining, len(article_probe_queue))
                batch = [article_probe_queue.popleft() for _ in range(current_batch_size)]
                futures = [executor.submit(probe_article, article_url, timeout, fetch_profile) for article_url in batch]
                for future in as_completed(futures):
                    probed_articles += 1
                    log_article_probe(
                        probed_articles,
                        max_article_pages_to_probe,
                        seen_topics,
                        article_probe_queue,
                        seen_articles,
                    )
                    try:
                        result = future.result()
                    except Exception as exc:
                        rows.append(error_row(pd.NA, pd.NA, pd.NA, f"article_probe_failure: {type(exc).__name__}: {exc}"))
                        continue
                    apply_article_probe_result(
                        result,
                        seen_topics=seen_topics,
                        topic_queue=topic_queue,
                        seen_articles=seen_articles,
                        article_probe_queue=article_probe_queue,
                        rows=rows,
                    )
                    if max_topics is not None and len(seen_topics) >= max_topics:
                        break
                    if max_urls is not None and len(seen_articles) >= max_urls:
                        break
                if pause_seconds:
                    time.sleep(pause_seconds)
                if max_topics is not None and len(seen_topics) >= max_topics:
                    break
                if max_urls is not None and len(seen_articles) >= max_urls:
                    return finalize_discovered(rows, checkpoint)
                maybe_write_checkpoint(rows, checkpoint)

    topics_processed = 0
    print(f"  mvs_topic_queue: queued={len(topic_queue):,}", flush=True)
    while topic_queue:
        topic_url = topic_queue.popleft()
        topics_processed += 1
        print(
            f"  mvs_topic_queue: topic {topics_processed:,}"
            f"{f'/{max_topics:,}' if max_topics is not None else ''} {topic_url}",
            flush=True,
        )
        discover_listing_chain(
            topic_url,
            seed_url=topic_url,
            listing_kind="mvs_topic",
            max_pages=max_topic_pages,
            seen_listings=seen_listings,
            seen_articles=seen_articles,
            article_probe_queue=article_probe_queue,
            topic_queue=topic_queue,
            rows=rows,
            timeout=timeout,
            pause_seconds=pause_seconds,
            fetch_profile=fetch_profile,
            max_urls=max_urls,
        )
        maybe_write_checkpoint(rows, checkpoint)
        if max_topics is not None and topics_processed >= max_topics:
            break
        if max_urls is not None and len(seen_articles) >= max_urls:
            break

    return finalize_discovered(rows, checkpoint)


def finalize_discovered(rows: list[dict[str, object]], checkpoint: CheckpointState) -> pd.DataFrame:
    """Dedupe discovery rows and force one final checkpoint."""
    discovered = pd.DataFrame(rows)
    if not discovered.empty and "url" in discovered.columns:
        url_rows = discovered[discovered["url"].notna()].drop_duplicates(
            ["source_id", "url"], keep="last"
        )
        error_rows = discovered[discovered["url"].isna()]
        discovered = pd.concat([url_rows, error_rows], ignore_index=True).reset_index(drop=True)
    write_checkpoint(discovered, checkpoint, force=True)
    return discovered


def maybe_write_checkpoint(rows: list[dict[str, object]], checkpoint: CheckpointState) -> None:
    """Write a checkpoint when enough new rows have accumulated."""
    if checkpoint.path is None or checkpoint.every <= 0:
        return
    if len(rows) - checkpoint.last_rows < checkpoint.every:
        return
    write_checkpoint(pd.DataFrame(rows), checkpoint, force=True)


def write_checkpoint(discovered: pd.DataFrame, checkpoint: CheckpointState, *, force: bool) -> None:
    """Write checkpoint CSV for long MVS discovery runs."""
    if checkpoint.path is None or not force:
        return
    checkpoint.path.parent.mkdir(parents=True, exist_ok=True)
    discovered.to_csv(checkpoint.path, index=False, encoding="utf-8")
    checkpoint.last_rows = len(discovered)
    print(f"  checkpoint: wrote {len(discovered):,} rows to {checkpoint.path}", flush=True)


def log_article_probe(
    probed_articles: int,
    max_article_pages_to_probe: int,
    seen_topics: set[str],
    article_probe_queue: deque[str],
    seen_articles: set[str],
) -> None:
    """Print article-probe progress periodically."""
    if probed_articles == 1 or probed_articles % 25 == 0:
        print(
            f"  mvs_article_probe: {probed_articles:,}/{max_article_pages_to_probe:,} "
            f"topics={len(seen_topics):,}, queued_articles={len(article_probe_queue):,}, "
            f"total_urls={len(seen_articles):,}",
            flush=True,
        )


def probe_article(article_url: str, timeout: float, fetch_profile: str) -> dict[str, object]:
    """Fetch one article and extract topic/related links."""
    response = fetch_mvs(article_url, timeout, profile=fetch_profile)
    status = response["status"]
    if not isinstance(status, int) or not 200 <= status < 300:
        return {"article_url": article_url, "status": status, "topic_urls": [], "article_urls": []}
    page = parse_page(safe_text(response.get("text")), article_url)
    return {
        "article_url": article_url,
        "status": status,
        "topic_urls": page["topic_urls"],
        "article_urls": page["article_urls"],
    }


def apply_article_probe_result(
    result: dict[str, object],
    *,
    seen_topics: set[str],
    topic_queue: deque[str],
    seen_articles: set[str],
    article_probe_queue: deque[str],
    rows: list[dict[str, object]],
) -> None:
    """Merge article-probe discoveries into the shared queues."""
    article_url = str(result["article_url"])
    status = result["status"]
    for topic_url in result["topic_urls"]:
        if topic_url not in seen_topics:
            seen_topics.add(topic_url)
            topic_queue.append(topic_url)
    for related_url in result["article_urls"]:
        if related_url not in seen_articles:
            seen_articles.add(related_url)
            article_probe_queue.append(related_url)
            rows.append(url_row(related_url, article_url, article_url, 1, status, "mvs_related"))


def discover_listing_chain(
    listing_url: str,
    *,
    seed_url: str,
    listing_kind: str,
    max_pages: int,
    seen_listings: set[str],
    seen_articles: set[str],
    article_probe_queue: deque[str],
    topic_queue: deque[str],
    rows: list[dict[str, object]],
    timeout: float,
    pause_seconds: float,
    fetch_profile: str,
    max_urls: int | None,
) -> None:
    """Follow one section/topic listing until its next link stops."""
    current_url: str | None = listing_url
    page_number = 0
    while current_url and page_number < max_pages:
        if current_url in seen_listings:
            break
        seen_listings.add(current_url)
        page_number += 1
        print(f"  {listing_kind}: page {page_number} {current_url}", flush=True)
        response = fetch_mvs(current_url, timeout, profile=fetch_profile)
        status = response["status"]
        if not isinstance(status, int) or not 200 <= status < 300:
            rows.append(error_row(seed_url, current_url, status, fallback_error(response.get("error"), f"http_status_{status}")))
            break

        parsed = parse_page(safe_text(response.get("text")), current_url)
        new_count = 0
        for article_url in parsed["article_urls"]:
            if article_url in seen_articles:
                continue
            seen_articles.add(article_url)
            article_probe_queue.append(article_url)
            rows.append(url_row(article_url, seed_url, current_url, page_number, status, listing_kind))
            new_count += 1
            if max_urls is not None and len(seen_articles) >= max_urls:
                print(f"    hit max_urls={max_urls}", flush=True)
                return
        for topic_url in parsed["topic_urls"]:
            if topic_url not in seen_listings and topic_url not in topic_queue:
                topic_queue.append(topic_url)
        print(
            f"    articles={len(parsed['article_urls']):,}, new={new_count:,}, total={len(seen_articles):,}",
            flush=True,
        )
        current_url = parsed["next_url"]
        if pause_seconds:
            time.sleep(pause_seconds)


def parse_page(html: str, page_url: str) -> dict[str, object]:
    """Return article, topic, and next links from an MVS page."""
    soup = parse_html(html)
    article_urls: list[str] = []
    topic_urls: list[str] = []
    next_url: str | None = None
    for link in soup.find_all("a", href=True):
        href = canonical_url(link.get("href"), page_url)
        parsed = urlparse(href)
        if normalized_host(parsed.netloc) != "mvsnoticias.com":
            continue
        clean = strip_fragment(href)
        if ARTICLE_RE.search(parsed.path):
            article_urls.append(clean)
        elif TOPIC_RE.match(parsed.path):
            topic_urls.append(clean.rstrip("/"))
        if is_next_link(link, parsed):
            next_url = clean
    return {
        "article_urls": dedupe(article_urls),
        "topic_urls": dedupe(topic_urls),
        "next_url": next_url,
    }


def fetch_mvs(url: str, timeout: float, *, profile: str) -> dict[str, object]:
    """Fetch MVS with requests, bypassing Windows Schannel curl failures."""
    try:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        result = request_mvs(url, timeout, profile=profile, verify=False)
    except requests.RequestException as exc:
        return {
            "status": pd.NA,
            "final_url": pd.NA,
            "content_type": pd.NA,
            "text": "",
            "error": f"requests_mvs: {exc}",
        }
    return {
        "status": result.status_code,
        "final_url": result.url,
        "content_type": result.headers.get("content-type", pd.NA),
        "text": result.text,
        "error": pd.NA,
    }


def request_mvs(url: str, timeout: float, *, profile: str, verify: bool) -> requests.Response:
    """Fetch an MVS page through requests."""
    return requests.get(
        url,
        headers=BROWSER_HEADERS if profile == "browser" else None,
        timeout=timeout,
        allow_redirects=True,
        verify=verify,
    )


def is_next_link(link, parsed_url) -> bool:
    """Return True when an anchor is the listing paginator's next link."""
    if not PAGE_RE.search(parsed_url.path):
        return False
    rel = " ".join(link.get("rel") or []).lower()
    text = link.get_text(" ", strip=True).lower()
    aria = str(link.get("aria-label") or "").lower()
    return "next" in rel or "siguiente" in text or "más" in text or "mas" in text or "next" in aria


def url_row(
    article_url: str,
    category_url: str,
    listing_url: str,
    page_number: int,
    status: object,
    strategy: str,
) -> dict[str, object]:
    """Return an article discovery row compatible with category extraction."""
    return {
        "source_id": SOURCE_ID,
        "source_name": SOURCE_NAME,
        "source_url": BASE_URL.rstrip("/"),
        "url": article_url,
        "canonical_url": article_url,
        "date_published": date_from_article_url(article_url),
        "lastmod": pd.NA,
        "topic": topic_from_url(category_url),
        "discovery_strategy": strategy,
        "category_url": category_url,
        "listing_url": listing_url,
        "listing_page": page_number,
        "status": status,
        "error": pd.NA,
        "discovered_at": pd.Timestamp.utcnow().isoformat(),
    }


def error_row(category_url: object, listing_url: object, status: object, error: object) -> dict[str, object]:
    """Return a discovery error row."""
    return {
        "source_id": SOURCE_ID,
        "source_name": SOURCE_NAME,
        "source_url": BASE_URL.rstrip("/"),
        "url": pd.NA,
        "canonical_url": pd.NA,
        "date_published": pd.NA,
        "lastmod": pd.NA,
        "topic": pd.NA,
        "discovery_strategy": "mvs_topic_graph",
        "category_url": category_url,
        "listing_url": listing_url,
        "listing_page": pd.NA,
        "status": status,
        "error": error,
        "discovered_at": pd.Timestamp.utcnow().isoformat(),
    }


def build_mvs_report(discovered: pd.DataFrame) -> str:
    """Create a compact report for MVS discovery."""
    lines = [
        "# MVS Discovery Report",
        "",
        f"- Rows: {len(discovered):,}",
        f"- URLs: {discovered['url'].notna().sum() if 'url' in discovered else 0:,}",
        f"- Errors: {discovered['error'].notna().sum() if 'error' in discovered else 0:,}",
        "",
    ]
    if not discovered.empty:
        summary = (
            discovered.groupby("discovery_strategy", dropna=False)
            .agg(
                rows=("source_id", "size"),
                urls=("url", lambda value: value.notna().sum()),
                categories=("category_url", lambda value: value.dropna().nunique()),
                min_date=("date_published", "min"),
                max_date=("date_published", "max"),
            )
            .reset_index()
            .sort_values(["urls", "rows"], ascending=False)
        )
        lines.extend(["## By Discovery Strategy", "", markdown_table(summary), ""])
    return "\n".join(lines)


def write_mvs_outputs(discovered: pd.DataFrame, report: str, discovery_dir, reports_dir) -> MvsDiscoveryOutputs:
    """Write MVS discovery outputs."""
    discovery_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    csv_path = discovery_dir / "discovered_urls_mvsnoticias.csv"
    parquet_path = discovery_dir / "discovered_urls_mvsnoticias.parquet"
    report_path = reports_dir / "mvsnoticias_discovery_report.md"
    discovered.to_csv(csv_path, index=False, encoding="utf-8")
    parquet_error = None
    try:
        discovered.to_parquet(parquet_path, index=False)
    except ImportError as exc:
        parquet_error = str(exc).splitlines()[0]
        parquet_path = None
    report_path.write_text(report, encoding="utf-8")
    return MvsDiscoveryOutputs(csv_path, parquet_path, report_path, parquet_error)


def parse_html(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except FeatureNotFound:
        return BeautifulSoup(html, "html.parser")


def safe_text(value: object) -> str:
    if is_missing(value):
        return ""
    return str(value)


def fallback_error(value: object, fallback: str) -> object:
    if is_missing(value) or str(value).strip() == "":
        return fallback
    return value


def is_missing(value: object) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return value is None


def canonical_url(value: object, base_url: str = BASE_URL) -> str:
    return strip_fragment(urljoin(base_url, safe_text(value).strip()))


def strip_fragment(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, ""))


def normalized_host(host: str) -> str:
    host = host.lower()
    return host[4:] if host.startswith("www.") else host


def date_from_article_url(url: str) -> object:
    match = re.search(r"/(\d{4})/(\d{1,2})/(\d{1,2})/", url)
    if not match:
        return pd.NA
    year, month, day = (int(part) for part in match.groups())
    return f"{year:04d}-{month:02d}-{day:02d}"


def topic_from_url(url: object) -> object:
    parsed = urlparse(str(url))
    segments = [segment for segment in parsed.path.strip("/").split("/") if segment]
    if not segments:
        return pd.NA
    if segments[0] == "temas":
        return segments[1].removesuffix(".html") if len(segments) > 1 else "temas"
    return segments[0]


def dedupe(values: list[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output

"""HTML article extraction for sitemap-discovered newspaper URLs."""

from __future__ import annotations

import json
import re
import time
import html as html_lib
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
from bs4 import BeautifulSoup, Comment, FeatureNotFound

from crawler_core.capabilities import fetch, markdown_table
from crawler_core.sitemaps import likely_article_url
from crawler_core.wordpress_articles import (
    is_parquet_path,
    normalize_articles_for_output,
    quote_sqlite_identifier,
    shorten_error,
    sqlite_value,
)


ARTICLE_KEY_COLUMNS = ["source_id", "url"]
HTML_BODY_TEXT_LIMIT = 12_000_000
ARTICLE_TYPES = {
    "article",
    "newsarticle",
    "reportagenewsarticle",
    "blogposting",
}
DATE_META_NAMES = (
    "article:published_time",
    "article:modified_time",
    "datePublished",
    "dateModified",
    "date",
    "pubdate",
    "publishdate",
    "publish_date",
    "dc.date",
    "dc.date.issued",
    "dcterms.created",
    "dcterms.modified",
    "og:updated_time",
    "parsely-pub-date",
    "sailthru.date",
    "date.published",
    "article.published",
    "pub_date",
    "publish-time",
)
TITLE_META_NAMES = ("og:title", "twitter:title", "title")
SUMMARY_META_NAMES = ("og:description", "twitter:description", "description")
AUTHOR_META_NAMES = ("author", "article:author", "dc.creator", "dcterms.creator")
NOISE_SELECTORS = (
    "script",
    "style",
    "noscript",
    "svg",
    "iframe",
    "form",
    "button",
    "nav",
    "header",
    "footer",
    "aside",
    ".advertisement",
    ".ads",
    ".ad",
    ".share",
    ".social",
    ".related",
    ".newsletter",
    ".comments",
    ".comment",
    ".menu",
    ".nav",
    ".navbar",
    ".site-header",
    ".site-footer",
    ".main-navigation",
    ".elementor-nav-menu",
    "[role='navigation']",
)
ARTICLE_SELECTORS = (
    "article",
    "main article",
    "[itemprop='articleBody']",
    "[property='articleBody']",
    ".article-body",
    ".article__body",
    ".entry-content",
    ".post-content",
    ".post__content",
    ".td-post-content",
    ".news-content",
    ".nota-contenido",
    ".contenido-nota",
    ".contenido",
    ".article-content",
    ".article__content",
    ".articleContent",
    ".article-text",
    ".articleText",
    ".nota",
    ".nota-body",
    ".notaBody",
    ".story-content",
    ".post-entry",
    ".entry__content",
    ".elementor-widget-theme-post-content .elementor-widget-container",
    ".elementor-widget-theme-post-content",
    ".single-post .entry-content",
    ".jeg_inner_content",
    ".tdb-block-inner",
    ".story-body",
    ".field-name-body",
    "#article-body",
    "#articleBody",
    "#content article",
    "main",
)
SPANISH_MONTHS = {
    "enero": "01",
    "febrero": "02",
    "marzo": "03",
    "abril": "04",
    "mayo": "05",
    "junio": "06",
    "julio": "07",
    "agosto": "08",
    "septiembre": "09",
    "setiembre": "09",
    "octubre": "10",
    "noviembre": "11",
    "diciembre": "12",
}
LAJORNADA_MAYA_SOURCE_IDS = {
    "lajornadamaya_campeche",
    "lajornadamaya_quintana_roo",
    "lajornadamaya_yucatan",
}
LAJORNADA_SECTION_SLUGS = {
    "arte-y-cultura",
    "cdmx",
    "deportes",
    "entretenimiento",
    "estados",
    "internacional",
    "mundial",
    "nacional",
    "opinion",
    "politica-y-gobierno",
    "region",
    "seguridad",
}
TIEMPO_SECTION_SLUGS = {
    "noticia",
    "local",
    "nacional",
    "opinion",
    "cronos",
    "economia",
    "espectaculos",
    "deportes",
    "cultura",
    "internacional",
    "tecnologia",
    "crealo",
}


@dataclass(frozen=True)
class SitemapArticleOutputs:
    """Paths written by sitemap article extraction."""

    articles_dir: Path
    report_path: Path
    parquet_error: str | None = None


def load_sitemap_discovery(path: Path) -> pd.DataFrame:
    """Load discovered sitemap URL rows from CSV or parquet."""
    if is_parquet_path(path):
        return pd.read_parquet(path)
    return pd.read_csv(path, low_memory=False)


def load_sitemap_article_statuses(db_path: Path) -> pd.DataFrame | None:
    """Load existing sitemap article keys and error status from SQLite."""
    if not db_path.exists():
        return None
    return load_sitemap_articles_from_sqlite(
        db_path,
        columns=["source_id", "url", "error", "main_text", "date_published", "date", "lastmod"],
    )


def prepare_sitemap_article_queue(
    discovered: pd.DataFrame,
    *,
    source_ids: list[str] | None = None,
    limit: int | None = None,
    existing_articles: pd.DataFrame | None = None,
    retry_errors: bool = False,
    refresh_missing_text: bool = False,
    refresh_missing_date: bool = False,
    refresh_date_after: str | None = None,
    refresh_all_existing: bool = False,
) -> pd.DataFrame:
    """Filter sitemap discovery rows to article extraction work items."""
    queue = discovered.copy()
    queue = queue[queue["url"].notna()].copy()
    if "error" in queue.columns:
        queue = queue[queue["error"].isna()].copy()
    queue = queue[queue.apply(lambda row: likely_article_url_for_source(row.get("source_id"), row.get("url")), axis=1)].copy()
    if source_ids:
        queue = queue[queue["source_id"].isin(source_ids)].copy()

    queue = queue.drop_duplicates(ARTICLE_KEY_COLUMNS, keep="last")
    if existing_articles is not None and not existing_articles.empty:
        existing = existing_articles.copy()
        existing = existing[existing["source_id"].notna() & existing["url"].notna()].copy()
        done_mask = pd.Series(True, index=existing.index)
        if "error" in existing.columns:
            error_present = existing["error"].notna() & existing["error"].astype(str).str.strip().ne("")
        else:
            error_present = pd.Series(False, index=existing.index)
        if retry_errors:
            done_mask &= ~error_present
        if refresh_missing_text and "main_text" in existing.columns:
            done_mask &= (~existing["main_text"].apply(is_blank_value)) | (error_present & ~retry_errors)
        if refresh_missing_date:
            done_mask &= existing.apply(row_has_any_date, axis=1) | (error_present & ~retry_errors)
        if refresh_date_after:
            future_date = existing.apply(lambda row: row_date_after(row, refresh_date_after), axis=1)
            done_mask &= ~future_date | (error_present & ~retry_errors)
        if refresh_all_existing:
            done_mask = pd.Series(False, index=existing.index)
        existing = existing[done_mask].copy()
        done = existing[ARTICLE_KEY_COLUMNS].drop_duplicates()
        done["_already_done"] = True
        queue = queue.merge(done, on=ARTICLE_KEY_COLUMNS, how="left")
        queue = queue[queue["_already_done"].isna()].drop(columns=["_already_done"]).copy()

    sort_columns = [column for column in ["source_id", "lastmod", "url"] if column in queue.columns]
    if sort_columns:
        queue = queue.sort_values(sort_columns, ascending=[True] + [False] * (len(sort_columns) - 1))
    if limit is not None:
        queue = queue.head(limit)
    return queue.reset_index(drop=True)


def extract_sitemap_articles(
    queue: pd.DataFrame,
    *,
    state_db_path: Path,
    checkpoint_every: int = 100,
    timeout: float = 30.0,
    pause_seconds: float = 0.1,
    progress_every: int = 100,
    progress_seconds: float = 60.0,
    workers: int = 1,
    row_log: bool = False,
    keep_rows: bool = False,
    fetch_profile: str = "default",
) -> pd.DataFrame:
    """Extract article text from sitemap URL rows and save progress to SQLite."""
    rows: list[dict[str, object]] = []
    total = len(queue)
    workers = max(1, int(workers or 1))
    started_at = time.monotonic()
    last_progress_at = 0.0
    processed_since_checkpoint = 0
    pending_rows: list[dict[str, object]] = []
    processed = 0
    errors = 0
    blank_text = 0
    sample_error = pd.NA

    print(f"Starting sitemap HTML extraction: {total:,} queued rows | workers={workers:,}")
    try:
        if workers == 1:
            for _, item in queue.iterrows():
                row = safe_extract_one_sitemap_article(
                    item,
                    timeout=timeout,
                    row_log=row_log,
                    fetch_profile=fetch_profile,
                )
                processed += 1
                (
                    rows,
                    pending_rows,
                    processed_since_checkpoint,
                    errors,
                    blank_text,
                    sample_error,
                    last_progress_at,
                ) = update_progress_and_checkpoint(
                    rows=rows,
                    pending_rows=pending_rows,
                    chunk_rows=[row],
                    keep_rows=keep_rows,
                    processed_since_checkpoint=processed_since_checkpoint,
                    processed=processed,
                    total=total,
                    errors=errors,
                    blank_text=blank_text,
                    sample_error=sample_error,
                    started_at=started_at,
                    last_progress_at=last_progress_at,
                    progress_every=progress_every,
                    progress_seconds=progress_seconds,
                    checkpoint_every=checkpoint_every,
                    state_db_path=state_db_path,
                )
                if pause_seconds:
                    time.sleep(pause_seconds)
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                iterator = iter(queue.iterrows())
                futures = set()

                def submit_next() -> bool:
                    try:
                        _, item = next(iterator)
                    except StopIteration:
                        return False
                    futures.add(
                        executor.submit(
                            safe_extract_one_sitemap_article,
                            item,
                            timeout=timeout,
                            row_log=row_log,
                            fetch_profile=fetch_profile,
                        )
                    )
                    return True

                for _ in range(workers * 4):
                    if not submit_next():
                        break

                while futures:
                    done, futures = wait(futures, return_when=FIRST_COMPLETED)
                    for future in done:
                        row = future.result()
                        processed += 1
                        (
                            rows,
                            pending_rows,
                            processed_since_checkpoint,
                            errors,
                            blank_text,
                            sample_error,
                            last_progress_at,
                        ) = update_progress_and_checkpoint(
                            rows=rows,
                            pending_rows=pending_rows,
                            chunk_rows=[row],
                            keep_rows=keep_rows,
                            processed_since_checkpoint=processed_since_checkpoint,
                            processed=processed,
                            total=total,
                            errors=errors,
                            blank_text=blank_text,
                            sample_error=sample_error,
                            started_at=started_at,
                            last_progress_at=last_progress_at,
                            progress_every=progress_every,
                            progress_seconds=progress_seconds,
                            checkpoint_every=checkpoint_every,
                            state_db_path=state_db_path,
                        )
                        submit_next()
    except KeyboardInterrupt:
        print("Interrupted by user; progress already saved to SQLite.")

    if pending_rows:
        save_sitemap_articles_to_sqlite(pd.DataFrame(pending_rows), state_db_path)
    articles = pd.DataFrame(rows)
    if not articles.empty:
        articles = articles.drop_duplicates(ARTICLE_KEY_COLUMNS, keep="last").reset_index(drop=True)
    return articles


def update_progress_and_checkpoint(
    *,
    rows: list[dict[str, object]],
    pending_rows: list[dict[str, object]],
    chunk_rows: list[dict[str, object]],
    keep_rows: bool,
    processed_since_checkpoint: int,
    processed: int,
    total: int,
    errors: int,
    blank_text: int,
    sample_error: object,
    started_at: float,
    last_progress_at: float,
    progress_every: int,
    progress_seconds: float,
    checkpoint_every: int,
    state_db_path: Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]], int, int, int, object, float]:
    """Save progress, update counters, and print compact terminal status."""
    if keep_rows:
        rows.extend(chunk_rows)
    pending_rows.extend(chunk_rows)
    processed_since_checkpoint += len(chunk_rows)

    for row in chunk_rows:
        if pd.notna(row.get("error")):
            errors += 1
            if pd.isna(sample_error):
                sample_error = row.get("error")
        elif is_blank_value(row.get("main_text")):
            blank_text += 1

    if processed_since_checkpoint >= checkpoint_every:
        save_sitemap_articles_to_sqlite(pd.DataFrame(pending_rows), state_db_path)
        pending_rows.clear()
        processed_since_checkpoint = 0

    now = time.monotonic()
    should_print_count = bool(progress_every and (processed % progress_every == 0 or processed == total))
    should_print_time = bool(progress_seconds and now - last_progress_at >= progress_seconds)
    if should_print_count or should_print_time:
        print_progress(processed, total, started_at, errors, blank_text, sample_error)
        last_progress_at = now
    return rows, pending_rows, processed_since_checkpoint, errors, blank_text, sample_error, last_progress_at


def extract_one_sitemap_article(
    item: pd.Series,
    *,
    timeout: float,
    row_log: bool = False,
    fetch_profile: str = "default",
) -> dict[str, object]:
    """Fetch and extract one article page from HTML."""
    url = str(item["url"])
    source_id = item.get("source_id")
    if row_log:
        print(f"{source_id} {url}")

    response = fetch(url, timeout, body_text_limit=HTML_BODY_TEXT_LIMIT, profile=fetch_profile)
    row = base_sitemap_article_row(item)
    row["status"] = response["status"]
    row["final_url"] = response["final_url"]
    row["content_type"] = response["content_type"]

    status = response["status"]
    if not isinstance(status, int) or status < 200 or status >= 300:
        error = response["error"]
        if pd.isna(error):
            error = f"http_status_{status}"
        row["error"] = error
        return row

    text = response["text"] or ""
    if not text.strip():
        row["error"] = "empty_response_body"
        return row

    try:
        fields = article_fields_from_html(text, url=url, source_id=source_id)
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
        return row

    if source_id == "diariopresente_tabasco_elsoldelsureste" and is_blank_value(
        first_present(fields.get("date_published"), fields.get("date"))
    ):
        amp_fields = fetch_diariopresente_amp_fields(url, timeout)
        for key, value in amp_fields.items():
            if is_blank_value(fields.get(key)):
                fields[key] = value

    row.update(fields)
    if pd.isna(row.get("date_published")) and pd.notna(item.get("lastmod")):
        row["date_published"] = item.get("lastmod")
    if is_blank_value(row.get("date")):
        row["date"] = first_present(row.get("date_published"), row.get("date_modified"), row.get("lastmod"))
    if is_blank_value(row.get("main_text")) or is_low_quality_source_text(source_id, row.get("main_text")):
        row["error"] = "missing_main_text"
    elif is_blank_value(first_present(row.get("date_published"), row.get("date"), row.get("lastmod"))):
        row["error"] = "missing_date"
    else:
        row["error"] = pd.NA
    return row


def safe_extract_one_sitemap_article(
    item: pd.Series,
    *,
    timeout: float,
    row_log: bool = False,
    fetch_profile: str = "default",
) -> dict[str, object]:
    """Extract one article and convert unexpected failures into error rows."""
    try:
        return extract_one_sitemap_article(
            item,
            timeout=timeout,
            row_log=row_log,
            fetch_profile=fetch_profile,
        )
    except Exception as exc:
        row = base_sitemap_article_row(item)
        row["error"] = f"{type(exc).__name__}: {exc}"
        return row


def base_sitemap_article_row(item: pd.Series) -> dict[str, object]:
    """Base article row populated from sitemap discovery metadata."""
    return {
        "source_id": item.get("source_id"),
        "source_name": item.get("source_name"),
        "source_url": item.get("source_url"),
        "url": item.get("url"),
        "canonical_url": item.get("canonical_url", item.get("url")),
        "original_url": item.get("original_url"),
        "wayback_url": item.get("wayback_url"),
        "wayback_timestamp": item.get("wayback_timestamp"),
        "wayback_mimetype": item.get("wayback_mimetype"),
        "wayback_statuscode": item.get("wayback_statuscode"),
        "wayback_digest": item.get("wayback_digest"),
        "wayback_length": item.get("wayback_length"),
        "final_url": pd.NA,
        "title": pd.NA,
        "summary": pd.NA,
        "main_text": pd.NA,
        "authors": pd.NA,
        "date": item.get("lastmod"),
        "date_published": pd.NA,
        "date_modified": item.get("lastmod"),
        "lastmod": item.get("lastmod"),
        "topic": item.get("topic"),
        "section": item.get("topic"),
        "language": pd.NA,
        "discovery_strategy": item.get("discovery_strategy", "sitemap"),
        "extractor_strategy": "sitemap_html",
        "sitemap_url": item.get("sitemap_url"),
        "scrape_timestamp": pd.Timestamp.utcnow().isoformat(),
        "status": pd.NA,
        "content_type": pd.NA,
        "error": pd.NA,
    }


def article_fields_from_html(html: str, *, url: str, source_id: object = pd.NA) -> dict[str, object]:
    """Extract article fields from an HTML page."""
    soup = parse_html(html)
    json_items = extract_json_ld_items(soup)
    raw_visible_text = soup.get_text("\n", strip=True)
    for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()
    for selector in NOISE_SELECTORS:
        for node in soup.select(selector):
            node.decompose()

    article_json = first_article_json(json_items)
    title = first_present(
        value_from_json(article_json, "headline"),
        first_meta_content(soup, TITLE_META_NAMES),
        text_or_na(soup.find("h1")),
        clean_title(text_or_na(soup.find("title")), url),
    )
    summary = first_present(
        value_from_json(article_json, "description"),
        first_meta_content(soup, SUMMARY_META_NAMES),
    )
    date_published = first_present(
        value_from_json(article_json, "datePublished"),
        first_meta_content(soup, DATE_META_NAMES),
        first_time_datetime(soup),
        date_from_source_patterns(source_id, url, title, raw_visible_text),
    )
    date_modified = first_present(
        value_from_json(article_json, "dateModified"),
        first_meta_content(soup, ("article:modified_time", "dateModified", "og:updated_time")),
    )
    authors = first_present(authors_from_json(article_json), first_meta_content(soup, AUTHOR_META_NAMES))
    canonical_url = first_present(canonical_from_html(soup), url)
    json_body = clean_article_body(value_from_json(article_json, "articleBody"))
    visible_byline_body = text_from_visible_byline(source_id, raw_visible_text, title)
    if str(source_id) == "tiempo":
        main_text = first_present(
            visible_byline_body,
            json_body,
            source_specific_main_text(soup, source_id),
            extract_main_text(soup),
        )
    else:
        main_text = first_present(
            json_body,
            visible_byline_body,
            source_specific_main_text(soup, source_id),
            extract_main_text(soup),
        )
    language = soup.html.get("lang") if soup.html and soup.html.get("lang") else pd.NA

    return {
        "canonical_url": canonical_url,
        "title": title,
        "summary": summary,
        "main_text": main_text,
        "authors": authors,
        "date": first_present(date_published, date_modified),
        "date_published": date_published,
        "date_modified": date_modified,
        "language": language,
    }


def parse_html(html: str) -> BeautifulSoup:
    """Parse HTML with lxml when available, otherwise use the built-in parser."""
    try:
        return BeautifulSoup(html, "lxml")
    except FeatureNotFound:
        return BeautifulSoup(html, "html.parser")


def first_present(*values: object) -> object:
    """Return the first non-empty scalar without evaluating pandas NA as bool."""
    for value in values:
        try:
            if pd.isna(value):
                continue
        except (TypeError, ValueError):
            pass
        if isinstance(value, str) and not value.strip():
            continue
        if value is not None:
            return value
    return pd.NA


def is_blank_value(value: object) -> bool:
    """Return True for None, pandas NA, or whitespace-only text."""
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip() == ""


def row_has_any_date(row: pd.Series) -> bool:
    """Return True if an existing SQLite status row has any date value."""
    return not is_blank_value(first_present(row.get("date_published"), row.get("date"), row.get("lastmod")))


def row_date_after(row: pd.Series, cutoff: str) -> bool:
    """Return True if an existing row's best date parses after the cutoff date."""
    value = first_present(row.get("date_published"), row.get("date"), row.get("lastmod"))
    if is_blank_value(value):
        return False
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    parsed_cutoff = pd.to_datetime(cutoff, errors="coerce", utc=True)
    if pd.isna(parsed) or pd.isna(parsed_cutoff):
        return False
    return parsed > parsed_cutoff


def likely_article_url_for_source(source_id: object, url: object) -> bool:
    """Apply generic and source-specific sitemap article URL filters."""
    if pd.isna(url):
        return False
    source_text = str(source_id)
    segments = path_segments(url)

    if source_text in LAJORNADA_MAYA_SOURCE_IDS:
        return likely_article_url(url) and len(segments) >= 3 and segments[1].isdigit()
    if source_text == "lajornadaestadodemexico":
        return len(segments) == 1 and segments[0] not in LAJORNADA_SECTION_SLUGS
    if source_text == "noroeste":
        return len(segments) >= 3 or not is_blank_value(date_from_url_path(str(url)))
    if source_text == "elbravo":
        return len(segments) == 1 and not any(segment.startswith(("tag", "category", "author")) for segment in segments)
    if source_text == "tiempo":
        return len(segments) >= 2 and segments[0] in TIEMPO_SECTION_SLUGS
    if source_text == "cuartopoder" and segments and segments[0] in {"videos", "fotogalerias"}:
        return False
    if not likely_article_url(url):
        return False
    return True


def path_segments(url: object) -> list[str]:
    """Return URL path segments without empty parts."""
    if pd.isna(url):
        return []
    return [segment for segment in urlparse(str(url)).path.strip("/").split("/") if segment]


def clean_article_body(value: object) -> object:
    """Normalize JSON-LD articleBody text."""
    value = clean_scalar(value)
    if is_blank_value(value):
        return pd.NA
    text = html_lib.unescape(str(value))
    if re.search(r"</?[a-z][^>]*>", text, flags=re.I):
        text = parse_html(text).get_text("\n", strip=True)
    return dedupe_lines(text)


def fetch_diariopresente_amp_fields(url: str, timeout: float) -> dict[str, object]:
    """Fetch Diario Presente AMP pages, which expose publication dates more reliably."""
    amp_url = diariopresente_amp_url(url)
    if not amp_url or amp_url == url:
        return {}
    response = fetch(amp_url, timeout, body_text_limit=HTML_BODY_TEXT_LIMIT)
    status = response["status"]
    if not isinstance(status, int) or status < 200 or status >= 300 or not response["text"]:
        return {}
    return article_fields_from_html(response["text"], url=amp_url, source_id="diariopresente_tabasco_elsoldelsureste")


def diariopresente_amp_url(url: str) -> str | None:
    """Build Diario Presente AMP URL from a canonical article URL."""
    parsed = urlparse(url)
    segments = [segment for segment in parsed.path.strip("/").split("/") if segment]
    if not segments or segments[0] == "amp":
        return url
    return f"{parsed.scheme}://{parsed.netloc}/amp/{'/'.join(segments)}"


def date_from_source_patterns(
    source_id: object,
    url: str,
    title: object,
    visible_text: str,
) -> object:
    """Extract dates from source-specific visible text, URL paths, or titles."""
    source_text = str(source_id)
    if source_text == "meganoticias":
        value = first_regex_date(
            visible_text,
            (
                r"Fecha:\s*(\d{1,2})[-/](\d{1,2})[-/](20\d{2})",
                r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b",
            ),
        )
        if not is_blank_value(value):
            return value
    if source_text == "diariopresente_tabasco_elsoldelsureste":
        value = first_regex_date(
            visible_text,
            (
                r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\s*[-–—]",
                r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b",
            ),
        )
        if not is_blank_value(value):
            return value
    if source_text == "eldiariodesonora":
        value = first_regex_date(
            visible_text,
            (
                r"\bel\s+(\d{1,2})/(\d{1,2})/(20\d{2})",
                r"\beditada\s+el\s+(\d{1,2})/(\d{1,2})/(20\d{2})",
            ),
        )
        if not is_blank_value(value):
            return value
    if source_text == "tiempo":
        value = tiempo_byline_date(visible_text)
        if not is_blank_value(value):
            return value
    if source_text == "cuartopoder":
        value = cuartopoder_byline_date(visible_text)
        if not is_blank_value(value):
            return value
        return pd.NA

    value = date_from_url_path(url)
    if not is_blank_value(value):
        return value
    return first_present(first_spanish_text_date(title), first_spanish_text_date(visible_text))


def first_regex_date(text: str, patterns: tuple[str, ...]) -> object:
    """Return the first dd/mm/yyyy or dd-mm-yyyy match as ISO date text."""
    for pattern in patterns:
        match = re.search(pattern, text or "", flags=re.I)
        if match:
            day, month, year = match.groups()[:3]
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return pd.NA


def date_from_url_path(url: str) -> object:
    """Extract an ISO date from common dated URL paths."""
    path = urlparse(url).path
    match = re.search(r"/(20\d{2})/(\d{1,2})/(\d{1,2})(?:/|$)", path)
    if match:
        year, month, day = match.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    match = re.search(r"(20\d{2})[-_](\d{1,2})[-_](\d{1,2})", path)
    if match:
        year, month, day = match.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return pd.NA


def first_spanish_text_date(value: object) -> object:
    """Extract dates such as 'Agosto 12, 2026' or '10 de Agosto del 2026'."""
    if is_blank_value(value):
        return pd.NA
    text = str(value)
    month_names = "|".join(SPANISH_MONTHS)
    patterns = (
        rf"\b({month_names})\s+(\d{{1,2}}),\s*(20\d{{2}})\b",
        rf"\b({month_names})\s+(\d{{1,2}})\s+(?:de|del)?\s*(20\d{{2}})\b",
        rf"\b(\d{{1,2}})\s+de\s+({month_names})\s+(?:de|del)?\s*(20\d{{2}})\b",
        rf"\b(\d{{1,2}})\s+({month_names})\s+(20\d{{2}})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if not match:
            continue
        first, second, year = match.groups()
        if first.isdigit():
            day = first
            month = second
        else:
            month = first
            day = second
        month_number = SPANISH_MONTHS.get(month.lower())
        if month_number:
            return f"{int(year):04d}-{month_number}-{int(day):02d}"
    return pd.NA


def cuartopoder_byline_date(text: str) -> object:
    """Extract Cuarto Poder publication dates from visible byline/date rows."""
    month_names = "|".join(SPANISH_MONTHS)
    match = re.search(
        rf"\bPor:\s+.+?\s+({month_names})\s+(\d{{1,2}})\s+(?:de|del)?\s*(20\d{{2}})\b",
        text or "",
        flags=re.I,
    )
    if match:
        month, day, year = match.groups()
        return f"{int(year):04d}-{SPANISH_MONTHS[month.lower()]}-{int(day):02d}"

    for line in normalized_visible_lines(text)[:80]:
        match = re.search(
            rf"^({month_names})\s+(\d{{1,2}})\s+(?:de|del)?\s*(20\d{{2}})$",
            line,
            flags=re.I,
        )
        if match:
            month, day, year = match.groups()
            return f"{int(year):04d}-{SPANISH_MONTHS[month.lower()]}-{int(day):02d}"
    return pd.NA


def tiempo_byline_date(text: str) -> object:
    """Extract Tiempo dates from bylines such as 'Por: Redacción 18 Junio 2026 07:45'."""
    month_names = "|".join(SPANISH_MONTHS)
    match = re.search(
        rf"\bPor:\s+.+?\s+(\d{{1,2}})\s+({month_names})\s+(20\d{{2}})(?:\s+(\d{{1,2}}:\d{{2}}))?",
        text or "",
        flags=re.I,
    )
    if not match:
        return pd.NA
    day, month, year, hour = match.groups()
    date_text = f"{int(year):04d}-{SPANISH_MONTHS[month.lower()]}-{int(day):02d}"
    return f"{date_text} {hour}" if hour else date_text


def text_from_visible_byline(source_id: object, visible_text: str, title: object) -> object:
    """Extract article body from full visible text for sites with reliable byline anchors."""
    source_text = str(source_id)
    if source_text not in {"tiempo", "cuartopoder", "eldiariodesonora"}:
        return pd.NA
    lines = normalized_visible_lines(visible_text)
    if source_text == "tiempo":
        byline_index = first_tiempo_byline_index(lines)
    elif source_text == "cuartopoder":
        byline_index = first_cuartopoder_byline_index(lines)
    else:
        byline_index = first_eldiariodesonora_byline_index(lines)
    if byline_index is None:
        return pd.NA
    start_index = byline_index + 1
    if source_text == "eldiariodesonora":
        while start_index < len(lines) and is_eldiariodesonora_metadata_line(lines[start_index]):
            start_index += 1
    body_lines = trim_source_body_lines(lines[start_index:], source_text)
    body_lines = remove_repeated_heading_lines(body_lines, title)
    text = "\n".join(body_lines)
    if len(text.strip()) < 80:
        return pd.NA
    return dedupe_lines(text)


def normalized_visible_lines(text: str) -> list[str]:
    """Return normalized non-empty visible text lines."""
    lines = []
    for raw_line in (text or "").splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if line:
            lines.append(line)
    return lines


def first_tiempo_byline_index(lines: list[str]) -> int | None:
    """Return the first line index that looks like a Tiempo byline/date."""
    month_names = "|".join(SPANISH_MONTHS)
    pattern = re.compile(
        rf"\bPor:\s+.+?\s+\d{{1,2}}\s+(?:{month_names})\s+20\d{{2}}(?:\s+\d{{1,2}}:\d{{2}})?",
        flags=re.I,
    )
    for index, line in enumerate(lines):
        if pattern.search(line):
            return index
    return None


def first_cuartopoder_byline_index(lines: list[str]) -> int | None:
    """Return the first line index that looks like a Cuarto Poder byline/date."""
    month_names = "|".join(SPANISH_MONTHS)
    byline_pattern = re.compile(
        rf"\bPor:\s+.+?\s+(?:{month_names})\s+\d{{1,2}}\s+(?:de|del)?\s*20\d{{2}}\b",
        flags=re.I,
    )
    date_line_pattern = re.compile(
        rf"^(?:{month_names})\s+\d{{1,2}}\s+(?:de|del)?\s*20\d{{2}}$",
        flags=re.I,
    )
    for index, line in enumerate(lines):
        if byline_pattern.search(line) or date_line_pattern.search(line):
            return index
    return None


def first_eldiariodesonora_byline_index(lines: list[str]) -> int | None:
    """Return the line index for El Diario de Sonora's author/publication row."""
    one_line_pattern = re.compile(
        r"^Autor\b.+\bel\s+\d{1,2}/\d{1,2}/20\d{2}\s+\d{1,2}:\d{2}\s*(?:AM|PM)\.?$",
        flags=re.I,
    )
    split_date_pattern = re.compile(
        r"^el\s+\d{1,2}/\d{1,2}/20\d{2}\s+\d{1,2}:\d{2}\s*(?:AM|PM)\.?$",
        flags=re.I,
    )
    for index, line in enumerate(lines):
        if one_line_pattern.search(line):
            return index
        if split_date_pattern.search(line) and any(
            "diario de sonora" in previous.lower() or previous.lower() == "autor"
            for previous in lines[max(0, index - 4) : index]
        ):
            return index
    return None


def is_eldiariodesonora_metadata_line(line: str) -> bool:
    """Return True for category/edit metadata between Diario de Sonora byline and body."""
    lowered = line.lower().strip()
    if lowered in {
        "en",
        "y",
        "nogales",
        "sonora",
        "méxico",
        "mexico",
        "arizona",
        "internacional",
        "deportes",
        "espectáculos",
        "espectaculos",
        "columna",
        "ciencia y tecnología",
        "ciencia y tecnologia",
    }:
        return True
    return bool(re.search(r"\beditada\s+el\s+\d{1,2}/\d{1,2}/20\d{2}", line, flags=re.I))


def trim_source_body_lines(lines: list[str], source_id: str) -> list[str]:
    """Trim common footer/share text from source-specific visible-text extraction."""
    stop_patterns = (
        r"^Síguenos\b",
        r"^También te puede interesar\b",
        r"^Notas relacionadas\b",
        r"^Comentarios\b",
        r"^Compartir\b",
        r"^Deja tu comentario$",
        r"^Comparte esta noticia$",
        r"^Más Noticias$",
        r"^Acerca de el Diario de Sonora$",
        r"^EDICIÓN IMPRESA$",
        r"^Fotos y Videos$",
        r"^Facebook$",
        r"^Twitter$",
        r"^Whatsapp$",
    )
    kept = []
    for line in lines:
        if any(re.search(pattern, line, flags=re.I) for pattern in stop_patterns):
            break
        if source_id == "cuartopoder" and re.match(r"^Foto:", line, flags=re.I):
            continue
        if line.lower() in {"image", "video", "publicidad"}:
            continue
        kept.append(line)
    return kept


def remove_repeated_heading_lines(lines: list[str], title: object) -> list[str]:
    """Remove repeated title lines from source-specific body candidates."""
    if is_blank_value(title):
        return lines
    normalized_title = normalize_compare_text(str(title))
    return [line for line in lines if normalize_compare_text(line) != normalized_title]


def normalize_compare_text(text: str) -> str:
    """Normalize text for simple title/body duplicate comparisons."""
    return re.sub(r"\W+", "", text.lower(), flags=re.UNICODE)


def source_specific_main_text(soup: BeautifulSoup, source_id: object) -> object:
    """Extract body text for sites whose markup needs a narrow selector."""
    selectors_by_source = {
        "eldiariodesonora": (
            ".newsfull__body",
            ".nota__contenido",
            ".article__body",
            ".content-body",
            ".entry-content",
            "[itemprop='articleBody']",
        ),
        "elbravo": (
            ".entry-content",
            ".post-content",
            ".elementor-widget-theme-post-content .elementor-widget-container",
            ".elementor-widget-theme-post-content",
        ),
        "meganoticias": (
            ".nota-texto",
            ".contenido-nota",
            ".article-body",
            ".news-content",
            "[itemprop='articleBody']",
        ),
        "diariopresente_tabasco_elsoldelsureste": (
            ".news-full-content",
            ".nota-contenido",
            ".contenido-nota",
            ".article-body",
            "[itemprop='articleBody']",
        ),
        "tiempo": (
            ".nota-contenido",
            ".contenido-nota",
            ".article-body",
            ".article-content",
            ".news-content",
            ".entry-content",
            "[itemprop='articleBody']",
        ),
    }
    candidates = []
    for selector in selectors_by_source.get(str(source_id), ()):
        for node in soup.select(selector):
            text = readable_text(node)
            if text and is_article_text_candidate(node, text):
                candidates.append((score_node(node, text), text))
    if not candidates:
        return pd.NA
    _, text = max(candidates, key=lambda item: item[0])
    return dedupe_lines(text)


def is_low_quality_source_text(source_id: object, value: object) -> bool:
    """Detect source-specific false positives such as menu-only article text."""
    if is_blank_value(value):
        return True
    text = str(value)
    if str(source_id) == "elbravo" and looks_like_elbravo_menu_text(text):
        return True
    if str(source_id) == "tiempo" and looks_like_tiempo_error_text(text):
        return True
    return False


def looks_like_elbravo_menu_text(text: str) -> bool:
    """Return True when El Bravo extraction captured the site menu instead of article text."""
    lowered = re.sub(r"\s+", " ", text.lower())
    menu_terms = (
        "local ciudad economía agrícola seguridad",
        "clasificados inmuebles empleos vehículos",
        "suplementos anuario bienestar",
    )
    return sum(term in lowered for term in menu_terms) >= 2


def looks_like_tiempo_error_text(text: str) -> bool:
    """Return True when Tiempo extraction captured the error/poll shell instead of an article."""
    lowered = re.sub(r"\s+", " ", text.lower()).strip()
    if "ocurrió un error al procesar la noticia" in lowered:
        return True
    if lowered.startswith("por:") and "¿" in lowered and ("votos:" in lowered or "no podría evaluarlo" in lowered):
        return True
    poll_markers = (
        "¿qué opinas de una posible alianza",
        "fortalecería al pan",
        "ambos partidos se necesitan",
        "¿cómo festejarás el grito de independencia",
        "¿crees que los niños y jóvenes de hoy comprenden bien",
    )
    return sum(marker in lowered for marker in poll_markers) >= 2


def extract_json_ld_items(soup: BeautifulSoup) -> list[dict[str, object]]:
    """Return flattened JSON-LD dict objects."""
    items: list[dict[str, object]] = []
    for script in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
        raw = script.string or script.get_text(" ", strip=True)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items.extend(flatten_json_ld(payload))
    return items


def flatten_json_ld(value: object) -> list[dict[str, object]]:
    """Flatten JSON-LD objects, lists, and @graph containers."""
    if isinstance(value, list):
        rows: list[dict[str, object]] = []
        for item in value:
            rows.extend(flatten_json_ld(item))
        return rows
    if not isinstance(value, dict):
        return []
    rows = [value]
    graph = value.get("@graph")
    if isinstance(graph, list):
        rows.extend(flatten_json_ld(graph))
    return rows


def first_article_json(items: list[dict[str, object]]) -> dict[str, object]:
    """Pick the first JSON-LD item that looks like an article."""
    for item in items:
        raw_type = item.get("@type", "")
        types = raw_type if isinstance(raw_type, list) else [raw_type]
        normalized = {str(value).lower() for value in types}
        if normalized & ARTICLE_TYPES:
            return item
    return items[0] if items else {}


def value_from_json(item: dict[str, object], key: str) -> object:
    """Return a scalar JSON-LD value."""
    value = item.get(key)
    if isinstance(value, list):
        value = first_present(*value)
    if isinstance(value, dict):
        value = first_present(value.get("name"), value.get("@id"))
    return clean_scalar(value)


def authors_from_json(item: dict[str, object]) -> object:
    """Extract author names from JSON-LD."""
    authors = item.get("author")
    if is_blank_value(authors):
        return pd.NA
    if isinstance(authors, dict):
        authors = [authors]
    if not isinstance(authors, list):
        return clean_scalar(authors)
    names = []
    for author in authors:
        if isinstance(author, dict):
            name = clean_scalar(author.get("name"))
        else:
            name = clean_scalar(author)
        if pd.notna(name):
            names.append(str(name))
    return "; ".join(names) if names else pd.NA


def first_meta_content(soup: BeautifulSoup, names: tuple[str, ...]) -> object:
    """Return the first matching meta content value."""
    lowered_names = {name.lower() for name in names}
    for meta in soup.find_all("meta"):
        name = (meta.get("name") or meta.get("property") or meta.get("itemprop") or "").lower()
        if name in lowered_names and meta.get("content"):
            return clean_scalar(meta.get("content"))
    return pd.NA


def first_time_datetime(soup: BeautifulSoup) -> object:
    """Return the first machine-readable time value."""
    for node in soup.find_all("time"):
        value = node.get("datetime") or node.get("content") or node.get_text(" ", strip=True)
        if value:
            return clean_scalar(value)
    return pd.NA


def canonical_from_html(soup: BeautifulSoup) -> object:
    """Return canonical URL from HTML if present."""
    link = soup.find("link", attrs={"rel": lambda value: value and "canonical" in value})
    if link and link.get("href"):
        return clean_scalar(link.get("href"))
    meta = soup.find("meta", attrs={"property": "og:url"})
    if meta and meta.get("content"):
        return clean_scalar(meta.get("content"))
    return pd.NA


def extract_main_text(soup: BeautifulSoup) -> object:
    """Extract readable article text using selectors plus paragraph-density fallback."""
    candidates = []
    for selector in ARTICLE_SELECTORS:
        for node in soup.select(selector):
            text = readable_text(node)
            if text and is_article_text_candidate(node, text):
                candidates.append((score_node(node, text), text))
    if not candidates and soup.body:
        body_text = readable_text(soup.body)
        if body_text and is_article_text_candidate(soup.body, body_text):
            candidates.append((score_node(soup.body, body_text), body_text))
    if not candidates:
        return pd.NA
    _, text = max(candidates, key=lambda item: item[0])
    return dedupe_lines(text)


def readable_text(node) -> str:
    """Return paragraph-oriented text for a BeautifulSoup node."""
    paragraphs = []
    for child in node.find_all(["p", "li", "blockquote", "h2", "h3"]):
        text = child.get_text(" ", strip=True)
        if len(text) >= 25:
            paragraphs.append(text)
    if len(paragraphs) >= 2:
        return "\n".join(paragraphs)
    return node.get_text("\n", strip=True)


def is_article_text_candidate(node, text: str) -> bool:
    """Reject obvious navigation/listing candidates before scoring."""
    clean_text = re.sub(r"\s+", " ", text or "").strip()
    if len(clean_text) < 80:
        return False
    paragraphs = len(node.find_all("p"))
    links = node.find_all("a")
    links_text = " ".join(link.get_text(" ", strip=True) for link in links)
    link_density = len(links_text) / max(1, len(clean_text))
    if len(links) >= 20 and paragraphs < 3:
        return False
    if link_density > 0.65 and paragraphs < 5:
        return False
    lowered = clean_text.lower()
    if lowered.count("leer más") >= 5 and paragraphs < 5:
        return False
    return True


def score_node(node, text: str) -> float:
    """Score an HTML node for article-body likelihood."""
    text_len = len(text)
    paragraphs = len(node.find_all("p"))
    links_text = " ".join(link.get_text(" ", strip=True) for link in node.find_all("a"))
    link_density = len(links_text) / max(1, text_len)
    return text_len + paragraphs * 120 - link_density * text_len * 2


def dedupe_lines(text: str) -> object:
    """Normalize whitespace and remove repeated adjacent lines."""
    lines = []
    previous = None
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line or line == previous:
            continue
        lines.append(line)
        previous = line
    joined = "\n".join(lines).strip()
    return joined if joined else pd.NA


def text_or_na(node) -> object:
    """Return node text or NA."""
    if node is None:
        return pd.NA
    return clean_scalar(node.get_text(" ", strip=True))


def clean_title(value: object, url: str) -> object:
    """Clean a page title by removing common site suffixes."""
    value = clean_scalar(value)
    if pd.isna(value):
        return pd.NA
    text = str(value)
    host = urlparse(url).netloc.replace("www.", "")
    for separator in (" | ", " - ", " – ", " — "):
        if separator in text:
            parts = [part.strip() for part in text.split(separator) if part.strip()]
            if parts and not any(host in part.lower() for part in parts[:1]):
                return parts[0]
    return text


def clean_scalar(value: object) -> object:
    """Return a normalized scalar or NA."""
    if value is None:
        return pd.NA
    try:
        if pd.isna(value):
            return pd.NA
    except (TypeError, ValueError):
        pass
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text if text else pd.NA


def print_progress(
    processed: int,
    total: int,
    started_at: float,
    errors: int,
    blank_text: int,
    sample_error: object,
) -> None:
    """Print compact extraction progress."""
    elapsed = time.monotonic() - started_at
    rate_per_minute = (processed / elapsed * 60) if elapsed else 0.0
    remaining = ((total - processed) / (processed / elapsed)) if processed and elapsed else 0.0
    pct = (processed / total * 100) if total else 100.0
    message = (
        f"Progress: {processed:,}/{total:,} ({pct:.1f}%) | "
        f"rate={rate_per_minute:.1f}/min | eta={format_duration(remaining)} | "
        f"errors={errors:,} | blank_text={blank_text:,}"
    )
    if pd.notna(sample_error):
        message += f" | sample_error={shorten_error(sample_error)}"
    print(message)


def format_duration(seconds: float) -> str:
    """Format a rough duration for terminal progress."""
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def save_sitemap_articles_to_sqlite(articles: pd.DataFrame, db_path: Path) -> None:
    """Upsert sitemap article rows into SQLite."""
    import sqlite3

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if articles.empty:
        return

    output_articles = normalize_articles_for_output(articles)
    columns = list(output_articles.columns)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        ensure_sitemap_article_table(conn, columns)
        quoted_columns = [quote_sqlite_identifier(column) for column in columns]
        placeholders = ", ".join("?" for _ in columns)
        update_columns = [column for column in columns if column not in ARTICLE_KEY_COLUMNS]
        updates = ", ".join(
            f"{quote_sqlite_identifier(column)} = excluded.{quote_sqlite_identifier(column)}"
            for column in update_columns
        )
        sql = (
            f"INSERT INTO sitemap_articles ({', '.join(quoted_columns)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT(source_id, url) DO UPDATE SET {updates}"
        )
        records = [
            tuple(sqlite_value(row[column]) for column in columns)
            for _, row in output_articles.iterrows()
        ]
        conn.executemany(sql, records)
        conn.commit()


def ensure_sitemap_article_table(conn, columns: list[str]) -> None:
    """Create or extend the sitemap article progress table."""
    column_defs = [f"{quote_sqlite_identifier(column)} TEXT" for column in columns]
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sitemap_articles ("
        + ", ".join(column_defs)
        + ", PRIMARY KEY (source_id, url))"
    )
    existing_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(sitemap_articles)").fetchall()
    }
    for column in columns:
        if column not in existing_columns:
            conn.execute(
                f"ALTER TABLE sitemap_articles ADD COLUMN {quote_sqlite_identifier(column)} TEXT"
            )


def load_sitemap_articles_from_sqlite(path: Path, columns: list[str] | None = None) -> pd.DataFrame:
    """Load sitemap article rows from SQLite."""
    import sqlite3

    if not path.exists():
        return pd.DataFrame(columns=columns or [])
    with sqlite3.connect(path) as conn:
        table_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sitemap_articles'"
        ).fetchone()
        if table_exists is None:
            return pd.DataFrame(columns=columns or [])
        if columns:
            available = {
                row[1]
                for row in conn.execute("PRAGMA table_info(sitemap_articles)").fetchall()
            }
            selected = [column for column in columns if column in available]
            if not selected:
                return pd.DataFrame(columns=columns)
            sql = "SELECT " + ", ".join(quote_sqlite_identifier(column) for column in selected) + " FROM sitemap_articles"
        else:
            sql = "SELECT * FROM sitemap_articles"
        return pd.read_sql_query(sql, conn)


def write_sitemap_article_outputs(
    articles: pd.DataFrame,
    report: str,
    articles_dir: Path,
    reports_dir: Path,
    *,
    write_per_source: bool = True,
) -> SitemapArticleOutputs:
    """Write per-source sitemap article parquet.gzip outputs and a report."""
    articles_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "sitemap_article_extraction_report.md"
    output_articles = normalize_articles_for_output(articles)

    parquet_error = None
    try:
        if write_per_source and not output_articles.empty:
            for source_id, source_articles in output_articles.groupby("source_id", dropna=True):
                source_dir = articles_dir / str(source_id)
                source_dir.mkdir(parents=True, exist_ok=True)
                source_articles.to_parquet(
                    source_dir / "articles.parquet.gzip",
                    index=False,
                    compression="gzip",
                )
    except Exception as exc:
        parquet_error = str(exc).splitlines()[0]
        print(f"Skipped one or more per-source parquet outputs: {parquet_error}")

    report_path.write_text(report, encoding="utf-8")
    return SitemapArticleOutputs(articles_dir, report_path, parquet_error)


def build_sitemap_article_report(articles: pd.DataFrame) -> str:
    """Create a compact sitemap article extraction report."""
    lines = [
        "# Sitemap Article Extraction Report",
        "",
        f"- Rows: {len(articles):,}",
        f"- Sources: {articles['source_id'].nunique() if not articles.empty else 0:,}",
        f"- Article URLs: {articles['url'].notna().sum() if not articles.empty else 0:,}",
        f"- Error rows: {articles['error'].notna().sum() if not articles.empty else 0:,}",
        f"- Missing main_text: {articles['main_text'].fillna('').astype(str).str.strip().eq('').sum() if not articles.empty else 0:,}",
        "",
        "## Coverage By Source",
        "",
    ]
    if articles.empty:
        lines.append("_No rows._")
    else:
        summary = (
            articles.groupby(["source_id", "source_name"], dropna=False)
            .agg(
                rows=("url", "size"),
                errors=("error", lambda values: values.notna().sum()),
                missing_text=("main_text", lambda values: values.fillna("").astype(str).str.strip().eq("").sum()),
                min_date=("date_published", "min"),
                max_date=("date_published", "max"),
            )
            .reset_index()
            .sort_values(["rows", "source_id"], ascending=[False, True])
        )
        lines.append(markdown_table(summary.head(100)))

    lines.extend(["", "## Sample Rows", ""])
    if articles.empty:
        lines.append("_No rows._")
    else:
        sample = articles[["source_id", "url", "date_published", "title", "authors", "topic", "error"]].head(30)
        lines.append(markdown_table(sample))
    lines.append("")
    return "\n".join(lines)

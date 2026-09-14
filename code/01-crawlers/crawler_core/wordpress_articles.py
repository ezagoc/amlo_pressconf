"""WordPress REST API article extraction."""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from urllib.parse import urlencode, urljoin

import pandas as pd

from crawler_core.capabilities import fetch, markdown_table
from crawler_core.wordpress import WP_POSTS_ENDPOINT, clean_html


ARTICLE_KEY_COLUMNS = ["source_id", "wp_post_id"]
ARTICLE_API_BODY_TEXT_LIMIT = 50_000_000
WORDPRESS_CATEGORIES_ENDPOINT = "/wp-json/wp/v2/categories"
WORDPRESS_TAGS_ENDPOINT = "/wp-json/wp/v2/tags"
WORDPRESS_ARTICLE_FIELDS = (
    "id",
    "date",
    "modified",
    "slug",
    "link",
    "title",
    "excerpt",
    "content",
    "categories",
    "tags",
    "_embedded",
)


@dataclass(frozen=True)
class ArticleOutputs:
    """Paths written by WordPress article extraction."""

    articles_dir: Path
    report_path: Path
    parquet_error: str | None = None


def load_discovered_urls(path: Path) -> pd.DataFrame:
    """Load discovered URL rows from CSV or parquet."""
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def load_existing_articles(path: Path | None) -> pd.DataFrame | None:
    """Load existing checkpoint/output article rows if present."""
    if path is None or not path.exists():
        return None
    if is_sqlite_path(path):
        return load_articles_from_sqlite(path)
    if is_parquet_path(path):
        return pd.read_parquet(path)
    return pd.read_csv(path, low_memory=False)


def load_existing_article_statuses(path: Path | None) -> pd.DataFrame | None:
    """Load only resume keys and error status from an existing article store."""
    if path is None or not path.exists():
        return None
    columns = ["source_id", "wp_post_id", "error"]
    if is_sqlite_path(path):
        return load_articles_from_sqlite(path, columns=columns)
    if is_parquet_path(path):
        return pd.read_parquet(path, columns=columns)
    return pd.read_csv(path, usecols=lambda column: column in set(columns), low_memory=False)


def is_sqlite_path(path: Path) -> bool:
    """Return True for SQLite progress database paths."""
    return path.suffix.lower() in {".sqlite", ".sqlite3", ".db"}


def is_parquet_path(path: Path) -> bool:
    """Return True for parquet output paths, including .parquet.gzip."""
    name = path.name.lower()
    return path.suffix.lower() == ".parquet" or name.endswith(".parquet.gzip")


def prepare_article_queue(
    discovered: pd.DataFrame,
    *,
    source_ids: list[str] | None = None,
    limit: int | None = None,
    existing_articles: pd.DataFrame | None = None,
    retry_errors: bool = False,
) -> pd.DataFrame:
    """Filter discovered URL rows to rows ready for article extraction."""
    queue = discovered.copy()
    queue = queue[queue["url"].notna() & queue["wp_post_id"].notna()].copy()
    if source_ids:
        queue = queue[queue["source_id"].isin(source_ids)].copy()

    queue["wp_post_id"] = queue["wp_post_id"].astype("int64")
    queue = queue.drop_duplicates(ARTICLE_KEY_COLUMNS, keep="last")

    if existing_articles is not None and not existing_articles.empty:
        existing = existing_articles.copy()
        existing = existing[existing["source_id"].notna() & existing["wp_post_id"].notna()].copy()
        existing["wp_post_id"] = existing["wp_post_id"].astype("int64")
        if retry_errors:
            existing = existing[existing["error"].isna()].copy()
        done = existing[ARTICLE_KEY_COLUMNS].drop_duplicates()
        done["_already_done"] = True
        queue = queue.merge(done, on=ARTICLE_KEY_COLUMNS, how="left")
        queue = queue[queue["_already_done"].isna()].drop(columns=["_already_done"]).copy()

    queue = queue.sort_values(["source_id", "date_published", "wp_post_id"], ascending=[True, False, False])
    if limit is not None:
        queue = queue.head(limit)
    return queue.reset_index(drop=True)


def extract_wordpress_articles(
    queue: pd.DataFrame,
    *,
    initial_rows: pd.DataFrame | None = None,
    checkpoint_path: Path | None = None,
    checkpoint_every: int = 100,
    timeout: float = 20.0,
    pause_seconds: float = 0.1,
    progress_every: int = 100,
    progress_seconds: float = 60.0,
    row_log: bool = False,
    batch_size: int = 1,
    workers: int = 1,
    keep_rows: bool = True,
) -> pd.DataFrame:
    """Extract full article records from WordPress API post endpoints."""
    rows: list[dict[str, object]] = []
    if initial_rows is not None and not initial_rows.empty:
        rows.extend(initial_rows.to_dict("records"))

    total = len(queue)
    processed_since_checkpoint = 0
    started_at = time.monotonic()
    last_progress_at = 0.0
    errors = 0
    blank_text = 0
    sample_error = pd.NA
    workers = max(1, int(workers or 1))
    chunks = list(iter_queue_chunks(queue, batch_size))
    print(
        f"Starting article extraction: {total:,} queued rows | "
        f"batches={len(chunks):,} | batch_size={batch_size:,} | workers={workers:,}"
    )

    try:
        if workers == 1:
            position = 0
            for chunk in chunks:
                chunk_rows = process_wordpress_article_chunk(chunk, timeout=timeout, row_log=row_log)
                position += len(chunk_rows)
                rows, processed_since_checkpoint, errors, blank_text, sample_error, last_progress_at = update_article_progress(
                    rows=rows,
                    chunk_rows=chunk_rows,
                    keep_rows=keep_rows,
                    processed_since_checkpoint=processed_since_checkpoint,
                    errors=errors,
                    blank_text=blank_text,
                    sample_error=sample_error,
                    position=position,
                    total=total,
                    started_at=started_at,
                    last_progress_at=last_progress_at,
                    progress_every=progress_every,
                    progress_seconds=progress_seconds,
                    checkpoint_path=checkpoint_path,
                    checkpoint_every=checkpoint_every,
                )
                if pause_seconds:
                    time.sleep(pause_seconds)
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(process_wordpress_article_chunk, chunk, timeout=timeout, row_log=row_log): len(chunk)
                    for chunk in chunks
                }
                position = 0
                for future in as_completed(futures):
                    chunk_rows = future.result()
                    position += len(chunk_rows)
                    rows, processed_since_checkpoint, errors, blank_text, sample_error, last_progress_at = update_article_progress(
                    rows=rows,
                    chunk_rows=chunk_rows,
                    keep_rows=keep_rows,
                        processed_since_checkpoint=processed_since_checkpoint,
                        errors=errors,
                        blank_text=blank_text,
                        sample_error=sample_error,
                        position=position,
                        total=total,
                        started_at=started_at,
                        last_progress_at=last_progress_at,
                        progress_every=progress_every,
                        progress_seconds=progress_seconds,
                        checkpoint_path=checkpoint_path,
                        checkpoint_every=checkpoint_every,
                    )
    except KeyboardInterrupt:
        print("Interrupted by user; saving partial results before exiting.")

    articles = pd.DataFrame(rows)
    if not articles.empty:
        articles = articles.drop_duplicates(ARTICLE_KEY_COLUMNS, keep="last").reset_index(drop=True)
    if checkpoint_path is not None and not is_sqlite_path(checkpoint_path):
        save_article_checkpoint(articles, checkpoint_path)
    return articles


def iter_queue_chunks(queue: pd.DataFrame, batch_size: int) -> list[pd.DataFrame]:
    """Yield queue chunks without mixing source endpoints."""
    position = 0
    while position < len(queue):
        chunk_size = effective_chunk_size(queue, position, batch_size)
        yield queue.iloc[position : position + chunk_size].copy()
        position += chunk_size


def effective_chunk_size(queue: pd.DataFrame, position: int, batch_size: int) -> int:
    """Return a chunk size that does not mix source endpoints."""
    size = max(1, int(batch_size or 1))
    if size == 1:
        return 1

    first = queue.iloc[position]
    end = min(position + size, len(queue))
    chunk = queue.iloc[position:end]
    same_source = (
        (chunk["source_id"] == first["source_id"])
        & (chunk["source_url"] == first["source_url"])
    )
    return max(1, int(same_source.sum()))


def process_wordpress_article_chunk(
    chunk: pd.DataFrame,
    *,
    timeout: float,
    row_log: bool,
) -> list[dict[str, object]]:
    """Fetch one article chunk, returning one output row per input row."""
    item = chunk.iloc[0]
    if row_log:
        ids = ", ".join(str(int(value)) for value in chunk["wp_post_id"].head(5))
        suffix = "..." if len(chunk) > 5 else ""
        print(f"{item['source_id']} batch={len(chunk)} posts={ids}{suffix}")

    try:
        if len(chunk) == 1:
            chunk_rows = [extract_one_wordpress_article(item, timeout=timeout)]
        else:
            chunk_rows = extract_wordpress_article_batch(chunk, timeout=timeout)
    except Exception as exc:
        chunk_rows = []
        for _, failed_item in chunk.iterrows():
            row = base_article_row(failed_item)
            row["status"] = pd.NA
            row["error"] = f"{type(exc).__name__}: {exc}"
            chunk_rows.append(row)
        if row_log:
            print(f"  batch error: {type(exc).__name__}: {exc}")

    if row_log:
        batch_errors = sum(pd.notna(row.get("error")) for row in chunk_rows)
        batch_blank = sum(
            pd.isna(row.get("error")) and len(str(row.get("main_text") or "")) == 0
            for row in chunk_rows
        )
        print(f"  ok batch_rows={len(chunk_rows):,}, batch_errors={batch_errors:,}, batch_blank={batch_blank:,}")
    return chunk_rows


def update_article_progress(
    *,
    rows: list[dict[str, object]],
    chunk_rows: list[dict[str, object]],
    keep_rows: bool,
    processed_since_checkpoint: int,
    errors: int,
    blank_text: int,
    sample_error: object,
    position: int,
    total: int,
    started_at: float,
    last_progress_at: float,
    progress_every: int,
    progress_seconds: float,
    checkpoint_path: Path | None,
    checkpoint_every: int,
) -> tuple[list[dict[str, object]], int, int, int, object, float]:
    """Accumulate rows, print progress, and checkpoint when needed."""
    if keep_rows:
        rows.extend(chunk_rows)
    processed_since_checkpoint += len(chunk_rows)
    for row in chunk_rows:
        if pd.notna(row.get("error")):
            errors += 1
            if pd.isna(sample_error):
                sample_error = row.get("error")
        elif len(str(row.get("main_text") or "")) == 0:
            blank_text += 1

    now = time.monotonic()
    should_print_count = bool(progress_every and (position % progress_every == 0 or position == total))
    should_print_time = bool(progress_seconds and now - last_progress_at >= progress_seconds)
    if should_print_count or should_print_time:
        print_progress(position, total, started_at, errors, blank_text, sample_error=sample_error)
        last_progress_at = now

    if checkpoint_path is not None:
        if is_sqlite_path(checkpoint_path):
            save_article_checkpoint(pd.DataFrame(chunk_rows), checkpoint_path)
        elif processed_since_checkpoint >= checkpoint_every:
            save_article_checkpoint(pd.DataFrame(rows), checkpoint_path)
            processed_since_checkpoint = 0

    return rows, processed_since_checkpoint, errors, blank_text, sample_error, last_progress_at


def print_progress(
    position: int,
    total: int,
    started_at: float,
    errors: int,
    blank_text: int,
    sample_error: object = pd.NA,
) -> None:
    """Print one compact extraction progress line."""
    elapsed = time.monotonic() - started_at
    rate_per_minute = (position / elapsed * 60) if elapsed else 0.0
    remaining = ((total - position) / (position / elapsed)) if position and elapsed else 0.0
    pct = (position / total * 100) if total else 100.0
    message = (
        "Progress: "
        f"{position:,}/{total:,} ({pct:.1f}%) | "
        f"rate={rate_per_minute:.1f}/min | "
        f"eta={format_duration(remaining)} | "
        f"errors={errors:,} | blank_text={blank_text:,}"
    )
    if pd.notna(sample_error):
        message += f" | sample_error={shorten_error(sample_error)}"
    print(message)


def shorten_error(error: object, limit: int = 160) -> str:
    """Shorten error text for terminal progress messages."""
    text = " ".join(str(error).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def format_duration(seconds: float) -> str:
    """Format a rough duration for terminal progress messages."""
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def extract_one_wordpress_article(item: pd.Series, *, timeout: float) -> dict[str, object]:
    """Fetch and extract one WordPress post."""
    api_url = wordpress_post_api_url(str(item["source_url"]), int(item["wp_post_id"]))
    response = fetch(api_url, timeout, body_text_limit=ARTICLE_API_BODY_TEXT_LIMIT)
    row = base_article_row(item)
    row["article_api_url"] = api_url
    row["status"] = response["status"]

    status = response["status"]
    if not isinstance(status, int) or status < 200 or status >= 300:
        error = response["error"]
        if pd.isna(error):
            error = f"http_status_{status}"
        row["error"] = error
        return row

    try:
        post = json.loads(response["text"] or "")
    except json.JSONDecodeError as exc:
        row["error"] = f"JSONDecodeError: {exc}"
        return row

    row.update(article_fields_from_post(post))
    row["error"] = pd.NA
    return row


def extract_wordpress_article_batch(items: pd.DataFrame, *, timeout: float) -> list[dict[str, object]]:
    """Fetch and extract a batch of WordPress posts from one source."""
    post_ids = [int(value) for value in items["wp_post_id"]]
    api_url = wordpress_posts_batch_api_url(str(items.iloc[0]["source_url"]), post_ids)
    response = fetch(api_url, timeout, body_text_limit=ARTICLE_API_BODY_TEXT_LIMIT)
    status = response["status"]

    if not isinstance(status, int) or status < 200 or status >= 300:
        error = response["error"]
        if pd.isna(error):
            error = f"http_status_{status}"
        return [batch_error_row(item, status, error) for _, item in items.iterrows()]

    try:
        payload = json.loads(response["text"] or "")
    except json.JSONDecodeError as exc:
        return [batch_error_row(item, status, f"JSONDecodeError: {exc}") for _, item in items.iterrows()]

    if not isinstance(payload, list):
        return [batch_error_row(item, status, "unexpected_batch_payload") for _, item in items.iterrows()]

    posts_by_id = {
        int(post["id"]): post
        for post in payload
        if isinstance(post, dict) and str(post.get("id", "")).isdigit()
    }

    rows = []
    for _, item in items.iterrows():
        row = base_article_row(item)
        row["article_api_url"] = wordpress_post_api_url(str(item["source_url"]), int(item["wp_post_id"]))
        row["status"] = status
        post = posts_by_id.get(int(item["wp_post_id"]))
        if post is None:
            row["error"] = "missing_from_batch_response"
        else:
            row.update(article_fields_from_post(post))
            row["error"] = pd.NA
        rows.append(row)
    return rows


def batch_error_row(item: pd.Series, status: object, error: object) -> dict[str, object]:
    """Create one failed article row from a failed batch response."""
    row = base_article_row(item)
    row["article_api_url"] = wordpress_post_api_url(str(item["source_url"]), int(item["wp_post_id"]))
    row["status"] = status
    row["error"] = error
    return row


def wordpress_post_api_url(source_url: str, wp_post_id: int) -> str:
    """Build a WordPress REST API URL for one post."""
    base = urljoin(source_url, f"{WP_POSTS_ENDPOINT}/{wp_post_id}")
    query = urlencode(
        {
            "_embed": "wp:term",
            "_fields": ",".join(WORDPRESS_ARTICLE_FIELDS),
        }
    )
    return f"{base}?{query}"


def wordpress_posts_batch_api_url(source_url: str, wp_post_ids: list[int]) -> str:
    """Build a WordPress REST API URL for a batch of posts."""
    base = urljoin(source_url, WP_POSTS_ENDPOINT)
    query = urlencode(
        {
            "include": ",".join(str(post_id) for post_id in wp_post_ids),
            "per_page": len(wp_post_ids),
            "orderby": "include",
            "_embed": "wp:term",
            "_fields": ",".join(WORDPRESS_ARTICLE_FIELDS),
        }
    )
    return f"{base}?{query}"


def base_article_row(item: pd.Series) -> dict[str, object]:
    """Base article row populated from discovery metadata."""
    return {
        "source_id": item.get("source_id"),
        "source_name": item.get("source_name"),
        "source_url": item.get("source_url"),
        "url": item.get("url"),
        "canonical_url": item.get("canonical_url", item.get("url")),
        "wp_post_id": item.get("wp_post_id"),
        "slug": item.get("slug"),
        "title": item.get("title"),
        "summary": item.get("summary"),
        "main_text": pd.NA,
        "authors": pd.NA,
        "date": item.get("date_published"),
        "date_published": item.get("date_published"),
        "date_modified": item.get("date_modified"),
        "topic": pd.NA,
        "section": pd.NA,
        "tags": pd.NA,
        "category_ids": item.get("category_ids"),
        "tag_ids": item.get("tag_ids"),
        "language": pd.NA,
        "discovery_strategy": item.get("discovery_strategy"),
        "extractor_strategy": "wordpress_api",
        "article_api_url": pd.NA,
        "scrape_timestamp": pd.Timestamp.utcnow().isoformat(),
        "status": pd.NA,
        "error": pd.NA,
    }


def article_fields_from_post(post: dict[str, object]) -> dict[str, object]:
    """Extract article fields from a WordPress post JSON object."""
    terms = embedded_terms(post)
    authors = embedded_authors(post)
    content_html = nested_rendered(post, "content")
    excerpt_html = nested_rendered(post, "excerpt")

    categories = [term["name"] for term in terms if term.get("taxonomy") == "category"]
    tags = [term["name"] for term in terms if term.get("taxonomy") == "post_tag"]

    return {
        "url": post.get("link"),
        "canonical_url": post.get("link"),
        "slug": post.get("slug"),
        "title": clean_html(nested_rendered(post, "title")),
        "summary": clean_html(excerpt_html),
        "main_text": html_to_text(content_html),
        "authors": "; ".join(authors) if authors else pd.NA,
        "date": post.get("date"),
        "date_published": post.get("date"),
        "date_modified": post.get("modified"),
        "topic": categories[0] if categories else pd.NA,
        "section": categories[0] if categories else pd.NA,
        "tags": "; ".join(tags) if tags else pd.NA,
        "category_names": "; ".join(categories) if categories else pd.NA,
        "tag_names": "; ".join(tags) if tags else pd.NA,
    }


def nested_rendered(post: dict[str, object], key: str) -> object:
    value = post.get(key)
    if isinstance(value, dict):
        return value.get("rendered")
    return pd.NA


def embedded_authors(post: dict[str, object]) -> list[str]:
    embedded = post.get("_embedded")
    if not isinstance(embedded, dict):
        return []
    authors = embedded.get("author")
    if not isinstance(authors, list):
        return []
    names = []
    for author in authors:
        if isinstance(author, dict) and author.get("name"):
            names.append(str(author["name"]).strip())
    return names


def embedded_terms(post: dict[str, object]) -> list[dict[str, object]]:
    embedded = post.get("_embedded")
    if not isinstance(embedded, dict):
        return []
    term_groups = embedded.get("wp:term")
    if not isinstance(term_groups, list):
        return []
    terms: list[dict[str, object]] = []
    for group in term_groups:
        if isinstance(group, list):
            terms.extend(term for term in group if isinstance(term, dict))
    return terms


def html_to_text(value: object) -> object:
    """Convert rendered article HTML to plain text."""
    if value is None or pd.isna(value):
        return pd.NA
    text = str(value)
    text = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|section|article|h[1-6]|li|blockquote)>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def refresh_article_term_names(
    articles: pd.DataFrame,
    *,
    source_ids: list[str] | None = None,
    timeout: float = 30.0,
    batch_size: int = 100,
) -> pd.DataFrame:
    """Fill category/tag names from WordPress term endpoints using stored IDs."""
    if articles.empty:
        return articles.copy()

    refreshed = articles.copy()
    for column in ("category_names", "tag_names", "topic", "section", "tags"):
        if column not in refreshed.columns:
            refreshed[column] = pd.NA

    sources = refreshed[["source_id", "source_url"]].drop_duplicates()
    if source_ids:
        sources = sources[sources["source_id"].isin(source_ids)].copy()

    for _, source in sources.iterrows():
        source_id = source["source_id"]
        source_url = source["source_url"]
        if pd.isna(source_id) or pd.isna(source_url):
            continue

        source_mask = refreshed["source_id"].eq(source_id)
        source_articles = refreshed.loc[source_mask]
        category_ids = sorted(
            {
                term_id
                for value in source_articles.get("category_ids", pd.Series(dtype=object))
                for term_id in parse_term_ids(value)
            }
        )
        tag_ids = sorted(
            {
                term_id
                for value in source_articles.get("tag_ids", pd.Series(dtype=object))
                for term_id in parse_term_ids(value)
            }
        )

        category_map = fetch_wordpress_terms(
            str(source_url),
            WORDPRESS_CATEGORIES_ENDPOINT,
            category_ids,
            timeout=timeout,
            batch_size=batch_size,
        )
        tag_map = fetch_wordpress_terms(
            str(source_url),
            WORDPRESS_TAGS_ENDPOINT,
            tag_ids,
            timeout=timeout,
            batch_size=batch_size,
        )
        print(
            f"Term refresh {source_id}: "
            f"categories={len(category_map):,}/{len(category_ids):,}, "
            f"tags={len(tag_map):,}/{len(tag_ids):,}"
        )

        for index in source_articles.index:
            category_names = names_from_ids(refreshed.at[index, "category_ids"], category_map)
            tag_names = names_from_ids(refreshed.at[index, "tag_ids"], tag_map)
            if category_names and is_missing_text(refreshed.at[index, "category_names"]):
                joined = "; ".join(category_names)
                refreshed.at[index, "category_names"] = joined
                if is_missing_text(refreshed.at[index, "topic"]):
                    refreshed.at[index, "topic"] = category_names[0]
                if is_missing_text(refreshed.at[index, "section"]):
                    refreshed.at[index, "section"] = category_names[0]
            if tag_names:
                joined = "; ".join(tag_names)
                if is_missing_text(refreshed.at[index, "tag_names"]):
                    refreshed.at[index, "tag_names"] = joined
                if is_missing_text(refreshed.at[index, "tags"]):
                    refreshed.at[index, "tags"] = joined

    return refreshed


def fetch_wordpress_terms(
    source_url: str,
    endpoint: str,
    ids: list[int],
    *,
    timeout: float,
    batch_size: int,
) -> dict[int, str]:
    """Fetch WordPress category/tag names for term IDs."""
    terms: dict[int, str] = {}
    if not ids:
        return terms

    size = max(1, min(100, int(batch_size or 100)))
    for start in range(0, len(ids), size):
        batch_ids = ids[start : start + size]
        url = wordpress_terms_api_url(source_url, endpoint, batch_ids)
        response = fetch(url, timeout, body_text_limit=10_000_000)
        status = response["status"]
        if not isinstance(status, int) or status < 200 or status >= 300:
            error = response["error"]
            if pd.isna(error):
                error = f"http_status_{status}"
            print(f"  term fetch failed: {endpoint} status={status}, error={shorten_error(error)}")
            continue
        try:
            payload = json.loads(response["text"] or "")
        except json.JSONDecodeError as exc:
            print(f"  term fetch failed: {endpoint} JSONDecodeError: {exc}")
            continue
        if not isinstance(payload, list):
            print(f"  term fetch failed: {endpoint} unexpected payload")
            continue
        for term in payload:
            if isinstance(term, dict) and str(term.get("id", "")).isdigit() and term.get("name"):
                terms[int(term["id"])] = clean_html(term["name"])
    return terms


def wordpress_terms_api_url(source_url: str, endpoint: str, ids: list[int]) -> str:
    """Build a WordPress REST API URL for category/tag ID lookup."""
    base = urljoin(source_url, endpoint)
    query = urlencode(
        {
            "include": ",".join(str(term_id) for term_id in ids),
            "per_page": len(ids),
            "orderby": "include",
            "_fields": "id,name",
        }
    )
    return f"{base}?{query}"


def parse_term_ids(value: object) -> list[int]:
    """Parse a stored semicolon/comma-separated term ID value."""
    if value is None or pd.isna(value):
        return []
    return [int(match) for match in re.findall(r"\d+", str(value))]


def names_from_ids(value: object, term_map: dict[int, str]) -> list[str]:
    """Return ordered unique names for a stored term-id value."""
    names: list[str] = []
    for term_id in parse_term_ids(value):
        name = term_map.get(term_id)
        if name and name not in names:
            names.append(name)
    return names


def is_missing_text(value: object) -> bool:
    """Return True for null or blank text-like values."""
    return value is None or pd.isna(value) or str(value).strip() == ""


def save_article_checkpoint(articles: pd.DataFrame, checkpoint_path: Path) -> None:
    """Write article progress to SQLite or a legacy CSV checkpoint."""
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    if not articles.empty:
        articles = articles.drop_duplicates(ARTICLE_KEY_COLUMNS, keep="last")
    if is_sqlite_path(checkpoint_path):
        save_articles_to_sqlite(articles, checkpoint_path)
        return
    articles.to_csv(checkpoint_path, index=False, encoding="utf-8")
    print(f"Checkpoint saved: {checkpoint_path} ({len(articles):,} rows)")


def save_articles_to_sqlite(articles: pd.DataFrame, db_path: Path) -> None:
    """Upsert article rows into a SQLite progress database."""
    import sqlite3

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if articles.empty:
        return

    output_articles = normalize_articles_for_output(articles)
    columns = list(output_articles.columns)
    if "source_id" not in columns or "wp_post_id" not in columns:
        raise ValueError("SQLite article progress requires source_id and wp_post_id columns")

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        ensure_article_table(conn, columns)
        quoted_columns = [quote_sqlite_identifier(column) for column in columns]
        placeholders = ", ".join("?" for _ in columns)
        update_columns = [column for column in columns if column not in ARTICLE_KEY_COLUMNS]
        updates = ", ".join(
            f"{quote_sqlite_identifier(column)} = excluded.{quote_sqlite_identifier(column)}"
            for column in update_columns
        )
        sql = (
            f"INSERT INTO articles ({', '.join(quoted_columns)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT(source_id, wp_post_id) DO UPDATE SET {updates}"
        )
        records = [
            tuple(sqlite_value(row[column]) for column in columns)
            for _, row in output_articles.iterrows()
        ]
        conn.executemany(sql, records)
        conn.commit()


def ensure_article_table(conn: sqlite3.Connection, columns: list[str]) -> None:
    """Create or extend the SQLite article progress table."""
    column_defs = [f"{quote_sqlite_identifier(column)} TEXT" for column in columns]
    conn.execute(
        "CREATE TABLE IF NOT EXISTS articles ("
        + ", ".join(column_defs)
        + ", PRIMARY KEY (source_id, wp_post_id))"
    )
    existing_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(articles)").fetchall()
    }
    for column in columns:
        if column not in existing_columns:
            conn.execute(
                f"ALTER TABLE articles ADD COLUMN {quote_sqlite_identifier(column)} TEXT"
            )


def load_articles_from_sqlite(path: Path, columns: list[str] | None = None) -> pd.DataFrame:
    """Load article rows from the SQLite progress database."""
    import sqlite3

    if not path.exists():
        return pd.DataFrame()
    with sqlite3.connect(path) as conn:
        table_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='articles'"
        ).fetchone()
        if table_exists is None:
            return pd.DataFrame(columns=columns or [])
        if columns:
            available = {
                row[1]
                for row in conn.execute("PRAGMA table_info(articles)").fetchall()
            }
            selected = [column for column in columns if column in available]
            if not selected:
                return pd.DataFrame(columns=columns)
            sql = "SELECT " + ", ".join(quote_sqlite_identifier(column) for column in selected) + " FROM articles"
        else:
            sql = "SELECT * FROM articles"
        return pd.read_sql_query(sql, conn)


def sqlite_value(value: object) -> object:
    """Convert pandas missing values to SQLite nulls."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def quote_sqlite_identifier(identifier: str) -> str:
    """Quote a SQLite identifier."""
    return '"' + identifier.replace('"', '""') + '"'


def normalize_articles_for_output(articles: pd.DataFrame) -> pd.DataFrame:
    """Normalize mixed object columns so pyarrow can write parquet consistently."""
    normalized = articles.copy()
    for column in normalized.columns:
        if normalized[column].dtype == "object":
            normalized[column] = normalized[column].map(normalize_output_value)
    return normalized


def normalize_output_value(value: object) -> object:
    """Convert mixed scalar/list values to stable output values."""
    if value is None:
        return pd.NA
    try:
        if pd.isna(value):
            return pd.NA
    except (TypeError, ValueError):
        pass
    if isinstance(value, (list, tuple, set)):
        return "; ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def write_article_outputs(
    articles: pd.DataFrame,
    report: str,
    articles_dir: Path,
    reports_dir: Path,
    *,
    write_per_source: bool = True,
) -> ArticleOutputs:
    """Write optional per-source compressed parquet article outputs and a report."""
    articles_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    report_path = reports_dir / "wordpress_article_extraction_report.md"

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
    return ArticleOutputs(articles_dir, report_path, parquet_error)


def build_article_extraction_report(articles: pd.DataFrame) -> str:
    """Create a compact article extraction report."""
    missing_text = pd.Series(dtype=bool)
    if not articles.empty:
        missing_text = articles["main_text"].fillna("").astype(str).str.strip().eq("")

    lines = [
        "# WordPress Article Extraction Report",
        "",
        f"- Rows: {len(articles):,}",
        f"- Sources: {articles['source_id'].nunique() if not articles.empty else 0:,}",
        f"- Usable article URLs: {articles['url'].notna().sum() if not articles.empty else 0:,}",
        f"- Error rows: {articles['error'].notna().sum() if not articles.empty else 0:,}",
        f"- Missing main_text: {missing_text.sum() if not articles.empty else 0:,}",
        "",
        "## Articles By Source",
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

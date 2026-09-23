"""Checkpointed historical URL discovery for El Universal via its public search index."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import threading
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlunparse

import pandas as pd

from crawler_core.capabilities import fetch, markdown_table


SOURCE_ID = "eluniversal"
SOURCE_NAME = "El Universal"
SOURCE_URL = "https://www.eluniversal.com.mx/"
QUERYLY_URL = "https://api.queryly.com/json.aspx"
QUERYLY_KEY = "000ca78dce0f4c6b"
NON_ARTICLE_SECTIONS = {
    "autores",
    "buscador",
    "consultas",
    "descuentos",
    "files",
    "newsletter",
    "portada-impresa",
}
DISCOVERY_COLUMNS = (
    "source_id",
    "source_name",
    "source_url",
    "url",
    "canonical_url",
    "date_published",
    "lastmod",
    "topic",
    "discovery_strategy",
    "query_date",
    "query_url",
    "page_number",
    "status",
    "error",
    "discovered_at",
)


@dataclass(frozen=True)
class ElUniversalOutputs:
    discovered_csv: Path
    discovered_parquet: Path | None
    report_path: Path
    parquet_error: str | None = None


@dataclass(frozen=True)
class ElUniversalSummary:
    rows: int
    urls: int
    errors: int
    duplicates_skipped: int


class RequestRateLimiter:
    """Space request starts across all discovery workers."""

    def __init__(self, interval_seconds: float) -> None:
        self.interval_seconds = max(0.0, interval_seconds)
        self.next_request_at = 0.0
        self.lock = threading.Lock()

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            delay = self.next_request_at - now
            if delay > 0:
                time.sleep(delay)
                now = time.monotonic()
            self.next_request_at = now + self.interval_seconds


def discover_eluniversal_urls(
    *,
    from_date: date,
    to_date: date,
    checkpoint_dir: Path,
    resume: bool = False,
    workers: int = 2,
    batch_size: int = 100,
    max_pages_per_day: int = 20,
    timeout: float = 60.0,
    pause_seconds: float = 1.0,
    request_retries: int = 2,
    retry_backoff_seconds: float = 2.0,
    limit_days: int | None = None,
) -> None:
    """Discover El Universal URLs in daily Queryly windows with per-day checkpoints."""
    if to_date < from_date:
        raise ValueError("to_date must be on or after from_date")
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    batch_size = min(100, max(1, int(batch_size)))
    workers = max(1, int(workers))
    days = date_range(from_date, to_date)
    if limit_days is not None:
        days = days[: max(0, limit_days)]

    completed = completed_checkpoint_days(checkpoint_dir) if resume else set()
    queued = [day for day in days if day.isoformat() not in completed]
    completed_in_range = sum(day.isoformat() in completed for day in days)
    print(
        f"El Universal dates: total={len(days):,}, completed={completed_in_range:,}, "
        f"queued={len(queued):,} | workers={workers:,}"
    )

    processed = 0
    new_urls = 0
    started_at = time.monotonic()
    rate_limiter = RequestRateLimiter(pause_seconds)
    executor = ThreadPoolExecutor(max_workers=workers)
    futures = set()
    iterator = iter(queued)

    def submit_next() -> bool:
        try:
            day = next(iterator)
        except StopIteration:
            return False
        futures.add(
            executor.submit(
                discover_eluniversal_day,
                day,
                checkpoint_dir=checkpoint_dir,
                batch_size=batch_size,
                max_pages=max_pages_per_day,
                timeout=timeout,
                pause_seconds=pause_seconds,
                request_retries=request_retries,
                retry_backoff_seconds=retry_backoff_seconds,
                rate_limiter=rate_limiter,
            )
        )
        return True

    try:
        for _ in range(workers):
            if not submit_next():
                break
        while futures:
            done, futures = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                day, rows, complete = future.result()
                processed += 1
                new_urls += sum(not is_blank(row.get("url")) for row in rows)
                elapsed = max(time.monotonic() - started_at, 0.001)
                rate = processed / elapsed * 60
                remaining = (len(queued) - processed) / (processed / elapsed) if processed else 0
                errors = sum(not is_blank(row.get("error")) for row in rows)
                print(
                    f"  {day.isoformat()}: rows={len(rows):,}, errors={errors:,}, "
                    f"complete={'yes' if complete else 'no'} | days={processed:,}/{len(queued):,} "
                    f"rate={rate:.1f}/min eta={format_duration(remaining)} urls={new_urls:,}"
                )
                rate_limit_error = next(
                    (
                        str(row.get("error"))
                        for row in rows
                        if str(row.get("error")) in {"http_status_403", "http_status_429"}
                    ),
                    None,
                )
                if rate_limit_error:
                    for pending in futures:
                        pending.cancel()
                    raise RuntimeError(
                        f"Queryly blocked discovery on {day.isoformat()} ({rate_limit_error}). "
                        "Wait before resuming and use a larger --pause-seconds value."
                    )
                submit_next()
    except KeyboardInterrupt:
        print("Interrupted by user; completed day checkpoints are preserved.")
        for future in futures:
            future.cancel()
    finally:
        executor.shutdown(wait=True, cancel_futures=True)

    return None


def discover_eluniversal_day(
    day: date,
    *,
    checkpoint_dir: Path,
    batch_size: int,
    max_pages: int,
    timeout: float,
    pause_seconds: float,
    request_retries: int,
    retry_backoff_seconds: float,
    rate_limiter: RequestRateLimiter | None = None,
) -> tuple[date, list[dict[str, object]], bool]:
    """Fetch and checkpoint every result page for one publication date."""
    rows: list[dict[str, object]] = []
    offset = 0
    total = None
    complete = False
    for page_number in range(1, max_pages + 1):
        if rate_limiter is not None:
            rate_limiter.wait()
        elif pause_seconds:
            time.sleep(pause_seconds)
        query_url = build_queryly_url(day, offset=offset, batch_size=batch_size)
        payload, error = fetch_queryly_payload(
            query_url,
            timeout=timeout,
            request_retries=request_retries,
            retry_backoff_seconds=retry_backoff_seconds,
        )
        if error:
            rows.append(error_row(day, query_url, page_number, error))
            break

        items = payload.get("items") if isinstance(payload, dict) else None
        metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
        if not isinstance(items, list):
            rows.append(error_row(day, query_url, page_number, "queryly_items_missing"))
            break
        try:
            total = int(metadata.get("total", len(items)))
        except (TypeError, ValueError):
            total = len(items)
        for item in items:
            row = queryly_item_row(item, day, query_url, page_number)
            if row is not None:
                rows.append(row)

        offset += len(items)
        if not items or offset >= total:
            complete = True
            break

    if not complete and total is not None and offset < total and len(rows) and not any(
        not is_blank(row.get("error")) for row in rows
    ):
        rows.append(
            error_row(
                day,
                build_queryly_url(day, offset=offset, batch_size=batch_size),
                max_pages,
                f"max_pages_exhausted:{offset}/{total}",
            )
        )

    frame = pd.DataFrame(rows, columns=DISCOVERY_COLUMNS)
    if not frame.empty and "url" in frame.columns:
        frame = frame.drop_duplicates(["source_id", "url"], keep="last")
    checkpoint_path = checkpoint_dir / f"{day.isoformat()}.csv"
    write_frame_atomic(frame, checkpoint_path)
    done_path = checkpoint_path.with_suffix(".done")
    if complete and not any(not is_blank(row.get("error")) for row in rows):
        done_path.write_text("complete\n", encoding="ascii")
    elif done_path.exists():
        done_path.unlink()
    return day, frame.to_dict("records"), complete


def fetch_queryly_payload(
    url: str,
    *,
    timeout: float,
    request_retries: int,
    retry_backoff_seconds: float,
) -> tuple[dict[str, object], str | None]:
    """Fetch a Queryly JSON response with bounded transient retries."""
    attempts = 1 + max(0, request_retries)
    last_error = "unknown_queryly_error"
    for attempt in range(1, attempts + 1):
        response = fetch(url, timeout, body_text_limit=20_000_000, profile="default")
        status = response.get("status")
        if status == 200 and response.get("text"):
            try:
                return parse_queryly_payload(str(response["text"])), None
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
        else:
            last_error = str(response.get("error")) if not is_blank(response.get("error")) else f"http_status_{status}"
        if attempt < attempts:
            time.sleep(max(0.0, retry_backoff_seconds) * attempt)
    return {}, last_error


def parse_queryly_payload(text: str) -> dict[str, object]:
    """Parse Queryly JSON or JSONP text."""
    value = text.strip().lstrip("\ufeff")
    if not value.startswith("{"):
        match = re.match(r"^[^(]+\((.*)\)\s*;?\s*$", value, flags=re.S)
        if not match:
            raise ValueError("unrecognized Queryly response")
        value = match.group(1)
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("Queryly response is not an object")
    return payload


def build_queryly_url(day: date, *, offset: int, batch_size: int) -> str:
    """Build one wildcard Queryly request for a publication day."""
    date_text = f"{day.month}/{day.day}/{day.year}"
    params = {
        "queryly_key": QUERYLY_KEY,
        "query": "*",
        "endindex": str(offset),
        "batchsize": str(min(100, max(1, batch_size))),
        "showfaceted": "false",
        "extendeddatafields": "creator,imageresizer,promo_image,subheadline",
        "timezoneoffset": "0",
        "daterange": f"{date_text},{date_text}",
        "sort": "date",
    }
    return f"{QUERYLY_URL}?{urlencode(params)}"


def queryly_item_row(
    item: object,
    day: date,
    query_url: str,
    page_number: int,
) -> dict[str, object] | None:
    """Convert one Queryly result into the shared discovery schema."""
    if not isinstance(item, dict):
        return None
    url = normalize_eluniversal_url(item.get("link"))
    if url is None or not is_eluniversal_article_url(url):
        return None
    published = normalize_queryly_date(item.get("pubdate"), day)
    segments = [part for part in urlparse(url).path.strip("/").split("/") if part]
    topic = segments[1] if segments and segments[0] == "articulo" and len(segments) > 1 else segments[0]
    return {
        "source_id": SOURCE_ID,
        "source_name": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "url": url,
        "canonical_url": url,
        "date_published": published,
        "lastmod": published,
        "topic": topic,
        "discovery_strategy": "eluniversal_queryly_daily",
        "query_date": day.isoformat(),
        "query_url": pd.NA,
        "page_number": page_number,
        "status": 200,
        "error": pd.NA,
        "discovered_at": pd.Timestamp.now("UTC").isoformat(),
    }


def normalize_eluniversal_url(value: object) -> str | None:
    """Normalize relative and absolute El Universal result links."""
    if is_blank(value):
        return None
    text = str(value).strip()
    if text.startswith("/"):
        text = f"https://www.eluniversal.com.mx{text}"
    parsed = urlparse(text)
    host = parsed.netloc.lower().split(":", 1)[0]
    if host not in {"eluniversal.com.mx", "www.eluniversal.com.mx"}:
        return None
    path = re.sub(r"/+", "/", parsed.path)
    if not path.endswith("/"):
        path += "/"
    return urlunparse(("https", "www.eluniversal.com.mx", path, "", "", ""))


def is_eluniversal_article_url(url: object) -> bool:
    """Return True for modern and legacy El Universal article paths."""
    if is_blank(url):
        return False
    segments = [part.lower() for part in urlparse(str(url)).path.strip("/").split("/") if part]
    if len(segments) < 2 or segments[0] in NON_ARTICLE_SECTIONS:
        return False
    if segments[0] == "notas":
        return len(segments) == 2 and bool(re.fullmatch(r"\d+\.html", segments[1]))
    if segments[0] == "articulo":
        return len(segments) >= 6 and bool(re.fullmatch(r"20\d{2}", segments[-4]))
    return len(segments[-1].split("-")) >= 3


def normalize_queryly_date(value: object, fallback: date) -> str:
    """Normalize Queryly's English display date to ISO form."""
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    return fallback.isoformat() if pd.isna(parsed) else parsed.date().isoformat()


def error_row(day: date, query_url: str, page_number: int, error: str) -> dict[str, object]:
    status_match = re.fullmatch(r"http_status_(\d{3})", error)
    return {
        "source_id": SOURCE_ID,
        "source_name": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "url": pd.NA,
        "canonical_url": pd.NA,
        "date_published": day.isoformat(),
        "lastmod": day.isoformat(),
        "topic": pd.NA,
        "discovery_strategy": "eluniversal_queryly_daily",
        "query_date": day.isoformat(),
        "query_url": query_url,
        "page_number": page_number,
        "status": int(status_match.group(1)) if status_match else pd.NA,
        "error": error,
        "discovered_at": pd.Timestamp.now("UTC").isoformat(),
    }


def date_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def completed_checkpoint_days(checkpoint_dir: Path) -> set[str]:
    return {path.stem for path in checkpoint_dir.glob("*.done") if path.with_suffix(".csv").exists()}


def combine_eluniversal_checkpoints(checkpoint_dir: Path) -> pd.DataFrame:
    frames = []
    for path in sorted(checkpoint_dir.glob("*.csv")):
        try:
            frames.append(pd.read_csv(path, low_memory=False))
        except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
            print(f"  ignored unreadable checkpoint {path.name}: {type(exc).__name__}: {exc}")
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    article_rows = combined[combined["url"].notna()].drop_duplicates(["source_id", "url"], keep="last")
    error_rows = combined[combined["url"].isna()]
    return pd.concat([article_rows, error_rows], ignore_index=True)


def write_frame_atomic(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_name(f"{path.stem}.tmp-{os.getpid()}-{time.time_ns()}{path.suffix}")
    frame.to_csv(temporary, index=False, encoding="utf-8")
    last_error = None
    for attempt in range(1, 11):
        try:
            os.replace(temporary, path)
            return
        except PermissionError as exc:
            last_error = exc
            if attempt < 10:
                time.sleep(min(5.0, attempt * 0.25))
    raise OSError(f"Could not save checkpoint {path}; recovery file: {temporary}") from last_error


def build_eluniversal_report(discovered: pd.DataFrame) -> str:
    lines = ["# El Universal Discovery Report", ""]
    if discovered.empty:
        return "\n".join(lines + ["_No rows._", ""])
    articles = discovered[discovered["url"].notna()].copy()
    errors = discovered[discovered["error"].notna()]
    articles["year"] = pd.to_datetime(articles["date_published"], errors="coerce").dt.year
    lines.extend(
        [
            f"- Rows: {len(discovered):,}",
            f"- Unique article URLs: {articles['url'].nunique():,}",
            f"- Error rows: {len(errors):,}",
            f"- Earliest date: {articles['date_published'].min() if not articles.empty else '<none>'}",
            f"- Latest date: {articles['date_published'].max() if not articles.empty else '<none>'}",
            "",
            "## Articles By Year",
            "",
            markdown_table(articles.groupby("year", dropna=False).size().reset_index(name="articles")),
            "",
            "## Articles By Topic",
            "",
            markdown_table(articles.groupby("topic", dropna=False).size().reset_index(name="articles").sort_values("articles", ascending=False).head(40)),
            "",
        ]
    )
    return "\n".join(lines)


def write_eluniversal_outputs(
    discovered: pd.DataFrame,
    discovery_dir: Path,
    reports_dir: Path,
) -> ElUniversalOutputs:
    discovery_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    csv_path = discovery_dir / "discovered_urls_eluniversal.csv"
    parquet_path = discovery_dir / "discovered_urls_eluniversal.parquet"
    report_path = reports_dir / "eluniversal_discovery_report.md"
    discovered.to_csv(csv_path, index=False, encoding="utf-8")
    parquet_error = None
    try:
        discovered.to_parquet(parquet_path, index=False)
    except Exception as exc:
        parquet_error = f"{type(exc).__name__}: {exc}"
        parquet_path = None
    report_path.write_text(build_eluniversal_report(discovered), encoding="utf-8")
    return ElUniversalOutputs(csv_path, parquet_path, report_path, parquet_error)


def finalize_eluniversal_checkpoints(
    checkpoint_dir: Path,
    discovery_dir: Path,
    reports_dir: Path,
) -> tuple[ElUniversalOutputs, ElUniversalSummary]:
    """Stream daily checkpoints into final CSV/Parquet outputs with bounded memory."""
    discovery_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    csv_path = discovery_dir / "discovered_urls_eluniversal.csv"
    temporary_csv = csv_path.with_name(f"{csv_path.stem}.tmp-{os.getpid()}.csv")
    rows = 0
    urls = 0
    errors = 0
    duplicates_skipped = 0
    seen_url_hashes: set[bytes] = set()
    by_year: Counter[str] = Counter()
    by_topic: Counter[str] = Counter()
    earliest = None
    latest = None

    with temporary_csv.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=DISCOVERY_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for path in sorted(checkpoint_dir.glob("*.csv")):
            try:
                with path.open("r", newline="", encoding="utf-8-sig") as source:
                    reader = csv.DictReader(source)
                    for row in reader:
                        url = row.get("url", "").strip()
                        if url:
                            url_hash = hashlib.blake2b(url.encode("utf-8"), digest_size=16).digest()
                            if url_hash in seen_url_hashes:
                                duplicates_skipped += 1
                                continue
                            seen_url_hashes.add(url_hash)
                        writer.writerow({column: row.get(column, "") for column in DISCOVERY_COLUMNS})
                        rows += 1
                        if url:
                            urls += 1
                            published = row.get("date_published", "").strip()
                            if published:
                                year = published[:4]
                                by_year[year] += 1
                                earliest = published if earliest is None or published < earliest else earliest
                                latest = published if latest is None or published > latest else latest
                            by_topic[row.get("topic", "").strip() or "<missing>"] += 1
                        if row.get("error", "").strip():
                            errors += 1
            except (OSError, csv.Error) as exc:
                print(f"  ignored unreadable checkpoint {path.name}: {type(exc).__name__}: {exc}")
    replace_with_retries(temporary_csv, csv_path)

    parquet_path = discovery_dir / "discovered_urls_eluniversal.parquet"
    temporary_parquet = parquet_path.with_name(f"{parquet_path.stem}.tmp-{os.getpid()}.parquet")
    parquet_error = None
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq

        writer = None
        try:
            for chunk in pd.read_csv(
                csv_path,
                dtype=str,
                keep_default_na=False,
                chunksize=100_000,
            ):
                table = pa.Table.from_pandas(chunk, preserve_index=False)
                if writer is None:
                    writer = pq.ParquetWriter(temporary_parquet, table.schema, compression="gzip")
                writer.write_table(table)
        finally:
            if writer is not None:
                writer.close()
        if writer is not None:
            replace_with_retries(temporary_parquet, parquet_path)
        elif parquet_path.exists():
            parquet_path.unlink()
    except Exception as exc:
        parquet_error = f"{type(exc).__name__}: {exc}"
        if temporary_parquet.exists():
            temporary_parquet.unlink()
        parquet_path = None

    report_path = reports_dir / "eluniversal_discovery_report.md"
    report_path.write_text(
        build_eluniversal_stream_report(
            rows=rows,
            urls=urls,
            errors=errors,
            duplicates_skipped=duplicates_skipped,
            earliest=earliest,
            latest=latest,
            by_year=by_year,
            by_topic=by_topic,
        ),
        encoding="utf-8",
    )
    return (
        ElUniversalOutputs(csv_path, parquet_path, report_path, parquet_error),
        ElUniversalSummary(rows, urls, errors, duplicates_skipped),
    )


def build_eluniversal_stream_report(
    *,
    rows: int,
    urls: int,
    errors: int,
    duplicates_skipped: int,
    earliest: str | None,
    latest: str | None,
    by_year: Counter[str],
    by_topic: Counter[str],
) -> str:
    year_frame = pd.DataFrame(sorted(by_year.items()), columns=["year", "articles"])
    topic_frame = pd.DataFrame(by_topic.most_common(40), columns=["topic", "articles"])
    return "\n".join(
        [
            "# El Universal Discovery Report",
            "",
            f"- Rows: {rows:,}",
            f"- Article URLs: {urls:,}",
            f"- Duplicate URL rows skipped: {duplicates_skipped:,}",
            f"- Error rows: {errors:,}",
            f"- Earliest date: {earliest or '<none>'}",
            f"- Latest date: {latest or '<none>'}",
            "",
            "## Articles By Year",
            "",
            markdown_table(year_frame),
            "",
            "## Articles By Topic",
            "",
            markdown_table(topic_frame),
            "",
        ]
    )


def replace_with_retries(temporary: Path, target: Path) -> None:
    last_error = None
    for attempt in range(1, 11):
        try:
            os.replace(temporary, target)
            return
        except PermissionError as exc:
            last_error = exc
            if attempt < 10:
                time.sleep(min(5.0, attempt * 0.25))
    raise OSError(f"Could not replace {target}; recovery file: {temporary}") from last_error


def is_blank(value: object) -> bool:
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return value is None or str(value).strip() == ""


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"

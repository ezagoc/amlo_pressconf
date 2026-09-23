"""Historical sitemap discovery for Aristegui Noticias."""

from __future__ import annotations

import os
import re
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pandas as pd

if not hasattr(pd, "NA"):
    pd.NA = None

from crawler_core.capabilities import fetch, markdown_table
from crawler_core.sitemaps import parse_sitemap_xml


SOURCE_ID = "aristeguinoticias"
SOURCE_NAME = "Aristegui Noticias"
PUBLIC_BASE_URL = "https://aristeguinoticias.com/"
EDITORIAL_HOST = "editorial.aristeguinoticias.com"
SITEMAP_INDEX_URL = f"https://{EDITORIAL_HOST}/sitemap.xml"
POST_SITEMAP_RE = re.compile(r"/post-sitemap(?P<number>\d*)\.xml$", flags=re.I)
DAY_MONTH_RE = re.compile(r"^\d{4}$")


@dataclass(frozen=True)
class AristeguiDiscoveryOutputs:
    """Paths written by Aristegui discovery."""

    discovered_csv: Path
    discovered_parquet: Path | None
    report_path: Path
    parquet_error: str | None = None


def discover_aristegui_urls(
    *,
    max_sitemaps: int | None = None,
    max_urls: int | None = None,
    timeout: float = 30.0,
    pause_seconds: float = 0.05,
    workers: int = 2,
    retries: int = 3,
    heartbeat_seconds: float = 15.0,
    checkpoint_path: Path | None = None,
    checkpoint_every: int = 5_000,
    resume: bool = False,
) -> pd.DataFrame:
    """Discover Aristegui articles from the hidden editorial sitemap index."""
    index_response = fetch(
        SITEMAP_INDEX_URL,
        timeout,
        body_text_limit=5_000_000,
        profile="browser",
    )
    if not is_ok(index_response.get("status")):
        raise RuntimeError(f"Aristegui sitemap index failed: {response_error(index_response)}")
    parsed_index = parse_sitemap_xml(str(index_response.get("text") or ""))
    if parsed_index.get("error"):
        raise RuntimeError(f"Aristegui sitemap index parse failed: {parsed_index['error']}")

    sitemap_urls = [
        str(url)
        for url in parsed_index.get("sitemaps", [])
        if POST_SITEMAP_RE.search(str(urlparse(str(url)).path))
    ]
    sitemap_urls.sort(key=sitemap_sort_key)
    if max_sitemaps is not None:
        sitemap_urls = sitemap_urls[:max_sitemaps]
    print(f"Aristegui post sitemaps selected: {len(sitemap_urls):,}")

    existing = load_checkpoint(checkpoint_path) if resume else pd.DataFrame()
    processed_sitemaps = successful_checkpoint_sitemaps(existing)
    if not existing.empty and "sitemap_url" in existing.columns:
        retry_mask = existing["sitemap_url"].notna() & ~existing["sitemap_url"].astype(str).isin(
            processed_sitemaps
        )
        existing = existing[~retry_mask].copy()
    rows = existing.to_dict(orient="records") if not existing.empty else []
    seen_urls = set(existing["url"].dropna().astype(str)) if "url" in existing.columns else set()
    queued = [url for url in sitemap_urls if url not in processed_sitemaps]
    if existing.empty:
        print("Resume state: no checkpoint rows loaded")
    else:
        print(
            f"Resume state: loaded {len(existing):,} rows, "
            f"{len(seen_urls):,} URLs, {len(processed_sitemaps):,} completed sitemaps"
        )
    print(f"Aristegui sitemaps queued: {len(queued):,} | workers={max(1, workers):,}")

    last_checkpoint_count = len(rows)
    completed = 0
    worker_count = max(1, workers)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        queued_iter = iter(queued)
        pending = {}

        def submit_next() -> bool:
            try:
                next_url = next(queued_iter)
            except StopIteration:
                return False
            future = executor.submit(fetch_aristegui_sitemap, next_url, timeout, retries)
            pending[future] = (next_url, time.monotonic())
            return True

        for _ in range(min(worker_count, len(queued))):
            submit_next()

        stop_requested = False
        while pending:
            done, _ = wait(
                pending,
                timeout=max(1.0, heartbeat_seconds),
                return_when=FIRST_COMPLETED,
            )
            if not done:
                elapsed = max(time.monotonic() - started for _, started in pending.values())
                active_names = ", ".join(
                    Path(urlparse(url).path).name for url, _ in list(pending.values())[:worker_count]
                )
                print(
                    f"  heartbeat: completed={completed:,}/{len(queued):,}, "
                    f"in_flight={len(pending):,}, slowest={elapsed:.0f}s [{active_names}]"
                )
                continue

            for future in done:
                sitemap_url, _ = pending.pop(future)
                completed += 1
                try:
                    sitemap_rows = future.result()
                except Exception as exc:
                    sitemap_rows = [error_row(sitemap_url, pd.NA, f"{type(exc).__name__}: {exc}")]

                new_count = 0
                for row in sitemap_rows:
                    url = row.get("url")
                    if is_missing(url):
                        rows.append(row)
                        continue
                    url_text = str(url)
                    if url_text in seen_urls:
                        continue
                    seen_urls.add(url_text)
                    rows.append(row)
                    new_count += 1
                    if max_urls is not None and len(seen_urls) >= max_urls:
                        break

                error_values = [
                    str(row.get("error"))
                    for row in sitemap_rows
                    if not is_missing(row.get("error"))
                ]
                error_suffix = f", error={error_values[0]}" if error_values else ""
                print(
                    f"  aristegui sitemap {completed:,}/{len(queued):,}: "
                    f"articles={sum(not is_missing(row.get('url')) for row in sitemap_rows):,}, "
                    f"new={new_count:,}, total={len(seen_urls):,}{error_suffix}"
                )
                if (
                    checkpoint_path is not None
                    and checkpoint_every > 0
                    and len(rows) - last_checkpoint_count >= checkpoint_every
                ):
                    write_checkpoint(rows, checkpoint_path)
                    last_checkpoint_count = len(rows)
                if max_urls is not None and len(seen_urls) >= max_urls:
                    stop_requested = True
                    print(f"Reached max_urls={max_urls:,}; stopping discovery")
                    break
                if pause_seconds:
                    time.sleep(pause_seconds)
                submit_next()

            if stop_requested:
                for pending_future in pending:
                    pending_future.cancel()
                break

    discovered = finalize_discovery(pd.DataFrame(rows), max_urls=max_urls)
    if checkpoint_path is not None:
        write_checkpoint(discovered.to_dict(orient="records"), checkpoint_path)
    return discovered


def fetch_aristegui_sitemap(
    sitemap_url: str,
    timeout: float,
    retries: int = 3,
) -> list[dict[str, object]]:
    """Fetch one post sitemap and return public article URL rows."""
    final_status = pd.NA
    final_error = "no_article_urls_found"
    for attempt in range(1, max(1, retries) + 1):
        response = fetch(
            sitemap_url,
            timeout,
            body_text_limit=15_000_000,
            profile="browser",
        )
        status = response.get("status")
        final_status = status
        if not is_ok(status):
            final_error = response_error(response)
        else:
            parsed = parse_sitemap_xml(str(response.get("text") or ""))
            if parsed.get("error"):
                final_error = parsed["error"]
            else:
                rows = []
                for item in parsed.get("urls", []):
                    backend_url = item.get("loc")
                    if not is_aristegui_article_url(backend_url):
                        continue
                    public_url = public_article_url(str(backend_url))
                    rows.append(url_row(public_url, backend_url, item, sitemap_url, status))
                if rows:
                    return rows
                final_error = "no_article_urls_found"
        if attempt < max(1, retries):
            print(
                f"  retry {attempt}/{max(1, retries) - 1}: "
                f"{Path(urlparse(sitemap_url).path).name} ({final_error})"
            )
            time.sleep(min(5.0, float(attempt)))
    return [error_row(sitemap_url, final_status, final_error)]


def is_aristegui_article_url(url: object) -> bool:
    """Return True for Aristegui's /DDMM/section/slug/ article paths."""
    if is_missing(url):
        return False
    parsed = urlparse(str(url))
    segments = [segment for segment in parsed.path.strip("/").split("/") if segment]
    if parsed.netloc.lower().removeprefix("www.") != EDITORIAL_HOST:
        return False
    if len(segments) < 3 or not DAY_MONTH_RE.fullmatch(segments[0]):
        return False
    lowered = str(url).lower()
    return not lowered.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".mp4"))


def public_article_url(url: str) -> str:
    """Replace the protected editorial host with the public frontend host."""
    parsed = urlparse(url)
    return urlunparse(("https", "aristeguinoticias.com", parsed.path, "", "", ""))


def sitemap_sort_key(url: str) -> int:
    """Order post-sitemap.xml before post-sitemap2.xml, etc."""
    match = POST_SITEMAP_RE.search(urlparse(url).path)
    if not match:
        return 10**9
    number = match.group("number")
    return int(number) if number else 1


def url_row(
    public_url: str,
    backend_url: object,
    item: dict[str, object],
    sitemap_url: str,
    status: object,
) -> dict[str, object]:
    segments = [segment for segment in urlparse(public_url).path.strip("/").split("/") if segment]
    return {
        "source_id": SOURCE_ID,
        "source_name": SOURCE_NAME,
        "source_url": PUBLIC_BASE_URL.rstrip("/"),
        "url": public_url,
        "canonical_url": public_url,
        "backend_url": backend_url,
        "date_published": pd.NA,
        "lastmod": item.get("lastmod"),
        "topic": segments[1] if len(segments) > 1 else pd.NA,
        "discovery_strategy": "aristegui_editorial_sitemap",
        "sitemap_url": sitemap_url,
        "sitemap_status": status,
        "discovered_at": pd.Timestamp.utcnow().isoformat(),
        "status": status,
        "error": pd.NA,
    }


def error_row(sitemap_url: object, status: object, error: object) -> dict[str, object]:
    return {
        "source_id": SOURCE_ID,
        "source_name": SOURCE_NAME,
        "source_url": PUBLIC_BASE_URL.rstrip("/"),
        "url": pd.NA,
        "canonical_url": pd.NA,
        "backend_url": pd.NA,
        "date_published": pd.NA,
        "lastmod": pd.NA,
        "topic": pd.NA,
        "discovery_strategy": "aristegui_editorial_sitemap",
        "sitemap_url": sitemap_url,
        "sitemap_status": status,
        "discovered_at": pd.Timestamp.utcnow().isoformat(),
        "status": status,
        "error": error,
    }


def finalize_discovery(discovered: pd.DataFrame, *, max_urls: int | None) -> pd.DataFrame:
    if discovered.empty:
        return discovered
    urls = discovered[discovered["url"].notna()].drop_duplicates("url", keep="last")
    if max_urls is not None:
        urls = urls.head(max_urls)
    errors = discovered[discovered["url"].isna()].drop_duplicates(
        ["sitemap_url", "error"], keep="last"
    )
    return pd.concat([urls, errors], ignore_index=True)


def load_checkpoint(path: Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    candidates = []
    if path.exists():
        candidates.append(path)
    candidates.extend(
        candidate
        for candidate in path.parent.glob(f"{path.stem}.tmp*{path.suffix}")
        if candidate not in candidates
    )
    valid = []
    for candidate in candidates:
        try:
            frame = pd.read_csv(candidate, low_memory=False)
        except (OSError, pd.errors.ParserError, UnicodeDecodeError) as exc:
            print(f"  checkpoint: ignored unreadable {candidate.name}: {type(exc).__name__}: {exc}")
            continue
        url_count = int(frame["url"].notna().sum()) if "url" in frame.columns else 0
        valid.append((url_count, len(frame), candidate.stat().st_mtime_ns, candidate, frame))
    if not valid:
        return pd.DataFrame()
    _, _, _, selected_path, selected = max(valid, key=lambda item: item[:3])
    if selected_path != path:
        print(
            f"  checkpoint: recovered newer temporary file {selected_path.name} "
            f"with {len(selected):,} rows"
        )
    return selected


def successful_checkpoint_sitemaps(existing: pd.DataFrame) -> set[str]:
    """Treat article-bearing and confirmed-empty post sitemaps as completed."""
    if existing.empty or "sitemap_url" not in existing.columns or "url" not in existing.columns:
        return set()
    successes = existing.loc[existing["url"].notna(), "sitemap_url"].dropna().astype(str)
    completed = set(successes)
    if "error" in existing.columns:
        empty_mask = existing["error"].astype(str).eq("no_article_urls_found")
        completed.update(existing.loc[empty_mask, "sitemap_url"].dropna().astype(str))
    return completed


def write_checkpoint(rows: list[dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = finalize_discovery(pd.DataFrame(rows), max_urls=None)
    temporary = path.with_name(
        f"{path.stem}.tmp-{os.getpid()}-{time.time_ns()}{path.suffix}"
    )
    frame.to_csv(temporary, index=False, encoding="utf-8")
    last_error = None
    for attempt in range(1, 11):
        try:
            os.replace(temporary, path)
            print(f"  checkpoint: wrote {len(frame):,} rows to {path}")
            remove_stale_checkpoint_temps(path)
            return
        except PermissionError as exc:
            last_error = exc
            if attempt < 10:
                delay = min(5.0, 0.25 * attempt)
                print(
                    f"  checkpoint: Dropbox lock, retrying replace "
                    f"{attempt}/10 in {delay:.2f}s"
                )
                time.sleep(delay)
        except OSError as exc:
            last_error = exc
            break
    print(
        f"  checkpoint warning: could not replace {path.name}; "
        f"kept complete recovery file {temporary.name} ({type(last_error).__name__}: {last_error})"
    )


def remove_stale_checkpoint_temps(path: Path) -> None:
    """Best-effort cleanup after a successful checkpoint replacement."""
    for candidate in path.parent.glob(f"{path.stem}.tmp*{path.suffix}"):
        try:
            candidate.unlink()
        except OSError:
            continue


def build_aristegui_report(discovered: pd.DataFrame) -> str:
    urls = discovered[discovered["url"].notna()].copy() if not discovered.empty else pd.DataFrame()
    errors = int(discovered["error"].notna().sum()) if "error" in discovered else 0
    lines = [
        "# Aristegui Noticias Discovery Report",
        "",
        f"- Rows: {len(discovered):,}",
        f"- Unique article URLs: {urls['url'].nunique() if not urls.empty else 0:,}",
        f"- Post sitemaps represented: {urls['sitemap_url'].nunique() if not urls.empty else 0:,}",
        f"- Error rows: {errors:,}",
        "- Source: hidden editorial WordPress sitemap, canonicalized to the public frontend",
        "",
    ]
    if not urls.empty:
        dates = pd.to_datetime(urls["lastmod"], errors="coerce", utc=True)
        lines.extend(
            [
                f"- Earliest sitemap lastmod: {dates.min()}",
                f"- Latest sitemap lastmod: {dates.max()}",
                "",
                "## URLs By Lastmod Year",
                "",
            ]
        )
        yearly = (
            dates.dt.year.value_counts(dropna=False).rename_axis("year").reset_index(name="urls")
        )
        yearly = yearly.sort_values("year")
        lines.extend([markdown_table(yearly), ""])
    return "\n".join(lines)


def write_aristegui_outputs(
    discovered: pd.DataFrame,
    report: str,
    discovery_dir: Path,
    reports_dir: Path,
) -> AristeguiDiscoveryOutputs:
    discovery_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    csv_path = discovery_dir / "discovered_urls_aristeguinoticias.csv"
    parquet_path = discovery_dir / "discovered_urls_aristeguinoticias.parquet"
    report_path = reports_dir / "aristeguinoticias_discovery_report.md"
    discovered.to_csv(csv_path, index=False, encoding="utf-8")
    parquet_error = None
    try:
        discovered.to_parquet(parquet_path, index=False)
    except Exception as exc:
        parquet_error = f"{type(exc).__name__}: {exc}"
        parquet_path = None
    report_path.write_text(report, encoding="utf-8")
    return AristeguiDiscoveryOutputs(csv_path, parquet_path, report_path, parquet_error)


def is_ok(status: object) -> bool:
    return isinstance(status, int) and 200 <= status < 300


def response_error(response: dict[str, object]) -> object:
    error = response.get("error")
    if not is_missing(error) and str(error).strip():
        return error
    return f"http_status_{response.get('status')}"


def is_missing(value: object) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return value is None

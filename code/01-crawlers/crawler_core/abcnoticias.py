"""Historical sitemap discovery and fetching for ABC Noticias."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

import pandas as pd

if not hasattr(pd, "NA"):
    pd.NA = None

from crawler_core.capabilities import BROWSER_USER_AGENT, fetch, markdown_table
from crawler_core.sitemaps import parse_sitemap_xml


SOURCE_ID = "abcnoticias"
SOURCE_NAME = "ABC"
BASE_URL = "https://abcnoticias.mx/"
SITEMAP_INDEX_URL = "https://abcnoticias.mx/sitemaps/index.xml"
ARTICLE_SITEMAP_RE = re.compile(r"/sitemaps/articles/(?P<year>\d{4})-(?P<month>\d{2})\.xml$")
ARTICLE_PATH_RE = re.compile(
    r"^/(?P<topic>[^/]+)/(?P<year>\d{4})/(?P<month>\d{1,2})/"
    r"(?P<day>\d{1,2})/[^/]+-(?P<article_id>\d+)\.html/?$",
    flags=re.I,
)
TLS_ERROR_MARKERS = (
    "acquirecredentialshandle",
    "certificate",
    "schannel",
    "ssl",
    "tls",
)


@dataclass(frozen=True)
class AbcNoticiasDiscoveryOutputs:
    """Files produced by ABC Noticias discovery."""

    discovered_csv: Path
    discovered_parquet: Path | None
    report_path: Path
    parquet_error: str | None = None


def discover_abcnoticias_urls(
    *,
    from_year: int | None = None,
    to_year: int | None = None,
    max_sitemaps: int | None = None,
    max_urls: int | None = None,
    timeout: float = 60.0,
    pause_seconds: float = 0.05,
    workers: int = 4,
    retries: int = 3,
    checkpoint_dir: Path | None = None,
    resume: bool = False,
) -> pd.DataFrame:
    """Discover ABC Noticias article URLs from monthly sitemaps."""
    index_response = fetch_abc(
        SITEMAP_INDEX_URL,
        timeout,
        body_text_limit=5_000_000,
        profile="browser",
    )
    if not is_ok(index_response.get("status")):
        raise RuntimeError(f"ABC Noticias sitemap index failed: {response_error(index_response)}")
    parsed = parse_sitemap_xml(str(index_response.get("text") or ""))
    if parsed.get("error"):
        raise RuntimeError(f"ABC Noticias sitemap index parse failed: {parsed['error']}")

    sitemap_urls = []
    for value in parsed.get("sitemaps", []):
        url = str(value)
        match = ARTICLE_SITEMAP_RE.search(urlparse(url).path)
        if not match:
            continue
        year = int(match.group("year"))
        if from_year is not None and year < from_year:
            continue
        if to_year is not None and year > to_year:
            continue
        sitemap_urls.append(url)
    sitemap_urls.sort(key=sitemap_sort_key)
    if max_sitemaps is not None:
        sitemap_urls = sitemap_urls[:max_sitemaps]
    print(f"ABC Noticias monthly article sitemaps selected: {len(sitemap_urls):,}")

    frames: list[pd.DataFrame] = []
    queued = []
    if checkpoint_dir is not None:
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
    for sitemap_url in sitemap_urls:
        checkpoint_path = sitemap_checkpoint_path(checkpoint_dir, sitemap_url)
        if resume and checkpoint_path is not None and checkpoint_path.exists():
            checkpoint = load_completed_checkpoint(checkpoint_path)
            if checkpoint is not None:
                frames.append(checkpoint)
                continue
        queued.append(sitemap_url)

    reused = len(sitemap_urls) - len(queued)
    print(f"Resume state: reused={reused:,}, queued={len(queued):,} | workers={max(1, workers):,}")
    completed = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(
                fetch_abc_sitemap,
                sitemap_url,
                timeout=timeout,
                pause_seconds=pause_seconds,
                retries=retries,
            ): sitemap_url
            for sitemap_url in queued
        }
        for future in as_completed(futures):
            sitemap_url = futures[future]
            completed += 1
            try:
                frame = future.result()
            except Exception as exc:
                frame = pd.DataFrame(
                    [error_row(sitemap_url, pd.NA, f"{type(exc).__name__}: {exc}")]
                )
            errors = int(frame["error"].notna().sum()) if "error" in frame else 0
            urls = int(frame["url"].notna().sum()) if "url" in frame else 0
            print(
                f"  abc sitemap {completed:,}/{len(queued):,}: "
                f"{Path(urlparse(sitemap_url).path).name} urls={urls:,}, errors={errors:,}"
            )
            checkpoint_path = sitemap_checkpoint_path(checkpoint_dir, sitemap_url)
            if checkpoint_path is not None and errors == 0:
                write_checkpoint(frame, checkpoint_path)
            frames.append(frame)

    if not frames:
        return pd.DataFrame()
    discovered = pd.concat(frames, ignore_index=True)
    url_rows = discovered[discovered["url"].notna()].drop_duplicates("url", keep="last")
    if max_urls is not None:
        url_rows = url_rows.head(max_urls)
    error_rows = discovered[discovered["url"].isna()].drop_duplicates(
        ["sitemap_url", "error"], keep="last"
    )
    return pd.concat([url_rows, error_rows], ignore_index=True)


def fetch_abc_sitemap(
    sitemap_url: str,
    *,
    timeout: float,
    pause_seconds: float = 0.0,
    retries: int = 3,
) -> pd.DataFrame:
    """Fetch and parse one monthly ABC Noticias article sitemap."""
    last_status: object = pd.NA
    last_error: object = "no_article_urls_found"
    for attempt in range(1, max(1, retries) + 1):
        if pause_seconds:
            time.sleep(pause_seconds)
        response = fetch_abc(
            sitemap_url,
            timeout,
            body_text_limit=25_000_000,
            profile="browser",
        )
        last_status = response.get("status")
        if is_ok(last_status):
            parsed = parse_sitemap_xml(str(response.get("text") or ""))
            if not parsed.get("error"):
                rows = [
                    url_row(item, sitemap_url, last_status)
                    for item in parsed.get("urls", [])
                    if is_abc_article_url(item.get("loc"))
                ]
                if rows:
                    return pd.DataFrame(rows)
                last_error = "no_article_urls_found"
            else:
                last_error = parsed["error"]
        else:
            last_error = response_error(response)
        if attempt < max(1, retries):
            time.sleep(min(5.0, float(attempt)))
    return pd.DataFrame([error_row(sitemap_url, last_status, last_error)])


def fetch_abc(
    url: str,
    timeout: float,
    body_text_limit: int = 12_000_000,
    *,
    profile: str = "browser",
) -> dict[str, object]:
    """Fetch ABC normally, with a verified Node TLS fallback for Schannel failures."""
    response = fetch(
        url,
        timeout,
        body_text_limit=body_text_limit,
        profile=profile,
    )
    if is_ok(response.get("status")) or not is_tls_error(response.get("error")):
        return response
    fallback = fetch_abc_with_node(url, timeout, body_text_limit=body_text_limit)
    if is_ok(fallback.get("status")):
        return fallback
    return response


def fetch_abc_with_node(
    url: str,
    timeout: float,
    *,
    body_text_limit: int,
) -> dict[str, object]:
    """Use Node's system CA store when Windows curl cannot initialize Schannel."""
    script = r"""
const fs = require('fs');
const [url, outputPath, limitText, userAgent] = process.argv.slice(1);
(async () => {
  const response = await fetch(url, {
    redirect: 'follow',
    headers: {
      'user-agent': userAgent,
      'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
      'accept-language': 'es-MX,es;q=0.9,en-US;q=0.7,en;q=0.6'
    }
  });
  const body = Buffer.from(await response.arrayBuffer()).subarray(0, Number(limitText));
  fs.writeFileSync(outputPath, body);
  process.stdout.write(JSON.stringify({
    status: response.status,
    finalUrl: response.url,
    contentType: response.headers.get('content-type') || ''
  }));
})().catch(error => {
  process.stderr.write(String(error && error.stack ? error.stack : error));
  process.exit(1);
});
"""
    with TemporaryDirectory() as temporary:
        body_path = Path(temporary) / "body.bin"
        try:
            completed = subprocess.run(
                [
                    "node",
                    "--use-system-ca",
                    "-e",
                    script,
                    url,
                    str(body_path),
                    str(body_text_limit),
                    BROWSER_USER_AGENT,
                ],
                capture_output=True,
                text=True,
                timeout=timeout + 5,
                env=os.environ.copy(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return fetch_error(f"node_fetch: {type(exc).__name__}: {exc}")
        if completed.returncode != 0:
            return fetch_error(f"node_fetch: {completed.stderr.strip() or completed.returncode}")
        try:
            metadata = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            return fetch_error(f"node_fetch_json: {exc}")
        text = body_path.read_bytes().decode("utf-8", errors="replace") if body_path.exists() else ""
        return {
            "status": int(metadata["status"]),
            "final_url": metadata.get("finalUrl") or url,
            "content_type": metadata.get("contentType") or pd.NA,
            "text": text,
            "error": pd.NA,
        }


def fetch_error(error: str) -> dict[str, object]:
    return {
        "status": pd.NA,
        "final_url": pd.NA,
        "content_type": pd.NA,
        "text": "",
        "error": error,
    }


def is_abc_article_url(url: object) -> bool:
    if is_missing(url):
        return False
    parsed = urlparse(str(url))
    if parsed.netloc.lower().removeprefix("www.") != "abcnoticias.mx":
        return False
    return bool(ARTICLE_PATH_RE.fullmatch(parsed.path))


def url_row(item: dict[str, object], sitemap_url: str, status: object) -> dict[str, object]:
    url = str(item["loc"])
    match = ARTICLE_PATH_RE.fullmatch(urlparse(url).path)
    assert match is not None
    date_published = (
        f"{int(match.group('year')):04d}-{int(match.group('month')):02d}-"
        f"{int(match.group('day')):02d}"
    )
    return {
        "source_id": SOURCE_ID,
        "source_name": SOURCE_NAME,
        "source_url": BASE_URL.rstrip("/"),
        "url": url,
        "canonical_url": url,
        "date_published": date_published,
        "lastmod": item.get("lastmod"),
        "topic": match.group("topic").lower(),
        "article_id": match.group("article_id"),
        "discovery_strategy": "abcnoticias_monthly_sitemap",
        "sitemap_url": sitemap_url,
        "sitemap_status": status,
        "changefreq": item.get("changefreq"),
        "priority": item.get("priority"),
        "discovered_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "status": status,
        "error": pd.NA,
    }


def error_row(sitemap_url: object, status: object, error: object) -> dict[str, object]:
    row = {key: pd.NA for key in (
        "url", "canonical_url", "date_published", "lastmod", "topic", "article_id",
        "changefreq", "priority",
    )}
    row.update(
        {
            "source_id": SOURCE_ID,
            "source_name": SOURCE_NAME,
            "source_url": BASE_URL.rstrip("/"),
            "discovery_strategy": "abcnoticias_monthly_sitemap",
            "sitemap_url": sitemap_url,
            "sitemap_status": status,
            "discovered_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "status": status,
            "error": error,
        }
    )
    return row


def sitemap_sort_key(url: str) -> tuple[int, int]:
    match = ARTICLE_SITEMAP_RE.search(urlparse(url).path)
    if not match:
        return (9999, 99)
    return (int(match.group("year")), int(match.group("month")))


def sitemap_checkpoint_path(checkpoint_dir: Path | None, sitemap_url: str) -> Path | None:
    if checkpoint_dir is None:
        return None
    return checkpoint_dir / Path(urlparse(sitemap_url).path).name.replace(".xml", ".csv")


def load_completed_checkpoint(path: Path) -> pd.DataFrame | None:
    try:
        frame = pd.read_csv(path, low_memory=False)
    except (OSError, pd.errors.ParserError, UnicodeDecodeError):
        return None
    if frame.empty or "url" not in frame or not frame["url"].notna().any():
        return None
    if "error" in frame and frame["error"].notna().any():
        return None
    return frame


def write_checkpoint(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8")
    for attempt in range(1, 11):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 10:
                raise
            time.sleep(min(5.0, attempt * 0.25))


def build_abcnoticias_report(discovered: pd.DataFrame) -> str:
    urls = discovered[discovered["url"].notna()].copy() if not discovered.empty else pd.DataFrame()
    errors = int(discovered["error"].notna().sum()) if "error" in discovered else 0
    lines = [
        "# ABC Noticias Discovery Report",
        "",
        f"- Rows: {len(discovered):,}",
        f"- Unique article URLs: {urls['url'].nunique() if not urls.empty else 0:,}",
        f"- Monthly sitemaps represented: {urls['sitemap_url'].nunique() if not urls.empty else 0:,}",
        f"- Error rows: {errors:,}",
        "- Source: official monthly article sitemaps",
        "",
        "## Articles By Year",
        "",
    ]
    if urls.empty:
        lines.append("_No article URLs._")
    else:
        years = (
            urls["date_published"].astype(str).str[:4].value_counts().sort_index()
            .rename_axis("year").reset_index(name="articles")
        )
        lines.append(markdown_table(years))
        lines.extend(["", "## Articles By Topic", ""])
        topics = urls["topic"].fillna("<missing>").value_counts().rename_axis("topic").reset_index(name="articles")
        lines.append(markdown_table(topics))
    lines.append("")
    return "\n".join(lines)


def write_abcnoticias_outputs(
    discovered: pd.DataFrame,
    report: str,
    discovery_dir: Path,
    reports_dir: Path,
) -> AbcNoticiasDiscoveryOutputs:
    discovery_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    csv_path = discovery_dir / "discovered_urls_abcnoticias.csv"
    parquet_path = discovery_dir / "discovered_urls_abcnoticias.parquet"
    report_path = reports_dir / "abcnoticias_discovery_report.md"
    discovered.to_csv(csv_path, index=False, encoding="utf-8")
    parquet_error = None
    try:
        discovered.to_parquet(parquet_path, index=False)
    except Exception as exc:
        parquet_error = str(exc).splitlines()[0]
        parquet_path = None
    report_path.write_text(report, encoding="utf-8")
    return AbcNoticiasDiscoveryOutputs(csv_path, parquet_path, report_path, parquet_error)


def is_ok(status: object) -> bool:
    return isinstance(status, int) and 200 <= status < 300


def is_tls_error(error: object) -> bool:
    if is_missing(error):
        return False
    lowered = str(error).lower()
    return any(marker in lowered for marker in TLS_ERROR_MARKERS)


def response_error(response: dict[str, object]) -> str:
    error = response.get("error")
    if not is_missing(error):
        return str(error)
    return f"http_status_{response.get('status')}"


def is_missing(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False

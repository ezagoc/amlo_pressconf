"""SDPNoticias URL discovery helpers."""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests
import urllib3

if not hasattr(pd, "NA"):
    pd.NA = None

from crawler_core.capabilities import BROWSER_USER_AGENT, markdown_table


SOURCE_ID = "sdpnoticias"
SOURCE_NAME = "SDPNoticias"
SOURCE_URL = "https://www.sdpnoticias.com/"
DISCOVERY_STRATEGY = "sdp_arc_sitemap"
SITEMAP_BASE_URL = SOURCE_URL + "arc/outboundfeeds/sitemap/?outputType=xml"
CATEGORY_SITEMAP_TEMPLATE = SOURCE_URL + "arc/outboundfeeds/sitemap/category/{category}/?outputType=xml"

CATEGORIES = (
    "mexico",
    "estados",
    "opinion",
    "deportes",
    "espectaculos",
    "internacional",
    "negocios",
    "tecnologia",
    "geek",
    "estilo-de-vida",
    "sorprendente",
    "diversidad",
    "motor",
)

BROWSER_HEADERS = {
    "User-Agent": BROWSER_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "es-MX,es;q=0.9,en-US;q=0.7,en;q=0.6",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


@dataclass(frozen=True)
class SdpDiscoveryOutputs:
    """Paths written by SDP discovery."""

    discovered_csv: Path
    discovered_parquet: Path | None
    report_path: Path
    parquet_error: str | None = None


@dataclass
class CheckpointState:
    """Track periodic discovery checkpoint writes."""

    path: Path | None = None
    every: int = 5_000
    last_rows: int = 0


def fetch_sdp(url: str, timeout: float, *, profile: str = "browser") -> dict[str, object]:
    """Fetch an SDPNoticias URL with requests to avoid local curl Schannel failures."""
    del profile
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    try:
        response = requests.get(
            url,
            timeout=float(timeout),
            verify=False,
            headers=BROWSER_HEADERS,
            allow_redirects=True,
        )
    except Exception as exc:
        return {
            "status": pd.NA,
            "final_url": pd.NA,
            "content_type": pd.NA,
            "text": "",
            "error": f"requests_sdp: {exc}",
        }
    return {
        "status": int(response.status_code),
        "final_url": response.url,
        "content_type": response.headers.get("content-type") or pd.NA,
        "text": response.text,
        "error": pd.NA,
    }


def discover_sdp_urls(
    *,
    max_offset: int = 10_000,
    offset_step: int = 100,
    categories: list[str] | None = None,
    timeout: float = 45.0,
    pause_seconds: float = 0.05,
    checkpoint_path: Path | None = None,
    checkpoint_every: int = 5_000,
    resume_checkpoint: bool = True,
    expand_nested_categories: bool = False,
    max_nested_rounds: int = 2,
) -> pd.DataFrame:
    """Discover SDPNoticias URLs from Arc top-level and category sitemap offsets."""
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    rows: list[dict[str, object]] = []
    seen_urls: set[str] = set()
    processed_sitemaps: set[str] = set()
    checkpoint = CheckpointState(checkpoint_path, checkpoint_every)

    if resume_checkpoint and checkpoint_path is not None and checkpoint_path.exists():
        existing = pd.read_csv(checkpoint_path, low_memory=False)
        rows.extend(existing.to_dict("records"))
        if "url" in existing.columns:
            seen_urls.update(existing["url"].dropna().astype(str))
        if "sitemap_url" in existing.columns:
            processed_sitemaps.update(existing["sitemap_url"].dropna().astype(str))
        checkpoint.last_rows = len(rows)
        print(f"Resume enabled: loaded {len(existing):,} SDP checkpoint rows", flush=True)

    processed_categories: set[str] = set()
    sitemap_specs: list[tuple[str, str]] = [("top", SITEMAP_BASE_URL)]
    for category in categories or list(CATEGORIES):
        sitemap_specs.append((category, CATEGORY_SITEMAP_TEMPLATE.format(category=category)))
        processed_categories.add(category)

    process_sitemap_specs(
        sitemap_specs,
        rows=rows,
        seen_urls=seen_urls,
        processed_sitemaps=processed_sitemaps,
        checkpoint=checkpoint,
        max_offset=max_offset,
        offset_step=offset_step,
        timeout=timeout,
        pause_seconds=pause_seconds,
    )

    if expand_nested_categories:
        for round_number in range(1, max(1, max_nested_rounds) + 1):
            nested = nested_categories_from_urls(seen_urls)
            new_categories = [category for category in nested if category not in processed_categories]
            if not new_categories:
                break
            print(
                f"  sdp_nested_categories: round={round_number}, queued={len(new_categories):,}",
                flush=True,
            )
            for category in new_categories:
                processed_categories.add(category)
            nested_specs = [
                (category, CATEGORY_SITEMAP_TEMPLATE.format(category=category))
                for category in new_categories
            ]
            process_sitemap_specs(
                nested_specs,
                rows=rows,
                seen_urls=seen_urls,
                processed_sitemaps=processed_sitemaps,
                checkpoint=checkpoint,
                max_offset=max_offset,
                offset_step=offset_step,
                timeout=timeout,
                pause_seconds=pause_seconds,
            )

    return finalize_discovered(rows, checkpoint)


def process_sitemap_specs(
    sitemap_specs: list[tuple[str, str]],
    *,
    rows: list[dict[str, object]],
    seen_urls: set[str],
    processed_sitemaps: set[str],
    checkpoint: CheckpointState,
    max_offset: int,
    offset_step: int,
    timeout: float,
    pause_seconds: float,
) -> None:
    """Process each SDP sitemap feed and its offset pages."""
    for sitemap_kind, base_url in sitemap_specs:
        for offset in range(0, max_offset + 1, offset_step):
            sitemap_url = with_offset(base_url, offset)
            if sitemap_url in processed_sitemaps:
                continue
            processed_sitemaps.add(sitemap_url)
            print(f"  sdp_sitemap: {sitemap_kind} from={offset:,} {sitemap_url}", flush=True)
            page_rows, url_count, stop_reason = discover_one_sdp_sitemap(
                sitemap_url,
                sitemap_kind=sitemap_kind,
                offset=offset,
                seen_urls=seen_urls,
                timeout=timeout,
            )
            rows.extend(page_rows)
            print(
                f"    rows={len(page_rows):,}, urls={url_count:,}, total_urls={len(seen_urls):,}"
                f"{f', stop={stop_reason}' if stop_reason else ''}",
                flush=True,
            )
            maybe_write_checkpoint(rows, checkpoint)
            if pause_seconds:
                time.sleep(pause_seconds)
            if stop_reason:
                break


def discover_one_sdp_sitemap(
    sitemap_url: str,
    *,
    sitemap_kind: str,
    offset: int,
    seen_urls: set[str],
    timeout: float,
) -> tuple[list[dict[str, object]], int, str | None]:
    """Read one SDP sitemap offset and return rows plus optional stop reason."""
    response = fetch_sdp(sitemap_url, timeout)
    status = response["status"]
    if not isinstance(status, int) or status < 200 or status >= 300:
        error = response["error"]
        if pd.isna(error):
            error = f"http_status_{status}"
        return [error_row(sitemap_url, sitemap_kind, offset, status, error)], 0, f"http_status_{status}"

    parsed = parse_sitemap_xml(response["text"] or "")
    if parsed["error"]:
        return [error_row(sitemap_url, sitemap_kind, offset, status, parsed["error"])], 0, parsed["error"]

    rows: list[dict[str, object]] = []
    urls = parsed["urls"]
    for item in urls:
        loc = item.get("loc")
        if not loc or loc in seen_urls:
            continue
        seen_urls.add(str(loc))
        rows.append(url_row(item, sitemap_url, sitemap_kind, offset, status))
    stop_reason = None
    if len(urls) < 100:
        stop_reason = f"short_page_{len(urls)}"
    return rows, len(urls), stop_reason


def parse_sitemap_xml(text: str) -> dict[str, object]:
    """Parse a sitemap URL set."""
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as exc:
        return {"urls": [], "error": f"ParseError: {exc}"}
    urls = []
    for child in root:
        if tag_name(child) != "url":
            continue
        loc = find_child_text(child, "loc")
        if not loc:
            continue
        urls.append(
            {
                "loc": loc,
                "lastmod": find_child_text(child, "lastmod"),
                "changefreq": find_child_text(child, "changefreq"),
                "priority": find_child_text(child, "priority"),
            }
        )
    return {"urls": urls, "error": None}


def with_offset(base_url: str, offset: int) -> str:
    """Append Arc from offset when nonzero."""
    if offset <= 0:
        return base_url
    return f"{base_url}&from={offset}"


def url_row(
    item: dict[str, object],
    sitemap_url: str,
    sitemap_kind: str,
    offset: int,
    status: object,
) -> dict[str, object]:
    """Return a discovered URL row."""
    loc = item.get("loc")
    return {
        "source_id": SOURCE_ID,
        "source_name": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "url": loc,
        "canonical_url": loc,
        "date_published": pd.NA,
        "lastmod": item.get("lastmod"),
        "topic": infer_topic_from_url(loc),
        "section": infer_topic_from_url(loc),
        "discovery_strategy": DISCOVERY_STRATEGY,
        "sitemap_url": sitemap_url,
        "sitemap_kind": sitemap_kind,
        "sitemap_offset": offset,
        "sitemap_status": status,
        "changefreq": item.get("changefreq"),
        "priority": item.get("priority"),
        "discovered_at": pd.Timestamp.utcnow().isoformat(),
        "status": status,
        "error": pd.NA,
    }


def error_row(sitemap_url: object, sitemap_kind: str, offset: int, status: object, error: object) -> dict[str, object]:
    """Return an error row using the discovery schema."""
    return {
        "source_id": SOURCE_ID,
        "source_name": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "url": pd.NA,
        "canonical_url": pd.NA,
        "date_published": pd.NA,
        "lastmod": pd.NA,
        "topic": pd.NA,
        "section": pd.NA,
        "discovery_strategy": DISCOVERY_STRATEGY,
        "sitemap_url": sitemap_url,
        "sitemap_kind": sitemap_kind,
        "sitemap_offset": offset,
        "sitemap_status": status,
        "changefreq": pd.NA,
        "priority": pd.NA,
        "discovered_at": pd.Timestamp.utcnow().isoformat(),
        "status": status,
        "error": error,
    }


def infer_topic_from_url(url: object) -> object:
    """Infer topic from the first SDP URL path segment."""
    if pd.isna(url):
        return pd.NA
    parts = [part for part in urlparse(str(url)).path.split("/") if part]
    if parts:
        return parts[0]
    return pd.NA


def nested_categories_from_urls(urls: set[str]) -> list[str]:
    """Infer two-level SDP category paths worth probing from discovered URLs."""
    counts: dict[str, int] = {}
    for url in urls:
        parts = [part for part in urlparse(str(url)).path.split("/") if part]
        if len(parts) < 3:
            continue
        first, second = parts[0], parts[1]
        if first not in CATEGORIES and first not in {"enelshow", "local", "nacional", "columnas"}:
            continue
        if second[:4].isdigit():
            continue
        category = f"{first}/{second}"
        counts[category] = counts.get(category, 0) + 1
    return [
        category
        for category, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def tag_name(element: ET.Element) -> str:
    """Return an XML element local tag name."""
    return element.tag.split("}", 1)[-1].lower()


def find_child_text(element: ET.Element, wanted_name: str) -> str | None:
    """Find child text by local XML tag name."""
    for child in element:
        if tag_name(child) == wanted_name:
            return child.text.strip() if child.text else None
    return None


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
    """Write checkpoint CSV for long SDP discovery runs."""
    if checkpoint.path is None or not force:
        return
    checkpoint.path.parent.mkdir(parents=True, exist_ok=True)
    discovered.to_csv(checkpoint.path, index=False, encoding="utf-8")
    checkpoint.last_rows = len(discovered)
    print(f"  checkpoint: wrote {len(discovered):,} rows to {checkpoint.path}", flush=True)


def build_sdp_report(discovered: pd.DataFrame) -> str:
    """Create a compact SDP discovery report."""
    lines = [
        "# SDPNoticias Discovery Report",
        "",
        f"- Rows: {len(discovered):,}",
        f"- URLs: {discovered['url'].notna().sum() if not discovered.empty else 0:,}",
        f"- Errors: {discovered['error'].notna().sum() if not discovered.empty else 0:,}",
        "",
        "## By Topic",
        "",
    ]
    if discovered.empty or discovered["url"].notna().sum() == 0:
        lines.append("_No URL rows._")
    else:
        topic_summary = (
            discovered[discovered["url"].notna()]
            .groupby("topic", dropna=False)
            .agg(
                rows=("url", "size"),
                urls=("url", "nunique"),
                min_lastmod=("lastmod", min_nonblank_text),
                max_lastmod=("lastmod", max_nonblank_text),
            )
            .reset_index()
            .sort_values(["rows", "topic"], ascending=[False, True])
        )
        lines.append(markdown_table(topic_summary.head(100)))
    lines.append("")
    return "\n".join(lines)


def min_nonblank_text(values: pd.Series) -> object:
    """Return the lexical minimum after dropping missing values."""
    clean = values.dropna().astype(str).str.strip()
    clean = clean[clean.ne("")]
    if clean.empty:
        return pd.NA
    return clean.min()


def max_nonblank_text(values: pd.Series) -> object:
    """Return the lexical maximum after dropping missing values."""
    clean = values.dropna().astype(str).str.strip()
    clean = clean[clean.ne("")]
    if clean.empty:
        return pd.NA
    return clean.max()


def write_sdp_outputs(
    discovered: pd.DataFrame,
    report: str,
    discovery_dir: Path,
    reports_dir: Path,
) -> SdpDiscoveryOutputs:
    """Write SDP discovery outputs."""
    discovery_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    csv_path = discovery_dir / "discovered_urls_sdpnoticias.csv"
    parquet_path = discovery_dir / "discovered_urls_sdpnoticias.parquet"
    report_path = reports_dir / "sdpnoticias_discovery_report.md"

    output = normalize_sdp_discovery_for_output(discovered)
    output.to_csv(csv_path, index=False, encoding="utf-8")
    parquet_error = None
    try:
        output.to_parquet(parquet_path, index=False)
    except Exception as exc:
        parquet_error = str(exc).splitlines()[0]
        parquet_path = None
    report_path.write_text(report, encoding="utf-8")
    return SdpDiscoveryOutputs(csv_path, parquet_path, report_path, parquet_error)


def normalize_sdp_discovery_for_output(discovered: pd.DataFrame) -> pd.DataFrame:
    """Normalize mixed XML scalar columns before parquet serialization."""
    output = discovered.copy()
    text_columns = [
        "source_id",
        "source_name",
        "source_url",
        "url",
        "canonical_url",
        "date_published",
        "lastmod",
        "topic",
        "section",
        "discovery_strategy",
        "sitemap_url",
        "sitemap_kind",
        "changefreq",
        "priority",
        "discovered_at",
        "error",
    ]
    for column in text_columns:
        if column in output.columns:
            output[column] = output[column].astype("string")
    return output

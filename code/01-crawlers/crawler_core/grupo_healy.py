"""Grupo Healy / El Imparcial URL discovery helpers."""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests
import urllib3

if not hasattr(pd, "NA"):
    pd.NA = None

from crawler_core.capabilities import BROWSER_USER_AGENT, markdown_table


BASE_URL = "https://www.elimparcial.com/"
SITEMAP_URL_TEMPLATE = BASE_URL + "arc/outboundfeeds/sitemap/{date}/?outputType=xml"
ROBOTS_SITEMAP_INDEX = BASE_URL + "arc/outboundfeeds/sitemap-index/"
DISCOVERY_STRATEGY = "grupo_healy_daily_sitemap"

SOURCE_PREFIXES = {
    "elimparcial_sonora_sonora": ("/son/", "/sonora/"),
    "elimparcial_baja_california_tij_tijuana": ("/tij/", "/tijuana/"),
    "elimparcial_baja_california_mxl_mexicali": ("/mxl/", "/mexicali/"),
}

SHARED_PREFIXES = (
    "/mexico/",
    "/mundo/",
    "/dinero/",
    "/deporte/",
    "/deportes/",
    "/espectaculos/",
    "/estilos/",
    "/locurioso/",
    "/tecnologia/",
    "/columnas/",
)

BROWSER_HEADERS = {
    "User-Agent": BROWSER_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "es-MX,es;q=0.9,en-US;q=0.7,en;q=0.6",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


@dataclass(frozen=True)
class GrupoHealyDiscoveryOutputs:
    """Paths written by Grupo Healy discovery."""

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


def fetch_grupo_healy(url: str, timeout: float, *, profile: str = "browser") -> dict[str, object]:
    """Fetch an El Imparcial URL with requests to avoid local curl Schannel failures."""
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
            "error": f"requests_grupo_healy: {exc}",
        }
    return {
        "status": int(response.status_code),
        "final_url": response.url,
        "content_type": response.headers.get("content-type") or pd.NA,
        "text": response.text,
        "error": pd.NA,
    }


def discover_grupo_healy_urls(
    sources: pd.DataFrame,
    *,
    from_date: date,
    to_date: date,
    source_ids: list[str] | None = None,
    max_urls: int | None = None,
    timeout: float = 45.0,
    pause_seconds: float = 0.05,
    checkpoint_path: Path | None = None,
    checkpoint_every: int = 5_000,
    resume_checkpoint: bool = True,
    include_shared_paths: bool = False,
) -> pd.DataFrame:
    """Discover Grupo Healy article URLs from predictable daily Arc sitemaps."""
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    selected = select_sources(sources, source_ids)
    source_by_id = {str(row["source_id"]): row for _, row in selected.iterrows()}
    rows: list[dict[str, object]] = []
    seen_keys: set[tuple[str, str]] = set()
    processed_sitemaps: set[str] = set()
    checkpoint = CheckpointState(checkpoint_path, checkpoint_every)

    if resume_checkpoint and checkpoint_path is not None and checkpoint_path.exists():
        existing = pd.read_csv(checkpoint_path, low_memory=False)
        for _, row in existing.iterrows():
            url = row.get("url")
            source_id = row.get("source_id")
            if pd.notna(url) and pd.notna(source_id):
                seen_keys.add((str(source_id), str(url)))
            sitemap_url = row.get("sitemap_url")
            if pd.notna(sitemap_url):
                processed_sitemaps.add(str(sitemap_url))
        rows.extend(existing.to_dict("records"))
        checkpoint.last_rows = len(rows)
        print(f"Resume enabled: loaded {len(existing):,} Grupo Healy checkpoint rows", flush=True)

    dates = list(iter_dates(from_date, to_date))
    for index, current_date in enumerate(dates, start=1):
        sitemap_url = SITEMAP_URL_TEMPLATE.format(date=current_date.isoformat())
        if sitemap_url in processed_sitemaps:
            continue
        print(f"  grupo_healy_sitemap: {index:,}/{len(dates):,} {sitemap_url}", flush=True)
        day_rows = discover_one_daily_sitemap(
            sitemap_url,
            current_date=current_date,
            source_by_id=source_by_id,
            seen_keys=seen_keys,
            timeout=timeout,
            include_shared_paths=include_shared_paths,
        )
        rows.extend(day_rows)
        kept = sum(1 for row in day_rows if pd.notna(row.get("url")))
        print(f"    rows={len(day_rows):,}, urls={kept:,}, total_urls={len(seen_keys):,}", flush=True)
        maybe_write_checkpoint(rows, checkpoint)
        if max_urls is not None and len(seen_keys) >= max_urls:
            break
        if pause_seconds:
            time.sleep(pause_seconds)

    discovered = finalize_discovered(rows, checkpoint)
    if max_urls is not None and not discovered.empty:
        url_rows = discovered[discovered["url"].notna()].head(max_urls)
        error_rows = discovered[discovered["url"].isna()]
        discovered = pd.concat([url_rows, error_rows], ignore_index=True)
    return discovered


def discover_one_daily_sitemap(
    sitemap_url: str,
    *,
    current_date: date,
    source_by_id: dict[str, pd.Series],
    seen_keys: set[tuple[str, str]],
    timeout: float,
    include_shared_paths: bool,
) -> list[dict[str, object]]:
    """Read one Arc daily sitemap and map matching URLs to source rows."""
    response = fetch_grupo_healy(sitemap_url, timeout)
    status = response["status"]
    if not isinstance(status, int) or status < 200 or status >= 300:
        error = response["error"]
        if pd.isna(error):
            error = f"http_status_{status}"
        return [error_row(source_by_id, sitemap_url, current_date, status, error)]

    parsed = parse_sitemap_xml(response["text"] or "")
    if parsed["error"]:
        return [error_row(source_by_id, sitemap_url, current_date, status, parsed["error"])]

    rows: list[dict[str, object]] = []
    for item in parsed["urls"]:
        loc = item.get("loc")
        if not loc:
            continue
        for source_id in source_ids_for_url(loc, source_by_id, include_shared_paths=include_shared_paths):
            key = (source_id, loc)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            rows.append(url_row(source_by_id[source_id], item, sitemap_url, current_date, status))
    if not rows:
        rows.append(error_row(source_by_id, sitemap_url, current_date, status, "no_matching_source_urls"))
    return rows


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


def source_ids_for_url(
    url: object,
    source_by_id: dict[str, pd.Series],
    *,
    include_shared_paths: bool = False,
) -> list[str]:
    """Return source IDs whose local edition prefix matches the URL path."""
    path = urlparse(str(url)).path.lower()
    matches = []
    for source_id in source_by_id:
        prefixes = SOURCE_PREFIXES.get(source_id, ())
        if any(path.startswith(prefix) for prefix in prefixes):
            matches.append(source_id)
        elif include_shared_paths and any(path.startswith(prefix) for prefix in SHARED_PREFIXES):
            matches.append(source_id)
    return matches


def select_sources(sources: pd.DataFrame, source_ids: list[str] | None) -> pd.DataFrame:
    """Select Grupo Healy sources, optionally restricted by source_id."""
    selected = sources[sources["source_id"].isin(SOURCE_PREFIXES)].copy()
    if source_ids:
        selected = selected[selected["source_id"].isin(source_ids)].copy()
        missing = sorted(set(source_ids) - set(selected["source_id"]))
        if missing:
            raise ValueError("Requested Grupo Healy source_id not found: " + ", ".join(missing))
    if selected.empty:
        raise ValueError("No Grupo Healy sources selected")
    return selected.reset_index(drop=True)


def iter_dates(from_date: date, to_date: date):
    """Yield inclusive date range."""
    current = from_date
    while current <= to_date:
        yield current
        current += timedelta(days=1)


def parse_date(value: str) -> date:
    """Parse an ISO calendar date."""
    return datetime.strptime(value, "%Y-%m-%d").date()


def url_row(
    source: pd.Series,
    item: dict[str, object],
    sitemap_url: str,
    sitemap_date: date,
    status: object,
) -> dict[str, object]:
    """Return a discovered URL row."""
    loc = item.get("loc")
    return {
        "source_id": source.get("source_id"),
        "source_name": source.get("source_name"),
        "source_url": source.get("canonical_url"),
        "url": loc,
        "canonical_url": loc,
        "date_published": date_from_url(loc),
        "lastmod": item.get("lastmod"),
        "topic": infer_topic_from_url(loc),
        "section": infer_topic_from_url(loc),
        "discovery_strategy": DISCOVERY_STRATEGY,
        "sitemap_url": sitemap_url,
        "sitemap_date": sitemap_date.isoformat(),
        "sitemap_status": status,
        "changefreq": item.get("changefreq"),
        "priority": item.get("priority"),
        "discovered_at": pd.Timestamp.utcnow().isoformat(),
        "status": status,
        "error": pd.NA,
    }


def error_row(
    source_by_id: dict[str, pd.Series],
    sitemap_url: object,
    sitemap_date: date,
    status: object,
    error: object,
) -> dict[str, object]:
    """Return an error row using the discovery schema."""
    first_source = next(iter(source_by_id.values()))
    return {
        "source_id": first_source.get("source_id"),
        "source_name": first_source.get("source_name"),
        "source_url": first_source.get("canonical_url"),
        "url": pd.NA,
        "canonical_url": pd.NA,
        "date_published": pd.NA,
        "lastmod": pd.NA,
        "topic": pd.NA,
        "section": pd.NA,
        "discovery_strategy": DISCOVERY_STRATEGY,
        "sitemap_url": sitemap_url,
        "sitemap_date": sitemap_date.isoformat(),
        "sitemap_status": status,
        "changefreq": pd.NA,
        "priority": pd.NA,
        "discovered_at": pd.Timestamp.utcnow().isoformat(),
        "status": status,
        "error": error,
    }


def infer_topic_from_url(url: object) -> object:
    """Infer a compact topic from El Imparcial path segments."""
    if pd.isna(url):
        return pd.NA
    parts = [part for part in urlparse(str(url)).path.split("/") if part]
    if len(parts) >= 2 and parts[1].isdigit():
        return parts[0]
    if len(parts) >= 2:
        return "/".join(parts[:2])
    if parts:
        return parts[0]
    return pd.NA


def date_from_url(url: object) -> object:
    """Infer article date from /YYYY/MM/DD/ URL paths."""
    if pd.isna(url):
        return pd.NA
    parts = [part for part in urlparse(str(url)).path.split("/") if part]
    for i in range(len(parts) - 2):
        year, month, day = parts[i : i + 3]
        if year.isdigit() and month.isdigit() and day.isdigit() and len(year) == 4:
            return f"{year}-{month}-{day}"
    return pd.NA


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
    if not discovered.empty and {"source_id", "url"}.issubset(discovered.columns):
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
    """Write checkpoint CSV for long Grupo Healy discovery runs."""
    if checkpoint.path is None or not force:
        return
    checkpoint.path.parent.mkdir(parents=True, exist_ok=True)
    discovered.to_csv(checkpoint.path, index=False, encoding="utf-8")
    checkpoint.last_rows = len(discovered)
    print(f"  checkpoint: wrote {len(discovered):,} rows to {checkpoint.path}", flush=True)


def build_grupo_healy_report(discovered: pd.DataFrame) -> str:
    """Create a compact Grupo Healy discovery report."""
    lines = [
        "# Grupo Healy / El Imparcial Discovery Report",
        "",
        f"- Rows: {len(discovered):,}",
        f"- URLs: {discovered['url'].notna().sum() if not discovered.empty else 0:,}",
        f"- Errors: {discovered['error'].notna().sum() if not discovered.empty else 0:,}",
        "",
        "## By Source",
        "",
    ]
    if discovered.empty:
        lines.append("_No rows._")
    else:
        url_rows = discovered[discovered["url"].notna()].copy()
        if url_rows.empty:
            lines.append("_No URL rows._")
        else:
            summary = (
                url_rows.groupby(["source_id", "source_name"], dropna=False)
                .agg(
                    rows=("url", "size"),
                    urls=("url", "nunique"),
                    topics=("topic", "nunique"),
                    min_date=("date_published", min_nonblank_text),
                    max_date=("date_published", max_nonblank_text),
                )
                .reset_index()
                .sort_values(["rows", "source_id"], ascending=[False, True])
            )
            lines.append(markdown_table(summary))
    lines.extend(["", "## By Topic", ""])
    if discovered.empty or discovered["url"].notna().sum() == 0:
        lines.append("_No URL rows._")
    else:
        topic_summary = (
            discovered[discovered["url"].notna()]
            .groupby(["source_id", "topic"], dropna=False)
            .agg(rows=("url", "size"), min_date=("date_published", min_nonblank_text), max_date=("date_published", max_nonblank_text))
            .reset_index()
            .sort_values(["rows", "source_id"], ascending=[False, True])
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


def write_grupo_healy_outputs(
    discovered: pd.DataFrame,
    report: str,
    discovery_dir: Path,
    reports_dir: Path,
    *,
    output_stem: str,
) -> GrupoHealyDiscoveryOutputs:
    """Write Grupo Healy discovery outputs."""
    discovery_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    csv_path = discovery_dir / f"{output_stem}.csv"
    parquet_path = discovery_dir / f"{output_stem}.parquet"
    report_path = reports_dir / f"{output_stem}_report.md"

    discovered.to_csv(csv_path, index=False, encoding="utf-8")
    parquet_error = None
    try:
        discovered.to_parquet(parquet_path, index=False)
    except Exception as exc:
        parquet_error = str(exc).splitlines()[0]
        parquet_path = None
    report_path.write_text(report, encoding="utf-8")
    return GrupoHealyDiscoveryOutputs(csv_path, parquet_path, report_path, parquet_error)

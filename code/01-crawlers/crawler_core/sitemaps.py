"""Sitemap-based URL discovery for newspaper sources."""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from crawler_core.capabilities import fetch, markdown_table


ARTICLE_HINT_RE = re.compile(
    r"/(?:noticias?|politica|estados?|nacional|mexico|opinion|columnas?|"
    r"mundo|economia|seguridad|policiaca|sociedad|cultura|deportes|"
    r"local|municipios?|jalisco|morelos|sonora|yucatan|tabasco|veracruz)/",
    flags=re.I,
)
DATE_PATH_RE = re.compile(r"/20[0-3][0-9]/|[-/]20[0-3][0-9][- /]")
NON_ARTICLE_PATH_RE = re.compile(
    r"/(?:users?|author|authors|tag|tags|categor(?:y|ies)|categoria|categorias|"
    r"page|search|buscar|"
    r"feed|rss|login|registro|newsletter|contacto|about|acerca-de)(?:/|$)",
    flags=re.I,
)


@dataclass(frozen=True)
class SitemapOutputs:
    """Paths written by sitemap discovery."""

    discovered_csv: Path
    discovered_parquet: Path | None
    report_path: Path
    parquet_error: str | None = None


def load_sitemap_sources(
    capabilities_path: Path,
    *,
    strategy: str = "sitemap",
    include_any_sitemap: bool = False,
) -> pd.DataFrame:
    """Load sources to discover through sitemaps."""
    capabilities = pd.read_csv(capabilities_path)
    if include_any_sitemap:
        mask = capabilities["sitemap_available"].astype(str).str.lower().isin({"true", "1"})
    else:
        mask = capabilities["recommended_strategy"].eq(strategy)
    return capabilities[mask].reset_index(drop=True)


def discover_sitemap_urls(
    sources: pd.DataFrame,
    *,
    source_ids: list[str] | None = None,
    limit_sources: int | None = None,
    max_sitemaps_per_source: int = 100,
    max_urls_per_source: int | None = None,
    timeout: float = 20.0,
    pause_seconds: float = 0.2,
) -> pd.DataFrame:
    """Discover URLs from sitemap indexes and URL sets."""
    if source_ids:
        sources = sources[sources["source_id"].isin(source_ids)].reset_index(drop=True)
    if limit_sources is not None:
        sources = sources.head(limit_sources)

    rows: list[dict[str, object]] = []
    total_sources = len(sources)
    for i, source in sources.iterrows():
        print(f"\n=== Sitemap source {i + 1}/{total_sources}: {source['source_id']} ===")
        try:
            source_rows = discover_one_source_sitemaps(
                source,
                max_sitemaps=max_sitemaps_per_source,
                max_urls=max_urls_per_source,
                timeout=timeout,
                pause_seconds=pause_seconds,
            )
        except Exception as exc:
            print(f"!!! {source['source_id']}: unexpected source failure: {type(exc).__name__}: {exc}")
            source_rows = [error_row(source, source.get("sitemap_url"), pd.NA, f"{type(exc).__name__}: {exc}")]
        rows.extend(source_rows)
        urls = sum(1 for row in source_rows if pd.notna(row.get("url")))
        errors = sum(1 for row in source_rows if pd.notna(row.get("error")))
        print(f"=== Finished {source['source_id']}: rows={len(source_rows):,}, urls={urls:,}, errors={errors:,} ===")
        if pause_seconds:
            time.sleep(pause_seconds)

    discovered = pd.DataFrame(rows)
    if not discovered.empty:
        discovered = discovered.drop_duplicates(["source_id", "url"], keep="last").reset_index(drop=True)
    return discovered


def discover_one_source_sitemaps(
    source: pd.Series,
    *,
    max_sitemaps: int,
    max_urls: int | None,
    timeout: float,
    pause_seconds: float,
) -> list[dict[str, object]]:
    """Discover URLs for one source by expanding sitemap indexes recursively."""
    start_url = source.get("sitemap_url")
    if pd.isna(start_url):
        return [error_row(source, pd.NA, pd.NA, "missing_sitemap_url")]

    rows: list[dict[str, object]] = []
    queue = [str(start_url)]
    seen_sitemaps: set[str] = set()
    sitemaps_read = 0
    source_id = source.get("source_id")

    while queue and sitemaps_read < max_sitemaps:
        sitemap_url = queue.pop(0)
        if sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)
        sitemaps_read += 1
        print(f"  {source_id}: reading sitemap {sitemaps_read}/{max_sitemaps}: {sitemap_url}")

        response = fetch(sitemap_url, timeout)
        status = response["status"]
        if not isinstance(status, int) or status < 200 or status >= 300:
            error = response["error"]
            if pd.isna(error):
                error = f"http_status_{status}"
            rows.append(error_row(source, sitemap_url, status, error))
            continue

        parsed = parse_sitemap_xml(response["text"] or "")
        if parsed["error"]:
            rows.append(error_row(source, sitemap_url, status, parsed["error"]))
            continue

        child_sitemaps = parsed["sitemaps"]
        urls = parsed["urls"]
        if child_sitemaps:
            queue.extend(url for url in child_sitemaps if url not in seen_sitemaps)
            print(f"  {source_id}: found {len(child_sitemaps):,} child sitemaps; queue={len(queue):,}")

        kept = 0
        for url_item in urls:
            if max_urls is not None and count_urls(rows) >= max_urls:
                print(f"  {source_id}: hit max_urls={max_urls}; stopping")
                queue = []
                break
            if not likely_article_url(url_item["loc"]):
                continue
            rows.append(url_row(source, url_item, sitemap_url, status, sitemaps_read))
            kept += 1
        if urls:
            print(f"  {source_id}: urlset urls={len(urls):,}, kept_likely_articles={kept:,}, total_kept={count_urls(rows):,}")

        if pause_seconds:
            time.sleep(pause_seconds)

    if queue:
        rows.append(error_row(source, start_url, pd.NA, f"max_sitemaps_reached_{max_sitemaps}"))
    if not rows:
        rows.append(error_row(source, start_url, pd.NA, "no_article_urls_found"))
    return rows


def parse_sitemap_xml(text: str) -> dict[str, object]:
    """Parse sitemap XML into child sitemap and URL records."""
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as exc:
        return {"sitemaps": [], "urls": [], "error": f"ParseError: {exc}"}

    def tag_name(element: ET.Element) -> str:
        return element.tag.split("}", 1)[-1].lower()

    sitemaps = []
    urls = []
    for child in root:
        name = tag_name(child)
        if name == "sitemap":
            loc = find_child_text(child, "loc")
            if loc:
                sitemaps.append(loc)
        elif name == "url":
            loc = find_child_text(child, "loc")
            if loc:
                urls.append(
                    {
                        "loc": loc,
                        "lastmod": find_child_text(child, "lastmod"),
                        "changefreq": find_child_text(child, "changefreq"),
                        "priority": find_child_text(child, "priority"),
                    }
                )
    return {"sitemaps": sitemaps, "urls": urls, "error": None}


def find_child_text(element: ET.Element, wanted_name: str) -> str | None:
    """Find child text by local XML tag name."""
    for child in element:
        if child.tag.split("}", 1)[-1].lower() == wanted_name:
            return child.text.strip() if child.text else None
    return None


def likely_article_url(url: object) -> bool:
    """Heuristic filter for article-like URLs."""
    if pd.isna(url):
        return False
    value = str(url)
    lowered = value.lower()
    if NON_ARTICLE_PATH_RE.search(lowered):
        return False
    if any(lowered.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".mp4"]):
        return False
    return bool(ARTICLE_HINT_RE.search(value) or DATE_PATH_RE.search(value))


def url_row(
    source: pd.Series,
    item: dict[str, object],
    sitemap_url: str,
    status: object,
    sitemap_number: int,
) -> dict[str, object]:
    """Return a discovered URL row."""
    return {
        "source_id": source.get("source_id"),
        "source_name": source.get("source_name"),
        "source_url": source.get("canonical_url"),
        "url": item.get("loc"),
        "canonical_url": item.get("loc"),
        "date_published": pd.NA,
        "lastmod": item.get("lastmod"),
        "topic": infer_topic_from_url(item.get("loc")),
        "discovery_strategy": "sitemap",
        "sitemap_url": sitemap_url,
        "sitemap_number": sitemap_number,
        "sitemap_status": status,
        "changefreq": item.get("changefreq"),
        "priority": item.get("priority"),
        "discovered_at": pd.Timestamp.utcnow().isoformat(),
        "status": status,
        "error": pd.NA,
    }


def error_row(source: pd.Series, sitemap_url: object, status: object, error: object) -> dict[str, object]:
    """Return an error row using the discovery schema."""
    return {
        "source_id": source.get("source_id"),
        "source_name": source.get("source_name"),
        "source_url": source.get("canonical_url"),
        "url": pd.NA,
        "canonical_url": pd.NA,
        "date_published": pd.NA,
        "lastmod": pd.NA,
        "topic": pd.NA,
        "discovery_strategy": "sitemap",
        "sitemap_url": sitemap_url,
        "sitemap_number": pd.NA,
        "sitemap_status": status,
        "changefreq": pd.NA,
        "priority": pd.NA,
        "discovered_at": pd.Timestamp.utcnow().isoformat(),
        "status": status,
        "error": error,
    }


def infer_topic_from_url(url: object) -> object:
    """Infer a rough topic from URL path segments."""
    if pd.isna(url):
        return pd.NA
    match = ARTICLE_HINT_RE.search(str(url))
    if not match:
        return pd.NA
    return match.group(0).strip("/").split("/")[0]


def count_urls(rows: list[dict[str, object]]) -> int:
    return sum(1 for row in rows if pd.notna(row.get("url")))


def write_sitemap_outputs(
    discovered: pd.DataFrame,
    report: str,
    discovery_dir: Path,
    reports_dir: Path,
) -> SitemapOutputs:
    """Write sitemap discovery outputs."""
    discovery_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    csv_path = discovery_dir / "discovered_urls_sitemap.csv"
    parquet_path = discovery_dir / "discovered_urls_sitemap.parquet"
    report_path = reports_dir / "sitemap_discovery_report.md"

    discovered.to_csv(csv_path, index=False, encoding="utf-8")
    parquet_error = None
    try:
        discovered.to_parquet(parquet_path, index=False)
    except ImportError as exc:
        parquet_error = str(exc).splitlines()[0]
        parquet_path = None
    report_path.write_text(report, encoding="utf-8")
    return SitemapOutputs(csv_path, parquet_path, report_path, parquet_error)


def build_sitemap_report(discovered: pd.DataFrame) -> str:
    """Create a coverage report for sitemap discovery."""
    lines = [
        "# Sitemap Discovery Report",
        "",
        f"- Rows: {len(discovered):,}",
        f"- Sources: {discovered['source_id'].nunique() if not discovered.empty else 0:,}",
        f"- URLs: {discovered['url'].notna().sum() if not discovered.empty else 0:,}",
        f"- Error rows: {discovered['error'].notna().sum() if not discovered.empty else 0:,}",
        "",
        "## Coverage By Source",
        "",
    ]
    if discovered.empty:
        lines.append("_No rows._")
    else:
        with_dates = discovered.copy()
        with_dates["lastmod_date"] = pd.to_datetime(with_dates["lastmod"], errors="coerce", utc=True)
        summary = (
            with_dates.groupby(["source_id", "source_name"], dropna=False)
            .agg(
                rows=("url", "size"),
                urls=("url", lambda values: values.notna().sum()),
                errors=("error", lambda values: values.notna().sum()),
                earliest_lastmod=("lastmod_date", "min"),
                latest_lastmod=("lastmod_date", "max"),
                sitemap_files=("sitemap_url", "nunique"),
            )
            .reset_index()
        )
        summary["reaches_2018"] = summary["earliest_lastmod"].le(pd.Timestamp("2018-12-31", tz="UTC"))
        summary["reaches_2016"] = summary["earliest_lastmod"].le(pd.Timestamp("2016-12-31", tz="UTC"))
        summary = summary.sort_values(["reaches_2016", "reaches_2018", "urls"], ascending=[False, False, False])
        lines.append(markdown_table(summary.head(100)))

    lines.extend(["", "## Sample Rows", ""])
    if discovered.empty:
        lines.append("_No rows._")
    else:
        lines.append(
            markdown_table(
                discovered[["source_id", "url", "lastmod", "topic", "sitemap_url", "error"]].head(40)
            )
        )
    lines.append("")
    return "\n".join(lines)

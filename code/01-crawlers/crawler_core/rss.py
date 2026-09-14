"""RSS and Atom feed URL discovery for newspaper sources."""

from __future__ import annotations

import email.utils
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd

from crawler_core.capabilities import fetch, markdown_table


@dataclass(frozen=True)
class RssDiscoveryOutputs:
    """Paths written by RSS discovery."""

    discovered_csv: Path
    discovered_parquet: Path | None
    report_path: Path
    parquet_error: str | None = None


def load_rss_sources(
    capabilities_path: Path,
    *,
    strategy: str = "rss",
    include_any_rss: bool = False,
) -> pd.DataFrame:
    """Load sources to discover through RSS/Atom feeds."""
    capabilities = pd.read_csv(capabilities_path)
    if include_any_rss:
        mask = capabilities["rss_available"].astype(str).str.lower().isin({"true", "1"})
    else:
        mask = capabilities["recommended_strategy"].eq(strategy)
    return capabilities[mask].reset_index(drop=True)


def discover_rss_urls(
    sources: pd.DataFrame,
    *,
    source_ids: list[str] | None = None,
    limit_sources: int | None = None,
    timeout: float = 30.0,
    pause_seconds: float = 0.2,
) -> pd.DataFrame:
    """Discover article URLs from RSS/Atom feeds."""
    if source_ids:
        sources = sources[sources["source_id"].isin(source_ids)].reset_index(drop=True)
    if limit_sources is not None:
        sources = sources.head(limit_sources)

    rows: list[dict[str, object]] = []
    total_sources = len(sources)
    for i, source in sources.iterrows():
        source_id = source.get("source_id")
        feed_url = effective_rss_url(source)
        print(f"\n=== RSS source {i + 1}/{total_sources}: {source_id} ===")
        print(f"  {source_id}: reading feed {feed_url}")
        try:
            response = fetch(str(feed_url), timeout, profile="browser")
            source_rows = parse_rss_response(source, feed_url, response)
        except Exception as exc:
            print(f"!!! {source_id}: unexpected source failure: {type(exc).__name__}: {exc}")
            source_rows = [error_row(source, feed_url, pd.NA, f"{type(exc).__name__}: {exc}")]
        rows.extend(source_rows)
        urls = sum(1 for row in source_rows if pd.notna(row.get("url")))
        errors = sum(1 for row in source_rows if pd.notna(row.get("error")))
        print(f"=== Finished {source_id}: rows={len(source_rows):,}, urls={urls:,}, errors={errors:,} ===")
        if pause_seconds:
            import time

            time.sleep(pause_seconds)

    discovered = pd.DataFrame(rows)
    if not discovered.empty and {"source_id", "url"}.issubset(discovered.columns):
        discovered = discovered.drop_duplicates(["source_id", "url"], keep="last").reset_index(drop=True)
    return discovered


def effective_rss_url(source: pd.Series) -> object:
    """Return source-specific RSS URL, fixing repeated OEM feed probes when possible."""
    canonical_url = source.get("canonical_url")
    rss_url = source.get("rss_url")
    if pd.notna(canonical_url):
        parsed = urlparse(str(canonical_url))
        segments = [segment for segment in parsed.path.strip("/").split("/") if segment]
        if parsed.netloc.lower().endswith("oem.com.mx") and segments:
            return f"{parsed.scheme}://{parsed.netloc}/{segments[0]}/rss"
    if pd.notna(rss_url):
        return rss_url
    if pd.notna(canonical_url):
        return urljoin(str(canonical_url).rstrip("/") + "/", "feed/")
    return pd.NA


def parse_rss_response(source: pd.Series, feed_url: object, response: dict[str, object]) -> list[dict[str, object]]:
    """Parse a fetched RSS/Atom response into discovery rows."""
    status = response.get("status")
    if not isinstance(status, int) or status < 200 or status >= 300:
        error = response.get("error")
        if pd.isna(error):
            error = f"http_status_{status}"
        return [error_row(source, feed_url, status, error)]

    text = response.get("text") or ""
    try:
        root = ET.fromstring(str(text).encode("utf-8"))
    except ET.ParseError as exc:
        return [error_row(source, feed_url, status, f"ParseError: {exc}")]

    items = parse_rss_items(root, str(feed_url))
    if not items:
        return [error_row(source, feed_url, status, "no_feed_items_found")]
    return [url_row(source, item, feed_url, status) for item in items if item.get("url")]


def parse_rss_items(root: ET.Element, feed_url: str) -> list[dict[str, object]]:
    """Return normalized items from RSS, RDF RSS, or Atom XML."""
    root_name = tag_name(root)
    if root_name == "feed":
        return parse_atom_entries(root, feed_url)
    channel = first_child(root, "channel")
    parent = channel if channel is not None else root
    return [parse_rss_item(item, feed_url) for item in direct_children(parent, "item")]


def parse_rss_item(item: ET.Element, feed_url: str) -> dict[str, object]:
    """Normalize one RSS item."""
    url = first_child_text(item, "link")
    guid = first_child_text(item, "guid")
    return {
        "url": url or guid,
        "title": first_child_text(item, "title"),
        "summary": first_present_text(
            first_child_text(item, "description"),
            first_child_text(item, "encoded"),
            first_child_text(item, "summary"),
        ),
        "date_published": normalize_feed_date(
            first_present_text(
                first_child_text(item, "pubDate"),
                first_child_text(item, "published"),
                first_child_text(item, "date"),
            )
        ),
        "date_modified": normalize_feed_date(first_child_text(item, "updated")),
        "guid": guid,
        "feed_url": feed_url,
    }


def parse_atom_entries(root: ET.Element, feed_url: str) -> list[dict[str, object]]:
    """Normalize Atom entries."""
    rows = []
    for entry in direct_children(root, "entry"):
        rows.append(
            {
                "url": atom_entry_link(entry),
                "title": first_child_text(entry, "title"),
                "summary": first_present_text(first_child_text(entry, "summary"), first_child_text(entry, "content")),
                "date_published": normalize_feed_date(first_child_text(entry, "published")),
                "date_modified": normalize_feed_date(first_child_text(entry, "updated")),
                "guid": first_child_text(entry, "id"),
                "feed_url": feed_url,
            }
        )
    return rows


def atom_entry_link(entry: ET.Element) -> object:
    """Return the best Atom entry link."""
    alternate = None
    first = None
    for child in direct_children(entry, "link"):
        href = child.attrib.get("href")
        if not href:
            continue
        if first is None:
            first = href
        if child.attrib.get("rel", "alternate") == "alternate":
            alternate = href
            break
    return alternate or first or pd.NA


def url_row(source: pd.Series, item: dict[str, object], feed_url: object, status: object) -> dict[str, object]:
    """Return a discovered RSS URL row compatible with the HTML extractor."""
    date_published = item.get("date_published")
    date_modified = item.get("date_modified")
    return {
        "source_id": source.get("source_id"),
        "source_name": source.get("source_name"),
        "source_url": source.get("canonical_url"),
        "url": item.get("url"),
        "canonical_url": item.get("url"),
        "title": item.get("title"),
        "summary": item.get("summary"),
        "date_published": date_published,
        "lastmod": first_present_text(date_modified, date_published),
        "topic": pd.NA,
        "discovery_strategy": "rss",
        "sitemap_url": pd.NA,
        "rss_url": feed_url,
        "rss_status": status,
        "guid": item.get("guid"),
        "discovered_at": pd.Timestamp.utcnow().isoformat(),
        "status": status,
        "error": pd.NA,
    }


def error_row(source: pd.Series, feed_url: object, status: object, error: object) -> dict[str, object]:
    """Return an RSS discovery error row."""
    return {
        "source_id": source.get("source_id"),
        "source_name": source.get("source_name"),
        "source_url": source.get("canonical_url"),
        "url": pd.NA,
        "canonical_url": pd.NA,
        "title": pd.NA,
        "summary": pd.NA,
        "date_published": pd.NA,
        "lastmod": pd.NA,
        "topic": pd.NA,
        "discovery_strategy": "rss",
        "sitemap_url": pd.NA,
        "rss_url": feed_url,
        "rss_status": status,
        "guid": pd.NA,
        "discovered_at": pd.Timestamp.utcnow().isoformat(),
        "status": status,
        "error": error,
    }


def build_rss_report(discovered: pd.DataFrame) -> str:
    """Create a markdown report for RSS discovery."""
    lines = [
        "# RSS Discovery Report",
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
            .agg(rows=("source_id", "size"), urls=("url", lambda value: value.notna().sum()), errors=("error", lambda value: value.notna().sum()))
            .reset_index()
            .sort_values(["urls", "rows"], ascending=False)
        )
        lines.extend(["## By Source", "", markdown_table(summary), ""])
    return "\n".join(lines)


def write_rss_outputs(
    discovered: pd.DataFrame,
    report: str,
    discovery_dir: Path,
    reports_dir: Path,
) -> RssDiscoveryOutputs:
    """Write RSS discovery CSV/parquet and report files."""
    discovery_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    discovered_csv = discovery_dir / "discovered_urls_rss.csv"
    discovered_parquet = discovery_dir / "discovered_urls_rss.parquet"
    report_path = reports_dir / "rss_discovery_report.md"
    discovered.to_csv(discovered_csv, index=False, encoding="utf-8")
    parquet_error = None
    try:
        discovered.to_parquet(discovered_parquet, index=False)
    except ImportError as exc:
        discovered_parquet = None
        parquet_error = str(exc).splitlines()[0]
    report_path.write_text(report, encoding="utf-8")
    return RssDiscoveryOutputs(discovered_csv, discovered_parquet, report_path, parquet_error)


def tag_name(element: ET.Element) -> str:
    """Return an XML element's local tag name."""
    return element.tag.split("}", 1)[-1].lower()


def direct_children(element: ET.Element, wanted_name: str) -> list[ET.Element]:
    """Return direct children by local tag name."""
    wanted = wanted_name.lower()
    return [child for child in element if tag_name(child) == wanted]


def first_child(element: ET.Element, wanted_name: str) -> ET.Element | None:
    """Return the first direct child matching a local tag name."""
    children = direct_children(element, wanted_name)
    return children[0] if children else None


def first_child_text(element: ET.Element, wanted_name: str) -> object:
    """Return text from the first descendant with a local tag name."""
    wanted = wanted_name.lower()
    for child in element.iter():
        if child is not element and tag_name(child) == wanted and child.text:
            return child.text.strip()
    return pd.NA


def first_present_text(*values: object) -> object:
    """Return the first non-empty text-like value."""
    for value in values:
        try:
            if pd.isna(value):
                continue
        except (TypeError, ValueError):
            pass
        text = str(value).strip()
        if text:
            return text
    return pd.NA


def normalize_feed_date(value: object) -> object:
    """Normalize common feed date text to ISO if possible."""
    value = first_present_text(value)
    if pd.isna(value):
        return pd.NA
    try:
        parsed_email = email.utils.parsedate_to_datetime(str(value))
    except (TypeError, ValueError, IndexError):
        parsed_email = None
    if parsed_email is not None:
        return parsed_email.isoformat()
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return value
    return parsed.isoformat()

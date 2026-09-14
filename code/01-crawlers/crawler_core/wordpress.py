"""WordPress REST API URL discovery for crawler sources."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from urllib.parse import urlencode, urljoin

import pandas as pd

from crawler_core.capabilities import fetch, markdown_table


WP_POSTS_ENDPOINT = "/wp-json/wp/v2/posts"
WP_FIELDS = ",".join(
    [
        "id",
        "date",
        "date_gmt",
        "modified",
        "modified_gmt",
        "slug",
        "link",
        "title",
        "excerpt",
        "categories",
        "tags",
    ]
)


@dataclass(frozen=True)
class DiscoveryOutputs:
    """Paths written by WordPress discovery."""

    discovered_csv: Path
    discovered_parquet: Path | None
    report_path: Path
    parquet_error: str | None = None


def load_wordpress_sources(
    sources_path: Path,
    capabilities_path: Path,
    *,
    include_blocked: bool = False,
) -> pd.DataFrame:
    """Load sources with available WordPress APIs."""
    sources = pd.read_csv(sources_path)
    capabilities = pd.read_csv(capabilities_path)
    merged = sources.merge(
        capabilities[
            [
                "source_id",
                "wordpress_api_available",
                "wordpress_api_url",
                "recommended_strategy",
                "cloudflare_like",
            ]
        ],
        on="source_id",
        how="inner",
    )

    if include_blocked:
        mask = merged["wordpress_api_available"].astype(str).str.lower().isin({"true", "1"})
    else:
        mask = merged["recommended_strategy"].eq("wordpress_api")

    return merged[mask].reset_index(drop=True)


def discover_wordpress_urls(
    sources: pd.DataFrame,
    *,
    limit_sources: int | None = None,
    max_pages: int | None = 5,
    per_page: int = 100,
    timeout: float = 15.0,
    pause_seconds: float = 0.5,
    checkpoint_path: Path | None = None,
    initial_rows: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Discover article URLs from WordPress REST APIs."""
    if limit_sources is not None:
        sources = sources.head(limit_sources)

    rows: list[dict[str, object]] = []
    if initial_rows is not None and not initial_rows.empty:
        rows.extend(initial_rows.to_dict("records"))

    total_sources = len(sources)
    for i, source in sources.iterrows():
        page_mode = "all pages" if max_pages is None else f"max {max_pages} pages"
        print(
            f"\n=== Source {i + 1}/{total_sources}: {source['source_id']} "
            f"({source.get('source_name')}) | {page_mode} ==="
        )
        try:
            source_rows = discover_source_wordpress_urls(
                source,
                max_pages=max_pages,
                per_page=per_page,
                timeout=timeout,
                pause_seconds=pause_seconds,
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            print(f"!!! {source['source_id']}: unexpected source failure: {error}")
            source_rows = [
                error_row(
                    source,
                    discovery_url=str(source.get("canonical_url")),
                    status=pd.NA,
                    error=error,
                    page=pd.NA,
                )
            ]
        rows.extend(source_rows)
        usable_urls = sum(1 for row in source_rows if pd.notna(row.get("url")))
        errors = sum(1 for row in source_rows if pd.notna(row.get("error")))
        print(
            f"=== Finished {source['source_id']}: rows={len(source_rows):,}, "
            f"urls={usable_urls:,}, errors={errors:,}, "
            f"total_rows_so_far={len(rows):,} ==="
        )
        if pause_seconds:
            time.sleep(pause_seconds)

        if checkpoint_path is not None:
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            checkpoint_df = pd.DataFrame(rows)
            if not checkpoint_df.empty:
                checkpoint_df = checkpoint_df.drop_duplicates(["source_id", "url"], keep="last")
            checkpoint_df.to_csv(checkpoint_path, index=False, encoding="utf-8")
            print(f"Checkpoint saved: {checkpoint_path} ({len(checkpoint_df):,} rows)")

    discovered = pd.DataFrame(rows)
    if not discovered.empty:
        discovered = discovered.drop_duplicates(["source_id", "url"], keep="last").reset_index(drop=True)
    return discovered


def discover_source_wordpress_urls(
    source: pd.Series,
    *,
    max_pages: int | None,
    per_page: int,
    timeout: float,
    pause_seconds: float,
) -> list[dict[str, object]]:
    """Discover URLs for one WordPress source."""
    rows: list[dict[str, object]] = []
    base_url = str(source["canonical_url"])
    api_base = urljoin(base_url, WP_POSTS_ENDPOINT)
    page = 1
    source_id = source.get("source_id")
    total_urls = 0
    stop_reason = "unknown"
    source_complete = False
    last_page_requested = pd.NA

    while max_pages is None or page <= max_pages:
        params = {
            "per_page": per_page,
            "page": page,
            "orderby": "date",
            "order": "desc",
            "_fields": WP_FIELDS,
        }
        discovery_url = f"{api_base}?{urlencode(params)}"
        last_page_requested = page
        print(f"  {source_id}: requesting page {page} ({per_page} posts/page)")
        response = fetch(discovery_url, timeout)
        status = response["status"]
        text = response["text"] or ""

        if status in {400, 404} and "rest_post_invalid_page_number" in text:
            print(f"  {source_id}: page {page} is past the end of the archive; stopping")
            stop_reason = "invalid_page_number"
            source_complete = True
            break
        if not isinstance(status, int) or status < 200 or status >= 300:
            error = response["error"]
            if pd.isna(error):
                error = f"http_status_{status}"
            print(f"  {source_id}: page {page} failed with status={status}, error={error}; stopping")
            rows.append(error_row(source, discovery_url, status, error, page))
            stop_reason = "http_error"
            break

        try:
            posts = json.loads(text)
        except json.JSONDecodeError as exc:
            print(f"  {source_id}: page {page} returned invalid JSON ({exc}); stopping")
            rows.append(error_row(source, discovery_url, status, f"JSONDecodeError: {exc}", page))
            stop_reason = "json_error"
            break

        if not posts:
            print(f"  {source_id}: page {page} returned 0 posts; stopping")
            stop_reason = "empty_page"
            source_complete = True
            break
        if not isinstance(posts, list):
            print(f"  {source_id}: page {page} returned unexpected JSON shape; stopping")
            rows.append(error_row(source, discovery_url, status, "unexpected_json_shape", page))
            stop_reason = "unexpected_json_shape"
            break

        page_urls = 0
        for post in posts:
            row = post_to_row(source, post, discovery_url, page, status)
            if row["url"]:
                rows.append(row)
                page_urls += 1

        total_urls += page_urls
        print(
            f"  {source_id}: page {page} status={status}, "
            f"posts={len(posts):,}, urls_added={page_urls:,}, cumulative_urls={total_urls:,}"
        )

        if len(posts) < per_page:
            print(
                f"  {source_id}: page {page} returned fewer than {per_page} posts; "
                "assuming final page"
            )
            stop_reason = "short_final_page"
            source_complete = True
            break

        page += 1
        if pause_seconds:
            time.sleep(pause_seconds)

    if stop_reason == "unknown":
        stop_reason = "max_pages_reached"

    for row in rows:
        row["source_complete"] = source_complete
        row["source_stop_reason"] = stop_reason
        row["source_last_page_requested"] = last_page_requested
        row["source_max_pages_requested"] = max_pages if max_pages is not None else "all"

    return rows


def post_to_row(
    source: pd.Series,
    post: dict[str, object],
    discovery_url: str,
    page: int,
    status: object,
) -> dict[str, object]:
    """Convert a WordPress API post object to the standard discovery schema."""
    return {
        "source_id": source.get("source_id"),
        "source_name": source.get("source_name"),
        "source_url": source.get("canonical_url"),
        "url": post.get("link"),
        "canonical_url": post.get("link"),
        "wp_post_id": post.get("id"),
        "slug": post.get("slug"),
        "title": clean_html(get_nested(post, "title", "rendered")),
        "summary": clean_html(get_nested(post, "excerpt", "rendered")),
        "date_published": post.get("date"),
        "date_published_gmt": post.get("date_gmt"),
        "date_modified": post.get("modified"),
        "date_modified_gmt": post.get("modified_gmt"),
        "category_ids": join_ids(post.get("categories")),
        "tag_ids": join_ids(post.get("tags")),
        "discovery_strategy": "wordpress_api",
        "discovery_url": discovery_url,
        "discovery_page": page,
        "discovered_at": pd.Timestamp.utcnow().isoformat(),
        "status": status,
        "error": pd.NA,
        "source_complete": pd.NA,
        "source_stop_reason": pd.NA,
        "source_last_page_requested": pd.NA,
        "source_max_pages_requested": pd.NA,
    }


def error_row(
    source: pd.Series,
    discovery_url: str,
    status: object,
    error: object,
    page: int,
) -> dict[str, object]:
    """Return a discovery error row using the common schema."""
    return {
        "source_id": source.get("source_id"),
        "source_name": source.get("source_name"),
        "source_url": source.get("canonical_url"),
        "url": pd.NA,
        "canonical_url": pd.NA,
        "wp_post_id": pd.NA,
        "slug": pd.NA,
        "title": pd.NA,
        "summary": pd.NA,
        "date_published": pd.NA,
        "date_published_gmt": pd.NA,
        "date_modified": pd.NA,
        "date_modified_gmt": pd.NA,
        "category_ids": pd.NA,
        "tag_ids": pd.NA,
        "discovery_strategy": "wordpress_api",
        "discovery_url": discovery_url,
        "discovery_page": page,
        "discovered_at": pd.Timestamp.utcnow().isoformat(),
        "status": status,
        "error": error,
        "source_complete": pd.NA,
        "source_stop_reason": pd.NA,
        "source_last_page_requested": pd.NA,
        "source_max_pages_requested": pd.NA,
    }


def write_discovery_outputs(
    discovered: pd.DataFrame,
    report: str,
    discovery_dir: Path,
    reports_dir: Path,
) -> DiscoveryOutputs:
    """Write discovered URL outputs."""
    discovery_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    csv_path = discovery_dir / "discovered_urls_wordpress.csv"
    parquet_path = discovery_dir / "discovered_urls_wordpress.parquet"
    report_path = reports_dir / "wordpress_discovery_report.md"

    discovered.to_csv(csv_path, index=False, encoding="utf-8")
    parquet_error = None
    try:
        discovered.to_parquet(parquet_path, index=False)
    except ImportError as exc:
        parquet_error = str(exc).splitlines()[0]
        parquet_path = None
    report_path.write_text(report, encoding="utf-8")

    return DiscoveryOutputs(csv_path, parquet_path, report_path, parquet_error)


def build_wordpress_discovery_report(discovered: pd.DataFrame) -> str:
    """Create a compact discovery report."""
    capped_sources = 0
    if not discovered.empty and "source_stop_reason" in discovered.columns:
        capped_sources = int(
            discovered.drop_duplicates("source_id")["source_stop_reason"]
            .eq("max_pages_reached")
            .sum()
        )
    elif not discovered.empty and "error" in discovered.columns:
        grouped = discovered[discovered["url"].notna()].groupby("source_id")["discovery_page"].max()
        capped_sources = int((grouped >= 5).sum())

    lines = [
        "# WordPress URL Discovery Report",
        "",
        f"- Rows: {len(discovered):,}",
        f"- Sources: {discovered['source_id'].nunique() if not discovered.empty else 0:,}",
        f"- URLs: {discovered['url'].notna().sum() if not discovered.empty else 0:,}",
        f"- Error rows: {discovered['error'].notna().sum() if not discovered.empty else 0:,}",
        f"- Sources that stopped at configured page cap: {capped_sources:,}",
        "",
        "## URLs By Source",
        "",
    ]

    if discovered.empty:
        lines.append("_No rows._")
    else:
        report_df = discovered.copy()
        report_df["date_published_report"] = pd.to_datetime(
            report_df["date_published"],
            errors="coerce",
            utc=True,
        )
        report_df.loc[
            report_df["date_published_report"].lt(pd.Timestamp("1900-01-01", tz="UTC")),
            "date_published_report",
        ] = pd.NaT
        if "source_complete" not in report_df.columns:
            report_df["source_complete"] = pd.NA
        if "source_stop_reason" not in report_df.columns:
            report_df["source_stop_reason"] = pd.NA
        if "source_last_page_requested" not in report_df.columns:
            report_df["source_last_page_requested"] = pd.NA

        summary = (
            report_df.groupby(["source_id", "source_name"], dropna=False)
            .agg(
                rows=("url", "size"),
                urls=("url", lambda values: values.notna().sum()),
                min_date=("date_published_report", "min"),
                max_date=("date_published_report", "max"),
                errors=("error", lambda values: values.notna().sum()),
                complete=("source_complete", first_nonmissing),
                stop_reason=("source_stop_reason", first_nonmissing),
                last_page=("source_last_page_requested", max_numeric),
            )
            .reset_index()
            .sort_values(["urls", "source_id"], ascending=[False, True])
        )
        lines.append(markdown_table(summary.head(100)))

    lines.extend(["", "## Sample Rows", ""])
    if discovered.empty:
        lines.append("_No rows._")
    else:
        lines.append(
            markdown_table(
                discovered[
                    [
                        "source_id",
                        "url",
                        "date_published",
                        "title",
                        "discovery_page",
                        "error",
                    ]
                ].head(30)
            )
        )
    lines.append("")
    return "\n".join(lines)


def first_nonmissing(values: pd.Series) -> object:
    """Return the first non-missing grouped value."""
    present = values.dropna()
    return present.iloc[0] if not present.empty else pd.NA


def max_numeric(values: pd.Series) -> object:
    """Return a tolerant numeric max for mixed object columns."""
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    return numeric.max() if not numeric.empty else pd.NA


def clean_html(value: object) -> str | object:
    """Remove simple HTML tags and entities from rendered WordPress fields."""
    if value is None or pd.isna(value):
        return pd.NA
    text = re.sub(r"<[^>]+>", " ", str(value))
    return re.sub(r"\s+", " ", unescape(text)).strip()


def get_nested(data: dict[str, object], first: str, second: str) -> object:
    value = data.get(first)
    if isinstance(value, dict):
        return value.get(second)
    return pd.NA


def join_ids(value: object) -> object:
    if isinstance(value, list):
        return ";".join(str(item) for item in value)
    return pd.NA

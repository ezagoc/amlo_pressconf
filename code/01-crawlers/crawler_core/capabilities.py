"""Shallow capability probes for newspaper source URLs."""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urljoin

import pandas as pd


USER_AGENT = (
    "AMLOPressConfResearchBot/0.1 "
    "(academic research; polite capability probe; contact: local project)"
)
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
BODY_TEXT_LIMIT = 5_000_000
SITEMAP_PATHS = (
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/wp-sitemap.xml",
    "/news-sitemap.xml",
    "/sitemaps/index.xml",
)
FEED_PATHS = (
    "/feed/",
    "/rss/",
    "/rss.xml",
)
WP_POSTS_PATH = "/wp-json/wp/v2/posts?per_page=1"


@dataclass(frozen=True)
class ProbeOutputs:
    """Paths written by the capability probe."""

    capabilities_csv: Path
    capabilities_parquet: Path | None
    report_path: Path
    parquet_error: str | None = None


def load_sources(sources_path: Path, candidates_only: bool = True) -> pd.DataFrame:
    """Load registry sources and optionally keep only first-wave candidates."""
    df = pd.read_csv(sources_path)
    if candidates_only:
        df = df[df["crawl_candidate"].astype(str).str.lower().isin({"true", "1"})]
    return df.reset_index(drop=True)


def probe_sources(
    sources: pd.DataFrame,
    *,
    limit: int | None = None,
    timeout: float = 10.0,
    pause_seconds: float = 0.5,
) -> pd.DataFrame:
    """Run shallow HTTP capability probes for source rows."""
    rows = []

    if limit is not None:
        sources = sources.head(limit)

    for i, row in sources.iterrows():
        result = probe_source(row, timeout=timeout)
        rows.append(result)
        print(
            f"[{i + 1}/{len(sources)}] {result['source_id']} "
            f"status={result['homepage_status']} strategy={result['recommended_strategy']}"
        )
        if pause_seconds:
            time.sleep(pause_seconds)

    return pd.DataFrame(rows)


def probe_source(row: pd.Series, *, timeout: float) -> dict[str, object]:
    """Probe one source URL for structured crawl surfaces."""
    base_url = row.get("canonical_url")
    result: dict[str, object] = {
        "source_id": row.get("source_id"),
        "source_name": row.get("source_name"),
        "canonical_url": base_url,
        "domain": row.get("domain"),
        "platform_cluster": row.get("platform_cluster"),
        "crawl_strategy_hint": row.get("crawl_strategy_hint"),
        "probe_timestamp": pd.Timestamp.utcnow().isoformat(),
        "homepage_status": pd.NA,
        "homepage_final_url": pd.NA,
        "homepage_content_type": pd.NA,
        "homepage_title": pd.NA,
        "homepage_error": pd.NA,
        "cloudflare_like": False,
        "paywall_like": False,
        "has_json_ld": False,
        "wordpress_footprint": False,
        "wordpress_api_status": pd.NA,
        "wordpress_api_available": False,
        "wordpress_api_url": pd.NA,
        "sitemap_status": pd.NA,
        "sitemap_available": False,
        "sitemap_url": pd.NA,
        "rss_status": pd.NA,
        "rss_available": False,
        "rss_url": pd.NA,
        "robots_status": pd.NA,
        "robots_available": False,
        "robots_url": pd.NA,
        "category_hint_count": 0,
        "category_hints": pd.NA,
        "recommended_strategy": "unprobed",
    }

    if pd.isna(base_url):
        result["homepage_error"] = "missing_url"
        result["recommended_strategy"] = "no_url"
        return result

    homepage = fetch(str(base_url), timeout)
    result.update(
        {
            "homepage_status": homepage["status"],
            "homepage_final_url": homepage["final_url"],
            "homepage_content_type": homepage["content_type"],
            "homepage_error": homepage["error"],
        }
    )

    text = homepage["text"] or ""
    result["homepage_title"] = extract_title(text)
    result["cloudflare_like"] = is_cloudflare_like(homepage["status"], text)
    result["paywall_like"] = is_paywall_like(text)
    result["has_json_ld"] = has_json_ld(text)
    result["wordpress_footprint"] = has_wordpress_footprint(text)
    hints = category_hints(text, str(base_url))
    result["category_hint_count"] = len(hints)
    result["category_hints"] = "; ".join(hints[:10]) if hints else pd.NA

    robots = fetch(urljoin(str(base_url), "/robots.txt"), timeout)
    result["robots_status"] = robots["status"]
    result["robots_available"] = is_ok(robots["status"]) and bool(robots["text"])
    result["robots_url"] = robots["final_url"] or urljoin(str(base_url), "/robots.txt")

    wp_url = urljoin(str(base_url), WP_POSTS_PATH)
    wp = fetch(wp_url, timeout)
    result["wordpress_api_status"] = wp["status"]
    result["wordpress_api_available"] = is_wordpress_posts_response(wp["status"], wp["text"])
    result["wordpress_api_url"] = wp["final_url"] or wp_url

    sitemap = first_available_xml(str(base_url), SITEMAP_PATHS, timeout)
    result["sitemap_status"] = sitemap["status"]
    result["sitemap_available"] = sitemap["available"]
    result["sitemap_url"] = sitemap["url"]

    feed = first_available_feed(str(base_url), FEED_PATHS, timeout)
    result["rss_status"] = feed["status"]
    result["rss_available"] = feed["available"]
    result["rss_url"] = feed["url"]

    result["recommended_strategy"] = recommend_strategy(result)
    return result


def write_probe_outputs(
    capabilities: pd.DataFrame,
    report: str,
    capabilities_dir: Path,
    reports_dir: Path,
) -> ProbeOutputs:
    """Write capability probe outputs."""
    capabilities_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    csv_path = capabilities_dir / "crawl_capabilities.csv"
    parquet_path = capabilities_dir / "crawl_capabilities.parquet"
    report_path = reports_dir / "capability_report.md"

    capabilities.to_csv(csv_path, index=False, encoding="utf-8")
    parquet_error = None
    try:
        capabilities.to_parquet(parquet_path, index=False)
    except ImportError as exc:
        parquet_error = str(exc).splitlines()[0]
        parquet_path = None
    report_path.write_text(report, encoding="utf-8")

    return ProbeOutputs(csv_path, parquet_path, report_path, parquet_error)


def build_capability_report(capabilities: pd.DataFrame) -> str:
    """Create a compact markdown report from probe results."""
    lines = [
        "# Crawler Capability Probe Report",
        "",
        f"- Probed sources: {len(capabilities):,}",
        f"- WordPress API available: {capabilities['wordpress_api_available'].sum():,}",
        f"- Sitemap available: {capabilities['sitemap_available'].sum():,}",
        f"- RSS available: {capabilities['rss_available'].sum():,}",
        f"- Cloudflare-like or blocked: {capabilities['cloudflare_like'].sum():,}",
        f"- Paywall-like markers: {capabilities['paywall_like'].sum():,}",
        "",
        "## Recommended Strategies",
        "",
        markdown_table(
            capabilities["recommended_strategy"]
            .fillna("<missing>")
            .value_counts()
            .rename_axis("recommended_strategy")
            .reset_index(name="rows")
        ),
        "",
        "## HTTP Statuses",
        "",
        markdown_table(
            capabilities["homepage_status"]
            .fillna("<missing>")
            .astype(str)
            .value_counts()
            .rename_axis("homepage_status")
            .reset_index(name="rows")
        ),
        "",
        "## Probe Details",
        "",
        markdown_table(
            capabilities[
                [
                    "source_id",
                    "source_name",
                    "homepage_status",
                    "wordpress_api_available",
                    "sitemap_available",
                    "rss_available",
                    "cloudflare_like",
                    "recommended_strategy",
                ]
            ].head(100)
        ),
        "",
    ]
    return "\n".join(lines)


def fetch(
    url: str,
    timeout: float,
    body_text_limit: int = BODY_TEXT_LIMIT,
    *,
    profile: str = "default",
    headers: list[str] | None = None,
    referer: str | None = None,
) -> dict[str, object]:
    """Fetch a URL with curl and return bounded response metadata and text."""
    with TemporaryDirectory() as tmp_dir:
        body_path = Path(tmp_dir) / "body.txt"
        completed = run_curl(
            url,
            body_path,
            timeout,
            insecure=False,
            profile=profile,
            headers=headers,
            referer=referer,
        )
        if isinstance(completed, subprocess.CompletedProcess) and should_retry_insecure(completed):
            completed = run_curl(
                url,
                body_path,
                timeout,
                insecure=True,
                profile=profile,
                headers=headers,
                referer=referer,
            )

        if not isinstance(completed, subprocess.CompletedProcess):
            return {
                "status": pd.NA,
                "final_url": pd.NA,
                "content_type": pd.NA,
                "text": "",
                "error": completed,
            }
        stdout = completed.stdout.strip()
        parts = stdout.split("\t")
        status = int(parts[0]) if parts and parts[0].isdigit() else pd.NA
        final_url = parts[1] if len(parts) > 1 and parts[1] else pd.NA
        content_type = parts[2] if len(parts) > 2 and parts[2] else pd.NA
        text = ""
        if body_path.exists():
            text = body_path.read_text(encoding="utf-8", errors="ignore")[:body_text_limit]
        error = pd.NA
        if completed.returncode != 0:
            error = completed.stderr.strip() or f"curl_exit_{completed.returncode}"
        return {
            "status": status,
            "final_url": final_url,
            "content_type": content_type,
            "text": text,
            "error": error,
        }


def run_curl(
    url: str,
    body_path: Path,
    timeout: float,
    *,
    insecure: bool,
    profile: str = "default",
    headers: list[str] | None = None,
    referer: str | None = None,
) -> subprocess.CompletedProcess[str] | str:
    """Run curl once, optionally with TLS certificate verification disabled."""
    user_agent = BROWSER_USER_AGENT if profile in {"browser", "ajax"} else USER_AGENT
    command = [
        "curl.exe",
        "--ssl-no-revoke",
        "-L",
        "-sS",
        "--compressed",
        "--max-time",
        str(timeout),
        "-A",
        user_agent,
        "-o",
        str(body_path),
        "-w",
        "%{http_code}\t%{url_effective}\t%{content_type}",
    ]
    if profile == "browser":
        command.extend(
            [
                "-H",
                "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "-H",
                "Accept-Language: es-MX,es;q=0.9,en-US;q=0.7,en;q=0.6",
                "-H",
                "Cache-Control: no-cache",
                "-H",
                "Pragma: no-cache",
                "-H",
                "Upgrade-Insecure-Requests: 1",
            ]
        )
    elif profile == "ajax":
        command.extend(
            [
                "-H",
                "Accept: text/html, */*; q=0.01",
                "-H",
                "Accept-Language: es-MX,es;q=0.9,en-US;q=0.7,en;q=0.6",
                "-H",
                "Cache-Control: no-cache",
                "-H",
                "Pragma: no-cache",
                "-H",
                "X-Requested-With: XMLHttpRequest",
                "-H",
                "Sec-Fetch-Site: same-origin",
                "-H",
                "Sec-Fetch-Mode: cors",
                "-H",
                "Sec-Fetch-Dest: empty",
            ]
        )
    if referer:
        command.extend(["-e", referer])
    for header in headers or []:
        command.extend(["-H", header])
    if insecure:
        command.insert(2, "--insecure")
    command.append(url)
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout + 5,
        )
    except subprocess.TimeoutExpired:
        return f"TimeoutExpired: curl exceeded {timeout + 5:.1f}s for {url}"


def should_retry_insecure(completed: subprocess.CompletedProcess[str]) -> bool:
    """Return True for curl TLS failures that may be Schannel/cert-chain specific."""
    if completed.returncode == 0:
        return False
    message = (completed.stderr or "").lower()
    retry_markers = (
        "schannel",
        "ssl",
        "tls",
        "certificate",
        "cert",
        "secur",
        "acquirecredentialshandle",
    )
    return any(marker in message for marker in retry_markers)


def first_available_xml(base_url: str, paths: tuple[str, ...], timeout: float) -> dict[str, object]:
    """Return the first endpoint that looks like an XML sitemap."""
    last_status = pd.NA
    last_url = pd.NA
    for path in paths:
        url = urljoin(base_url, path)
        response = fetch(url, timeout)
        last_status = response["status"]
        last_url = response["final_url"] or url
        if is_ok(response["status"]) and looks_like_sitemap(response["text"]):
            return {"available": True, "status": response["status"], "url": last_url}
    return {"available": False, "status": last_status, "url": last_url}


def first_available_feed(base_url: str, paths: tuple[str, ...], timeout: float) -> dict[str, object]:
    """Return the first endpoint that looks like RSS or Atom."""
    last_status = pd.NA
    last_url = pd.NA
    for path in paths:
        url = urljoin(base_url, path)
        response = fetch(url, timeout)
        last_status = response["status"]
        last_url = response["final_url"] or url
        if is_ok(response["status"]) and looks_like_feed(response["text"]):
            return {"available": True, "status": response["status"], "url": last_url}
    return {"available": False, "status": last_status, "url": last_url}


def is_ok(status: object) -> bool:
    return isinstance(status, int) and 200 <= status < 300


def extract_title(text: str) -> str | object:
    if not text:
        return pd.NA
    match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.I | re.S)
    if not match:
        return pd.NA
    title = re.sub(r"<[^>]+>", " ", match.group(1))
    return re.sub(r"\s+", " ", unescape(title)).strip()


def is_cloudflare_like(status: object, text: str) -> bool:
    lowered = text.lower()
    markers = (
        "just a moment",
        "cf-browser-verification",
        "cloudflare",
        "challenge-platform",
        "checking your browser",
    )
    return status in {403, 429} or any(marker in lowered for marker in markers)


def is_paywall_like(text: str) -> bool:
    lowered = strip_accents(text.lower())
    markers = (
        "paywall",
        "suscribete",
        "suscripcion",
        "subscriber only",
        "solo suscriptores",
        "contenido exclusivo",
        "inicia sesion para continuar",
    )
    return any(marker in lowered for marker in markers)


def strip_accents(value: str) -> str:
    import unicodedata

    return "".join(
        char
        for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )


def has_json_ld(text: str) -> bool:
    return 'type="application/ld+json"' in text.lower()


def has_wordpress_footprint(text: str) -> bool:
    lowered = text.lower()
    return "wp-content" in lowered or "wp-json" in lowered or "wp-includes" in lowered


def is_wordpress_posts_response(status: object, text: str) -> bool:
    return is_ok(status) and text.lstrip().startswith("[") and '"date"' in text[:3000]


def looks_like_sitemap(text: object) -> bool:
    if not isinstance(text, str):
        return False
    sample = text[:3000].lower()
    return "<urlset" in sample or "<sitemapindex" in sample


def looks_like_feed(text: object) -> bool:
    if not isinstance(text, str):
        return False
    sample = text[:3000].lower()
    return "<rss" in sample or "<feed" in sample


def category_hints(text: str, base_url: str) -> list[str]:
    """Extract a short list of likely category/archive links from homepage HTML."""
    if not text:
        return []
    hints = []
    patterns = ("/category/", "/categoria/", "/seccion/", "/tag/", "/archivo", "/noticias/")
    for match in re.finditer(r"""href=["']([^"']+)["']""", text, flags=re.I):
        href = unescape(match.group(1)).strip()
        if any(pattern in href.lower() for pattern in patterns):
            full_url = urljoin(base_url, href)
            if full_url not in hints:
                hints.append(full_url)
        if len(hints) >= 25:
            break
    return hints


def recommend_strategy(result: dict[str, object]) -> str:
    """Choose a practical first crawl strategy from probe results."""
    if result.get("cloudflare_like"):
        return "manual_or_playwright_review"
    if result.get("wordpress_api_available"):
        return "wordpress_api"
    if result.get("sitemap_available"):
        return "sitemap"
    if result.get("rss_available"):
        return "rss"
    hint = str(result.get("crawl_strategy_hint") or "")
    if hint.startswith("platform_adapter:"):
        return hint
    if int(result.get("category_hint_count") or 0) > 0:
        return "category_pagination"
    if is_ok(result.get("homepage_status")):
        return "custom_html_probe"
    return "unreachable_or_error"


def markdown_table(df: pd.DataFrame) -> str:
    """Render a small DataFrame as a GitHub-compatible Markdown table."""
    if df.empty:
        return "_No rows._"
    formatted = df.astype("object").where(pd.notna(df), "").astype(str)
    headers = list(formatted.columns)
    rows = formatted.values.tolist()

    def clean(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ")

    output = [
        "| " + " | ".join(clean(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        output.append("| " + " | ".join(clean(value) for value in row) + " |")
    return "\n".join(output)

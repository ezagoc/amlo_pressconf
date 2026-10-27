"""Polemon (polemon.mx): collect the 2015-2025 archive through the WordPress REST API and export it.

Polemon is a WordPress site, but it has its own adapter instead of the generic discover/extract
pipeline: posts are listed by local publication year, 100 full post objects per request, so one
pass collects the whole archive (14,809 posts in 196 requests) and every response is kept
unchanged for audit.

Access rules agreed for this source (2026-10-26): WordPress REST API only (no article pages),
2.5 s between requests, and stop at once on a Cloudflare / rate-limit block or after 3 errors in
a row, without trying any other access method. Deleted posts are not recovered.

Steps (run through scripts/crawl_polemon_articles.py):

    collect  raw/posts/<year>/page_NNN.json, raw/categories, raw/users, requests.jsonl
    sitemap  raw/sitemap/*, plus API links dated outside 2015-2025 (for the reconciliation)
    build    polemon_posts.parquet, monthly_counts.csv, sitemap reconciliation (offline)
    clean    polemon_posts_clean.parquet and excluded_invalid.csv (offline)
    export   polemon/articles_part_000001.parquet.gzip in the WordPress article schema, with
             manifest.json, README.md and audit/ (offline)
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlencode, urlparse

import pandas as pd

from crawler_core.wordpress import clean_html
from crawler_core.wordpress_articles import base_article_row, normalize_articles_for_output


SOURCE_ID = "polemon"
SOURCE_NAME = "Polemon"
SITE = "https://polemon.mx"
SOURCE_URL = f"{SITE}/"
API = f"{SITE}/wp-json/wp/v2"
YEARS = range(2015, 2026)
FIRST_DATE, LAST_DATE = "2015-01-01", "2025-12-31"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0 Safari/537.36"
)
CURL = "curl.exe" if sys.platform == "win32" else "curl"
MAX_TRIES = 3
MAX_CONSECUTIVE_ERRORS = 3
PART_ROWS = 50_000  # same chunk size as scripts/export_wordpress_articles_by_source.py

# Same columns, in the same order, as the WordPress article parts under crawler/articles/<source_id>/.
WORDPRESS_ARTICLE_COLUMNS = [
    *base_article_row(pd.Series(dtype=object)).keys(),
    "category_names",
    "tag_names",
]


class Stop(Exception):
    """Collection must halt and be reported; no other access method is tried."""


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def curl_fetch(url: str, body_path: Path, header_path: Path, timeout: float = 90.0) -> tuple[int, int]:
    """Fetch one URL with curl; returns (HTTP status, curl exit code)."""
    proc = subprocess.run(
        [CURL, "-s", "-L", "--compressed", "-m", str(int(timeout)), "-A", USER_AGENT,
         "-D", str(header_path), "-o", str(body_path), "-w", "%{http_code}", url],
        capture_output=True,
        text=True,
    )
    return int(proc.stdout.strip() or 0), proc.returncode


class Client:
    """Polite API client: fixed pause, raw responses saved unchanged, every request logged."""

    def __init__(self, state_dir: Path, pause: float, fetcher: Callable[[str, Path, Path], tuple[int, int]] = curl_fetch):
        self.raw, self.ledger, self.pause, self.fetcher = state_dir / "raw", state_dir / "requests.jsonl", pause, fetcher
        self.last, self.errors_in_a_row, self.n = 0.0, 0, 0

    def done(self, rel: str) -> bool:
        return (self.raw / rel).exists()

    def get(self, url: str, rel: str, ok: tuple[int, ...] = (200,), validate=None) -> tuple[int, bytes, dict]:
        target = self.raw / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(1, MAX_TRIES + 1):
            wait = self.pause - (time.time() - self.last)
            if wait > 0:
                time.sleep(wait)
            tmp, hdr = target.with_name(target.name + ".part"), target.with_name(target.name + ".headers")
            fetched_at = now()
            status, rc = self.fetcher(url, tmp, hdr)
            self.last, self.n = time.time(), self.n + 1
            data = tmp.read_bytes() if tmp.exists() else b""
            headers = read_headers(hdr)
            wp_error = data[:10].lstrip().startswith(b'{"code"')
            blocked = (
                status in (429, 503)
                or (status == 403 and not wp_error)
                or b"Just a moment" in data[:5000]
                or b"cf-chl" in data[:8000]
                or b"challenge-platform" in data[:8000]
            )
            problem = None
            if blocked:
                problem = "blocked"
            elif rc != 0 or status not in ok:
                problem = f"curl_rc={rc} http={status}"
            elif validate and status == 200:
                problem = validate(data)
            entry = {
                "url": url, "file": rel, "fetched_at_utc": fetched_at, "attempt": attempt, "status": status,
                "curl_rc": rc, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                "x_wp_total": headers.get("x-wp-total"), "x_wp_totalpages": headers.get("x-wp-totalpages"),
                "server": headers.get("server"), "cf_ray": headers.get("cf-ray"), "problem": problem,
            }
            with self.ledger.open("a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            if problem is None:
                tmp.replace(target)
                self.errors_in_a_row = 0
                return status, data, headers
            tmp.replace(target.with_name(f"{target.name}.failed{attempt}"))
            if blocked:
                raise Stop(f"blocked (HTTP {status}) at {url}")
            self.errors_in_a_row += 1
            print(f"  error {self.errors_in_a_row} in a row: {problem} at {url}", flush=True)
            if self.errors_in_a_row >= MAX_CONSECUTIVE_ERRORS:
                raise Stop(f"{self.errors_in_a_row} consecutive errors, last: {problem} at {url}")
        raise Stop(f"gave up after {MAX_TRIES} tries at {url}")


def read_headers(path: Path) -> dict[str, str]:
    headers: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="latin-1").splitlines():
            key, sep, value = line.partition(":")
            if sep:
                headers[key.strip().lower()] = value.strip()
    return headers


def json_list(data: bytes) -> str | None:
    try:
        return None if isinstance(json.loads(data), list) else "response is not a JSON list"
    except ValueError:
        return "response is not valid JSON"


def api_url(path: str, **params: object) -> str:
    return f"{API}/{path}?{urlencode(params)}"


def paged(client: Client, path: str, folder: str, **params: object) -> list[str]:
    """Fetch every page of a WordPress list endpoint; returns the saved page files."""
    pages, page, total_pages = [], 1, None
    while True:
        rel = f"{folder}/page_{page:03d}.json"
        if client.done(rel):
            total = read_headers(client.raw / (rel + ".headers")).get("x-wp-totalpages")
            total_pages = int(total) if total else total_pages
        else:
            _, _, headers = client.get(api_url(path, per_page=100, page=page, **params), rel, validate=json_list)
            total_pages = int(headers.get("x-wp-totalpages") or 1)
            print(f"  {folder} page {page}/{total_pages} (total {headers.get('x-wp-total')})", flush=True)
        pages.append(rel)
        if page >= (total_pages or 1):
            return pages
        page += 1


def collect_posts(state_dir: Path, pause: float, client: Client | None = None) -> None:
    """Posts for each year by local publication date, then categories and users."""
    client = client or Client(state_dir, pause)
    for year in YEARS:
        # `after` and `before` are exclusive and compare the local publication date.
        paged(client, "posts", f"posts/{year}", orderby="id", order="asc",
              after=f"{year - 1}-12-31T23:59:59", before=f"{year + 1}-01-01T00:00:00")
    paged(client, "categories", "categories", orderby="id", order="asc")
    rel = "users/page_001.json"
    if not client.done(rel) and not any((client.raw / "users").glob("page_001.json.status*")):
        status, _, headers = client.get(api_url("users", per_page=100, page=1, orderby="id", order="asc"), rel,
                                        ok=(200, 401, 403, 404))
        if status != 200:
            # Keep the refusal as evidence, under a name `build` does not read as a user list.
            (client.raw / rel).replace(client.raw / "users" / f"page_001.json.status{status}")
            print(f"  users endpoint answered HTTP {status}; authors come from Yoast metadata", flush=True)
        elif int(headers.get("x-wp-totalpages") or 1) > 1:
            paged(client, "users", "users", orderby="id", order="asc")
    print(f"collect done, {client.n} requests this run", flush=True)


SITEMAP_CANDIDATES = ["sitemap.xml", "wp-sitemap.xml", "sitemap_index.xml"]
SKIP_SITEMAP = re.compile(r"image|video|news|categor|tag|author|page-sitemap|taxonom|users", re.I)
POST_SITEMAP = re.compile(r"post-sitemap\d*\.xml$|posts-post-\d+\.xml$")


def sitemap_locs(data: bytes) -> list[str]:
    return [html.unescape(m.decode("utf-8", "replace")) for m in re.findall(rb"<loc>\s*([^<]+?)\s*</loc>", data)]


def collect_sitemap(state_dir: Path, pause: float, client: Client | None = None) -> None:
    """Post sitemaps, plus API links dated outside 2015-2025 so they are not reported as missing."""
    client = client or Client(state_dir, pause)
    index_rel = None
    for name in SITEMAP_CANDIDATES:
        rel = f"sitemap/{name}"
        if client.done(rel):
            index_rel = rel
            break
        status, data, _ = client.get(f"{SITE}/{name}", rel, ok=(200, 404))
        if status == 200 and b"<loc>" in data:
            index_rel = rel
            break
    if index_rel is None:
        raise Stop("no sitemap found at " + ", ".join(SITEMAP_CANDIDATES))
    queue, seen = [index_rel], set()
    while queue:
        rel = queue.pop(0)
        data = (client.raw / rel).read_bytes()
        if b"<sitemapindex" not in data[:2000]:
            continue
        for child in sitemap_locs(data):
            name = urlparse(child).path.strip("/").replace("/", "_")
            if child in seen or SKIP_SITEMAP.search(name):
                continue
            seen.add(child)
            child_rel = f"sitemap/{name}"
            if not client.done(child_rel):
                client.get(child, child_rel)
                print(f"  sitemap {name}", flush=True)
            queue.append(child_rel)
    paged(client, "posts", "posts_outside/before_2015", orderby="id", order="asc",
          before="2015-01-01T00:00:00", _fields="id,date,date_gmt,link,slug")
    paged(client, "posts", "posts_outside/after_2025", orderby="id", order="asc",
          after="2025-12-31T23:59:59", _fields="id,date,date_gmt,link,slug")
    print(f"sitemap done, {client.n} requests this run", flush=True)


# Body text: share buttons, related-post widgets and Advanced Ads placements (image-only banners)
# are dropped before the text is taken.
DROP_SELECTORS = ["script", "style", ".sharedaddy", ".jp-relatedposts", "[class*=entity-placement]"]
BLOCK_TAGS = ["p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "figcaption", "tr"]


def body_text(fragment: str) -> tuple[str, int]:
    """Plain article text from rendered content HTML, and the number of ad placements removed."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(fragment or "", "lxml")
    removed = 0
    for selector in DROP_SELECTORS:
        for node in soup.select(selector):
            removed += 1 if "entity-placement" in selector else 0
            node.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for block in soup.find_all(BLOCK_TAGS):
        block.insert_after("\n")
    text = soup.get_text()
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{2,}", "\n\n", text).strip(), removed


def body_media(fragment: str) -> tuple[list[str], list[str], int]:
    """In-body image URLs (ad placements excluded), embedded frame/video URLs, embedded tweet count."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(fragment or "", "lxml")
    for node in soup.select("[class*=entity-placement]"):
        node.decompose()
    images: list[str] = []
    for img in soup.find_all("img"):
        url = img.get("data-orig-file") or img.get("src") or ""
        if url and not url.startswith("data:") and url not in images:
            images.append(url)
    embeds: list[str] = []
    for node in soup.find_all(["iframe", "video", "source"]):
        url = node.get("src") or node.get("data-src") or ""
        if url and url not in embeds:
            embeds.append(url)
    return images, embeds, len(soup.select("blockquote.twitter-tweet"))


def load_pages(raw: Path, pattern: str) -> list[tuple[str, list]]:
    return [(p.relative_to(raw).as_posix(), json.loads(p.read_bytes())) for p in sorted(raw.glob(pattern))]


def load_ledger(state_dir: Path) -> list[dict]:
    return [json.loads(line) for line in (state_dir / "requests.jsonl").read_text(encoding="utf-8").splitlines()]


def build_posts_table(state_dir: Path, save: bool = True) -> pd.DataFrame:
    """One row per post from the saved API pages (offline); `save` writes polemon_posts.parquet."""
    raw = state_dir / "raw"
    ok = {e["file"]: e for e in load_ledger(state_dir) if e["problem"] is None}
    categories: dict[int, str] = {}
    for _, rows in load_pages(raw, "categories/page_*.json"):
        categories.update({r["id"]: html.unescape(r["name"]) for r in rows})
    users: dict[int, str] = {}
    for _, rows in load_pages(raw, "users/page_*.json"):
        users.update({r["id"]: html.unescape(r.get("name") or "") for r in rows})

    records, seen = [], set()
    for year in YEARS:
        for rel, rows in load_pages(raw, f"posts/{year}/page_*.json"):
            for post in rows:
                if post["id"] in seen:
                    continue
                seen.add(post["id"])
                content = post["content"]["rendered"]
                text, ads = body_text(content)
                images, embeds, tweets = body_media(content)
                category_ids = post.get("categories") or []
                category_names = [categories.get(i) for i in category_ids]
                # /users answers 401, but Yoast SEO puts the author's display name in every post;
                # it matched the byline on all 160 article pages checked by hand.
                author = users.get(post.get("author")) or ""
                author_source = "users_endpoint" if author else ""
                yoast = post.get("yoast_head_json") or {}
                if not author and yoast.get("author"):
                    author, author_source = yoast["author"], "yoast_head_json.author"
                records.append({
                    "post_id": post["id"],
                    "url": post["link"],
                    "title": html.unescape(re.sub(r"<[^>]+>", "", post["title"]["rendered"])).strip(),
                    "title_html": post["title"]["rendered"],
                    "excerpt_html": (post.get("excerpt") or {}).get("rendered") or "",
                    "body": text,
                    "date": post["date"],
                    "date_gmt": post["date_gmt"],
                    "modified": post.get("modified"),
                    "author": author,
                    "author_source": author_source,
                    "author_id": post.get("author"),
                    "featured_image_url": post.get("jetpack_featured_media_url") or "",
                    "content_image_count": len(images),
                    "embed_count": len(embeds),
                    "embedded_tweet_count": tweets,
                    "category_ids": ";".join(map(str, category_ids)),
                    "tag_ids": ";".join(map(str, post.get("tags") or [])),
                    "category_names": [n for n in category_names if n],
                    "slug": post.get("slug"),
                    "status": post.get("status"),
                    "body_chars": len(text),
                    "ad_blocks_removed": ads,
                    "content_html": content,
                    "raw_file": rel,
                    "api_request_url": ok[rel]["url"],
                    "fetched_at_utc": ok[rel]["fetched_at_utc"],
                })
    posts = pd.DataFrame(records).sort_values(["date", "post_id"]).reset_index(drop=True)
    if save:
        posts.to_parquet(state_dir / "polemon_posts.parquet", index=False)
    return posts


def monthly_counts(dates: pd.Series) -> pd.DataFrame:
    """Posts per month by local publication date, with low-month flags."""
    months = pd.period_range(FIRST_DATE[:7], LAST_DATE[:7], freq="M")
    counts = dates.str[:7].value_counts()
    table = pd.DataFrame({"month": [str(m) for m in months]})
    table["articles"] = table["month"].map(counts).fillna(0).astype(int)
    table["year_median"] = table.groupby(table["month"].str[:4])["articles"].transform("median")
    flags = []
    for n, median in zip(table["articles"], table["year_median"]):
        # Relative to the same year (dips inside a busy year) and absolute (quiet years such as 2015).
        found = []
        if n == 0:
            found.append("empty")
        else:
            if n < 0.25 * median:
                found.append("low: under 25% of the year's monthly median")
            if n < 10:
                found.append("low: under 10 posts")
        flags.append("; ".join(found))
    table["flag"] = flags
    return table


def norm_url(url: str) -> str:
    parts = urlparse(unquote(url.strip()))
    return f"{parts.netloc.lower().removeprefix('www.')}{parts.path.rstrip('/')}".lower()


def sitemap_reconciliation(state_dir: Path, posts: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Post-sitemap URLs missing from the API table, API URLs missing from the sitemaps, and totals."""
    raw = state_dir / "raw"
    sitemap_urls: dict[str, tuple[str, str]] = {}
    for f in sorted((raw / "sitemap").glob("*")):
        if POST_SITEMAP.search(f.name) and b"<urlset" in f.read_bytes()[:3000]:
            for url in sitemap_locs(f.read_bytes()):
                sitemap_urls.setdefault(norm_url(url), (url, f.name))
    api_in = {norm_url(u) for u in posts["url"]}
    outside = {norm_url(p["link"]): p["date"] for _, rows in load_pages(raw, "posts_outside/*/page_*.json") for p in rows}
    root = norm_url(SITE)
    missing = []
    for key, (url, file_name) in sorted(sitemap_urls.items()):
        if key in api_in:
            continue
        path = key.removeprefix(root).strip("/")
        if key in outside:
            result = f"in the API, published {outside[key][:4]} (outside 2015-2025)"
        elif not path:
            result = "home page"
        elif "/" in path:
            result = "not in the API (nested path, probably not an article)"
        else:
            result = "not in the API"
        missing.append({"url": url, "sitemap_file": file_name, "result": result, "api_date": outside.get(key, "")})
    not_in_api = pd.DataFrame(missing, columns=["url", "sitemap_file", "result", "api_date"])
    not_in_sitemap = pd.DataFrame({"url": sorted(u for u in posts["url"] if norm_url(u) not in sitemap_urls)})
    totals = {
        "sitemap_urls": len(sitemap_urls),
        "api_urls_2015_2025": len(api_in),
        "api_urls_in_sitemap": len(api_in & set(sitemap_urls)),
        "sitemap_not_in_api_2015_2025": len(not_in_api),
        "sitemap_not_in_api_by_result": not_in_api["result"].value_counts().to_dict(),
        "api_not_in_sitemap": len(not_in_sitemap),
    }
    return not_in_api, not_in_sitemap, totals


# Cleaning. Invalid pages are excluded by rules I1-I3; the four posts below were read one by one
# and must all be caught, so the build fails if a rule change lets one through. Every other
# suspicious post stays in the delivery with flags (rules V, E, S, T, B).
REVIEWED_INVALID = {
    26: ("feminismos", "adsasdadsads", "test post: the body is random letters"),
    29: ("cines", "jkasdfcadfadf", "test post: the body is random letters"),
    32: ("tomen", "", "test post: title only, empty body and empty source HTML"),
    16155: ("google-site-verification: googlea1d61bf0610190e7.html", "googlea1d61bf0610190e7",
            "Google Search Console site-verification page, not an article"),
}
PLACEHOLDER_MAX_CHARS = 30  # rule I2
SYSTEM_TITLE = re.compile(r"^google-site-verification|\.html?$|^(?:robots|sitemap|ads)\.txt$", re.I)  # rule I3
SHORT_CHARS = 300           # rule S
DUP_BODY_MIN_CHARS = 200    # rule B
VIDEO_EMBED = re.compile(r"<iframe|<video", re.I)  # rule V: judged by content, not by "en vivo" wording
INVALID_RULES = {
    "I1": "no content: no body text and no in-body image, embedded video or tweet",
    "I2": f"placeholder: body under {PLACEHOLDER_MAX_CHARS} characters with no space and no media",
    "I3": "system page: the title is a site-verification or configuration file name",
}
FLAG_LABELS = {
    "flag_video_page": "video or livestream page",
    "flag_empty_body": "no text (images or video only)",
    "flag_short_body": "short body",
    "flag_dup_title": "duplicate title",
    "flag_dup_body": "duplicate body",
}


def norm_title(title: str) -> str:
    title = (title or "").replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    return re.sub(r"\s+", " ", title).strip().lower()


def norm_body(body: str) -> str:
    return re.sub(r"\s+", " ", body or "").strip()


def group_ids(keys: pd.Series, eligible: pd.Series, prefix: str) -> tuple[pd.Series, pd.Series]:
    """Group id and size for keys shared by two or more eligible rows; "" and 0 otherwise."""
    sizes = keys[eligible].map(keys[eligible].value_counts())
    dup = eligible & sizes.reindex(keys.index).fillna(0).ge(2)
    order = {k: f"{prefix}{i:03d}" for i, k in enumerate(sorted(keys[dup].unique()), 1)}
    gid = keys.where(dup).map(order).fillna("")
    size = keys.where(dup).map(keys[dup].value_counts()).fillna(0).astype(int)
    return gid, size


def clean_posts_table(posts: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split posts into delivered rows (with flag columns) and excluded invalid pages."""
    # "Media" is an in-body image (ads excluded), an embedded frame/video or an embedded tweet;
    # a featured image alone does not make a page content.
    no_media = posts["content_image_count"].eq(0) & posts["embed_count"].eq(0) & posts["embedded_tweet_count"].eq(0)
    hits = pd.DataFrame({
        "I1": posts["body_chars"].eq(0) & no_media,
        "I2": posts["body_chars"].between(1, PLACEHOLDER_MAX_CHARS - 1) & ~posts["body"].str.contains(r"\s") & no_media,
        "I3": posts["title"].str.contains(SYSTEM_TITLE),
    })
    invalid = hits.any(axis=1)
    missed = (set(REVIEWED_INVALID) & set(posts["post_id"])) - set(posts.loc[invalid, "post_id"])
    if missed:
        raise ValueError(f"rules no longer catch reviewed invalid posts {sorted(missed)}; re-check rules I1-I3")
    for row in posts[posts["post_id"].isin(REVIEWED_INVALID)].itertuples():
        title, body, _ = REVIEWED_INVALID[row.post_id]
        if row.title != title or row.body.strip() != body:
            raise ValueError(f"post {row.post_id} no longer matches the reviewed content")
    excluded = posts[invalid].copy()
    excluded["exclude_rule"] = hits[invalid].apply(lambda r: ",".join(k for k in INVALID_RULES if r[k]), axis=1)
    excluded["exclude_reason"] = hits[invalid].apply(lambda r: "; ".join(INVALID_RULES[k] for k in INVALID_RULES if r[k]), axis=1)
    excluded["manual_review_note"] = excluded["post_id"].map(lambda i: REVIEWED_INVALID.get(i, ("", "", "not reviewed by hand"))[2])

    clean = posts[~invalid].copy()
    clean["flag_video_page"] = clean["content_html"].str.contains(VIDEO_EMBED) & clean["body_chars"].lt(SHORT_CHARS)
    clean["flag_empty_body"] = clean["body_chars"].eq(0)
    clean["flag_short_body"] = clean["body_chars"].between(1, SHORT_CHARS - 1)
    clean["dup_title_group"], clean["dup_title_count"] = group_ids(clean["title"].map(norm_title), clean["title"].ne(""), "T")
    clean["flag_dup_title"] = clean["dup_title_group"].ne("")
    clean["dup_body_group"], clean["dup_body_count"] = group_ids(
        clean["body"].map(norm_body), clean["body_chars"].ge(DUP_BODY_MIN_CHARS), "B")
    clean["flag_dup_body"] = clean["dup_body_group"].ne("")
    clean["flags"] = clean[list(FLAG_LABELS)].apply(lambda r: "; ".join(FLAG_LABELS[c] for c in FLAG_LABELS if r[c]), axis=1)
    return clean.reset_index(drop=True), excluded.reset_index(drop=True)


def to_wordpress_articles(clean: pd.DataFrame) -> pd.DataFrame:
    """Map delivered posts onto the WordPress article schema used by crawler/articles/<source_id>/."""
    articles = pd.DataFrame({
        "source_id": SOURCE_ID,
        "source_name": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "url": clean["url"],
        "canonical_url": clean["url"],
        "wp_post_id": clean["post_id"].astype("int64"),
        "slug": clean["slug"],
        "title": clean["title_html"].map(clean_html),
        "summary": clean["excerpt_html"].map(clean_html),
        "main_text": clean["body"],
        "authors": clean["author"].where(clean["author"].ne(""), pd.NA),
        "date": clean["date"],
        "date_published": clean["date"],
        "date_modified": clean["modified"],
        "topic": clean["category_names"].map(lambda names: names[0] if len(names) else pd.NA),
        "section": clean["category_names"].map(lambda names: names[0] if len(names) else pd.NA),
        "tags": pd.NA,  # tag names were not collected; tag_ids are kept
        "category_ids": clean["category_ids"].where(clean["category_ids"].ne(""), pd.NA),
        "tag_ids": clean["tag_ids"].where(clean["tag_ids"].ne(""), pd.NA),
        "language": pd.NA,
        "discovery_strategy": "wordpress_api",
        "extractor_strategy": "wordpress_api",
        "article_api_url": clean["api_request_url"],
        "scrape_timestamp": clean["fetched_at_utc"],
        "status": 200,
        "error": pd.NA,
        "category_names": clean["category_names"].map(lambda names: "; ".join(names) if len(names) else pd.NA),
        "tag_names": pd.NA,
    })
    articles["summary"] = articles["summary"].where(articles["summary"].ne(""), pd.NA)
    return normalize_articles_for_output(articles[WORDPRESS_ARTICLE_COLUMNS]).astype({"wp_post_id": "int64", "status": "int64"})


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_delivery(state_dir: Path, out_dir: Path, export_date: str) -> dict:
    """Write <out_dir>/polemon/: WordPress-schema parts, manifest.json, README.md and audit/ (offline)."""
    posts = build_posts_table(state_dir, save=False)
    clean, excluded = clean_posts_table(posts)
    articles = to_wordpress_articles(clean)
    target = out_dir / SOURCE_ID
    audit = target / "audit"
    audit.mkdir(parents=True, exist_ok=True)
    for old in target.glob("articles_part_*.parquet.gzip"):
        old.unlink()

    parts = []
    for number, start in enumerate(range(0, len(articles), PART_ROWS), start=1):
        name = f"articles_part_{number:06d}.parquet.gzip"
        articles.iloc[start:start + PART_ROWS].to_parquet(target / name, index=False, compression="gzip")
        parts.append({"file": name, "rows": len(articles.iloc[start:start + PART_ROWS]), "sha256": sha256_file(target / name)})

    csv = {"index": False, "encoding": "utf-8-sig", "lineterminator": "\n"}
    flags = clean[["post_id", "url", "date", "date_gmt", "body_chars", "flags", *FLAG_LABELS,
                   "dup_title_group", "dup_title_count", "dup_body_group", "dup_body_count", "author_source",
                   "featured_image_url", "content_image_count", "embed_count", "embedded_tweet_count",
                   "ad_blocks_removed"]].rename(columns={"post_id": "wp_post_id", "body_chars": "main_text_chars"})
    flags.to_csv(audit / "quality_flags.csv", **csv)
    excluded.rename(columns={"post_id": "wp_post_id", "body": "main_text"})[
        ["wp_post_id", "url", "date", "title", "main_text", "exclude_rule", "exclude_reason", "manual_review_note"]
    ].to_csv(audit / "excluded_invalid.csv", **csv)
    months = monthly_counts(posts["date"]).rename(columns={"articles": "articles_collected"})
    months.insert(2, "articles_delivered", months["month"].map(clean["date"].str[:7].value_counts()).fillna(0).astype(int))
    months.insert(3, "articles_delivered_not_video_page", months["month"].map(
        clean.loc[~clean["flag_video_page"], "date"].str[:7].value_counts()).fillna(0).astype(int))
    months.to_csv(audit / "monthly_counts.csv", **csv)
    not_in_api, not_in_sitemap, sitemap_totals = sitemap_reconciliation(state_dir, posts)
    not_in_api.to_csv(audit / "sitemap_urls_not_in_api.csv", **csv)
    not_in_sitemap.to_csv(audit / "api_urls_not_in_sitemap.csv", **csv)

    checks = read_back_checks(target, parts, articles)
    ledger = load_ledger(state_dir)
    report = {
        "source_id": SOURCE_ID,
        "exported_at_utc": now(),
        "date_range_local": f"{FIRST_DATE}..{LAST_DATE}",
        "collection": {
            "method": "WordPress REST API /wp-json/wp/v2/posts by local publication year, 100 posts per request",
            "requests": len(ledger),
            "failed_attempts": sum(1 for e in ledger if e["problem"]),
            "first_fetch_utc": min(e["fetched_at_utc"] for e in ledger),
            "last_fetch_utc": max(e["fetched_at_utc"] for e in ledger),
            "pause_seconds": 2.5,
        },
        "rows_collected": len(posts),
        "rows_excluded_invalid": len(excluded),
        "rows_delivered": len(articles),
        "rows_delivered_by_year": articles["date"].str[:4].value_counts().sort_index().to_dict(),
        "flag_counts": {label: int(clean[col].sum()) for col, label in FLAG_LABELS.items()}
        | {"any flag": int(clean["flags"].ne("").sum()), "no flag": int(clean["flags"].eq("").sum())},
        "missing_values": {col: int(articles[col].isna().sum()) for col in WORDPRESS_ARTICLE_COLUMNS},
        "author_source_counts": clean["author_source"].value_counts().to_dict(),
        "sitemap_reconciliation": sitemap_totals,
        "read_back_checks": checks,
    }
    (audit / "export_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8", newline="\n")
    (audit / f"polemon_export_audit_{export_date}.md").write_text(audit_markdown(report, export_date), encoding="utf-8", newline="\n")
    (audit / "CLEANING_RULES.md").write_text(cleaning_rules_markdown(report, excluded), encoding="utf-8", newline="\n")
    (target / "README.md").write_text(readme_markdown(report), encoding="utf-8", newline="\n")
    manifest = {"source_id": SOURCE_ID, "rows": len(articles), "parts": parts,
                "audit_files": [{"file": f"audit/{p.name}", "bytes": p.stat().st_size, "sha256": sha256_file(p)}
                                for p in sorted(audit.iterdir())]}
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return report


def read_back_checks(target: Path, parts: list[dict], articles: pd.DataFrame) -> dict:
    """Read every part back and check rows, keys, required fields and dates."""
    back = pd.concat([pd.read_parquet(target / p["file"]) for p in parts], ignore_index=True)
    blank = lambda col: back[col].isna() | back[col].astype(str).str.strip().eq("")  # noqa: E731
    checks = {
        "rows_read_back": len(back),
        "rows_match": len(back) == len(articles),
        "columns_match_wordpress_schema": list(back.columns) == WORDPRESS_ARTICLE_COLUMNS,
        "duplicate_wp_post_id": int(back["wp_post_id"].duplicated().sum()),
        "duplicate_url": int(back["url"].duplicated().sum()),
        "blank_title": int(blank("title").sum()),
        "blank_url": int(blank("url").sum()),
        "missing_date": int(blank("date").sum()),
        "dates_outside_range": int((~back["date"].between(FIRST_DATE, LAST_DATE + "T23:59:59")).sum()),
        "other_source_id": int(back["source_id"].ne(SOURCE_ID).sum()),
        "error_rows": int(back["error"].notna().sum()),
        "blank_main_text": int(blank("main_text").sum()),
    }
    required_zero = ["duplicate_wp_post_id", "duplicate_url", "blank_title", "blank_url", "missing_date",
                     "dates_outside_range", "other_source_id", "error_rows"]
    if not (checks["rows_match"] and checks["columns_match_wordpress_schema"] and not any(checks[k] for k in required_zero)):
        raise ValueError(f"export read-back failed: {checks}")
    return checks


def audit_markdown(report: dict, export_date: str) -> str:
    c, s = report["read_back_checks"], report["sitemap_reconciliation"]
    return "\n".join([
        f"# Polemon export audit - {export_date}",
        "",
        f"- {report['rows_delivered']:,} posts in {len(report['rows_delivered_by_year'])} years "
        f"({report['date_range_local']}, local publication date), WordPress article schema, gzip Parquet.",
        f"- Collected {report['rows_collected']:,} posts with {report['collection']['requests']} WordPress API requests "
        f"({report['collection']['failed_attempts']} failed attempts), "
        f"{report['collection']['first_fetch_utc'][:16]} to {report['collection']['last_fetch_utc'][:16]} UTC.",
        f"- {report['rows_excluded_invalid']} invalid pages excluded (test posts and a site-verification page); "
        "listed in `excluded_invalid.csv`. Rules: `CLEANING_RULES.md`.",
        f"- Every part read back: {c['rows_read_back']:,} rows; zero duplicate post IDs or URLs, blank titles, "
        "missing dates, dates outside the range, other sources or error rows.",
        f"- {c['blank_main_text']} rows have no body text; they are image or video posts and are flagged, not removed.",
        f"- Review flags kept (`quality_flags.csv`): " + "; ".join(f"{k} {v:,}" for k, v in report["flag_counts"].items()) + ".",
        f"- Sitemap check: {s['api_urls_in_sitemap']:,} of the {s['api_urls_2015_2025']:,} collected URLs are in the "
        f"post sitemaps; {s['sitemap_not_in_api_2015_2025']:,} sitemap URLs were not collected "
        f"({'; '.join(f'{k}: {v:,}' for k, v in s['sitemap_not_in_api_by_result'].items())}).",
        "- Not collected: tag names (`tags`, `tag_names` empty; `tag_ids` kept), deleted posts, posts from 2026 "
        "and the single 2011 post. Images and embedded documents were not downloaded; URLs are in the post HTML.",
        "",
    ])


def readme_markdown(report: dict) -> str:
    return "\n".join([
        "# Polemon article export",
        "",
        f"{report['rows_delivered']:,} posts from polemon.mx published {report['date_range_local'].replace('..', ' to ')} "
        "(local publication date), in one gzip Parquet part. Includes short and image-only posts.",
        f"{report['rows_excluded_invalid']} invalid pages (test posts and a site-verification page) are excluded and",
        "listed in `audit/excluded_invalid.csv`.",
        "",
        "Columns follow the WordPress article schema of `crawler/articles/<source_id>/`",
        "(`code/01-crawlers/crawler_core/wordpress_articles.py`); the core fields are `url`, `title`,",
        "`summary`, `main_text`, `authors`, `date` and `topic`. `date` is the local publication time",
        "(America/Mexico_City) as given by WordPress. `authors` comes from the Yoast SEO author field",
        "because the WordPress users endpoint is closed (HTTP 401). `tags` and `tag_names` are empty",
        "because tag names were not collected; `tag_ids` are kept.",
        "",
        "All posts were collected through the WordPress REST API only, 2.5 seconds between requests,",
        "with code `code/01-crawlers/crawler_core/polemon.py`. `manifest.json` lists the row count and",
        "SHA-256 of every file. `audit/` holds the export audit, cleaning rules, per-post review flags",
        "(`quality_flags.csv`, joined on `wp_post_id`), monthly counts and the sitemap reconciliation.",
        "",
    ])


def cleaning_rules_markdown(report: dict, excluded: pd.DataFrame) -> str:
    lines = [
        "# Polemon cleaning rules",
        "",
        "The collected table is never modified. Invalid pages are excluded by rule; every other",
        "suspicious post is kept and flagged in `quality_flags.csv`.",
        "",
        "## Excluded (invalid pages)",
        "",
        "Media below means an in-body image (ad banners excluded), an embedded video or frame, or an",
        "embedded tweet. A featured image alone does not count.",
        "",
    ]
    lines += [f"- **{rule}**: {text}." for rule, text in INVALID_RULES.items()]
    lines += ["", "Excluded posts:", ""]
    lines += [f"- {r.post_id} ({r.date[:10]}, rule {r.exclude_rule}): {r.manual_review_note}" for r in excluded.itertuples()]
    lines += [
        "",
        "The four posts above were read one by one; the export fails if a rule change stops catching any of them.",
        "",
        "## Kept with flags",
        "",
        f"- **V, video or livestream page**: body under {SHORT_CHARS} characters and an embedded video player "
        "(`<iframe>` or `<video>`). Judged by content; the words \"en vivo\" alone over- and under-match.",
        "- **E, no text**: empty body; these posts are images or video and are valid content.",
        f"- **S, short body**: 1 to {SHORT_CHARS - 1} characters.",
        "- **T, duplicate title**: same title after normalizing quotes, spaces and case; `dup_title_group` links them.",
        f"- **B, duplicate body**: same body after normalizing spaces, only for bodies of {DUP_BODY_MIN_CHARS}+ characters; "
        "`dup_body_group` links them.",
        "",
        "Counts: " + "; ".join(f"{k} {v:,}" for k, v in report["flag_counts"].items()) + ".",
        "",
        "Body text drops share buttons, related-post widgets and Advanced Ads placements (image-only banners).",
        "",
    ]
    return "\n".join(lines)

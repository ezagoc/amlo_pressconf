"""Collect a WordPress news site through its REST API only, and export it to crawler/articles/<source_id>/.

One collector for every WordPress source; the newspaper is a parameter. Each source is a
WordPressSource subclass in crawler_core/<source_id>.py (polemon.py, noticiasdequeretaro.py) that sets
the site, the years and the cleaning options, and overrides the audit texts it needs; load_source()
returns it. Posts are listed by local publication year, 100 full post objects per request, so one pass
collects the whole archive, and every response is kept unchanged for audit.

Access rules agreed for these sources (Polemon 2026-10-26, Noticias de Querétaro 2026-10-27): WordPress
REST API only (no article pages), 2.5 s between requests, and stop at once on a Cloudflare / rate-limit
block or after 3 errors in a row, without trying any other access method. Deleted posts are not recovered.

Steps (run through scripts/crawl_wordpress_api.py --source <source_id>):

    collect  raw/posts/<year>/page_NNN.json, raw/categories, raw/users, requests.jsonl
    sitemap  raw/sitemap/* and, if the source asks for it, API links dated outside its years
    build    <source_id>_posts.parquet, one row per collected post (offline)
    clean    reports delivered and excluded posts (offline)
    export   <source_id>/articles.parquet.gzip in the WordPress article schema, with crawl_report.json,
             README.md, manifest.json and audit/ (offline)
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import importlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Callable
from urllib.parse import unquote, urlencode, urlparse

import pandas as pd

from crawler_core.wordpress import clean_html
from crawler_core.wordpress_articles import base_article_row, normalize_articles_for_output


SOURCES = ("polemon", "noticiasdequeretaro", "exclusivaspuebla")  # modules crawler_core/<source_id>.py
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0 Safari/537.36"
)
CURL = "curl.exe" if sys.platform == "win32" else "curl"
MAX_TRIES = 3
MAX_CONSECUTIVE_ERRORS = 3
OUTPUT_FILE = "articles.parquet.gzip"  # name used by write_article_outputs in wordpress_articles.py
CSV = {"index": False, "encoding": "utf-8-sig", "lineterminator": "\n"}

# Same columns, in the same order, as the WordPress article rows: base_article_row plus the two
# name columns that article_fields_from_post adds (crawler_core/wordpress_articles.py).
WORDPRESS_ARTICLE_COLUMNS = [
    *base_article_row(pd.Series(dtype=object)).keys(),
    "category_names",
    "tag_names",
]


def load_source(source_id: str) -> "WordPressSource":
    if source_id not in SOURCES:
        raise ValueError(f"unknown WordPress source {source_id!r}; known: {', '.join(SOURCES)}")
    return importlib.import_module(f"crawler_core.{source_id}").SOURCE


class Stop(Exception):
    """Collection must halt and be reported; no other access method is tried."""


class Paused(Exception):
    """PAUSE_REQUESTED exists in the state folder; stop before the next request."""


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
        self.pause_request = state_dir / "PAUSE_REQUESTED"
        self.last, self.errors_in_a_row, self.n = 0.0, 0, 0

    def done(self, rel: str) -> bool:
        return (self.raw / rel).exists()

    def get(self, url: str, rel: str, ok: tuple[int, ...] = (200,), validate=None) -> tuple[int, bytes, dict]:
        if self.pause_request.exists():
            raise Paused()
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
            if tmp.exists():  # curl writes no body when the connection fails (e.g. exit code 35, TLS error)
                tmp.replace(target.with_name(f"{target.name}.failed{attempt}"))
            if blocked:
                raise Stop(f"blocked (HTTP {status}) at {url}")
            self.errors_in_a_row += 1
            print(f"{now()} error {self.errors_in_a_row} in a row: {problem} at {url}", flush=True)
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


def paged(client: Client, api: str, path: str, folder: str, **params: object) -> list[str]:
    """Fetch every page of a WordPress list endpoint, skipping pages already saved; returns the page files."""
    pages, page, total_pages = [], 1, None
    while True:
        rel = f"{folder}/page_{page:03d}.json"
        if client.done(rel):
            total = read_headers(client.raw / (rel + ".headers")).get("x-wp-totalpages")
            total_pages = int(total) if total else total_pages
        else:
            _, _, headers = client.get(f"{api}/{path}?{urlencode(dict(per_page=100, page=page, **params))}", rel,
                                       validate=json_list)
            total_pages = int(headers.get("x-wp-totalpages") or 1)
            print(f"{now()} {folder} page {page}/{total_pages} (total {headers.get('x-wp-total')})", flush=True)
        pages.append(rel)
        if page >= (total_pages or 1):
            return pages
        page += 1


# attachment-sitemap lists media pages, not posts (160 files on Noticias de Querétaro).
SKIP_SITEMAP = re.compile(r"attachment|image|video|news|categor|tag|author|page-sitemap|taxonom|users", re.I)
POST_SITEMAP = re.compile(r"post-sitemap\d*\.xml$|posts-post-\d+\.xml$")


def sitemap_locs(data: bytes) -> list[str]:
    return [html.unescape(m.decode("utf-8", "replace")) for m in re.findall(rb"<loc>\s*([^<]+?)\s*</loc>", data)]


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
    text = re.sub(r"[ \t ]+", " ", text)  # the class holds a no-break space (U+00A0)
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


def norm_title(title: str) -> str:
    title = (title or "").replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    return re.sub(r"\s+", " ", title).strip().lower()


def norm_body(body: str) -> str:
    return re.sub(r"\s+", " ", body or "").strip()


def norm_url(url: str) -> str:
    parts = urlparse(unquote(url.strip()))
    return f"{parts.netloc.lower().removeprefix('www.')}{parts.path.rstrip('/')}".lower()


def group_ids(keys: pd.Series, eligible: pd.Series, prefix: str) -> tuple[pd.Series, pd.Series]:
    """Group id and size for keys shared by two or more eligible rows; "" and 0 otherwise."""
    sizes = keys[eligible].map(keys[eligible].value_counts())
    dup = eligible & sizes.reindex(keys.index).fillna(0).ge(2)
    order = {k: f"{prefix}{i:03d}" for i, k in enumerate(sorted(keys[dup].unique()), 1)}
    gid = keys.where(dup).map(order).fillna("")
    size = keys.where(dup).map(keys[dup].value_counts()).fillna(0).astype(int)
    return gid, size


def legacy_url_problems(link: str) -> str:
    """Rule L: why a URL as given by the API is unlikely to open; empty when the slug looks normal.

    A normal WordPress slug holds only letters, digits and hyphens. Slugs imported from older systems can
    carry tabs, periods, semicolons, mojibake or a trailing hyphen that the site no longer resolves. The raw
    string is checked: urlparse silently drops tabs and newlines.
    """
    slug = unquote(link.rstrip("/").rsplit("/", 1)[-1])
    found = []
    if re.search(r"[\x00-\x20\x7f]", slug):
        found.append("whitespace or control character")
    if re.search(r"[ÂÃ]", slug):
        found.append("mojibake (Â/Ã)")
    if re.search(r"[.;,:!?¿¡\"'“”‘’()\[\]{}<>|\\^`]", slug):
        found.append("punctuation in slug")
    if slug.endswith("-"):
        found.append("slug ends with a hyphen")
    # Percent-encoded characters such as a zero-width space (%e2%80%8b) are valid URLs and are not flagged.
    return "; ".join(found)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def n(x) -> str:
    return f"{x:,}"


PLACEHOLDER_MAX_CHARS = 30  # rule I2
SYSTEM_TITLE = re.compile(r"^google-site-verification|\.html?$|^(?:robots|sitemap|ads)\.txt$", re.I)  # rule I3
SHORT_CHARS = 300           # rules S and V
DUP_BODY_MIN_CHARS = 200    # rule B
VIDEO_EMBED = re.compile(r"<iframe|<video", re.I)  # rule V: judged by content, not by "en vivo" wording
INVALID_RULES = {
    "I1": "no content: no body text and no in-body image, embedded video or tweet",
    "I2": f"placeholder: body under {PLACEHOLDER_MAX_CHARS} characters with no space and no media",
    "I3": "system page: the title is a site-verification or configuration file name",
}
# What each review flag means, for the generic CLEANING_RULES.md.
FLAG_RULES = {
    "flag_video_page": f"body under {SHORT_CHARS} characters and an embedded video player (`<iframe>` or `<video>`).",
    "flag_cover_page": "a daily front-page post, by its title; kept.",
    "flag_empty_body": "empty body; these posts are images, video or embedded documents and are kept.",
    "flag_short_body": f"1 to {SHORT_CHARS - 1} characters of body text.",
    "flag_dup_title": "same title after normalizing quotes, spaces and case; `dup_title_group` links them.",
    "flag_dup_body": f"same body after normalizing spaces, bodies of {DUP_BODY_MIN_CHARS}+ characters; `dup_body_group` links them.",
    "flag_legacy_url": "the URL's last segment holds characters the site no longer resolves; kept as given.",
    "flag_dup_url": "two or more post IDs carry the same URL with different text; `dup_url_group` links them.",
    "flag_no_title": "the post has an empty title; kept.",
}


class WordPressSource:
    """One WordPress newspaper. Subclasses set the class attributes; the defaults are the Polemon rules."""

    source_id: str
    source_name: str
    site: str  # e.g. "https://polemon.mx", no trailing slash
    years: range
    year_order: list[int] | None = None  # collection order; None is oldest first
    pause_seconds = 2.5

    sitemap_candidates = ["sitemap.xml", "wp-sitemap.xml", "sitemap_index.xml"]
    skip_sitemap = SKIP_SITEMAP
    # The sitemap step also lists the API links dated outside the years (id, date and link only), so the
    # reconciliation can tell them apart from posts the API is missing.
    fetch_posts_outside = True
    # Where the byline comes from, in order: "users" (the /users endpoint) and "yoast" (yoast_head_json.author).
    author_sources: tuple[str, ...] = ("users", "yoast")

    # Cleaning options. Invalid pages are excluded by rules I1-I3; posts listed in reviewed_invalid
    # (post id -> (title, body, note)) were read one by one and the export fails if a rule stops catching them.
    reviewed_invalid: dict[int, tuple[str, str, str]] = {}
    media_includes_featured = False  # a featured image or a gallery/video/image post format counts as media
    video_post_format = False        # rule V also takes the video post format, not only an embedded player
    cover_title: re.Pattern | None = None      # rule C: front-page posts by title
    date_only_title: re.Pattern | None = None  # rule C: titles that are only a date, when the body is short
    flag_legacy_urls = False         # rule L
    drop_duplicate_imports = False   # rule D (identical copies under one URL dropped) and rule U
    flag_no_title = False            # rule N
    # quality_flags.csv: columns after wp_post_id, url, date, date_gmt, main_text_chars, flags and the flag columns.
    quality_flag_columns = ["dup_title_group", "dup_title_count", "dup_body_group", "dup_body_count", "author_source",
                            "featured_image_url", "content_image_count", "embed_count", "embedded_tweet_count",
                            "ad_blocks_removed"]

    @property
    def source_url(self) -> str:
        return f"{self.site}/"

    @property
    def api(self) -> str:
        return f"{self.site}/wp-json/wp/v2"

    @property
    def first_date(self) -> str:
        return f"{self.years[0]}-01-01"

    @property
    def last_date(self) -> str:
        return f"{self.years[-1]}-12-31"

    @property
    def year_span(self) -> str:
        return f"{self.years[0]}-{self.years[-1]}"

    @property
    def flag_labels(self) -> dict[str, str]:
        labels = {"flag_video_page": "video or livestream page"}
        if self.cover_title is not None:
            labels["flag_cover_page"] = "front-page (portada) post"
        labels |= {"flag_empty_body": "no text (images or video only)", "flag_short_body": "short body",
                   "flag_dup_title": "duplicate title", "flag_dup_body": "duplicate body"}
        if self.flag_legacy_urls:
            labels["flag_legacy_url"] = "legacy URL that may not open"
        if self.drop_duplicate_imports:
            labels["flag_dup_url"] = "URL shared with another post"
        if self.flag_no_title:
            labels["flag_no_title"] = "no title"
        return labels

    # ---- collection (network) ----

    def collect_posts(self, state_dir: Path, pause: float | None = None, client: Client | None = None) -> None:
        """Posts for each year by local publication date, then categories and users."""
        client = client or Client(state_dir, self.pause_seconds if pause is None else pause)
        for year in self.year_order or self.years:
            # `after` and `before` are exclusive and compare the local publication date; id order keeps pages stable.
            paged(client, self.api, "posts", f"posts/{year}", orderby="id", order="asc",
                  after=f"{year - 1}-12-31T23:59:59", before=f"{year + 1}-01-01T00:00:00")
            print(f"{now()} year {year} complete", flush=True)
        paged(client, self.api, "categories", "categories", orderby="id", order="asc")
        rel = "users/page_001.json"
        if not client.done(rel) and not any((client.raw / "users").glob("page_001.json.status*")):
            status, _, headers = client.get(f"{self.api}/users?per_page=100&page=1&orderby=id&order=asc", rel,
                                            ok=(200, 401, 403, 404))
            if status != 200:
                # Keep the refusal as evidence, under a name `build` does not read as a user list.
                (client.raw / rel).replace(client.raw / "users" / f"page_001.json.status{status}")
                print(f"{now()} users endpoint answered HTTP {status}; authors come from Yoast metadata", flush=True)
            elif int(headers.get("x-wp-totalpages") or 1) > 1:
                paged(client, self.api, "users", "users", orderby="id", order="asc")
        print(f"{now()} collect done, {client.n} requests this run", flush=True)

    def collect_sitemap(self, state_dir: Path, pause: float | None = None, client: Client | None = None) -> None:
        """Post sitemaps, plus (fetch_posts_outside) API links dated outside the years."""
        client = client or Client(state_dir, self.pause_seconds if pause is None else pause)
        index_rel = None
        for name in self.sitemap_candidates:
            rel = f"sitemap/{name}"
            if client.done(rel):
                index_rel = rel
                break
            status, data, _ = client.get(f"{self.site}/{name}", rel, ok=(200, 404))
            if status == 200 and b"<loc>" in data:
                index_rel = rel
                break
        if index_rel is None:
            raise Stop("no sitemap found at " + ", ".join(self.sitemap_candidates))
        queue, seen = [index_rel], set()
        while queue:
            rel = queue.pop(0)
            data = (client.raw / rel).read_bytes()
            if b"<sitemapindex" not in data[:2000]:
                continue
            for child in sitemap_locs(data):
                name = urlparse(child).path.strip("/").replace("/", "_")
                if child in seen or self.skip_sitemap.search(name):
                    continue
                seen.add(child)
                child_rel = f"sitemap/{name}"
                if not client.done(child_rel):
                    client.get(child, child_rel)
                    print(f"{now()} sitemap {name}", flush=True)
                queue.append(child_rel)
        if self.fetch_posts_outside:
            first, last = self.years[0], self.years[-1]
            paged(client, self.api, "posts", f"posts_outside/before_{first}", orderby="id", order="asc",
                  before=f"{first}-01-01T00:00:00", _fields="id,date,date_gmt,link,slug")
            paged(client, self.api, "posts", f"posts_outside/after_{last}", orderby="id", order="asc",
                  after=f"{last}-12-31T23:59:59", _fields="id,date,date_gmt,link,slug")
        print(f"{now()} sitemap done, {client.n} requests this run", flush=True)

    # ---- offline build and cleaning ----

    def build_posts_table(self, state_dir: Path, save: bool = True) -> pd.DataFrame:
        """One row per post from the saved API pages (offline); `save` writes <source_id>_posts.parquet."""
        raw = state_dir / "raw"
        ok = {e["file"]: e for e in load_ledger(state_dir) if e["problem"] is None}
        categories: dict[int, str] = {}
        for _, rows in load_pages(raw, "categories/page_*.json"):
            categories.update({r["id"]: html.unescape(r["name"]) for r in rows})
        users: dict[int, str] = {}
        if "users" in self.author_sources:
            for _, rows in load_pages(raw, "users/page_*.json"):
                users.update({r["id"]: html.unescape(r.get("name") or "") for r in rows})

        records, seen = [], set()
        for year in self.years:
            for rel, rows in load_pages(raw, f"posts/{year}/page_*.json"):
                for post in rows:
                    if post["id"] in seen:
                        continue
                    seen.add(post["id"])
                    content = post["content"]["rendered"]
                    text, ads = body_text(content)
                    images, embeds, tweets = body_media(content)
                    category_ids = post.get("categories") or []
                    author, author_source = "", ""
                    for source in self.author_sources:
                        if source == "users" and users.get(post.get("author")):
                            author, author_source = users[post["author"]], "users_endpoint"
                        elif source == "yoast" and (post.get("yoast_head_json") or {}).get("author"):
                            author, author_source = post["yoast_head_json"]["author"], "yoast_head_json.author"
                        if author:
                            break
                    records.append({
                        "post_id": post["id"],
                        "url": post["link"],
                        "slug": post.get("slug"),
                        "title": html.unescape(re.sub(r"<[^>]+>", "", post["title"]["rendered"])).strip(),
                        "title_html": post["title"]["rendered"],
                        "excerpt_html": (post.get("excerpt") or {}).get("rendered") or "",
                        "body": text,
                        "body_chars": len(text),
                        "date": post["date"],
                        "date_gmt": post["date_gmt"],
                        "modified": post.get("modified"),
                        "author": author,
                        "author_source": author_source,
                        "author_id": post.get("author"),
                        "wp_format": post.get("format"),
                        "status": post.get("status"),
                        "featured_media": post.get("featured_media") or 0,
                        "featured_image_url": post.get("jetpack_featured_media_url") or "",
                        "content_image_count": len(images),
                        "embed_count": len(embeds),
                        "embedded_tweet_count": tweets,
                        "has_video_embed": bool(VIDEO_EMBED.search(content)),
                        "ad_blocks_removed": ads,
                        "category_ids": ";".join(map(str, category_ids)),
                        "tag_ids": ";".join(map(str, post.get("tags") or [])),
                        "category_names": [categories[i] for i in category_ids if categories.get(i)],
                        "categories_unknown": [i for i in category_ids if i not in categories],
                        "raw_file": rel,
                        "api_request_url": ok[rel]["url"],
                        "fetched_at_utc": ok[rel]["fetched_at_utc"],
                    })
        posts = pd.DataFrame(records).sort_values(["date", "post_id"]).reset_index(drop=True)
        if save:
            posts.to_parquet(state_dir / f"{self.source_id}_posts.parquet", index=False)
        return posts

    def clean_posts_table(self, posts: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Split posts into delivered rows (with flag columns), excluded invalid pages and excluded duplicate imports."""
        # "Media" is an in-body image (ads excluded), an embedded frame/video or an embedded tweet; with
        # media_includes_featured also a featured image or a gallery/video/image post format.
        no_media = posts["content_image_count"].eq(0) & posts["embed_count"].eq(0) & posts["embedded_tweet_count"].eq(0)
        if self.media_includes_featured:
            no_media &= posts["featured_media"].eq(0) & ~posts["wp_format"].isin(["gallery", "video", "image"])
        hits = pd.DataFrame({
            "I1": posts["body_chars"].eq(0) & no_media,
            "I2": posts["body_chars"].between(1, PLACEHOLDER_MAX_CHARS - 1) & ~posts["body"].str.contains(r"\s") & no_media,
            "I3": posts["title"].str.contains(SYSTEM_TITLE),
        })
        invalid = hits.any(axis=1)
        missed = (set(self.reviewed_invalid) & set(posts["post_id"])) - set(posts.loc[invalid, "post_id"])
        if missed:
            raise ValueError(f"rules no longer catch reviewed invalid posts {sorted(missed)}; re-check rules I1-I3")
        for row in posts[posts["post_id"].isin(self.reviewed_invalid)].itertuples():
            title, body, _ = self.reviewed_invalid[row.post_id]
            if row.title != title or row.body.strip() != body:
                raise ValueError(f"post {row.post_id} no longer matches the reviewed content")
        excluded = posts[invalid].copy()
        excluded["exclude_rule"] = hits[invalid].apply(lambda r: ",".join(k for k in INVALID_RULES if r[k]), axis=1)
        excluded["exclude_reason"] = hits[invalid].apply(lambda r: "; ".join(INVALID_RULES[k] for k in INVALID_RULES if r[k]), axis=1)
        if self.reviewed_invalid:
            excluded["manual_review_note"] = excluded["post_id"].map(
                lambda i: self.reviewed_invalid.get(i, ("", "", "not reviewed by hand"))[2])

        clean = posts[~invalid].copy()
        # Rule D: posts sharing a URL with the same title and text are one post imported twice; the lowest
        # post id is kept. Posts sharing a URL whose title or text differ are all kept (rule U).
        shared = clean["url"].ne("") & clean["url"].duplicated(keep=False) & self.drop_duplicate_imports
        candidates = clean[shared]
        key = candidates["title_html"].map(clean_html) + "\x00" + candidates["body"]
        keep_id = candidates.groupby([candidates["url"], key])["post_id"].transform("min")
        duplicates = candidates[candidates["post_id"].ne(keep_id)].copy()
        duplicates["kept_post_id"] = keep_id[duplicates.index]
        duplicates["exclude_rule"], duplicates["exclude_reason"] = "D", "duplicate import"
        clean = clean.drop(index=duplicates.index)

        short = clean["body_chars"].lt(SHORT_CHARS)
        video = clean["has_video_embed"] | (clean["wp_format"].eq("video") if self.video_post_format else False)
        clean["flag_video_page"] = video & short
        if self.cover_title is not None:
            clean["flag_cover_page"] = clean["title"].str.contains(self.cover_title)
            if self.date_only_title is not None:
                clean["flag_cover_page"] |= clean["title"].str.match(self.date_only_title) & short
        clean["flag_empty_body"] = clean["body_chars"].eq(0)
        clean["flag_short_body"] = clean["body_chars"].between(1, SHORT_CHARS - 1)
        clean["dup_title_group"], clean["dup_title_count"] = group_ids(clean["title"].map(norm_title), clean["title"].ne(""), "T")
        clean["flag_dup_title"] = clean["dup_title_group"].ne("")
        clean["dup_body_group"], clean["dup_body_count"] = group_ids(
            clean["body"].map(norm_body), clean["body_chars"].ge(DUP_BODY_MIN_CHARS), "B")
        clean["flag_dup_body"] = clean["dup_body_group"].ne("")
        if self.flag_legacy_urls:
            clean["legacy_url_problem"] = clean["url"].map(legacy_url_problems)
            clean["flag_legacy_url"] = clean["legacy_url_problem"].ne("")
        if self.drop_duplicate_imports:
            clean["dup_url_group"], clean["dup_url_count"] = group_ids(clean["url"], clean["url"].ne(""), "U")
            clean["flag_dup_url"] = clean["dup_url_group"].ne("")
        if self.flag_no_title:
            clean["flag_no_title"] = clean["title"].str.strip().eq("")
        labels = self.flag_labels
        clean["flags"] = clean[list(labels)].apply(lambda r: "; ".join(labels[c] for c in labels if r[c]), axis=1)
        return (clean.reset_index(drop=True), excluded.reset_index(drop=True),
                duplicates.sort_values("post_id").reset_index(drop=True))

    def to_wordpress_articles(self, clean: pd.DataFrame) -> pd.DataFrame:
        """Map delivered posts onto the WordPress article schema used by crawler/articles/<source_id>/."""
        articles = pd.DataFrame({
            "source_id": self.source_id,
            "source_name": self.source_name,
            "source_url": self.source_url,
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

    # ---- export ----

    def export_delivery(self, state_dir: Path, out_dir: Path, export_date: str, sample_dir: Path | None = None) -> dict:
        """Write <out_dir>/<source_id>/ (offline): articles.parquet.gzip, crawl_report.json, README.md,
        manifest.json and audit/. `out_dir` is the crawler/articles folder of the WordPress sources;
        `sample_dir` is an earlier sample run of the source, for the sources whose audit uses one."""
        posts = self.build_posts_table(state_dir, save=False)
        clean, excluded, duplicates = self.clean_posts_table(posts)
        articles = self.to_wordpress_articles(clean)
        target = out_dir / self.source_id
        audit = target / "audit"
        audit.mkdir(parents=True, exist_ok=True)

        # Same file and writer as write_article_outputs in crawler_core/wordpress_articles.py.
        articles.to_parquet(target / OUTPUT_FILE, index=False, compression="gzip")
        crawl_report = self.build_crawl_report(target / OUTPUT_FILE, articles)
        (target / "crawl_report.json").write_text(json.dumps(crawl_report, indent=2) + "\n", encoding="utf-8", newline="\n")
        checks = self.read_back_checks(target / OUTPUT_FILE, articles)

        flags = clean[["post_id", "url", "date", "date_gmt", "body_chars", "flags", *self.flag_labels,
                       *self.quality_flag_columns]].rename(columns={"post_id": "wp_post_id", "body_chars": "main_text_chars"})
        flags.to_csv(audit / "quality_flags.csv", **CSV)
        if self.flag_legacy_urls:
            flags[flags["flag_legacy_url"]][["wp_post_id", "url", "date", "legacy_url_problem"]].to_csv(
                audit / "legacy_urls.csv", **CSV)
        excluded.rename(columns={"post_id": "wp_post_id", "body": "main_text"})[
            ["wp_post_id", "url", "date", "title", "main_text", "exclude_rule", "exclude_reason"]
            + (["manual_review_note"] if self.reviewed_invalid else [])
        ].to_csv(audit / "excluded_invalid.csv", **CSV)
        if self.drop_duplicate_imports:
            duplicates.rename(columns={"post_id": "wp_post_id", "kept_post_id": "kept_wp_post_id"})[
                ["wp_post_id", "kept_wp_post_id", "url", "date", "title", "exclude_reason"]
            ].to_csv(audit / "excluded_duplicate_import.csv", **CSV)

        ctx = SimpleNamespace(state_dir=state_dir, sample_dir=sample_dir, target=target, posts=posts, clean=clean,
                              excluded=excluded, duplicates=duplicates, articles=articles, checks=checks)
        self.monthly_table(ctx).to_csv(audit / "monthly_counts.csv", **CSV)
        ctx.sitemap_totals = self.write_sitemap_check(ctx, audit)
        report = self.report(ctx)
        (audit / "export_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str),
                                                 encoding="utf-8", newline="\n")
        (audit / f"{self.source_id}_export_audit_{export_date}.md").write_text(
            self.audit_markdown(report, export_date), encoding="utf-8", newline="\n")
        (audit / "CLEANING_RULES.md").write_text(self.cleaning_rules_markdown(report, excluded), encoding="utf-8", newline="\n")
        (target / "README.md").write_text(self.readme_markdown(report), encoding="utf-8", newline="\n")
        files = [target / OUTPUT_FILE, target / "crawl_report.json", target / "README.md", *sorted(audit.iterdir())]
        manifest = {"source_id": self.source_id, "rows": len(articles),
                    "files": [{"file": p.relative_to(target).as_posix(), "bytes": p.stat().st_size, "sha256": sha256_file(p)}
                              for p in files]}
        (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                              encoding="utf-8", newline="\n")
        return report

    def build_crawl_report(self, path: Path, articles: pd.DataFrame) -> dict:
        """crawl_report.json with the fields of the other crawler/articles/<source_id>/ folders."""
        import pyarrow.parquet as pq

        blank_text = articles["main_text"].isna() | articles["main_text"].astype(str).str.strip().eq("")
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "rows": len(articles),
            "output_file": path.name,
            "row_groups": pq.ParquetFile(path).metadata.num_row_groups,
            "errors": int(articles["error"].notna().sum()),
            "missing_main_text": int(blank_text.sum()),
            "min_date": articles["date_published"].min(),
            "max_date": articles["date_published"].max(),
            "exported_at": now(),
        }

    def read_back_checks(self, path: Path, articles: pd.DataFrame) -> dict:
        """Read the exported file back and check rows, keys, required fields and dates."""
        back = pd.read_parquet(path)
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
            "dates_outside_range": int((~back["date"].between(self.first_date, self.last_date + "T23:59:59")).sum()),
            "other_source_id": int(back["source_id"].ne(self.source_id).sum()),
            "error_rows": int(back["error"].notna().sum()),
            "blank_main_text": int(blank("main_text").sum()),
        }
        # Shared URLs (rule U) and posts without a title (rule N) are kept and flagged where the source allows them.
        required_zero = ["duplicate_wp_post_id", "blank_url", "missing_date", "dates_outside_range", "other_source_id", "error_rows"]
        required_zero += [] if self.drop_duplicate_imports else ["duplicate_url"]
        required_zero += [] if self.flag_no_title else ["blank_title"]
        if not (checks["rows_match"] and checks["columns_match_wordpress_schema"] and not any(checks[k] for k in required_zero)):
            raise ValueError(f"export read-back failed: {checks}")
        return checks

    def monthly_counts(self, dates: pd.Series) -> pd.DataFrame:
        """Posts per month by local publication date, with low-month flags."""
        months = pd.period_range(self.first_date[:7], self.last_date[:7], freq="M")
        counts = dates.str[:7].value_counts()
        table = pd.DataFrame({"month": [str(m) for m in months]})
        table["articles"] = table["month"].map(counts).fillna(0).astype(int)
        table["year_median"] = table.groupby(table["month"].str[:4])["articles"].transform("median")
        flags = []
        for count, median in zip(table["articles"], table["year_median"]):
            # Relative to the same year (dips inside a busy year) and absolute (quiet years).
            found = []
            if count == 0:
                found.append("empty")
            else:
                if count < 0.25 * median:
                    found.append("low: under 25% of the year's monthly median")
                if count < 10:
                    found.append("low: under 10 posts")
            flags.append("; ".join(found))
        table["flag"] = flags
        return table

    def monthly_table(self, ctx: SimpleNamespace) -> pd.DataFrame:
        """audit/monthly_counts.csv: collected and delivered posts per month."""
        months = self.monthly_counts(ctx.posts["date"]).rename(columns={"articles": "articles_collected"})
        months.insert(2, "articles_delivered", months["month"].map(ctx.clean["date"].str[:7].value_counts()).fillna(0).astype(int))
        months.insert(3, "articles_delivered_not_video_page", months["month"].map(
            ctx.clean.loc[~ctx.clean["flag_video_page"], "date"].str[:7].value_counts()).fillna(0).astype(int))
        return months

    def sitemap_reconciliation(self, state_dir: Path, posts: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
        """Post-sitemap URLs missing from the API table, API URLs missing from the sitemaps, and totals."""
        raw = state_dir / "raw"
        sitemap_urls: dict[str, tuple[str, str]] = {}
        for f in sorted((raw / "sitemap").glob("*")):
            if POST_SITEMAP.search(f.name) and b"<urlset" in f.read_bytes()[:3000]:
                for url in sitemap_locs(f.read_bytes()):
                    sitemap_urls.setdefault(norm_url(url), (url, f.name))
        api_in = {norm_url(u) for u in posts["url"]}
        outside = {norm_url(p["link"]): p["date"] for _, rows in load_pages(raw, "posts_outside/*/page_*.json") for p in rows}
        root = norm_url(self.site)
        missing = []
        for key, (url, file_name) in sorted(sitemap_urls.items()):
            if key in api_in:
                continue
            path = key.removeprefix(root).strip("/")
            if key in outside:
                result = f"in the API, published {outside[key][:4]} (outside {self.year_span})"
            elif not path:
                result = "home page"
            elif "/" in path:
                result = "not in the API (nested path, probably not an article)"
            else:
                result = "not in the API"
            missing.append({"url": url, "sitemap_file": file_name, "result": result, "api_date": outside.get(key, "")})
        not_in_api = pd.DataFrame(missing, columns=["url", "sitemap_file", "result", "api_date"])
        not_in_sitemap = pd.DataFrame({"url": sorted(u for u in posts["url"] if norm_url(u) not in sitemap_urls)})
        span = self.year_span.replace("-", "_")
        totals = {
            "sitemap_urls": len(sitemap_urls),
            f"api_urls_{span}": len(api_in),
            "api_urls_in_sitemap": len(api_in & set(sitemap_urls)),
            f"sitemap_not_in_api_{span}": len(not_in_api),
            "sitemap_not_in_api_by_result": not_in_api["result"].value_counts().to_dict(),
            "api_not_in_sitemap": len(not_in_sitemap),
        }
        return not_in_api, not_in_sitemap, totals

    def write_sitemap_check(self, ctx: SimpleNamespace, audit: Path) -> dict | None:
        """Sitemap reconciliation files in audit/; returns the totals for the report (all zero without sitemaps)."""
        not_in_api, not_in_sitemap, totals = self.sitemap_reconciliation(ctx.state_dir, ctx.posts)
        not_in_api.to_csv(audit / "sitemap_urls_not_in_api.csv", **CSV)
        not_in_sitemap.to_csv(audit / "api_urls_not_in_sitemap.csv", **CSV)
        return totals

    def report(self, ctx: SimpleNamespace) -> dict:
        """audit/export_audit.json."""
        ledger = load_ledger(ctx.state_dir)
        clean, articles, labels = ctx.clean, ctx.articles, self.flag_labels
        report = {
            "source_id": self.source_id,
            "exported_at_utc": now(),
            "date_range_local": f"{self.first_date}..{self.last_date}",
            "collection": {
                "method": "WordPress REST API /wp-json/wp/v2/posts by local publication year, 100 posts per request",
                "requests": len(ledger),
                "failed_attempts": sum(1 for e in ledger if e["problem"]),
                "first_fetch_utc": min(e["fetched_at_utc"] for e in ledger),
                "last_fetch_utc": max(e["fetched_at_utc"] for e in ledger),
                "pause_seconds": self.pause_seconds,
            },
            "rows_collected": len(ctx.posts),
            "rows_excluded_invalid": len(ctx.excluded),
        }
        if self.drop_duplicate_imports:
            report["rows_excluded_duplicate_import"] = len(ctx.duplicates)
        report |= {
            "rows_delivered": len(articles),
            "rows_delivered_by_year": articles["date"].str[:4].value_counts().sort_index().to_dict(),
            "flag_counts": {label: int(clean[col].sum()) for col, label in labels.items()}
            | {"any flag": int(clean["flags"].ne("").sum()), "no flag": int(clean["flags"].eq("").sum())},
            "missing_values": {col: int(articles[col].isna().sum()) for col in WORDPRESS_ARTICLE_COLUMNS},
            "author_source_counts": clean["author_source"].value_counts().to_dict(),
            "sitemap_reconciliation": ctx.sitemap_totals,
            "read_back_checks": ctx.checks,
        }
        return report

    # ---- audit texts; sources override them where they need their own wording ----

    def audit_markdown(self, report: dict, export_date: str) -> str:
        c, s, span = report["read_back_checks"], report["sitemap_reconciliation"], self.year_span.replace("-", "_")
        lines = [
            f"# {self.source_name} export audit - {export_date}",
            "",
            f"- {n(report['rows_delivered'])} posts in {len(report['rows_delivered_by_year'])} years "
            f"({report['date_range_local']}, local publication date), WordPress article schema, gzip Parquet.",
            f"- Collected {n(report['rows_collected'])} posts; {n(report['collection']['requests'])} requests to the site "
            f"(WordPress API and sitemaps, {report['collection']['failed_attempts']} failed attempts), "
            f"{report['collection']['first_fetch_utc'][:16]} to {report['collection']['last_fetch_utc'][:16]} UTC.",
            f"- {n(report['rows_excluded_invalid'])} invalid pages excluded; listed in `excluded_invalid.csv`. "
            "Rules: `CLEANING_RULES.md`.",
        ]
        if "rows_excluded_duplicate_import" in report:
            lines.append(f"- {n(report['rows_excluded_duplicate_import'])} identical copies of posts sharing a URL excluded; "
                         "listed in `excluded_duplicate_import.csv`.")
        lines += [
            f"- `{OUTPUT_FILE}` read back: {n(c['rows_read_back'])} rows; duplicate post IDs {c['duplicate_wp_post_id']}, "
            f"duplicate URLs {c['duplicate_url']}, blank titles {c['blank_title']}, dates outside the range "
            f"{c['dates_outside_range']}; {n(c['blank_main_text'])} rows have no body text (flagged, not removed).",
            "- Review flags kept (`quality_flags.csv`): " + "; ".join(f"{k} {n(v)}" for k, v in report["flag_counts"].items()) + ".",
        ]
        if s:
            lines.append(
                f"- Sitemap check: {n(s['api_urls_in_sitemap'])} of the {n(s[f'api_urls_{span}'])} collected URLs are in the "
                f"post sitemaps; {n(s[f'sitemap_not_in_api_{span}'])} sitemap URLs were not collected "
                f"({'; '.join(f'{k}: {n(v)}' for k, v in s['sitemap_not_in_api_by_result'].items()) or 'none'}).")
        lines += [
            f"- Not collected: tag names (`tags`, `tag_names` empty; `tag_ids` kept), deleted posts and posts outside "
            f"{self.year_span}. Images and embedded documents were not downloaded; URLs are in the post HTML.",
            "",
        ]
        return "\n".join(lines)

    def readme_markdown(self, report: dict) -> str:
        host = urlparse(self.site).netloc
        return "\n".join([
            f"# {self.source_name} article export",
            "",
            f"{n(report['rows_delivered'])} posts from {host} published {report['date_range_local'].replace('..', ' to ')} "
            f"(local publication date), in `{OUTPUT_FILE}` (gzip Parquet). {n(report['rows_excluded_invalid'])} invalid",
            "pages are excluded and listed in `audit/excluded_invalid.csv`; other suspicious posts are kept and flagged.",
            "",
            "Columns follow the WordPress article schema of `crawler/articles/<source_id>/`",
            "(`code/01-crawlers/crawler_core/wordpress_articles.py`); the core fields are `url`, `title`,",
            "`summary`, `main_text`, `authors`, `date` and `topic`. `date` is the local publication time as",
            "given by WordPress. `tags` and `tag_names` are empty because tag names were not collected;",
            "`tag_ids` are kept.",
            "",
            f"All posts were collected through the WordPress REST API only, {self.pause_seconds:g} seconds between requests,",
            "with code `code/01-crawlers/crawler_core/wordpress_api.py`. `crawl_report.json` has the same fields as",
            "the other sources in `crawler/articles/`; `manifest.json` lists the size and SHA-256 of every",
            "file. `audit/` holds the export audit, cleaning rules, per-post review flags",
            "(`quality_flags.csv`, joined on `wp_post_id`), monthly counts and the sitemap reconciliation.",
            "",
        ])

    def cleaning_rules_markdown(self, report: dict, excluded: pd.DataFrame) -> str:
        lines = [
            f"# {self.source_name} cleaning rules",
            "",
            "The collected table is never modified. Invalid pages are excluded by rule; every other",
            "suspicious post is kept and flagged in `quality_flags.csv`.",
            "",
            "## Excluded (invalid pages)",
            "",
            *[f"- **{rule}**: {text}." for rule, text in INVALID_RULES.items()],
            "",
            f"{n(len(excluded))} posts excluded, listed in `excluded_invalid.csv`" + (":" if 0 < len(excluded) <= 40 else "."),
            *([""] + [f"- {r.post_id} ({r.date[:10]}, rule {r.exclude_rule}): {r.title or '(no title)'}"
                      for r in excluded.itertuples()] if 0 < len(excluded) <= 40 else []),
            "",
            "## Kept with flags",
            "",
            *[f"- **{label}**: {FLAG_RULES[col]}" for col, label in self.flag_labels.items()],
            "",
            "Counts: " + "; ".join(f"{k} {n(v)}" for k, v in report["flag_counts"].items()) + ".",
            "",
        ]
        return "\n".join(lines)

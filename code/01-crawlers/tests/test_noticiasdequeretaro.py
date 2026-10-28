from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd


CRAWLER_DIR = Path(__file__).resolve().parents[1]
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

from crawler_core.noticiasdequeretaro import SOURCE  # noqa: E402
from crawler_core.wordpress_api import WORDPRESS_ARTICLE_COLUMNS, Client, load_source  # noqa: E402


SITE = "https://noticiasdequeretaro.com.mx"


def post(post_id: int, date: str, title: str, content: str, link: str, fmt: str = "standard", featured: int = 0) -> dict:
    return {
        "id": post_id, "date": date, "date_gmt": date, "modified": date, "slug": f"post-{post_id}", "link": link,
        "status": "publish", "type": "post", "format": fmt, "featured_media": featured,
        "title": {"rendered": title}, "excerpt": {"rendered": ""}, "content": {"rendered": content},
        "categories": [3], "tags": [], "author": 1, "yoast_head_json": {"author": "Brenda"},
    }


SAME = f"{SITE}/2013/05/01/nota-repetida/"
EDITED = f"{SITE}/2013/05/02/nota-editada/"
LEGACY = f"{SITE}/2013/05/03/nota\tvieja./"
POSTS = {
    2013: [
        post(101, "2013-05-01T10:00:00", "Nota repetida", "<p>Texto igual.</p>", SAME),
        post(102, "2013-05-01T10:10:00", "Nota repetida", "<p>Texto igual.</p>", SAME),  # imported twice: dropped
        post(103, "2013-05-02T10:00:00", "Nota editada", "<p>Versión uno.</p>", EDITED),
        post(104, "2013-05-02T11:00:00", "Nota editada", "<p>Versión dos.</p>", EDITED),  # differs: kept
        post(105, "2013-05-03T10:00:00", "Nota vieja", "<p>Texto viejo.</p>", LEGACY),
    ],
    2019: [
        post(106, "2019-03-01T06:00:00", "¡Conoce la portada de hoy!", "", f"{SITE}/2019/03/01/portada/", "gallery", 55),
        post(107, "2019-03-01T07:00:00", "Borrador automático", "", f"{SITE}/2019/03/01/borrador/"),
        post(108, "2019-03-01T08:00:00", "En vivo", "<p>En vivo</p>", f"{SITE}/2019/03/01/en-vivo/", "video"),
    ],
}


def fake_site(requested: list[str]):
    """Noticias de Querétaro stand-in: posts in 2013 and 2019, an open users endpoint, Yoast sitemaps."""

    def fetch(url: str, body_path: Path, header_path: Path) -> tuple[int, int]:
        requested.append(url)
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        body: object = []
        if parsed.path.endswith("/posts"):
            body = POSTS.get(int(query["after"][0][:4]) + 1, [])
        elif parsed.path.endswith("/categories"):
            body = [{"id": 3, "name": "Querétaro"}]
        elif parsed.path.endswith("/users"):
            body = [{"id": 1, "name": "Usuario del sitio"}]
        elif parsed.path.endswith("sitemap_index.xml"):
            locs = "".join(f"<sitemap><loc>{SITE}/{n}</loc></sitemap>" for n in ("post-sitemap.xml", "attachment-sitemap.xml"))
            body_path.write_text(f"<sitemapindex>{locs}</sitemapindex>", encoding="utf-8")
            header_path.write_text("HTTP/1.1 200\r\n", encoding="latin-1")
            return 200, 0
        elif parsed.path.endswith("post-sitemap.xml"):
            # The real sitemap drops the tab of a legacy slug; that URL matches only after the loose comparison.
            urls = [SAME, EDITED, f"{SITE}/2013/05/03/notavieja./",f"{SITE}/2019/03/01/portada/", f"{SITE}/2026/01/02/nueva/"]
            locs = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
            body_path.write_text(f"<urlset>{locs}</urlset>", encoding="utf-8")
            header_path.write_text("HTTP/1.1 200\r\n", encoding="latin-1")
            return 200, 0
        body_path.write_text(json.dumps(body), encoding="utf-8")
        pages = 1 if body else 0
        header_path.write_text(f"HTTP/1.1 200\r\nX-WP-Total: {len(body)}\r\nX-WP-TotalPages: {pages}\r\n", encoding="latin-1")
        return 200, 0

    return fetch


def test_collect_sitemap_and_export_apply_the_queretaro_rules(tmp_path: Path) -> None:
    requested: list[str] = []
    client = Client(tmp_path, 0, fetcher=fake_site(requested))
    SOURCE.collect_posts(tmp_path, 0, client=client)
    SOURCE.collect_sitemap(tmp_path, 0, client=client)

    years = [int(parse_qs(urlparse(u).query)["after"][0][:4]) + 1 for u in requested if "/posts?" in u]
    assert years == [*range(2018, 2026), *range(2012, 2018)]  # 2018-2025 first; 2026 never requested
    assert not any("attachment-sitemap" in u for u in requested)
    assert not (tmp_path / "raw" / "posts_outside").exists()

    report = SOURCE.export_delivery(tmp_path, tmp_path / "out", "2026-10-28")
    target = tmp_path / "out" / "noticiasdequeretaro"
    articles = pd.read_parquet(target / "articles.parquet.gzip")
    assert list(articles.columns) == WORDPRESS_ARTICLE_COLUMNS
    assert articles["wp_post_id"].tolist() == [101, 103, 104, 105, 106, 108]
    assert set(articles["authors"]) == {"Brenda"}  # Yoast author, not the users endpoint
    assert set(articles["topic"]) == {"Querétaro"}
    assert articles.set_index("wp_post_id").loc[105, "url"] == LEGACY  # kept exactly, not repaired

    duplicates = pd.read_csv(target / "audit" / "excluded_duplicate_import.csv", encoding="utf-8-sig")
    assert duplicates[["wp_post_id", "kept_wp_post_id", "exclude_reason"]].values.tolist() == [[102, 101, "duplicate import"]]
    excluded = pd.read_csv(target / "audit" / "excluded_invalid.csv", encoding="utf-8-sig")
    assert excluded["wp_post_id"].tolist() == [107]
    assert "manual_review_note" not in excluded.columns

    flags = pd.read_csv(target / "audit" / "quality_flags.csv", encoding="utf-8-sig").set_index("wp_post_id")
    assert flags.loc[[103, 104], "flag_dup_url"].all() and not flags.loc[101, "flag_dup_url"]
    assert flags.loc[105, "flag_legacy_url"] and "whitespace" in flags.loc[105, "legacy_url_problem"]
    assert flags.loc[106, "flag_cover_page"] and flags.loc[106, "flag_empty_body"]
    assert flags.loc[108, "flag_video_page"]
    legacy = pd.read_csv(target / "audit" / "legacy_urls.csv", encoding="utf-8-sig")
    assert legacy["wp_post_id"].tolist() == [105]

    assert report["rows_collected"] == 8
    assert (report["rows_excluded_invalid"], report["rows_excluded_duplicate_import"], report["rows_delivered"]) == (1, 1, 6)
    assert report["api_x_wp_total_by_year"]["2013"] == 5
    sitemap = report["sitemap"]
    assert sitemap["sitemap_urls_matched"] == {"exact": 3, "after removing whitespace and decoding": 1}
    assert sitemap["sitemap_not_in_api_by_result"] == {"outside 2012-2025 (by URL date)": 1}
    assert (target / "audit" / "sitemap_vs_api_by_month.csv").exists()

    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["rows"] == 6
    assert "audit/excluded_duplicate_import.csv" in [f["file"] for f in manifest["files"]]


def test_registry_and_parameters() -> None:
    assert load_source("noticiasdequeretaro") is SOURCE
    assert SOURCE.api == f"{SITE}/wp-json/wp/v2"
    assert (SOURCE.first_date, SOURCE.last_date) == ("2012-01-01", "2025-12-31")

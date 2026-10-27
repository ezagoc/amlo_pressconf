from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd


CRAWLER_DIR = Path(__file__).resolve().parents[1]
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

from crawler_core.polemon import (  # noqa: E402
    WORDPRESS_ARTICLE_COLUMNS,
    Client,
    Stop,
    collect_posts,
    export_delivery,
)
from crawler_core.wordpress_articles import article_fields_from_post, base_article_row  # noqa: E402


def sample_post(post_id: int, date: str, title: str, content: str, author: str = "Jorge Gómez Naredo") -> dict[str, object]:
    return {
        "id": post_id,
        "date": date,
        "date_gmt": date,
        "modified": date,
        "slug": f"post-{post_id}",
        "link": f"https://polemon.mx/post-{post_id}/",
        "status": "publish",
        "title": {"rendered": title},
        "excerpt": {"rendered": "<p>Resumen &amp; más</p>"},
        "content": {"rendered": content},
        "categories": [6, 2],
        "tags": [184],
        "author": 10,
        "jetpack_featured_media_url": "",
        "yoast_head_json": {"author": author},
    }


POSTS_2019 = [
    sample_post(
        773, "2019-09-03T16:44:15", "La poesía de <em>Eduardo</em> Galeano",
        '<p>Texto principal.</p><div class="polem-entity-placement"><img src="https://polemon.mx/ad.jpg"></div>'
        '<div class="sharedaddy">Compartir</div><p>Segundo párrafo.</p>',
    ),
    sample_post(26, "2019-01-02T10:00:00", "feminismos", "<p>adsasdadsads</p>"),
    sample_post(900, "2019-10-01T20:00:00", "En vivo", '<iframe src="https://www.youtube.com/embed/x"></iframe>'),
    sample_post(901, "2019-10-02T09:00:00", "Cartón del día", '<p><img src="https://polemon.mx/carton.jpg"></p>'),
]


def fake_api(requested: list[str]):
    """Polemon API stand-in: posts only in 2019, two categories, a closed users endpoint."""

    def fetch(url: str, body_path: Path, header_path: Path) -> tuple[int, int]:
        requested.append(url)
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        status, body, pages = 200, [], 1
        if parsed.path.endswith("/posts"):
            body = POSTS_2019 if query["after"][0].startswith("2018-12-31") else []
            pages = 1 if body else 0
        elif parsed.path.endswith("/categories"):
            body = [{"id": 2, "name": "Política"}, {"id": 6, "name": "Cultura &amp; libros"}]
        elif parsed.path.endswith("/users"):
            status, body = 401, {"code": "rest_user_cannot_view"}
        body_path.write_text(json.dumps(body), encoding="utf-8")
        header_path.write_text(f"HTTP/1.1 {status}\r\nX-WP-Total: {len(body)}\r\nX-WP-TotalPages: {pages}\r\n",
                               encoding="latin-1")
        return status, 0

    return fetch


def test_collect_and_export_match_wordpress_article_schema(tmp_path: Path) -> None:
    requested: list[str] = []
    collect_posts(tmp_path, 0, client=Client(tmp_path, 0, fetcher=fake_api(requested)))

    assert sum("/posts?" in url for url in requested) == 11  # one request per year 2015-2025
    year_2019 = parse_qs(urlparse(requested[4]).query)
    assert year_2019["after"] == ["2018-12-31T23:59:59"]
    assert year_2019["before"] == ["2020-01-01T00:00:00"]
    assert (tmp_path / "raw" / "users" / "page_001.json.status401").exists()

    report = export_delivery(tmp_path, tmp_path / "out", "2026-10-27")
    target = tmp_path / "out" / "polemon"
    articles = pd.read_parquet(target / "articles.parquet.gzip")

    assert list(articles.columns) == WORDPRESS_ARTICLE_COLUMNS
    assert report["rows_collected"] == 4
    assert report["rows_excluded_invalid"] == 1
    assert articles["wp_post_id"].tolist() == [773, 900, 901]
    first = articles.iloc[0]
    assert first["title"] == "La poesía de Eduardo Galeano"
    assert first["main_text"] == "Texto principal.\nSegundo párrafo."  # ad banner and share box dropped
    assert first["summary"] == "Resumen & más"
    assert first["authors"] == "Jorge Gómez Naredo"
    assert first["topic"] == "Cultura & libros"
    assert first["category_names"] == "Cultura & libros; Política"
    assert first["category_ids"] == "6;2"
    assert first["date"] == "2019-09-03T16:44:15"
    assert first["source_id"] == "polemon"
    assert pd.isna(first["tag_names"])

    flags = pd.read_csv(target / "audit" / "quality_flags.csv", encoding="utf-8-sig").set_index("wp_post_id")
    assert bool(flags.loc[900, "flag_video_page"]) is True
    assert bool(flags.loc[901, "flag_empty_body"]) is True
    excluded = pd.read_csv(target / "audit" / "excluded_invalid.csv", encoding="utf-8-sig")
    assert excluded["wp_post_id"].tolist() == [26]

    report_file = json.loads((target / "crawl_report.json").read_text(encoding="utf-8"))
    assert list(report_file) == ["source_id", "source_name", "rows", "output_file", "row_groups", "errors",
                                 "missing_main_text", "min_date", "max_date", "exported_at"]
    assert report_file["rows"] == 3
    assert report_file["output_file"] == "articles.parquet.gzip"
    assert report_file["missing_main_text"] == 2  # the video page and the image-only post
    assert (report_file["min_date"], report_file["max_date"]) == ("2019-09-03T16:44:15", "2019-10-02T09:00:00")

    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["rows"] == 3
    assert manifest["files"][0]["file"] == "articles.parquet.gzip"


def test_columns_match_wordpress_extractor_rows() -> None:
    # A row as extract_wordpress_articles builds it: discovery fields, then the post's fields.
    row = base_article_row(pd.Series(dtype=object))
    row.update(article_fields_from_post(sample_post(1, "2019-01-01T00:00:00", "t", "<p>x</p>")))
    assert WORDPRESS_ARTICLE_COLUMNS == list(row)
    assert len(WORDPRESS_ARTICLE_COLUMNS) == 28


def test_block_stops_at_once_without_retry(tmp_path: Path) -> None:
    calls: list[str] = []

    def blocked(url: str, body_path: Path, header_path: Path) -> tuple[int, int]:
        calls.append(url)
        body_path.write_text("<html>Just a moment...</html>", encoding="utf-8")
        return 403, 0

    try:
        Client(tmp_path, 0, fetcher=blocked).get("https://polemon.mx/wp-json/wp/v2/posts", "posts/page_001.json")
    except Stop as exc:
        assert "blocked" in str(exc)
    else:
        raise AssertionError("a block must stop collection")
    assert len(calls) == 1


def test_three_errors_in_a_row_stop(tmp_path: Path) -> None:
    calls: list[str] = []

    def failing(url: str, body_path: Path, header_path: Path) -> tuple[int, int]:
        calls.append(url)
        body_path.write_text("error", encoding="utf-8")
        return 500, 0

    try:
        Client(tmp_path, 0, fetcher=failing).get("https://polemon.mx/wp-json/wp/v2/posts", "posts/page_001.json")
    except Stop as exc:
        assert "3 consecutive errors" in str(exc)
    else:
        raise AssertionError("repeated errors must stop collection")
    assert len(calls) == 3
    ledger = (tmp_path / "requests.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(ledger) == 3

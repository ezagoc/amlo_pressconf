from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd


CRAWLER_DIR = Path(__file__).resolve().parents[1]
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

from crawler_core.depeso import (  # noqa: E402
    DEPESO_SOURCES,
    build_archive_page_url,
    crawl_depeso_sources,
    load_source_state,
)


def sample_post(post_id: int, date: str) -> dict[str, object]:
    return {
        "id": post_id,
        "date": date,
        "modified": date,
        "slug": f"post-{post_id}",
        "link": f"https://depesoyucatan.com/policia/post-{post_id}/",
        "title": {"rendered": f"Post {post_id}"},
        "excerpt": {"rendered": "Resumen"},
        "content": {"rendered": "<p>Texto principal</p>"},
        "categories": [7],
        "tags": [11],
        "_embedded": {
            "author": [{"name": "Reportera"}],
            "wp:term": [
                [{"taxonomy": "category", "name": "Policía"}],
                [{"taxonomy": "post_tag", "name": "Yucatán"}],
            ],
        },
    }


def test_archive_url_uses_stable_id_order() -> None:
    url = build_archive_page_url("https://depeso.com/", page=9, per_page=100)
    query = parse_qs(urlparse(url).query)

    assert query["page"] == ["9"]
    assert query["per_page"] == ["100"]
    assert query["orderby"] == ["id"]
    assert query["order"] == ["asc"]
    assert query["_embed"] == ["author,wp:term"]


def test_short_page_is_saved_and_marks_source_complete(tmp_path: Path) -> None:
    db_path = tmp_path / "depeso.sqlite"

    def fake_fetch(url: str, timeout: float, **kwargs: object) -> dict[str, object]:
        return {
            "status": 200,
            "text": json.dumps([sample_post(181019, "2017-03-05T08:35:09")]),
            "error": pd.NA,
        }

    results = crawl_depeso_sources(
        ["depesoyucatan"],
        state_db_path=db_path,
        per_page=100,
        pause_seconds=0,
        request_retries=0,
        progress_every_pages=0,
        fetcher=fake_fetch,
    )

    assert results[0].complete is True
    assert results[0].rows_saved == 1
    state = load_source_state(db_path, "depesoyucatan")
    assert state["stop_reason"] == "short_final_page"
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT title, main_text, authors, category_names FROM articles"
        ).fetchone()
    assert row == ("Post 181019", "Texto principal", "Reportera", "Policía")


def test_page_cap_resumes_from_exact_next_page(tmp_path: Path) -> None:
    db_path = tmp_path / "depeso.sqlite"
    requested_pages: list[int] = []

    def fake_fetch(url: str, timeout: float, **kwargs: object) -> dict[str, object]:
        page = int(parse_qs(urlparse(url).query)["page"][0])
        requested_pages.append(page)
        posts = [sample_post(180000 + page, f"2017-03-{page:02d}T08:00:00")]
        return {"status": 200, "text": json.dumps(posts), "error": pd.NA}

    for _ in range(2):
        crawl_depeso_sources(
            ["depeso"],
            state_db_path=db_path,
            per_page=1,
            pause_seconds=0,
            request_retries=0,
            max_pages_per_run=1,
            progress_every_pages=0,
            fetcher=fake_fetch,
        )

    assert requested_pages == [1, 2]
    state = load_source_state(db_path, "depeso")
    assert state["next_page"] == 3
    assert state["per_page"] == 1
    assert state["complete"] == 0
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 2

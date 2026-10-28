"""Noticias de Querétaro (noticiasdequeretaro.com.mx), 2012-2025, through the generic WordPress API collector.

Authorized by Kevin on 2026-10-27: WordPress REST API only, 2.5 s between requests, raw responses kept
locally, stop at once on a Cloudflare / rate-limit block or repeated errors, 2026 not requested. Years
2018-2025 first, then 2012-2017. The sitemap step makes no API calls for posts outside 2012-2025: this
site's URLs carry the date (/YYYY/MM/DD/slug/), so the build classifies them offline.

Kevin's rules (2026-10-27, 2026-10-28): legacy 2012-2016 URLs that no longer work are kept exactly as the
API gives them and flagged (rule L), never repaired; front-page ("portada") and video posts are kept and
flagged (rules C and V); posts sharing a URL with an identical title and text are one post imported twice
and only the lowest post id is kept (rule D), the others sharing a URL are kept (rule U). Authors come
from yoast_head_json.author; categories are given by name.

    python code/01-crawlers/scripts/crawl_wordpress_api.py export --source noticiasdequeretaro \
        --state-dir <dir> --out-dir <dir> --sample-dir <sample run>
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote

import pandas as pd

from crawler_core import wordpress_api as wp
from crawler_core.wordpress_api import (
    CSV,
    DUP_BODY_MIN_CHARS,
    INVALID_RULES,
    SHORT_CHARS,
    WORDPRESS_ARTICLE_COLUMNS,
    WordPressSource,
    legacy_url_problems,
    load_ledger,
    n,
    sitemap_locs,
)


URL_DATE = re.compile(r"/(20\d\d)/(\d\d)/\d\d/")


def exact_key(u: str) -> str:
    return u.rstrip("/").lower()


def loose_key(u: str) -> str:
    """The sitemap drops the tabs and control characters of the legacy slugs and percent-encodes the mojibake,
    so legacy URLs are matched again after decoding and removing whitespace, control characters and the
    zero-width space (U+200B, the last character of the class below)."""
    return re.sub(r"[\x00-\x20\x7f​]", "", unquote(u)).rstrip("/").lower()


class NoticiasDeQueretaro(WordPressSource):
    source_id = "noticiasdequeretaro"
    source_name = "Noticias de Queretaro"
    site = "https://noticiasdequeretaro.com.mx"
    years = range(2012, 2026)
    year_order = [*range(2018, 2026), *range(2012, 2018)]
    sitemap_candidates = ["sitemap_index.xml", "sitemap.xml", "wp-sitemap.xml"]
    fetch_posts_outside = False
    # /users answers here, but Kevin asked for the Polemon method: the author field each post carries.
    author_sources = ("yoast",)
    # The daily front-page posts are galleries whose images sit outside the content HTML, and Kevin keeps them.
    media_includes_featured = True
    video_post_format = True
    # Rule C: "Consulta aquí nuestras portadas", "¡Conoce la portada de hoy!", "Portadas 10 Noviembre 2015",
    # and the gallery posts titled only with a date ("13 de Octubre 2016").
    cover_title = re.compile(r"\bportadas?\b", re.I)
    date_only_title = re.compile(r"^\s*\d{1,2} de [a-záéíóú]+ (?:de |del )?\d{4}\s*$", re.I)
    flag_legacy_urls = True
    drop_duplicate_imports = True
    flag_no_title = True
    quality_flag_columns = ["legacy_url_problem", "dup_title_group", "dup_title_count", "dup_body_group", "dup_body_count",
                            "dup_url_group", "dup_url_count", "wp_format", "author_source",
                            "content_image_count", "embed_count", "embedded_tweet_count"]

    def monthly_table(self, ctx: SimpleNamespace) -> pd.DataFrame:
        """Collected and delivered posts per month, with the API's own monthly totals from the sample run."""
        api_month_totals = {}
        if ctx.sample_dir and (ctx.sample_dir / "monthly_counts_2012_2025.csv").exists():
            mc = pd.read_csv(ctx.sample_dir / "monthly_counts_2012_2025.csv", encoding="utf-8-sig")
            api_month_totals = dict(zip(mc["month"], mc["articles"]))
        months = [str(m) for m in pd.period_range(self.first_date[:7], self.last_date[:7], freq="M")]
        t = pd.DataFrame({"month": months})
        t["api_reported"] = t["month"].map(api_month_totals)
        t["articles_collected"] = t["month"].map(ctx.posts["date"].str[:7].value_counts()).fillna(0).astype(int)
        t["articles_delivered"] = t["month"].map(ctx.clean["date"].str[:7].value_counts()).fillna(0).astype(int)
        t["year_median"] = t.groupby(t["month"].str[:4])["articles_collected"].transform("median")
        flags = []
        for count, med in zip(t["articles_collected"], t["year_median"]):
            f = ["empty"] if count == 0 else ([] + (["low: under 25% of the year's monthly median"] if count < 0.25 * med else [])
                                              + (["low: under 10 posts"] if count < 10 else []))
            flags.append("; ".join(f))
        t["flag"] = flags
        return t

    def sitemap_check(self, state_dir: Path, posts: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
        """Post sitemaps vs API: missing URLs both ways and per-month counts by the date in the URL."""
        sm = {}
        for f in sorted((state_dir / "raw" / "sitemap").glob("*")):
            if f.suffix in (".headers", ".part") or ".failed" in f.name or not re.search(r"post-sitemap\d*\.xml$", f.name):
                continue
            b = f.read_bytes()
            if b"<urlset" in b[:3000]:
                for u in sitemap_locs(b):
                    sm.setdefault(exact_key(u), (u, f.name))
        api_exact = set(posts["url"].map(exact_key))
        api_loose = set(posts["url"].map(loose_key))
        sm_loose = {loose_key(u) for u, _ in sm.values()}
        rows, matched = [], {"exact": 0, "after removing whitespace and decoding": 0}
        for k, (u, fname) in sorted(sm.items()):
            if k in api_exact:
                matched["exact"] += 1
                continue
            if loose_key(u) in api_loose:
                matched["after removing whitespace and decoding"] += 1
                continue
            m = URL_DATE.search(u)
            ym = f"{m.group(1)}-{m.group(2)}" if m else ""
            where = (f"outside {self.year_span} (by URL date)" if ym and not (self.first_date[:7] <= ym <= self.last_date[:7])
                     else "no date in URL" if not ym else "not in the API table")
            rows.append({"url": u, "sitemap_file": fname, "url_month": ym, "result": where})
        not_in_api = pd.DataFrame(rows, columns=["url", "sitemap_file", "url_month", "result"])
        in_sm = posts["url"].map(exact_key).isin(sm) | posts["url"].map(loose_key).isin(sm_loose)
        not_in_sm = posts.loc[~in_sm, ["post_id", "url", "date"]]
        by_month = pd.Series([f"{m.group(1)}-{m.group(2)}" for u, _ in sm.values() if (m := URL_DATE.search(u))]).value_counts()
        api_by_url_month = pd.Series([f"{m.group(1)}-{m.group(2)}" for u in posts["url"] if (m := URL_DATE.search(u))]).value_counts()
        api_by_post_month = posts["date"].str[:7].value_counts()
        months = [str(m) for m in pd.period_range(self.first_date[:7], self.last_date[:7], freq="M")]
        cmp_ = pd.DataFrame({"url_month": months})
        cmp_["sitemap_urls"] = cmp_["url_month"].map(by_month).fillna(0).astype(int)
        cmp_["api_urls"] = cmp_["url_month"].map(api_by_url_month).fillna(0).astype(int)
        cmp_["sitemap_minus_api"] = cmp_["sitemap_urls"] - cmp_["api_urls"]
        cmp_["api_posts_by_publication_month"] = cmp_["url_month"].map(api_by_post_month).fillna(0).astype(int)
        cmp_["sitemap_not_in_api"] = cmp_["url_month"].map(not_in_api["url_month"].value_counts()).fillna(0).astype(int)
        span = self.year_span.replace("-", "_")
        totals = {"sitemap_urls": len(sm), "sitemap_urls_matched": matched, f"api_posts_{span}": len(posts),
                  "api_distinct_urls": len(api_exact), "api_posts_in_sitemap": int(in_sm.sum()),
                  "sitemap_not_in_api": len(not_in_api), "sitemap_not_in_api_by_result": not_in_api["result"].value_counts().to_dict(),
                  "api_not_in_sitemap": len(not_in_sm),
                  "api_not_in_sitemap_by_year": not_in_sm["date"].str[:4].value_counts().sort_index().to_dict()}
        return not_in_api, not_in_sm, cmp_, totals

    def write_sitemap_check(self, ctx: SimpleNamespace, audit: Path) -> dict | None:
        if not (ctx.state_dir / "raw" / "sitemap").exists():
            return None
        not_in_api, not_in_sm, by_month, totals = self.sitemap_check(ctx.state_dir, ctx.posts)
        not_in_api.to_csv(audit / "sitemap_urls_not_in_api.csv", **CSV)
        not_in_sm.rename(columns={"post_id": "wp_post_id"}).to_csv(audit / "api_urls_not_in_sitemap.csv", **CSV)
        by_month.to_csv(audit / "sitemap_vs_api_by_month.csv", **CSV)
        return totals

    def legacy_rule_vs_sample(self, sample_dir: Path | None) -> dict | None:
        """Rule L against the sample run, where each link was actually opened."""
        if not (sample_dir and (sample_dir / "samples.csv").exists()):
            return None
        s = pd.read_csv(sample_dir / "samples.csv", encoding="utf-8-sig")
        s = s[s["link"].notna()]
        s["broken_live"] = s["error"].eq("page_http_0") | s["page_title"].eq("Inicio - Noticias de Querétaro")
        s["flagged"] = s["link"].map(legacy_url_problems).ne("")
        return {"sampled_links": len(s), "broken_live": int(s["broken_live"].sum()), "flagged": int(s["flagged"].sum()),
                "broken_and_flagged": int((s["broken_live"] & s["flagged"]).sum()),
                "broken_not_flagged": int((s["broken_live"] & ~s["flagged"]).sum()),
                "flagged_but_opened": int((~s["broken_live"] & s["flagged"]).sum())}

    def report(self, ctx: SimpleNamespace) -> dict:
        posts, c, excluded, dup, articles = ctx.posts, ctx.clean, ctx.excluded, ctx.duplicates, ctx.articles
        labels = self.flag_labels
        ledger = load_ledger(ctx.state_dir)
        api_ledger = [e for e in ledger if not e["file"].startswith("sitemap/")]
        back = pd.read_parquet(ctx.target / wp.OUTPUT_FILE)
        expected_by_year = {}
        for y in self.years:
            h = ctx.state_dir / "raw" / "posts" / str(y) / "page_001.json.headers"
            m = re.search(r"(?im)^x-wp-total:\s*(\d+)", h.read_text(encoding="latin-1")) if h.exists() else None
            expected_by_year[str(y)] = int(m.group(1)) if m else None
        return {
            "source_id": self.source_id, "built_at_utc": wp.now(), "date_range_local": f"{self.first_date}..{self.last_date}",
            "collection": {"requests": len(api_ledger), "failed_attempts": sum(1 for e in api_ledger if e["problem"]),
                           "first_fetch_utc": min(e["fetched_at_utc"] for e in api_ledger),
                           "last_fetch_utc": max(e["fetched_at_utc"] for e in api_ledger),
                           "pause_seconds": self.pause_seconds},
            "sitemap_requests": {"requests": len(ledger) - len(api_ledger),
                                 "failed_attempts": sum(1 for e in ledger if e["problem"] and e["file"].startswith("sitemap/"))},
            "api_x_wp_total_by_year": expected_by_year,
            "rows_collected_by_year": posts["date"].str[:4].value_counts().sort_index().to_dict(),
            "rows_collected": len(posts), "rows_excluded_invalid": len(excluded),
            "rows_excluded_duplicate_import": len(dup), "rows_delivered": len(articles),
            "duplicate_import_groups": int(dup["url"].nunique()),
            "rows_delivered_by_year": articles["date"].str[:4].value_counts().sort_index().to_dict(),
            "ten_minute_times_share_by_year": posts.assign(y=posts["date"].str[:4], t=posts["date"].str.match(r".{14}\d0:00$"))
            .groupby("y")["t"].mean().round(3).to_dict(),
            "excluded_by_rule": excluded["exclude_rule"].value_counts().to_dict(),
            "flag_counts": {lab: int(c[k].sum()) for k, lab in labels.items()}
            | {"any flag": int(c["flags"].ne("").sum()), "no flag": int(c["flags"].eq("").sum())},
            "flag_counts_2018_2025": {lab: int(c.loc[c["date"] >= "2018", k].sum()) for k, lab in labels.items()},
            "legacy_url_by_year": c.loc[c["flag_legacy_url"], "date"].str[:4].value_counts().sort_index().to_dict(),
            "legacy_url_rule_vs_sample": self.legacy_rule_vs_sample(ctx.sample_dir),
            "authors": {"missing": int(articles["authors"].isna().sum()), "distinct": int(articles["authors"].nunique()),
                        "top": articles["authors"].value_counts().head(10).to_dict()},
            "categories_unknown_ids": sorted({i for ids in posts["categories_unknown"] for i in ids}),
            "missing_values": {k: int(articles[k].isna().sum()) for k in WORDPRESS_ARTICLE_COLUMNS},
            "read_back": {"rows": len(back), "columns_match": list(back.columns) == WORDPRESS_ARTICLE_COLUMNS,
                          "duplicate_wp_post_id": int(back["wp_post_id"].duplicated().sum()),
                          "duplicate_url": int(back["url"].duplicated().sum()),
                          "blank_title": int((back["title"].isna() | back["title"].astype(str).str.strip().eq("")).sum()),
                          "dates_outside_range": int((~back["date"].between(self.first_date, self.last_date + "T23:59:59")).sum())},
            "sitemap": ctx.sitemap_totals,
        }

    # ---- audit texts ----

    @staticmethod
    def flag_sentence(counts: dict) -> str:
        return "; ".join(f"{k} {n(v)}" for k, v in counts.items())

    @staticmethod
    def legacy_sentence(r: dict) -> str:
        by_year = ", ".join(f"{y}: {n(v)}" for y, v in r["legacy_url_by_year"].items())
        s = r["legacy_url_rule_vs_sample"]
        check = (f" In the sample run, where {s['sampled_links']} links were opened one by one, the rule flagged "
                 f"{s['broken_and_flagged']} of the {s['broken_live']} links that did not open and "
                 f"{s['flagged_but_opened']} of the links that did.") if s else ""
        return f"{n(r['flag_counts']['legacy URL that may not open'])} posts ({by_year}).{check}"

    @staticmethod
    def sitemap_sentence(r: dict) -> str:
        sm = r["sitemap"]
        if not sm:
            return "Sitemap check: not run."
        parts = "; ".join(f"{k}: {n(v)}" for k, v in sm["sitemap_not_in_api_by_result"].items())
        loose = sm["sitemap_urls_matched"]["after removing whitespace and decoding"]
        return (f"Sitemap check: {n(sm['api_posts_in_sitemap'])} of the {n(sm['api_posts_2012_2025'])} collected posts are in the "
                f"post sitemaps ({n(loose)} legacy URLs match only after removing the tabs and decoding, because the sitemap "
                f"cleans them); {n(sm['api_not_in_sitemap'])} collected posts are not; {n(sm['sitemap_not_in_api'])} sitemap URLs "
                f"were not collected ({parts or 'none'}). Monthly comparison by the date in the URL: `sitemap_vs_api_by_month.csv`.")

    def audit_markdown(self, r: dict, export_date: str) -> str:
        col = r["collection"]
        rb = r["read_back"]
        lines = [
            f"# Noticias de Queretaro export audit - {export_date}", "",
            f"- {n(r['rows_delivered'])} posts in 14 years ({r['date_range_local']}, local publication date), WordPress article schema, gzip Parquet.",
            f"- Collected {n(r['rows_collected'])} posts with {n(col['requests'])} WordPress API requests ({col['failed_attempts']} failed attempts), "
            f"{col['first_fetch_utc'][:16]} to {col['last_fetch_utc'][:16]} UTC. "
            + ("Every year matches the API's own total (`X-WP-Total`)." if r["api_x_wp_total_by_year"] == r["rows_collected_by_year"]
               else "Some years differ from the API's own total (`X-WP-Total`); see `export_audit.json`."),
            f"- Duplicate imports: the old system created some 2012-2016 posts more than once under different post IDs and one URL. "
            f"Where the title and text are identical, only the lowest post ID is kept; {n(r['rows_excluded_duplicate_import'])} copies "
            f"in {n(r['duplicate_import_groups'])} URLs are excluded and listed in `excluded_duplicate_import.csv`. "
            f"{n(r['flag_counts']['URL shared with another post'])} posts still share a URL because their title or text differ; "
            "all are kept and linked by `dup_url_group`.",
            f"- {n(r['rows_excluded_invalid'])} invalid pages excluded; listed in `excluded_invalid.csv`. Rules: `CLEANING_RULES.md`.",
            f"- `articles.parquet.gzip` read back: {n(rb['rows'])} rows; duplicate post IDs {rb['duplicate_wp_post_id']}, duplicate URLs "
            f"{rb['duplicate_url']}, blank titles {rb['blank_title']}, dates outside the range {rb['dates_outside_range']}.",
            f"- Review flags kept (`quality_flags.csv`): {self.flag_sentence(r['flag_counts'])}.",
            f"- Legacy URLs (`legacy_urls.csv`): {self.legacy_sentence(r)}",
            f"- Publication times on a whole 10-minute mark (seconds 00, minute ending in 0), share by year: "
            + ", ".join(f"{y}: {v:.0%}" for y, v in r["ten_minute_times_share_by_year"].items())
            + ". Rounded times in the early years suggest the old posts were imported from an earlier system (inference).",
            f"- Volume: about 2,500-3,000 posts a month until June 2016, about 570-1,250 a month from July 2016 on; "
            f"June-August 2025 have about half the usual monthly count (`monthly_counts.csv`). The post sitemaps list the same "
            "number of posts for those months, so the API did not miss them; the drop coincides with the most frequent 2025 "
            "author publishing almost nothing from June to mid-August and with no posts on most Sundays in that period.",
            f"- {self.sitemap_sentence(r)}",
            "- Not collected: tag names (`tags`, `tag_names` empty; `tag_ids` kept), deleted posts and posts from 2026. "
            "Images, videos and embedded documents were not downloaded; their URLs are in the post HTML.",
        ]
        return "\n".join(lines) + "\n"

    def cleaning_rules_markdown(self, r: dict, excluded: pd.DataFrame) -> str:
        lines = [
            "# Noticias de Queretaro cleaning rules", "",
            "The collected table is never modified. Invalid pages are excluded by rule; every other",
            "suspicious post is kept and flagged in `quality_flags.csv`.", "",
            "## Excluded (invalid pages)", "",
            "Media below means an in-body image, an embedded video or frame, an embedded tweet, a featured image,",
            "or a gallery, video or image post format (the daily front-page posts are galleries with no body HTML).", "",
            *[f"- **{k}**: {v}." for k, v in INVALID_RULES.items()], "",
        ]
        if len(excluded) == 0:
            lines.append("No post matched these rules.")
        elif len(excluded) <= 40:
            lines.append("Excluded posts:")
            lines.append("")
            for _, e in excluded.iterrows():
                lines.append(f"- {e['post_id']} ({e['date'][:10]}, rule {e['exclude_rule']}): {e['title'] or '(no title)'}")
        else:
            lines.append(f"{n(len(excluded))} posts excluded; see `excluded_invalid.csv`.")
        lines += [
            "", "## Excluded (duplicate imports)", "",
            "- **D, duplicate import**: two or more post IDs carry the same URL with exactly the same title and main text",
            "  (posts created more than once by the old 2012-2016 system). The lowest post ID is kept and the others are",
            f"  excluded: {n(r['rows_excluded_duplicate_import'])} posts in {n(r['duplicate_import_groups'])} URLs, listed in",
            "  `excluded_duplicate_import.csv` with the kept post ID (`kept_wp_post_id`).",
        ]
        lines += [
            "", "## Kept with flags", "",
            f"- **V, video or livestream page**: body under {SHORT_CHARS} characters and an embedded video player (`<iframe>` or `<video>`) or the video post format.",
            f"- **C, front-page post**: the title contains \"portada\"/\"portadas\", or the title is only a date and the body is under {SHORT_CHARS} characters. Kept as Kevin asked.",
            "- **E, no text**: empty body; these posts are images or video and are valid content.",
            f"- **S, short body**: 1 to {SHORT_CHARS - 1} characters.",
            "- **T, duplicate title**: same title after normalizing quotes, spaces and case; `dup_title_group` links them.",
            f"- **B, duplicate body**: same body after normalizing spaces, only for bodies of {DUP_BODY_MIN_CHARS}+ characters; `dup_body_group` links them.",
            "- **L, legacy URL**: the URL's last segment holds a tab or control character, mojibake (Â/Ã), punctuation or a trailing",
            "  hyphen. These 2012-2016 URLs no longer open (they redirect to the home page or cannot be requested). The URL is kept",
            "  exactly as the API gives it and not repaired; `legacy_url_problem` says why. Title, date and text come from the API.",
            "- **U, URL shared with another post**: two or more post IDs carry the same URL but their title or text differ",
            "  (edited copies made by the old system); all are kept and `dup_url_group` links them. `wp_post_id` is the",
            "  unique key, not `url`.",
            "- **N, no title**: the post has an empty title; kept.", "",
            f"Counts: {self.flag_sentence(r['flag_counts'])}.", "",
            f"2018-2025 only: {self.flag_sentence(r['flag_counts_2018_2025'])}.", "",
            "Body text drops share buttons, related-post widgets and ad placements, as for Polemon.",
        ]
        return "\n".join(lines) + "\n"

    def readme_markdown(self, r: dict) -> str:
        excl = (f"{n(r['rows_excluded_invalid'])} invalid pages are excluded and listed in `audit/excluded_invalid.csv`."
                if r["rows_excluded_invalid"] else "No post was excluded as invalid.")
        by_year = ", ".join(f"{y}: {n(v)}" for y, v in r["rows_delivered_by_year"].items())
        return f"""# Noticias de Queretaro article export

{n(r['rows_delivered'])} posts from noticiasdequeretaro.com.mx published 2012-01-01 to 2025-12-31 (local publication date),
in `articles.parquet.gzip` (gzip Parquet). Includes short, image-only, front-page ("portada") and video posts,
which are flagged, not removed. {excl}

Posts by year: {by_year}.

Columns follow the WordPress article schema of `crawler/articles/<source_id>/`
(`code/01-crawlers/crawler_core/wordpress_articles.py`), as for Polemon; the core fields are `url`, `title`,
`summary`, `main_text`, `authors`, `date` and `topic`. `date` is the local publication time
(America/Mexico_City) as given by WordPress. `authors` comes from each post's Yoast SEO author field.
`topic`, `section` and `category_names` hold category names. `tags` and `tag_names` are empty because tag
names were not collected; `tag_ids` are kept.

**Old URLs.** {n(r['flag_counts']['legacy URL that may not open'])} posts from 2012-2016 have URLs that the site no longer
resolves (malformed slugs from an older system). They are kept exactly as the API gives them, not repaired,
and listed in `audit/legacy_urls.csv`; do not treat them as working links. Their title, date and text come
from the API. The old system also created some posts more than once under one URL: identical copies (same title
and text) are excluded, keeping the lowest post ID ({n(r['rows_excluded_duplicate_import'])} copies, listed in
`audit/excluded_duplicate_import.csv`); {n(r['flag_counts']['URL shared with another post'])} posts whose title or text differ
still share a URL and are all kept, so use `wp_post_id`, not `url`, as the unique key.

All posts were collected through the WordPress REST API only, 2.5 seconds between requests, 100 posts per
request, by local publication year. `crawl_report.json` has the same fields as the other sources in
`crawler/articles/`; `manifest.json` lists the size and SHA-256 of every file. `audit/` holds the export
audit, cleaning rules, per-post review flags (`quality_flags.csv`, joined on `wp_post_id`), monthly counts
and the sitemap reconciliation.
"""


SOURCE = NoticiasDeQueretaro()

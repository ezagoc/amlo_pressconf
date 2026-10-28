"""Exclusivas Puebla (exclusivaspuebla.com.mx), 2015-2025, through the generic WordPress API collector.

Not in the September registry; the progress sheet lists it (Periodicos row 272, founded 2009). Kevin
confirmed source_id "exclusivaspuebla" (the domain without its suffix, as for the other WordPress folders).

Authorized by Kevin on 2026-10-28: WordPress REST API only, raw responses kept locally, stop at once on a
block or repeated errors without trying another access method, 2026 not requested. The first run (2.5 s
between requests) stopped on three connection errors in a row (TLS failures and a timeout, no HTTP block);
Kevin had it resumed an hour later at 5 s between requests.

    python code/01-crawlers/scripts/crawl_wordpress_api.py collect --source exclusivaspuebla --state-dir <dir> --pause-seconds 5
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from crawler_core.wordpress_api import CSV, WordPressSource, n, norm_url


class ExclusivasPuebla(WordPressSource):
    source_id = "exclusivaspuebla"
    source_name = "Exclusivas Puebla"
    site = "https://exclusivaspuebla.com.mx"
    years = range(2015, 2026)
    # 2018-2025 first, then the older years, as for Noticias de Querétaro.
    year_order = [*range(2018, 2026), *range(2015, 2018)]
    pause_seconds = 5.0
    sitemap_candidates = ["sitemap_index.xml", "sitemap.xml", "wp-sitemap.xml"]
    # No API calls for posts outside 2015-2025: Kevin asked for no 2026 requests. URLs carry no date, so the
    # sitemap reconciliation classifies the sitemap-only URLs by their <lastmod> instead.
    fetch_posts_outside = False
    # Authors: the posts carry no Yoast author field; /users is open, so the Polemon order (users, then
    # Yoast) gives every post a name. Cleaning follows Polemon (a featured image alone is not content).
    # Rule C: the 2025 daily front pages ("Portada Mx 26 Agosto", "Portada Puebla 7 Octubre"), an embedded
    # issuu PDF with no text. Stricter than "portada" alone, which would catch two Playboy cover stories.
    cover_title = re.compile(r"^\s*portadas?\s+(?:mx|m[eé]xico|puebla|exclusivas)\b", re.I)
    flag_no_title = True  # two 2018-2019 articles have an empty title; kept and flagged (rule N)
    quality_flag_columns = [*WordPressSource.quality_flag_columns, "wp_format"]

    def sitemap_reconciliation(self, state_dir: Path, posts: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
        """As the generic check, but sitemap-only URLs are classified by <lastmod>, and repeated entries are counted."""
        entries = []
        for f in sorted((state_dir / "raw" / "sitemap").glob("post-sitemap*.xml")):
            data = f.read_bytes().decode("utf-8", "replace")
            for block in re.findall(r"<url>(.*?)</url>", data, re.S):
                loc = re.search(r"<loc>\s*([^<]+?)\s*</loc>", block)
                lastmod = re.search(r"<lastmod>\s*([^<]+?)\s*</lastmod>", block)
                if loc:
                    entries.append((html.unescape(loc.group(1)), lastmod.group(1) if lastmod else "", f.name))
        sitemap_urls: dict[str, tuple[str, str, str]] = {}
        for url, lastmod, name in entries:
            sitemap_urls.setdefault(norm_url(url), (url, lastmod, name))
        api_in = {norm_url(u) for u in posts["url"]}
        missing = []
        for key, (url, lastmod, name) in sorted(sitemap_urls.items()):
            if key in api_in:
                continue
            result = (f"modified {lastmod[:4]} (outside {self.year_span}, not collected)" if lastmod[:4] > str(self.years[-1])
                      else "not in the API")
            missing.append({"url": url, "sitemap_file": name, "lastmod": lastmod, "result": result})
        not_in_api = pd.DataFrame(missing, columns=["url", "sitemap_file", "lastmod", "result"])
        absent = posts[~posts["url"].map(norm_url).isin(sitemap_urls)]
        not_in_sitemap = absent[["post_id", "url", "date"]].rename(columns={"post_id": "wp_post_id"})
        span = self.year_span.replace("-", "_")
        totals = {
            "sitemap_entries": len(entries),
            "sitemap_urls": len(sitemap_urls),
            "sitemap_entries_repeated": len(entries) - len(sitemap_urls),
            f"api_urls_{span}": len(api_in),
            "api_urls_in_sitemap": len(api_in & set(sitemap_urls)),
            f"sitemap_not_in_api_{span}": len(not_in_api),
            "sitemap_not_in_api_by_result": not_in_api["result"].value_counts().to_dict(),
            "api_not_in_sitemap": len(not_in_sitemap),
            "api_not_in_sitemap_by_month": absent["date"].str[:7].value_counts().sort_index().to_dict(),
        }
        return not_in_api, not_in_sitemap, totals

    # Wayback Machine CDX counts (Kevin 2026-10-28: at most 20 requests, counts only, no archived page opened),
    # saved by tools/wayback_count.py in <state_dir>/wayback/raw/<window>.json. Capture dates, not publication dates.
    WAYBACK_WINDOWS = {"mar": "2022-03-01..2022-03-31", "apr01_28": "2022-04-01..2022-04-28",
                       "apr29_may": "2022-04-29..2022-05-31"}
    NOT_ARTICLE = re.compile(r"^(?:wp-content|wp-json|wp-admin|wp-includes|category|tag|author|page|feed|comments)(?:/|$)")

    def wayback_check(self, state_dir: Path, posts: pd.DataFrame, sitemap_only: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
        """Archived article URLs (one path segment, HTTP 200) per capture window, matched to the collected posts
        and to the sitemap-only URLs; returns the April 1-28 URLs found in neither, and the totals."""
        api_month = {norm_url(u): d[:7] for u, d in zip(posts["url"], posts["date"])}
        sitemap = {norm_url(u) for u in sitemap_only["url"]}
        totals, missing = {}, pd.DataFrame(columns=["url", "first_capture_utc"])
        for label, window in self.WAYBACK_WINDOWS.items():
            path = state_dir / "wayback" / "raw" / f"{label}.json"
            if not path.exists():
                continue
            rows = json.loads(path.read_text(encoding="utf-8"))[1:]  # urlkey, timestamp, original, mimetype, statuscode
            first: dict[str, tuple[str, str]] = {}
            for _, ts, url, _, status in rows:
                key = norm_url(url)
                slug = key.partition("/")[2]
                if status == "200" and slug and "/" not in slug and not self.NOT_ARTICLE.match(slug):
                    if key not in first or ts < first[key][0]:
                        first[key] = (ts, url)
            in_api = [api_month[k] for k in first if k in api_month]
            neither = {k: v for k, v in first.items() if k not in api_month and k not in sitemap}
            start, end = window.split("..")
            totals[window] = {
                "captures": len(rows),
                "collected_posts_dated_in_window": int(posts["date"].str[:10].between(start, end).sum()),
                "article_urls": len(first),
                "in_api": len(in_api),
                "in_api_by_month": pd.Series(in_api, dtype=str).value_counts().sort_index().to_dict(),
                "sitemap_only": sum(1 for k in first if k not in api_month and k in sitemap),
                "in_neither": len(neither),
                "in_neither_by_capture_day": pd.Series([ts[:8] for ts, _ in neither.values()], dtype=str)
                .value_counts().sort_index().to_dict(),
            }
            if label == "apr01_28":
                missing = pd.DataFrame(
                    [{"url": url, "first_capture_utc": dt.datetime.strptime(ts, "%Y%m%d%H%M%S").strftime("%Y-%m-%dT%H:%M:%SZ")}
                     for ts, url in sorted(neither.values(), key=lambda v: (v[0], v[1]))],
                    columns=["url", "first_capture_utc"])
        return missing, totals

    def write_sitemap_check(self, ctx: SimpleNamespace, audit: Path) -> dict | None:
        totals = super().write_sitemap_check(ctx, audit)
        not_in_api, _, _ = self.sitemap_reconciliation(ctx.state_dir, ctx.posts)
        missing, ctx.wayback = self.wayback_check(ctx.state_dir, ctx.posts, not_in_api)
        if ctx.wayback:
            missing.to_csv(audit / "wayback_2022_04_01_28_urls_not_on_site.csv", **CSV)
        return totals

    def report(self, ctx: SimpleNamespace) -> dict:
        report = super().report(ctx)
        if ctx.wayback:
            report["wayback_cdx_counts"] = ctx.wayback
        return report

    def wayback_note(self, report: dict) -> list[str]:
        w = report.get("wayback_cdx_counts")
        if not w:
            return []
        mar, apr, may = (w["2022-03-01..2022-03-31"], w["2022-04-01..2022-04-28"], w["2022-04-29..2022-05-31"])
        bulk = sum(v for d, v in may["in_neither_by_capture_day"].items() if d >= "20220517")
        return [
            f"Wayback Machine check (CDX index only, {n(len(w))} requests 5 s apart on 2026-10-28; no archived page "
            f"was opened). The archive captured {n(apr['article_urls'])} article URLs of the site between 1 and 28 April "
            f"2022: {n(apr['in_api'])} are collected posts (all dated March 2022 or earlier) and {n(apr['in_neither'])} "
            "are neither in the API nor in the sitemaps (listed in `wayback_2022_04_01_28_urls_not_on_site.csv`), first "
            "captured on every one of the 28 days. For comparison, of the "
            f"{n(mar['article_urls'])} article URLs captured in March 2022, {n(mar['in_api'])} are collected posts. So "
            "the site did publish in early April 2022 and those posts are no longer on it. Capture dates are not "
            f"publication dates; at the March capture rate ({n(mar['in_api_by_month'].get('2022-03', 0))} of the "
            f"{n(mar['collected_posts_dated_in_window'])} March posts) the lost posts would number about "
            f"{round(apr['in_neither'] * mar['collected_posts_dated_in_window'] / mar['in_api_by_month']['2022-03'], -2):,.0f} "
            "(inference).",
            f"Captures from 29 April to 31 May 2022 include {n(may['in_neither'])} article URLs that the site no longer "
            f"has; {n(bulk)} of them come from five deep crawls on 17-29 May that also picked up older posts. Their "
            "publication dates are unknown without opening the archived pages (not done), so they may include other "
            "posts deleted before or during the 2022 move.",
        ]

    NOTES = [
        "Posts dated 2018 to July 2022 were moved into WordPress in one batch, newest first: along the publication "
        "date their post IDs fall (87,762 in January 2018 down to 2,229 in July 2022), and the modified time equals "
        "the publication time. Their dates come from the earlier system. Where the text says \"este lunes\" and so on, "
        "the weekday matches the publication day or the day before as often as in 2023-2025 (2018: 69%; 2023: 73%), so "
        "the dates look right to the day; times of day cluster at 10-11 and 23-01 h, unlike later years, and may "
        "reflect upload batches (inference).",
        "No post is dated 2022-04-01 to 2022-04-28 (April 2022 has 28 posts, all on 29-30 April); the gap falls inside "
        "the batch move. Every sitemap URL that was not collected was last modified in 2026, and no sitemap entry "
        "has a <lastmod> in those days other than 3 collected posts, so the posts are missing on the site itself, "
        "not only in the API.",
        "April and May 2024 have about a third of the usual daily posts (255 and 219) but no long gap. The sitemaps "
        "list no post outside 2026 that the API lacks, so the site published fewer posts then (normal volume returns "
        "on 4 June 2024, after the 2 June election).",
        "The first 140 API pages (2018 and 2019 up to page 47) were requested 2.5 s apart; that run stopped on three "
        "connection errors in a row (TLS failures and a timeout, no HTTP block). The rest, and the sitemaps, were "
        "requested 5 s apart an hour later.",
        "One post (id 193971) is dated 2015-12-11 while its id is among the newest; the date is probably wrong. "
        "There are no posts dated 2016 or 2017. The post is kept.",
        "Authors come from the WordPress users endpoint; 99.8% of posts carry the site account \"Exclusivas Puebla\".",
    ]

    def audit_markdown(self, report: dict, export_date: str) -> str:
        s = report["sitemap_reconciliation"]
        notes = self.NOTES + self.wayback_note(report) + [
            f"The post sitemaps repeat {n(s['sitemap_entries_repeated'])} entries and lack {n(s['api_not_in_sitemap'])} "
            "collected posts (`api_urls_not_in_sitemap.csv`). Nearly all are one file: post-sitemap299.xml came back "
            "with the same posts as post-sitemap.xml instead of the January 2019 posts it should hold; the rest sit at "
            "file boundaries that shifted while new posts went up during the one-hour download (inference)."]
        return super().audit_markdown(report, export_date).rstrip("\n") + "\n" + "".join(f"- {t}\n" for t in notes)

    def readme_markdown(self, report: dict) -> str:
        base = super().readme_markdown(report).replace(
            "5 seconds between requests,", "2.5 and then 5 seconds between requests (see below),")
        w = report.get("wayback_cdx_counts", {}).get("2022-04-01..2022-04-28")
        april = (f"1-28 April 2022; the Wayback Machine captured {n(w['in_neither'])} article URLs in those days that"
                 "\nthe site no longer has" if w else "1-28 April 2022 (missing on the site itself)")
        return base + "\n" + "\n".join([
            "**Dates.** Posts dated 2018 to July 2022 were moved into WordPress in one batch from an earlier system;",
            "their dates look right to the day, but times of day are less certain. There are no posts from",
            f"{april}. None are dated 2016-2017; one post is dated 2015-12-11, probably wrongly.",
            "The first 140 API pages were requested 2.5 seconds apart, the rest 5 seconds apart",
            "(after the site stopped answering three times in a row). See the export audit in `audit/`.",
            "",
        ])


SOURCE = ExclusivasPuebla()

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

import html
import re
from pathlib import Path

import pandas as pd

from crawler_core.wordpress_api import WordPressSource, n, norm_url


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
        notes = self.NOTES + [
            f"The post sitemaps repeat {n(s['sitemap_entries_repeated'])} entries and lack {n(s['api_not_in_sitemap'])} "
            "collected posts (`api_urls_not_in_sitemap.csv`). Nearly all are one file: post-sitemap299.xml came back "
            "with the same posts as post-sitemap.xml instead of the January 2019 posts it should hold; the rest sit at "
            "file boundaries that shifted while new posts went up during the one-hour download (inference)."]
        return super().audit_markdown(report, export_date).rstrip("\n") + "\n" + "".join(f"- {t}\n" for t in notes)

    def readme_markdown(self, report: dict) -> str:
        base = super().readme_markdown(report).replace(
            "5 seconds between requests,", "2.5 and then 5 seconds between requests (see below),")
        return base + "\n" + "\n".join([
            "**Dates.** Posts dated 2018 to July 2022 were moved into WordPress in one batch from an earlier system;",
            "their dates look right to the day, but times of day are less certain. There are no posts from",
            "1-28 April 2022 (missing on the site itself) and none dated 2016-2017; one post is dated 2015-12-11,",
            "probably wrongly. The first 140 API pages were requested 2.5 seconds apart, the rest 5 seconds apart",
            "(after the site stopped answering three times in a row). See the export audit in `audit/`.",
            "",
        ])


SOURCE = ExclusivasPuebla()

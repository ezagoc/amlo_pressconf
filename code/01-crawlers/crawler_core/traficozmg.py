"""Tráfico ZMG (traficozmg.com), through the generic WordPress API collector.

In the September registry as source_id traficozmg (row 184, media_type periodico, crawl_candidate True,
first_wave_candidate); the progress sheet lists it on Periodicos row 185.

Authorized by Kevin on 2026-10-30: WordPress REST API only, 5 s between requests, raw responses kept
locally, stop at once on a block (403/429/Cloudflare challenge) or 3 errors in a row without trying another
access method, 2026 not requested. The full run (2026-10-30, 342 API requests and 38 sitemap requests) had
no failed request; /users answered 401 as expected (authors come from Yoast).

    python code/01-crawlers/scripts/crawl_wordpress_api.py collect --source traficozmg --state-dir <dir>
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import pandas as pd

from crawler_core.wordpress_api import WordPressSource, n, norm_url


class TraficoZMG(WordPressSource):
    source_id = "traficozmg"
    source_name = "Tráfico ZMG"
    site = "https://traficozmg.com"
    years = range(2013, 2026)  # earliest post 2013-07-09 (screening of 2026-10-27)
    pause_seconds = 5.0
    # No API calls for posts outside the years: no 2026 requests.
    fetch_posts_outside = False
    flag_no_title = True  # one post has an empty title; kept and flagged (rule N)

    # The site has Jetpack sitemaps (sitemap-1.xml ... sitemap-36.xml: posts and pages together), not Yoast
    # post-sitemaps, and every post URL carries /YYYY/MM/, so sitemap-only URLs are classified by that path.
    JETPACK_SITEMAP = re.compile(r"^sitemap-\d+\.xml$")
    DATED = re.compile(r"^https://traficozmg\.com/(\d{4})/\d{2}/")

    def sitemap_reconciliation(self, state_dir: Path, posts: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
        """As the generic check, on the Jetpack sitemaps; sitemap-only URLs are classified by the year in the URL."""
        entries = []
        files = [f for f in (state_dir / "raw" / "sitemap").glob("sitemap-*.xml") if self.JETPACK_SITEMAP.match(f.name)]
        for f in sorted(files, key=lambda p: int(re.search(r"\d+", p.name).group())):
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
            dated = self.DATED.match(url)
            if not dated:
                result = "site page, not a post (no /YYYY/MM/ in the URL)"
            elif dated.group(1) > str(self.years[-1]):
                result = f"post URL dated {dated.group(1)} (outside {self.year_span}, not collected)"
            else:
                result = "not in the API"
            missing.append({"url": url, "sitemap_file": name, "lastmod": lastmod, "result": result})
        not_in_api = pd.DataFrame(missing, columns=["url", "sitemap_file", "lastmod", "result"])
        absent = posts[~posts["url"].map(norm_url).isin(sitemap_urls)]
        not_in_sitemap = absent[["post_id", "url", "date"]].rename(columns={"post_id": "wp_post_id"})
        span = self.year_span.replace("-", "_")
        totals = {
            "sitemap_files": len(files),
            "sitemap_entries": len(entries),
            "sitemap_urls": len(sitemap_urls),
            "sitemap_entries_repeated": len(entries) - len(sitemap_urls),
            f"api_urls_{span}": len(api_in),
            "api_urls_in_sitemap": len(api_in & set(sitemap_urls)),
            f"sitemap_not_in_api_{span}": len(not_in_api),
            "sitemap_not_in_api_by_result": not_in_api["result"].value_counts().to_dict(),
            "api_not_in_sitemap": len(not_in_sitemap),
        }
        return not_in_api, not_in_sitemap, totals

    # Checks of 2026-10-30 on the collected posts (offline).
    NOTES = [
        "The site posts regularly from October 2015. Before that the API has five posts: two dated 2013 and three "
        "dated 2014. Their IDs (4991-19669) and modified times (October 2015 to August 2016) suggest they were entered "
        "or re-dated when the site started (inference); they are kept as dated.",
        "2018-2025 has posts in every month (136 to 507), so no Wayback Machine check was made.",
        "Post IDs rise with the publication date: the monthly ID ranges never step back, and only 16 posts have an "
        "ID above the median ID of every day a week or more later. Three posts have IDs far below their day (created "
        "earlier, published later: 2021-11-20, 2022-06-21, 2025-02-23). There is no sign of a batch move.",
        "Dates were checked as for Exclusivas Puebla: where the text says \"este lunes\" and so on (7,131 posts), the "
        "weekday is the publication day or the day before in 85% of posts (81-92% by year). The dates look right to "
        "the day.",
        "Authors come from Yoast metadata (/users needs a login). The names are as the site gives them: of the "
        "delivered posts, 8,763 carry the account name \"chanito.pruebas\" and 3,905 carry \"[email protected]\" (the "
        "site hides an e-mail address there); 5,231 carry \"Redacción\".",
        "One post has an empty title; it is kept and flagged (rule N).",
    ]

    def audit_markdown(self, report: dict, export_date: str) -> str:
        s = report["sitemap_reconciliation"]
        span = self.year_span.replace("-", "_")
        notes = self.NOTES + [
            f"The {n(s['sitemap_files'])} Jetpack sitemaps list {n(s['sitemap_urls'])} URLs, posts and pages together "
            f"({n(s['sitemap_entries_repeated'])} repeated). All {n(s[f'api_urls_{span}'])} collected posts are in them. "
            "The URLs not collected (counts above) are 2026 posts, which were not requested (the API's total for all "
            "years minus the 2013-2025 posts gives the same number), and site pages such as the contact page."]
        return super().audit_markdown(report, export_date).rstrip("\n") + "\n" + "".join(f"- {t}\n" for t in notes)

    def readme_markdown(self, report: dict) -> str:
        return super().readme_markdown(report) + "\n" + "\n".join([
            "**Coverage and dates.** Regular posting starts in October 2015; five earlier posts are dated 2013-2014.",
            "2018-2025 has posts in every month. Post IDs and the weekdays named in the text show no sign of a batch",
            "move, and the dates look right to the day. Author names are as the site gives them, including an",
            "account name and a hidden e-mail address. See the export audit in `audit/`.",
            "",
        ])


SOURCE = TraficoZMG()

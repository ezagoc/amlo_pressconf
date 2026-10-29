"""La Pancarta de Quintana Roo (lapancartadequintanaroo.com.mx), through the generic WordPress API collector.

Not in the September registry; the progress sheet lists it (Periodicos row 257). source_id is the domain
without its suffix, as for the other WordPress folders.

Authorized by Kevin on 2026-10-28: WordPress REST API only, 5 s between requests, raw responses kept
locally, stop at once on a block or repeated errors without trying another access method, 2026 not requested.
The full run (2026-10-29, 1,080 API requests and 118 sitemap requests) had no failed request.

    python code/01-crawlers/scripts/crawl_wordpress_api.py collect --source lapancartadequintanaroo --state-dir <dir>
"""

from __future__ import annotations

import pandas as pd

from crawler_core.exclusivaspuebla import ExclusivasPuebla
from crawler_core.wordpress_api import WordPressSource, n


class LaPancartaDeQuintanaRoo(WordPressSource):
    source_id = "lapancartadequintanaroo"
    source_name = "La Pancarta de Quintana Roo"
    site = "https://lapancartadequintanaroo.com.mx"
    years = range(2016, 2026)  # earliest post 2016-02-29 (sample run)
    pause_seconds = 5.0
    # No API calls for posts outside the years: Kevin asked for no 2026 requests.
    fetch_posts_outside = False
    # Five posts went up twice (consecutive ids, same URL, title and text, 2023-2024): rule D keeps the lower id.
    drop_duplicate_imports = True
    flag_no_title = True  # three posts have an empty title; kept and flagged (rule N)
    # URLs carry no date and 2026 is not requested, so sitemap-only URLs are classified by <lastmod>, as for
    # Exclusivas Puebla.
    sitemap_reconciliation = ExclusivasPuebla.sitemap_reconciliation

    # Checks of 2026-10-29 on the collected posts (offline).
    NOTES = [
        "Monthly volume rises from about 500 posts to about 2,000 on 1 November 2021, when the account \"Redaccion La "
        "Pancarta de Quintana Roo\" starts posting about 60 a day (the whole site had about 19 a day in October 2021); "
        "it falls to about 900-1,600 a month from May 2024. This looks like an expansion of the site, not a batch move: "
        "day by day the post IDs rise with the publication date in every year (99.4% of days or more), and no post has "
        "an ID above every post dated a week or more later. From November 2021 to April 2024 the IDs follow the time "
        "of day less closely within a day (58% of consecutive posts in ID order, against 94% before and after) and 62% "
        "of posts have a modified time equal to the publication time, which fits posts written ahead and scheduled "
        "(inference).",
        "Dates were checked as for Exclusivas Puebla: where the text says \"este lunes\" and so on (25,558 posts), the "
        "weekday is the publication day or the day before in 90% of posts from November 2021 to April 2024, against "
        "86% from 2016 to October 2021 and 84% from May 2024. The dates look right to the day.",
        "February 2024 has 747 posts, half of January: every day has posts, but 6-25 February average about 19 a day "
        "against about 49 in January and 61 in March. The site published less; there is no gap, so no Wayback Machine "
        "check was made.",
        "The site's earliest post is dated 29 February 2016 (15 posts that day); the API has nothing earlier.",
        "Five posts went up twice (consecutive IDs, same URL, title and text, December 2023 to June 2024); the copy "
        "with the higher ID is excluded (`excluded_duplicate_import.csv`). Three posts have an empty title; they are "
        "kept and flagged.",
        "Authors come from the WordPress users endpoint.",
    ]

    def audit_markdown(self, report: dict, export_date: str) -> str:
        s = report["sitemap_reconciliation"]
        notes = self.NOTES + [
            f"All {n(s['sitemap_not_in_api_2016_2025'])} post-sitemap URLs that were not collected were last modified "
            "in 2026 (about 900 a month, January to October), as the 2026 posts would be; 2026 was not requested. "
            f"The sitemaps repeat {n(s['sitemap_entries_repeated'])} entries and lack {n(s['api_not_in_sitemap'])} "
            "collected posts (`api_urls_not_in_sitemap.csv`)."]
        return super().audit_markdown(report, export_date).rstrip("\n") + "\n" + "".join(f"- {t}\n" for t in notes)

    def cleaning_rules_markdown(self, report: dict, excluded: pd.DataFrame) -> str:
        return super().cleaning_rules_markdown(report, excluded).replace("## Kept with flags", "\n".join([
            "## Excluded (posted twice)",
            "",
            "- **D, duplicate import**: two post IDs carry the same URL with exactly the same title and main text",
            "  (consecutive IDs, posted twice). The lower post ID is kept and the other is excluded:",
            f"  {n(report['rows_excluded_duplicate_import'])} posts, listed in `excluded_duplicate_import.csv` with the "
            "kept post ID (`kept_wp_post_id`).",
            "",
            "## Kept with flags"]), 1)

    def readme_markdown(self, report: dict) -> str:
        return super().readme_markdown(report) + "\n" + "\n".join([
            "**Volume and dates.** The site posts about four times as much from November 2021 to April 2024 as",
            "before (a new newsroom account); post IDs and the weekdays named in the text show no sign of a batch",
            "move, and the dates look right to the day. February 2024 has fewer posts per day but no gap.",
            "The earliest post is dated 29 February 2016. See the export audit in `audit/`.",
            "",
        ])


SOURCE = LaPancartaDeQuintanaRoo()

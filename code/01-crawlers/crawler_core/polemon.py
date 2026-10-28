"""Polemon (polemon.mx), 2015-2025, through the generic WordPress API collector (crawler_core/wordpress_api.py).

Access rules agreed for this source (2026-10-26): WordPress REST API only (no article pages), 2.5 s
between requests, and stop at once on a Cloudflare / rate-limit block or after 3 errors in a row,
without trying any other access method. Deleted posts are not recovered. 196 requests collected all
14,809 posts; the users endpoint answers HTTP 401, so authors come from yoast_head_json.author.

    python code/01-crawlers/scripts/crawl_wordpress_api.py export --source polemon --state-dir <dir> --out-dir <dir>
"""

from __future__ import annotations

import pandas as pd

from crawler_core.wordpress_api import (
    DUP_BODY_MIN_CHARS,
    INVALID_RULES,
    OUTPUT_FILE,
    SHORT_CHARS,
    WordPressSource,
)


class Polemon(WordPressSource):
    source_id = "polemon"
    source_name = "Polemon"
    site = "https://polemon.mx"
    years = range(2015, 2026)
    # Read one by one; the build fails if rules I1-I3 stop catching any of them.
    reviewed_invalid = {
        26: ("feminismos", "adsasdadsads", "test post: the body is random letters"),
        29: ("cines", "jkasdfcadfadf", "test post: the body is random letters"),
        32: ("tomen", "", "test post: title only, empty body and empty source HTML"),
        16155: ("google-site-verification: googlea1d61bf0610190e7.html", "googlea1d61bf0610190e7",
                "Google Search Console site-verification page, not an article"),
    }

    def audit_markdown(self, report: dict, export_date: str) -> str:
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
            f"- `{OUTPUT_FILE}` read back: {c['rows_read_back']:,} rows; zero duplicate post IDs or URLs, blank titles, "
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

    def readme_markdown(self, report: dict) -> str:
        return "\n".join([
            "# Polemon article export",
            "",
            f"{report['rows_delivered']:,} posts from polemon.mx published {report['date_range_local'].replace('..', ' to ')} "
            f"(local publication date), in `{OUTPUT_FILE}` (gzip Parquet). Includes short, image-only and video posts.",
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
            "with code `code/01-crawlers/crawler_core/polemon.py`. `crawl_report.json` has the same fields as",
            "the other sources in `crawler/articles/`; `manifest.json` lists the size and SHA-256 of every",
            "file. `audit/` holds the export audit, cleaning rules, per-post review flags",
            "(`quality_flags.csv`, joined on `wp_post_id`), monthly counts and the sitemap reconciliation.",
            "",
        ])

    def cleaning_rules_markdown(self, report: dict, excluded: pd.DataFrame) -> str:
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


SOURCE = Polemon()

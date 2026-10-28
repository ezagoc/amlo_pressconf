"""Exclusivas Puebla (exclusivaspuebla.com.mx), 2015-2025, through the generic WordPress API collector.

Not in the September registry; the progress sheet lists it (Periodicos row 272, founded 2009) and the
first post the API returns is dated 2015-12-11. source_id follows the other WordPress folders: the
domain without its suffix.

Authorized by Kevin on 2026-10-28: WordPress REST API only, 2.5 s between requests, raw responses kept
locally, stop at once on a block or repeated errors without trying another access method, 2026 not
requested.

    python code/01-crawlers/scripts/crawl_wordpress_api.py collect --source exclusivaspuebla --state-dir <dir>
"""

from __future__ import annotations

from crawler_core.wordpress_api import WordPressSource


class ExclusivasPuebla(WordPressSource):
    source_id = "exclusivaspuebla"
    source_name = "Exclusivas Puebla"
    site = "https://exclusivaspuebla.com.mx"
    years = range(2015, 2026)
    # 2018-2025 first, then the older years, as for Noticias de Querétaro.
    year_order = [*range(2018, 2026), *range(2015, 2018)]
    sitemap_candidates = ["sitemap_index.xml", "sitemap.xml", "wp-sitemap.xml"]
    # No API calls for posts outside 2015-2025: Kevin asked for no 2026 requests.
    fetch_posts_outside = False


SOURCE = ExclusivasPuebla()

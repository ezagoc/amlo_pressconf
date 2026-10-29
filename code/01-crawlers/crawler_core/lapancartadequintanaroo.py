"""La Pancarta de Quintana Roo (lapancartadequintanaroo.com.mx), through the generic WordPress API collector.

Not in the September registry; the progress sheet lists it (Periodicos row 257). source_id is the domain
without its suffix, as for the other WordPress folders.

Authorized by Kevin on 2026-10-28: WordPress REST API only, 5 s between requests, raw responses kept
locally, stop at once on a block or repeated errors without trying another access method, 2026 not requested.

    python code/01-crawlers/scripts/crawl_wordpress_api.py collect --source lapancartadequintanaroo --state-dir <dir>
"""

from __future__ import annotations

from crawler_core.wordpress_api import WordPressSource


class LaPancartaDeQuintanaRoo(WordPressSource):
    source_id = "lapancartadequintanaroo"
    source_name = "La Pancarta de Quintana Roo"
    site = "https://lapancartadequintanaroo.com.mx"
    years = range(2016, 2026)  # earliest post 2016-02-29 (sample run)
    pause_seconds = 5.0
    # No API calls for posts outside the years: Kevin asked for no 2026 requests.
    fetch_posts_outside = False


SOURCE = LaPancartaDeQuintanaRoo()

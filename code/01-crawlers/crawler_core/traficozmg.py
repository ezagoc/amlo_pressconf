"""Tráfico ZMG (traficozmg.com), through the generic WordPress API collector.

In the September registry as source_id traficozmg (row 184, media_type periodico, crawl_candidate True,
first_wave_candidate); the progress sheet lists it on Periodicos row 185.

Authorized by Kevin on 2026-10-30: WordPress REST API only, 5 s between requests, raw responses kept
locally, stop at once on a block (403/429/Cloudflare challenge) or 3 errors in a row without trying another
access method, 2026 not requested.

    python code/01-crawlers/scripts/crawl_wordpress_api.py collect --source traficozmg --state-dir <dir>
"""

from __future__ import annotations

from crawler_core.wordpress_api import WordPressSource


class TraficoZMG(WordPressSource):
    source_id = "traficozmg"
    source_name = "Tráfico ZMG"
    site = "https://traficozmg.com"
    years = range(2013, 2026)  # earliest post 2013-07-09 (screening of 2026-10-27)
    pause_seconds = 5.0
    # No API calls for posts outside the years: no 2026 requests.
    fetch_posts_outside = False


SOURCE = TraficoZMG()

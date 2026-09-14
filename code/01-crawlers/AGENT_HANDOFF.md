# Agent Handoff: Mexican Newspaper Article Crawling

Date: 2026-08-04
Repo: `C:\Users\Dell\Documents\GitHub\amlo_pressconf`
Crawler folder: `code\01-crawlers`
Source workbook: `C:\Users\Dell\Dropbox\Media\data\00-newspaper_data\mexican_newspapers.xlsx`

## Goal

Build a reusable scraping pipeline for Mexican newspapers listed in
`mexican_newspapers.xlsx`. The desired output is one article-level dataset per
source, following the rough schema used by the existing crawlers:

- `url`
- `title`
- `summary`
- `main_text`
- `authors`
- `date`
- `topic`

The broader target is to collect all articles available online for each
newspaper, starting from the earliest discoverable date, while keeping scraping
polite, resumable, auditable, and easy to extend.

## Current Folder State

`code\01-crawlers` contains one Python script and several exploratory notebooks.

- `jornada.py`
  - Cleanest existing crawler.
  - Scrapes La Jornada by date and topic.
  - Date range currently set to `2009-01-01` through `2024-10-30`.
  - Extracts `url`, `title`, `summary`, `main_text`, `authors`, `date`, `topic`.
  - Saves daily progress to parquet and resumes from the last saved date.
  - Uses `media_output_path(...)` from `project_paths`.

- `campechehoy.ipynb`
  - Daily page crawler for `http://campechehoy.mx/{year}/{month}/{day}/`.
  - Output path in notebook:
    `../../data/00-newspaper_data/crawler/campechehoy/articles.parquet`.
  - Embedded output shows many 404s from older daily pages.

- `tabascohoy.ipynb`
  - Category/page crawler for `https://www.tabascohoy.com/{category}/page/{page}/`.
  - Includes exploratory Selenium / undetected-chromedriver code.
  - Embedded outputs show Cloudflare-like "Just a moment..." pages, SSL issues,
    and interrupted runs.
  - It appears to have duplicated/experimental cells and one output path typo or
    copy-paste artifact referencing `qrohoy`.

- `voz_imagen_oaxaca.ipynb`
  - Category/page crawler for `https://www.nvinoticias.com/{category}?page={page}`.
  - Output path in notebook:
    `../../data/00-newspaper_data/crawler/vozeimagen/articles.parquet`.
  - Very large notebook due to embedded outputs.

- `yucatan.ipynb`
  - Category/page crawler for
    `https://www.yucatan.com.mx/seccion/{category}/page/{page}`.
  - Tracks scraped URLs in JSON.
  - Current local `scraped_urls.json` contains placeholder `example.com` URLs,
    so do not treat it as production state.

- `lajornadamaya.ipynb`
  - More polished/refactored than the other notebooks.
  - Contains helpers for polite sleeps, retries, Spanish date parsing, sitemap or
    listing discovery, article extraction, topic extraction, and parquet saving.

- `lajornada_maya_idcrawl.parquet`
  - Existing parquet sidecar in this folder.
  - Not inspected deeply in this pass because the available Python launcher in
    the shell was not configured, and the bundled Python lacked some network
    dependencies. Use bundled runtime paths from Codex if needed.

## Workbook Audit

Workbook sheets:

- `Periodicos`: main metadata table.
- `Pictures`: small journalist/photo helper table.
- `Estados`: state to `CVE_ENT` lookup table.

Main table shape:

- 245 rows
- 28 columns

Important columns in `Periodicos`:

- `bene_final`
- `name.comsoc`
- `source. Name`
- `sa.de.cv`
- `name.page`
- `names.transcripts`
- `names.conference`
- `twitter.handle`
- `youtube.channel`
- `url`
- `state`
- `municipality`
- `CVE_ENT`
- `scrapped`
- `subscription`
- `folder_name`
- `file_name`
- `year_founded`
- `not.newspaper`
- `antibot.java`
- `last.date.scrapped`
- `ideology.subjective`
- `ideology.source`
- `type.media`
- `journalist.mananera` in normalized ASCII references; source column is
  `journalist.mañanera`

Observed metadata counts:

- `url`: 206 non-null rows.
- `type.media`: 208 non-null rows.
- `type.media == periodico`: 187 rows.
- `scrapped == 1`: 9 rows.
- `scrapped == 0`: 80 rows.
- `scrapped` missing: 156 rows.
- `subscription == 1`: 4 rows.
- `antibot.java == 1`: 1 row.
- `folder_name`: 7 non-null rows.
- `file_name`: 7 non-null rows.
- `last.date.scrapped`: 0 non-null rows.

URL and metadata quality:

- 206 rows have URLs.
- 202 unique non-missing URLs.
- No malformed URLs were found in a basic syntax check.
- No state/CVE mismatches were found where both values are populated and the
  state exists in `Estados`.
- There are many missing states and CVEs:
  - `state` missing: 124 rows.
  - `CVE_ENT` missing: 149 rows.
- `last.date.scrapped` is empty everywhere, so the workbook is not yet a useful
  crawl ledger.

Already marked as scraped:

- Diario Basta
- Quintana Roo Hoy
- Campeche Hoy
- Noticias Voz e Imagen
- El Diario de Yucatan
- 24 Horas el Diario sin Limites
- 24 Horas el Diario sin Limites Puebla
- La Jornada de Morelos
- La Jornada

Promising first-wave set:

- 161 rows are newspapers with URL present, not already scraped, not marked
  subscription, and not marked antibot.

Duplicate/platform clusters worth exploiting:

- `oem.com.mx`: 15 rows.
- `elimparcial.com`: 3 rows.
- `lajornadamaya.mx`: 3 rows, representing Yucatan, Quintana Roo, Campeche.
- `yucatan.com.mx`: 2 rows, one duplicate already scraped.
- `diariopresente.mx`: 2 rows.
- `tiempo.com.mx`: 2 rows.

Ownership or media groups also cluster sources:

- `medios masivos mexicanos`: 24 rows.
- `la jornada demos`: 6 rows.
- `diario 24 horas`: 5 rows.
- `grupo canton`: 4 rows.
- `grupo healy`: 3 rows.

## Spot Checks and Source Notes

Live spot checks through browser/search showed:

- La Jornada is accessible at `https://www.jornada.com.mx/`.
- La Jornada has an RSS page at `https://www.jornada.com.mx/rss/`.
- La Jornada has archive/previous edition pages.
- NVI Noticias is accessible at `https://www.nvinoticias.com/`.
- El Informador is accessible at `https://www.informador.mx/`.
- El Informador's terms/search pages indicate the site is open and indexable.
- El Sol de Mexico redirects into the OEM platform at
  `https://oem.com.mx/elsoldemexico/`.

Attempted local network probing with bundled Python hit environment issues:

- The bundled Python has `pandas`, but did not have `requests`.
- A standard-library `urllib` attempt failed with an OpenSSL Applink error in
  this Windows runtime.

Recommendation: use repo-managed dependencies or the Codex bundled runtime
carefully. For crawler implementation, prefer a dedicated virtual environment or
project dependency setup with `requests`, `httpx`, `beautifulsoup4`, `lxml`,
`trafilatura`, `playwright`, `pandas`, `pyarrow`, and optionally `duckdb`.

## Recommended Architecture

Do not build one bespoke crawler per newspaper. Build a layered crawler:

1. Registry layer
2. Capability probe
3. URL discovery strategies
4. Article fetcher
5. Article extractor
6. State database / queue
7. Parquet output writer
8. QA and reporting layer

### 1. Registry Layer

Create a normalized source registry from `mexican_newspapers.xlsx`.

Suggested fields:

- `source_id`
- `source_name`
- `canonical_url`
- `domain`
- `state`
- `municipality`
- `cve_ent`
- `media_type`
- `owner_group`
- `conference_name`
- `transcript_name`
- `twitter_handle`
- `youtube_channel`
- `subscription_flag`
- `antibot_flag`
- `not_newspaper_flag`
- `scraped_flag`
- `folder_name`
- `file_name`
- `platform_cluster`
- `crawl_strategy`
- `available_from`
- `last_successful_scrape`
- `notes`

Rules:

- Preserve the Excel workbook as the human-editable source of truth.
- Generate a machine-readable `sources.parquet` or `sources.csv`.
- Assign missing `folder_name` values deterministically from URL/domain and
  newspaper name.
- Do not overwrite user metadata without producing a reviewable diff/report.

### 2. Capability Probe

For each URL, test:

- Homepage reachable.
- Final redirect URL.
- HTTP status.
- `robots.txt` reachable.
- `sitemap.xml` or sitemap index.
- RSS/feed endpoints.
- WordPress REST API:
  - `/wp-json/wp/v2/posts?per_page=1`
- JSON-LD on homepage/article pages.
- OpenGraph metadata.
- Category/archive pages.
- Date archive pages.
- Search endpoint.
- Cloudflare or JavaScript challenge.
- Paywall/subscription markers.

Save this as:

- `crawl_capabilities.parquet`
- `crawl_capabilities.csv`
- optional markdown summary for manual review.

### 3. Strategy Ladder

Try strategies in this order:

1. WordPress REST API
2. XML sitemap / sitemap index
3. RSS feeds
4. Platform-specific adapters
5. Static category pagination
6. Date archive pages
7. Site search by date/topic
8. Playwright-rendered pages
9. External historical sources for gaps, such as Wayback or Common Crawl,
   only when appropriate and legally/ethically acceptable.

The goal is to use the most structured source available before falling back to
HTML crawling.

### 4. URL Discovery

Each strategy should emit rows into a common URL queue:

- `source_id`
- `url`
- `canonical_url`
- `discovery_strategy`
- `discovered_at`
- `source_listing_url`
- `listing_page`
- `candidate_date`
- `candidate_topic`
- `status`
- `error`

The queue should deduplicate by canonical URL and preserve discovery provenance.

### 5. Article Fetching

Fetcher rules:

- Use a clear research user agent.
- Respect per-domain rate limits.
- Use exponential backoff for transient errors.
- Save raw HTML, preferably compressed, for auditability and reprocessing.
- Track status codes and fetch errors.
- Do not bypass paywalls.
- Do not escalate bot evasion beyond normal browser rendering unless the user
  explicitly decides to handle that source differently.

Suggested raw layout:

```text
data/00-newspaper_data/crawler/raw_html/
  source_id/
    yyyy/
      mm/
        url_hash.html.gz
```

### 6. Article Extraction

Use a common extractor first, then site-specific overrides.

Generic extraction order:

1. JSON-LD `NewsArticle` / `Article`.
2. OpenGraph and meta tags.
3. HTML article selectors.
4. Readability/trafilatura-style main text extraction.
5. Site-specific parser if generic extraction fails.

Target article schema:

- `source_id`
- `source_name`
- `url`
- `canonical_url`
- `title`
- `summary`
- `main_text`
- `authors`
- `date_published`
- `date_modified`
- `topic`
- `section`
- `tags`
- `state`
- `municipality`
- `cve_ent`
- `language`
- `scrape_timestamp`
- `discovery_strategy`
- `extractor_strategy`
- `raw_html_path`
- `status`
- `error`

Compatibility with existing output:

- Provide a simplified compatibility view containing:
  `url`, `title`, `summary`, `main_text`, `authors`, `date`, `topic`.

### 7. State Database

Use SQLite or DuckDB for crawl state. Recommended tables:

- `sources`
- `capabilities`
- `discovered_urls`
- `fetch_attempts`
- `article_extractions`
- `crawl_runs`
- `errors`

This makes the crawler resumable and inspectable. Parquet should be the final
analytical output, not the only operational state store.

### 8. Output Layout

Recommended layout:

```text
data/00-newspaper_data/crawler/
  registry/
    sources.parquet
    sources.csv
    crawl_capabilities.parquet
    crawl_capabilities.csv
  state/
    crawl_state.duckdb
  raw_html/
    <source_id>/
  articles/
    <source_id>/
      articles.parquet
      articles_compat.parquet
  logs/
    crawl_runs.parquet
    errors.parquet
  reports/
    capability_report.md
    source_progress.csv
```

## Platform Adapter Priorities

Start with clusters and high-yield sources:

1. Standardize existing scraped sources.
   - Convert `jornada.py` and the notebooks into importable scripts/modules.
   - Preserve their known behavior before refactoring heavily.

2. OEM adapter.
   - Covers 15 rows under `oem.com.mx`.
   - Likely high return from one adapter.

3. 24 Horas adapter.
   - Multiple rows in workbook.
   - Already has at least CDMX and Puebla marked as scraped.

4. La Jornada family adapter.
   - `jornada.com.mx`, `lajornadamaya.mx`, `lajornadamorelos.mx`.
   - Existing code and notebook work are useful starting points.

5. Grupo Canton adapter.
   - Diario Basta, Tabasco Hoy, Quintana Roo Hoy, Campeche Hoy.
   - Some sources are already marked scraped.
   - Tabasco Hoy may require special handling due to bot/Cloudflare-like pages.

6. El Imparcial / Grupo Healy adapter.
   - 3 rows under `elimparcial.com`.

7. Remaining first-wave easy sources.
   - Rank by capability probe:
     WordPress API > sitemap > RSS > clean static category pagination.

## Suggested Initial Implementation Plan

Phase 1: Normalize and report.

- Create `registry.py`.
- Read `mexican_newspapers.xlsx`.
- Normalize columns and URLs.
- Generate deterministic `source_id` and missing `folder_name`.
- Validate state/CVE consistency.
- Produce `sources.parquet`, `sources.csv`, and a metadata audit report.

Phase 2: Probe capabilities.

- Create `probe_sources.py`.
- For each active newspaper URL, test homepage, redirects, robots, sitemaps,
  feeds, WordPress API, and obvious bot/paywall markers.
- Save a capability table and rank sources by likely scrape difficulty.

Phase 3: Build common crawling core.

- `http_client.py`: rate limits, retries, user agent, backoff.
- `queue.py`: URL queue operations.
- `extractors.py`: generic article extraction.
- `storage.py`: DuckDB/SQLite plus parquet output.
- `schemas.py`: shared dataclasses or typed dictionaries.

Phase 4: Convert existing crawlers.

- Convert `jornada.py` into an adapter.
- Convert `lajornadamaya.ipynb` into an adapter.
- Convert one category-pagination notebook into an adapter.
- Keep compatibility output matching the old parquet schema.

Phase 5: Platform adapters.

- OEM.
- 24 Horas.
- Grupo Canton.
- El Imparcial.

Phase 6: QA and progress reporting.

- Report per source:
  - discovered URLs
  - fetched URLs
  - extracted articles
  - earliest date
  - latest date
  - null title rate
  - null main_text rate
  - errors by type
- Update `last.date.scrapped` only through an explicit workbook update step or
  reviewable export.

## Recommended File Names

Potential module layout:

```text
code/01-crawlers/
  crawler_core/
    __init__.py
    registry.py
    capabilities.py
    http_client.py
    discovery.py
    extraction.py
    storage.py
    schemas.py
    qa.py
  adapters/
    __init__.py
    jornada.py
    la_jornada_maya.py
    oem.py
    horas24.py
    grupo_canton.py
    elimparcial.py
    category_pagination.py
    wordpress.py
    sitemap.py
    rss.py
  scripts/
    build_registry.py
    probe_sources.py
    crawl_source.py
    crawl_batch.py
    export_articles.py
    report_progress.py
```

## Environment Notes

The current shell did not have `python` on PATH. Codex reported this bundled
Python path:

```text
C:\Users\Dell\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
```

The bundled runtime can read Excel with pandas, but local network probing from
that runtime had missing/dependent package issues. Before implementing crawlers,
set up or confirm a Python environment with:

- `pandas`
- `pyarrow`
- `requests` or `httpx`
- `beautifulsoup4`
- `lxml`
- `trafilatura`
- `duckdb`
- `playwright`
- `python-dotenv`

Existing `requirements.txt` should be checked and expanded rather than creating
an unrelated dependency path.

## Important Cautions

- Treat notebooks as prototypes, not production scripts.
- Do not trust embedded notebook outputs as current state.
- Do not trust `scraped_urls.json` in this folder; it currently contains
  placeholder `example.com` URLs.
- Do not mark workbook rows as complete just because a crawler ran. Require row
  counts, date ranges, and extraction quality checks.
- Do not bypass subscriptions or strong bot defenses.
- Keep raw HTML for auditability and future extractor improvements.
- Keep the workbook human-editable; generate machine-readable registry files
  from it.

## Best Next Task

Implement Phase 1:

1. Add `code/01-crawlers/crawler_core/registry.py`.
2. Add `code/01-crawlers/scripts/build_registry.py`.
3. Read `mexican_newspapers.xlsx`.
4. Normalize `Periodicos`.
5. Generate source IDs/folder names.
6. Write:
   - `data/00-newspaper_data/crawler/registry/sources.csv`
   - `data/00-newspaper_data/crawler/registry/sources.parquet`
   - `data/00-newspaper_data/crawler/reports/metadata_audit.md`

This creates the stable base for capability probing and batch crawling.

## Implemented Since This Handoff

Phase 1 and Phase 2 foundations now exist in code:

- `crawler_core/registry.py`
- `crawler_core/capabilities.py`
- `crawler_core/wordpress.py`
- `scripts/build_registry.py`
- `scripts/probe_sources.py`
- `scripts/discover_wordpress_urls.py`
- `scripts/extract_wordpress_articles.py`
- `scripts/discover_sitemap_urls.py`

Generated outputs are written under:

```text
C:\Users\Dell\Dropbox\Media\data\00-newspaper_data\crawler\registry
C:\Users\Dell\Dropbox\Media\data\00-newspaper_data\crawler\discovery
C:\Users\Dell\Dropbox\Media\data\00-newspaper_data\crawler\reports
```

The WordPress discovery script has two modes:

```powershell
# Pilot mode: first 5 pages per source, 100 posts per page.
python .\code\01-crawlers\scripts\discover_wordpress_urls.py

# Full mode: keep paginating until the WordPress API returns no more posts.
python .\code\01-crawlers\scripts\discover_wordpress_urls.py --all-pages

# Full mode for one source.
python .\code\01-crawlers\scripts\discover_wordpress_urls.py --source-id diariodelosaltos --all-pages
```

The full mode was smoke-tested on `diariodelosaltos`; it stopped naturally at
258 discovered URLs. The earlier 14,867-row WordPress file was only a capped
pilot: `max_pages=5`, `per_page=100`.

A full all-pages WordPress run completed into the checkpoint CSV and was then
finalized with:

```powershell
python .\code\01-crawlers\scripts\finalize_wordpress_discovery.py
```

The canonical full WordPress discovery file is now:

```text
C:\Users\Dell\Dropbox\Media\data\00-newspaper_data\crawler\discovery\discovered_urls_wordpress.parquet
```

It contains 3,016,117 deduplicated rows from 33 WordPress sources, with
3,016,114 usable URLs and 3 fetch-error rows. The full CSV checkpoint remains at
`discovered_urls_wordpress.checkpoint.csv`. The plain
`discovered_urls_wordpress.csv` may still be the older pilot CSV unless the
finalizer is rerun with `--promote-csv`, which copies the multi-GB checkpoint to
that final CSV path.

Environment note: Python HTTPS in the bundled Codex runtime has OpenSSL/Windows
certificate issues, so the probe/discovery fetch layer currently shells out to
`curl.exe --ssl-no-revoke` and parses the results in Python.

Once WordPress discovery is complete, run article extraction:

```powershell
python .\code\01-crawlers\scripts\extract_wordpress_articles.py --resume --timeout 30 --pause-seconds 0.1 --checkpoint-every 100
```

This reads `discovered_urls_wordpress.parquet`, fetches each post through the
WordPress REST API, extracts `title`, `summary`, `main_text`, `authors`, `date`,
`topic`, tags, and source metadata, and writes:

```text
C:\Users\Dell\Dropbox\Media\data\00-newspaper_data\crawler\articles\wordpress_articles.csv
C:\Users\Dell\Dropbox\Media\data\00-newspaper_data\crawler\articles\wordpress_articles.parquet
C:\Users\Dell\Dropbox\Media\data\00-newspaper_data\crawler\articles\<source_id>\articles.csv
C:\Users\Dell\Dropbox\Media\data\00-newspaper_data\crawler\articles\<source_id>\articles.parquet
C:\Users\Dell\Dropbox\Media\data\00-newspaper_data\crawler\reports\wordpress_article_extraction_report.md
```

The extractor was smoke-tested on three `diariodelosaltos` posts. All three
returned non-empty `main_text`.

For a larger stress test, start with `am`, the largest WordPress source in the
current discovery table:

```powershell
python .\code\01-crawlers\scripts\extract_wordpress_articles.py --source-id am --limit 5000 --resume --timeout 45 --pause-seconds 0.02 --checkpoint-every 1000 --progress-every 500 --progress-seconds 60 --batch-size 100 --workers 4
```

If that looks healthy, continue the same source without `--limit`:

```powershell
python .\code\01-crawlers\scripts\extract_wordpress_articles.py --source-id am --resume --timeout 45 --pause-seconds 0.02 --checkpoint-every 10000 --progress-every 5000 --progress-seconds 60 --batch-size 100 --workers 4
```

Use `--row-log` only for small tests; printing every URL for hundreds of
thousands of articles makes the terminal hard to read and can slow the run.
The extractor batches WordPress posts by ID with `--batch-size`; WordPress
usually caps `per_page` at 100, so speedups beyond that should come from
`--workers`, not larger batches. Start with `--workers 4`; if errors stay low
and the site is responsive, try `--workers 8`. Use `--batch-size 1` only as a
fallback for sources whose API rejects batched `include=` requests. If a long
run is interrupted with Ctrl+C, the current code will write partial outputs
before exiting.

AM stress-test note: an early `--batch-size 100 --workers 4` run produced many
timeouts and one large-response JSON truncation error. The extractor now requests
lean WordPress API fields (`content`, `title`, `excerpt`, dates, author, terms)
instead of full `_embed=1`, allows larger article API bodies, and prints a
sample error in progress lines. When continuing AM after that failed attempt,
include `--retry-errors`; otherwise previously failed rows will be treated as
already attempted.

Follow-up AM tests: the gentler 5,000-row retry succeeded and then another
5,000-row run also succeeded. Current combined article output has 10,214 AM rows
with 0 errors; 10,212 have non-empty body text. The 10,000 newer AM rows have
body text and category/tag IDs, but human-readable `topic/category_names` are
still missing because the first lean `_fields` selection did not include embedded
term objects. The request was adjusted again to use `_embed=wp:term` and
`_fields=..., _embedded`. If category names matter for already-extracted AM rows,
rerun with a fresh temporary output or add a targeted metadata-refresh step,
because `--retry-errors` will not revisit successful rows.

Large article-run recovery note: a later multi-source run saved
`wordpress_articles.checkpoint.csv` with 1,797,253 rows, then crashed during
final parquet writing because `category_ids` had mixed object values
(`ArrowTypeError: Expected bytes, got int`). The checkpoint is valid. The writer
now normalizes mixed object columns before parquet output, and
`scripts/finalize_wordpress_articles.py` can rebuild the final CSV/parquet/report
from the checkpoint without re-scraping:

```powershell
python .\code\01-crawlers\scripts\finalize_wordpress_articles.py --no-per-source
```

Omit `--no-per-source` when per-source CSV/parquet outputs should also be
rewritten; that is slower for million-row runs.

Sitemap discovery has also been scaffolded:

```powershell
python .\code\01-crawlers\scripts\discover_sitemap_urls.py --timeout 30 --pause-seconds 0.2
```

It targets `recommended_strategy == "sitemap"` by default, expands sitemap
indexes recursively, filters likely article URLs, and writes:

```text
C:\Users\Dell\Dropbox\Media\data\00-newspaper_data\crawler\discovery\discovered_urls_sitemap.csv
C:\Users\Dell\Dropbox\Media\data\00-newspaper_data\crawler\discovery\discovered_urls_sitemap.parquet
C:\Users\Dell\Dropbox\Media\data\00-newspaper_data\crawler\reports\sitemap_discovery_report.md
```

The report includes `earliest_lastmod`, `latest_lastmod`, `reaches_2018`, and
`reaches_2016`. This is intended to test whether sitemap discovery gives enough
historical coverage to be useful; sources that do not reach 2018/2016 should be
sent to another strategy.

## Current WordPress Article Storage

The current WordPress article storage format is per-source parquet, compressed
with gzip:

```text
C:\Users\Dell\Dropbox\Media\data\00-newspaper_data\crawler\articles\<source_id>\articles_part_*.parquet.gzip
```

Those per-source files are the authoritative WordPress article output. The
SQLite file at:

```text
C:\Users\Dell\Dropbox\Media\data\00-newspaper_data\crawler\articles\wordpress_articles.sqlite
```

is a resumable progress log for newer extraction runs. It should not be treated
as a complete archive of all WordPress articles if older rows were exported
before SQLite logging was introduced.

The latest discovery/export comparison showed:

- WordPress discovered URLs: 3,016,114
- WordPress exported article rows: 3,015,954
- Remaining rows: 160
- Remaining sources: `diariodelosaltos` 158, `suracapulco` 1, `lucesdelsiglo` 1

## Sitemap Article Extraction

Sitemap discovery completed with 1,126,584 rows, 1,126,577 URLs, and 21 sources.
The next strategy is generic HTML article extraction for those sitemap URLs.
This is necessarily less exact than the WordPress REST API, but it should recover
article text, dates, titles, authors, canonical URLs, and source metadata for
non-WordPress sources whose sitemaps reach 2016 or 2018.

The new extractor is:

```text
C:\Users\Dell\Documents\GitHub\amlo_pressconf\code\01-crawlers\scripts\extract_sitemap_articles.py
```

It reads:

```text
C:\Users\Dell\Dropbox\Media\data\00-newspaper_data\crawler\discovery\discovered_urls_sitemap.parquet
```

and writes resumable progress to:

```text
C:\Users\Dell\Dropbox\Media\data\00-newspaper_data\crawler\articles_sitemap\sitemap_articles.sqlite
```

Run a small test first:

```powershell
python .\code\01-crawlers\scripts\extract_sitemap_articles.py --source-id diariodemorelos --limit 100 --resume --timeout 60 --pause-seconds 0.05 --checkpoint-every 50 --progress-every 25 --progress-seconds 60 --workers 2 --no-final-output
```

If the first `diariodemorelos` test was run before the pandas `NA` parser fix,
the 100 rows may all show `TypeError: boolean value of NA is ambiguous`. Rerun
that test with `--retry-errors` so the failed rows are attempted again:

```powershell
python .\code\01-crawlers\scripts\extract_sitemap_articles.py --source-id diariodemorelos --limit 100 --resume --retry-errors --timeout 60 --pause-seconds 0.05 --checkpoint-every 50 --progress-every 25 --progress-seconds 60 --workers 2 --no-final-output
```

The fixed 100-row rerun produced 100 rows, 0 errors, 0 missing titles, 0 missing
dates, and 0 missing `main_text`. Six rows were author/profile pages such as
`/noticias/users/...`; the URL filter now excludes obvious non-article paths
(`users`, `author`, `tag`, `category/categories`, `search`, `feed`, etc.)
during future sitemap discovery, article extraction queueing, and parquet
export.

A later 5,000-row `diariodemorelos` run also completed cleanly. The sitemap
article SQLite now has 5,100 rows, all from `diariodemorelos`, with 0 errors,
0 missing titles, 0 missing dates, and 0 missing `main_text`. After the stricter
URL filter, 5,092 of those rows are article-like rows that will be included in
parquet export.

Filtered sitemap backlog after that run:

- Filtered sitemap article URLs: 1,126,473
- Done in `sitemap_articles.sqlite`: 5,092
- Remaining filtered URLs: 1,121,381
- `diariodemorelos`: 199,544 filtered URLs, 5,092 done, 194,452 remaining

Then export the tested source to per-source parquet:

```powershell
python .\code\01-crawlers\scripts\export_sitemap_articles_by_source.py --source-id diariodemorelos --chunksize 50000
```

To finish the rest of `diariodemorelos`:

```powershell
python .\code\01-crawlers\scripts\extract_sitemap_articles.py --source-id diariodemorelos --resume --timeout 75 --pause-seconds 0.05 --checkpoint-every 5000 --progress-every 1000 --progress-seconds 300 --workers 4 --no-final-output
```

Recovery note: a later continuation run crashed around the progress print
`2,000/189,531` with another pandas `NA` truth-value issue in the `main_text`
emptiness check. SQLite still contained 10,021 `diariodemorelos` rows and 0
errors after the crash. The extractor now uses explicit blank-value checks and
wraps each worker so unexpected page-level failures become row-level errors
instead of crashing the process. Use a smaller checkpoint interval for the next
resume run:

```powershell
python .\code\01-crawlers\scripts\extract_sitemap_articles.py --source-id diariodemorelos --resume --timeout 75 --pause-seconds 0.05 --checkpoint-every 1000 --progress-every 1000 --progress-seconds 300 --workers 4 --no-final-output
```

Latest check after the resumed `diariodemorelos` run:

- SQLite rows: 199,552
- Good filtered article rows: 199,513
- Remaining filtered `diariodemorelos` rows: 31
- Row-level errors: 31 (`missing_main_text`, timeouts, and one `http_status_500`)
- Missing any date among all rows: 0
- Date coverage: 2016-02-08 to 2026-08-18

The exporter now skips row-level errors by default, so parquet output contains
only successful article rows unless `--include-errors` is passed.

Retry the remaining `diariodemorelos` failures with:

```powershell
python .\code\01-crawlers\scripts\extract_sitemap_articles.py --source-id diariodemorelos --resume --retry-errors --timeout 120 --pause-seconds 0.1 --checkpoint-every 25 --progress-every 10 --progress-seconds 60 --workers 2 --no-final-output
```

Export `diariodemorelos` after retrying:

```powershell
python .\code\01-crawlers\scripts\export_sitemap_articles_by_source.py --source-id diariodemorelos --chunksize 50000
```

For a larger run that should last a while and cover several historically useful
sitemap sources:

```powershell
python .\code\01-crawlers\scripts\extract_sitemap_articles.py --source-id diariodemorelos --source-id diariodemexico --source-id laverdad --source-id actualidad --source-id eldiariodesonora --resume --timeout 75 --pause-seconds 0.05 --checkpoint-every 5000 --progress-every 1000 --progress-seconds 300 --workers 4 --no-final-output
```

When that finishes or is stopped, export those sources:

```powershell
python .\code\01-crawlers\scripts\export_sitemap_articles_by_source.py --source-id diariodemorelos --source-id diariodemexico --source-id laverdad --source-id actualidad --source-id eldiariodesonora --chunksize 50000
```

Latest sitemap article check on 2026-09-04:

- SQLite rows: 252,645
- Good filtered rows: 247,954
- Exported parquet so far: `diariodemorelos`, 4 parts, 199,544 rows
- `diariodemorelos`: 199,552 SQLite rows, 0 errors, 199,544 filtered URLs complete
- `diariodemexico`: 28,083 rows, 28,076 good rows, 7 `missing_main_text`
- `actualidad`: 16,413 rows, 16,393 good rows, 20 errors
- `laverdad`: 3,845 rows, 3,843 good rows, 2 HTTP 503 rows
- `mediosdigitalesdelpacifico`: 98 rows, 98 good rows
- `eldiariodesonora`: 4,654 rows, essentially all failed with `missing_main_text`

For now, do not include `eldiariodesonora` in large sitemap runs. It fetches
HTTP 200 pages but needs a source-specific HTML extractor because the generic
selectors are not finding body text.

Export the currently-good sitemap sources with:

```powershell
python .\code\01-crawlers\scripts\export_sitemap_articles_by_source.py --source-id diariodemorelos --source-id diariodemexico --source-id actualidad --source-id laverdad --source-id mediosdigitalesdelpacifico --chunksize 50000
```

Optionally retry the small number of row-level failures for the good sources:

```powershell
python .\code\01-crawlers\scripts\extract_sitemap_articles.py --source-id diariodemexico --source-id actualidad --source-id laverdad --resume --retry-errors --timeout 120 --pause-seconds 0.1 --checkpoint-every 25 --progress-every 10 --progress-seconds 60 --workers 2 --no-final-output
```

Recommended next sitemap run, excluding `eldiariodesonora`:

```powershell
python .\code\01-crawlers\scripts\extract_sitemap_articles.py --source-id grupoanimal --source-id ejecentral --source-id diariopresente_tabasco_elsoldelsureste --source-id meganoticias --source-id lajornadamaya_campeche --source-id lajornadamaya_quintana_roo --source-id lajornadamaya_yucatan --source-id elbravo --source-id lajornadaestadodemexico --source-id noroeste --resume --timeout 90 --pause-seconds 0.05 --checkpoint-every 1000 --progress-every 1000 --progress-seconds 300 --workers 4 --no-final-output
```

Export that next batch afterward:

```powershell
python .\code\01-crawlers\scripts\export_sitemap_articles_by_source.py --source-id grupoanimal --source-id ejecentral --source-id diariopresente_tabasco_elsoldelsureste --source-id meganoticias --source-id lajornadamaya_campeche --source-id lajornadamaya_quintana_roo --source-id lajornadamaya_yucatan --source-id elbravo --source-id lajornadaestadodemexico --source-id noroeste --chunksize 50000
```

Latest sitemap article check on 2026-09-05:

- SQLite rows: 340,990
- Good filtered rows against the discovery inventory: 327,949
- Remaining filtered discovery URLs: 798,524
- Exported parquet still only exists for `diariodemorelos`; the newer good
  sources have not yet been exported.

Strict quality counts (`no error`, `main_text` length >= 500, and any date):

- `diariodemorelos`: 187,388
- `grupoanimal`: 69,288
- `diariodemexico`: 27,924
- `actualidad`: 15,838
- `laverdad`: 3,829
- `mediosdigitalesdelpacifico`: 98
- `lajornadamaya_*`: 133 each
- `ejecentral`: only 794 usable; most rows are HTTP 403
- `diariopresente_tabasco_elsoldelsureste`: text is mostly present but dates
  are almost entirely missing
- `meganoticias`: text is partly present but dates are missing and 181 rows are
  HTTP 403
- `elbravo`: no errors, but sampled `main_text` is navigation/menu text rather
  than article body, and dates are missing
- `eldiariodesonora`: still unusable with the generic extractor

The sitemap exporter now supports quality gates:

```powershell
python .\code\01-crawlers\scripts\export_sitemap_articles_by_source.py --source-id diariodemorelos --source-id grupoanimal --source-id diariodemexico --source-id actualidad --source-id laverdad --source-id mediosdigitalesdelpacifico --source-id lajornadamaya_campeche --source-id lajornadamaya_quintana_roo --source-id lajornadamaya_yucatan --chunksize 50000 --require-date --min-text-chars 500
```

Do not export `diariopresente_tabasco_elsoldelsureste`, `meganoticias`,
`elbravo`, `lajornadaestadodemexico`, `noroeste`, `ejecentral`, or
`eldiariodesonora` as analysis-ready text yet without source-specific repairs.

Proceed next with the large not-yet-attempted sitemap sources, but keep
`tiempo` separate. It has 465,393 sitemap URLs, no sitemap `lastmod`, and was
reported as not working well in earlier tests. Do not mix it into a long batch
with other sources until a smaller pilot confirms article text and dates are
usable.

Run `cuartopoder` and `elporvenir` first:

```powershell
python .\code\01-crawlers\scripts\extract_sitemap_articles.py --source-id cuartopoder --source-id elporvenir --resume --timeout 90 --pause-seconds 0.05 --checkpoint-every 1000 --progress-every 1000 --progress-seconds 300 --workers 4 --no-final-output
```

Only pilot `tiempo` separately:

```powershell
python .\code\01-crawlers\scripts\extract_sitemap_articles.py --source-id tiempo --limit 1000 --resume --timeout 90 --pause-seconds 0.05 --checkpoint-every 250 --progress-every 100 --progress-seconds 120 --workers 2 --no-final-output
```

Tiempo-specific repair added:

- `tiempo` URLs are accepted when they have at least two path segments and start
  with one of the known article sections, including `/noticia/`, `/local/`,
  `/nacional/`, `/opinion/`, `/cronos/`, `/economia/`, `/espectaculos/`,
  `/deportes/`, `/cultura/`, `/internacional/`, `/tecnologia/`, or `/crealo/`.
- Dates are parsed from bylines such as
  `Por: Redacción 11 Agosto 2026 07:15` and
  `Por: María Fernanda Ibarvo Romo 15 Junio 2026 12:47`.
- Generic Spanish date parsing now also handles `15 Junio 2026`, without
  requiring `15 de Junio de 2026`.
- When Tiempo selectors are unreliable, the parser extracts body text from the
  visible text after the byline line and stops at common footer/share markers.

Use this smaller Tiempo pilot after the repair:

```powershell
python .\code\01-crawlers\scripts\extract_sitemap_articles.py --source-id tiempo --limit 1000 --resume --refresh-missing-date --refresh-missing-text --retry-errors --timeout 90 --pause-seconds 0.05 --checkpoint-every 100 --progress-every 100 --progress-seconds 120 --workers 2 --no-final-output
```

Source-specific sitemap repair work added after the 2026-09-05 check:

- JSON-LD is now extracted before `<script>` tags are removed, so
  `datePublished`, `author`, and JSON-LD `articleBody` are available to the
  parser.
- `articleBody` from JSON-LD is now used as a high-priority body-text source.
- Missing dates are now row-level errors (`missing_date`) instead of silent
  successes.
- Date extraction now handles visible patterns such as `Fecha: 11-08-2026`,
  `08/06/2026 - 01:30 p.m.`, dated URL paths such as `/2025/08/01/`, and
  Spanish title dates such as `BRAVO 10 de Agosto del 2026`.
- `diariopresente_tabasco_elsoldelsureste` now tries the `/amp/...` page when
  the normal page has text but no date.
- `elbravo` menu-only text is marked as `missing_main_text`.
- Source-aware URL filters now exclude list pages from `lajornadamaya_*`,
  `lajornadaestadodemexico`, and `noroeste`.
- The extraction CLI now supports `--refresh-missing-date`,
  `--refresh-missing-text`, and `--refresh-all-existing`.

Repair queue estimates from the current SQLite:

- `diariopresente_tabasco_elsoldelsureste`: 8,093 successful rows missing dates
- `meganoticias`: 639 successful rows missing dates, 181 errors
- `elbravo`: 88 successful rows missing dates/menu-like text
- `lajornadaestadodemexico`: source-aware filter keeps 9 article-like URLs
- `noroeste`: source-aware filter keeps 0 current sitemap URLs
- `eldiariodesonora`: 4,654 errors to retry, likely helped by JSON-LD body
  extraction

Run the repair batch with:

```powershell
python .\code\01-crawlers\scripts\extract_sitemap_articles.py --source-id diariopresente_tabasco_elsoldelsureste --source-id meganoticias --source-id elbravo --source-id lajornadaestadodemexico --source-id eldiariodesonora --resume --refresh-missing-date --refresh-missing-text --retry-errors --timeout 120 --pause-seconds 0.05 --checkpoint-every 100 --progress-every 100 --progress-seconds 120 --workers 3 --no-final-output
```

After the repair run, inspect before export. For any repaired sources that pass
the strict quality gate, export with:

```powershell
python .\code\01-crawlers\scripts\export_sitemap_articles_by_source.py --source-id diariopresente_tabasco_elsoldelsureste --source-id meganoticias --source-id elbravo --source-id lajornadaestadodemexico --source-id eldiariodesonora --chunksize 50000 --require-date --min-text-chars 500
```

Repair run result checked after execution:

- SQLite rows: 341,742
- `diariopresente_tabasco_elsoldelsureste`: repaired well; 8,108 ok rows and
  8,086 strict rows with text >= 500 chars and a date. Only 2
  `missing_main_text` rows remain.
- `meganoticias`: repaired well; 820 ok/strict rows, 0 errors.
- `lajornadaestadodemexico`: source-aware filter reduces it to a tiny usable
  set; only 8 strict rows. Treat as marginal.
- `elbravo`: all 88 rows are now marked `missing_main_text`; previous output
  was menu/navigation text, not article body.
- `noroeste`: all 9 rows are listing/opinion index pages with very short text;
  source-aware filter keeps 0 current sitemap URLs.
- `eldiariodesonora`: dates are now mostly recovered, but body text still fails;
  4,651 `missing_main_text` rows remain. Needs another extractor strategy.

The sitemap exporter now supports `--replace-existing` to clear old
`articles_part_*.parquet.gzip` files for selected sources before writing new
parts. Use it when re-exporting a source whose quality gate changed.

Export repaired sources that are now analysis-ready:

```powershell
python .\code\01-crawlers\scripts\export_sitemap_articles_by_source.py --source-id diariopresente_tabasco_elsoldelsureste --source-id meganoticias --source-id lajornadaestadodemexico --chunksize 50000 --require-date --min-text-chars 500 --replace-existing
```

Leave `elbravo`, `noroeste`, and `eldiariodesonora` out of analysis-ready
exports for now.

Use `--resume` to skip rows already present in `sitemap_articles.sqlite`. Use
`--retry-errors` only when you intentionally want to reattempt previously failed
URLs. Keep `--no-final-output` for long runs so the extractor only appends to
SQLite; use the export script afterward to produce per-source parquet.gzip part
files without loading the entire run into memory.

2026-09-06 Cuarto Poder interrupted long-run check:

- The interrupted progress with roughly 319k queued rows was the
  `cuartopoder` + `elporvenir` batch, not the Tiempo pilot.
- Current SQLite snapshot: 514,283 sitemap article rows total.
- `cuartopoder`: 173,293 rows saved; 107,152 ok, 66,141 errors, and 91,446
  strict rows with text >= 500 chars and a date.
- Cuarto Poder error mix: 63,511 `missing_date`, 2,490 `missing_main_text`,
  plus small network/DNS/404 failures.
- The `missing_main_text` rows are almost entirely media pages:
  `/videos/` (2,295) and `/fotogalerias/` (195).
- Cuarto Poder repair added:
  - Parses publication dates from bylines like
    `Por: Jesús Ortega/Cp Septiembre 05 del 2026`.
  - Parses older standalone date lines like `Enero 03 del 2007`.
  - Extracts article text from the visible text after the Cuarto Poder
    byline/date row, skips `Foto:` credit rows, and stops before comments,
    print-edition, or media/footer blocks.
  - Excludes Cuarto Poder `/videos/` and `/fotogalerias/` URLs from future
    queue/export filters.

Recommended next Cuarto Poder repair pilot:

```powershell
python .\code\01-crawlers\scripts\extract_sitemap_articles.py --source-id cuartopoder --limit 2000 --resume --refresh-missing-date --refresh-missing-text --retry-errors --timeout 120 --pause-seconds 0.05 --checkpoint-every 100 --progress-every 100 --progress-seconds 120 --workers 2 --no-final-output
```

If that pilot has low errors, continue Cuarto Poder repair at scale:

```powershell
python .\code\01-crawlers\scripts\extract_sitemap_articles.py --source-id cuartopoder --resume --refresh-missing-date --refresh-missing-text --retry-errors --timeout 120 --pause-seconds 0.05 --checkpoint-every 1000 --progress-every 1000 --progress-seconds 300 --workers 4 --no-final-output
```

Only after the repair looks good, export Cuarto Poder with:

```powershell
python .\code\01-crawlers\scripts\export_sitemap_articles_by_source.py --source-id cuartopoder --chunksize 50000 --require-date --min-text-chars 500 --replace-existing
```

2026-09-07 Cuarto Poder repair pilot result:

- Updated SQLite snapshot: 526,566 sitemap article rows total.
- `cuartopoder`: 185,576 rows saved; 182,986 ok, 2,590 errors, and 165,599
  strict rows with text >= 500 chars and a date.
- The repair worked: Cuarto Poder `missing_date` fell from 63,511 to 6.
- Remaining Cuarto Poder `missing_main_text` rows: 2,491. These are effectively
  media rows (`/videos/` and `/fotogalerias/`) and are excluded by the current
  source-specific queue/export filter.
- There are 22 already-saved Cuarto Poder ok rows with future-looking years
  after 2026. These likely came from the older broad Spanish-date parser, so the
  extractor now supports `--refresh-date-after YYYY-MM-DD` for small targeted
  date cleanup.

Run this small Cuarto Poder cleanup before final export:

```powershell
python .\code\01-crawlers\scripts\extract_sitemap_articles.py --source-id cuartopoder --resume --retry-errors --refresh-missing-date --refresh-date-after 2026-09-07 --timeout 120 --pause-seconds 0.05 --checkpoint-every 100 --progress-every 100 --progress-seconds 120 --workers 3 --no-final-output
```

Then export Cuarto Poder:

```powershell
python .\code\01-crawlers\scripts\export_sitemap_articles_by_source.py --source-id cuartopoder --chunksize 50000 --require-date --min-text-chars 500 --replace-existing
```

Next untouched sitemap sources:

- `elporvenir`: 134,522 likely article URLs, 0 rows in SQLite.
- `tiempo`: 465,393 likely article URLs, 0 rows in SQLite. Keep separate until
  the Tiempo-specific parser has passed a real pilot.

2026-09-07 post-El Porvenir run overview:

- Sitemap SQLite snapshot: 661,088 rows total.
- Sitemap per-source parquet exports currently total 479,369 strict rows across
  13 exported source folders.
- `cuartopoder`: exported; 185,576 SQLite rows, 183,078 ok, 2,498 errors, and
  165,691 strict/exported rows. Max date is now `2026-09-05`, so the future-date
  cleanup worked.
- `elporvenir`: extraction completed and looks good; 134,522 SQLite rows,
  134,210 ok, 312 errors, and 132,370 strict rows. Random samples had coherent
  article text and dates. Export still needs to be run.
- `tiempo`: 465,393 likely article URLs, still 0 SQLite rows. This is the next
  major untouched sitemap source and should start with a pilot.
- Known sitemap sources needing different repair/extractor work: `ejecentral`
  and `eldiariodesonora`. `elbravo`, `noroeste`, and
  `lajornadaestadodemexico` remain marginal/low-value from current sitemap URLs.
- WordPress article SQLite snapshot: 1,246,059 rows. WordPress per-source
  folders exist for 31 sources.

Next commands:

```powershell
python .\code\01-crawlers\scripts\export_sitemap_articles_by_source.py --source-id elporvenir --chunksize 50000 --require-date --min-text-chars 500 --replace-existing
```

Then pilot Tiempo:

```powershell
python .\code\01-crawlers\scripts\extract_sitemap_articles.py --source-id tiempo --limit 2000 --resume --timeout 120 --pause-seconds 0.05 --checkpoint-every 100 --progress-every 100 --progress-seconds 120 --workers 3 --no-final-output
```

If the Tiempo pilot is clean, run a larger day-scale Tiempo batch:

```powershell
python .\code\01-crawlers\scripts\extract_sitemap_articles.py --source-id tiempo --resume --timeout 120 --pause-seconds 0.05 --checkpoint-every 1000 --progress-every 1000 --progress-seconds 300 --workers 4 --no-final-output
```

2026-09-07 Tiempo pilot check:

- `elporvenir` export exists and is complete: 132,370 strict rows in 4
  `articles_part_*.parquet.gzip` files.
- Tiempo pilot saved 2,000 rows: 1,569 ok, 431 errors, and 1,560 strict rows.
- The Tiempo errors were all `missing_date`, but sampled rows showed they were
  actually site error/poll pages: title `Ocurrió un error al procesar la
  noticia`, body text beginning with `Por:` followed by a poll. These should be
  discarded as bad text, not treated as date parser misses.
- Tiempo extraction repair added:
  - Detects the Tiempo error/poll shell as low-quality text, so it is marked
    `missing_main_text`.
  - Decodes HTML-escaped JSON-LD article bodies before saving text.
  - Gives the byline-anchored Tiempo body extractor priority over JSON-LD when
    available, reducing duplicated byline/body text.

Re-run the same Tiempo pilot once after this repair:

```powershell
python .\code\01-crawlers\scripts\extract_sitemap_articles.py --source-id tiempo --limit 2000 --resume --refresh-all-existing --timeout 120 --pause-seconds 0.05 --checkpoint-every 100 --progress-every 100 --progress-seconds 120 --workers 3 --no-final-output
```

If the refreshed pilot remains around 1,500+ strict rows and errors are mostly
`missing_main_text` for site error pages, continue with:

```powershell
python .\code\01-crawlers\scripts\extract_sitemap_articles.py --source-id tiempo --resume --timeout 120 --pause-seconds 0.05 --checkpoint-every 1000 --progress-every 1000 --progress-seconds 300 --workers 4 --no-final-output
```

2026-09-09 Tiempo full run check:

- Sitemap SQLite snapshot: 1,126,481 rows total. This is essentially the full
  sitemap discovery set after source-aware filters and prior retries.
- `tiempo`: 465,393 rows saved; 361,828 ok, 103,565 errors, and 359,662 strict
  rows with text >= 500 chars and a date.
- Tiempo strict rows cover 2018-2024:
  - 2018: 22,069
  - 2019: 54,332
  - 2020: 73,785
  - 2021: 64,703
  - 2022: 60,737
  - 2023: 58,459
  - 2024: 25,577
- Tiempo errors: 67,818 `missing_date`, 35,743 `missing_main_text`, 3
  `http_status_500`, and 1 timeout. Samples show the `missing_date` rows are
  also Tiempo's site-error/poll shell (`Ocurrió un error al procesar la
  noticia`), so export with `--require-date --min-text-chars 500` is safe.
- The Tiempo low-quality detector was broadened after this run to catch more of
  these poll shells in future diagnostics. No need to rerun Tiempo before export
  unless clean error labels are important.

Export Tiempo next:

```powershell
python .\code\01-crawlers\scripts\export_sitemap_articles_by_source.py --source-id tiempo --chunksize 50000 --require-date --min-text-chars 500 --replace-existing
```

After Tiempo export, there are no more large generic sitemap runs to do. The
remaining sitemap work is targeted repair/fallback extraction:

- `ejecentral`: 8,535 rows, only 794 ok; 7,738 are `http_status_403`, so this
  needs a different fetch method such as browser/Playwright or a better HTTP
  profile.
- `eldiariodesonora`: 4,654 rows, 0 strict; 4,651 are `missing_main_text`, so
  this needs a source-specific extractor or rendered-page fallback.
- `elbravo`, `noroeste`, and `lajornadaestadodemexico` are low-value/marginal
  with the current sitemap URLs.

2026-09-09 Tiempo export verified and EjeCentral HTTP-profile pilot added:

- Tiempo export completed: 359,662 rows in 10 `articles_part_*.parquet.gzip`
  files, about 217.8 MB compressed.
- Total sitemap per-source parquet exports now cover 15 source folders and
  971,401 strict rows.
- Added `--fetch-profile browser` to `extract_sitemap_articles.py`. It keeps
  the default research-bot curl profile unchanged, but allows a browser-like
  user agent and headers for sources that reject the default profile.
- This is intended as the first lightweight repair attempt for `ejecentral`,
  whose failures are almost entirely `http_status_403`.

Next EjeCentral pilot:

```powershell
python .\code\01-crawlers\scripts\extract_sitemap_articles.py --source-id ejecentral --limit 500 --resume --retry-errors --fetch-profile browser --timeout 120 --pause-seconds 0.1 --checkpoint-every 50 --progress-every 50 --progress-seconds 120 --workers 2 --no-final-output
```

If the 403s disappear and text/date quality looks normal, continue with:

```powershell
python .\code\01-crawlers\scripts\extract_sitemap_articles.py --source-id ejecentral --resume --retry-errors --fetch-profile browser --timeout 120 --pause-seconds 0.1 --checkpoint-every 250 --progress-every 250 --progress-seconds 180 --workers 3 --no-final-output
```

If `ejecentral` still returns mostly 403s under `--fetch-profile browser`, stop
and build a true rendered/browser fallback rather than repeating the same run.

2026-09-09/10 EjeCentral browser-profile run check:

- The `--fetch-profile browser` pilot initially worked, but the longer retry
  started returning 403s after the first few hundred rows.
- Current `ejecentral` SQLite state: 8,535 rows total; 2,004 ok/strict rows,
  6,531 errors.
- Error mix: 6,529 `http_status_403`, 1 `curl_exit_3221225477`, and 1 curl
  connection reset.
- Successful samples have coherent titles, dates, and article text.
- 403 samples still carry dates from sitemap metadata but no HTML title/body.
- Interpretation: EjeCentral is probably rate-limiting or selectively blocking
  after too many curl requests, even with browser-like headers.

Do not repeat the fast EjeCentral run. If trying HTTP again, wait for cooldown
and run a slow single-worker retry:

```powershell
python .\code\01-crawlers\scripts\extract_sitemap_articles.py --source-id ejecentral --resume --retry-errors --fetch-profile browser --timeout 120 --pause-seconds 2 --checkpoint-every 50 --progress-every 50 --progress-seconds 180 --workers 1 --no-final-output
```

If that still returns mostly 403s after the first 100-200 rows, stop and build
a rendered/browser fallback. Current 2,004 strict EjeCentral rows can be exported
at any time with:

```powershell
python .\code\01-crawlers\scripts\export_sitemap_articles_by_source.py --source-id ejecentral --chunksize 50000 --require-date --min-text-chars 500 --replace-existing
```

2026-09-10 EjeCentral completed:

- `ejecentral` is now essentially recovered.
- SQLite state: 8,535 rows total; 8,506 ok; 29 errors; 8,498 strict rows.
- Remaining errors are small/network-like: 17 curl connection resets, 6 404s,
  3 `missing_main_text`, and 3 DNS failures.
- Export exists: 8,498 rows in the `ejecentral` sitemap export folder.
- Total sitemap per-source parquet exports now cover 979,899 strict rows.
- Next real repair target: `eldiariodesonora`, with 4,654 rows and 0 strict
  rows because body text is not being extracted by the current HTML selectors.

2026-09-10 El Diario de Sonora repair added:

- Live page inspection showed the useful body text starts after an author/date
  line such as `Autor El Diario de Sonora el 12/11/2025 03:47 PM.` and the
  following edit line, then stops before `Comparte esta noticia` / `Más
  Noticias`.
- `text_from_visible_byline` now supports `eldiariodesonora` using this visible
  text anchor.
- Synthetic test passed: date `2025-11-12`, title, and body text were extracted
  while related-news/footer blocks were excluded.

Run this El Diario de Sonora pilot:

```powershell
python .\code\01-crawlers\scripts\extract_sitemap_articles.py --source-id eldiariodesonora --limit 500 --resume --retry-errors --refresh-missing-text --timeout 120 --pause-seconds 0.05 --checkpoint-every 50 --progress-every 50 --progress-seconds 120 --workers 3 --no-final-output
```

If the pilot is clean, continue with:

```powershell
python .\code\01-crawlers\scripts\extract_sitemap_articles.py --source-id eldiariodesonora --resume --retry-errors --refresh-missing-text --timeout 120 --pause-seconds 0.05 --checkpoint-every 250 --progress-every 250 --progress-seconds 180 --workers 4 --no-final-output
```

Then export:

```powershell
python .\code\01-crawlers\scripts\export_sitemap_articles_by_source.py --source-id eldiariodesonora --chunksize 50000 --require-date --min-text-chars 500 --replace-existing
```

2026-09-10 El Diario de Sonora first retry failed:

- User reported the full retry was still producing 100% `missing_main_text`.
- The issue is likely that the live fetched DOM splits the byline across lines:
  `Autor` / `El Diario de Sonora` / `el 12/11/2025 03:47 PM.` instead of the
  one-line pattern seen in the browser text snapshot.
- The extractor now also detects a split publication-date line near `Autor` or
  `El Diario de Sonora`, skips category/edit metadata lines, and starts body
  extraction after that.
- Synthetic tests now pass for both one-line and split-line byline layouts.

Re-run a small El Diario de Sonora pilot, not the full source:

```powershell
python .\code\01-crawlers\scripts\extract_sitemap_articles.py --source-id eldiariodesonora --limit 200 --resume --retry-errors --refresh-missing-text --timeout 120 --pause-seconds 0.05 --checkpoint-every 25 --progress-every 25 --progress-seconds 120 --workers 2 --no-final-output
```

2026-09-10 pause El Diario de Sonora and start RSS lane:

- User asked to skip `eldiariodesonora` for now after another 100%
  `missing_main_text` pilot. Leave it parked until we add raw-HTML capture or a
  browser-rendered fallback.
- Added RSS/Atom discovery and extraction scripts:
  - `scripts/discover_rss_urls.py`
  - `scripts/extract_rss_articles.py`
  - `scripts/export_rss_articles_by_source.py`
  - core parser: `crawler_core/rss.py`
- RSS outputs are separated from sitemap/WordPress:
  - discovery: `crawler/discovery/discovered_urls_rss.*`
  - SQLite: `crawler/articles_rss/rss_articles.sqlite`
  - exports: `crawler/articles_rss/<source_id>/articles_part_*.parquet.gzip`
- RSS extraction reuses the hardened HTML article parser and defaults to the
  browser-like HTTP profile.
- OEM feed URLs are corrected internally from each source canonical URL, e.g.
  `https://oem.com.mx/eloccidental/rss`, instead of reusing the repeated
  registry probe URL `https://oem.com.mx/elsoldemexico/rss`.
- RSS is usually recent-feed coverage, not a full archive replacement. Treat it
  as a way to add otherwise-uncovered sources quickly.

RSS-first sources from the registry:

`esto`, `oem_sinaloa_elsoldemazatlan`,
`oem_baja_california_sur_elsudcaliforniano`, `oem_nacional_la_prensa`,
`ovaciones`, `elfinanciero`, `oem_guanajuato_elsoldelbajio`,
`oem_chihuahua_elheraldodechihuahua`, `oem_guadalajara_eloccidental`,
`oem_ciudad_de_mexico_elsoldemexico`, `oem_morelos_elsoldecuautla`,
`oem_hidalgo_elsoldehidalgo`, `oem_puebla_elsoldepuebla`,
`oem_queretaro_diariodequeretaro`, `oem_tamaulipas_elsoldetampico`,
`oem_tlaxcala_elsoldetlaxcala`, `oem_zacatecas_elsoldezacatecas`,
`oem_elsoldeacapulco`.

Run RSS discovery:

```powershell
python .\code\01-crawlers\scripts\discover_rss_urls.py --timeout 45 --pause-seconds 0.2
```

Then run RSS article extraction:

```powershell
python .\code\01-crawlers\scripts\extract_rss_articles.py --resume --timeout 120 --pause-seconds 0.1 --checkpoint-every 50 --progress-every 50 --progress-seconds 120 --workers 3 --no-final-output
```

Then export RSS articles:

```powershell
python .\code\01-crawlers\scripts\export_rss_articles_by_source.py --chunksize 50000 --require-date --min-text-chars 500
```

After RSS, the next non-parked workstream should be category-pagination adapters
for sources such as `informador`, `criteriohidalgo`, `eldiariodechihuahua`,
`diario`, `mvsnoticias`, `publimetro`, `infobae`, and `mexicoalminuto`.

2026-09-10 category/archive discovery lane added:

- RSS discovery only returned 1,750 recent-feed URLs, so it is not a serious
  historical archive path.
- Added generic category/listing-page discovery:
  - `crawler_core/category_pagination.py`
  - `scripts/discover_category_urls.py`
  - `scripts/extract_category_articles.py`
  - `scripts/export_category_articles_by_source.py`
- Outputs are isolated from sitemap/WordPress/RSS:
  - discovery: `crawler/discovery/discovered_urls_category.*`
  - SQLite: `crawler/articles_category/category_articles.sqlite`
  - exports: `crawler/articles_category/<source_id>/articles_part_*.parquet.gzip`
- The article extraction/export side reuses the hardened sitemap HTML extractor,
  so source-specific text/date repairs continue to apply.
- Registry currently has 11 `category_pagination` sources:
  `eldiariodedelicias`, `eldiariodechihuahua`, `diario`, `criteriohidalgo`,
  `informador`, `eleconomista`, `eluniversal`, `mvsnoticias`, `publimetro`,
  `infobae`, and `mexicoalminuto`.
- Local compile passed for the crawler package and scripts.
- Small local wrapper test was successful, but a live `informador` probe from
  Codex hit a Windows `curl.exe` Schannel credentials error before fetching
  HTML. User terminal may still work normally; if not, switch that source to a
  different fetch method/browser fallback.

First category discovery pilot:

```powershell
python .\code\01-crawlers\scripts\discover_category_urls.py --source-id eldiariodedelicias --source-id eldiariodechihuahua --source-id diario --source-id mvsnoticias --source-id publimetro --source-id mexicoalminuto --max-categories-per-source 6 --max-pages-per-category 10 --max-urls-per-source 5000 --timeout 45 --pause-seconds 0.2 --fetch-profile browser
```

If that produces useful rows, run a small extraction check:

```powershell
python .\code\01-crawlers\scripts\extract_category_articles.py --source-id eldiariodedelicias --source-id eldiariodechihuahua --source-id diario --source-id mvsnoticias --source-id publimetro --source-id mexicoalminuto --limit 2000 --resume --timeout 120 --pause-seconds 0.1 --checkpoint-every 100 --progress-every 100 --progress-seconds 120 --workers 3 --no-final-output
```

Export the pilot:

```powershell
python .\code\01-crawlers\scripts\export_category_articles_by_source.py --source-id eldiariodedelicias --source-id eldiariodechihuahua --source-id diario --source-id mvsnoticias --source-id publimetro --source-id mexicoalminuto --chunksize 50000 --require-date --min-text-chars 500 --replace-existing
```

2026-09-10 category lane should now run one source at a time:

- User wants one-by-one category/archive discovery rather than mixed batches.
- `discover_category_urls.py` now supports `--append-existing`; when a
  `--source-id` is supplied, old discovery rows for that source are replaced,
  while discoveries for other sources are preserved.
- `category_pagination.py` now expands discovered section/listing links and
  avoids treating article URLs as pagination links.
- The first six-source pilot was intentionally limited and returned only 806
  URLs. Treat it as a smoke test, not as the full category crawl.

Recommended first one-source category target:

```powershell
python .\code\01-crawlers\scripts\discover_category_urls.py --source-id eldiariodedelicias --append-existing --max-categories-per-source 30 --max-pages-per-category 500 --max-urls-per-source 50000 --timeout 45 --pause-seconds 0.15 --fetch-profile browser
```

Then extract only that source:

```powershell
python .\code\01-crawlers\scripts\extract_category_articles.py --source-id eldiariodedelicias --resume --timeout 120 --pause-seconds 0.08 --checkpoint-every 1000 --progress-every 500 --progress-seconds 180 --workers 3 --no-final-output
```

Then export only that source:

```powershell
python .\code\01-crawlers\scripts\export_category_articles_by_source.py --source-id eldiariodedelicias --chunksize 50000 --require-date --min-text-chars 500 --replace-existing
```

After that, repeat the same three commands by replacing `eldiariodedelicias`
with `eldiariodechihuahua`, then `diario`, then `mvsnoticias`, then
`publimetro`, then `mexicoalminuto`.

2026-09-10 category pilot was still too shallow:

- User correctly noted that ~900 URLs is not enough.
- Latest category discovery file had 903 rows / 900 URLs total:
  `mvsnoticias` 255, `eldiariodedelicias` 254, `diario` 155,
  `eldiariodechihuahua` 148, `publimetro` 57, `mexicoalminuto` 31.
- The old run only reached one or two pages for most `eldiariodedelicias`
  sections and had false positives where top-level section URLs like `/local/`
  were counted as articles.
- `category_pagination.py` was tightened again:
  - top-level section URLs are not articles;
  - pagination URLs are not articles;
  - stop reasons are printed for each category;
  - compile and parser smoke tests passed.
- Next action: rerun one source only, deep, and inspect the stop messages.

Deep one-source discovery to run next:

```powershell
python .\code\01-crawlers\scripts\discover_category_urls.py --source-id eldiariodedelicias --append-existing --max-categories-per-source 30 --max-pages-per-category 500 --max-urls-per-source 50000 --timeout 45 --pause-seconds 0.15 --fetch-profile browser
```

If this still returns only a few hundred URLs and the stop messages say
`no next listing page found`, then this site needs a source-specific archive
strategy rather than generic category pagination.

2026-09-14 pivot away from category pagination:

- User concluded category pagination is not working in general. That is right:
  it is a shallow/recent listing strategy and should not be treated as a bulk
  historical archive method.
- Added a new Common Crawl URL discovery lane:
  - `crawler_core/commoncrawl.py`
  - `scripts/discover_commoncrawl_urls.py`
  - `scripts/extract_commoncrawl_articles.py`
  - `scripts/export_commoncrawl_articles_by_source.py`
- Outputs are isolated:
  - discovery: `crawler/discovery/discovered_urls_commoncrawl.*`
  - SQLite: `crawler/articles_commoncrawl/commoncrawl_articles.sqlite`
  - exports:
    `crawler/articles_commoncrawl/<source_id>/articles_part_*.parquet.gzip`
- Common Crawl discovery queries CDX indexes by source domain, keeps status 200
  HTML captures, collapses duplicate URL keys, filters likely article URLs, and
  stores CDX metadata (`commoncrawl_index`, `timestamp`, `digest`, WARC
  filename/offset, etc.) alongside the live URL.
- Extraction still fetches live URLs and reuses the existing hardened HTML
  extractor. If many old URLs are now dead, a later step can use the saved WARC
  metadata to extract from archived Common Crawl captures instead of live pages.
- Compile and parser smoke tests passed.

First Common Crawl pilot, one site / one index / small limit:

```powershell
python .\code\01-crawlers\scripts\discover_commoncrawl_urls.py --source-id diario --index-id CC-MAIN-2026-34 --limit-per-query 5000 --max-urls-per-source 5000 --timeout 120 --pause-seconds 1 --append-existing
```

If that finds thousands of URLs, expand one site across historical years:

```powershell
python .\code\01-crawlers\scripts\discover_commoncrawl_urls.py --source-id diario --year 2018 --year 2019 --year 2020 --year 2021 --year 2022 --year 2023 --year 2024 --year 2025 --year 2026 --limit-per-query 50000 --max-urls-per-source 250000 --timeout 180 --pause-seconds 1 --append-existing
```

Then extract a pilot:

```powershell
python .\code\01-crawlers\scripts\extract_commoncrawl_articles.py --source-id diario --limit 2000 --resume --timeout 120 --pause-seconds 0.08 --checkpoint-every 250 --progress-every 250 --progress-seconds 180 --workers 3 --no-final-output
```

Then export:

```powershell
python .\code\01-crawlers\scripts\export_commoncrawl_articles_by_source.py --source-id diario --chunksize 50000 --require-date --min-text-chars 500 --replace-existing
```

2026-09-14 Common Crawl first pilot returned zero:

- User ran the broad one-index `diario` pilot.
- Saved output showed:
  - `diario.mx/*`: `http_status_504`
  - `www.diario.mx/*`: `http_status_404`
  - no URLs.
- Interpretation: the whole-domain CDX query was too broad/heavy; this is not
  evidence that Common Crawl has no Diario URLs.
- Updated Common Crawl discovery to use path-first patterns by default and to
  support explicit `--path-pattern` filters. When `--path-pattern` is supplied,
  only those paths are queried.
- Compile passed.

Run this narrower Diario Common Crawl pilot next:

```powershell
python .\code\01-crawlers\scripts\discover_commoncrawl_urls.py --source-id diario --index-id CC-MAIN-2026-34 --path-pattern juarez --path-pattern nacional --path-pattern estado --path-pattern economia --path-pattern deportes --limit-per-query 5000 --max-urls-per-source 20000 --timeout 120 --pause-seconds 1 --append-existing
```

If that still has 504s, lower `--limit-per-query` to 1000. If it returns 404
for every narrowed path, try another site such as `eldiariodechihuahua` or
`mvsnoticias` with its obvious section paths.

2026-09-14 Common Crawl narrowed Diario run still failed:

- User reported the narrowed `diario` query was still returning one error row
  per path in `CC-MAIN-2026-34`.
- Updated `commoncrawl_query_url()` to use explicit `matchType=prefix` and a
  prefix URL such as `diario.mx/juarez/` instead of relying on the wildcard
  shortcut `diario.mx/juarez/*`.
- HTTP 404 from CDX now means no captures for that path/index and no longer
  becomes an error row. This keeps the report from looking like a scrape failure
  when a crawl simply lacks captures for a prefix.
- Compile passed.

Next rerun should stop the current command if it is still running, then use:

```powershell
python .\code\01-crawlers\scripts\discover_commoncrawl_urls.py --source-id diario --year 2024 --year 2025 --year 2026 --limit-indexes 8 --path-pattern juarez --limit-per-query 1000 --max-urls-per-source 10000 --timeout 120 --pause-seconds 1 --append-existing
```

If that works, add more paths (`nacional`, `estado`, `economia`, `deportes`).
If it still returns no URLs, move to `mvsnoticias` or `publimetro` before
investing more time in `diario`.

2026-09-14 Common Crawl abandoned for now; Wayback lane added:

- User reported everything tested through Common Crawl returned zeroes.
- Treat Common Crawl as parked. It may still be useful later via the columnar
  URL index or WARC metadata, but the CDX endpoint is not paying off quickly.
- Added an Internet Archive Wayback CDX lane:
  - `crawler_core/wayback.py`
  - `scripts/discover_wayback_urls.py`
  - `scripts/extract_wayback_articles.py`
  - `scripts/export_wayback_articles_by_source.py`
- Outputs are isolated:
  - discovery: `crawler/discovery/discovered_urls_wayback.*`
  - SQLite: `crawler/articles_wayback/wayback_articles.sqlite`
  - exports: `crawler/articles_wayback/<source_id>/articles_part_*.parquet.gzip`
- Discovery uses Wayback CDX fields
  `urlkey,timestamp,original,mimetype,statuscode,digest,length`, filters
  `statuscode:200` and `mimetype:text/html`, collapses by `urlkey`, and writes
  no-toolbar archived playback URLs of the form
  `https://web.archive.org/web/{timestamp}id_/{original_url}`.
- Article rows now preserve Wayback metadata in the shared extractor base row:
  `original_url`, `wayback_url`, `wayback_timestamp`, `wayback_mimetype`,
  `wayback_statuscode`, `wayback_digest`, and `wayback_length`.
- Compile and JSON parser smoke tests passed.

First Wayback pilot:

```powershell
python .\code\01-crawlers\scripts\discover_wayback_urls.py --source-id diario --from 20180101 --to 20261231 --path-pattern juarez --limit-per-page 1000 --max-pages-per-query 3 --max-urls-per-source 5000 --timeout 120 --pause-seconds 1 --append-existing
```

If it discovers URLs, extract a small pilot:

```powershell
python .\code\01-crawlers\scripts\extract_wayback_articles.py --source-id diario --limit 500 --resume --timeout 120 --pause-seconds 0.15 --checkpoint-every 50 --progress-every 50 --progress-seconds 120 --workers 2 --no-final-output
```

Then export:

```powershell
python .\code\01-crawlers\scripts\export_wayback_articles_by_source.py --source-id diario --chunksize 50000 --require-date --min-text-chars 500 --replace-existing
```

2026-09-14 Wayback also parked; Diario source-specific API added:

- User's month-window Wayback run still returned one error row per window.
- Local checks against Wayback CDX produced `503` / timeouts even for tiny
  exact/prefix queries, so Wayback is parked for now.
- Browser inspection of live Diario section page found a real load-more
  endpoint:
  - button: `button.btn-more`
  - endpoint: `https://diario.mx/com/snr/dmx/show-more-section.jsp`
  - data fields: `data-page`, `data-long`, `data-section`, `data-type`
  - observed example: page advanced from `2` to `3` after clicking, and the
    DOM gained more `diario.mx/juarez/...html` links.
- Added a new source-specific API lane:
  - `crawler_core/source_api.py`
  - `scripts/discover_source_api_urls.py`
  - `scripts/extract_source_api_articles.py`
  - `scripts/export_source_api_articles_by_source.py`
- Outputs are isolated:
  - discovery: `crawler/discovery/discovered_urls_source_api.*`
  - SQLite: `crawler/articles_source_api/source_api_articles.sqlite`
  - exports:
    `crawler/articles_source_api/<source_id>/articles_part_*.parquet.gzip`
- Current adapter supports `source_id == diario` and paginates Diario sections
  by calling:
  `show-more-section.jsp?page=N&section=<section>&long=15&type=1`.
- After the first user pilot, Diario returned only 50 URLs for `juarez`: page 2
  added new links, but pages 3 and 4 repeated page 2. This likely happened
  because the endpoint was being fetched like a normal page navigation.
- Updated `crawler_core/capabilities.py` with an `ajax` fetch profile, optional
  referer, and optional extra headers.
- Updated the Diario adapter so the load-more endpoint uses an AJAX-style
  request with `Referer: https://diario.mx/seccion/<section>/` and
  `X-Requested-With: XMLHttpRequest`.
- Also added a second Diario section archive pass through live listing URLs of
  the form `https://diario.mx/seccion/<section>/?ch=N`. Public indexed copies of
  these pages show older section listings, so this may be the better bulk route
  if the load-more endpoint remains shallow.
- Compile smoke test passed after these changes.

Stop any Wayback run and try this Diario source-API pilot:

```powershell
python .\code\01-crawlers\scripts\discover_source_api_urls.py --source-id diario --section juarez --max-pages-per-section 20 --max-urls-per-source 1000 --timeout 60 --pause-seconds 0.2 --fetch-profile browser --append-existing
```

If the endpoint is correct, expand Juarez:

```powershell
python .\code\01-crawlers\scripts\discover_source_api_urls.py --source-id diario --section juarez --max-pages-per-section 1000 --max-urls-per-source 50000 --timeout 60 --pause-seconds 0.2 --fetch-profile browser --append-existing
```

Then extract:

```powershell
python .\code\01-crawlers\scripts\extract_source_api_articles.py --source-id diario --limit 1000 --resume --timeout 120 --pause-seconds 0.08 --checkpoint-every 100 --progress-every 100 --progress-seconds 120 --workers 3 --no-final-output
```

Then export:

```powershell
python .\code\01-crawlers\scripts\export_source_api_articles_by_source.py --source-id diario --chunksize 50000 --require-date --min-text-chars 500 --replace-existing
```

## MVS Noticias Discovery Start

2026-09-14 MVS Noticias (`source_id == mvsnoticias`) started.

- The public section pagination is shallow. For example:
  - `https://mvsnoticias.com/nacional/pagina/10` returns `200`.
  - `https://mvsnoticias.com/nacional/pagina/11` returns `404`.
- Historical article pages do exist, including 2019/2020 article URLs, so the
  impediment is discovery coverage rather than missing article pages.
- MVS is a Next.js site. Rendered page HTML includes article links, and article
  pages include high-quality JSON-LD with `headline`, `description`,
  `datePublished`, `dateModified`, `author`, `articleSection`, `keywords`, and
  `articleBody`.
- The best discovered historical path is graph expansion:
  1. section pages;
  2. article pages;
  3. topic links from article pages;
  4. paginated topic archives.
- The MVS search page also supports server-rendered date-filtered queries like
  `/buscar?q=amlo&desde=2019-01-01&hasta=2019-12-31&page=1`; search appears
  useful as a supplement, but it is term-based and not a complete archive by
  itself.
- Local non-elevated `curl.exe` fails against MVS with Schannel
  `SEC_E_NO_CREDENTIALS`. Elevated `curl.exe` can fetch MVS pages, but elevated
  Python cannot read the local virtualenv package files correctly. Hidden
  browser navigation through Codex CUA was the reliable local route.
- Added reusable MVS discovery files:
  - `crawler_core/mvs.py`
  - `scripts/discover_mvs_urls.py`
- `discover_mvs_urls.py` now supports `--workers` for parallel article-page
  probing. MVS fetches go directly through `requests` with the MVS-specific TLS
  fallback instead of trying failing Windows `curl.exe` first.
- `py_compile` passed for both files.
- A hidden-browser discovery pilot wrote:
  - `tmp/mvsnoticias_browser_discovery/discovered_urls_mvsnoticias.csv`
  - `tmp/mvsnoticias_browser_discovery/discovered_urls_mvsnoticias.parquet`
  - `tmp/mvsnoticias_browser_discovery/mvsnoticias_discovery_report.md`
- Discovery pilot result:
  - 2,010 unique article URLs.
  - date range from URL paths: `2018-04-04` through `2026-09-14`.
  - 59 listing pages visited.
  - 120 article pages probed for topic links.
  - 10 topic archives processed.
  - 252 topic archives remained queued when the pilot hit the URL cap.
  - by strategy: 545 section URLs, 688 related-article URLs, 777 topic URLs.
- A hidden-browser extraction pilot wrote:
  - `tmp/mvsnoticias_browser_discovery/articles_pilot/mvsnoticias_articles_pilot_150.csv`
  - `tmp/mvsnoticias_browser_discovery/articles_pilot/mvsnoticias_articles_pilot_150.parquet`
  - `tmp/mvsnoticias_browser_discovery/articles_pilot/mvsnoticias_articles_pilot_150_report.md`
- Extraction pilot result:
  - 150/150 article pages loaded successfully.
  - 148/150 rows had `main_text` length >= 500.
  - median article body length was 2,063 characters.

Next MVS action:

1. Run a larger hidden-browser discovery pass, raising the URL cap and topic cap.
2. Persist the queued topic frontier between browser runs so discovery can resume
   beyond the pilot.
3. Once discovery coverage stabilizes, extract MVS articles in browser-driven
   batches and export to the same per-source parquet layout used by the category
   lane.

Faster MVS discovery command:

```powershell
python .\code\01-crawlers\scripts\discover_mvs_urls.py --max-section-pages 10 --max-topic-pages 1000 --max-article-pages-to-probe 5000 --max-topics 20000 --max-urls 200000 --timeout 60 --pause-seconds 0.05 --fetch-profile browser --workers 8
```

## Google Programmable Search Discovery Layer

2026-09-14 added an official Google Custom Search JSON API discovery lane for
date-in-URL newspaper articles.

- New files:
  - `crawler_core/google_search.py`
  - `scripts/discover_google_urls.py`
- `.env.example` now documents:
  - `GOOGLE_CUSTOM_SEARCH_API_KEY`
  - `GOOGLE_CUSTOM_SEARCH_CX`
- The script builds daily queries of the form:
  - `site:mvsnoticias.com inurl:/2026/9/11/`
  - `site:mvsnoticias.com after:2026-09-10 before:2026-09-12`
  - optional section shards like
    `site:mvsnoticias.com/nacional inurl:/2026/9/11/`
  - optional topic shards by appending repeated `--topic-term` values to each
    daily query.
- It writes:
  - `crawler/discovery/discovered_urls_google.csv`
  - `crawler/discovery/discovered_urls_google.parquet`
  - `crawler/reports/google_discovery_report.md`
- It supports `--append-existing`; when `--source-id` is used, previous rows for
  those sources are replaced before deduping by `source_id,url`.
- MVS daily cap check from visible section pagination found 1,750 unique URLs
  across 137 days, with a maximum of 97 URLs on one day. So day-level Google
  sharding is plausible, but section sharding is needed near the 100-result API
  cap.

Suggested MVS pilot:

```powershell
python .\code\01-crawlers\scripts\discover_google_urls.py --source-id mvsnoticias --from 2026-09-01 --to 2026-09-14 --query-mode date-inurl --query-mode date-range --section-path nacional --section-path mundo --section-path economia --section-path entretenimiento --section-path deportes --section-path entrevistas --section-path nuevo-leon --topic-term AMLO --topic-term Sheinbaum --saturation-threshold 80 --max-results-per-query 100 --timeout 60 --pause-seconds 1 --append-existing
```

Suggested MVS full run:

```powershell
python .\code\01-crawlers\scripts\discover_google_urls.py --source-id mvsnoticias --from 2018-01-01 --to 2026-09-14 --query-mode date-inurl --query-mode date-range --section-path nacional --section-path mundo --section-path economia --section-path entretenimiento --section-path deportes --section-path entrevistas --section-path nuevo-leon --saturation-threshold 80 --max-results-per-query 100 --max-urls-per-source 200000 --timeout 60 --pause-seconds 1 --append-existing
```

# Tiempo: complete advertised sitemap traversal

Author: Kevin. This lane inventories public article entrances; it does not
declare the newspaper or its historical corpus complete.

The September 2026 index advertises 652 numbered child files. The older shared
discovery stopped at `max_sitemaps_reached_500`, including the index itself,
so its last numbered file was 499. Child 500 begins on 2024-05-27, explaining
the old stored-data boundary. The previous generic discovery also collapsed
different null-URL error records when deduplicating by source and URL. This lane
retains a status for every advertised child and every URL occurrence.

## Freeze and traverse

Read the official index with the existing verified-TLS transport and preserve
its complete decoded XML and capture metadata. Freeze it into a new independent
directory, separate from team discovery files:

```sh
.venv/bin/python code/01-crawlers/scripts/discover_tiempo_sitemaps.py freeze \
  --index-file '/absolute/saved/index.xml' --run-dir '/absolute/independent/discovery'
.venv/bin/python code/01-crawlers/scripts/discover_tiempo_sitemaps.py run \
  --run-dir '/absolute/independent/discovery' --limit 105 --priority-from 500
```

The explicit per-invocation limit is not a completion threshold. Continue bounded
invocations until every frozen entrance has a recorded outcome. Review and
explicitly retry failures; never turn pending or failed into complete to close
the task. The live index advertises legacy HTTP/apex locations; both those
advertised locations and the verified HTTPS/www request locations are retained.

`discovery.sqlite` stores child states, attempts, and `(child URL, ordinal)`
article occurrences. `snapshots/` preserves full decoded UTF-8 XML and response
metadata before a result transaction. An interrupted complete response can be
reused. `network_calls/` distinguishes requests started from responses durably
saved. Existing database state is backed up before each discovery invocation,
and the operation is logged under Kevin's name. A single worker pauses at least
one second between requests and stops on 403, 429 or server errors.

The index hash, URL-to-number identity, completed XML hashes and every parsed
entry are checked before continuation. Malformed input or changed state stops
instead of silently pairing a child with another child's response. A saved
reconnaissance directory can provide verified same-site numbered snapshots for
reuse. Capture time remains the original response time; processing time is
separate.

## Dates, titles and limits

`news:publication_date` is preserved as `discovery_publication_date`, with a
strictly validated `discovery_day` for queue planning. `lastmod` remains separate.
`news:title` is discovery metadata. Neither substitutes for article-page
publication dates, titles or unavailable text.

The article request, final URL and valid canonical must be compared with the
old database/export before a new crawl. Do not match by slug alone. Retain good
old records, expose short/failed/incomplete ones separately, and distinguish
known reviewed pilot results from the old protected baseline. See
`TIEMPO_BATCHES.md` for the subsequent extraction gate.

The target 2018–2025 range is filtered per entry, not by sitemap number. Older
dates are retained for later extension; 2026 entries are explicitly outside
that target. Missing, malformed or conflicting discovery dates need their own
queue. Visiting all advertised children proves index traversal only: it cannot
prove that the index advertises every article ever published, or that deleted
historical article pages can be recovered.

## Verification

The Task 3 audit keeps the index, child responses, old discovery boundary,
read-only source hashes, queue reconciliation and per-batch quality records.
Tests cover malformed dates, interrupted-response recovery, explicit retries,
legacy index locations and identity/content mismatch rejection without network.
Consult the dated run note for any narrowly documented source XML repairs;
the original XML remains available for inspection.

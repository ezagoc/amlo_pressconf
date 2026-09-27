# Tiempo Task 3: provenance and staged collection

Author: Kevin. Status: in progress. Shared historical data and the newspaper
tracker are preserved. A finished worker or completed sitemap traversal is not
proof of historical coverage or final newspaper acceptance.

## Read in order

1. `TIEMPO_DISCOVERY.md`: immutable original sitemap responses and narrow XML
   repair. Discovery dates and titles are provenance, not replacements for
   missing article-page fields.
2. `crawler_core/tiempo_queue.py`: read-only baseline/request/canonical/final-URL
   identity matching, separate source-date conflicts and fixed validation queue.
3. `TIEMPO_PILOT.md`: article parsing, snapshots, resumable state and review-bound
   exports, still capped at 80 URLs per individual execution directory.
4. `TIEMPO_BATCHES.md`: immutable program/input/settings, isolated bounded batches,
   safety stops, real review gates and separate retry queues.

## Local locations

The repository stores code. Set `MEDIA_ROOT` to the existing Media Dropbox root;
never paste a different operator's absolute root into code. Kevin's isolated
Task 3 run is below
`data/00-newspaper_data/crawler/pilots/Kevin/tiempo_task3_2026-09-26/`.
The `pilots` placement reuses isolation safeguards; it is not shared corpus data.
Original shared SQLite, shards and spreadsheet are not target outputs.

Local audit provenance, baseline index, queue construction, independent QA and
verification helpers are in Kevin's Econ 496 workspace at
`review_work/media_task3_2026-09-26/`. Its `paths.json` identifies current absolute
locations. Desktop deliverables are in the Media project task-3 folder. Native
HTML is kept once in the isolated Dropbox run; desktop evidence uses hash/path
indexes instead of duplicating all snapshots.

## Established discovery and protected baseline

The frozen current index advertises 652 child sitemaps: 651,754 URL occurrences,
646,758 distinct URL identities. All advertised children were processed. Thirty
XML documents contain control characters in 35 news-title entries, confined to
news-title text; originals remain unchanged and narrowly repaired extraction is
flagged. This says nothing definitive about articles absent from the index.

The historical DB has 465,393 requested-URL records; old exports have 359,662
rows, including canonical aliases, so these are not two additive article counts.
Keep old records and all failed attempts. A previous discovery max of 500 total
maps stopped after child499; child500 begins on2024-05-27, matching the old data
boundary. Some additional old children had failed parsing.

The strict 2018–2025 queue separates 106,220 new URLs,24,429 old errors,2,150 old
short texts and2 old missing-field records (132,801 candidate requests total).
A further2,589 conflicting discovery-date identities remain separately tracked.
Earlier2015–2017 and2026 discoveries are separate. Source gaps, new requests,
URL aliases, complete-field rows and independent articles must not be conflated.

## Current expansion and recovery rules

The first400 new URLs use20 fixed selections in each of20 months from2024-05
to2025-12. Five80-URL batches retain outcomes; failures are not replaced.
Expansionv1 stopped after8 responses when four source-empty titles were treated
as system failures. Its responses/code are preserved. A narrowly corrected
parser and evidence-based source-gap classification use independentv2; those
same8 responses were reused offline without another network request.

Real defects fixed: terminal standalone related-story promotion could pollute
prose; Instagram UI boilerplate could appear as body while its permalink was
omitted. Genuine captions remain, with source warnings where needed. Empty
article titles stay null and `missing_title` even when the recognized template
proves all source channels empty. Do not fill them from guessed URL words or
silently promote them to complete records. Sitemap titles may be provided in a
separately named provenance field, never represented as observed article titles.

The400 expansion currently requires at least10 actual source checks per batch,
plus every error and additional risk/section cases. Approval notes signed Kevin
are AI-assisted project records; they do not imply Kevin personally read each
page. Unchecked records remain `not_reviewed`. The method preserves lead and
article-body prose and embedded-media references, not independent main-image
captions, all navigation text, audiovisual transcripts or OCR.

Use native reviewed exports or apply review sidecars/history before using raw
SQLite payloads. Complete-field exports omit missing-title partial records;
`batch_reports/*/all_results` retains them. The failure list distinguishes
source missing fields from responses with no usable article body. Never equate
all failures with absent news text.

## Before further scale

All five expansion batches must pass their frozen protocol, including the last
approval and zero-new-request completed resume, before a new production protocol
is frozen. Subsequent stages should be bounded by month/category and at most2000
URLs so status checks do not repeatedly scan a130,000-row prefix. Protocol and
sampling reductions must be explicit in a new plan; never rewrite the400 rules.
Maintain the one-second request gap, safety-stop policies and10GiB disk reserve.
Back up existing isolated data before modifications and append a Kevin note.

Known remaining work includes the rest of new target URLs, old failure/short
record recovery, conflicting discovery dates, earlier history, retries or explicit
source-gap dispositions, cross-batch identities and coverage accounting. Other
newspapers start only after this first newspaper has an honest acceptance scope.
No shared tracker completion mark, final corpus merge or Task4 acceptance has
been carried out by this Task3 setup.

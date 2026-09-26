# Tiempo: bounded Mac pilot

Author: Kevin. This validates selected articles; it does not discover or certify
the complete 2018–2025 archive. Shared production databases, discovery files,
exports and trackers are not outputs of this workflow.

## Setup

From the repository root, using Python 3.10 or newer:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r code/01-crawlers/requirements-tiempo.txt
```

Set `MEDIA_ROOT` in the ignored repository `.env` to the local Dropbox Media
directory. Example for macOS:

```text
MEDIA_ROOT=/Users/name/Library/CloudStorage/Dropbox/Media
```

The pilot uses macOS/Linux file locking and the system `curl` with normal TLS
verification. It requires no API credentials or browser automation. The shared
network helper also selects `curl.exe` on Windows; the pilot runner itself is
tested on Mac. The older broad repository requirements include unrelated tasks
and are not necessary for this pilot.

## Explicit input and isolated output

Create an independent folder below
`$MEDIA_ROOT/data/00-newspaper_data/crawler/pilots/` and put `Kevin_NOTE.md` in it
to describe the experiment. Supply 1–80 unique Tiempo URLs in a UTF-8 CSV with
`sample_id,url,expected_year,selection_reason,expected_kind`. The aliases
`stratum,sample_role` are accepted for the last two columns. Other columns are
retained as selection metadata. Expected values never determine extracted data.

```sh
.venv/bin/python code/01-crawlers/scripts/run_tiempo_pilot.py \
  --input '/absolute/path/to/sample_manifest.csv' \
  --run-dir '/absolute/path/to/Media/data/00-newspaper_data/crawler/pilots/Kevin/run-name'
```

Use the same command to resume. One worker fetches sequentially, with a default
one-second pause. Each completed HTML response and its metadata are preserved
before a per-URL database transaction. Ctrl-C leaves committed rows intact.
Normal resume skips completed results, including errors, and can recover a
complete saved response if interruption occurred before its database commit.
An interrupted response without a complete snapshot must be fetched again.

- `--retry-errors`: back up and request only existing error results.
- `--reparse-cache`: back up and re-extract saved complete snapshots, offline.
- `--export-only`: regenerate exports without making requests.

These three modes are mutually exclusive. Changing the sample URL set requires
a separate run folder. A lock prevents two processes from writing the same run.
Before revising existing pilot results, backups and a Kevin note are recorded.

## Extraction and review contract

The Tiempo-specific parser is used by the existing sitemap extractor and this
pilot. It reads the visible article title, lead paragraphs, article body and
byline. `main_text` contains the lead plus the article's prose, without the
author/date line, advertisements or recommendation sidebar. `summary` separately
retains the lead. Short news is not rejected merely for being under 500 characters.
Video URLs are retained as `media_embeds`; the parser does not invent a transcript.

Publication evidence comes only from the article's visible byline or explicitly
published metadata. Modification dates, sitemap dates, URL text and sample
expectations never become publication dates. Conflicting publication evidence
is quarantined for review. No timezone is invented when the site supplies none.
An absent author remains null; the site's publisher meta tag is not an author.
The site's HTTP-200 error pages, incomplete transfers and unknown body layouts
are recorded as failures rather than exported as news.

Outputs retain `url,title,summary,main_text,authors,date,topic` for compatibility,
plus canonical/final URL, source and field evidence, capture timestamp, raw HTML
path/hash and input metadata. `articles.csv` and `articles.parquet` contain
successful unique articles. `attempts.csv` and `attempts.parquet` preserve
request outcomes including error controls and URL aliases. Empty CSV fields
mean null; Parquet preserves nulls. SQLite is the resumable source of truth.
`export_manifest.json` contains counts and file hashes. Always reconcile
attempted URLs, successful URLs and unique articles separately.

Automated success is not manual acceptance: compare every pilot row with its
saved webpage, including title, all prose, publication evidence, canonical URL
and the author actually shown. Keep unavailable pages and uncertainties visible.

## Checks

```sh
.venv/bin/python -m unittest discover -s code/01-crawlers/tests -v
```

The live pilot additionally requires a real interruption/resume check, field
review of every sample, export readback and original-file preservation checks.
Do not start a full historical crawl or mark the shared tracker complete on the
strength of a small pilot alone.

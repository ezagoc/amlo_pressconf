# Sheinbaum conference preprocessing

## Current snapshot: October 26, 2026

The preferred archive now contains **503 official conferences, October 2, 2024
through October 15, 2026**. Source collection and journalist/outlet extraction
are complete for this snapshot. Later dates have not been collected.
Use `official_source/through-2026-10-15/` and
`api_extraction/official-through-2026-10-15/` below the data root.

The extraction contains 4,326 normalized daily reporter/outlet records before
manual harmonization. The latest reviewed export contains 3,391 daily records,
453 reporter forms and 328 outlet labels. These are identification records,
not question counts or attendance totals. The raw extraction and introduction
evidence remain available alongside harmonized records.

`05_deduplicate_outlets_periodistas.R` defaults to `official_latest`, with
`OFFICIAL_THROUGH <- "2026-10-15"` and `WRITE_OUTPUT <- FALSE`. See the
[project recap](../../../../docs/PROJECT_STATUS_2026-10-26.md) for the approved
groupings, attendance review results, paths, and pending panel refresh.

The separate speaker/question–answer extension remains incomplete. Its saved
progress reports 114 completed dates out of 221, while the published export
still contains ten pilot dates. Quota exhaustion and eight validation failures
are recorded. Do not interpret completed identity extraction as completed
question–answer analysis. The following sections preserve the earlier 221-date
and pilot workflows; their counts refer to those historical snapshots.

Adaptation of the AMLO `question_class` workflow for **all available** main
transcripts in [NOSTRODATA/conferencias_matutinas_sheinbaum](https://github.com/NOSTRODATA/conferencias_matutinas_sheinbaum).
The requested scope was expanded from the first year to all available data.
Code stays here; raw data, checkpoints, and generated datasets live under
`MEDIA_ROOT/data/02-conferences-sheinbaum/`. Existing AMLO outputs are separate.

## Transcript analysis pilot: stages 1–2

**Preferred source:** official Presidencia HTML. See the official-source
replacement workflow in [transcript_pilot/README.md](transcript_pilot/README.md).
Raw HTML, metadata, parsed paragraphs and source comparisons are separate under
`official_source/`; the refreshed ten-conference analysis is under
`transcript_analysis/official-pilot-10/`. The collection covers the existing
subset's dates, not every official conference published since August 2025.
The earlier GitHub-based results below are preserved and provisional: the
official pilot restores 435 whole paragraphs and additional partial text.
The completed official pilot contains **454 questions/requests, 22 opinions,
357 questions linked to presidential responses, and 47,924 live presidential
words**. All 221 existing dates have been collected from official pages; model
speaker/question analysis covers the ten pilot dates. The full official-source
journalist/outlet runner is described below.

### Full transcript analysis in progress

On October 14, 2026, the user authorized extending the existing speaker,
word-count and question/response stages to all 221 official dates. Run
`transcript_pilot/full_analysis.py`; results and live checkpoint progress are
under `transcript_analysis/official-full/`. Ten compatible pilot analyses and
all completed journalist/outlet identifications are reused. The remaining 211
dates require two model stages each. The pilot reuse/export check passed with
API calls disabled. The runner automatically exports and audits after every
requested date completes; incomplete runs retain checkpoints and error records.
Consult `run_progress.json` and `auxiliar/corpus_report.json` for actual
completion, rather than treating this launch note as evidence of completion.
Topics, dissent, anger and responsiveness scoring are not included in this run.

## Official-source journalist/outlet extraction

The resumed 2026-10-14 run is **complete: all 221 dates**, including ten reused
pilot dates and 211 new dates. The final `official-full/auxiliar/` export
contains **1,978 normalized daily reporter/outlet records from 1,486
introduction passages**, preserving 1,995 evidence records. There are 72
outlet-only records and 24 named records without a stated outlet. At least
one identification was extracted on 220 dates. Source/input hashes, literal
evidence support, full date coverage and daily-key uniqueness checks pass.
The older `official-full/partial/` export remains a historical incomplete
snapshot; use the main final export instead.

Select `DATA_VERSION <- "official_full"` to review this older 221-date export;
the default is now `official_latest`. Existing manual alias rules are preserved. The 436
outlet labels and 283 reporter name forms are not fully harmonized entities.
There are 53 aligned old evidence records requiring review and eight mapped
prior review leads; these flags are not automatically classified as omissions.

Thirteen introduction passages were checked directly against their source
text; see `official_run_spot_checks.json`. This is a purposive evidence check,
not a measured accuracy/recall estimate. A validation edge case on June 27,
2025 was fixed: `HCTV —Javier Pérez— Noticias` explicitly inserts the reporter
name into the outlet name. Outlet validation now allows removing that exact
name only within paired aside markers in one source row; arbitrary intervening
words remain disallowed. The original evidence is retained unchanged, and
regression checks cover accepted and rejected variants.

Run all 221 archived official transcripts with the same `gpt-6.1-sol` prompt
and strict evidence validation used in the official pilot:

```sh
.venv/bin/python code/03-cleaning_conf/question_class/sheinbaum/official_journalists.py --dry-run
.venv/bin/python code/03-cleaning_conf/question_class/sheinbaum/official_journalists.py
```

Outputs are separate under
`MEDIA_ROOT/data/02-conferences-sheinbaum/api_extraction/official-full/`.
The ten pilot journalist checkpoints are reused only when the model, prompt,
schema and complete ordered transcript match. The remaining 211 dates use
official press/generic-intervention headings as eligible evidence and provide
the entire transcript for context. Recorded speakers and incidental mentions
are excluded by the extraction instructions. Names and outlets must occur in
their cited introduction text; unstated names remain missing.

The runner validates archived source hashes, resumes successful checkpoints,
and writes per-date failures to `run_errors.json`. Rerun the same command after
resolving a failure. `--export-only` rebuilds exports and the audit without API
calls. Main deliverables:

- `auxiliar/journalists_and_media.csv` and `periodistas_v2_all_years.parquet`:
  one row per date and normalized reporter/outlet combination.
- `auxiliar/journalist_media_evidence.csv` and `.parquet`: all explicit
  introductions, preserving repeated same-day evidence and original labels.
- `auxiliar/official_vs_github_coverage.csv`: date-level introduction comparison.
- `auxiliar/aligned_old_evidence_missing_review.csv`: previously extracted
  evidence with verified official-source alignment but no matching new anchor.
- `auxiliar/full_run_review_flags.csv`: earlier semantic review leads mapped
  to official paragraphs; these are review leads, not automatic exclusions.
- `auxiliar/api_run_audit.json`: coverage, provenance, counts, successful token
  usage and limitations. Reused pilot usage is separated from new calls.
- `review/index.html`: summary and expandable introduction evidence.

Use `--export-partial` to rebuild the clearly marked `partial/` review and
exports without API calls while the full run is incomplete. Comparisons and
missing-evidence review leads are restricted to the completed dates.

Counts describe explicit identifications, not individual questions or unique
attendees. Deduplication of normalized daily keys is automatic; deciding
whether different labels refer to the same person or outlet remains part of
the manual R harmonization. The original extraction is preserved.

The ten-conference speaker/section and question–response pilot is complete.
See [transcript_pilot/README.md](transcript_pilot/README.md) for execution,
definitions, and the read-only R review script. Outputs are separate under
`MEDIA_ROOT/data/02-conferences-sheinbaum/transcript_analysis/pilot-10/`.

The pilot contains 295 questions/requests, seven independent opinions, and
47,131 transcribed live presidential words. There are 235 questions with a
thematically linked presidential response; adjacency is stored separately.
These are provisional counts for the supplied text. Official-source checks
revealed missing speaker labels and at least one question omitted from the CSV.
Eight sourced speaker-register corrections are recorded; source omissions are
flagged rather than reconstructed from answers. All 3,719 source rows are
accounted for, and literal excerpt, word-partition, and link checks pass.
Thirty question/response excerpt checks supplement automated validation; this
is not a held-out, independently annotated accuracy evaluation.

## Completed full API extraction

The full journalist/media run completed on 2026-10-13 using `gpt-6.1-sol`.
All 221 source dates are covered: 216 were processed by the API and five
had no eligible question-speaker rows. Results live under
`MEDIA_ROOT/data/02-conferences-sheinbaum/api_extraction/full/auxiliar/`.

- **656 dated reporter–outlet records**, from 514 identification passages;
  670 evidence records retain repeated introductions.
- **292 outlet-only records** and six named records without an outlet.
- Identifications on 162 dates, with 141 normalized name forms and 277 outlet
  labels. These labels still require alias harmonization.
- All stored evidence matches source text and hashes; daily normalized keys
  are unique. All 454 previously reviewed passage anchors occur in the API
  evidence (two were incorporated into multi-row introductions). There are
  62 additional introduction anchors; this is not an accuracy/recall score.
- Estimated successful-response cost: **USD 14.51**, including cache writes,
  from the saved usage metadata. This is not an invoice.

`journalists_and_media.csv` and `periodistas_v2_all_years.parquet` are the raw
daily export. `api_run_audit.json` stores integrity checks and usage;
`introductions_added_vs_review.csv` and `introductions_missing_vs_review.csv`
show passage comparisons. `full_run_review_flags.csv` contains 12 recorded
review cases with source text and nearby context, including a likely false
self-identification of Sáenz de Miera, ambiguous affiliations, slogans and
repeated/variant labels. Raw records are preserved pending review. The manual
inspection focused on differences from the previous extraction and selected
edge cases; it was not an exhaustive semantic review of every full-run record.

Reproduce the audit and recorded review flags without API calls:

```sh
.venv/bin/python code/03-cleaning_conf/question_class/sheinbaum/audit_api_run.py
```

These are identification records, not counts of individual questions or unique
attendees. The earlier PDF still describes the original extraction below.

## Original journalist and outlet extraction (no API)

The final requested scope is **journalists and media only**, using their
self-introductions and explicit statements of affiliation in the transcripts.
Outlet-only introductions are included with the journalist name left blank.
No news collection, question classification, or political alignment is needed.

The reviewed export contains **602 daily reporter–outlet combinations**, including
**239 outlet-only records**, on **149 of the 221 source conference dates**.
There are 137 normalized reporter name forms and 203 outlet labels. These are
not verified counts of unique people or organizations: spelling/name variants
are retained and parent media groups and their titles remain separate labels.
Three named records have no stated outlet.

Primary outputs under `MEDIA_ROOT/data/02-conferences-sheinbaum/auxiliar/`:

- `journalists_and_media.csv`: dated records with reporter, outlet, normalized
  labels, missing-value flags, source rows, and exact transcript evidence.
- `periodistas_v2_all_years.parquet`: the same records in the AMLO-compatible
  filename, with additional evidence columns.
- `journalist_media_directory.csv` and `media_directory.csv`: observed names
  and media with first/last dates and number of observed conference days.
- `journalist_media_evidence.csv` and `.parquet`: all 606 evidence records,
  retaining repeated same-day introductions that the main table deduplicates.
- `journalists_media_review.csv`: missing or partial identities and ambiguous
  outlet labels; `journalist_media_coverage.csv` covers all 221 source dates.
- `journalist_media_report.json`: counts and limitations.

Reproduce the export from the prepared source snapshot:

```sh
.venv/bin/python code/03-cleaning_conf/question_class/sheinbaum/extract_journalists_local.py
```

`reviewed_introductions.tsv` and `reviewed_outlet_only.tsv` are the inclusion
ledgers. Their source-row references and SHA-256 evidence hashes are validated
on every run. The outlet dictionary validates only the reviewed affiliations;
it does not include incidental mentions of other media. Names are never
transferred from another date or inferred from an outlet. Missing introductions
remain missing, so this export is **not a complete attendance census**. A named
and anonymous reference to the same outlet on the same day may be the same
person; rows must not be interpreted as distinct attendees. Refreshing the
source requires reviewing new introductions and updating the ledgers.

## Completed preparation

### Manual alias review

Open `05_deduplicate_outlets_periodistas.R` in RStudio for the same editable
`case_when()` workflow as AMLO. Run in the default review mode, inspect
`outlet_table`, `reporter_table`, `name_table`, and `candidate_pairs`, and use
`inspect_names()` to retrieve the exact supporting introductions. The user-confirmed
mapping of `grupo transmedia` and `la chispa` to `grupo transmedia la chispa`
is active, alongside the user's subsequent editable alias/grouping rules.
`DATA_VERSION <- "official_full"` will read the official-source run after it
completes and load `review_flags` for inspection. While API credits block
completion, the default remains `"api_full"`, the earlier GitHub-source API
run. Set `"original_reviewed"` for the original extraction.
`WRITE_OUTPUT <- FALSE` keeps the script in
review mode.
After editing the rules, inspect `changed_rows`, `collapsed_rows`, and
`before_after`. Set `WRITE_OUTPUT <- TRUE` when ready to save separate
`periodistas_v2_all_years_dedup.parquet` and `journalists_and_media_dedup.csv`
outputs, plus all mapped records and an alias audit. Existing source exports
and the PDF report remain unchanged; the PDF would need regeneration from the
reviewed dataset after manual harmonization.

The source snapshot `5cf67b3aaf08ceb24db34df4dd8d94d69f3a8d39` contains **221
conferences, October 2, 2024–August 22, 2025**. It does not cover a full year.
Preparation completed with 84,547 transcript rows and 15,139 nonempty
question-speaker paragraphs. These paragraphs have **not** yet been split into
individual questions/opinions or assigned to named journalists by the model.

| Month | Conferences | Question-speaker paragraphs |
| --- | ---: | ---: |
| 2024-10 | 22 | 1,881 |
| 2024-11 | 18 | 704 |
| 2024-12 | 18 | 1,102 |
| 2025-01 | 22 | 1,461 |
| 2025-02 | 20 | 1,476 |
| 2025-03 | 21 | 1,439 |
| 2025-04 | 19 | 1,115 |
| 2025-05 | 21 | 1,368 |
| 2025-06 | 21 | 1,439 |
| 2025-07 | 23 | 1,844 |
| 2025-08 | 16 | 1,310 |

Five source files contain no recognized question-speaker rows: 2024-11-11,
2024-11-14, 2024-11-21, 2024-11-25, and 2025-02-07. Their recorded participants
are officials/presenters. Treat these as source-coverage review cases, **not**
confirmed zero-question conferences. Twelve weekdays inside the observed range
have no main transcript; holidays/cancellations may account for gaps.

The existing daily news summaries end on 2024-09-30. None of these conferences
has complete news context. Existing raw La Jornada articles extend to
2024-10-30 and 24 Horas articles to 2024-11-29, before topic filtering; they
cannot supply news context for 2025. New news collection is a separate input
requirement. The 10-conference journalist/media API pilot completed on 2026-10-13
after the initial exhausted-credit error was resolved. Other model stages have
not been run. News inputs are unnecessary for
the requested journalist/media extraction.

## Run

From the repository root, using the existing virtual environment:

```sh
.venv/bin/python code/03-cleaning_conf/question_class/sheinbaum/prepare.py
```

The default selects all main conference CSVs. To restrict the original first
year request, add `--start-date 2024-10-01 --end-date 2025-09-30`. To reproduce
the saved snapshot without network access:

```sh
.venv/bin/python code/03-cleaning_conf/question_class/sheinbaum/prepare.py --offline
```

### API extraction: full text and outlet-only introductions

The API implementation is tested offline; both the live 10-conference pilot
and full run completed on 2026-10-13. Billing errors stop without retries.
The default stage is **journalists only** and
uses `gpt-6.1-sol` with low reasoning effort through the Responses API.
Structured output permits `name: null` and partial names. The prompt preserves
compound labels such as Grupo Transmedia La Chispa and never infers a name
from an outlet. Names and outlet labels must occur in their cited source rows.
These checks establish textual support, not perfect speaker attribution.

#### Completed pilot verification

The pilot returned **36 dated records from 21 identification passages**,
including **13 outlet-only records**. All 20 passages in the earlier reviewed
sample were recovered, and Telemax on 2024-10-02 row 95 was newly recovered.
Every returned record was reviewed against its cited transcript. One label
included a trailing slogan after Animales con Derechos; this is trimmed in a
separate reviewed copy. An ambiguous Telesur statement is flagged, not added.
The prior sample is incomplete, so its 20/20 recovery is not a general recall
estimate. Question attribution was not evaluated.

Successful checkpoints recorded 269,126 input tokens (269,096 cache-write
tokens) and 956 output tokens, for an estimated **USD 0.68236** at the documented
standard rates. This is an estimate, not an invoice or failed-attempt total.

Pilot `auxiliar/` deliverables:

- `journalists_and_media_reviewed.csv` and `.parquet`: reviewed copy with the
  single label correction and preserved `outlet_api`/`outlet_aux_api` columns.
- `pilot_verification.html`: readable audit and all returned evidence.
- `pilot_verification_report.json`: counts, usage, scope and limitations.
- `pilot_review_candidates.csv`: ambiguous and correctly excluded examples.

`verify_pilot.py` reproduces integrity checks and the recorded manual decisions
for this specific pilot. It makes no API calls. Raw API outputs remain intact.

The model receives the complete transcript (no 500-character truncation), with
speaker labels and an explicit list of eligible question-speaker rows.
Official and other paragraphs provide context to help identify narrated or
replayed material; they cannot be cited as the reporter's self-introduction.
The five conferences without eligible rows are listed in full-run coverage
but are not submitted to the API.

With `OPENAI_API_KEY` configured locally in `.env`, preview the pilot without
calls, writes, or requiring a key:

```sh
.venv/bin/python code/03-cleaning_conf/question_class/sheinbaum/run_models.py --limit-conferences 10 --dry-run
```

Run the pilot (paid API calls):

```sh
.venv/bin/python code/03-cleaning_conf/question_class/sheinbaum/run_models.py --limit-conferences 10
```

The 10 dates are deterministic and evenly spaced over eligible conference
dates, including the first and last. Omit `--limit-conferences` to process
all available dates. `--model` overrides the model; `--input-root` selects
prepared inputs. The default output is a separate directory:

- Pilot: `MEDIA_ROOT/data/02-conferences-sheinbaum/api_extraction/pilot-10/`
- Full run: `MEDIA_ROOT/data/02-conferences-sheinbaum/api_extraction/full/`

`--output-root` overrides the destination; using the input root itself is
rejected to protect the reviewed extraction. Pilot and full-run checkpoints
are separate. Repeating a run with the same destination reuses validated
responses with the same prompt, input, schema, and model settings. Response
usage is saved with each successful checkpoint; it does not account for
failed/retried requests without a validated checkpoint.

The API output's `auxiliar/` contains `journalist_media_evidence.parquet`,
`periodistas_v2_all_years.parquet`, `journalists_and_media.csv`, missing-identity
review rows, per-date coverage, and `journalist_extraction_report.json`.
The daily dataset collapses date + normalized name + normalized outlet;
evidence records retain repeated introductions. These are raw model labels,
not fully harmonized entities. Review API results against the existing
transcript-reviewed ledger before manual alias reconciliation or new rankings.
The manual review R script now defaults to the full API output and preserves
the original extraction as an optional input.

Broader stages remain optional and are outside the current extraction task:
`--stage questions`, `--stage news`, `--stage alignment`, or `--stage all`.
They use outputs in the selected API output directory. Question attribution
between successive introductions is tentative and requires review.

`--stage news` reuses the existing article files, topic filters, and
source-labelled summary construction. It writes Sheinbaum summaries separately.
To supply newly collected news, extend the original source parquet inputs or
provide a Sheinbaum `auxiliar/daily_summaries.parquet` with unique `date`,
`daily_summary`, and `n_articles` columns, then run `--stage alignment`.

Alignment defaults to leaving items pending when any expected context day is
missing. An explicit `--allow-missing-context` enables the original pipeline's
fallback and marks these outputs `complete_incomplete_context`.

## Outputs

Under `MEDIA_ROOT/data/02-conferences-sheinbaum/`:

- `raw/`: original complete transcript CSVs, retaining upstream paths.
- `source_tree.json`, `source_manifest.json`: pinned source inventory, file
  hashes, dates, and conference counts.
- `source_metadata/`: upstream README and license, with NOSTRODATA attribution.
- `auxiliar/transcript_rows.parquet`: all transcript paragraphs with date,
  original and normalized speaker labels, text, word counts, source path, and
  zero-based source row (header excluded).
- `auxiliar/question_rows.parquet` and `.csv`: recognized question-speaker
  paragraphs, retaining their original order and source references.
- `auxiliar/conference_manifest.csv`, `monthly_coverage.csv`,
  `speaker_labels.csv`, `news_context_coverage.csv`,
  `conferences_without_question_rows_review.csv`, and
  `weekday_gaps_for_review.csv`: preparation audits.
- `auxiliar/preprocessing_report.json`: preparation counts and limitations.

After model execution, outputs use the original dataset names:
`periodistas_v2_all_years.parquet`, `questions_dataset.parquet`,
`daily_summaries.parquet`, `periodistas_with_news_context.parquet`, and
`questions_with_alignment.parquet`. Additional files are
`journalist_blocks.parquet`, `unassigned_rows_review.csv`, and
`no_outlet_review.csv`. Responses and token usage are recorded under
`checkpoints/<stage>/`; credentials are never stored there.

## Method and differences from AMLO

Preparation discovers dates from filenames rather than AMLO's directory
naming convention. Each download is verified against its Git blob hash;
filename dates must agree with every CSV row. Only complete transcripts are
read, avoiding duplicate participant-specific exports. Raw bytes remain
unchanged. `Sentimiento` is excluded because the source says it is invalid.

Question labels include whitespace-normalized `PREGUNTA`, `PREGUNTAS`,
`PREGUNTA (VIDEOLLAMADA)`, `INTERLOCUTOR`, `INTERLOCUTORA`, and the observed
`INTERLOCUTIR` typo. Generic `INTERVENCION` labels and `REPORTERO` are excluded:
the latter's six rows on 2025-02-14 are a replayed media exchange, not questions
to the president. Inspect `speaker_labels.csv` when refreshing the source.

API journalist identification uses a dedicated Spanish prompt for explicit
introductions, nullable names, and source-row evidence. It sees complete
paragraphs and the surrounding transcript context. Question/opinion definitions and
alignment definitions come directly from the original scripts. Monday
conferences use Friday–Sunday news; other days use the preceding day.

Blocks run from an identified journalist introduction to the next identified
introduction, retaining follow-up paragraphs across official responses.
Attribution remains model-assisted: an unidentified intervening journalist
can be included in the preceding block. Review introductions, block source
rows, and unassigned paragraphs before substantive analysis. This method
avoids the original short-comma/greeting cutoff but does not establish ground
truth. The original ten-word minimum is retained for question extraction.

Journalist data remain long by reporter–outlet–appearance. Questions have a
stable `item_id` and are repeated across the reporter's outlets for downstream
compatibility; **count unique `item_id` values for intervention totals**.
Alignment is called once per unique item. Name/outlet normalization preserves
numbers in outlets and short outlet names such as W. The manually curated AMLO
R alias rules and the 2022 lottery analyses are not automatically applied to
Sheinbaum; review aliases for this population before pooling identities.

Validated responses are cached by model, prompt, and input hash; empty results
also count as completed requests. Truncated or malformed responses fail
validation and are not cached. A failed run stops with its completed response
cache intact; rerun the same command to resume. Final stage tables are only
written once that stage finishes. After input changes, rerun downstream stages.

## Validation

```sh
.venv/bin/python -m unittest discover -s code/03-cleaning_conf/question_class/sheinbaum -p 'test_*.py' -v
```

Six API-extraction tests cover exhausted-credit handling, complete text, outlet-only and partial names,
source evidence validation, deterministic pilot dates, no-call dry runs,
no-eligible-row coverage, separate outputs, and modern API request/caching
parameters. Three local-extraction tests cover outlet-only retention, multiple evidence
rows, exclusion of incidental affiliations, daily deduplication, and rejection
of changed or unsupported evidence. Six additional offline tests cover filename discovery, speaker labels and weekend context,
reporter block boundaries, response validation, empty-response caching/input
invalidation, and a mocked extraction-to-alignment run with multiple outlets
and missing context. All downloaded source hashes and embedded dates were
validated during the completed real-data preparation run. Real model quality
has not been evaluated because no model calls have run.

Data source: **NOSTRODATA**, distributed under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Preserve its
attribution and license when sharing derived data.

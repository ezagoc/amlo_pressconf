# Transcript analysis pilot: stages 1–2

This pipeline reconstructs speakers/sections, counts transcribed words, extracts
individual questions/requests/opinions, and links them to subsequent response
passages. It uses the same ten dates as the journalist-identification pilot.
It does not classify topics, dissent, emotion, evasion, or answer completeness.

## Simple question-alignment pilot

`alignment.py` codes the 454 questions and action requests in the completed
official ten-date pilot; the 22 standalone opinions are excluded. The agreed
labels are `neutral`, `supportive`, `challenging`, and `mixed_unclear`. There
is no question-function variable. Ordinary requests for project/situation
updates are neutral unless their wording or preamble adds endorsement or a
challenge. The target is the current federal government, not whether the
question contains negative words about any actor.

Completed October 14, 2026: 339 neutral, 43 supportive, 43 challenging and 29
mixed/unclear annotations. All 454 question IDs and evidence quotations pass
validation. `alignment_review_notes.json` records 25 purposive assistant
checks, with eight boundary cases flagged for review; these do not establish
an accuracy estimate and do not overwrite model labels. The export includes
`alignment_review_queue.csv` and shows review notes beside each annotation.
June 17 required smaller retry batches after a nonliteral quotation was
rejected. All 42 annotations for that date then passed exact-text checks;
the batching and request fingerprints are retained in its result metadata.

```sh
.venv/bin/python code/03-cleaning_conf/question_class/sheinbaum/transcript_pilot/alignment.py --dry-run
.venv/bin/python code/03-cleaning_conf/question_class/sheinbaum/transcript_pilot/alignment.py
```

Outputs are separate under `question_alignment/official-pilot-10/`: versioned
`codebook.json`, cached requests, per-date results, `auxiliar/question_alignment`
in CSV/Parquet, counts/report, and a readable `review/index.html`.
Only question IDs, question text and selected preamble text are submitted.
Answers, model response-link labels and reporter/outlet metadata are excluded;
known reporter/outlet strings inside the input are masked. Text may still
reveal identity indirectly, so this is not guaranteed full blinding.
Every code requires literal evidence and a short reason. Export checks
coverage, input hashes and quotations. These checks do not establish semantic
accuracy. Model results remain provisional pending sample review. `--export-only`
rebuilds outputs without API calls; `--source`/`--output` support later expansion.

## Full official subset: stages 1–2

`full_analysis.py` extends the same definitions and model to all 221 archived
official dates. It checks archived HTML hashes, exact transcript/input hashes
for journalist evidence, and compatible pilot cache keys before running.
The ten pilot structure/QA passes are reused. All 221 completed official
journalist/outlet results are reused without new identity API calls. Existing
manual alias rules are not applied to question labels automatically.

```sh
.venv/bin/python code/03-cleaning_conf/question_class/sheinbaum/transcript_pilot/full_analysis.py --dry-run
.venv/bin/python code/03-cleaning_conf/question_class/sheinbaum/transcript_pilot/full_analysis.py
```

Output: `transcript_analysis/official-full/` under the Sheinbaum data root.
`--dates YYYY-MM-DD ...` restricts a run; `--export-only` rebuilds from saved
results without API calls. Unchanged successful model requests resume from
checkpoints. At most `--workers` conferences are in flight (default three);
billing/authentication errors stop new submissions. Per-date errors and
progress are saved in `run_errors.json` and `run_progress.json`.

Each new date requires a speaker/section pass followed by a question/response
pass. Reused introductions that cannot attach to one reconstructed live press
speaker are retained as `identity_link` review flags, not forced onto a person.
The exports use the pilot's table names and include `corpus_report.json` to
distinguish selected-date exports from a complete 221-date export. During a
run, existing exported tables may describe an earlier subset: inspect the
report's `complete` and `n_exported_dates` fields before analysis.

The ten-date reuse/export/audit check completed with API calls disabled and
the same 454 questions/requests and 47,924 presidential words. The full run
was started October 14, 2026. Counts and completion will be updated after the
final saved-file audit; model classifications remain provisional.

## Official-source replacement

**Completed official pilot:** 454 questions/requests, 22 opinions, 357 questions
with a thematic presidential response, and 47,924 live presidential words.
There are 58 explicit introduction passages producing 78 reporter–outlet
evidence records. The preserved GitHub pilot has 295 questions/requests,
seven opinions, 235 presidential links, 47,131 presidential words and 21
introduction passages. Source recovery and model annotation variability both
contribute to differences in model-derived counts.

All 30 model passes completed. Thirteen parser/evidence tests, the exported
quotation/word/ID/link audit and the read-only R review passed. Thirty assistant
question–answer excerpt checks are recorded in `assistant_semantic_review.csv`,
with eight additional unextracted-turn inspections. These are not a gold
standard or an accuracy estimate. There are 203 review leads, not confirmed
errors, including two missing institution annotations and the declarative
follow-up kind decision described below. `review/comparison.html` and
`auxiliar/pilot_before_after.csv` show the side-by-side results.

The official Presidencia pages are now the preferred source. The original
GitHub pilot described below is preserved for comparison; its counts should not
be interpreted as complete conference-level counts. The official pilot has
4,156 paragraphs and 125,591 raw text words, compared with 3,719 paragraphs and
116,967 words in the GitHub CSVs. Ordered text alignment finds 435 whole added
paragraphs in pure insertion blocks and eight blocks with partial text or
punctuation differences. The net paragraph increase is 437, not a count of
additional questions.

```sh
.venv/bin/python code/03-cleaning_conf/question_class/sheinbaum/transcript_pilot/official_source.py
.venv/bin/python code/03-cleaning_conf/question_class/sheinbaum/transcript_pilot/pipeline.py --official
.venv/bin/python code/03-cleaning_conf/question_class/sheinbaum/transcript_pilot/audit_pilot.py --official
.venv/bin/python code/03-cleaning_conf/question_class/sheinbaum/transcript_pilot/compare_pilots.py
# Collection only: existing 221-date subset, no model calls.
.venv/bin/python code/03-cleaning_conf/question_class/sheinbaum/transcript_pilot/official_source.py --scope full
```

Archives and source comparisons live under `official_source/pilot-10/` and
`official_source/full/` in the Sheinbaum data root. Each raw HTML file has URL,
retrieval timestamp and SHA-256 metadata. Cached archives are hash-checked and
not silently refreshed. Pages must identify the expected date and contain a
stenographic article. Parsing keeps native inline spacing, list items,
bold-only questions, full speaker headings and stage/video markers. Every
nonempty article-body text node must be covered exactly once in source order;
unsupported layouts fail explicitly. Full collection records failures in its
manifest instead of silently counting them as complete.

Official analysis outputs live in `transcript_analysis/official-pilot-10/`.
There are three cached model passes per conference: speakers/sections,
individual questions and response links, and fresh explicit journalist/outlet
introductions. The latter is rerun because official pages restore missing
introductions and names. A separate comparison bridge maps 34 of the 36 old
pilot introduction evidence records by exact text; two partially truncated old
introductions are left unmapped. That bridge is diagnostic, not the source of
the refreshed identity table. Old speaker-ID corrections are never applied to
the new source. `review_pilot.R` selects official outputs by default; set
`SOURCE_VERSION <- 'github'` to inspect the original results.

Question, turn and speaker IDs are local to a source version. Do not join the
old and new outputs by their IDs: use text alignment and evidence instead.
Official transcription fidelity does not establish completeness against video,
and model classifications still require semantic review.

Collection is complete for all 221 dates in the existing subset, October 2,
2024–August 22, 2025: 98,154 text rows (98,150 transcript rows and four document
metadata rows), versus 84,547 GitHub rows. Raw text words total 2,837,924 versus
2,568,513. All 221 page titles/dates, archive hashes and body text coverage pass.
The July 14 official page has an internal header dated July 11: this is retained
and flagged in `document_metadata.csv`, not treated as speech. This collection
does not add later dates or rerun the full-corpus journalist API extraction.

`official_review_notes.json` records a kind-classification review for the
recovered March 4 cardiac-emergency follow-up: it is a declarative challenge
classified as an opinion, with replies correctly linked to Kershenobich and
Robledo. Its text is retained; deciding whether implicit challenges count as
questions is an annotation-codebook decision. Missing institution annotations
also receive explicit review flags, even when a speaker's name is confident.

## Original GitHub-source pilot (preserved)

Completed pilot: 3,719 source paragraphs, 643 reconstructed turns, 295
questions/requests, seven substantive opinions, and 362 thematic links to 314
response ranges. There are 47,131 live presidential words; June 17 has no
presidential speech in the source. The register has 154 conference-local
entries including anonymous/recorded voices and technical marker-only entries;
filter `has_transcribed_speech`/`live_words` and role before counting people.
There are 263 review leads, including medium/low confidence, source corrections,
and missing-context warnings; these are not 263 confirmed errors.

## Run

From the repository root:

```sh
.venv/bin/python code/03-cleaning_conf/question_class/sheinbaum/transcript_pilot/pipeline.py --dry-run
.venv/bin/python code/03-cleaning_conf/question_class/sheinbaum/transcript_pilot/pipeline.py
```

Default data destination:
`MEDIA_ROOT/data/02-conferences-sheinbaum/transcript_analysis/pilot-10/`.
The established API model and credential configuration are reused. Paid calls
send public transcript text, source labels, and instructions to the OpenAI API.
Each conference has a structure pass and a question/response pass. Inputs,
settings, usage, and validated output are cached; unchanged requests resume.
`--dates YYYY-MM-DD` restricts to dates in the existing ten-conference pilot.
`--stage structure` runs only the first pass. `--stage export` regenerates
exports/review HTML from saved results with no API calls. `--workers` defaults
to two concurrent conferences. This does not run the full corpus.

## Data and units

Every `auxiliar/` table is exported as both CSV and Parquet:

- `speaking_turns`: one continuous speaker/section/delivery segment. All source
  rows are covered exactly once, including videos and unresolved material.
- `speaker_registry`: **conference-local** people/anonymous speaker entities,
  role, position, institution, evidence and uncertainty. These are not a
  cross-date deduplicated directory or a census of silent attendees.
- `questions`: one question, request for action, or independent substantive
  opinion. Exact quotations have source-row and zero-based character spans;
  `char_end` is exclusive. `context_rows` retains preambles. The full parent
  intervention is accessible through `turn_id`. `followup_of` is optional.
- `responses`: one cited contiguous response range within one speaking turn.
  Different ranges may overlap; **do not sum this table to measure total speech**.
- `question_response_links`: many-to-many links with respondent role, uncertainty
  and presidential flag. A linked response need not answer substantively.
- `adjacent_response_turns`: the immediately following live respondent turn,
  regardless of thematic relevance. This preserves diversions for later analysis.
  `no_response_found` in the thematic-link table does not mean nobody spoke next.
- `journalist_affiliations`: earlier explicit introductions attached to provisional
  local speaker entities. Multiple outlets do not duplicate question records.
- `conference_measures`: source/live/recorded words, presidential words by section,
  other speaking officials/institutions, question and response-link counts.
- `review_flags`: all model uncertainty/notes and automatic coverage review leads.
- `question_turn_coverage`: every live press turn, including turns with no extracted
  substantive item, for checking extraction omissions.
- `excluded_stage_directions`: explicit full-row parenthetical/bracketed directions,
  separators and recognized inline directions excluded from spoken-word counts.

`review/index.html` links to each conference's speaker register, flags, questions,
linked answers and full source transcript. `auxiliar/pilot_report.json` contains
counts and validation results. Model confidence labels are not calibrated
probabilities or a measured accuracy score.

## Definitions and limitations

Word counts use whitespace-separated tokens after excluding explicit stage
directions; `source_word_count` retains the unchanged preparation count. They
are counts in this source transcription, not speaking time. Recorded
material and uncertain delivery are separate from live-word denominators.
Zero presidential words means none observed in this transcript; it does not
independently establish physical absence. Institutions are normalized only
where the source title/context supports them; unknown affiliations remain null.

A raw label may incorrectly persist across speakers. Context-based corrections
retain that raw label and a review note. Names are not expanded from outside
knowledge. A title-only official may count as a discernible local speaker while
the person's name remains unknown. Distinct anonymous journalist IDs should not
be interpreted as a verified unique-attendee count.

The pilot is provisional until semantic review. Source matching establishes
fidelity, not completeness or correct interpretation. No general accuracy/recall
claim is warranted without independently annotated held-out conferences.

## Recorded review and source limitations

`speaker_corrections.json` applies narrowly scoped official-source corrections
at export time. Each change checks the original model name before applying,
preserves changed values in `*_model` columns, and supplies its evidence URL.
Raw checkpoints and raw result JSON are unchanged. March 4 required separating
Eduardo Clark from David Kershenobich and recovering their omitted official
headings; June 17 required identifying the health secretary and institutions.

The official March 4 transcript contains a press follow-up between local CSV
rows 236–237 that is absent from the repository data. Other passages appear to
answer omitted questions. `source_quality_notes.csv` records these limitations;
the pipeline never invents questions from answers or creates unsupported local
row references. Reconcile source completeness before interpreting counts as an
exhaustive record of the events or scaling the analysis to the full corpus.

Open `review_pilot.R` for read-only RStudio inspection. `inspect_question(id)`
shows the question, thematic links, and immediately following respondent turn.
Run `audit_pilot.py` after export for evidence/count checks and the recorded
assistant spot-check sample. This is not independently double-coded validation.

## Checks

```sh
.venv/bin/python -m unittest discover -s code/03-cleaning_conf/question_class/sheinbaum/transcript_pilot -p 'test_*.py'
```

Checks cover complete source partitions, exclusion of recorded speech from
questions, literal excerpts, split questions sharing an answer, invalid
follow-ups, and invalid response-speaker links.

Structured responses follow the [official API documentation](https://developers.openai.com/api/docs/guides/structured-outputs).

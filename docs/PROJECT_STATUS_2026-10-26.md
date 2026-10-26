# Project status — October 26, 2026

**Subsequent update:** the user authorized and completed a panel rebuild and
initial Sheinbaum participation analysis. See [the rebuild record](PANEL_REBUILD_2026-10-26.md).
The following is the earlier consolidation snapshot; its panel-deferral status
is superseded by that update. Question–answer extraction remains incomplete.

## Scope and status

This snapshot consolidates the official transcript workflows, reviewed journalist/outlet identities, attendance reconciliation, and the existing panel, YouTube, balance, and effect-of-asking work. All current project changes were authorized for versioning. No panel rebuild or new model/API run was performed during consolidation.

| Component | Verified saved status |
| --- | --- |
| Sheinbaum official source | 503 conferences, 2024-10-02–2026-10-15; discovery and collection complete for the saved snapshot; 221 reused dates and 282 added dates |
| Sheinbaum journalist/outlet extraction | All 503 requested dates complete; `gpt-6.1-sol`; no remaining extraction errors |
| Manual identity harmonization | 4,326 raw normalized daily records → 3,391 harmonized daily records; 457 → 453 reporter forms; 686 → 328 outlet labels |
| Speaker and question–answer analysis | Ten official pilot dates exported; larger 221-date run incomplete, with 114 completed dates in its progress file |
| Question alignment | Ten-date pilot complete: 454 questions/requests; 339 neutral, 43 supportive, 43 challenging, 29 mixed/unclear; human review still matters |
| Attendance flags | All 130 original labels reviewed: 63 resolved, 13 only roster gaps, 12 outside attendance coverage, 42 with unmatched dates remaining |
| AMLO official archive | 1,369 parsed pages / 1,366 distinct dates; 90 original CSV dates unmatched and 66 additional official dates |
| Panel and metadata refresh | Deferred after the latest outlet decisions; existing analysis outputs predate this refresh |
| YouTube effect-of-asking extension | Earlier full-calendar FEct extension remains marked in progress in its dedicated handoff |

The archive cutoff is October 15, not the date of this document. Completion refers to the discovered/saved corpus; gaps between weekdays do not establish that a conference is missing. AMLO date discrepancies remain a separate review task.

## How the transcript data were produced

1. The initial NOSTRODATA CSV workflow was compared against official Presidencia transcripts. Missing text and speaker-label problems motivated using official HTML as the preferred source. The ten-date official pilot restored 435 whole paragraphs plus additional partial text.
2. Scraping/parsing code saves source HTML, URLs, retrieval information, source hashes, ordered rows, and comparison audits. Scraping does not use GPT.
3. GPT extracts explicit journalist/outlet introductions from the transcript, with full context and literal evidence spans. Unstated journalist names remain missing; outlet-only identifications are retained. Source fingerprints and literal evidence are validated in code. Reusable checkpoints are accepted only when compatible with the input and extraction configuration.
4. The manual R script applies reviewed name/outlet rules. Original extracted labels and evidence are preserved. Daily duplicates are collapsed on date, harmonized reporter, and harmonized outlet. This is identification deduplication; it does not count individual questions or establish physical attendance.
5. The outlet review checks introductions against actual attendance labels and metadata. Approved shared conference IDs are distinct from brand, ownership, legal-entity, and channel identities. Date-specific evidence is used where a global merge was not approved.

Raw extraction includes 144 outlet-only records and 50 named records without a stated outlet; at least one identity was extracted on 500 dates. Reporter forms and outlet labels are not a claim that every remaining entity has been resolved. Automated checks and purposive spot checks are not an independently estimated accuracy/recall score.

## Dataset units and destinations

Paths below are relative to `MEDIA_ROOT/data/02-conferences-sheinbaum/` unless stated otherwise.

| Location | Meaning |
| --- | --- |
| `official_source/through-2026-10-15/` | Archived official pages, ordered transcript rows, provenance, and collection manifest |
| `api_extraction/official-through-2026-10-15/` | Identity extraction checkpoints, progress, errors, review pages, and exports |
| `…/auxiliar/periodistas_v2_all_years.parquet` | Original normalized daily reporter/outlet combinations |
| `…/auxiliar/journalist_media_evidence.parquet` | Explicit introduction evidence; repeated same-day evidence retained |
| `…/auxiliar/journalist_media_mapped_records.parquet` | Original identification records with reviewed mappings; raw items retained |
| `…/auxiliar/periodistas_v2_all_years_dedup.parquet` and `journalists_and_media_dedup.csv` | Harmonized daily identity combinations |
| `…/auxiliar/manual_alias_audit.csv` and `manual_dedup_counts.csv` | Mapping changes and before/after counts |
| `…/auxiliar/reviewed_dated_attendance_links_20261026.csv` | Approved outlet/date/raw-attendance-label links |
| `transcript_analysis/official-pilot-10/` | Completed official speaker and question–answer pilot |
| `transcript_analysis/official-full/` | Incomplete 221-date extension; inspect progress and export scope separately |
| `question_alignment/official-pilot-10/` | Question-only alignment coding and review interface |

The question–answer pilot separates speaking turns, speaker registry, question/request/opinion items, responses, and a many-to-many question–response link table. The president can answer several items in one response; an item can link to several responses. Adjacency is stored separately from thematic linking. Source spans and review flags preserve auditability.

The current `official-full/auxiliar/corpus_report.json` contains 1,133 speaking turns, 476 question/request/opinion items, 471 responses, and 576 links across ten exported dates. Of the 476 items, 454 are questions/requests and 22 are opinions; 357 questions have a linked presidential response. The completed official pilot reports 47,924 live presidential words. These counts must not be extrapolated to 503 conferences.

The broader run stopped on exhausted credits and records eight source-span/order validation failures. Its `run_progress.json` reports 114 completed dates, whereas the saved export remains the ten-date pilot. Resume/review/export is pending. Emotion, anger, dismissal, response style, topic prevalence, and preparation/coordination measures are not completed corpus variables. The user explicitly excluded a separate question-function variable. Preparation evidence, such as ready material, must not be coded as proof of scripting by itself.

## Outlet decisions and attendance reconciliation

The comparison window is **2024-10-01–2025-09-30**. Later transcript dates are outside that attendance snapshot. A missing label or sparse/missing roster is not evidence that the journalist was absent.

The final flagged review records 15 approved groupings, 73 minimal brand additions to each source metadata workbook, and 28 validated date-specific links. Unknown ownership/legal fields remain blank. Physical attendance rows and raw introduction records were preserved. Existing metadata IDs were retained, with ABC Radio appended separately from unrelated ABC newspaper identities.

Authoritative review files:

- [Decision registry](../info_newspapers_gpt/outlet_review_20261026/decisions.json): approved groupings, exact aliases, rationale, and exclusions.
- [Review results](../info_newspapers_gpt/outlet_review_20261026/review_results.json), [reviewed dates](../info_newspapers_gpt/outlet_review_20261026/reviewed_question_dates.csv), and [dated links](../info_newspapers_gpt/outlet_review_20261026/dated_question_attendance_links.csv).
- [Attendance aliases](../info_newspapers_gpt/attendance_aliases_20261016.tsv) and [question aliases](../info_newspapers_gpt/question_aliases_20261016.tsv): executable linkage inputs.
- [Manual R rules](../code/03-cleaning_conf/question_class/sheinbaum/05_deduplicate_outlets_periodistas.R) and [metadata helpers](../src/metadata_helpers.R).

| Shared conference ID | Approved brands/labels |
| --- | --- |
| medios digitales del pacifico | sin puntos ni comas; medios digitales del pacifico |
| movimiento conciencia | movimiento conciencia; animales con derechos; sendero de la luna |
| sonora power | sonora power; lobos cadena 7 |
| comunicante mx | comunicante mx; alerta multimedia |
| agua quemada | agua quemada; los tubos; revista posdata; el portal del noreste |
| grupo tribu | grupo tribu; cultura colectiva; ecosfera; el fildeo |
| grupo imagen | grupo imagen; excelsior |
| global energy | poder mexico; global energy |
| efecto colateral | efecto colateral; el chapucero |
| universidad de guadalajara | universidad de guadalajara; red periodistica de puerto vallarta |
| amarc | amarc; politica y rock radio |
| alcanzando el conocimiento | alcanzando el conocimiento; el regreso de donald trump |
| nopal times | nopal times; el charro politico |
| el financiero | el financiero; bloomberg news; bloomberg linea |
| audiorama | asi lo dice la mont; abc radio; audiorama; grupo audiorama comunicaciones |

Earlier reviewed combinations also remain active: Mexico News World / Marco Olvera Oficial / Hidalgo News; Sin Línea / El Político en las Redes; Tiempo / Puente Libre; W Radio / Teleurban / Radiópolis; Jaime Farías Informa / Frecuencia CAD / Es Ahora AM; and Oro Sólido / Empuje Migrante. Grupo Transmedia La Chispa is a combined name. All ACI variants are grouped; the existing internal key is retained. Chiwas News follows the approved Efecto Colateral assignment.

Keep separate globally: TV Migrante and Canal 14; SandraAguilera.com and Larsa; Miled and Perspectivas; 10 AM MX and Jaime Farías Informa. Approved dated co-affiliation links do not create a blanket merger. Judith Sánchez Reyes's 11 Miled/Perspectivas links do not change Norma Ramírez's Miled affiliation. Generic CANAL 44, unspecified Bloomberg, and unrelated ABC brands are not automatically assigned to the reviewed groups.

Corrections also prevent El Popular from matching POPLab, Claudia Reina/Reyna from matching Reyna Haydeé, AP Noticias from matching Associated Press, Ágora Celaya from matching Ágora Digital, and Abel Cuapa's Capital Puebla from matching Capital 21.

The updated local review workbook is `outputs/sheinbaum-roster-20261019/sheinbaum_outlet_attendance_review.xlsx`. The published source masters live in `MEDIA_ROOT/data/00-newspaper_data/`; clean attendance and its bridge are under `MEDIA_ROOT/data/02-conferences/raw/attendance/merged/`, and AMLO question deduplication under `MEDIA_ROOT/data/02-conferences/auxiliar/`. These files are local data, not Git deliverables. Latest publication backups/hashes are under `recovery/flagged-outlets-20261026/published-lamont-audiorama/`.

All 130 original flags remain traceable; reviewing the whole list does not mean every date was matched. Several labels share one conference ID, so their review rows must not be added together as independent outlet totals.

## Other project work included

- Metadata-aware panel assembly and source coverage helpers; descriptive statistics, monthly attendance/questions, and outlet ranking workflows in `code/07-final_panel/`.
- YouTube reviewed-outlet extraction, playlist backfill, text outcomes, and API-coverage diagnostics. Reported channel totals exceeding saved pagination are flagged rather than treated as complete coverage.
- Balance workflows with prior histories, missingness rules, separate metadata/history checks, subgroup/period comparisons, and publication tables. See the [specification](../code/08-results/balance/BALANCE_TESTING_SPEC_DRAFT.md) and [dictionary](../code/08-results/balance/VARIABLE_DICTIONARY.md).
- Daily/weekly effect-of-asking models, ideology interactions, clustered and wild-bootstrap inference, outcome transformations, and FEct extensions. [The dedicated handoff](../code/08-results/01-effect-of-asking/HANDOFF.md) distinguishes completed outputs from the in-progress earlier full-calendar extension.
- Selected Overleaf tables/figures. Conference-video descriptives use title **or** description matching by default. Saved engagement counters are cumulative counters on videos published in a month, not engagement received during that month.

These source changes and existing publication artifacts are preserved without rerunning regressions. Their saved outputs are not represented as refreshed for the latest identity rules.

## Validation and next steps

Consolidation checks: 50 Python unit tests across the AMLO scraper, Sheinbaum identity extraction, transcript pilot, and project tests; 12 R test scripts covering outlet linkage, role filters, histories, and saved balance results. All passed. Saved-output tests validate the existing snapshots; they do not replace a panel rebuild. All 72 changed/new Python files and 83 R files passed syntax checks. Staged diffs passed whitespace checks; TSV trailing delimiters are retained as missing fields. No credential-shaped values were found in the candidate files.

Next substantive work:

1. Resume and review the incomplete speaker/question–answer run, then export a clearly scoped dataset before extending it to later conferences.
2. Review the remaining unmatched attendance dates individually; preserve missing-roster and outside-coverage statuses.
3. When authorized, rebuild processed metadata/panels and downstream reports with the reviewed mappings, checking entity/date uniqueness and source coverage.
4. Continue human alignment review, then pilot preparation/coordination and response-style measures with a small codebook.
5. Return to AMLO source date gaps and extraction refresh separately.

Use the normal source workflows for future updates. The dated `scripts/stage_*`, `standardize_*`, and `publish_*` tools are historical migrations tied to backups and intermediate files; see [scripts/README.md](../scripts/README.md) before reusing them. Credentials, raw data, checkpoints, generated bulk outputs, and recovery backups remain outside Git.

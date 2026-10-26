# Project utilities and dated outlet migrations

The October 2026 outlet utilities document the reviewed changes to source
metadata, attendance identities, and question identities. They are not a
single fresh-clone build pipeline. The current decisions and evidence are
versioned in `info_newspapers_gpt/outlet_review_20261026/`; local data and
recovery snapshots remain outside Git.

## Routine entry points

- Official transcript and journalist extraction: follow
  [the Sheinbaum README](../code/03-cleaning_conf/question_class/sheinbaum/README.md).
- Manual harmonization: review
  `code/03-cleaning_conf/question_class/sheinbaum/05_deduplicate_outlets_periodistas.R`
  with `WRITE_OUTPUT <- FALSE` before deliberately exporting.
- `audit_sheinbaum_outlet_roster.py` compares recorded identities, roster
  coverage, and metadata; inspect its configured paths and period before use.
- `export_reviewed_youtube_parquet.R` is an output conversion utility for the
  reviewed YouTube extraction; it is separate from transcript harmonization.
- `Rscript tests/test_reviewed_outlet_linkage.R` checks approved mappings,
  exclusions, separate brand identities, and stable metadata IDs without
  rebuilding production panels.

## Historical migration families

`standardize_*`, `stage_*`, `verify_*_workbooks.py`, and `publish_*` scripts
record the Mexico News World, Sin Línea, Puente Libre, Teleurban, Frecuencia
CAD, and Empuje Migrante changes. `prepare_flagged_*`,
`apply_flagged_outlet_rules.py`, `build_flagged_review_results.py`,
`stage_flagged_outlets.R`, and the flagged-workbook tools record the subsequent
full review. `publish_bloomberg_linea.py` and `publish_lamont_audiorama.py`
record the final two follow-up decisions.

These scripts use dated local folders and, in several cases, absolute machine
paths. Staging requires the original extraction/source masters and the matching
backup snapshot. Some review operations also require `/tmp` exports such as
`sheinbaum-current-mapped.csv`, `attendance-current-clean.csv`, and
`attendance-original.csv`. Those files are not supplied by a fresh checkout.
Local `outputs/flagged-outlets-20261026/decisions.json` was the working copy;
the final reviewed copy is now tracked under `info_newspapers_gpt/`.
The initial preparation script only seeds the earliest four groups if its
working copy is absent. It is not a way to reconstruct the final 15-group
registry. Use the final registry when preparing a new migration.

The workbook authoring source is preserved as `edit_flagged_workbooks.mjs`
(originally run from the ignored output folder). It requires Node with
`@oai/artifact-tool`, the dated original XLSX backups, and the generated
`workbook_patches.json`. Its preview/edit modes render review images and stage
edited workbooks; they do not reconstruct missing backups or patch manifests.
Formula/row/metadata verification precedes publication. The original runs
preserved 129 existing formulas and physical attendance row counts.

Publisher scripts replace the explicitly listed local data files after
verification and save backup/hash manifests. Do not replay an older publisher
over newer data: its snapshot may precede later manual decisions. For future
changes, prepare a new dated stage and verify the delta against current files.
The latest backup manifest is
`recovery/flagged-outlets-20261026/published-lamont-audiorama/manifest.json`.

`rebuild_sin_linea_reports.R` and `render_sin_linea_reports.py` are historical
report-generation steps. They are not part of the current documentation/git
consolidation. Panel and processed-metadata rebuilding remains deferred.

See [the project recap](../docs/PROJECT_STATUS_2026-10-26.md) for completed
decisions, unresolved attendance dates, dataset units, and current run status.

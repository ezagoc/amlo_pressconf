# Initialization Handoff

## Sheinbaum alignment heterogeneity — October 26, 2026

Completed pooled aligned versus opposition+independent interactions, matching
AMLO's combined specification. Scripts 03/04 in `code/08-results/05-sheinbaum-main/`.
Six upper-p99 log1p outcomes, baseline/quarter-history adjustment, shared date
and outlet FE, main-sample caps unchanged; 36 null-imposed 9,999-draw wild tests.
Sample 5,221 rows / 80 outlets / 161 dates: 30 aligned and 50 comparison outlets,
583 identified-speaking days and all 1,230 zero-video days retained.
Eight missing and six conflicting classifications excluded under the AMLO rule;
full list is in the report. Independent label corresponds to registry `unclear`.

No adjusted difference is statistically detectable: difference wild p=.852
(videos), .999 (interactions), .898 (mean interactions), .881 (likes), .303
(comments), .867 (views). Do not infer equality from imprecise estimates.
Report: `output/pdf/sheinbaum_heterogeneity.pdf`. Models/HTML/audits in main
results subfolder `pooled_interactions_combined/`. Validation passed independent
coefficients, group-slope reparameterization, classifications/sample and all
359,964 bootstrap draws. Original pooled-main outputs remain unchanged.

## Sheinbaum main regressions — October 26, 2026

Completed the user's next step: main pooled daily YouTube results. Entry point:
[main workflow](code/08-results/05-sheinbaum-main/README.md). Copied AMLO's six
upper-p99 log1p outcomes, outlet/date FE, baseline and prior-AMLO-ratio-by-quarter
adjusted models, plus 9,999-draw outlet wild-bootstrap inference. Uncapped log1p
sensitivity uses the same rows. No new FEct/heterogeneity/event study here.

Sample: 6,228 rows / 94 outlets / 163 dates after two singleton outlets; 683
identified speaking days. All 1,387 zero-video days remain. Every outcome/model
uses identical rows. Adjusted coefficients are positive but all wild p>.05:
videos .330, interactions .157, mean interactions .151, likes .206, comments
.219, views .063. Baseline views are marginal (wild p=.049). Interpret as
conditional associations with an identification proxy and later engagement
snapshots, not established causal effects. Both model variants validated.

Data/models/HTML: `MEDIA_ROOT/results/sheinbaum/main_results/lottery-through-2025-06-15/`.
PDF: `output/pdf/sheinbaum_main_results.pdf`. Scripts 01/02 in the new folder;
`tests/test_sheinbaum_main.R` independently checks coefficients, sources,
singleton exclusions, caps and all 119,988 saved bootstrap draws.

## Sheinbaum balance / current YouTube data — October 26, 2026

Start at [the new workflow](code/08-results/04-sheinbaum-balance/README.md).
User explicitly corrected the added YouTube archive-completeness restrictions:
**follow the original `04-build_panel.py` balanced-calendar construction**.
`09-build_extended_panel.py` now creates every channel/day, aggregates recovered
videos and counters, fills no-video days and missing counters with zero, and
uses all recovered videos as per-video denominators (zero if no videos).
Archive completeness is diagnostic only. Never drop a date because no video
was published or an archive interval is incomplete. Only channels with no
recovered videos anywhere in the entire period are excluded, as in the original.
Sources extend through 2026. Current panel: 189 channels x 3,213 days = 607,257
rows, January 1, 2018–October 18, 2026; 1,640,344 unique dated recovered videos.
Legacy AMLO source/results remain unchanged; use `youtube/extended/` for current
Sheinbaum analysis. Outlet aggregation: 125 canonical outlets x 3,213 days in
`output/balance/sheinbaum_12m/youtube_outlet_daily.parquet`.

Attendance analysis stays October 1, 2024–June 15, 2025 (user lottery cutoff);
last observed conference June 13. Full balance: 162 outlets / 164 dates;
YouTube-linked: 96 outlets / 163 dates / 6,230 outlet-days, including 1,387
zero-video days. All nine YouTube history measures have 96 outlets. Prior AMLO
ratio remains 85 and contracts 61 in the full sample. Earlier 48/89-outlet
history/YouTube-sample results were artifacts of the rejected completeness rule
and are superseded. Keep later source attendance records outside this sample.
Exposure is explicit transcript identification, a speaking proxy, not exhaustive
question coding. Nine metadata and twelve prior-year histories, separate joint
tests. Report and audits: `output/balance/sheinbaum_12m/`; PDF:
`output/pdf/sheinbaum_balance_12m.pdf`. Main regressions are now completed above.

## Attendance eligibility tightened — October 26, 2026

User confirmed keeping REPORTERO and YOUTUBER only (clear variants and REPORTETO
typo allowed), excluding all other cargos. Shared policy is in
`src/attendance_roles.R`; attendance role counts use the same grouping helper.
The restriction removes 1,142 earlier physical rows; Sheinbaum's 13,277 eligible
rows and transcript participation remain unchanged. Actual speaking evidence
must not be deleted based on an outlet-level roster role. See the
[participation workflow](code/08-results/03-sheinbaum-participation/README.md)
for role details and validation. All affected panels were rebuilt and validated
in `outputs/panel-rebuild-20261026T211402Z/`; original derived files are backed up
under the matching `recovery/` directory. Historical models have not been refit.

## Panel rebuild completed — October 26, 2026

The user subsequently authorized rebuilding panels and starting analysis.
See [the rebuild record](docs/PANEL_REBUILD_2026-10-26.md) and
[Sheinbaum participation workflow](code/08-results/03-sheinbaum-participation/README.md).
Metadata, attendance, historical final/source panels, and a separate Sheinbaum
participation panel are rebuilt and validated. Earlier deferral notes below are
superseded. The analysis measures explicit identification days; the 503-date
question–answer analysis is still incomplete. No historical models were refit.

## October 26, 2026 consolidation

Start with [the verified project recap](docs/PROJECT_STATUS_2026-10-26.md).
It supersedes historical progress notes below for transcript and outlet status.
All 503 official-source journalist/outlet dates are complete through October 15,
2026. The distinct speaker/question–answer run is incomplete: 114/221 dates in
its progress file and only ten dates in its published export. All 130 outlet
flags have been reviewed; unresolved attendance dates remain explicitly marked.
Latest grouping: La Mont / ABC Radio / Audiorama, plus El Financiero / Bloomberg
News / Bloomberg Línea. Preserve separate brands and physical attendance rows.
The user authorized documenting, committing, and pushing all current project
changes. Panel/processed-metadata rebuilding remains deferred.

## Current FEct extension — in progress

User confirmed ALL six all-video outcomes on the EARLIER full-calendar panel
with attendance dummy, plus historical adjustment and upper-p99 asinh outcomes.
Scripts 18/19/20 under code/08-results/01-effect-of-asking/; details and checkpoints
in that folder's HANDOFF.md. 1,000 outlet bootstraps per fit; baseline/history
pairs. Preserve the earlier 165-entity Apr2022-Dec2024 calendar; not attendee-only.

## Conference-only YouTube descriptives — October 12, 2026

New script: code/08-results/02-descriptive-youtube/00-conference-trends.R.
Default --scope=title_or_description preserves the earlier OR definition;
--scope=title supports the title-only sensitivity. The user was asked which
definition they prefer; no answer had arrived when the default was produced.
Do not describe the default figure as title-only. Regex matches normalized
mananera(s), conferencia(s) [de prensa] matutina(s), or conferencia(s) mananera(s).

One 7.2 x 7.1-inch, six-panel figure, all outlets, whole months Oct 2020-Oct 2023
(same earlier 18-month-around-lottery month-rounded window). Panels: conference
videos; conference share of all videos; views; interactions; likes; comments.
Raw monthly lines/points in light blue, LOESS span .5 in dark navy, lottery
Apr 18, 2022 dashed line. No overall title, subtitle, or bottom note. No winsorizing
or regression transformations. A smoothed fit is descriptive, not a causal break.

Outputs:
- output/pdf/youtube_conference_monthly_18m_title_or_description.pdf and .png
- overleaf/figures/descriptive_stats/youtube_conference_monthly_18m_title_or_description.pdf
- MEDIA_ROOT/results/descriptive_stats/youtube_conference/ contains monthly
  .rds/.csv, coverage columns, source fingerprints, and each panel's raw/clipped
  smooth values. --plot-only checks fingerprints and reuses those aggregates.

Fresh counts reconciled monthly to the rebuilt text entity-day panel. Globally
unique video IDs, restricted to matched/observed skeleton entity-days, no metadata
expansion or ideology exclusions. Video counters are maxima across duplicate
snapshots, not sums. All 199 source files checked; two empty ID-less placeholders
skipped only after verifying zero rows. In the figure window: 478,057 all-topic
videos; 13,137 conference videos; pooled share 2.748%. Views reported for all
13,137; likes for 13,129; comments for 12,856. 289 videos miss any metric. Sum
observed counters, do not treat missing as genuine zero; monthly interactions
equal displayed likes plus comments. These are cumulative saved engagement
counters on videos published in a month, NOT engagement received in that month.
Monthly contributor counts are retained, so this is a pooled observed-output
trend, not a balanced fixed-outlet average. The PDF was rendered and checked.

## New YouTube effect-of-asking workflow — October 12, 2026

Start the next session at code/08-results/01-effect-of-asking/HANDOFF.md.
Latest: scriptsize reordered tables plus separate asinh and Chen-Roth x=0
versions of the six-outcome daily winsor99 models. Add --transform=asinh or
--transform=chen_roth_x0 to scripts 16/11/15; validate all with script 17.
The three PDF stems append _asinh and _chen_roth_x0 to the winsor99 report;
all are in output/pdf/. Order is videos, total interactions, mean interactions
per video, likes, comments, views. All 144 wild tests validated across variants.
Newest tables add videos, interactions, and mean interactions per video, with
ALL SIX raw outcomes upper-capped at pooled-sample p99 BEFORE log1p. Run 16,
11 --pooled --winsor99, 11 --winsor99, and 15 --winsor99. Original files preserved.
Final: output/pdf/effect_of_asking_daily_regression_tables_winsor99.pdf (2 pages).
Latest deliverable: DAILY pooled-main and combined-interaction regression tables,
with clustered SEs and both clustered/wild-bootstrap p-values. Script 15 exports
the inclusion-ready LaTeX; script 11 --pooled adds six validated 9,999-draw main
tests. Preview: output/pdf/effect_of_asking_daily_regression_tables.pdf.
Latest check is WEEKLY: all usable weeks including partial conference coverage,
as explicitly requested. 3,683 outlet-weeks / 54 outlets / 110 weeks; wild
bootstrap completed. Run 13, 11 --weekly, 14, and 12 --weekly. Daily results
are preserved. Read the partial-coverage and calendar-week interpretation caveats.
Latest inference check: scripts 11/12 perform/report the null-imposed outlet
wild cluster bootstrap (9,999 draws) for the combined-group models. Results
remain nonsignificant; full diagnostics and report paths are in the handoff.
Latest comparison: Opp. + Independent versus Aligned in pooled interactions;
run scripts 09/10 with --combine. Separate outputs preserve the three-group model.
It documents the new recorded-attendee TWFE/history-adjusted regressions for
likes, comments and views, the sample/channel-coverage audits, and comparable
FEct robustness. New model outputs are under configured
MEDIA_ROOT/results/effect_of_asking/. Earlier balance and FEct fits are preserved.
The current MAIN heterogeneity analysis uses pooled asking-by-ideology
interactions with shared date FE and common history slopes (09/10 scripts;
pooled_interactions/ results). Separate opposition/aligned/independent models
remain sensitivity checks in heterogeneity/. The same handoff records results,
sample/support cautions, coefficient-difference tests and PDF/LaTeX exports.
The current styled balance table is now ONE compact centered scriptsize table
containing histories and metadata; the two-page description below is historical.

This repo contains code only. Data, generated outputs, checkpoints, figures, and large artifacts should stay under the Dropbox Media tree configured by `MEDIA_ROOT`.

## Latest: 12-month histories, separate metadata without age — October 12, 2026

- Publication-style preview/export follow-up: the currently open
  `overleaf/tables/balance/separate_12m_no_age/balance_histories.tex` now contains
  BOTH styled tables, histories on page 1 and metadata on page 2, with separate
  joint tests. Conditional standalone wrapper preserves inclusion with input.
  Built-in compilation and pdflatex export succeeded; both pages visually checked.
  Updated PDF: `output/pdf/balance_histories_12m_table.pdf` (despite its singular
  legacy filename, now two pages). No model changes. These manual publication
  styling edits are not yet encoded in exporter 15; rerunning that exporter would
  overwrite this styled source with the earlier plain table fragment.

- User shortened the historical window to ONE YEAR before the lottery:
  April 18, 2021–April 17, 2022. Full post-lottery recorded-attendee sample stays
  unchanged (7,976 outlet-days, 81 units, 318 dates); metadata without age unchanged.
- Scripts 14/15 now accept `--months=12` (default) or `--months=18`. Reuse audited
  existing window-specific histories and models, updating all historical rows,
  model objects, raw values, missingness maps and period labels consistently.
- Separate joint tests: metadata F(9,80)=2.992, p=.0040 (no missingness controls);
  histories F(12,80)=1.496, p=.1430 (3 missingness controls, not tested).
- Outputs `output/balance/separate_12m_no_age/`; report
  `output/pdf/balance_separate_12m_no_age.pdf`; two LaTeX fragments under
  `overleaf/tables/balance/separate_12m_no_age/`. Earlier 18-month files preserved.
- `tests/test_separate_balance_no_age.R --months=12` passes selected-history,
  coefficient/covariance, metadata invariance, sample and independent Wald checks.
  PDF has three visually checked pages and correct 12-month labels/results.

## Previous: separate metadata (no age) and histories — October 12, 2026

- User requested removing founding age until corrected and retaining TWO separate
  analyses/joint tests, not the combined model. Full post-lottery recorded-attendee
  sample and 18-month pre-lottery histories remain unchanged.
- Run `14-separate_balance_without_age.R`, then bundled Python
  `15-export_separate_balance.py` in `code/08-results/balance/`. Uses the audited
  snapshot from the prior run; no workbook reread or upstream mutation.
- Metadata: 9 flags, no history controls or missingness dummies; every individual
  row and joint model N=7,976, 81 units, 318 dates. F(9,80)=2.992, p=.0040.
- Histories: prior 12-variable model unchanged, with 3 missingness controls
  unrestricted/not tested. F(12,80)=2.670, p=.0046. Individual cohorts unchanged.
- New outputs `output/balance/separate_18m_no_age/`, PDF
  `output/pdf/balance_separate_18m_no_age.pdf`, and two caption/note-free LaTeX
  fragments `overleaf/tables/balance/separate_18m_no_age/balance_metadata.tex`
  and `balance_histories.tex`. Older age/combined outputs preserved as history.
- Geography still provisional as documented below. Age no longer depends on
  finding the user's updated workbook; revisit only when user requests it.
- `tests/test_separate_balance_no_age.R` passed; saved historical coefficients
  and covariance exactly unchanged, independent metadata Wald check passed.
  Three PDF pages visually checked with pypdfium2 (high-resolution page 3 also
  checked). Poppler still has broken fontconfig; avoid rerunning it unconfigured.

## Previous: full post-lottery, 18-month histories + metadata — October 12, 2026

- Latest user explicitly returned to the FULL post-lottery sample, not the
  January 2023 restriction. Reuses the established recorded-attendee base:
  7,976 outlet-days, 81 deduplicated units, 318 informative dates, actual
  April 19, 2022–September 27, 2024. Histories: October 18, 2020–April 17, 2022.
- Added `12-balance_18m_metadata.R`, `13-export_18m_metadata_report.py`, and
  `metadata_geography.R`. Run from repository root, then export using bundled
  Python. Source workbooks and upstream panels remain untouched.
- Outputs `output/balance/full_post_18m_metadata/`; four-page report
  `output/pdf/balance_full_post_18m_metadata.pdf`; caption/note-free fragments
  `overleaf/tables/balance/full_post_18m_metadata/balance_{histories,metadata,combined}.tex`.
- 22 individual day-FE balance tests, outlet-clustered; individual historical
  cohorts unchanged. Ten metadata variables: age as of 2022, print/newspaper,
  digital, social media, radio, TV, national/state coverage, Mexico City,
  metropolitan. Shared metadata members collapsed before joining daily rows.
- PROVISIONAL: user said founding years were updated, but the canonical workbook
  (mtime September 28) has zero changes versus the processed snapshot. Downloads
  copy (September 17) has identical founding values too. Asked user for the saved
  revision's path. Do not claim this report incorporates unlocated new dates.
- PROVISIONAL geography: city.headq=9 for Mexico City; explicit metropolitan
  coverage.scope token for metropolitan, NOT Mexico City metro HQ. Asked user
  whether geographic covariates should describe HQ or coverage. Await reply.
- Age uses unambiguous four-digit years <=2022; conflicting subsidiary years
  remain NA. 32/81 units have known consensus age, 28 remain in informative
  age-regression dates (N=1,272). Binary attributes use any member positive,
  missing->0 as previously requested. National/state use whole-word matches
  locally, avoiding international/multistate substring false positives.
- Joint tests leave missingness coefficients unrestricted: histories
  F(12,80)=2.670, p=.00457; metadata F(10,80)=2.535, p=.0104; combined
  F(22,80)=1.779, p=.0333. 3/1/4 missingness controls respectively. The joint
  covariance remains ill-conditioned (~9e7 combined); do not overstate inference.
- `tests/test_18m_metadata_balance.R` passes independent Wald calculations,
  age/geography coding, no duplicate days, original history/coefficient invariance.
  Script checks centered-placeholder invariance too. Four PDF pages visually
  inspected via pypdfium2. Updated founding-file/geography answers require rerun.

## Previous: January 2023 through end of AMLO tenure — October 12, 2026

- User requested January 1, 2023–September 30, 2024. Attendance and question
  source panels were checked directly: September 28–30 have unobserved flags
  in both sources. September 27 is the final usable date; no zero imputation
  of these missing final dates. `end_date_coverage.csv` preserves the audit.
- Run `10-subgroup_balance.R --from-2023`, then
  `11-export_subgroup_pvalues.py --from-2023`. New mutually exclusive variant
  preserves the full-period and second-year runs. If later source dates become
  observed beyond the saved baseline sample, this variant stops and requests
  a rebuild instead of silently truncating them.
- Histories, subgroup definitions and models are unchanged: 288 individual
  tests and 24 historical joint-test attempts. Pre-history cutoff remains
  April 17, 2022. Recorded-attendee restriction, within-group/date variation,
  date FE, missingness controls in joint models, outlet-clustered inference.
- Pooled joint sample: 5,420 outlet-days, 79 units, 217 dates. Raw p-values
  (12m/18m/24m/full): .220/.0722/.0106/.0342. These are unadjusted values.
  Pooled participation differences: .134/.174/.160/.172, p=.0235/.0566/.0847/.0759,
  on 4,941 outlet-days, 69 units, 206 dates.
- Digital joint p=.429/.118/.0139/.297. Print, aligned and independent joint
  p-values all <.001, with the existing small-sample/correlated-measure caveats.
  Opposition has nine units/158 outlet-days; all four full joint tests are NE.
- Outputs: `output/balance/from_2023/`, LaTeX fragments in
  `overleaf/tables/balance/from_2023/`, report `output/pdf/balance_from_2023.pdf`.
  Seven pages compiled without layout warnings and visually checked.
  `Rscript tests/test_second_year_balance.R --from-2023` passes date, frozen
  history, source-end coverage, coefficient and joint-Wald checks.

## Previous: second post-lottery year — October 12, 2026

The user clarified and confirmed **April 18, 2023–April 17, 2024**, NOT the first
year after implementation. Only the post-period restriction changes; all four
historical windows still end April 17, 2022. No covariates rolled forward.

- `10-subgroup_balance.R --second-year` reuses saved histories and metadata,
  filters dates, and refits pooled + five subgroup specifications. Individual
  tests use observed-data cohorts common across historical windows; joint
  tests retain missing histories with indicators. Recorded attendees only;
  require within-group/date variation in asking; day FE and outlet clustering.
- `11-export_subgroup_pvalues.py --second-year` exports separate caption-free
  p-value fragments under `overleaf/tables/balance/second_year/` and a seven-page
  report wrapper. Full-period outputs remain untouched; defaults still target
  the original full-period subgroup workflow.
- Results: `output/balance/second_year/` (288 individual tests with estimates,
  SEs/CIs/p-values, 24 joint attempts, membership, period dates, models/audits).
  Report: `output/pdf/balance_second_year.pdf`, all seven pages rendered and
  visually checked, no LaTeX layout warnings. Main page joint p-values plus
  individual-variable p-value pages for pooled, print, digital, aligned,
  opposition, and independent/unclear.
- Pooled joint sample: 2,735 outlet-days, 71 units, 109 informative dates.
  Joint p-values (12m/18m/24m/full): .133/.312/.0784/.0664; none rejects at 5%.
  Pooled participation-ratio sample: 2,529 outlet-days, 63 units, 105 dates.
  Positive differences .149/.193/.167/.190, with p=.0456/.0935/.150/.114.
- Digital joint p-values .253/.429/.122/.264. Print, aligned and independent
  joint tests all p<.001 but remain exploratory with small groups and strongly
  correlated regressors. Opposition has nine clusters/69 outlet-days and all
  four full joint tests are NE; no reduced hypothesis substituted.
- `tests/test_second_year_balance.R` passes: exact date restriction, same frozen
  histories, 288 individual coefficient/p-value checks, joint sample/NA coding,
  direct full-null Wald calculations and re-centering numerical checks.
  No first-year analysis was generated during the interrupted/corrected request.

## Previous: joint-test footers and subgroup p-values — October 12, 2026

- User requested compact `F(df1,df2)=F; p=p` joint-test footers on the published
  tables and subgroup reports containing only p-values. Script 09 now adds the
  four historical-only F-tests beneath the individual table. Its separate joint
  fragment is simplified to the same compact block. Pooled fits are unchanged;
  Holm p-values remain available in the earlier reports/data, not these footers.
- New `code/08-results/balance/10-subgroup_balance.R` uses saved unit metadata:
  print/newspaper = media_print_any; digital = media_digital; aligned/opposition
  = respective ideology flags; independent = ideology_4t_unclear. These are
  the existing definitions. Print/digital overlap; independent is not verified
  independence. La Jornada and Sonora Power have conflicting ideology and are
  excluded from the political groups, not arbitrarily assigned.
- Re-estimates 240 individual tests (12 variables x 4 windows x 5 groups) and
  attempts 20 full historical joint tests. Recorded attendees only, date FE,
  source-unit clustering. Keep only dates with askers AND nonaskers within each
  subgroup. Individual tests preserve script 05's common-window observed-data
  cohorts; joint tests use missing indicators within each group/window.
- Joint subgroup samples: print 25 units/1,463 outlet-days; digital 70/5,381;
  aligned 29/1,878; opposition 9/224; independent 37/1,213. All individual
  p-values available. Opposition's 12-restriction clustered joint test is NE
  (too few clusters); no reduced null or generalized-inverse p-value substituted.
- Other joint tests pass positive-eigenvalue and machine-tolerance rank checks
  on covariance correlation matrices, direct Wald verification and observed-
  value recentering invariance (relative F difference <= 1e-5). Default qr(V)
  rank with tolerance 1e-7 was scale-sensitive and spuriously flagged some
  nonsingular matrices. Small samples and covariance condition numbers up to
  about 6e9 still warrant caution; these are exploratory, unadjusted tests.
- Joint p-values (12m,18m,24m,full): print 1.90e-9,9.08e-10,4.40e-9,1.22e-6;
  digital .2349,.00967,.00232,.0302; aligned 3.74e-11,2.00e-6,1.62e-15,4.02e-14;
  opposition all NE; independent 5.12e-8,5.63e-9,1.98e-9,5.14e-7.
- `11-export_subgroup_pvalues.py` creates caption/note-free subgroup LaTeX
  fragments in `overleaf/tables/balance/subgroups/`. Main report includes a
  short definitions/cautions page, then five p-value-only subgroup tables.
- Outputs: `output/balance/subgroups/` (models, full-precision results,
  membership, numerical audits); `output/pdf/balance_subgroup_pvalues.pdf`
  (six pages); updated `output/pdf/balance_latex_tables_preview.pdf` (two pages).
  Both compiled without layout warnings; all eight pages visually checked.
  `tests/test_subgroup_balance.R` and updated `tests/test_balance_latex.py` pass.
  Prior individual/joint pooled estimates and outcome models remain unchanged.

## Previous: publication balance tables and interpretation — October 11, 2026

The user requested clean LaTeX individual-variable and historical-only joint
balance tables, with no titles/captions or notes. Saved under
`overleaf/tables/balance/`:

- `balance_individual_histories.tex`: all 48 saved one-variable day-FE contrasts,
  asking minus nonasking, with individual 95% CIs. Four window columns and
  participation/contract/YouTube groups. Uses script 05's observed-history
  samples (7,441 / 3,925 / 5,308 outlet-days); no NA-to-zero change.
- `balance_joint_histories.tex`: script 07's four primary tests only, testing
  12 historical coefficients while allowing three missingness coefficients to
  be unrestricted. Includes F, p, Holm p, sample sizes, controls and within R2.
  Omits the broader histories-plus-missingness joint tests.
- `balance_interpretation.tex`: separate prose draft describing persistent
  participation patterns; willingness/motivation is a possible interpretation,
  not measured directly. Explains that joint rejection cannot be attributed
  exclusively to participation and that adjustment is not proof of conditional
  random assignment. Retains the YouTube engagement snapshot timing caveat.

Exporter: `code/08-results/balance/09-export_balance_latex.py`; no re-estimation.
Fragments require `booktabs`, have no table float/caption/note or star legend,
and are ready for `\input{tables/balance/...}` from the Overleaf root. Table
labels/captions, if desired later, belong to the surrounding paper environment.
Two-page multi-file preview: `output/pdf/balance_latex_tables_preview.pdf`.
Compile its `.tex` wrapper in `output/balance/latex/` from the repo root with
TinyTeX pdflatex, then copy the PDF from `tmp/pdfs` to `output/pdf`. The preview
was rendered and visually checked; compile has no overfull/underfull warnings.
`tests/test_balance_latex.py` checks all saved estimates/CIs, four primary joint
tests and formatting constraints; passed. Existing model outputs are unchanged.

Important next-step limitation: the current FEct model has outlet fixed effects,
which absorb histories frozen before the lottery. Adding these as standalone
levels does NOT implement further adjustment. A prespecified history-by-time
interaction or another explicit design must be agreed before fitting new outcome
models. No conditional outcome model was implemented in this presentation turn.

## Previous: four all-measure joint tests with missingness — October 11, 2026

The user approved four joint tests, one per historical window, after checking
that a single all-window model was numerically problematic. New entry points:
`code/08-results/balance/07-joint_balance_by_window.R` and
`08-export_joint_window_pdf.py`. They consume the NA-preserving script 05 outputs
and saved recorded-attendee sample from script 03, without changing either.

- Each regression: asked-question ~ all 12 historical measures for ONE window
  + three distinct missingness indicators | date. Cluster SEs by source unit.
  No metadata predictors. All four use the same 7,976 outlet-days, 81 units,
  318 dates and 428 asking outlet-days, April 18, 2022–September 27, 2024.
- Raw histories retain NA. For estimation only, histories are divided by their
  observed outlet-day SD and missing entries replaced by zero; indicators mark
  missing access ratio, contracts, and YouTube. Identical missingness patterns
  appear only once. No missing indicators from other windows enter a model.
- Primary null: all 12 historical coefficients zero, conditional on unrestricted
  missingness coefficients. F(12,80), raw p, and four-test Holm p:
  12m: 1.49621 / 0.142968 / 0.149380;
  18m: 2.67026 / 0.004574 / 0.013721;
  24m: 3.43656 / 0.0004293 / 0.001717;
  full: 1.73437 / 0.074690 / 0.149380.
- Supplementary null: all 15 history AND missingness coefficients zero.
  F(15,80) = 2.97998, 4.77877, 5.19721, 3.52737; all p < .001.
  These broader tests may reject because of missing-data status, not just values.
- Each model and clustered covariance retain rank 15. Correlation condition
  numbers remain high (3.9e7–1.5e8); results remain exploratory, especially
  individual coefficients. All coefficients were independently recovered via
  within-day demeaning; all eight Wald tests checked directly; recentering
  observed histories preserved fitted values and both joint tests.
- `Rscript tests/test_joint_balance_by_window.R` passes. Outputs and saved
  models: `output/balance/joint_by_window/`. PDF:
  `output/pdf/balance_joint_by_window.pdf` (two pages, rendered and checked).
  Previous reports are preserved. The YouTube snapshot timing limitation and
  pending transcript-attribution corrections remain applicable.

## Previous balance extension: contracts and YouTube — October 11, 2026

The user's latest request extends the ratio-only historical-window exercise to
contracts and YouTube, without restoring metadata predictors. Earlier analyses
are preserved. Run `code/08-results/balance/05-historical_outcome_balance.R`
after `03-prior_ratio_balance.R`; export with
`06-export_historical_outcomes_pdf.py` using the bundled Python runtime.

- Histories: prior 12, 18, 24 months and available presidency history from
  December 1, 2018; all end April 17, 2022. Recorded-attendee post sample remains
  April 18, 2022–September 27, 2024, with informative within-day comparisons.
- Measures: question/recorded-attendance ratio; contract value and count;
  YouTube videos, views, likes, comments, interactions, and the four engagement
  totals divided by window video count. Interactions = likes + comments.
- The ratio stays raw; contract/YouTube measures use log(1+x), no winsorization.
  Each company/channel is counted once per source unit, despite metadata repeats.
  Latest correction: unmatched/unobserved contract histories remain NA, restoring
  `history_sum()` from the original baseline definition; matched, observed
  beneficiaries with no awards in a window retain zero. Multi-beneficiary sums
  use available observed histories. Matching is not an eligibility measure.
  Known YouTube calendar
  grids with zero posts use zero; unmatched/incomplete grids remain missing.
- Individual models: history ~ asked-question | date, clustered by source unit.
  Joint models: asked-question ~ four windows of ONE measure | date, with each
  history divided by its sample SD. Twelve separate joint tests, not one combined
  all-outcomes model. Windows use identical samples within each measure.
- Samples: access ratio 7,441 outlet-days / 71 units / 305 dates; contracts
  3,925 / 46 / 224; YouTube 5,308 / 60 / 258. Contract joint p-values are
  0.000000184 (value) and 0.000729 (count); YouTube joint p-values range
  0.321–0.839. Nonsignificance is not proof of balance or random access.
- Important: YouTube engagement is a saved snapshot for videos published before
  the cutoff, NOT verified engagement measured before the lottery. These checks
  are descriptive, not established pre-treatment covariate tests. Archived
  calendar coverage also does not prove complete historical scraping.
- November 2021 is excluded from the access ratio only, retained for contracts
  and YouTube. Five ambiguous attendance/question mappings remain excluded;
  pending transcript attribution corrections are not applied. Results provisional.
- Outputs: `output/balance/historical_outcomes/` (raw histories, link audits,
  definitions, individual and joint results, saved models, report, session info).
  PDF: `output/pdf/balance_historical_outcomes.pdf`, five pages, rendered and
  visually checked. These follow the existing local balance-output convention.
- Validation: `Rscript tests/test_historical_outcome_balance.R` passes checks
  for deduplicated assets, cutoff dates, window sums, per-video aggregation,
  all 48 individual coefficients, 12 joint Wald tests, and prior-ratio agreement.
  The added NA-versus-observed-zero checks pass; all non-contract estimates are
  identical to the preceding run. All five updated PDF pages were visually checked.
- The prior zero-imputed extension, PDF and scripts are preserved under
  `output/balance/historical_outcomes_before_contract_na_20261011/`.
  This correction changes the active historical-outcomes extension only;
  earlier metadata-balance results/scripts remain archived or unchanged and
  should not be mistaken for the corrected specification.

## Local Setup

1. Copy `.env.example` to `.env`.
2. Set `MEDIA_ROOT` to the local Dropbox Media folder for this machine.

Examples:

```text
MEDIA_ROOT=C:\Users\Dell\Dropbox\Media
MEDIA_ROOT=D:\Dropbox\Media
MEDIA_ROOT=/Users/name/Dropbox/Media
```

3. Add API secrets only in `.env` or the shell environment:

```text
OPENAI_API_KEY=
YOUTUBE_API_KEYS=
```

`YOUTUBE_API_KEYS` can contain one key or multiple keys separated by commas.

## Path Convention

Python scripts should use:

```python
from project_paths import media_path, media_input_path, media_output_path
```

R scripts should use the correct relative source path to the repo helper, for example:

```r
source("../../project_paths.R")
```

Then build paths with:

```r
media_path("data", "folder", "input.csv")
media_output_path("data", "folder", "output.csv")
```

Do not hardcode `C:\Users\Dell\Dropbox\Media` inside scripts.

## Current State

- Root `.env.example`, `.gitignore`, `README.md`, `requirements.txt`, `project_paths.py`, and `project_paths.R` are in place.
- Python/R/Rmd source files have been migrated away from hardcoded Dropbox paths where found.
- Notebooks may still contain old paths in saved cells and outputs; treat them as exploratory unless separately cleaned.
- Python files passed syntax compilation with the bundled Python runtime.
- R was not parse-tested here because `Rscript` was not available on PATH.

## Pipeline refresh, 2026-10-07

Rebuilt attendance, questions, processed metadata, the 2012-2025 final daily
panel, and all four deduplicated source panels. Refreshed descriptive scripts
03, 25, and 26 in `code/07-final_panel`; their four PDFs are in
`output/desc_stats` (the user's explicitly requested location).

- Run the attendance cleaner, question cleaner, and metadata builder first;
  then final-panel scripts 00 and 05, followed by descriptive scripts 03, 25,
  and 26. The cleaners now support `Rscript` from the repository root.
- `apply_reviewed_conference_keys()` in `src/metadata_helpers.R` applies the
  reviewed Reporteros/Quintana Roo and Grupo Sol matching keys after the
  workbook merge. The workbooks themselves were not edited by this refresh.
- Keep Mexico News World separate from The Mexico News and Mexico News Daily.
  Radio Tepoztlan maps to AMARC; regional Grupo Sol names precede the OEM rule.
- Later on 2026-10-07 the user explicitly confirmed a broad BCS grouping under
  Medios Digitales del Pacifico, not just the exact BCS Noticias label. Preserve
  their saved attendance `case_when` rule and its existing precedence; the
  question cleaner now also includes `bcs` in the Medios Digitales rule. Do not
  narrow this aggregation back to BCS Noticias without a new user request.
- Rebuilt again with that BCS rule. Script 27 now replaces count-based top-10
  charts with `questions_per_attendance_distribution_and_top10_changes.pdf`:
  distributions for the fixed common-date cohort, plus (as subsequently
  requested) the ten largest increases AND ten largest decreases side by side.
  Ties use combined attendance-days (descending), then name/ID. Counts and
  percentage-point changes are shown; this is descriptive, not a causal estimate.
  Distribution panels name every outlet with a ratio >=40% in that period;
  this is a descriptive threshold, not a formal statistical outlier test. The one-year
  windows and November-2021 exclusion in the ratio sample are unchanged.
  Script 26 retains legacy count charts only behind `--legacy-count-rankings`;
  run 27 after 26. Current audits are `top10_increases_decreases.csv` and
  `named_high_ratio_outlets.csv` in `output/desc_stats/outlet_lottery_tables`.
  The older `top10_ratio_changes.csv` describes the superseded pre-ratio ranking.
  Script 27 also overwrites the standalone distribution PDF with named labels.
- Removed Gini annotations from the ratio figures (scripts 26/27); the original
  audit statistic remains in `stats.csv`. Script 27 also produces
  `questions_per_attendance_distribution_opposition_aligned.pdf` (overlaid before/
  after distributions, opposition above aligned)
  and `questions_per_attendance_distribution_and_changes_opposition_aligned.pdf`
  (one page per group). At the user's explicit confirmation, opposition means
  `ideology_4t == "opp"`, NOT Opp. + Independent. Unique attendance-entity metadata
  supplies classification without duplicating subsidiaries; independent/unclear
  and unmatched entities are excluded. This leaves 15 opposition and 28 aligned
  outlets in the same fixed two-period cohort. Opposition has four increases,
  four decreases and seven unchanged; aligned has nine increases, fifteen
  decreases and four unchanged. Display up to ten strictly positive/negative
  changes within each group, not zero changes to fill ranks. Group distribution
  axes are shared; the >=40% naming threshold remains unchanged. New audit CSVs
  have the `_opposition_aligned` suffix, including all outlet-level changes.
  Latest layout overlays the same 5-percentage-point histogram bins with navy
  before and burgundy after (transparent fills, colored borders and median
  labels). Each group page now combines decreases and increases in one named
  before/after chart, retaining the same up-to-ten-per-direction selection,
  count labels and signed percentage-point changes. A dotted divider separates
  decreases from increases. Use script 27 `--groups-only` to refresh these two
  PDFs without re-exporting the unchanged all-outlet figures.
  For Overleaf, use the standalone single-page vector exports
  `questions_per_attendance_changes_opposition.pdf` and
  `questions_per_attendance_changes_aligned.pdf`: changes only, no distribution
  or title, with counts, period legend and signed percentage-point changes.
  Script 27 `--changes-only` exports just these two PDFs; the selected outlets
  and ratio definitions are unchanged. Heights scale with the number of rows.
- At the user's explicit direction, every Sin Censura date supplies at least
  one The Mexico News attendance. `src/attendance_coaffiliation.R` adds at most
  one missing target record per day, flagged `attendance_assumed`. This is a
  co-affiliation assumption, not a verified additional person. Physical
  conference totals and script 25 exclude these added records. Outlet panels
  and script 26 retain them, with recorded/assigned counts reported separately.
- Panel builders 00/05 deduplicate canonical outlet/reporter/question-item
  keys after alias consolidation; raw affiliations remain in the cleaned
  questions file for the source-to-clean-name bridge used by scripts 25/26.
  Script 25's full-source question total retains its original raw-item
  definition, rather than counting canonical outlet-level observations.
- Validation: `Rscript tests/test_outlet_aliases.R`; final panel has 245
  metadata IDs x 5,114 dates = 1,252,930 rows. Entity/date panels are unique and
  balanced. All 118 metadata beneficiary names match contracts. There are
  364 flagged co-affiliation rows and 67,960 recorded attendance rows.
- The latest FEct estimates were NOT rerun and still use their earlier inputs.
- The attendance-role issue noted during this refresh was corrected on
  2026-10-08; see the correction and superseding counts below.

## Attendance-role correction, 2026-10-08

- At the user's request, the attendance cleaner now uses
  `src/attendance_roles.R::keep_attendance_role()` to normalize accents, case,
  and whitespace before excluding camera, photographer, student, technical,
  INGENIERO KU, and audio roles. Gender/plural variants of camera/photo/technical
  roles are covered. Original `cargo` values remain available for auditing;
  missing-role exclusion is unchanged. This does not establish unique persons.
- Added `tests/test_attendance_roles.R`; both it and `tests/test_outlet_aliases.R`
  pass. Regenerated attendance outputs, final-panel builders 00/05, and
  descriptive scripts 03/25/26/27. Current PDFs remain in `output/desc_stats`.
  The legacy count-based top-10 PDF is not regenerated (superseded by ratios).
- Exactly 7,576 recorded FOTÓGRAFO rows were removed: 67,960 -> 60,384 recorded
  attendance rows, with 364 assumed Mexico News co-affiliation rows unchanged.
  Recorded outlet-days: 66,485 -> 59,658. Recorded attendance dates:
  1,603 -> 1,602; 2022-04-23 had only one photographer record. This is a change
  in retained attendance coverage, not proof that no conference occurred.
- All surviving recorded rows equal the previous dataset minus excluded roles.
  Upstream daily counts reconcile to filtered rows. Final panel remains
  245 metadata IDs x 5,114 days = 1,252,930 unique rows. Deduplicated panels
  remain balanced (141 attendance, 135 questions, 116 contracts, 187 YouTube
  entities). Questions/contracts/YouTube entity panels are unchanged in content.
  Raw attendance, question files, and processed metadata hashes are unchanged.
- Refreshed ratio sample: 99 outlets with attendance in both periods. The
  opposition-only subset is now 14 outlets (3 increases, 5 decreases, 6
  unchanged); aligned remains 28 (9 increases, 15 decreases, 4 unchanged).
- Recoverable pre-fix outputs, source hashes, run logs and validation counts:
  `MEDIA_ROOT/results/audits/attendance_role_filter_20261008_193612/`.
  One-off runner and validation script are in `tmp/refresh_attendance_roles.py`
  and `tmp/validate_attendance_roles.R` on this checkout.
- FEct estimation files were NOT rerun and still reflect their earlier inputs.
  The separately documented transcript speaker-attribution issues have NOT
  been applied to the question data; this refresh only fixes attendance roles.

## Deferred Analysis: Pre-Lottery Covariate Adjustment

Recorded 2026-10-06 at the user's request. **Documentation only: do not implement
or run estimation until the user asks to resume it.** The starter dataset was
subsequently authorized and implemented on 2026-10-11 (see below); FEct covariate
adjustment remains deferred.

### Starter dataset implemented, 2026-10-11

- Entry point: `code/08-results/balance/00-balance.R`; helper:
  `src/baseline_history.R`; synthetic tests: `tests/test_baseline_history.R`.
  Imports the refreshed final metadata-ID/day panel, not the stale FEct inputs.
  User confirmed presidency years beginning December 1, 2018. Uses 2022-04-18
  as lottery cutoff and defaults to the existing 2022-04-18--2024-12-31 analysis
  period, all configurable at the top of the script.
- `windows`: all pre-period; presidency years 1/2/3 and partial year 4;
  immediately prior 12 and 24 months. Every window ends before the lottery.
  `balance_outlets`: 245 rows, full processed metadata plus 168 history/coverage
  fields. `balance_panel`: 242,305 metadata-day rows with these frozen baselines.
  `baseline_long` and the complete source `crosswalk` remain available in memory.
- `pre_attendance_*` counts recorded journalist rows, `pre_questions_*` counts
  questions, not question-days. Assumed co-affiliation and minimum attendance
  inferred from questions are separate fields. Main questions/attendance ratio
  uses corrected attendance records on common observed source dates; both a
  recorded-only ratio and a binary question-day/attendance-day share are included.
- Source coverage is enforced from deduplicated entity panels. Entirely
  unavailable histories remain NA; partial observed totals carry observed-day
  counts. November 2021 recorded attendance/ratios are excluded while question
  totals and explicitly marked inferred lower bounds remain available.
- Added contract histories in the same seven windows: `pre_contracts_costo_*`
  (the nominal MXN measure used in existing graphs), `pre_contracts_importe_*`,
  `pre_contracts_received_n_*`, `pre_contracts_n_*`, `pre_contracts_award_days_*`,
  and `pre_contracts_observed_days_*`. Uses contract/order dates and the existing
  deduplicated COMSOC beneficiary/day panel. received_n sums daily distinct
  contract/order IDs; n counts line items. These are not interchangeable, and
  IDs are not re-deduplicated across dates within each historical window.
  Contract totals include November 2021 and use the same December-2018 history
  start (not the complete contracts archive starting in 2012). Entirely absent
  source coverage/mappings remain NA; observed no-award periods remain zero.
  `contract_baseline_entities` is computed once per beneficiary before attaching
  to metadata rows, so subsidiaries do not multiply each outlet's baseline.
  Synthetic and actual-data annual-to-total reconciliation checks pass.
- Each metadata row has at most one attendance, question and contract ID. Shared
  entity histories may repeat across subsidiaries; never sum metadata rows for
  source totals. Multiple YouTube IDs remain in `crosswalk`, not expanded into
  duplicate balance-panel rows. All metadata columns/dummies are retained.
  Current metadata are not guaranteed to be baseline-era measurements.
- `SAVE_OUTPUTS <- FALSE` by default: running creates R objects only and does
  not alter panels/estimates. Setting TRUE exports to `MEDIA_ROOT/data/06-outcomes/balance`.
  Legacy attendance_total/before/after fields are omitted from the starter
  panel so their full-period/other-cutoff counts are not mistaken for baselines.
  This starter does not estimate models. Simple balance regressions were
  subsequently run in `01-run_balance.R` (see below); FEct covariate-adjusted
  outcome models have not been estimated.

### Simple Balance Regressions — October 11, 2026

- User requested a simple run with existing data: individual covariate
  regressions on any-question with date FE, and a joint any-question regression
  on the core covariates with date FE. User confirmed directly recorded
  attendance as the main sample; actual lottery/seating assignments are absent.
- Entry point: `code/08-results/balance/01-run_balance.R`. Outputs:
  `output/balance/RESULTS.md`, CSV tables/audits, `balance_core.tex`,
  `joint_regression.tex`, and `balance_models.rds`. No upstream data changed.
- Period April 18, 2022–September 27, 2024; both sources matched/observed,
  recorded attendance positive, one unambiguous source pair per unit, dates
  with both askers and non-askers. Joint N = 7,976 unit-days, 81 units,
  318 dates, 428 asking unit-days. No future-attendance threshold.
- Five ambiguous attendance mappings excluded: bajo palabra, jaime farias
  informa, lord molecula oficial, mmm otros, oem otros. Shared unambiguous pairs
  count once. Conflicting metadata values are missing, not arbitrarily selected.
- Core: ideology, media formats, national coverage, age, subscription, distance,
  prior-year attendance and question counts, contract value and contract count.
  Counts/money use log1p; continuous joint regressors use observed-SD units.
  Missing core values get zero plus missing indicators. Other historical windows
  and ratios are tested individually, not all placed in one joint regression.
- Initial run (superseded by the coding revision below): unit-clustered joint
  test of 15 substantive coefficients: F(15,80)=5.171642,
  p=4.900349e-7. Aligned coefficient in joint model: 0.0362295, p=0.0334050.
  These are provisional observed-access balance results, not causal coefficients
  or a direct test of seating draws. Pending transcript corrections remain unapplied.
- Validation: `Rscript tests/test_balance_outputs.R` checks unique sources,
  recorded attendance/coverage, dates, independent within-date coefficient
  calculations and the clustered joint Wald calculation.

#### Same-day user-requested coding revision

- Updated 01-run_balance.R and reran. User requested missing format/coverage
  flags and contract histories coded 0, all three ideology categories displayed,
  and questions per attendance in the core model. Recorded-attendee sample and
  date FE are unchanged: 7,976 outlet-days, 81 source units, 318 dates.
- Format/scope flags use any positive metadata member within a source unit,
  with NA otherwise treated as 0. Social media and personal are now separate.
  These individual rows and contract rows now all have N=7,976.
- Contract covariates aggregate each distinct beneficiary once per unit/window;
  absent histories contribute 0 before log1p. The beneficiary audit is exported.
  This is a user-requested coding convention, not proof of no unrecorded awards.
- All three political indicators use the same classified sample (N=7,382).
  La Jornada and Sonora Power have conflicting member classifications; all three
  indicators remain missing for those units rather than inventing a category.
  Neutral/unclear is explicitly displayed as the joint reference, not estimated
  alongside a full set of three dummies and date fixed effects.
- Main ratio is pre_questions_per_recorded_attendance_last_year, based on
  common-covered dates. Zero denominators remain NA. Individual N=7,441;
  joint model imputes remaining missing values with missingness indicators.
- Revised joint test: F(17,80)=12.01283, p=1.336806e-15. Aligned coefficient
  =0.01981, p=0.246; this replaces the earlier 0.03623 coefficient.
- Updated PDF: output/pdf/balance_results.pdf, exported by
  code/08-results/balance/02-export_balance_pdf.py and visually checked.
  Prior results/PDF preserved in output/balance_before_zero_coding_20261011/.

#### Conditional-balance revision — October 11, 2026

- Subscription missing values now count as 0 in both model families, using
  the same any-positive metadata-member rule as other binary format flags.
- Individual balance regressions now use `X ~ ask + prior_ratio | date`, where
  prior_ratio is pre_questions_per_recorded_attendance_last_year. Undefined
  ratios are excluded, not treated as observed zero: eligible N=7,441,
  71 units, 305 dates; additional covariate missingness can reduce a row's N.
- Both the PDF and tables show date-FE-only and ratio-adjusted estimates on
  exactly the same sample. The ratio is not regressed on itself. Standalone
  prior-question/attendance count measures are removed from individual tests
  and the joint model, including the supplementary count-history tests.
- Joint model retains its full sample (N=7,976) and missing-indicator approach;
  ratio remains a tested predictor, not an untested conditioning variable in
  a newly defined partial joint test. Revised F(15,80)=7.663835, p=2.993881e-10.
- Same-sample aligned individual contrast: 0.223 without ratio control versus
  0.220 with it (p=0.000723); the ratio does not remove this imbalance.
- Updated PDF/CSV/LaTeX and tests; independent FWL checks partial out both
  date and ratio and verify the unadjusted same-sample comparison as well.
  Previous results and the R/Python export code are preserved under
  output/balance_before_ratio_control_20261011/.

#### Current focus: alternative historical ratios only — October 11, 2026

- User asked to set metadata and other covariates aside and compare historical
  question/recorded-attendance ratios over different pre-lottery windows.
- New standalone entry point: code/08-results/balance/03-prior_ratio_balance.R.
  Windows are 12, 18, 24 months, plus full history from December 1, 2018;
  all end April 17, 2022. MONTH_WINDOWS is configurable. No contract or metadata
  values are imported as predictors; metadata is used only for the ID crosswalk.
- Counts use dates observed in both sources and exclude November 2021 from
  numerator and denominator. Ratio is questions / recorded journalist records,
  not question-days / attendance-days. No zero-imputation for undefined ratios.
- Each ratio is separately tested as ratio ~ ask | date. Joint model is
  ask ~ all four ratios | date. Both use the same complete-ratio sample:
  7,441 outlet-days, 71 source units, 305 dates; source-unit clustered SEs.
- Individual differences (12m,18m,24m,full): 0.152,0.185,0.171,0.176;
  unadjusted-for-multiplicity p-values: 0.00263,0.0149,0.0256,0.0318.
  Joint F(4,70)=1.22019, p=0.310114. Overlapping ratios are strongly correlated;
  individual balance and simultaneous access-prediction tests differ.
- Actual common historical coverage: 145,221,276,365 dates respectively.
  First common dates: 2021-04-19,2020-10-20,2020-07-02,2019-03-01.
  Calendar windows must not be described as fully observed histories.
- Outputs: output/balance/prior_ratios/; new PDF output/pdf/balance_prior_ratios.pdf,
  created by code/08-results/balance/04-export_prior_ratio_pdf.py, visually checked.
  Earlier metadata analyses/PDF remain available and unchanged.
- tests/test_prior_ratio_balance.R passes count/coverage/window checks, independent
  FE coefficient and joint Wald checks, and reconciliation of the 12-month ratio
  against the earlier definition. Transcript corrections remain pending.

### Requested Covariates

- Outlet metadata characteristics. Select the actual fields with the user when
  resuming; possible fields already discussed include ideology, outlet type,
  coverage scope, and location. Do not assume the current metadata describe the
  outlet before the lottery without checking their timing.
- Pre-lottery journalist attendance history: total attendance, year 1, year 2,
  year 3, and the prior year.
- Pre-lottery questions asked: total questions, year 1, year 2, year 3, and the
  prior year, using the same windows as attendance.

Historical attendance should count journalist attendance records, not merely
days on which an outlet attended. Historical questions should count questions,
not merely question-day indicators. This differs intentionally from the
same-day attendance dummy and question-day treatment in the current model.

### Decisions and Data Checks Before Implementation

- Confirm the exact lottery date. The existing estimation sample starts on
  2022-04-18, but verify that this is the intended historical cutoff. Include
  only observations strictly before the confirmed cutoff, never the lottery
  date or later observations.
- Resolved on 2026-10-11: years 1/2/3 mean successive presidency years from
  December 1, 2018. The starter also supplies the immediately prior 12 and 24
  calendar months, as distinct overlapping candidate measures.
- Freeze these histories at the cutoff for every outlet; do not replace them
  with rolling histories around each later question episode.
- Audit source coverage and outlet identifiers before counting. Use the
  deduplicated attendance/question entities and metadata crosswalks to match
  the YouTube estimation entities without multiplying records across outlets
  or subsidiaries sharing an identifier. Resolve ambiguous mappings explicitly.
- Preserve the rule that asking a question implies attendance, but distinguish
  recorded journalist counts from inferred attendance. A question alone does
  not identify the full number of attending journalists. Document any minimum
  attendance imputation and its effect on historical totals.
- Distinguish genuine zeros from missing source coverage. Do not silently turn
  an unobserved historical year into zero attendance or zero questions.
- Check overlap/collinearity among the total and annual measures: if annual
  windows partition the total, including all of them is redundant. The prior
  year may also duplicate another annual window. Treat these as candidate
  control sets, not a commitment to include every measure simultaneously.

### Econometric Plan to Discuss When Resuming

The current FEct specification uses outlet and date fixed effects, question-day
treatment, and a same-day outlet attendance dummy. Metadata that do not vary
over time and histories frozen before the lottery are absorbed by outlet fixed
effects if added as standalone regressors. They therefore cannot simply be
appended as ordinary controls to obtain additional adjustment.

A candidate robustness specification is to interact a small, prespecified set
of baseline characteristics and historical measures with calendar-quarter
indicators (or another agreed calendar-time structure). This allows baseline
characteristics to predict different untreated time paths. The exact controls,
time interactions, reference periods, and missing-data rules require agreement
before estimation. Check rank and support, especially in the small Opp. sample;
do not add a large saturated set mechanically.

Pre-lottery does not necessarily mean pre-treatment: outlets could ask questions
before the lottery. Baseline histories may reflect earlier question exposure,
so discuss what effect is being estimated and the assumptions for conditioning
on that history. These controls do not automatically resolve pre-trend concerns.

Adding controls requires new FEct fits and new bootstrap inference; saved
coefficients cannot be adjusted after estimation. Preserve existing estimates,
tables, and figures as the unadjusted comparison. Current entry points are:

- `code/07-final_panel/19-run-daily-question-day-event-studies-fect.R`: model fits.
- `code/07-final_panel/22-export-log1p-att-latex.R`: ATT and diagnostic tables.
- `code/07-final_panel/24-plot-pooled-and-heterogeneity-events.R`: saved-estimate
  figures, pooled 1x3 and heterogeneity 3x3; all axes currently -2 to +2.5.

Retain the agreed raw `log(1+y)` and winsorized-then-`log(1+y)` comparisons and
1,000 outlet bootstrap replications unless the user changes the specification.
Use configured Media paths for future data and generated artifacts, following
the repository path convention above.

## Outlet review update, 2026-10-26

The user approved combining Sin Linea and El Politico en las Redes under
`sin linea`. Exact alias registries, the Sheinbaum deduplication rule, both
metadata master workbooks, cleaned attendance/bridge, and cleaned identity
outputs were updated with backups. There are 35 unique Sheinbaum appearance
dates; all 18 within attendance coverage match recorded attendance. Three
uncertain reporter identifications remain unresolved.

The user explicitly said: "do not re do the whole panel building just yet".
Do not automatically rebuild panels, reports, or model estimates during the
remaining outlet-by-outlet review. The running source-panel rebuild was stopped.
No live processed metadata, balanced/final/outcome panels or reports were
replaced. Those remain pending for a later user-requested refresh. Unpublished
staging products are documented in `outputs/sin-linea-20261026/STATUS.txt`;
the publication manifest is `recovery/sin-linea-20261026/published/manifest.json`.

Puente Libre follow-up, 2026-10-26: the user instructed "keep both but combine
the attendance and question record". Tiempo La Noticia Digital and PuenteLibreMX
remain distinct metadata/brand rows, with their own legal entities and YouTube
channels. Their conference source keys both use `tiempo la noticia digital`.
The Sheinbaum mapped records retain `outlet_brand_aux`; deduplicated records
retain the full `outlet_brands` list. This combines 24 joint introductions into
25 unique group appearance dates (including one Tiempo-only date). All 15 dates
inside attendance coverage match. No panel/report builds were run for this step.

Teleurban follow-up, 2026-10-26: user approved putting it together with W Radio.
Use `w radio` for conference records; exact `RADIOPOLIS` attendance labels also
map to this ID. Preserve Teleurban in the brand fields and raw evidence, without
inferring corporate ownership. There are 15 joint named appearance dates, plus
one extra unnamed W Radio identification on 2025-02-24 retained for review.
12 of 13 dates inside attendance coverage match; 2025-02-24 stays unmatched.
No attendance was imputed, physical attendance rows are unchanged, and no panels
or reports were rebuilt. Metadata workbooks retain W Radio's corporate details.

Frecuencia CAD follow-up, 2026-10-26: user approved combining Frecuencia CAD,
Es Ahora AM and JF Informa under `jaime farias informa` for conferences while
retaining their three brand metadata rows and separate channels. Original
extraction labels and `outlet_brand_aux`/`outlet_brands` retain provenance.
21 unique Sheinbaum dates; 18 duplicate brand identifications collapsed;
10 of 11 dates within attendance coverage match. 2024-11-06 remains unmatched.
Alberto Marroquin Espinosa is standardized to Espinoza (five mapped records).
10 AM MX is separate. Exact shared aliases also update AMLO identity inputs
without dropping any question-item rows. Four old Frecuencia K/Kcom AMLO
records remain outside the approved grouping pending evidence review.
The official https://frecuenciacad.com/ website lists Alberto's Es Ahora
program, resolving the previous conference-linkage uncertainty. Formal
ownership and channel verification remain separate. Published 11 identity/
metadata files with backups in recovery/frecuencia-cad-20261026/published.
No panels, processed metadata, reports or models rebuilt.

Empuje Migrante follow-up, 2026-10-26: user approved shared conference key
`oro solido` for Empuje Migrante and Oro Solido. Preserve both metadata/brand
rows and existing channels/ownership fields. Nancy Rodriguez explicitly names
both on all 13 Sheinbaum dates; 26 brand records collapse to 13 identifications.
6 of 8 dates within attendance coverage match. 2025-03-04 has only one raw
attendance row (possible incomplete coverage); 2025-05-06 has 48 rows and no
match. Both gaps remain flagged; no attendance imputed. Five further dates
are outside attendance coverage. Amigo Migrante, Mitote Migrante, Conexion
Migrante and TV Migrante remain outside this grouping. AMLO exact labels also
updated (131 rows), preserving all original question-item rows. Published 11
metadata/identity files with backups in recovery/empuje-migrante-20261026/published.
No panels, processed metadata, reports, models or channels rebuilt.

Flagged-outlet workbook review, 2026-10-26: reviewed all 130 original flagged
labels and applied 14 explicitly approved conference groups. Decisions and
dated evidence are in `info_newspapers_gpt/outlet_review_20261026/`; refreshed
workbook remains `outputs/sheinbaum-roster-20261019/sheinbaum_outlet_attendance_review.xlsx`.
Original flagged labels: 62 resolved on all covered dates, 13 with only missing
or sparse rosters, 12 outside attendance coverage, 43 with at least one usable
roster date lacking a verified label. Rows sharing a conference ID must not be
summed. Four identities restored from overmatches appear as additional rows.
User's latest decision: Bloomberg News AND Bloomberg Linea share `el financiero`
with El Financiero; preserve all three brands. Bare Bloomberg stays unspecified. AP Noticias is distinct
from Associated Press; Gabriela Montejano's Agora (Celaya) is distinct from
Gerardo Romo's Agora Digital; Abel Cuapa's Capital is Capital Puebla.
AMARC/Politica y Rock Radio, Alcanzando el Conocimiento/El Regreso de Donald
Trump, and Nopal Times/El Charro Politico are approved conference groups.
TV Migrante/Canal 14 SPR and SandraAguilera.com/Larsa remain separate, with
verified date-specific co-affiliations. Miled and Perspectivas remain separate;
Judith Sanchez Reyes has 11 verified dated links. There are 28 dated links total,
each checked against the actual raw eligible attendance row, with no imputation.
Added 72 evidence-only brand entries to both source metadata workbooks; ownership
and legal details were left unverified. Separate brand rows/channels retained.
Published 12 identity/review files with originals backed up under
`recovery/flagged-outlets-20261026/published/`. Raw introductions, reporter keys,
physical attendance rows, unrelated workbook values and 129 formulas preserved.
Do not rebuild panels, processed metadata or reports until the user requests it.

Bloomberg Linea follow-up, 2026-10-26: explicitly approved the same El Financiero
conference group. Updated identity rules and inputs; 22/24 covered asking dates
match, 2025-04-14 lacks a usable roster and 2025-06-03 has no verified label.
Publication backups: recovery/flagged-outlets-20261026/published-bloomberg-linea/.
No panels or processed metadata rebuilt. Original 130-flag status counts unchanged.

La Mont/ABC Radio/Audiorama follow-up, 2026-10-26: user explicitly approved
combining all three for conference records, canonical audiorama. Separate brand
rows remain. Only exact ABC Radio/760/XEABC labels join this group; ABC Australia,
ABC de Monterrey, unspecified ABC News and other ABC titles are not included.
Added ABC Radio as a distinct source-metadata brand at the end of both workbooks,
preserving all earlier row IDs. La Mont has 6/6 covered dates matched; the shared
group has 13 transcript dates (12 La Mont plus one Audiorama introduction).
Original flag totals now 63 resolved, 13 roster gaps, 12 outside coverage, 42 with
unmatched dates. Decisions and review workbook refreshed; no panels rebuilt.
Backups: recovery/flagged-outlets-20261026/published-lamont-audiorama/.

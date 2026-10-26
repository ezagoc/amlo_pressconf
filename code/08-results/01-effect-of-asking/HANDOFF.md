# Effect of asking: YouTube outcomes

Started October 12, 2026. This is the entry point for a new session.

## Run status

IN PROGRESS: the user explicitly chose six ALL-VIDEO outcomes and the EARLIER
FULL-CALENDAR FEct panel with an attendance dummy. Scripts 18/19/20 implement
this separate extension, with baseline and prior-year-history-adjusted fits,
upper-p99 asinh outcomes, and 1,000 ordinary outlet bootstrap draws. See below.

Latest deliverable: six-outcome, upper-p99-winsorized DAILY regression tables,
pooled main results followed by combined-group interactions. See the section below.
Now in three transformations (log1p, asinh, Chen-Roth x=0), with smaller scriptsize
tables and outcome order videos, total interactions, mean interactions/video,
likes, comments, views. Each transformation has a separate two-page PDF.
The earlier three-outcome raw tables and estimates remain unchanged.

The preceding requested check is WEEKLY, using all usable weeks including partial
conference-source coverage as explicitly requested by the user. Completed with
9,999-draw outlet wild bootstrap. See the weekly section immediately below.

Latest inference check: completed null-imposed outlet wild cluster bootstrap
for the combined-group models, 9,999 draws per test. See the section below;
no group effect or contrast is significant at 5% under this inference either.

Latest requested comparison combines opposition and independent as
Opp. + Independent versus Aligned. Run scripts 09 and 10 with --combine.
It is saved separately and preserves the three-category interaction results.

Latest main heterogeneity specification: the pooled asking-by-ideology interaction
model described immediately below. Earlier separate subgroup regressions and
subgroup FEct results are sensitivity checks, not the main interaction model.

### Earlier full-calendar FEct + histories — October 12, 2026

Explicit user choice after clarification: all six all-video outcomes; earlier
full-calendar FEct, not conference-only outcomes or the newer attendee sample.
This extension is pooled same-question-day ATT, baseline and history adjusted.
No new heterogeneity, carryover holdout, or event study has been requested here.

Build: 18-build-full-calendar-fect.R. Output folder:
MEDIA_ROOT/results/effect_of_asking/legacy_full_calendar_asinh_winsor99_history/.
Preserves the original output/fect_youtube/youtube_questions_attendance_daily.parquet
exactly in entity/date rows, attendance dummy, and treatment. Apr 18, 2022 through
Dec 31, 2024; 163,185 outlet-days, 165 YouTube entities, 989 days, 499 treated cells,
66 ever-treated entities. All 163,185 source metric cells are matched/covered and
none of the six underlying metric inputs is missing. Existing likes/comments
and interactions match current source values exactly. Do not truncate to AMLO's
last conference or silently replace this user's chosen legacy coding.

Raw outcomes order: videos, interactions, mean_interactions, likes, comments,
views. Interactions = raw likes + comments; mean = raw interactions / raw videos,
zero on no-video days. Each raw outcome independently upper-capped at the p99 of
THIS full-calendar pooled sample (R type 7), then asinh. Caps: 57; 60,464.48;
11,910.60; 54,944.92; 6,192.16; 2,287,884.92. Both models share all rows and caps.

History is the existing audited ratio_12m: Apr 18, 2021-Apr 17, 2022 questions /
recorded journalist attendance on jointly observed dates, excluding Nov 2021
from numerator and denominator. Unique attendance-question pairs map to unique
YouTube source IDs through metadata, without row expansion. Each of 104 mapped
YouTube entities has one unambiguous history ID; 71 have finite ratios, 33 are
undefined, 61 have no resolved pair. Missingness is flagged and the ratio is
zero-filled ONLY as an estimation placeholder. Quarter interactions with ratio
and missingness, omitting 2022Q2, add 20 identified controls. Untreated-sample
two-way-residualized rank checked; attendance dummy retained in both models.
Time-invariant history levels themselves are absorbed by unit FE.

Run: 19-run-full-calendar-fect.R --nboots=1000 --resume (optional repeatable
--outcome=... to parallelize independent outcomes). Ordinary FEct outlet/entity
bootstrap, not wild bootstrap. method=fe, force=two-way, min.T0=5, seed20261012,
serial inside each process. Every fit is checkpointed with exact inputs under
fect_1000/. Per-fit scalar files prevent concurrent write conflicts. Resume
requires identical inputs including panel fingerprint and fect package version.

Runtime note: macOS R initially used the slow reference BLAS. The three completed
baseline fits were preserved; unfinished calculations were restarted with R's
bundled libRblas.vecLib.dylib (Accelerate), selected only for those processes via
DYLD_LIBRARY_PATH pointing to temporary libRblas.dylib/libRblas.0.dylib symlinks.
No installed R files or global settings were changed. Launch the R binary directly
(Resources/bin/exec/R with R_HOME=Resources) because intermediate protected shells
can strip DYLD variables; VECLIB_MAXIMUM_THREADS=1. A separate six-bootstrap smoke
run under fect_6/ reproduced the original fect_5/ point estimates and first five
bootstrap draws to <1e-15 for BOTH videos models. Neither smoke run is final
inference. Full production fits still use 1,000 draws and identical saved inputs.

Five-bootstrap videos smoke fits passed sample, finite-draw, bootstrap-SD,
attendance-slope and independent untreated-FE imputation ATT checks. Those are
under fect_5/ and MUST NOT be presented as final inference. Full fits are running.
Each final fit independently checks the same conditions. Exporter 20 requires
all twelve fits and 12,000 finite draws and rechecks table scalars/transformations.

Planned table: centered scriptsize, two outcome panels, six columns per panel
(baseline/history pairs), ATT with bootstrap SEs in parentheses; FEct p-values
in brackets below a rule. Stats: FE, attendance, history, N, entities, calendar
days, question-days, ever-treated entities, RMSE, bootstrap count. Do not label
these SEs as conventional cluster-robust or the p-values as wild-bootstrap tests.

### Compact tables and transformation checks — October 12, 2026

Formatting follow-up: all six numeric columns are centered (coefficients, SEs,
column numbers, and statistics). P-values use square brackets and appear in a
separate block BELOW the coefficient/SE block's horizontal rule; interaction
p-value rows explicitly identify Asked versus Asked x Aligned. Applied to all
three six-outcome transformations, both pooled and interaction tables. The
exporter validates against saved fits; no estimates or inference were rerun or
changed. All six PDF pages re-rendered and visually checked after this update.

The user requested smaller tables, the outcome order videos / total interactions /
mean interactions per video / likes / comments / views, and separate asinh and
Chen-Roth tables in the same format. All three versions retain upper-only p99
winsorization BEFORE transformation, unchanged samples/history controls, and
9,999-draw conventional/wild outlet inference. There are two panels per table:
publishing/interactions first, likes/comments/views second. Font is scriptsize,
width 94% of line width; pooled and interaction tables occupy separate pages.

Scripts 00/16/11/15 support --transform=asinh or --transform=chen_roth_x0.
The default is log1p. To reproduce EACH new alternative, run:

1. 16-daily-six-outcomes-winsor99.R --transform=TRANSFORM
2. 11-wild-cluster-bootstrap.R --winsor99 --pooled --transform=TRANSFORM
3. 11-wild-cluster-bootstrap.R --winsor99 --transform=TRANSFORM
4. 15-export-daily-regression-tables.R --winsor99 --transform=TRANSFORM

Only re-export log1p to change layout; its stored fits/inference were not changed.
Data folders append _asinh or _chen_roth_x0 to daily_winsor99_six_outcomes.
PDF and LaTeX names append the same suffix to their existing winsor99 stems.
Final PDFs (all six pages rendered and visually checked, no overflow):

- output/pdf/effect_of_asking_daily_regression_tables_winsor99.pdf
- output/pdf/effect_of_asking_daily_regression_tables_winsor99_asinh.pdf
- output/pdf/effect_of_asking_daily_regression_tables_winsor99_chen_roth_x0.pdf

The corresponding main and interaction fragments live in
overleaf/tables/effect_of_asking/ with daily_main_regression_winsor99 and
daily_interaction_regression_winsor99 stems and those suffixes. Preview wrappers
have daily_regression_tables_preview_winsor99 stems.

Chen-Roth uses the previously requested x=0 calibration from script 19 in the
older FEct workflow: log(y) for y>0, log(m) for zero, one fixed minimum positive
value per outcome over the CURRENT pooled estimation sample, shared by groups
and bootstrap tests. Values m: videos=1, interactions=1, mean interactions=1/11,
likes=1, comments=1, views=3. This is a calibrated-log sensitivity, not an
automatic percentage-effect interpretation or a new panel estimator. In
particular, x=0 maps zero and the minimum positive value to the same value.
Alternative normalized log(y/m) for positive y, zero otherwise differs only by
a constant: all 24 Chen-Roth coefficient vectors/covariances match under that
equivalent normalized specification within 1e-9.

Model columns retain the legacy log_ prefix across transformations; use the
saved panel$transformation and outcome_definitions, not the prefix, to identify
the outcome transform. Calibration values are saved with panels and cutoff CSVs.

17-validate-daily-transformations.R independently checks all three variants:
raw data/controls unchanged, mean construction and zero handling, exact pooled
quantiles, cap-before-transform, original estimation rows, provenance, and all
144 wild tests / 1,439,856 finite bootstrap draws and their tail p-values.
PASS. New alternatives add 48 fits and 96 bootstrap tests; no old model changed.

Adjusted pooled views estimates / conventional p / wild p:
log1p .20855 / .05285 / .05281; asinh .22250 / .04665 / .04510;
Chen-Roth .18547 / .06922 / .07491. Other adjusted pooled outcomes and all
adjusted interaction contrasts exceed .05. No multiple-testing adjustment;
do not present the transformation-dependent threshold crossing as robust proof.

### Six outcomes, upper-only 99th-percentile winsorization — October 12, 2026

The user added videos, total interactions, and mean interactions per video, then
requested winsorization at 99%. Applied to ALL SIX outcomes before log1p.
Do not change this to two-sided 1/99 winsorization or cap after transformation.

Reproduce in this order:

1. 16-daily-six-outcomes-winsor99.R
2. 11-wild-cluster-bootstrap.R --pooled --winsor99
3. 11-wild-cluster-bootstrap.R --winsor99
4. 15-export-daily-regression-tables.R --winsor99
5. Compile daily_regression_tables_preview_winsor99.tex from its Overleaf table
   folder, then copy the PDF to the final path below.

Saved separately under MEDIA_ROOT/results/effect_of_asking/daily_winsor99_six_outcomes/.
The interaction subfolder is pooled_interactions_combined. Both contain fits,
panels, model sample statistics, provenance manifests, and wild_cluster_9999/.
Original fits, sources, raw tables, FEct, and weekly results are untouched.

- Sample and controls unchanged: pooled 5,303 rows/55 outlets/258 dates;
  interactions 4,979 rows/54 outlets/253 dates. Baseline and history adjusted.
- Total interactions = raw likes + raw comments. Mean interactions = raw
  interactions / raw video count, zero when no videos (1,279 pooled days and
  1,245 interaction days). These are not means conditional on posting.
- Compute each raw outcome first, then cap it separately at its pooled
  estimation-sample p99 (R quantile type 7); use the SAME cap in both models.
  In particular, do not sum separately capped likes/comments to get interactions,
  and do not divide capped interactions by capped videos to get their mean.
- Approximate caps: likes 91,886; comments 10,235.06; views 4,936,366.04;
  videos 145; interactions 98,777.40; mean interactions 24,524.21.
  Exact calculations use in-memory doubles; CSV decimal serialization differs
  by at most 4.1e-15 relatively. Cutoff audit: winsorization_cutoffs.csv.
- Validation: saved videos matched fresh unique-channel source sums; all 24
  fits retained the exact original sample; raw definitions, zero handling and
  log1p(min(raw,p99)) independently checked using recalculated exact quantiles.
  All Aligned marginal effects and SEs checked using direct-slope models.
  All 48 wild tests (12 pooled, 36 interaction), 479,952 finite draws validated;
  refits reproduced coefficient/covariance to 1e-9 and tail p-values reproduced.
- Adjusted pooled wild p-values in outcome order likes/comments/views/videos/
  interactions/mean interactions: .36694/.33793/.05281/.38004/.19932/.20092.
- LaTeX: overleaf/tables/effect_of_asking/daily_main_regression_winsor99.tex and
  daily_interaction_regression_winsor99.tex. Each has two panels with six columns;
  same estimate, clustered SE, both p-values, and model-statistics format as before.
- Final PDF: output/pdf/effect_of_asking_daily_regression_tables_winsor99.pdf.
  Two pages (main, then interaction), compiled without overflow warnings and
  both pages visually reviewed. Original raw preview remains available.

### Daily publication tables — October 12, 2026

The user requested estimates with clustered SEs and explicitly chose BOTH
conventional clustered and wild-bootstrap p-values. Wild bootstrap-t has no
reported SE; do not substitute the spread of null-imposed bootstrap t draws.

- Run 11-wild-cluster-bootstrap.R --pooled for the six main daily tests (9,999
  null-imposed outlet WCR11/Rademacher draws). Saved separately under
  MEDIA_ROOT/results/effect_of_asking/wild_cluster_9999/.
- All six refits reproduce the saved main coefficients and clustered covariance
  within 1e-9 on exactly 5,303 rows, 55 outlets, 258 dates. All 59,994 draws are
  finite and every p-value is verified from its saved tail frequency.
- Adjusted pooled wild p-values: likes 0.40344034, comments 0.33353335,
  views 0.05630563. No earlier estimates or bootstrap outputs were overwritten.
- Run 15-export-daily-regression-tables.R to validate input fingerprints and
  coefficient/SE/p-value consistency and export the two inclusion-ready fragments:
  overleaf/tables/effect_of_asking/daily_main_regression.tex and
  overleaf/tables/effect_of_asking/daily_interaction_regression.tex.
- Both tables have six columns (baseline and history-adjusted for likes,
  comments, views), outlet-clustered SEs in parentheses, both p-values, FE and
  history-control indicators, N, clusters, conference dates, within R-squared,
  and 9,999 bootstrap draws. No stars or confidence intervals. Requires booktabs.
- Interactions reuse the existing combined daily results (4,979 rows, 54 outlets,
  253 dates); ask is the Opp. + Independent effect, ask_aligned is the Aligned
  minus reference difference, NOT the total Aligned effect. No weekly estimates.
- Standalone LaTeX preview: same folder/daily_regression_tables_preview.tex.
  Compile from that folder with pdflatex, output-directory=repo/tmp/pdfs; copy
  the resulting PDF to output/pdf/effect_of_asking_daily_regression_tables.pdf.
  The one-page final PDF was rendered and visually checked; no clipping or
  LaTeX overflow warnings. Fragments omit titles/notes; preview supplies both.

### Weekly check, all usable weeks — October 12, 2026

The user asked for the final weekly-level check, then explicitly said "use all"
after the coverage audit found only 21 full weeks with complete overlap across
known attendance/question conference dates. DO NOT restrict this run to those
21 weeks. This is an observed-records weekly analysis, with its measurement
limitation explicit, not a complete-coverage weekly experiment.

Build with 13-weekly-interactions.R from source panels, not from the selected
daily regression rows. Keep the 54-outlet roster and the combined ideology
classification from the preceding daily model. Histories, transformations,
no-winsorization rule, cluster level and common-slope design are unchanged.

- Weeks run Monday-Sunday; include dates Apr 18, 2022-Sep 27, 2024. The final
  Sep 23 week has only five in-window days and is retained per "use all".
- Sum raw snapshot likes/comments/views on ALL videos published in the week,
  across each outlet's distinct mapped channels, including weekends and days
  it did not attend. Then apply log1p to each sum. Require complete YouTube
  coverage of all expected channel-days within the analysis window.
- Attendance eligibility: at least one directly recorded attendance that week.
  Sum observed recorded journalist attendance, without question-implied or
  assumed co-affiliation attendance. No new attendance-frequency control.
- Treatment: at least one OBSERVED question in that week, regardless of whether
  attendance is separately recorded on that same question day. Zero means no
  question in AVAILABLE records, not verified absence across a complete week.
- Do not fill an entirely unobserved question week with zero. Six of the 128
  calendar weeks have no question-source dates and remain missing. Twelve more
  lack pooled asking/nonasking variation. Partial overlap is NOT an exclusion.
- Final: 3,683 outlet-weeks, 54 units, 110 weeks, 317 treated outlet-weeks.
  Aligned: 1,353 rows / 20 units / 180 treated; combined: 2,330 / 34 / 137.
  No FE singletons are removed in these weekly fits. All six models share rows.
- 90 of the 110 estimation weeks have incomplete source overlap; 20 have full
  overlap relative to dates known in either conference source. This is not an
  independently verified census of all actual conference dates.
- Outlet and shared WEEK FE; quarter of the Monday determines the history
  interaction cell. Underlying prior-year ratio remains exactly as before.

Adjusted estimates (wild-bootstrap p-values), likes/comments/views:

- Opp. + Independent: .02982 (.7631), .10116 (.3873), .15404 (.2225).
- Aligned: .03566 (.8125), .06155 (.6756), .11129 (.6141).
- Aligned minus combined: .00585 (.9760), -.03961 (.8338), -.04275 (.8573).

No group effect or difference rejects zero at 5% under conventional or wild
bootstrap inference, for baseline or adjusted models. Interpret weak precision
and partial treatment measurement explicitly. Calendar-week exposure is NOT
a seven-day window starting after the question; videos can precede it, and
snapshot engagement is not engagement received that week. No carryover or
new FEct fit is estimated. All daily results remain unchanged.

Run:

    Rscript code/08-results/01-effect-of-asking/13-weekly-interactions.R
    Rscript code/08-results/01-effect-of-asking/11-wild-cluster-bootstrap.R --weekly
    Rscript code/08-results/01-effect-of-asking/14-validate-weekly.R
    python3 code/08-results/01-effect-of-asking/12-export-wild-bootstrap.py --weekly

Validation: raw source outcomes and recorded attendance independently aggregated
with base R and matched to every analysis row; seven-day/final-five-day channel
coverage checked; log after aggregation; unchanged input fingerprints; equivalent
reference-group coefficients/SEs; 18 bootstrap tests with 179,982 finite draws
and p-values independently reproduced from tail frequencies. PDF rendered and
visually checked; scriptsize LaTeX fragment compiles successfully.

Outputs are under MEDIA_ROOT/results/effect_of_asking/weekly_interactions_combined/,
with wild_cluster_9999/ for inference. Coverage audit files include all roster
outlet-weeks, daily source dates, weekly coverage and the retained-week calendar.
PDF: output/pdf/effect_of_asking_weekly_wild_bootstrap.pdf (one page).
LaTeX: overleaf/tables/effect_of_asking/weekly_wild_bootstrap.tex.

### Wild cluster bootstrap — October 12, 2026

User requested the proposed wild-bootstrap inference check, not a change in
specification or clustering level. Implemented in 11-wild-cluster-bootstrap.R;
12-export-wild-bootstrap.py creates the report and compact LaTeX table.

- Combined-group pooled interaction specification, baseline and adjusted;
  likes/comments/views; each group's effect and the aligned-minus-combined
  contrast tested separately against zero (18 tests total).
- WCR11, fwildclusterboot 0.14.3, fnw11 R engine, two-sided bootstrap-t,
  null imposed separately for each test; Rademacher weights by outlet.
- 9,999 draws per test, 54 outlet clusters. Both set.seed and dqset.seed use
  20261012. Common random weights across tests; no multiplicity correction.
- Project-local package library: tmp/Rlibs/wildclusterboot (not the existing
  user/system R libraries). If absent, install fwildclusterboot with required
  dependencies into that directory from https://s3alfisc.r-universe.dev and
  https://cloud.r-project.org. R 4.6.0 loads the 4.6.1-built binary with a warning.
- Bootstrap p-values only, not bootstrap SEs or inverted confidence intervals.
  Existing conventional intervals are saved distinctly in results.csv.

All six models were refitted on the exact 4,979 estimation rows, dropping the
already-known five singletons before boottest. Unit/date variables are explicit
factors to avoid fwildclusterboot's Date-class get_cluster incompatibility;
this does not alter FE membership. Do not use fixest data.save=TRUE here: this
version of boottest cannot resolve its DATA_SAVED call placeholder. The refit
data remain in script scope. Every coefficient and conventional covariance
matches the original saved model within 1e-9. Outlet FE are projected out in
the bootstrap; shared date FE are retained as dummies.

The bootstrap uses boot_ssc defaults (adj=TRUE, cluster.adj=TRUE, fixef.K=none).
Its t-statistic's finite-sample scale need not equal the previous conventional
fixest t scale. The bootstrap tail comparison applies the same correction to
observed and simulated statistics. Saved estimates and conventional p-values
still come from the unchanged original specification.

Adjusted conventional -> wild p-values (likes/comments/views):

- Opp. + Independent: .9553 -> .9567; .7334 -> .7439; .2032 -> .2232.
- Aligned: .6017 -> .6364; .6187 -> .6952; .4658 -> .4915.
- Aligned minus combined: .7817 -> .7907; .8159 -> .8410; .6173 -> .6387.

No baseline or adjusted group effect or contrast rejects at 5%. This does not
show that power is adequate, only that this inference check does not uncover
significance hidden by conventional clustered inference. Do not infer zero
effects or group equivalence. Maximum approximate Monte Carlo SE is .005.

Validation: 179,982 finite bootstrap t draws; correct sample N, cluster count,
zero null and imposed-null flag for all 18 tests; each package p-value equals
the tail frequency recomputed from saved draws. Original source fingerprints
and result input fingerprints pass. The one-page PDF was rendered and checked;
the scriptsize LaTeX fragment compiles successfully.

Run 11 with Rscript (default B=9999; --B=... available), then 12 with the bundled
Python/reportlab runtime. The exporter requires the completed 9,999-draw run.

- Results: MEDIA_ROOT/results/effect_of_asking/pooled_interactions_combined/
  wild_cluster_9999/ (18 test RDS files, refits, results.csv, estimation rows,
  input fingerprints and session info).
- PDF: output/pdf/effect_of_asking_combined_wild_bootstrap.pdf.
- LaTeX: overleaf/tables/effect_of_asking/combined_wild_bootstrap.tex.
- Method reference: https://s3alfisc.github.io/fwildclusterboot/reference/boottest.fixest.html.

Previous models/reports and FEct outputs remain unchanged. No leave-one-outlet-out
analysis or new FEct fit was run in this request.

### Combined opposition + independent comparison — October 12, 2026

Re-estimated the pooled model with ask + ask_aligned, shared outlet/date FE and
the same common historical controls. Opp. + Independent is the reference group;
aligned has effect beta + interaction. This constrains opposition/independent
to share one asking effect; it does not average their previous coefficients.
No metadata or underlying source IDs were modified. Mixed aligned/unclear
La Jornada remains excluded, and independent retains the unclear definition.

Both baseline and adjusted models use exactly the previous 4,979 rows, 54 units,
253 dates, original outcomes and controls; equivalence is asserted in code.
Combined group: 3,305 rows, 34 units, 133 asking rows. Aligned: 1,674 rows,
20 units, 173 asking rows. Group estimates and clustered SEs also match the
equivalent direct two-slope model. Each F(1,53) test is independently verified.

Adjusted estimates (p-values), likes/comments/views:

- Opp. + Independent: 0.00698 (.9553), 0.03285 (.7334), 0.21423 (.2032).
- Aligned: 0.05702 (.6017), 0.07776 (.6187), 0.09945 (.4658).
- Aligned minus combined: 0.05003 (.7817), 0.04491 (.8159), -0.11478 (.6173).

No adjusted group effect or between-group contrast is significant at 5%.
Report the uncertainty, not evidence that the groups are identical.
No FEct model was rerun or relabeled for this request.

Run:

    Rscript code/08-results/01-effect-of-asking/09-pooled-interactions.R --combine
    python3 code/08-results/01-effect-of-asking/10-export-pooled-interactions.py --combine

Outputs: MEDIA_ROOT/results/effect_of_asking/pooled_interactions_combined/.
PDF: output/pdf/effect_of_asking_pooled_interactions_combined.pdf (one page,
rendered and visually checked). Compact scriptsize LaTeX fragments in
overleaf/tables/effect_of_asking/pooled_interaction_combined_effects.tex and
pooled_interaction_combined_differences.tex; both compile successfully together.
Without --combine, scripts 09/10 retain the original three-group behavior.

Main regressions and all six FEct fits are complete. Every FEct fit has 1,000
finite bootstrap draws, and every point estimate passes the independent
untreated-only imputation check. Full source/data/model validation passes.
The PDF report and LaTeX fragments are generated by 03-export-report.py.
Per-outcome checkpoints are under fect_1000/.
The final three-page PDF was rendered and all pages visually checked. Both
LaTeX fragments compile successfully in a booktabs/lmodern wrapper. The saved
report contains main regressions, paired-sample FEct, sensitivities, legacy
reference estimates and identification/coverage caveats.

## Main heterogeneity: pooled interactions — October 12, 2026

User requested the simpler interaction specification after seeing the separate
subgroup fits. Implemented in 09-pooled-interactions.R; exported by
10-export-pooled-interactions.py. Both baseline and history-adjusted models use:

    log1p(outcome) ~ ask + ask_aligned + ask_independent [+ original controls]
                    | unit_id + date

Opposition is the reference. Aligned/independent effects add their interaction
to the ask coefficient. Date FE and history slopes are COMMON across ideology,
unlike the separate regressions. Main group indicators are absorbed by outlet FE.
No new transformations, winsorization, attendance assumptions or history controls.
The only date-overlap restriction is pooled asking/nonasking variation, not
within each group. Retain the same consensus ideology classification and exclude
La Jornada's mixed aligned/unclear source unit. Independent still means unclear.

Sample: 5,308 pooled input rows -> 5,073 unambiguous-classification rows ->
4,984 rows on 253 pooled-informative dates -> 4,979 rows and 54 units after five
singleton exclusions. All six models use exactly the same observations.
Group sizes: opposition 1,275 rows / 10 units / 45 asking rows;
aligned 1,674 / 20 / 173; independent 2,030 / 24 / 88.
Window: April 19, 2022-September 27, 2024.

Adjusted group effects (p-values), likes/comments/views:

- Opposition: -0.2706 (.0692), -0.0540 (.7206), -0.0833 (.6870).
- Aligned: 0.0569 (.6024), 0.0777 (.6189), 0.0993 (.4664).
- Independent: 0.1478 (.3146), 0.0769 (.5147), 0.3652 (.0813).

Adjusted joint heterogeneity tests set both interaction terms to zero:
likes F(2,53)=2.4038, p=.10016; comments F=.28844, p=.75060;
views F=1.17963, p=.31533. Outlet-clustered covariance and standard fixest
cluster-based t/F denominator df=54-1=53, not the minimum-group df used in the
earlier separate-regression contrast exercise. Interpret subgroup support
cautiously: only six opposition outlets ever ask in this sample.

One unadjusted pairwise result: independent-minus-opposition likes difference
0.4184, 95% CI [0.0104,0.8263], p=.0446. Nine adjusted pairwise comparisons
were evaluated; this isolated result is exploratory and the joint likes test
does not reject at 5%. Do not summarize as no individually significant
interaction contrasts, or as definitive evidence of heterogeneity.

Validation: all group estimates AND clustered SEs match an equivalent pooled
direct-group-slope parameterization; all six joint F statistics match independent
matrix calculations; identical samples, raw log1p values, source fingerprints,
unique unit/dates and recorded attendance are asserted. Full covariance is used
for all sums and contrasts. The two-page PDF is rendered and visually checked;
both scriptsize, caption-free LaTeX fragments compile successfully.

New outputs:

- MEDIA_ROOT/results/effect_of_asking/pooled_interactions/: fits, panel, group
  effects, interaction coefficients, pairwise differences, joint tests, sample
  sizes, exclusions, classification audit, input fingerprints and session info.
- output/pdf/effect_of_asking_pooled_interactions.pdf.
- overleaf/tables/effect_of_asking/pooled_interaction_effects.tex.
- overleaf/tables/effect_of_asking/pooled_interaction_differences.tex.

Run 09 then 10 from the same configured runtime as the original workflow.
Existing pooled and separate-subgroup models/reports are preserved. No FEct
bootstrap was rerun for this interaction request, and existing subgroup FEct
results are not relabeled as common-date interaction estimates.

## User request and agreed starting point

Run the proposed effect-of-asking regressions for the SAME YouTube outcomes:
**likes, comments, views**, with FEct as robustness. Future attendance is NOT the
outcome. Start a separate results workflow and preserve all prior analyses.

Main specification uses recorded attendees only, after the April 18, 2022
lottery through AMLO's last observed conference, September 27, 2024.
Do not call this an experimentally identified lottery ITT: actual seat assignments
and full eligibility rules are unavailable. The observed treatment is asking.

## Locations and rerunning

- Code and this handoff: code/08-results/01-effect-of-asking/.
- Models, panel, diagnostics and scalar result files:
  MEDIA_ROOT/results/effect_of_asking/.
- On this machine, MEDIA_ROOT is /Users/ezagoc/Dropbox/Media.
- PDF report: output/pdf/effect_of_asking_youtube_first_results.pdf.
- Compact, caption-free LaTeX fragments:
  overleaf/tables/effect_of_asking/main_results.tex and
  overleaf/tables/effect_of_asking/fect_robustness.tex.

From the repository root:

    Rscript code/08-results/01-effect-of-asking/01-build-and-estimate.R
    Rscript code/08-results/01-effect-of-asking/02-fect-robustness.R --nboots=1000 --resume
    Rscript code/08-results/01-effect-of-asking/04-validate.R
    /Users/ezagoc/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 code/08-results/01-effect-of-asking/03-export-report.py

Runtime: /usr/local/bin/Rscript; fect 2.4.5; fixest/arrow/dplyr/tidyr.
The PDF exporter requires reportlab. The config locates the repository from the
script path and reads the existing project_paths.R / .env; it does not assume
the caller's working directory. New output writes to Dropbox may need filesystem
approval. No raw inputs or prior output files are changed.

## Outcomes and estimands

- Unit: resolved, one-to-one attendance/question source unit, not metadata row,
  owner group, or individual YouTube channel.
- ask: 1 if at least one question was asked on the conference date.
- Outcomes: log(1 + sum of snapshot likes/comments/views on videos PUBLISHED on
  that date across the unit's distinct linked YouTube source entities).
- True covered zero-post days remain zero. Unmatched channels are not zero.
- Same-day publication is NOT necessarily after the conference. These measures
  are NOT engagement increments observed on that date; lifetime/snapshot timing
  is an important limitation.
- No winsorization in the primary regressions or new main FEct fits.
- Baseline: log1p(Y_it) ~ ask_it | unit_id + date.
- Adjusted: baseline plus fixed prior ratio x calendar-quarter interactions.
- Outlet-clustered SEs; 95% confidence intervals; no significance stars or
  multiple-testing adjustment. Coefficients are not automatically raw-outcome
  percentage effects.

### Historical control

Exactly the prior-year measure used in the final balance tables:
April 18, 2021-April 17, 2022, common attendance/question coverage only.
November 2021 is excluded from BOTH numerator and denominator.
Ratio = total QUESTIONS / recorded JOURNALIST ATTENDANCE RECORDS.
This is not a question-day probability and not question days / attendance days.

Use the frozen ratio audit from output/balance/prior_ratios/models.rds.
It is deliberately not recalculated against a different source vintage.
Contemporaneous attendance/question values and the source crosswalk are freshly
checked against that saved balance sample; a mismatch stops the script.
Raw missing ratios stay missing. For estimation: zero placeholder plus
missing-ratio-by-quarter indicators. 2022 Q2 is the omitted reference quarter.
Standalone histories and metadata would be absorbed by outlet FE; they are NOT
mistakenly appended as time-invariant adjustment regressors.

## Sample attrition: user explicitly asked why so few outlets

| Stage | Units | Outlet-days |
|---|---:|---:|
| All recorded post-lottery attendance source units | 111 | 16,223 |
| Unambiguous attendance-question source pair | 99 | 15,981 |
| Both sources matched and date observed | 82 | 9,759 |
| Established recorded-attendee balance sample | 81 | 7,976 |
| YouTube metadata link | 67 | 7,029 |
| All linked YouTube entities matched/covered | 60 | 6,508 |
| Dates still containing asking and nonasking outlets | 60 | 5,308 |
| Main TWFE after singleton removal | 55 | 5,303 |
| FEct: five untreated dates + quarter/history overlap | 50 | 5,256 |

Main model: 258 dates and 313 treated outlet-days. FEct: 256 dates and 311 treated
outlet-days. Main baseline and adjusted samples are identical.
Main dates run April 19, 2022-September 27, 2024.

The five singleton units each have only one usable observation, all nonasking:
eje central, la hoguera, noticias zmg, quadratin, quinto poder.
Outlet FE absorb their sole observation, so fixest removes them. Nothing was
deleted from source data. FEct's five-untreated-observation rule is different.

YouTube mapping excludes ambiguous shared channels rather than duplicating an
outcome; NONE was found across these resolved source units. Several units have
multiple subsidiary channels, each summed once. Do not confuse 55 aggregated
outlet units with the number of metadata outlets or with 165 legacy channels.
The builder also checks canonical UC channel identifiers across linked source
entities, not only normalized source keys; see canonical_channel_id_audit.csv.

### Incomplete channel coverage: a high-priority next choice

The primary specification requires ALL metadata-linked YouTube entities to
have matched source data. This conservative rule was explicitly disclosed.
Two units have some usable channels but one missing channel:

- Grupo Canton: tvbasta and tabascohoyradio available; lavozdeqroo unmatched.
- Sonora Power: sonorapower available; vigiliasonora1718 unmatched.

Five additional units have no matched linked YouTube entity:
IMER (imernoticias), El Pais (elpais), Sin Embargo (sinembargoalaire),
The Mexico News (memeyamel), Rompeviento (rompevientotv).

Fourteen of the original 81 units have no YouTube crosswalk link.
The earlier attendance funnel is also material: 111 recorded source units over
610 dates, 99 with unambiguous question pairs, 82 jointly observed over 398 dates,
then 81 over the 318 dates with both askers and nonaskers. This was inherited
from the balance sample, not a new YouTube restriction. The twelve units without
an unambiguous paired link include Lord Molecula Oficial. See
upstream_attendance_flow.csv and unresolved_attendance_units.csv.
See channel_coverage_audit.csv, excluded_youtube_units.csv,
channel_mapping_audit.csv, and analysis_units.csv for the exact audit.
An observed-channel-only sensitivity could restore the two partial units, but
changes the outcome to the available-channel total. Do not silently fill the
missing channels with zero, and do not overwrite the complete-coverage run.

## Primary first-pass findings

| Outcome | Baseline coefficient | p | History-adjusted coefficient | p |
|---|---:|---:|---:|---:|
| Likes | 0.0559 | 0.524 | 0.0652 | 0.393 |
| Comments | 0.0952 | 0.327 | 0.0923 | 0.300 |
| Views | 0.182 | 0.123 | 0.207 | 0.0553 |

All adjusted estimates are positive; none rejects zero at 5%.
Do not describe these as clear positive causal effects. Read exact CIs and
unrounded values from regression_results.csv, not this rounded summary.

On the separately supported FEct sample (50 units, 5,256 rows), the adjusted
ATTs are:

| Outcome | FEct ATT | 95% CI | p |
|---|---:|---|---:|
| Likes | 0.0570 | [-0.1055, 0.2194] | 0.4919 |
| Comments | 0.0932 | [-0.0887, 0.2752] | 0.3152 |
| Views | 0.1868 | [-0.0321, 0.4057] | 0.0944 |

The corresponding paired-sample adjusted TWFE coefficients are 0.0638, 0.0948,
and 0.2013, respectively. No adjusted FEct result rejects zero at 5%.

Saved sensitivities:

1. Two-way outlet/date clustered inference for baseline and adjusted models.
2. Winsorized (1st/99th percentiles of raw outcomes), then log1p, adjusted.
3. Adjusted regression restricted to observed prior history.
4. Date FE only.

Two-way covariance calculations sometimes required fixest's non-PSD repair.
Warnings are recorded in regression_results.csv; primary outlet clustering
did not generate those warnings. Main history controls had no collinearity drops.

## FEct robustness

Six NEW fits: three outcomes x baseline/adjusted, 1,000 outlet bootstraps each,
seed 20261012, method fe, force two-way, min.T0 = 5, parallel = FALSE.
Stored under fect_1000/, with exact inputs and package version for safe resume.
Never reuse a fit unless its input object matches.

This is an unbalanced attendee-only sample. Absent dates/cells do NOT become
nonattendee controls. No attendance dummy is needed: all included cells are
recorded attendance. The row and treated-cell counts are checked against FEct's
observation mask.

Before FEct, restrict common support and select a full-rank control basis in
UNTREATED data, after residualizing outlet/date FE. The missingness interactions
for 2022 Q4 and 2024 Q3 are redundant there and are omitted. See
fect_control_rank_audit.csv. Paired TWFE models use exactly this sample and
control basis; therefore compare FEct with these paired estimates before
comparing with the main 5,303-observation estimates.

An initial attempt had one unsupported treated missing-history observation in
2022 Q4. It was interrupted before completing the adjusted model. Corrected
support requires untreated observations for each missing-history-by-quarter
cell; removes the unsupported treated cell; rechecks informative dates and
five-untreated-date support; and verifies that controls redundant in untreated
data are also redundant over the whole supported sample. This removes the
November 14, 2022 asking observation for Noticieros El Reloj and that now
noninformative date. Meganoticias' October 28, 2022 treated observation is removed
by the minimum-untreated requirement. Primary TWFE is unchanged.

Each FEct ATT is independently checked against an untreated-only fixest
regression, predicting treated observations and averaging their residuals.
Numerical tolerance is 1e-4. Check valid_bootstraps, not only requested draws.
Bootstrap resamples can lose rare missing-history groups, producing collinearity
messages. Automatic event-time F tests can be singular in this sparse panel;
do not use these as evidence of parallel trends.

For speed, individual outcomes can run in parallel processes using
--outcome=likes, --outcome=comments, --outcome=views. Each writes separate
results_OUTCOME.csv checkpoints atomically. The last finishing process collects
all available outcomes into results.csv. Before export, require 12 rows (six
FEct estimates and six paired TWFE estimates) and 1,000 valid draws per FEct fit.

This first pass is STATIC: untreated cells are not cleaned of recent-question
carryover. The result requires assumptions on carryover/anticipation and
treatment feedback. No new event-study graph or exact randomization test was run.
Also, FEct targets a treated-observation ATT, whereas TWFE has regression weights;
heterogeneous effects can produce differences even on the same sample.

### Prior FEct results

legacy_fect_reference.csv contains the existing pooled raw-log1p, 1,000-bootstrap
same-question-day estimates from output/fect_youtube/.
They use a full-calendar CHANNEL panel and an attendance dummy, not this
recorded-attendee, aggregated source-unit panel, and extend beyond this sample.
They are reference results only, NOT a like-for-like robustness comparison.
Do not quietly relabel them as using the new history adjustment.

## Next steps to discuss

1. Whether to add the observed-channel-only sensitivity for partial units.
2. Next-day and next-seven-day publication outcomes, with complete follow-up;
   use log1p of the total raw outcome, not a sum of daily logs.
3. Temporal-ordering audit using upload timestamps if feasible.
4. Recent-treatment histories, clean comparison windows and carryover tests.
   Do not count adjacent observed attendance dates as adjacent calendar days.
5. Heterogeneity is implemented below; consider simpler prespecified history
   adjustment and stronger small-cluster inference before treating it as confirmatory.
6. Distinguish within-attendee asking effects from true randomized-seat ITT.
7. Multiple-outcome inference if this becomes confirmatory.
8. Same-day recorded journalist counts: outlets can send different numbers of
   journalists, which may change the chance of asking even among attendees.
   Consider a prespecified count control or appropriate assignment strata once
   the actual seating rules can be established.

The balance analysis and its manually styled compact scriptsize table remain
unchanged by this workflow. Its current table combines histories and metadata
on one page; older root handoff statements saying two pages are stale.

## Ideology heterogeneity — October 12, 2026

Completed: all 18 subgroup regressions and 18 FEct fits validate, including
18,000 finite bootstrap draws and independent checks of every FEct ATT. The
three-page PDF was rendered and visually checked; all four LaTeX fragments
compile together. Final FEct samples are 219 rows / 7 outlets / 44 dates for
opposition; 1,061 / 18 / 151 for aligned; 696 / 21 / 81 for independent.

Requested extension: opposition, aligned and independent separately, retaining
the same likes/comments/views outcomes and baseline/history-adjusted models.
The pooled models, source data and prior reports are not overwritten.

### Classification and sample

Use metadata_outcome_crosswalk.parquet, outcome = attendance, joining entity_id
to the existing unit_id. Take consensus of nonmissing ideology_4t codes across
metadata subsidiaries: opp = Opposition; aligned = Aligned; unclear = Independent.
Independent is a label for the existing unclear code, not independently verified
neutrality. La Jornada has both aligned and unclear subsidiary codes and is
excluded from the subgroup analysis, without changing its pooled observations.
The member-level and source-unit classification audits are saved.

Within each group, retain dates with both asking and nonasking recorded attendees.
This is more restrictive than asking/nonasking variation across all groups.
Then remove outlet-FE singletons as before. Main baseline and adjusted samples:

| Group | Outlet-days | Outlets | Dates | Asking outlet-days | Ever-asking outlets |
|---|---:|---:|---:|---:|---:|
| Opposition | 223 | 8 | 44 | 45 | 6 |
| Aligned | 1,080 | 20 | 153 | 173 | 18 |
| Independent | 703 | 23 | 83 | 86 | 19 |

Adjusted coefficients (p-values), likes/comments/views respectively:

- Opposition: -0.1408 (.538), 0.1424 (.072), 0.1935 (.355).
- Aligned: 0.1443 (.241), 0.1589 (.286), 0.1978 (.190).
- Independent: 0.1493 (.318), 0.1080 (.349), 0.3162 (.192).

None rejects zero at 5%. The stacked model has group-by-date FE and
group-specific history slopes, reproducing all separate group point estimates.
Between-group covariance clusters by outlet with the stacked model's common
finite-sample correction. For t/F reference distributions use the smallest
compared group outlet count minus one (7 for the three-group joint test).
Adjusted equality-test p-values: likes .458, comments .953, views .900.
Pairwise difference tests are also saved. Failure to reject is NOT evidence of
equal or absent effects: opposition has only eight clusters and low power.

### Subgroup FEct safeguards

Keep >=5 untreated recorded-attendance dates per unit and informative dates.
Quarter-by-missing-history overlap alone is insufficient for sparse subgroups.
The new script also checks full untreated-design estimability using a QR basis
of unit FE, date FE and all intended history interactions. Dependent-column
identities must hold on treated rows; otherwise remove those unsupported rows
and iterate all support restrictions to stability. The adjusted-supported
sample is common to baseline and adjusted models within each group.

An initial opposition manual check failed because fixest removed untreated FE
singletons; the independent check found a nonestimable history counterfactual.
These were not reported as completed estimates. Use fixef.rm = none for the
manual untreated regression, alongside the explicit full-design estimability
check, to preserve identified singleton FE predictions without extrapolating
unidentified ones. Independent Healy's February 17, 2023 asking cell is excluded
by the stricter support check; the noninformative date is then removed.

Each fit uses 1,000 outlet bootstrap draws and is checked against independent
untreated-only imputation. Bootstrap resamples can drop collinear controls;
finite draws alone do not resolve small-sample fragility. Do not use the
automatic event-time tests as proof of parallel trends. Paired-sample TWFE
estimates are exported separately to distinguish support from estimator changes.

### Files and rerunning

- Code: 05-heterogeneity.R; 06-heterogeneity-fect.R;
  07-export-heterogeneity.py; 08-validate-heterogeneity.R.
- Outputs: MEDIA_ROOT/results/effect_of_asking/heterogeneity/.
- Each group's FEct fits: GROUP/fect_1000/, with baseline/adjusted RDS files,
  per-outcome result checkpoints and results.csv.
- PDF: output/pdf/effect_of_asking_youtube_heterogeneity.pdf.
- LaTeX, under overleaf/tables/effect_of_asking/:
  heterogeneity_main.tex, heterogeneity_fect.tex,
  heterogeneity_paired_twfe.tex, heterogeneity_difference_pvalues.tex.
  All are scriptsize booktabs fragments without captions or notes.

Run 05 first; then 06 once for each --group=opposition, --group=aligned,
--group=independent, adding --nboots=1000 --resume. Different groups may run in
parallel processes. Run 08 to validate before exporting with 07. The exporter
requires all 18 FEct fits and 1,000 finite draws each. Re-read this section's
sample and classification caveats when interpreting the PDF.

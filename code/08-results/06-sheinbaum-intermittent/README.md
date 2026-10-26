# Sheinbaum: intermittent treatment, five weekdays

Replicates the AMLO full-calendar FEct approach for October 1, 2024 through June 15, 2025, with the user's five-weekday treatment window including the identified speaking day. Wednesday implies Wednesday, Thursday, Friday, Monday, Tuesday. Weekends are omitted from estimation, not classified as untreated. Weekday holidays count; this is not a five-conference-date window. June 15 is Sunday, so the last estimation date is June 13.

## Design

- Start with the existing full daily YouTube outlet panel, retaining every outlet with recovered videos anywhere in the source history. Use all 125 canonical outlets rather than the attendee-only main-regression sample. No-video days and missing counters retain the original zero-fill convention. Archive-completeness flags do not filter the sample.
- Treatment is one on the identified speaking day and next four weekdays. Speaking identification is the existing transcript proxy, not exhaustive question coding. Repeated events extend the union of windows; events are never deleted to force the ballot assumption. The full calendar is preserved separately.
- The missing May 2 transcript creates uncertain exposure on May 2, 5, 6, 7 and 8. Those dates have no known untreated outlets: 547 cells have unknown treatment, and the other 78 are known treated but lack untreated date support. All five dates are excluded from estimation. Events known on excluded dates still contribute to subsequent exposure windows.
- Final sample: 125 outlets, 179 weekdays, 22,375 observations; 3,426 treated outlet-days, 78 ever-treated outlets, 7,717 zero-video observations. There are 736 source speaking events, 717 within the estimation sample. No outlet is lost for missing histories or intermittent video output.
- Treatment windows are constructed before removing unsupported dates, using the original weekday sequence. The five omitted weekdays are never compressed out of treatment duration. The first window begins with the presidency; end-of-period windows stop at the lottery cutoff. There are 22 right-truncated windows and 49 repeated events within an ongoing window.

## Estimator and outcomes

Use `fect` 2.4.5, `method="fe"`, `force="two-way"`, `min.T0=5`, ordinary outlet/entity bootstrap with 1,000 draws, seed 20261026. FEct estimates the untreated outcome model using D=0 observations and imputes counterfactuals for D=1 observations. ATT averages across treated outlet-days (not equally across events or outlets). Report package normal-approximation intervals and p-values from the bootstrap standard errors; these are not wild-bootstrap p-values or percentile intervals. Six outcome tests are unadjusted for multiplicity.

All six daily outcomes are upper-p99 capped on the pooled weekday estimation sample, then asinh transformed: video count, interactions (likes + comments), interactions per video, likes, comments, views. Ratios divide by all recovered videos and are zero without videos. Engagement comes from the recovered cumulative video counters attributed to publication day; it is not engagement accrued on that calendar day. Transformed coefficients are not direct percentage effects.

Both specifications include recorded attendance OR identified speaking as an attendance dummy, matching AMLO. This is a contemporaneous conditional specification: if treatment changes subsequent attendance, conditioning on it can change the estimand from a total effect. The adjusted model adds prior-year AMLO question/attendance ratio and its missingness indicator interacted with 2025Q1/Q2 (2024Q4 reference). Seventy outlets have observed histories; the rest remain in the model with missingness controls.

The five-day exclusion rule and effect horizon are maintained assumptions, not verified facts. Ballot exclusion does not itself establish no anticipation, parallel untreated outcomes or absence of carryover after day five. Repeated speaking can reflect exceptions or identification issues. These pooled results precede event-time, placebo, carryover and alternative-window checks.

References: AMLO scripts `code/08-results/01-effect-of-asking/18-build-full-calendar-fect.R` and `19-run-full-calendar-fect.R`; earlier intermittent weekly code `code/07-final_panel/15-run-asinh-event-studies-fect.R`. [Official FEct manual](https://yiqingxu.org/packages/fect/02-fect.html).

## Run and validation

From repository root:

```sh
.venv/bin/python code/08-results/06-sheinbaum-intermittent/00-build.py
Rscript code/08-results/06-sheinbaum-intermittent/01-estimate.R --nboots=1000 --resume
.venv/bin/python tests/test_sheinbaum_intermittent.py
Rscript tests/test_sheinbaum_intermittent.R
python3 code/08-results/06-sheinbaum-intermittent/02-report.py
```

Reporting requires ReportLab (the bundled Codex Python supplies it). The R runner accepts repeated `--outcome=...` for independent jobs. Each fit saves its exact data, formula, seed, package version and panel MD5. Resume requires identical inputs. Source SHA256 hashes are captured and verified during construction. Every fit independently checks FEct's ATT and attendance coefficient against a `fixest` untreated-only regression, exact sample dimensions, treated-cell count, and finite bootstrap draws. Python tests independently expand event dates to verify treatment, check weekend/unknown handling and source outcome preservation.

Results live at `MEDIA_ROOT/results/sheinbaum/intermittent_did/five_weekdays_including_question/`; `fect_1000` contains final models. `fect_5` is smoke validation only. The earlier `seven_days_including_question` directory is a superseded exploratory panel with no final results. This analysis does not rebuild participation panels or change outlet aliases.

For this run, R used its installed Accelerate BLAS through temporary process-specific library symlinks, with one BLAS thread per process. No installed R libraries were modified.

## Initial results (October 26, 2026)

History-adjusted ATT and bootstrap p-values:

| Outcome | ATT | p-value |
| --- | ---: | ---: |
| Videos | 0.0294 | 0.1381 |
| Total interactions | 0.1308 | 0.0244 |
| Interactions per video | 0.1119 | 0.0144 |
| Likes | 0.1242 | 0.0322 |
| Comments | 0.0617 | 0.1013 |
| Views | 0.2119 | 0.0036 |

Baseline results have the same signs and the same set of outcomes below p=0.05. These are transformed-outcome ATT estimates under the maintained assumptions, with no multiplicity adjustment. All twelve model validations and 12,000 finite bootstrap draws passed. The three-page report is `output/pdf/sheinbaum_intermittent_did.pdf`; the data directory also contains `index.html` and machine-readable results.

## Held-out diagnostics and alignment heterogeneity

Follow-up scripts:

```sh
.venv/bin/python code/08-results/06-sheinbaum-intermittent/03-build-diagnostics.py
Rscript code/08-results/06-sheinbaum-intermittent/04-estimate-diagnostics.R --mode=diagnostics --nboots=1000 --resume
Rscript code/08-results/06-sheinbaum-intermittent/04-estimate-diagnostics.R --mode=heterogeneity --nboots=1000 --resume
.venv/bin/python tests/test_sheinbaum_diagnostics.py
Rscript tests/test_sheinbaum_diagnostic_results.R
.venv/bin/python code/08-results/06-sheinbaum-intermittent/05-plot-diagnostics.py
python3 code/08-results/06-sheinbaum-intermittent/06-report-diagnostics.py
```

Outputs are in `diagnostics_heterogeneity/` beneath the existing data directory, with a separate PDF at `output/pdf/sheinbaum_intermittent_diagnostics_heterogeneity.pdf`. The original results remain unchanged.

### Diagnostic windows and support

Known 0-to-1 transitions define onset; known 1-to-0 transitions define exit. Unknown treatment is never a transition, and the full original weekday sequence determines distance. A new question during an existing spell does not create another onset; the union ends only when treatment returns to zero. We examine the five continuously untreated weekdays before onset and the five continuously untreated weekdays after exit. Post day 1 is the first day outside the treated spell, not the day after the question.

Both windows are held out jointly from the untreated regression. This implements the FEct out-of-sample placebo/carryover principle with explicitly constructed masks, rather than allowing package event-time indexing to compress the five omitted May weekdays. An untreated cell that belongs to both windows is ambiguous: hold it out of training and omit it from diagnostic targets. The diagnostic sample has 927 such cells; the full sample has 1,079. Event-time composition is not balanced. All targets and their counts are exported.

The diagnostic sample requires at least five remaining untreated training dates per outlet. Avan Noticias (0), Healy (0) and NX Noticias (4) fail that requirement. Diagnostic estimation uses 122 outlets, 21,838 rows, 14,531 training cells, 1,667 pre targets and 1,557 carryover targets. There are no unsupported date effects after these restrictions. Target counts range from 267 to 420 per pre day and 240 to 398 per post day. The original full-calendar outcomes and p99 caps are preserved.

The primary diagnostics are history adjusted. The pooled ATT sensitivity compares original versus held-out training on the SAME 122-outlet sample. This holds composition fixed, but does not make the resulting estimates causal or remove selection bias. Conditioning on attendance still has the interpretation caveat above.

### Imputation and inference

`04-estimate-diagnostics.R` implements the FEct `method="fe"` point estimator as an untreated-only `fixest` regression and averages prediction errors over the required cells. All six original adjusted package FEct estimates are reproduced within 1e-4 before either analysis starts. The custom implementation permits exact weekday masks and paired group differences. It does not call package `placeboTest`, `carryoverTest` or `loo` options, nor report in-sample residual plots as diagnostics.

Each analysis uses 1,000 ordinary outlet bootstrap draws (seed 20261027), refitting all counterfactual models. Frequency weights represent literal replicated outlet clusters; an independent test checks equality with explicit resampling that assigns new IDs to duplicates. No failed draw is discarded. Saved RDS files contain input panel MD5, units, software version, point estimates and every paired bootstrap draw. Resume requires matching saved inputs; after changing model code, regenerate checkpoints.

Diagnostic average intervals/p-values use bootstrap standard errors with a normal approximation. For each outcome, a joint zero-deviation test uses the maximum absolute t-statistic across the five pre (or post) days, calibrated against centered bootstrap errors. Joint p-values have a plus-one correction. The 95% simultaneous bands use the 95th percentile of that same centered maximum statistic. These tests adjust across the five days within a test/outcome, not across six outcomes or both diagnostic families. No equivalence threshold was specified, so failure to reject never establishes negligible departures.

### Heterogeneity

The existing canonical-outlet metadata crosswalk determines alignment. All linked brand codes must agree: `aligned` is Aligned; `opp` or `unclear` alone maps to Opposition + Independent. Mixed codes or missing labels are excluded, even if mixed codes would fall within the combined comparison group, matching the prior strict rule. `unclear` does not establish political neutrality. Labels are fixed, not re-estimated from these outcomes.

Original heterogeneity uses 106 outlets (33 aligned, 73 comparison), 18,974 weekday rows and 2,896 treated cells. Nineteen outlets have missing/conflicting classifications. It retains the three frequent outlets excluded from diagnostics. Both groups share the untreated outcome model's date effects, attendance coefficient and history slopes; outlet effects are specific. Group ATTs average treated residuals within each group. The directly estimated gap is Aligned minus Comparison in each bootstrap draw. Sampling is stratified by alignment group so group sizes remain fixed; uncertainty comes from resampling outlets within each group.

Held-out training sensitivity uses 103 classified outlets (32 aligned, 71 comparison); its composition differs from the original heterogeneity sample. The baseline and adjusted group effects, direct gaps, all SEs and all paired draws are saved. A group being significant while the other is not is not treated as evidence of a difference. Neither group heterogeneity nor the held-out sensitivity cures failed pre-treatment or carryover diagnostics.

For the heterogeneity sensitivity, resampling starts from the original 106 classified outlets and then applies the fixed diagnostic-eligibility restriction. Thus original group sizes are fixed in each draw, while the number of retained eligible copies can fluctuate. Each eligible group's ATT uses its retained treated-cell weights; group differences remain paired within each draw.

### Follow-up results (October 26, 2026)

The history-adjusted, held-out joint pre-treatment test rejects zero deviations for five of six outcomes at the nominal 5% level: interactions p=0.0170, interactions/video p=0.0100, likes p=0.0420, comments p=0.0320, views p=0.0250; videos p=0.1329. These tests account for five days within each outcome, but not multiple outcomes. The patterns raise concerns about the original causal interpretation; they can reflect anticipation, selection or outcome-model misspecification.

Carryover is less conclusive: interactions/video joint p=0.0430, views p=0.0599, interactions p=0.0849, likes p=0.1139, comments p=0.2248, videos p=0.3656. No five-day carryover average rejects at 5%; joint tests can detect individual days even when the average is imprecise. Non-rejection does not establish negligible carryover.

Original history-adjusted aligned-minus-comparison gaps are positive for all outcomes, but none is significant: videos 0.0683 (p=0.1036), interactions 0.2018 (p=0.1217), interactions/video 0.1303 (p=0.2174), likes 0.2141 (p=0.1017), comments 0.0975 (p=0.2670), views 0.2055 (p=0.2193). Baseline conclusions are unchanged. The held-out sensitivity also has no significant group gaps (adjusted p range 0.1119-0.2944). This is imprecision, not proof of equal effects.

All original adjusted FEct point estimates matched the independent implementation. Both analyses completed all 1,000 paired bootstrap draws without discarding failures. Independent tests verified event labels, source hashes and outcome preservation, explicit versus weighted whole-outlet resampling, group gaps on every draw, and reported SEs/joint tests. The five-page PDF and HTML report include both diagnostic plots, baseline/adjusted heterogeneity and the matched-sample training sensitivity.

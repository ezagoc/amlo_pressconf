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

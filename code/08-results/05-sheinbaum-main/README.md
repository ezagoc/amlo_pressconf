# Sheinbaum main YouTube results

Completed October 26, 2026. Pooled same-day regressions corresponding to the
AMLO main daily tables; no raw sources or AMLO estimates are modified.

## Specification copied from AMLO

Reference implementations:

- `code/08-results/01-effect-of-asking/01-build-and-estimate.R`: recorded-attendee
  sample, outlet/date fixed effects, prior-ratio-by-quarter adjustment.
- `16-daily-six-outcomes-winsor99.R` in that folder: six all-video outcomes,
  pooled-sample upper-p99 cap before log(1+x), baseline/history-adjusted pairs.
- `11-wild-cluster-bootstrap.R`: 9,999 null-imposed outlet Rademacher draws,
  WCR11/fnw11, seed 20261012 and matching small-sample settings.

The Sheinbaum exposure is explicit transcript outlet identification on that
conference date, a speaking-access proxy. It is not labeled exhaustive question
coding. Eligible rows require directly recorded REPORTERO/YOUTUBER attendance,
usable roster/transcript dates and a linked recovered YouTube channel.
The attendance window is October 1, 2024–June 15, 2025 (user lottery cutoff).

Outcomes: videos; likes + comments; interactions per video; likes; comments;
views. Every outcome uses all recovered videos published that day. The corrected
balanced daily panel supplies zeros on no-video days, sums missing counters as
zero, and uses all recovered videos as per-video denominators, zero when no
videos. No archive completeness condition or positive-video filter is imposed.

Main models: each raw outcome upper-capped at the pooled estimation sample's
99th percentile (R type 7), then log(1+x). Both baseline and adjusted models
have outlet and conference-date fixed effects and outlet-clustered SEs.
Adjusted models add the prior-year AMLO questions/recorded-attendance ratio
(2023-10-01–2024-09-30) interacted with calendar quarters, omitting 2024Q4.
Undefined ratios have estimation placeholders plus matching quarter-specific
missingness indicators. Four controls are identified: ratio and missingness
interacted with 2025Q1 and 2025Q2. No other historical covariate is silently added.

An uncapped log(1+x) sensitivity repeats all twelve models on identical rows.
It reports conventional outlet-clustered inference. The twelve main models
add the same wild-bootstrap inference as AMLO. No heterogeneity, FEct, event
study or full-calendar attendance-dummy specification is estimated here.

## Sample and results

The balance sample has 6,230 rows and 96 outlets. Outlet/date fixed effects
remove two singleton outlets (two rows), leaving **6,228 rows, 94 outlets,
163 conference dates**, October 2, 2024–June 13, 2025. There are 683 identified
speaking days, 75 outlets with within-outlet exposure variation, and **1,387
zero-video days retained**, including 168 identified-speaking days. Twenty-eight
outlets have undefined prior ratios, handled with missingness interactions.
All 24 models use the exact same rows; exclusions are saved separately.

Main history-adjusted results (log1p after upper-p99 cap):

| Outcome | Coefficient | Clustered p | Wild-bootstrap p |
|---|---:|---:|---:|
| Videos | 0.019 | 0.313 | 0.330 |
| Total interactions | 0.108 | 0.150 | 0.157 |
| Interactions/video | 0.090 | 0.143 | 0.151 |
| Likes | 0.096 | 0.196 | 0.206 |
| Comments | 0.080 | 0.200 | 0.219 |
| Views | 0.194 | 0.058 | 0.063 |

All point estimates are positive; none of the adjusted tests rejects zero at
5%. Baseline views are marginal: coefficient 0.197, conventional p=0.046,
wild p=0.049. The uncapped sensitivity is nearly unchanged. These p-values
are unadjusted across outcomes; the marginal baseline result is not evidence
of a robust effect across all specifications.

These are conditional associations. The prior balance tests found observable
selection, and transcript identification is a speaking proxy. Engagement values
are later cumulative snapshots for videos published on a date, not engagement
accrued on that date. Log1p coefficients should not automatically be reported
as percentage effects on raw outcomes.

## Files and reproduction

Run from repository root:

```sh
Rscript code/08-results/05-sheinbaum-main/01-estimate.R
Rscript tests/test_sheinbaum_main.R
python code/08-results/05-sheinbaum-main/02-report.py
```

R uses the installed `fixest` and local `tmp/Rlibs/wildclusterboot` libraries.
The report needs reportlab and bundled Ubuntu fonts. Source inputs are the
current balance sample and corrected outlet daily panel; hashes are verified
before and after estimation, and saved in `input_manifest.csv`.

Outputs: `MEDIA_ROOT/results/sheinbaum/main_results/lottery-through-2025-06-15/`:
analysis panel (.parquet/.rds), all 24 fits, regression CSV, caps, sample summary,
singleton exclusions, twelve saved bootstrap objects and diagnostics, manifest,
session info and HTML report. PDF: `output/pdf/sheinbaum_main_results.pdf`.

Validation independently applies iterative singleton pruning, reconciles
outcomes to the source panel, verifies zero-video rows remain, reconstructs
all 24 coefficients via within-fixed-effect OLS, checks CIs, and reproduces
all twelve bootstrap p-values from 119,988 saved finite draws. The final PDF
is rendered and visually checked.

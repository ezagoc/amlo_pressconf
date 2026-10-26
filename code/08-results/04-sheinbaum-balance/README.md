# Sheinbaum balance and current YouTube panel

Updated October 26, 2026. This repeats the AMLO YouTube-outcome workflow,
starting with balance. No Sheinbaum YouTube effect regressions have been run.

## Original panel construction restored

The user explicitly requested the construction in
`code/06-outcomes/youtube/04-build_panel.py`. That script creates a full
channel-by-calendar-day skeleton, deduplicates videos, aggregates daily counts
and engagement with `sum`, fills missing daily totals with zero, and sets
per-video ratios to zero on no-video days. It excludes a channel only when
there are no recovered videos anywhere in the entire panel period.
`code/07-final_panel/05-build_deduplicated_outcome_panels.R` then sums channels
into source entities, and `code/08-results/balance/05-historical_outcome_balance.R`
sums the daily panel into historical windows, dividing totals by all videos.

The new `code/06-outcomes/youtube/09-build_extended_panel.py` uses that daily
sum-and-zero-fill construction with the existing local archives through 2026:

- Every recovered channel has every day in the common calendar. A day with no
  recovered videos has zero videos, views, likes, comments and publication.
- Missing video counters contribute zero under the original aggregation rule.
  Interactions equal likes plus comments. Per-video ratios divide by all
  recovered videos, with zero ratios on no-video days.
- Archive intervals, pagination caps and missing counters never exclude a date
  or outlet from this recovered-video panel. `archive_complete_interval` is an
  audit flag only. `source_date_observed` means the calendar row is present,
  not independently verified archive completeness.
- Channels with no recovered videos anywhere in the period are listed in
  `channels_without_recovered_videos.csv` and excluded, as in the original.
  Outlets without a recovered channel match remain unmatched, not fabricated
  zero-history outlets.

The prior completeness-based panel, the 48-outlet histories, and the later
metric-specific available-video averages are superseded. Historical covariates
now come directly from this daily panel, without a separate video-level formula.

## Inputs and outputs

The legacy `04-build_panel.py` cutoff was 2024, but local archives contain 2025
and 2026 videos. The extended builder reads original uploads, large-channel
archives, curated playlists and reviewed-channel downloads. It does not call an
API or change raw files. Output: `MEDIA_ROOT/data/06-outcomes/youtube/extended/`.
Legacy AMLO panels and estimates are left available for reproduction.

The corrected panel has **189 channels x 3,213 days = 607,257 rows**, from
2018-01-01 through 2026-10-18. Nine dimension channels have no recovered videos
anywhere in this period. All 1,640,344 unique dated recovered videos are counted
in daily totals, including 429,243 published in 2025 and 137,844 in 2026.
The previous 506,568-video exclusion based on archive intervals is removed.
The calendar ends on the latest complete retrieval day; individual retrieval
dates and pagination coverage remain available as diagnostics only.

The extension retains the existing physical-channel identity/crosswalk cleanup:
196 of 210 metadata URL rows resolve; zero ambiguous URL aliases. It also retains
the existing cross-archive snapshot convention: globally unique video IDs with
maximum available saved counters, rather than summing duplicated snapshots.
Nineteen video IDs with conflicting publication dates are separately quarantined
(all in 2026), rather than assigned guessed publication dates. These identity
and conflict audits are independent of the restored daily zero-fill rule.

`panel_daily.parquet` and `youtube_entity_daily_panel.parquet` are the channel
panels. The Sheinbaum builder aggregates each distinct linked channel once per
canonical outlet into `output/balance/sheinbaum_12m/youtube_outlet_daily.parquet`:
**125 outlets x 3,213 days = 401,625 rows**. Fields include unit/date, channels,
videos, views, likes, comments, interactions, publication and four per-video
means. The historical measures are sums of this panel in the baseline window;
per-video means are window totals divided by window videos, not averages of
daily ratios. Current engagement counters are cumulative archived snapshots
attached to publication dates, not daily engagement flows or counters verified
as measured before treatment. Publication days retain the UTC convention.

## Balance specification

Analysis: October 1, 2024–June 15, 2025, the user-specified lottery cutoff.
Actual conference dates end June 13. Later source attendance rows are retained
but excluded from this analysis. Histories: October 1, 2023–September 30, 2024.

Exposure is explicit outlet identification in the transcript, a speaking-access
proxy, not an exhaustive question indicator. Eligibility requires directly
recorded REPORTERO/YOUTUBER attendance and usable transcript/roster dates.
No imputed attendance or dated-affiliation-only presence. Only metadata-linked
outlets enter balance regressions. Dates without variation in speaking status
within each estimation sample are excluded. Zero-video days are not excluded.
The YouTube subset requires an outlet link to recovered channels; shared-channel
identity ambiguity is separately audited (none in the current crosswalk).

The latest AMLO specification supplies nine metadata flags and twelve histories,
with separate metadata/history joint tests and no age. Metadata flags use the
any-linked-brand rule and missing-flag-to-zero convention; entirely unlinked
outlets are audited separately. Mexico City means headquarters-state code 9;
metropolitan coverage is any explicit metropolitan label. Current metadata is
not verified historical status.

Prior access uses AMLO questions / recorded attendance on overlapping observed
dates. Missing or ambiguous source mappings remain missing; a zero denominator
is undefined. Contracts sum distinct linked beneficiaries with observed histories.
Neither access nor contract rules changed in this YouTube correction.
Histories use log(1+x), except the raw access ratio; no winsorization.

Individual regressions: characteristic ~ speaking identification | date,
clustered by outlet. Joint models: speaking identification ~ block covariates
+ distinct missingness indicators | date. The null tests substantive variables,
not missingness indicators. Joint histories are SD-scaled for conditioning;
missing values get placeholders plus indicators, not fabricated histories.
Each individual test uses its available history sample and informative dates.

## Verified current results

| Sample | Outlet-days | Outlets | Dates | Identified speaking days |
|---|---:|---:|---:|---:|
| All directly recorded attendees | 8,904 | 279 | 165 | 936 |
| Metadata-linked balance | 8,348 | 162 | 164 | 924 |
| YouTube-linked balance | 6,230 | 96 | 163 | 684 |

The YouTube-linked estimation sample retains **1,387 zero-video outlet-days**.
Before excluding uninformative conference dates, it has 6,305 rows on 165 dates.
All nine YouTube history measures now have 96 outlets in both samples. The full
sample retains 85 outlets for prior AMLO access and 61 for contracts; the
YouTube-linked subset has 66 and 54 respectively.

| Sample | Metadata joint p | Histories joint p |
|---|---:|---:|
| Full | 0.0000223 | 0.000140 |
| YouTube linked | 0.000287 | 0.000012 |

These are descriptive selection diagnostics. History covariance matrices remain
poorly conditioned (correlation condition numbers about 7.48m and 8.12m), so
interpret their joint tests cautiously. Individual p-values are unadjusted for
multiple testing. Prior provisional results using other coverage rules or the
September attendance endpoint are superseded by this construction and cutoff.

## Reproduction and validation

Run from the repository root:

```sh
.venv/bin/python code/06-outcomes/youtube/09-build_extended_panel.py
.venv/bin/python -m unittest discover -s tests -p 'test_extended_youtube.py'
.venv/bin/python code/08-results/04-sheinbaum-balance/00-build.py
Rscript code/08-results/04-sheinbaum-balance/01-estimate.R
.venv/bin/python -m unittest discover -s tests -p 'test_sheinbaum_available_histories.py'
Rscript tests/test_sheinbaum_balance.R
python code/08-results/04-sheinbaum-balance/02-report.py
```

The report command requires reportlab and bundled Ubuntu font files. The source
builder supports `--output-dir` and `--through`. Tests independently reconcile
all daily totals with deduplicated recovered videos using the original sum rule,
verify every channel/outlet has every calendar date, check no-video zeros remain
in the balance sample, reconcile histories with the daily panel, recover all
42 individual coefficients and check four joint-test p-values. Source hashes
confirm raw inputs were not modified.

Reports, samples, CSV tables, model RDS, mappings and audits:
`output/balance/sheinbaum_12m/`. PDF: `output/pdf/sheinbaum_balance_12m.pdf`.
Next step: estimate the AMLO-style outcome regressions from the corrected panel.

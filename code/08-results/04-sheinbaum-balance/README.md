# Sheinbaum balance and updated YouTube outcomes

Completed October 26, 2026. This is the entry point for repeating the AMLO
YouTube-outcome analysis in the Sheinbaum period, starting with balance.
No YouTube effect regression has been estimated in this workflow yet.

## Current inputs and coverage

The old `code/06-outcomes/youtube/04-build_panel.py` deliberately stops in 2024.
That limit did **not** describe the raw archives: they contain 2025 and 2026 data.
Use the new `09-build_extended_panel.py` and
`MEDIA_ROOT/data/06-outcomes/youtube/extended/` for this analysis. The old AMLO
panel and estimates remain available for reproduction; do not use their calendar
endpoint as the endpoint of the current YouTube data.

The extended build has 198 physical channel IDs and 636,174 channel-days from
2018-01-01 through 2026-10-18, the latest complete day before retrieval. The
archive contains 1,640,344 unique dated videos, including 429,243 in 2025 and
137,844 in 2026. Most older downloads end in March 2026; reviewed channels extend
into October. Coverage is channel-specific, not complete for every channel
through the global end date. The raw attendance source ends on September 30, 2025,
but the user now restricts the analysis to October 1, 2024-June 15, 2025, the
lottery stopping date they specified. Later roster rows are excluded from the
balance/regression sample, not deleted from the original source.

The extension:

- Includes the original videos, large-channel archives, curated playlists, and
  the newer reviewed-channel downloads. Deduplicates globally by video ID,
  using maximum available cumulative counters, not sums across copies.
- Uses physical channel IDs for outcome identities and joins metadata through
  returned handles, custom URLs and channel IDs. A metadata cell listing several
  channel URLs is not assigned wholesale to each individual channel. Of 210
  metadata URL rows, 196 resolve; unmatched links are exported, not guessed.
- Supports zero-video days only inside uploads-archive coverage intervals.
  Suspected capped uploads (about 20,000 videos) start strictly after their oldest
  downloaded uploads date. Older curated playlist additions do not prove complete
  all-video coverage. Retrieval days are partial and excluded. Complete pagination
  is an archive assumption, not independent proof that every historical video
  remains publicly available. Legacy archives lacking upload-pagination evidence
  contribute saved videos but do not establish all-video coverage by themselves.
- Leaves unavailable dates and unknown engagement metrics missing. Of the dated
  archived videos, 506,568 fall outside supported all-video intervals and remain
  in the archived-video export, not regression totals. This is principally a
  completeness restriction on older/capped archives, not removal of those raw files.
- Quarantines 19 videos with conflicting publication dates across saved snapshots;
  all candidate channel-days are marked unavailable. These conflicts are in 2026,
  outside the current attendance-period balance sample. Raw sources are unchanged.
- Retains the previous UTC publication-day convention. Engagement counters are
  later cumulative snapshots attached to publication dates, not daily engagement
  flows and not verified pre-treatment measurements.

## Balance specification

The specification follows the latest AMLO `14-separate_balance_without_age.R`:
9 metadata characteristics and 12 historical measures, with separate joint tests.
No founding age, combined metadata/history test, or extra question function.

The exposure is **explicit outlet identification in the transcript**, used as a
speaking-access proxy. It is not an exhaustive question indicator or question
count. The full-corpus journalist/outlet extraction is complete; the separate
question-answer extraction is not. A missing identification is not proof that
an outlet did not speak. These estimates must remain labeled accordingly.

Units are canonical conference outlets, one observation per date. Main eligibility
requires directly recorded REPORTERO/YOUTUBER attendance and usable coverage of
both transcript and roster. No imputed attendance or dated-affiliation-only
presence is added. Only metadata-linked outlets enter balance regressions;
metadata-unmatched attendees are separately audited. Dates without variation in
the speaking indicator within the applicable sample are excluded from estimation.

Individual fits: `characteristic ~ speaking_identified | date`, clustering by
`unit_id`. Binary coefficients are in proportion units. Joint fits reverse the
regression: `speaking_identified ~ block_covariates + missing_flags | date`.
The joint null tests substantive covariates only. There are no outlet fixed
effects because the histories and metadata are fixed characteristics.

History window: **2023-10-01 through 2024-09-30**. Access is AMLO questions per
recorded attendance entry on jointly covered dates, using fresh panels and the
new role filter. Ambiguous attendance/question source pairs are missing. Distinct
contract beneficiaries and physical YouTube channels are each counted once per
unit. Contracts and nine YouTube histories use log(1+x), no winsorization. Per-video
means are ratios of window totals. Complete channel grids are required for YouTube
histories; individual tests use observed 12-month histories and informative dates.
Unlike the older multi-window AMLO exercise, no availability in additional 18/24-
month windows is required here. Joint history fits use placeholders plus distinct
missingness indicators, leaving the original missing histories intact.

The nine metadata flags use the AMLO any-linked-brand rule and missing-flag-to-zero
convention. Entirely unmatched outlets are never assigned fabricated metadata.
Geographic definitions repeat its provisional coding: Mexico City = headquarters
state code 9; metropolitan coverage = an explicit metropolitan label for any metro
area. Metadata status is current, not verified at the historical cutoff.

## Verified results

| Sample | Outlet-days | Outlets | Dates | Identified speaking days |
|---|---:|---:|---:|---:|
| All directly recorded attendees | 8,904 | 279 | 165 | 936 |
| Metadata-linked balance | 8,348 | 162 | 164 | 924 |
| YouTube outcome-coverage balance | 5,164 | 89 | 161 | 607 |

Both estimation samples span October 2, 2024-June 13, 2025, the last observed
conference before the June 15 cutoff. Before excluding uninformative dates,
YouTube coverage has 5,280 eligible outlet-days on 165 dates.
The initial 55-date/70-outlet result used the outdated derived YouTube panel and
is superseded; do not report it as the current coverage. The subsequent 93-outlet /
235-date result used the longer September attendance window and is also superseded
by the user's June 15 cutoff.

| Sample | Metadata joint p | Histories joint p |
|---|---:|---:|
| Full | 0.0000223 | 0.0001025 |
| YouTube coverage | 0.00901 | 0.0001866 |

These are descriptive selection diagnostics, not evidence of random assignment
or causal effects. History covariances are highly ill-conditioned (correlation
condition numbers about 14.7m and 13.1m); interpret their joint tests cautiously.
The joint values were independently calculated and checked for invariance to
centering. Missingness patterns and row-specific individual sample sizes are
exported. Tests independently recover all 42 individual coefficients using
within-date demeaning and check all four F-test p-values, source coverage, and
roster eligibility. Individual p-values are not multiplicity adjusted.

## Reproduction and files

Run from the repository root:

```sh
.venv/bin/python code/06-outcomes/youtube/09-build_extended_panel.py
.venv/bin/python -m unittest discover -s tests -p 'test_extended_youtube.py'
.venv/bin/python code/08-results/04-sheinbaum-balance/00-build.py
Rscript code/08-results/04-sheinbaum-balance/01-estimate.R
Rscript tests/test_sheinbaum_balance.R
python code/08-results/04-sheinbaum-balance/02-report.py
```

The last command requires reportlab and the bundled Ubuntu font files. The build
can also take `--output-dir` and `--through`; it reads saved files only, with no API
calls. Source hashes are checked before/after both data builds. New output paths
avoid overwriting legacy AMLO outcomes or results.

Results: `output/balance/sheinbaum_12m/` (HTML, CSVs, model RDS, samples, source
mapping, prior-access, contracts, YouTube, coverage and missingness audits).
PDF: `output/pdf/sheinbaum_balance_12m.pdf`, five rendered and visually checked
pages. The extended YouTube directory contains physical-channel and entity-day
panels, deduplicated video metrics, metadata crosswalk, coverage intervals, source
fingerprints, conflict quarantine and annual counts.

Next: specify and estimate the same all-video outcome regressions on the updated
Sheinbaum sample, preserving coverage flags and the identification-proxy label.
The six outcomes can be constructed from the current video, view, like and comment
totals (interactions = likes + comments; mean interactions = interactions/videos,
zero only on genuinely covered no-video days).

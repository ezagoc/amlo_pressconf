# Sheinbaum participation analysis

This workflow uses the completed 503-date **journalist/outlet identity**
extraction, refreshed metadata, physical attendance records, and approved dated
affiliation links. It measures identified outlet participation, not the number
of individual questions. The separate question–answer extraction is incomplete.

## Rebuild and analysis

From the repository root:

```sh
.venv/bin/python code/07-final_panel/rebuild_panels.py --execute
.venv/bin/python code/07-final_panel/validate_rebuild.py --manifest outputs/panel-rebuild-RUN_ID/manifest.json
.venv/bin/python code/07-final_panel/sheinbaum_participation.py --through 2026-10-15
.venv/bin/python code/08-results/03-sheinbaum-participation/01-descriptives.py --through 2026-10-15
.venv/bin/python -m unittest discover -s tests -p 'test_sheinbaum_participation.py'
```

The first command backs up existing derived outputs before rebuilding metadata,
attendance, the historical metadata/day panel, and four outcome entity panels.
It prints the concrete manifest path to use in the next command. It does not
rerun extraction or estimation. Metadata geocoding reuses the cache and queries
only uncached addresses. The historical builders retain their 2012–2025 window
and AMLO question source; they do not add Sheinbaum identities as question items.

The separate Sheinbaum panel is saved under
`MEDIA_ROOT/data/02-conferences-sheinbaum/participation_panel/through-2026-10-15/`.
The analysis report, chart previews, CSV tables, and audit are under
`MEDIA_ROOT/results/sheinbaum/participation/through-2026-10-15/`.
Open `index.html` for the report. Both charts were checked as static previews;
the local HTML report was not browser-rendered during the build.

## Panel definition

There is one row per canonical outlet and observed conference date. Dates are
the union of transcript and physical attendance dates, not every calendar day.
Outlets are the union of identified and physically recorded source labels;
rare attendance labels are retained rather than applying the legacy >4 filter.
Metadata brands are grouped without multiplying outlet-date observations.
Source labels that remain unresolved can still describe the same organization.

| Variable | Interpretation |
| --- | --- |
| `identified` | Explicit identification on a completed extraction date; NA without transcript coverage |
| `identification_records` | Harmonized reporter/outlet/date records, not individual questions |
| `named_reporters` | Distinct nonmissing reporter names for this outlet/date |
| `recorded_attendance_n` | Eligible physical roster rows; NA when no roster exists |
| `assumed_attendance_n` | Existing flagged co-attendance assumptions, kept outside physical totals |
| `verified_dated_affiliation` | Approved exact label/date link; no extra physical row |
| `attendance_supported` | Direct recorded outlet presence or verified dated affiliation |
| `common_coverage` | Both sources observed, with at least five physical roster records |
| `ideology_4t` | Existing metadata classification; unclear, conflicting, and unmatched values remain explicit |

Zero identifies absence from an observed source, not proof of nonparticipation.
In particular, someone may speak without stating a journalist/outlet identity.
Missing reporter names are not inferred from attendance. Joint attendance
labels without a global canonical ID can support approved date-specific links
while remaining unassigned in the physical outlet counts.

Primary attendance-conditioned rates use only `common_coverage` dates:

`days with both identification and direct recorded attendance / recorded attendance days`.

The affiliation-supported counterpart is exported separately. Neither rate
adds unmatched identification days to its numerator. Alignment comparisons pool
outlet-days within the existing metadata groups; they are descriptive, not
adjusted or causal estimates. Top-rate rankings require ten recorded days.

## October 26 rebuild

The panel has 243,936 rows: 484 source outlet IDs × 504 observed dates. It covers
503 transcript dates (246 in the first year in office; 257 afterwards), 241
attendance dates, and 239 common usable dates. March 4, 2025 is excluded from
common coverage because its roster has one record; May 2, 2025 has a roster but
no transcript in the saved official corpus.

There are 3,294 identified outlet-days across 328 identity labels. The 13,277
physical attendance records include 89 without a canonical outlet. Seven identity
records lack an outlet. Those records remain audited rather than being assigned
to a fabricated outlet. All 28 approved dated links validate against real roster
rows. The top ten labels account for 19.4% of identified outlet-days.

Of 1,608 identified outlet-days on common usable dates, 1,425 have direct or
dated affiliation support and 183 remain unmatched. The unmatched-date export
also retains sparse-roster cases with their flag. No attendance after September
30, 2025 is inferred.

Next work is to review residual matches/metadata and specify a participation
model. Actual question counts, presidential response style, and evidence of
preparation require completing and reviewing the separate transcript analysis.

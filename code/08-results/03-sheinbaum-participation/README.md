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

When intentionally restricting attendance roles, add `--apply-current-role-filter`
to the validator. It applies the production R policy to backed-up physical rows,
regenerates flagged co-affiliation assumptions, and checks the resulting records
and outlet labels against the rebuilt output. It exports removed records beside
the manifest. Without this option, validation requires attendance to be unchanged.

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

## Cargo audit

The user confirmed REPORTERO and YOUTUBER as the only eligible attendance cargos
on October 26, 2026. `src/attendance_roles.R` uses exact normalized matching,
allowing gender/plural variants and the observed REPORTETO typo. All other roles,
including COLUMNISTA, CORRESPONSAL, ASISTENTE, AUDIO, missing values, and mixed
job labels, are excluded. Original roster files retain every role. This policy
restricts the attendance pool; it does not delete transcript speaking evidence.

Relative to the previous filter, 1,142 physical rows are removed, all before the
Sheinbaum period: 774 ASISTENTE, 189 CORRESPONSAL, one CORRESPONSAL Y, 88 COLUMNISTA,
42 POOL, 22 OTRO (ESPECIFICA, 21 INVITADO, two SUBDIRECTOR ED, and one each DIRECTOR,
PRODUCCIÓN, and TITULAR DEL NOT. This is 2.42% of the earlier 47,107 physical rows.
Audio, technical, camera, photographer, and student entries were already excluded.
Sheinbaum's 13,277 eligible rows and participation statistics are unchanged.
Historical estimates have not been refit for this revised attendance denominator.

Run `Rscript code/08-results/03-sheinbaum-participation/02-prepare-role-audit.R`
followed by `.venv/bin/python code/08-results/03-sheinbaum-participation/03-cargo-audit.py`.
The first step applies the production outlet cleaner to all original cargos,
without role/government exclusions or co-attendance imputation, and writes an
audit copy only. The second compares exact outlet/date and approved dated links
against transcript identities. Results and the HTML report are under
`outputs/sheinbaum-cargo-audit-20261026/`. Production inputs remain unchanged.

In the Sheinbaum attendance window, the original merged roster has 13,235
REPORTERO, 42 YOUTUBER, 1,269 FOTÓGRAFO, and 29 CAMARÓGRAFO rows. The retained
physical attendance multiset exactly matches the first two cargos. All YOUTUBER
rows belong to Lord Molécula Oficial during October–December 2024.

On the 239 common usable dates, the 1,608 identified outlet-days divide into
1,420 with REPORTERO (22 also have support roles), five with YOUTUBER but no
REPORTERO, one with only an excluded support role, and 182 unmatched. The lone
support-only case is El Financiero on June 3, 2025: its photographer entry is
excluded from attendance, while Angélica Guerrero explicitly introduces herself
and asks a question in the transcript. This is a roster-role discrepancy, not
evidence that a photographer asked the question. Attendance has no person names,
so roles cannot be assigned to individual speakers from outlet matching alone.

## Subsequent lottery-period analysis

For the new balance and YouTube regression workflow, the user specified
October 1, 2024-June 15, 2025 as the analysis window. The unrestricted descriptive
report above remains a full-source coverage audit. Use
`code/08-results/04-sheinbaum-balance/README.md` for the restricted regression
samples and updated YouTube outcomes extending into 2026. Do not carry this
report's September attendance endpoint into the lottery-period estimates.

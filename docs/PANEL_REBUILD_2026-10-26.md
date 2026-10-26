# Panel rebuild and initial Sheinbaum analysis — October 26, 2026

The user authorized rebuilding after completing outlet reconciliation. The
metadata, attendance, final daily panel, and four deduplicated source panels
have now been rebuilt. The first Sheinbaum participation analysis is available
in a separate panel/report; it does not substitute identity records for questions.

| Output | Refreshed dimensions |
| --- | --- |
| Processed metadata | 359 rows, up from the prior processed snapshot's 245 |
| Historical metadata/day panel, 2012–2025 | 1,835,926 rows × 137 columns |
| Attendance entity/day panel | 229 entities; 1,171,106 rows |
| AMLO questions entity/day panel | 224 entities; 1,145,536 rows |
| Contracts entity/day panel | 118 entities; 603,452 rows |
| YouTube entity/day panel | 206 entities; 1,053,484 rows |
| Sheinbaum outlet/conference-date panel | 484 source IDs; 243,936 rows across 504 dates |

The source panel entity counts reflect metadata linkage and differ from the
broader Sheinbaum source-label universe. Outcome entity panels preserve NA for
unobserved source dates. The legacy metadata/day export retains its earlier zero
filling; analyses using it must obtain coverage flags from the entity panels.

Validation confirmed all existing metadata IDs/name assignments were preserved
(including the pre-existing unnamed row), as were all physical attendance rows
and approved clean attendance labels. All panel keys are unique. Original input
hashes remained unchanged. Source-panel missingness checks, four synthetic
Sheinbaum participation tests, and reviewed-outlet linkage tests passed.

Build manifest and read-only validation results:

- `outputs/panel-rebuild-20261026T204129Z/manifest.json`
- `outputs/panel-rebuild-20261026T204129Z/validation.json`
- Original derived files: `recovery/panel-rebuild-20261026T204129Z/`

The [Sheinbaum analysis README](../code/08-results/03-sheinbaum-participation/README.md)
documents commands, variables, denominators, and caveats. The report is
`MEDIA_ROOT/results/sheinbaum/participation/through-2026-10-15/index.html`;
the panel is under `MEDIA_ROOT/data/02-conferences-sheinbaum/participation_panel/through-2026-10-15/`.

Initial results: 3,294 identified outlet-days across 328 identity labels; the
top ten account for 19.4%. On 239 common usable dates, 1,425 of 1,608 identified
outlet-days have direct attendance or approved dated-affiliation support, and
183 remain unmatched. First-year transcript coverage is 246 dates; the remaining
257 transcript dates fall after the available attendance period.

The report includes top-ten participation, monthly coverage, rates conditional
on recorded attendance, and existing outlet-alignment comparisons. These are
descriptive, not causal estimates or question-tone classifications. Full-corpus
question counts and presidential-response analyses remain pending completion of
the separate question–answer extraction. Historical model/balance estimates were
not re-estimated by this rebuild and must not be described as refreshed results.

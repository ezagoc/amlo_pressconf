# AMLO Tracking Poll: daily approval series

The code for this workflow is in `code/06-outcomes/approval_tracking/` in the
`amlo_pressconf` repository. Its frozen inputs, source images, working files, and
outputs live under `MEDIA_ROOT/data/06-outcomes/approval_tracking/`:

```text
inputs/           accepted readings, OCR and review records, image hashes
evidence/images/  cached source graphics
output/           final daily analysis CSV
source_workflow/  optional discovery, OCR and recovery working files
```

Set `MEDIA_ROOT` in the repository's ignored `.env` file for each computer.
`paths.py` uses the repository's `project_paths.py` helper, so these paths do
not depend on the current working directory. `MANIFEST.json` is kept with the
code; its file paths are relative to the Media approval directory.

The source collection scripts need the packages in
`code/06-outcomes/approval_tracking/requirements-workflow.txt` and Tesseract
OCR. For example, a new source discovery run starts with:

```bash
python3 code/06-outcomes/approval_tracking/source_workflow/build_approval_series.py --discovery-only
```

Its checkpoints and preliminary exports go to the `source_workflow/` directory
in Media. A new web scrape does not automatically replace the audited
`inputs/accepted_observations.csv`; newly found readings need review first.

This workflow builds **one analysis dataset**, `MEDIA_ROOT/data/06-outcomes/approval_tracking/output/amlo_tracking_poll_daily.csv`, for 14 April 2019–30 September 2024 (1,997 calendar days). It places the original approval and disapproval series beside completed series, with explicit observation/imputation indicators and source links. The input is a frozen set of 1,919 audited daily readings from Consulta Mitofsky / El Economista and Roy Campos's public reporting. The remaining 78 dates are interpolated and are **not** presented as published poll results.

## Rebuild

Requires Python 3.10 or newer; the canonical build uses only the standard library. From the repository root:

```bash
python3 code/06-outcomes/approval_tracking/build.py --check --verify-evidence
python3 code/06-outcomes/approval_tracking/build.py
```

To replay the preceding selection of accepted observations from the frozen OCR and recovery logs, run `python3 code/06-outcomes/approval_tracking/replay_selection.py`. That optional check needs Pillow (`python3 -m pip install Pillow`) because it imports the archived source-workflow code. It reproduces the selected 1,919-row source CSV byte for byte against the SHA-256 in `MANIFEST.json`; it does not re-download or re-OCR the historical web pages.

`inputs/accepted_observations.csv` is the frozen transcription of accepted readings and the only numerical input to `build.py`. `evidence/` contains the 1,292 distinct source images used by those readings, at their original cached resolution. Forty-two accepted readings have no local image because their evidence is a public post, news text, or video transcript; their URLs and source details are in the input and audit records. `inputs/evidence_manifest.csv` gives the SHA-256 of every cached image. The other files in `inputs/` preserve the article inventory, original OCR, manually reviewed recoveries, and acceptance decisions. `source_workflow/` in this code directory preserves the collection and extraction scripts used to create those inputs; they are supplied for methodological audit, while `build.py` is the self-contained offline rebuild. The source workflow scripts default to `Media/.../approval_tracking/source_workflow/` for new working files and may require Pillow, Tesseract, or yt-dlp for their optional stages.

## Variables in the single final CSV

| Variable | Meaning |
| --- | --- |
| `date` | Date measured, ISO `YYYY-MM-DD`; one row per calendar day. |
| `approval_original_pct`, `disapproval_original_pct` | Percentages actually read from a dated source. Blank if that specific percentage was not published for that date. |
| `approval_filled_pct`, `disapproval_filled_pct` | Continuous analysis series: original where available, otherwise the explicitly flagged replacement. Interpolations may have three decimals. |
| `original_day_missing` | `1` on the 78 dates with no accepted original approval or disapproval; `0` otherwise. |
| `approval_status` | `observed` or `linear_interpolation`. |
| `disapproval_status` | `observed`, `derived_complement`, or `linear_interpolation`. |
| `approval_imputed`, `disapproval_imputed` | `1` when the corresponding filled percentage was **not directly published for that date**, otherwise `0`. `derived_complement` is flagged as imputed. |
| `source_type` | `article_graphic`, `recovered_public_source`, or `interpolated`; the first two are accepted original readings. |
| `source_url`, `source_image_url`, `archive_url` | Public source, direct image, and archived copy where available. Blank on interpolated dates. |
| `evidence_file` | Relative path to the cached source image, when one exists. |
| `publication_date` | Source publication date; it may differ from the date measured. |
| `date_assignment` | How the measurement date was established from the source. |
| `anchor_before`, `anchor_after`, `gap_length_days` | Nearest observed dates and gap length for an interpolation; blank/zero for observed dates. |

There are 1,596 dates with both percentages directly observed, 323 with observed approval only, and 78 without an accepted daily reading. On those 78 dates, **both original columns are blank**, `original_day_missing = 1`, and both imputation flags equal `1`. For the 323 approval-only dates, `disapproval_original_pct` is blank, `disapproval_filled_pct = 100 − approval_original_pct`, and `disapproval_status = derived_complement`. **This complement is not a reported disapproval measurement**: it may include undecided or nonresponse. For the 78 wholly missing dates, approval and effective disapproval are separately linearly interpolated between adjacent accepted dates; the longest run is three missing days. The observed values are never smoothed or modified.

## Scope and source audit

Original dates and percentages were read from El Economista's daily graphics, dated historical comparisons, recovered newspaper covers, public posts, and official weekly videos. Source-backed values were checked for date alignment, percentage role, and conflicting readings. Monthly averages, curve heights, and unverified OCR were excluded as original daily values. The included audit files record accepted recoveries and manual corrections; the research workspace's exploratory downloads and rejected candidates are excluded to keep this review package focused. The archived workflow scripts document how sources were discovered and extracted, but a complete rerun of historical web discovery is outside this frozen offline rebuild.

The package reproduces the final numerical series from accepted source transcriptions. It does not establish that interpolated values equal unpublished daily survey results, or that changes around any political event were caused by that event. The current source context is described in [El Economista's Tracking Poll archive](https://www.eleconomista.com.mx/autor/consulta.mitofsky?facet=app) and [Mitofsky's final evaluation](https://www.mitofsky.mx/post/evaluacion-final-gobierno-de-amlo-septiembre-2024).

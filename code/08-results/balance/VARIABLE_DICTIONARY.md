# Balance panel: variable dictionary

Updated October 11, 2026. Describes `00-balance.R` and `src/baseline_history.R`.

## Scope and objects

- **Analysis period:** April 18, 2022 through December 31, 2024, inclusive.
- **Lottery cutoff:** April 18, 2022. Every historical covariate uses dates strictly before this date.
- **Historical start:** December 1, 2018, including for contracts. The contract archive's earlier 2012–2018 observations are not included in these baseline totals.
- **Unit:** metadata outlet × calendar day. The current panel has 245 metadata outlets and 242,305 daily rows.
- **`balance_panel`:** daily outcomes, source identifiers, all processed metadata, and frozen historical covariates.
- **`balance_outlets`:** one row per metadata outlet, with all metadata and historical covariates.
- **`baseline_long`:** one row per metadata outlet and historical window.
- **`contract_baseline_entities`:** contract histories before attaching them to metadata subsidiaries.
- **`windows`:** historical window boundaries.
- **`crosswalk`:** full metadata-to-source identifier mapping, including multiple YouTube IDs where applicable.

The script creates R objects only by default. Set `SAVE_OUTPUTS <- TRUE` to export to `MEDIA_ROOT/data/06-outcomes/balance`. It does not estimate regressions or balance tests.

## 1. Outlet and day identifiers

| Variable | Meaning |
|---|---|
| `metadata_id` | Outlet identifier in the balance panel |
| `name.page` | Original outlet name |
| `date` | Calendar date |
| `attendance_entity_id` | Deduplicated attendance-source ID |
| `questions_entity_id` | Deduplicated question-source ID |
| `contracts_entity_id` | Deduplicated COMSOC company/beneficiary ID |

Different metadata outlets may share a source ID. Their identical source histories are intentionally attached to each metadata row. Do not sum these metadata rows to calculate source-level totals: deduplicate or aggregate at the appropriate source entity instead. Company-level contract history is not a separately measured allocation to each subsidiary.

## 2. Treatment and daily attendance variables

| Variable | Meaning |
|---|---|
| `question_asked` | Treatment-day indicator: 1 if the outlet asked at least one question that day |
| `questions_n` | Number of questions asked that day |
| `attendance_attended` | Attendance indicator from the attendance source, including assumed co-affiliation |
| `attendance_n_journalists_recorded` | Recorded journalist attendance count |
| `attendance_n_journalists_assumed` | Attendance assigned through the co-affiliation rule |
| `attendance_n_journalists` | Recorded plus assumed attendance |

The current balance script does **not** create the earlier estimation aliases `treatment_day`, `treatment_plus_1`, `treatment_plus_2`, `treatment_plus_3`, `attendance_dummy`, or `sample_day`. The imported daily `attendance_attended` is also **not** corrected using “a question implies attendance”; the historical covariates below implement that correction separately.

The full daily panel's numeric outcomes were zero-filled upstream. A daily zero alone does not distinguish an observed zero from an unavailable date or an unmatched source. Historical covariates instead use source coverage and matching flags from the deduplicated source panels.

### Other daily question and conference variables

| Variable | Meaning |
|---|---|
| `question_items_n` | Total classified transcript items |
| `question_opinions_n` | Items classified as opinions |
| `question_other_n` | Other classified items |
| `question_reporters_n` | Distinct standardized reporter labels across classified items, not exclusively questions |
| `question_reporter_names` | Reporter labels combined for the outlet-day |
| `conference_n_total_attend` | Conference-level retained recorded attendance count |
| `conference_n_reporters` | Conference-level recorded reporter-role count |
| `conference_n_youtubers` | Conference-level recorded YouTuber-role count |

Conference-level counts are repeated across outlets. Do not sum them across outlet rows.

## 3. Historical covariates

Every historical variable follows:

```text
pre_<measure>_<window>
```

There are **24 measures × 7 windows = 168 historical variables**, including coverage and ratio-support fields. They are frozen at the lottery cutoff and repeated over the analysis dates.

### Attendance and questions

| Measure | Definition |
|---|---|
| `attendance` | Total recorded journalist attendance records |
| `attendance_assumed` | Total assumed co-affiliation attendance records |
| `attendance_inferred` | Additional minimum attendance inferred from recorded questions |
| `attendance_corrected` | Recorded + assumed + inferred attendance |
| `questions` | Total questions, not question-day indicators |
| `attendance_days` | Days with positive recorded attendance |
| `question_days` | Days with at least one question |
| `questions_per_attendance` | Questions / corrected attendance records on common observed dates |
| `questions_per_recorded_attendance` | Questions / recorded attendance records on common observed dates |
| `question_day_share` | Question-days / corrected attendance-days on common observed dates |

Examples: `pre_attendance_year1`, `pre_questions_last_year`, `pre_questions_per_attendance_total`.

**Attendance correction:** a day with at least one question implies at least one attendee. It does not imply one attendee per question. When attendance is observed, corrected attendance is the maximum of recorded-plus-assumed attendance and the question-day indicator. When attendance is unavailable but a question is recorded, the minimum is one. Unavailable attendance with no positive question evidence remains missing.

### Contracts and money

| Measure | Definition |
|---|---|
| `contracts_costo` | Total contract value used in the existing graphs, in nominal MXN |
| `contracts_importe` | Alternative monetary field, retained separately; do not add it to `contracts_costo` |
| `contracts_received_n` | Sum of daily distinct contract/order-ID counts |
| `contracts_n` | Number of source contract line items |
| `contracts_award_days` | Days with at least one source contract line item |
| `contracts_observed_days` | Days with source coverage for a matched beneficiary |

Examples: `pre_contracts_costo_last_2years`, `pre_contracts_received_n_year3`.

Contract dates come from `fecha.de.contratopedido`, not payment or policy dates. Contract histories are aggregated once per deduplicated beneficiary before mapping to metadata outlets. The contract count retains the existing daily definition: IDs are not re-deduplicated across different dates within a window. Missing contract IDs may contribute value and line items without contributing to the distinct-ID count. Amounts retain the upstream panel's numeric aggregation and missing-value conventions.

### Coverage and ratio-support measures

| Measure | Definition |
|---|---|
| `attendance_observed_days` | Dates with usable attendance-source coverage for the matched outlet |
| `questions_observed_days` | Dates with question-source coverage for the matched outlet |
| `common_observed_days` | Dates observed in both sources |
| `common_questions` | Questions on those common dates |
| `common_attendance` | Corrected attendance records on common dates |
| `common_attendance_recorded` | Recorded attendance records on common dates |
| `common_attendance_days` | Common dates with positive corrected attendance |
| `common_question_days` | Common dates with at least one question |

These fields expose the support and components of the ratios. For example:

```text
pre_questions_per_attendance_total
  = pre_common_questions_total / pre_common_attendance_total
```

It need not equal `pre_questions_total / pre_attendance_total`, because the latter totals can cover different dates and the attendance definitions differ.

### Historical window suffixes

All endpoints are inclusive.

| Suffix | From | To |
|---|---|---|
| `total` | 2018-12-01 | 2022-04-17 |
| `year1` | 2018-12-01 | 2019-11-30 |
| `year2` | 2019-12-01 | 2020-11-30 |
| `year3` | 2020-12-01 | 2021-11-30 |
| `year4` | 2021-12-01 | 2022-04-17 |
| `last_year` | 2021-04-18 | 2022-04-17 |
| `last_2years` | 2020-04-18 | 2022-04-17 |

Years follow the presidency, starting every December 1. `year4` is a partial year. `last_year` and `last_2years` are backward-looking 12- and 24-calendar-month windows, not prior calendar years.

### Missingness and November 2021

- Entirely unavailable or unmatched histories remain `NA`; coverage counts are zero.
- Observed periods with no recorded activity have zero counts.
- Partially covered windows contain observed-history totals, not estimates of activity on missing dates. Examine the coverage counts alongside them.
- Ratios with zero attendance denominators remain `NA`.
- November 2021 is excluded from recorded attendance and common-date attendance ratios.
- November 2021 questions and contracts remain included in their totals. Corrected attendance can retain explicitly flagged question-based lower bounds on unavailable dates, including November 2021.
- Contract observed-day counts follow the source panel's coverage convention; they are not counts of press-conference dates.

## 4. Outlet metadata covariates

All processed metadata columns are retained. The principal substantive and matching variables are listed below; source citations, verification fields, geocoding provenance and scraping bookkeeping also remain in the data.

| Category | Variables |
|---|---|
| Political orientation | `ideology.4t`, `ideology.leftright`, `ideology.subjective`, `owner.ideology`, `founder.ideology` |
| Coverage and format | `coverage.scope`, `type.media` |
| Ownership and organization | `owner.person`, `owner.family`, `owner_group`, `conglomerate`, `legal_name`, `founder.name`, `asociacion.name`, `asociacion.legal` |
| Outlet characteristics | `year_founded`, `subscription`, `journalist.mañanera` |
| Geography | `state`, `municipality`, `CVE_ENT`, `CVE_MUN`, `address`, `address2`, `city.headq`, `office_latitude`, `office_longitude`, `distance_palacio_nacional_km` |
| Source matching and links | `bene_final`, `name.comsoc`, `names.conference`, `names.transcripts`, `youtube.channel`, `twitter.handle`, `url` |

### Metadata dummy variables

Append each listed suffix to its prefix; these are exact column names, not additional variables generated by the balance script.

| Prefix | Suffixes |
|---|---|
| `ideology_4t_` | `aligned`, `opposition`, `unclear` |
| `ideology_` | `left`, `center`, `center_right`, `right`, `unclear` |
| `owner_ideology_` | `left`, `right`, `unclear` |
| `coverage_` | `national`, `state`, `regional`, `international`, `multistate`, `metropolitan`, `municipal`, `local`, `community`, `city`, `unclear` |
| `media_` | `periodico`, `social_media`, `digital`, `print`, `radio`, `television`, `video`, `magazine`, `news_agency`, `podcast`, `network`, `personal`, `unverified` |

Examples: `ideology_4t_opposition`, `coverage_national`, `media_periodico`.

## 5. Interpretation and estimation cautions

- These are candidate covariates, not controls already included in a regression.
- Current metadata are not necessarily measurements from before the lottery.
- Frozen histories and time-invariant metadata are absorbed by outlet fixed effects when entered as standalone regressors. Additional adjustment requires a separately specified approach, such as appropriate interactions with time.
- Totals and annual counts overlap; the trailing windows also overlap. Do not include every measure mechanically in one model.
- Pre-lottery histories are not necessarily pre-treatment histories: outlets could ask questions before the lottery.
- The balance script omits legacy `attendance_total`, `attendance_before` and `attendance_after` fields, which are not the new frozen historical measures.
- Recorded attendance rows are not verified distinct-person counts. Photographers/cameramen are filtered upstream; assumed co-affiliations remain separately identified.
- The transcript speaker-attribution audit corrections remain pending upstream. Constructing baseline histories does not resolve those extraction issues.

## 6. Inspect exact column names in R

After sourcing `00-balance.R`:

```r
names(balance_panel)                                  # Every panel column
names(metadata)                                       # Every metadata column
grep("^pre_", names(balance_outlets), value = TRUE)     # All 168 history fields
windows                                               # Exact date boundaries
```

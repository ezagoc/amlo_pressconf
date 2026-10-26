# Balance of question access among attending outlets

Discussion draft — October 11, 2026. This document specifies proposed balance checks, not an approved estimation run. It does not change the data, existing code, or earlier estimates.

## 1. Question and agreed decisions

**Research question:** after the April 18, 2022 seating reform, are outlets that ask a question comparable to other outlets attending the same conference in their predetermined characteristics and pre-lottery histories?

Confirmed in this conversation:

- We have attendance and question records, **not actual lottery or seating assignments**.
- The main attendance sample uses **directly recorded attendance only**.
- Assumed co-affiliations and attendance inferred from questions are separate sensitivity checks, not additions to the main roster.
- The exposure of interest is whether an outlet asked **at least one question that day**, not the number of questions.
- Historical presidency years start December 1, 2018. Retain the existing last-year, last-two-years, total, and presidency-year histories.

Everything below is a proposal for discussion unless identified as a confirmed decision or an existing data definition. Scope is balance and access diagnostics only; effects on subsequent attendance or YouTube outcomes require a separate specification.

## 2. What these tests can establish

A random assignment of seats is not necessarily a random assignment of opportunities to speak. Contemporary reports describe a draw for the first **three rows**, organized by media type; they also report that a seat did not guarantee speaking because the president still selected speakers. The original protocol and its implementation have not been independently verified here. See [El Financiero, April 11, 2022](https://www.elfinanciero.com.mx/nacional/2022/04/11/la-mananera-es-una-tom-tom-tombola-asi-sera-el-sorteo-para-acomodar-a-reporteros-en-la-conferencia/) and [La Razón, April 11, 2022](https://www.razon.com.mx/mexico/2022/04/11/se-comenzaran-a-rifar-los-lugares-en-la-mananera-de-amlo/).

Therefore:

- Call the exercise **balance of observed question access**, not a test proving the seat lottery was random.
- Date fixed effects compare attendees at the same conference, but do not reconstruct unknown eligibility rules, media-type allocations, or seating assignments.
- Outlet-level probabilities need not be equal if the draw operated over journalists and outlets sent different numbers of journalists. Recorded attendance rows are not necessarily distinct-person counts.
- Neither insignificant differences nor a large joint-test p-value proves random access. Differences may reflect discretion, eligibility, differing participation, or measurement error.
- Attendance itself may respond to past speaking opportunities. These are comparisons conditional on the observed attendance roster, not evidence that attendance is randomly selected.

## 3. Inputs, coverage, and dates

Use `00-balance.R`, `VARIABLE_DICTIONARY.md`, and the deduplicated source panels under `MEDIA_ROOT/data/06-outcomes/deduplicated_source_panels`. The existing metadata panel is a starting point, **not yet the deduplicated analysis sample**. Pre-lottery source data already exist; no new path is needed from the user.

### Proposed periods

- Main post-lottery period: **2022-04-18 through 2024-09-27**, the last currently observed question-source date within AMLO's tenure.
- Historical covariates: existing windows ending **2022-04-17**, beginning no earlier than **2018-12-01**.
- Descriptive pre/post contrast: one calendar year on each side, **2021-04-18–2022-04-17** versus **2022-04-18–2023-04-17**. A full available pre-period contrast can be supplementary.
- Within each range, use dates with usable attendance and question-source coverage. Calendar endpoints alone do not establish coverage.

The existing starter script ends December 31, 2024. That is not the proposed endpoint for this AMLO-only exercise. No change to that script has been made by drafting this document.

### Coverage rules

1. Bring source matching and date-coverage flags into the analysis before interpreting zeros. A matched, covered source with no activity can supply zero; unavailable sources or dates cannot.
2. Do not define a non-conference solely by `conference_n_total_attend == 0`. The current files contain questions but no attendance-source rows on **2022-05-13, 2022-06-28, 2022-06-30, 2022-07-07, and 2023-06-06**. Audit these as coverage inconsistencies, not non-events.
3. Positive source coverage does not guarantee complete identification of every speaker. Report unresolved outlets and transcript attribution issues separately. An unmatched question entity is not a verified non-asking outlet.
4. Keep November 2021 excluded from attendance-based comparisons. Its question and contract totals remain available for the historical summaries, with coverage limitations disclosed.
5. Conference totals are repeated across metadata rows; never sum them across outlets.
6. If venue can be recovered, distinguish Palacio Nacional conferences from travel conferences where the same seating procedure may not apply. Without that information, explicitly limit the institutional interpretation.

## 4. Analysis unit and matching

Create an audited `analysis_unit_id` representing a consistently identified conference outlet/source unit. Do not simply coalesce the question ID and attendance ID or select the first metadata row.

The current crosswalk has five attendance IDs linked to multiple question IDs: **bajo palabra, jaime farias informa, lord molecula oficial, mmm otros, and oem otros**. These may represent aliases or aggregate categories. They need explicit resolution; sharing an aggregate attendance label is not enough to conclude that all linked outlets are one unit.

Required rules:

- Maintain an explicit crosswalk from every analysis unit back to attendance IDs, question IDs, and metadata IDs.
- Combine verified aliases; quarantine unresolved many-to-many or aggregate mappings from the main analysis and report them. Do not automatically merge connected components of the matching graph.
- Count each original attendance record and question item once. After matching, assert one row per analysis unit and date; define `ask` as any qualifying question on that date.
- Resolve substantive metadata conflicts explicitly. A canonical display name is acceptable; an arbitrary canonical ideology or company history is not.
- If one analysis unit has multiple contract beneficiaries, establish whether they are genuinely distinct companies before aggregating. Conversely, a company's value shared by several subsidiaries is a **company-level covariate**, not separate money allocated to each subsidiary.
- Describe whether the final sample represents all recorded attendees or only the metadata-linked subset. Do not present probabilities calculated on the latter as probabilities for the full conference roster.

Recompute histories at the resolved analysis-unit level where mappings combine sources. Never sum duplicated metadata histories.

## 5. Attendance sample and exposure

On dates with usable coverage, define:

| Definition | Rule | Use |
|---|---|---|
| `att_recorded` | `attendance_n_journalists_recorded > 0` | Main roster |
| `att_recorded_assumed` | Recorded + assumed attendance > 0 | Sensitivity 1 |
| `att_question_corrected` | Recorded + assumed attendance > 0, or `ask == 1` | Sensitivity 2 |
| `ask` | At least one correctly attributed question that day | Main exposure |

The Mexico News/Sin Censura co-affiliation rule remains in the existing data, but belongs to assumed attendance, not the main roster. Photographers and camera/technical roles remain excluded upstream.

Report asking without recorded attendance overall, by unit, and by ideology. Adding only previously unrecorded askers can mechanically increase their measured asking rate, so the question-corrected sample is not automatically more representative.

Proposed primary cohort: all resolved, source-matched recorded attendees, with **no minimum attendance based on future or whole-term activity**. Sensitivities may require at least 5, 10, or 20 recorded attendance days **before** the lottery. A restriction requiring attendance in both periods is permissible for an explicitly labeled common-outlet descriptive graph, not the main design check.

For each analysis date, report unique attending units, asking units, and total questions. Only dates containing both askers and non-askers identify within-date contrasts. Dates with no such variation remain in the sample-flow report; do not mislabel them as non-conferences.

## 6. Covariates and historical windows

Present all requested history families descriptively, but use a small prespecified core for the main joint test. Do not put all 168 overlapping history fields into one regression.

### Proposed core

| Domain | Main variables / coding |
|---|---|
| Political orientation | Aligned and opposition indicators; unclear is the reference category, not a verified independent affiliation |
| Format and scope | Radio, television, print/newspaper, digital, social-media/personal indicators; national coverage; retain overlapping formats explicitly |
| Organization | Age at lottery, subscription categories after verifying their coding, distance to Palacio Nacional |
| Prior attendance | `log1p(pre_attendance_last_year)`: recorded journalist attendance records |
| Prior questions | `log1p(pre_questions_last_year)`: total questions |
| Prior money | `log1p(pre_contracts_costo_last_year)`, subject to a negative-value audit |
| Prior contracts | `log1p(pre_contracts_received_n_last_year)` |

Do not label all digital outlets as “personal.” Nor should overlapping metadata format indicators be treated automatically as the actual mutually exclusive lottery categories. Verify the print/newspaper consolidation before implementation.

Additional prespecified balance rows: recorded attendance-days, question-days, questions per recorded attendance, and the probability of asking on a recorded attendance-day. For the last measure, construct a **strict-recorded historical rate**:

```text
count(common covered dates with recorded attendance > 0 AND ask == 1)
----------------------------------------------------------------------------
count(common covered dates with recorded attendance > 0)
```

This is a new derived measure, not the existing `pre_question_day_share_*`, whose denominator uses corrected attendance. Report the corrected rate as a sensitivity. Do not describe question counts per attendance record as probabilities; they can exceed one.

The primary joint test uses the core above. A supplementary joint test adds the strict historical asking rate, with any loss of sample or rank reported. This avoids selecting the preferred rate specification after seeing its p-value.

Repeat history summaries for `total`, `year1`, `year2`, `year3`, partial `year4`, and `last_2years`; use these as clearly labeled alternatives to `last_year`, not simultaneous substitutes chosen for significance. Presidency years and trailing windows follow the existing dictionary exactly.

### Timing, money, and missingness

- Current metadata are treated as stable characteristics only provisionally; flag fields that may have changed after April 2022.
- All historical windows end before the lottery. They are pre-lottery, not necessarily before an outlet's first-ever question.
- Contracts use `fecha.de.contratopedido`, nominal MXN, and the deduplicated beneficiary. Never add `contracts_importe` to `contracts_costo`. Distinct contract counts retain the existing daily-ID definition.
- Audit negative monetary totals before applying `log1p`; do not silently truncate or invent a replacement transformation.
- Preserve unavailable histories as missing. Report source coverage and missingness by asking status. Partial-window totals are observed totals, not complete histories.
- Each balance row uses available values and reports its own N. Test missingness indicators separately.
- For the main joint model, use fixed-value imputation plus missing indicators, omitting constant/redundant columns under a documented rule. This permits a joint diagnostic; it does not recover missing histories. Report a complete-covariate sensitivity and its coverage.

## 7. Main statistical output

### Covariate-by-covariate balance

For each covariate `X`, estimate:

```text
X_it = date_FE_t + beta * ask_it + error_it
```

No unit fixed effects: these would absorb frozen covariates. Primary standard errors cluster by analysis unit; report two-way unit/date clustering as a sensitivity, with the number of clusters and any small-sample limitations.

Table columns: asking and non-asking means, adjusted difference `beta`, 95% CI, p-value, standardized adjusted difference, N unit-days, N units, N dates, and missingness. Raw means and adjusted differences are different quantities.

Define the standardized adjusted difference as `beta / SD(X)` on that row's estimation sample; leave it undefined for constant X. This is a **standardized date-adjusted contrast**, not the attached document's difference between group means of demeaned X. Plot these contrasts and CIs; any reference threshold such as 0.1 is descriptive, not proof of validity.

These regressions weight attendance occasions, not outlets equally. The FE contrast weights each date's mean difference in proportion to `n_t * p_t * (1 - p_t)`. State this estimand; an equal-outlet weighted version can be supplementary.

### Joint prediction of question access

```text
ask_it = date_FE_t + X_i' * gamma + missing_i' * delta + error_it
```

Use a linear probability model and report the joint Wald test of retained substantive covariate coefficients; report a second joint test that includes missingness indicators. Record rank, omitted columns, sample, and cluster counts. Do not interpret individual coefficients causally.

Within aligned, opposition, and unclear groups, repeat the non-ideology diagnostics as secondary analyses; omit constant ideology indicators. Report reduced precision and the number of informative dates. Preserve opposition and unclear separately.

Balance diagnostics should respect the comparison structure; see [Hansen and Bowers (2008)](https://arxiv.org/abs/0808.3857). If verified media-type strata become available, add a date-by-stratum analysis. Format indicators absorbed by those fixed effects cannot then be tested within strata.

## 8. Permutations: an explicitly hypothetical benchmark

Because the actual assignments and eligible draw roster are unavailable, do **not** label a within-date shuffle an exact test of the implemented seat lottery.

Optional benchmark: conditional on the resolved recorded-attendee sample, suppose the observed number of asking outlets was selected uniformly within each date. Shuffle `ask`, preserving that number and a fixed covariate/sample specification, for 2,000 draws with seed 20261011. Compare the same prespecified joint statistic across draws. Use `(1 + number at least as extreme) / (2000 + 1)`, not a formula that can return zero; see [Hemerik and Goeman (2018)](https://pmc.ncbi.nlm.nih.gov/articles/PMC6405018/).

Label the result **equal-access permutation benchmark, conditional on the observed roster**. Its validity for the actual assignment process is not established: unknown type quotas, journalist-level draws, repeat-winner restrictions, and attendance responses can break exchangeability. If subgroup statistics are evaluated, shuffle the full relevant roster first, then recompute subgroup statistics; shuffling within ideology would condition away between-ideology access differences.

Observed-versus-expected asking counts may use the same explicitly hypothetical benchmark. Do not call a Poisson-binomial calculation exact without justified independence and assignment probabilities. Do not remove unusual outlets because their outcomes fail the benchmark and then claim improved randomization.

## 9. Secondary analyses and exclusions

- **Before/after:** compare access balance in the proposed one-year windows using metadata only, subject to its stability caveat. The frozen April 2022 histories contain outcomes during the pre-period and therefore cannot be predetermined covariates for those earlier dates. A change in balance is descriptive, not automatically a causal effect of the lottery.
- **Historical access:** whether pre-lottery asking predicts post-lottery access is informative, but not by itself decisive evidence for or against random assignment.
- **Rolling histories and persistence:** reserve for a second stage. They must use strictly earlier dates and observed coverage. A zero persistence coefficient is not guaranteed under a valid lottery with eligibility restrictions. Treatment-derived lags cannot simply remain fixed under a purported randomization of entire treatment histories.
- **Conference length:** do not use total questions as a length control or balance stratifier. It is jointly determined with asking and contains the outcome being studied. Actual duration, if obtained, is also potentially post-assignment.
- **Question counts:** a separate intensive-margin analysis, not an interchangeable definition of receiving access.
- **Effects on attendance or YouTube:** outside this balance-only document.

## 10. Proposed deliverables and checks before estimation

Keep analysis code alongside `00-balance.R`; proposed result directory is `output/balance/`. Do not overwrite existing descriptive or estimation outputs.

Deliverables:

1. Sample-flow, coverage, source-ID mapping, metadata-conflict, and attendance/question mismatch audits.
2. Main post-lottery balance table (CSV and LaTeX), joint-test summary, and standardized-contrast PDF.
3. Separate tables for attendance definitions, history windows, missingness, and pre-eligibility thresholds.
4. Secondary before/after and ideology-specific comparisons, clearly separated from the main result.
5. Optional permutation benchmark, labeled with its hypothetical assignment assumptions.
6. Reproducibility log: input versions, mapping decisions, periods, exclusions, transformations, covariate lists, software versions, and seeds.

Before implementation, resolve or explicitly quarantine ambiguous entity mappings, establish date coverage, and document remaining transcript attribution errors. Existing speaker-attribution audit corrections have **not** yet been applied upstream. Any exploratory results using current questions must be labeled provisional.

Acceptance assertions: unique unit-date rows; no duplicated source contributions; all baseline dates before April 18, 2022; no missing sources converted to observed zeros; sample counts at every exclusion; strictly recorded main attendance; conference totals not summed; fixed permutation counts where used.

### Remaining discussion decisions

1. Approve the proposed AMLO-only post period and one-year pre/post descriptive window?
2. Approve the core covariates and supplementary strict-recorded historical asking rate?
3. After auditing mappings, run provisional diagnostics with current question attribution, or wait for upstream corrections?
4. Include the hypothetical permutation benchmark, or initially show only balance estimates, CIs, and joint tests?

# Run from the repository root: Rscript code/08-results/balance/01-run_balance.R
# Simple post-lottery balance tests; no upstream files are changed.
suppressPackageStartupMessages({library(dplyr); library(tidyr); library(arrow); library(fixest)})
arg <- grep("^--file=", commandArgs(FALSE), value = TRUE)
this_file <- if (length(arg)) sub("^--file=", "", arg[[1]]) else
  file.path(getwd(), "code/08-results/balance/01-run_balance.R")
source(file.path(dirname(this_file), "00-balance.R"))
fixest::setFixest_nthreads(1)
FROM <- as.Date("2022-04-18")
TO <- as.Date("2024-09-27")
RATIO_VARIABLE <- "pre_questions_per_recorded_attendance_last_year"
out <- file.path(root, "output/balance")
dir.create(out, recursive = TRUE, showWarnings = FALSE)

# Deduplicate shared sources; exclude ambiguous cross-source mappings.
pairs <- source_ids |> filter(!is.na(attendance_entity_id), !is.na(questions_entity_id)) |>
  distinct(attendance_entity_id, questions_entity_id)
bad_a <- pairs |> count(attendance_entity_id) |> filter(n > 1)
bad_q <- pairs |> count(questions_entity_id) |> filter(n > 1)
links <- pairs |> anti_join(bad_a, by = "attendance_entity_id") |>
  anti_join(bad_q, by = "questions_entity_id") |> mutate(unit_id = attendance_entity_id)
write.csv(pairs |> mutate(excluded_ambiguous = attendance_entity_id %in% bad_a$attendance_entity_id |
                           questions_entity_id %in% bad_q$questions_entity_id),
          file.path(out, "source_mapping_audit.csv"), row.names = FALSE)

# Core: last-year histories. Other windows are tested individually, not jointly.
safe_log <- function(x) ifelse(is.na(x) | x < 0, NA_real_, log1p(pmax(x, 0)))
bo <- balance_outlets |>
  mutate(age_at_lottery = ifelse(grepl("^[0-9]{4}$", trimws(year_founded)),
                                2022 - suppressWarnings(as.numeric(year_founded)), NA_real_),
         age_at_lottery = ifelse(age_at_lottery < 0, NA_real_, age_at_lottery),
         subscription_binary = suppressWarnings(as.numeric(as.character(subscription))),
         media_print_any = pmax(coalesce(media_print, 0), coalesce(media_periodico, 0)),
         log_pre_attendance = safe_log(pre_attendance_last_year),
         log_pre_questions = safe_log(pre_questions_last_year),
         log_pre_money = safe_log(pre_contracts_costo_last_year),
         log_pre_contracts = safe_log(pre_contracts_received_n_last_year))
labels <- c(ideology_4t_aligned = "Aligned", ideology_4t_unclear = "Neutral / unclear",
            ideology_4t_opposition = "Opposition",
            media_radio = "Radio", media_television = "Television",
            media_print_any = "Print / newspaper", media_digital = "Digital",
            media_social_media = "Social media", media_personal = "Personal",
            coverage_national = "National coverage",
            age_at_lottery = "Outlet age (years)", subscription_binary = "Subscription",
            distance_palacio_nacional_km = "Distance to Palacio Nacional (km)",
            pre_questions_per_recorded_attendance_last_year = "Prior-year questions / recorded attendance",
            log_pre_money = "Prior-year contract value: log(1 + MXN)",
            log_pre_contracts = "Prior-year contracts: log(1 + count)")
core <- names(labels)
histories <- grep("^pre_", names(bo), value = TRUE)
covariates <- unique(c(core, histories))
binary_zero <- c("coverage_national", "media_radio", "media_television",
                 "media_print_any", "media_digital", "media_social_media", "media_personal",
                 "subscription_binary")
stopifnot(all(vapply(bo[covariates], is.numeric, logical(1))),
          all(na.omit(bo$subscription_binary) %in% 0:1))

# Agreement among available metadata values; conflicts are NA, never an
# arbitrary subsidiary's characteristics. Histories are not summed.
consensus <- function(x) {
  z <- unique(x[!is.na(x)])
  if (length(z) == 1L) z[[1]] else NA_real_
}
rows <- bo |> inner_join(links, by = c("attendance_entity_id", "questions_entity_id"),
                         relationship = "many-to-one")
conflicts <- rows |> group_by(unit_id) |>
  summarise(across(all_of(covariates), ~ n_distinct(.x, na.rm = TRUE)), .groups = "drop") |>
  pivot_longer(-unit_id, names_to = "covariate", values_to = "distinct_values") |>
  filter(distinct_values > 1)
write.csv(conflicts, file.path(out, "metadata_conflicts.csv"), row.names = FALSE)
units <- rows |> group_by(unit_id) |>
  summarise(outlet_names = paste(sort(unique(name.page)), collapse = " / "),
            metadata_ids = paste(sort(unique(metadata_id)), collapse = " | "),
            n_beneficiaries = n_distinct(contracts_entity_id, na.rm = TRUE),
            across(all_of(covariates), consensus), .groups = "drop")
# Format/scope flags describe whether ANY member of the deduplicated source
# unit has that attribute. Missing flags count as 0 by the user's convention.
flags <- rows |> group_by(unit_id) |>
  summarise(across(all_of(binary_zero), ~ as.numeric(any(.x == 1, na.rm = TRUE))), .groups = "drop")
units <- units |> select(-all_of(binary_zero)) |> left_join(flags, by = "unit_id")

# Preserve conflicting political classifications as missing, not neutral.
# All three displayed categories use the same classified sample.
ideology_vars <- c("ideology_4t_aligned", "ideology_4t_unclear", "ideology_4t_opposition")
valid_ideology <- complete.cases(units[ideology_vars]) & rowSums(units[ideology_vars], na.rm = TRUE) == 1
units[!valid_ideology, ideology_vars] <- NA_real_

# Contracts: aggregate each distinct beneficiary ONCE per source unit/window.
# No matched/available history contributes 0, per the user's requested coding.
# A known positive amount must not become 0 just because subsidiaries disagree.
contract_links <- rows |> filter(!is.na(contracts_entity_id)) |>
  distinct(unit_id, contracts_entity_id)
contract_by_unit <- contract_links |>
  left_join(contract_baseline_entities, by = "contracts_entity_id", relationship = "many-to-many")
write.csv(contract_by_unit, file.path(out, "contract_beneficiary_audit.csv"), row.names = FALSE)
contract_by_unit <- contract_by_unit |> filter(!is.na(window)) |>
  group_by(unit_id, window) |>
  summarise(across(starts_with("contracts_") & where(is.numeric), ~ sum(.x, na.rm = TRUE)), .groups = "drop") |>
  pivot_wider(id_cols = unit_id, names_from = window,
              values_from = starts_with("contracts_"), names_glue = "pre_{.value}_{window}")
contract_vars <- grep("^pre_contracts_", names(units), value = TRUE)
units <- units |> select(-all_of(contract_vars), -log_pre_money, -log_pre_contracts) |>
  left_join(contract_by_unit, by = "unit_id", relationship = "one-to-one") |>
  mutate(across(all_of(contract_vars), ~ coalesce(.x, 0)),
         log_pre_money = safe_log(pre_contracts_costo_last_year),
         log_pre_contracts = safe_log(pre_contracts_received_n_last_year))
stopifnot(all(unlist(units[binary_zero]) %in% 0:1),
          !anyNA(units[contract_vars]))
write.csv(units, file.path(out, "analysis_unit_covariates.csv"), row.names = FALSE)

# Preserve source coverage: full-panel zero filling does not establish non-asking.
a <- open_dataset(file.path(source_dir, "attendance_entity_daily_panel.parquet")) |>
  filter(date >= FROM, date <= TO) |>
  select(entity_id, date, source_entity_matched, source_date_observed,
         attendance_n_journalists_recorded) |> collect() |>
  rename(attendance_entity_id = entity_id, attendance_matched = source_entity_matched,
         attendance_observed = source_date_observed)
q <- open_dataset(file.path(source_dir, "questions_entity_daily_panel.parquet")) |>
  filter(date >= FROM, date <= TO) |>
  select(entity_id, date, source_entity_matched, source_date_observed, question_asked) |>
  collect() |> rename(questions_entity_id = entity_id, questions_matched = source_entity_matched,
                      questions_observed = source_date_observed, ask = question_asked)
stopifnot(!anyDuplicated(a[c("attendance_entity_id", "date")]),
          !anyDuplicated(q[c("questions_entity_id", "date")]))
daily <- a |> inner_join(links, by = "attendance_entity_id", relationship = "many-to-one") |>
  inner_join(q, by = c("questions_entity_id", "date"), relationship = "one-to-one") |>
  mutate(recorded = attendance_matched & attendance_observed & attendance_n_journalists_recorded > 0)
write.csv(daily |> filter(questions_matched, questions_observed, ask == 1, !recorded) |>
            select(unit_id, date, attendance_matched, attendance_observed, attendance_n_journalists_recorded),
          file.path(out, "questions_without_recorded_attendance.csv"), row.names = FALSE)
attendees <- daily |> filter(recorded, questions_matched, questions_observed, !is.na(ask)) |>
  left_join(units, by = "unit_id", relationship = "many-to-one")
informative <- function(d) d |> group_by(date) |> filter(any(ask == 1), any(ask == 0)) |> ungroup()
sample <- informative(attendees)
stopifnot(nrow(sample) > 0, !anyDuplicated(sample[c("unit_id", "date")]), all(sample$ask %in% 0:1),
          all(sample$attendance_n_journalists_recorded > 0))
flow_row <- function(d, stage) tibble(stage = stage, n = nrow(d),
                                     units = n_distinct(d$unit_id), days = n_distinct(d$date))
flow <- bind_rows(flow_row(daily, "Resolved source pairs, joined calendar days"),
                 flow_row(attendees, "Recorded attendees, both sources observed and matched"),
                 flow_row(sample, "Dates with both askers and non-askers"))
write.csv(flow, file.path(out, "sample_flow.csv"), row.names = FALSE)

# Individual regressions condition on the observed pre-lottery ratio.
# Compare unadjusted and adjusted estimates on exactly the SAME row sample.
# The ratio is a control, not an outcome regressed on itself. Remove standalone
# prior-question/attendance counts from the main and supplementary tests.
count_histories <- grep(paste0("^pre_(attendance|attendance_assumed|attendance_inferred|",
  "attendance_corrected|attendance_days|questions|question_days|common_questions|",
  "common_attendance|common_attendance_recorded|common_attendance_days|common_question_days)_",
  "(total|year[1-4]|last_year|last_2years)$"), covariates, value = TRUE)
individual_covariates <- setdiff(covariates, c(RATIO_VARIABLE, count_histories))
ratio_sample <- informative(sample |> filter(is.finite(.data[[RATIO_VARIABLE]])))
flow <- bind_rows(flow, flow_row(ratio_sample, "Observed prior questions/recorded-attendance ratio"))
write.csv(flow, file.path(out, "sample_flow.csv"), row.names = FALSE)
models <- list()
unadjusted_models <- list()
one_balance <- function(v) {
  d <- informative(ratio_sample |> filter(is.finite(.data[[v]]))) |>
    mutate(prior_ratio = .data[[RATIO_VARIABLE]])
  base <- tibble(covariate = v, n = nrow(d), units = n_distinct(d$unit_id),
                 days = n_distinct(d$date), missing_share = mean(!is.finite(sample[[v]])))
  if (!nrow(d) || sd(d[[v]]) == 0) return(mutate(base, status = "No usable variation"))
  d <- mutate(d, x = .data[[v]])
  if (sum((d$x - ave(d$x, d$date))^2) < 1e-12)
    return(mutate(base, status = "No within-date variation"))
  control_fit <- feols(x ~ prior_ratio | date, data = d, notes = FALSE)
  if (sum(resid(control_fit)^2) < 1e-12)
    return(mutate(base, status = "No variation after conditioning on prior ratio"))
  fit <- feols(x ~ ask + prior_ratio | date, data = d, cluster = ~unit_id, notes = FALSE)
  unadjusted <- feols(x ~ ask | date, data = d, cluster = ~unit_id, notes = FALSE)
  models[[v]] <<- fit
  unadjusted_models[[v]] <<- unadjusted
  ct <- coeftable(fit)["ask", ]; ci <- confint(fit, parm = "ask")
  mutate(base, status = "Estimated", mean_asking = mean(d$x[d$ask == 1]),
         mean_not_asking = mean(d$x[d$ask == 0]), estimate = ct[[1]], se = ct[[2]],
         ci_low = ci[[1]], ci_high = ci[[2]], p_value = ct[[4]],
         unadjusted_estimate = unname(coef(unadjusted)[["ask"]]),
         unadjusted_p_value = coeftable(unadjusted)["ask", 4],
         standardized_difference = ct[[1]] / sd(d$x))
}
balance <- bind_rows(lapply(individual_covariates, one_balance))
write.csv(balance, file.path(out, "individual_balance_all_windows.csv"), row.names = FALSE)
main_table <- balance |> filter(covariate %in% core) |> mutate(label = unname(labels[covariate]))
write.csv(main_table, file.path(out, "individual_balance_core.csv"), row.names = FALSE)

# Joint regression: any question = day FE + all core covariates together.
# Zero-impute missing values WITH indicators. Continuous variables use SD units.
joint_data <- sample
terms <- character(); missing_terms <- character()
scales <- setNames(rep(1, length(core)), core)
# Neutral / unclear is the explicit omitted reference in the joint model.
joint_covariates <- setdiff(core, "ideology_4t_unclear")
for (v in joint_covariates) {
  x <- joint_data[[v]]; valid <- is.finite(x)
  if (sum(valid) < 2 || sd(x[valid]) == 0) next
  if (!all(x[valid] %in% 0:1)) scales[[v]] <- sd(x[valid])
  joint_data[[v]] <- ifelse(valid, x / scales[[v]], 0)
  terms <- c(terms, v)
  if (any(!valid)) {
    mv <- paste0(v, "_missing")
    joint_data[[mv]] <- as.integer(!valid)
    missing_terms <- c(missing_terms, mv)
  }
}
joint <- feols(as.formula(paste("ask ~", paste(c(terms, missing_terms), collapse = " + "), "| date")),
               data = joint_data, cluster = ~unit_id, notes = FALSE)
substantive <- intersect(terms, names(coef(joint)))
joint_wald <- wald(joint, keep = paste0("^(", paste(substantive, collapse = "|"), ")$"), print = FALSE)
all_wald <- wald(joint, print = FALSE)
stopifnot(is.list(joint_wald), is.finite(joint_wald$p))
joint_table <- as.data.frame(coeftable(joint))
names(joint_table) <- c("estimate", "se", "t_statistic", "p_value")
joint_table$term <- rownames(joint_table); rownames(joint_table) <- NULL
cis <- confint(joint)
joint_table$ci_low <- cis[, 1]; joint_table$ci_high <- cis[, 2]
joint_table$scale <- ifelse(joint_table$term %in% core, scales[joint_table$term], 1)
write.csv(joint_table, file.path(out, "joint_regression.csv"), row.names = FALSE)
test_row <- function(w, label) tibble(test = label, F = w$stat, p = w$p, df1 = w$df1, df2 = w$df2)
write.csv(bind_rows(test_row(joint_wald, "Substantive covariates"),
                    test_row(all_wald, "Covariates and missingness")),
          file.path(out, "joint_tests.csv"), row.names = FALSE)
write.csv(tibble(n = nobs(joint), units = n_distinct(sample$unit_id),
                 dates = n_distinct(sample$date), asking = sum(sample$ask),
                 within_r2 = r2(joint, "wr2")[[1]], covariates = length(substantive),
                 conditional_n = nrow(ratio_sample), conditional_units = n_distinct(ratio_sample$unit_id),
                 conditional_dates = n_distinct(ratio_sample$date), conditional_asking = sum(ratio_sample$ask)),
          file.path(out, "model_summary.csv"), row.names = FALSE)
saveRDS(list(individual = models, unadjusted = unadjusted_models,
             joint = joint, joint_wald = joint_wald, all_wald = all_wald,
             sample = sample, ratio_variable = RATIO_VARIABLE, scales = scales, core = core, period = c(FROM, TO)),
        file.path(out, "balance_models.rds"))

# Readable results and Overleaf-ready tables.
fmt <- function(x) ifelse(is.na(x), "--", formatC(x, digits = 3, format = "f"))
fp <- function(x) ifelse(is.na(x), "--", ifelse(x < .001, "<0.001", fmt(x)))
rows_md <- sprintf("| %s | %s | %s | [%s, %s] | %s | %s |",
                   main_table$label, fmt(main_table$unadjusted_estimate),
                   fmt(main_table$estimate), fmt(main_table$ci_low), fmt(main_table$ci_high),
                   fp(main_table$p_value), main_table$n)
joint_core <- joint_table[joint_table$term %in% core, ]
joint_labels <- labels
joint_labels[scales != 1] <- paste0(joint_labels[scales != 1], " [1 SD]")
joint_rows_md <- sprintf("| %s | %s | [%s, %s] | %s |",
                         joint_labels[joint_core$term], fmt(100 * joint_core$estimate),
                         fmt(100 * joint_core$ci_low), fmt(100 * joint_core$ci_high),
                         fp(joint_core$p_value))
joint_rows_md <- append(joint_rows_md, "| Neutral / unclear | Reference | -- | -- |", after = 1)
report <- c("# Post-lottery balance: day fixed effects", "",
  "Provisional: pending transcript speaker-attribution corrections are not applied.", "",
  sprintf("Period: %s to %s. Main sample: directly recorded attendees with both sources matched and observed.", FROM, TO),
  sprintf("%s unit-days; %s source units; %s informative conference dates; %s asking unit-days.",
          nrow(sample), n_distinct(sample$unit_id), n_distinct(sample$date), sum(sample$ask)), "",
  "Individual models: covariate ~ ask + prior_questions_per_recorded_attendance | date.",
  "Joint model: ask ~ core covariates (including the ratio) + missing indicators | date. Its joint null still includes the ratio; it is not a partial test excluding that predictor.",
  "SEs cluster by deduplicated attendance-source unit. No unit FE, minimum-attendance threshold, winsorization, permutations, or outcome regressions.", "",
  "## Individual balance conditional on prior questions / recorded attendance", "",
  sprintf("Eligible conditional sample: %s outlet-days, %s units, %s dates. Undefined ratios are excluded rather than treated as observed zero.", nrow(ratio_sample), n_distinct(ratio_sample$unit_id), n_distinct(ratio_sample$date)), "",
  "| Covariate | Day FE only | Day FE + prior ratio | Adjusted 95% CI | Adjusted p-value | N |",
  "|---|---:|---:|---|---:|---:|", rows_md, "",
  "Both estimates on each row use exactly the same sample. This separates conditioning from changes caused by dropping undefined ratios. Raw means remain in the CSV.",
  "The prior ratio is not tested against itself. Standalone prior-question and attendance counts are removed from all tests; supplementary contracts, coverage and other ratio windows remain in individual_balance_all_windows.csv.", "",
  "## Joint regression", "",
  sprintf("Substantive covariates: F(%s, %s) = %.3f; p = %s.", joint_wald$df1, joint_wald$df2, joint_wald$stat, fp(joint_wald$p)),
  sprintf("Covariates plus missingness: F(%s, %s) = %.3f; p = %s.", all_wald$df1, all_wald$df2, all_wald$stat, fp(all_wald$p)),
  sprintf("Within R-squared: %.4f. N = %s.", r2(joint, "wr2")[[1]], nobs(joint)),
  "Continuous core regressors are divided by their observed sample SD in the joint model; binary regressors retain 0/1 units. Neutral / unclear is the ideology reference. Remaining missing values (e.g. age, distance, unresolved ideology, undefined ratios) get zero plus missing indicators only in the joint model. Tests concern retained, non-collinear coefficients.",
  "",
  "Coefficients below are percentage-point differences in asking probability, conditional on the other regressors and date. They are associations, not causal effects.",
  "",
  "| Covariate | Coefficient (pp) | 95% CI (pp) | p-value |",
  "|---|---:|---|---:|", joint_rows_md, "",
  paste("Collinear terms omitted:", paste(joint$collin.var, collapse = ", ")), "",
  "## Sample and data caveats", "",
  paste("Ambiguous attendance mappings excluded:", paste(bad_a$attendance_entity_id, collapse = "; ")),
  "Shared source pairs count once. Format/scope/subscription flags equal 1 if any metadata member has the attribute and 0 otherwise, including missing flags. Social media and personal are separate. Conflicting political classifications remain missing across all three ideology indicators; neutral is not assigned arbitrarily.",
  "Contract histories sum distinct beneficiaries once per unit/window; absent or unavailable histories contribute zero by the user's convention. This does not establish that an unmatched outlet truly received no money. Shared beneficiaries can still recur across different source units: these are covariates, not an aggregate spending total. Units without a question-source match remain excluded.",
  "Age uses only unambiguous four-digit founding years. Negative money totals are missing in the log specification. Current metadata are not necessarily pre-lottery measurements.",
  "The main questions/attendance covariate is prior-year questions divided by recorded journalist attendance records on dates covered by both sources. It is not question-days divided by attendance-days, and can exceed 1. A zero denominator remains missing; the joint model flags that missingness. November 2021 is excluded from this common-date ratio.",
  "The joint model uses questions/recorded-attendance, contract values/counts, and metadata; standalone prior-question and attendance counts are removed. Individual p-values are unadjusted for multiple testing.",
  "Results concern observable balance in the resolved metadata-linked sample conditional on date, not a direct test of the seating draws.")
writeLines(report, file.path(out, "RESULTS.md"))
tex_rows <- sprintf("%s & %s & %s & %s & %s & %s \\\\", main_table$label,
                    fmt(main_table$unadjusted_estimate), fmt(main_table$estimate),
                    fmt(main_table$se), fp(main_table$p_value), main_table$n)
writeLines(c("% Requires booktabs; same-sample date-FE comparisons before/after prior-ratio control.",
             "% SE and p concern the prior-ratio-adjusted coefficient. Clustered by source unit.",
             "\\begin{tabular}{lrrrrr}", "\\toprule",
             "Covariate & Day FE only & + Prior ratio & SE & $p$ & N \\\\", "\\midrule", tex_rows,
             "\\bottomrule", "\\end{tabular}"), file.path(out, "balance_core.tex"))
etable(joint, tex = TRUE, file = file.path(out, "joint_regression.tex"), replace = TRUE,
       dict = joint_labels, fitstat = ~ n + wr2, title = "Question access: joint balance regression",
       notes = c("Recorded attendees; April 18, 2022 to September 27, 2024.",
                 "Continuous regressors are in SD units; coefficients are probability units, not percentage points.",
                 "Missing covariates are zero-imputed with missing indicators. Question attribution is provisional."))
writeLines(capture.output(sessionInfo()), file.path(out, "session_info.txt"))
print(flow)
print(main_table |> select(label, estimate, p_value, n))
print(joint_wald)
cat("Results saved to:", out, "\n")

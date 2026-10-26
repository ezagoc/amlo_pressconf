# Ratio-only balance, with alternative pre-lottery windows.
# Run: Rscript code/08-results/balance/03-prior_ratio_balance.R
suppressPackageStartupMessages({library(arrow); library(dplyr); library(tidyr); library(fixest); library(lubridate)})
arg <- grep("^--file=", commandArgs(FALSE), value = TRUE)
script <- if (length(arg)) sub("^--file=", "", arg[[1]]) else
  file.path(getwd(), "code/08-results/balance/03-prior_ratio_balance.R")
root <- normalizePath(file.path(dirname(script), "../../.."), mustWork = TRUE)
source(file.path(root, "project_paths.R"))
LOTTERY <- as.Date("2022-04-18")
HISTORY_FROM <- as.Date("2018-12-01")
POST_TO <- as.Date("2024-09-27")
MONTH_WINDOWS <- c(12L, 18L, 24L) # Edit this vector to add other trailing windows.
EXCLUDE_ATTENDANCE_MONTHS <- "2021-11"
out <- file.path(root, "output/balance/prior_ratios")
dir.create(out, recursive = TRUE, showWarnings = FALSE)
source_dir <- media_path("data/06-outcomes/deduplicated_source_panels")
setFixest_nthreads(1)

# Metadata is used only as an ID crosswalk, never as a regression covariate.
links <- read_parquet(file.path(source_dir, "metadata_outcome_crosswalk.parquet")) |>
  select(metadata_id, outcome, entity_id) |> distinct() |>
  filter(outcome %in% c("attendance", "questions")) |>
  pivot_wider(names_from = outcome, values_from = entity_id) |>
  filter(!is.na(attendance), !is.na(questions)) |> distinct(attendance, questions)
bad_a <- links |> count(attendance) |> filter(n > 1)
bad_q <- links |> count(questions) |> filter(n > 1)
mapping <- links |> mutate(excluded = attendance %in% bad_a$attendance | questions %in% bad_q$questions)
write.csv(mapping, file.path(out, "source_mapping.csv"), row.names = FALSE)
links <- mapping |> filter(!excluded) |> select(-excluded) |> mutate(unit_id = attendance)

a <- open_dataset(file.path(source_dir, "attendance_entity_daily_panel.parquet")) |>
  filter(date >= HISTORY_FROM, date <= POST_TO) |>
  select(entity_id, date, source_entity_matched, source_date_observed, attendance_n_journalists_recorded) |>
  collect() |> rename(attendance = entity_id, attendance_matched = source_entity_matched,
                      attendance_observed = source_date_observed, records = attendance_n_journalists_recorded)
q <- open_dataset(file.path(source_dir, "questions_entity_daily_panel.parquet")) |>
  filter(date >= HISTORY_FROM, date <= POST_TO) |>
  select(entity_id, date, source_entity_matched, source_date_observed, questions_n, question_asked) |>
  collect() |> rename(questions = entity_id, questions_matched = source_entity_matched,
                      questions_observed = source_date_observed, ask = question_asked)
stopifnot(!anyDuplicated(a[c("attendance", "date")]), !anyDuplicated(q[c("questions", "date")]))
daily <- a |> inner_join(links, by = "attendance", relationship = "many-to-one") |>
  inner_join(q, by = c("questions", "date"), relationship = "one-to-one") |>
  mutate(covered = coalesce(attendance_matched & attendance_observed & questions_matched &
                            questions_observed, FALSE) & is.finite(records) & is.finite(questions_n))
stopifnot(!anyDuplicated(daily[c("unit_id", "date")]))

windows <- tibble(variable = c(paste0("ratio_", MONTH_WINDOWS, "m"), "ratio_full"),
                  label = c(paste(MONTH_WINDOWS, "months"), "Full pre-lottery"),
                  from = c(LOTTERY %m-% months(MONTH_WINDOWS), HISTORY_FROM),
                  to = LOTTERY - 1)
stopifnot(all(windows$from >= HISTORY_FROM), all(windows$to < LOTTERY), !anyDuplicated(windows$variable))
write.csv(windows, file.path(out, "windows.csv"), row.names = FALSE)
history <- daily |> filter(date < LOTTERY) |>
  mutate(common = covered & !format(date, "%Y-%m") %in% EXCLUDE_ATTENDANCE_MONTHS) |>
  select(unit_id, date, records, questions_n, common)
histories <- bind_rows(lapply(seq_len(nrow(windows)), function(i) {
  w <- windows[i, ]
  history |> filter(between(date, w$from, w$to)) |> group_by(unit_id) |>
    summarise(variable = w$variable, numerator = if (any(common)) sum(questions_n[common]) else NA_real_,
              denominator = if (any(common)) sum(records[common]) else NA_real_,
              common_dates = sum(common),
              first_common = if (any(common)) min(date[common]) else as.Date(NA),
              last_common = if (any(common)) max(date[common]) else as.Date(NA),
              .groups = "drop") |>
    mutate(ratio = ifelse(is.finite(denominator) & denominator > 0, numerator / denominator, NA_real_))
}))
write.csv(histories, file.path(out, "ratio_history_audit.csv"), row.names = FALSE)
ratios <- histories |> select(unit_id, variable, ratio) |>
  pivot_wider(names_from = variable, values_from = ratio)
ratio_vars <- windows$variable
informative <- function(x) x |> group_by(date) |> filter(any(ask == 1), any(ask == 0)) |> ungroup()
attendees <- daily |> filter(date >= LOTTERY, covered, records > 0, is.finite(ask)) |>
  select(unit_id, date, ask, records) |> left_join(ratios, by = "unit_id", relationship = "many-to-one")
base <- informative(attendees)
sample <- informative(base |> filter(if_all(all_of(ratio_vars), is.finite)))
stopifnot(nrow(sample) > 0, all(sample$records > 0), all(sample$ask %in% 0:1),
          !anyDuplicated(sample[c("unit_id", "date")]))
count_sample <- function(x, stage) tibble(stage = stage, n = nrow(x), units = n_distinct(x$unit_id),
                                         dates = n_distinct(x$date), asking = sum(x$ask))
flow <- bind_rows(count_sample(attendees, "Covered recorded attendees"),
                 count_sample(base, "Dates with asking and non-asking outlets"),
                 count_sample(sample, "All four ratios defined: common estimation sample"))
write.csv(flow, file.path(out, "sample_flow.csv"), row.names = FALSE)

# Individual balance: one historical ratio at a time; same post-lottery sample.
individual <- list()
balance <- bind_rows(lapply(ratio_vars, function(v) {
  fit <- feols(as.formula(paste(v, "~ ask | date")), sample, cluster = ~unit_id, notes = FALSE)
  individual[[v]] <<- fit
  ct <- coeftable(fit)["ask", ]; ci <- confint(fit, "ask")
  tibble(variable = v, asking_mean = mean(sample[[v]][sample$ask == 1]),
         nonasking_mean = mean(sample[[v]][sample$ask == 0]), estimate = ct[[1]],
         se = ct[[2]], ci_low = ci[[1]], ci_high = ci[[2]], p_value = ct[[4]],
         n = nobs(fit), units = n_distinct(sample$unit_id), dates = n_distinct(sample$date))
})) |> left_join(windows, by = "variable")
write.csv(balance, file.path(out, "individual_balance.csv"), row.names = FALSE)

# Joint model contains ONLY the four ratios and date FE; no imputation.
# Scale to 1 sample SD for comparability. Overlapping windows are correlated.
scales <- vapply(sample[ratio_vars], sd, numeric(1))
stopifnot(all(scales > 0))
joint_data <- sample
for (v in ratio_vars) joint_data[[v]] <- joint_data[[v]] / scales[[v]]
joint <- feols(as.formula(paste("ask ~", paste(ratio_vars, collapse = " + "), "| date")),
               joint_data, cluster = ~unit_id, notes = FALSE)
stopifnot(setequal(names(coef(joint)), ratio_vars))
joint_test <- wald(joint, print = FALSE)
jt <- as.data.frame(coeftable(joint))
names(jt) <- c("estimate", "se", "t", "p_value")
jt$variable <- rownames(jt); rownames(jt) <- NULL
jt$ci_low <- confint(joint)[, 1]; jt$ci_high <- confint(joint)[, 2]
jt$sd <- scales[jt$variable]
jt <- left_join(jt, windows, by = "variable")
write.csv(jt, file.path(out, "joint_regression.csv"), row.names = FALSE)
write.csv(tibble(F = joint_test$stat, p = joint_test$p, df1 = joint_test$df1, df2 = joint_test$df2,
                 n = nobs(joint), units = n_distinct(sample$unit_id), dates = n_distinct(sample$date),
                 within_r2 = r2(joint, "wr2")[[1]]), file.path(out, "joint_test.csv"), row.names = FALSE)
write.csv(cor(sample[ratio_vars]), file.path(out, "ratio_correlations.csv"))

# Show how available coverage differs without changing the primary comparison.
support <- bind_rows(lapply(ratio_vars, function(v) {
  available <- informative(base |> filter(is.finite(.data[[v]])))
  h <- histories |> filter(variable == v, unit_id %in% sample$unit_id)
  tibble(variable = v, available_n = nrow(available), available_units = n_distinct(available$unit_id),
         common_n = nrow(sample), common_units = n_distinct(sample$unit_id),
         min_covered_dates = min(h$common_dates), max_covered_dates = max(h$common_dates),
         first_common = min(h$first_common), last_common = max(h$last_common))
})) |> left_join(windows, by = "variable")
write.csv(support, file.path(out, "window_support.csv"), row.names = FALSE)
saveRDS(list(individual = individual, joint = joint, joint_test = joint_test, sample = sample,
             base = base, history = history, histories = histories, windows = windows, scales = scales),
        file.path(out, "models.rds"))
fmt <- function(x) formatC(x, digits = 3, format = "f")
fp <- function(x) ifelse(x < .001, "<0.001", fmt(x))
report <- c("# Historical ratios only", "",
  "The earlier control used 12 months (2021-04-18 to 2022-04-17). This analysis compares 12, 18, 24 months and the full available pre-lottery history.", "",
  "Ratio = total questions / recorded journalist attendance records on dates covered by both sources. All windows end 2022-04-17. November 2021 is excluded from both numerator and denominator. Zero denominators remain undefined; no zero-imputation.", "",
  "Post period: 2022-04-18 to 2024-09-27. Recorded attendees only; source-ID exclusions are unchanged. Metadata is used only to link sources, not as a predictor. No contracts, ideology, media characteristics or standalone counts enter the models.", "",
  sprintf("Common estimation sample: %s outlet-days, %s source units, %s dates.", nrow(sample), n_distinct(sample$unit_id), n_distinct(sample$date)), "",
  "## Individual balance: ratio ~ asked_question | date", "",
  "| Prior window | Start | Asking mean | Non-asking mean | Adjusted difference | 95% CI | p-value |",
  "|---|---|---:|---:|---:|---|---:|",
  sprintf("| %s | %s | %s | %s | %s | [%s, %s] | %s |", balance$label, balance$from,
          fmt(balance$asking_mean), fmt(balance$nonasking_mean), fmt(balance$estimate),
          fmt(balance$ci_low), fmt(balance$ci_high), fp(balance$p_value)), "",
  "Differences are in questions per attendance record, not percentage points. This is a ratio of totals, not an average daily ratio or probability of asking.", "",
  "## Joint model: asked_question ~ all four ratios | date", "",
  sprintf("F(%s, %s) = %.3f; p = %.4g. N = %s.", joint_test$df1, joint_test$df2,
          joint_test$stat, joint_test$p, nobs(joint)),
  "Each ratio is scaled by its sample SD. The joint null tests all four coefficients together. Because the windows overlap, coefficients conditional on all other windows can be unstable; do not rank windows solely by joint-model p-values.", "",
  "| Prior window | Coefficient (pp per SD) | 95% CI (pp) | p-value |",
  "|---|---:|---|---:|",
  sprintf("| %s | %s | [%s, %s] | %s |", jt$label, fmt(100 * jt$estimate),
          fmt(100 * jt$ci_low), fmt(100 * jt$ci_high), fp(jt$p_value)), "",
  "All SEs cluster by source unit. Both model families use the same common sample. Individual p-values are unadjusted for multiple comparisons. This run tests the ratios themselves, not metadata balance conditional on those ratios.", "",
  "Full history nominally begins 2018-12-01, but only common-covered dates contribute; see window_support.csv for actual coverage. Provisional: pending speaker-attribution corrections remain unapplied. Earlier metadata analyses are preserved separately.")
writeLines(report, file.path(out, "RESULTS.md"))
etable(joint, tex = TRUE, file = file.path(out, "joint_ratios.tex"), replace = TRUE,
       dict = setNames(paste0(windows$label, " [1 SD]"), ratio_vars), fitstat = ~ n + wr2)
writeLines(capture.output(sessionInfo()), file.path(out, "session_info.txt"))
print(windows); print(flow); print(balance |> select(label, estimate, p_value, n)); print(joint_test)
cat("Saved to", out, "\n")

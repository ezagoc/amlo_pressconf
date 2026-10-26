# Extend the prior-ratio comparison to contracts and YouTube histories.
# Run 03-prior_ratio_balance.R first, then this file. No upstream data are edited.
suppressPackageStartupMessages({library(arrow); library(dplyr); library(tidyr); library(fixest)})
arg <- grep("^--file=", commandArgs(FALSE), value = TRUE)
script <- if (length(arg)) sub("^--file=", "", arg[[1]]) else
  file.path(getwd(), "code/08-results/balance/05-historical_outcome_balance.R")
root <- normalizePath(file.path(dirname(script), "../../.."), mustWork = TRUE)
source(file.path(root, "project_paths.R"))
source(file.path(root, "src/baseline_history.R"))
old <- readRDS(file.path(root, "output/balance/prior_ratios/models.rds"))
windows <- old$windows |> rename(window = variable)
base <- old$base |> select(unit_id, date, ask, records)
out <- file.path(root, "output/balance/historical_outcomes")
dir.create(out, recursive = TRUE, showWarnings = FALSE)
source_dir <- media_path("data/06-outcomes/deduplicated_source_panels")
setFixest_nthreads(1)
write.csv(windows, file.path(out, "windows.csv"), row.names = FALSE)

# Link via source IDs and deduplicate each company/channel within a source unit.
crosswalk <- read_parquet(file.path(source_dir, "metadata_outcome_crosswalk.parquet")) |>
  select(metadata_id, outcome, entity_id) |> distinct()
aq <- crosswalk |> filter(outcome %in% c("attendance", "questions")) |>
  pivot_wider(names_from = outcome, values_from = entity_id)
resolved <- read.csv(file.path(root, "output/balance/prior_ratios/source_mapping.csv")) |>
  filter(!excluded) |> select(attendance, questions) |> mutate(unit_id = attendance)
metadata_links <- aq |> inner_join(resolved, by = c("attendance", "questions"), relationship = "many-to-one") |>
  filter(unit_id %in% base$unit_id) |> select(metadata_id, unit_id)
asset_links <- metadata_links |>
  inner_join(crosswalk |> filter(outcome %in% c("contracts", "youtube")),
             by = "metadata_id", relationship = "many-to-many") |>
  distinct(unit_id, outcome, entity_id)
write.csv(asset_links, file.path(out, "company_channel_links.csv"), row.names = FALSE)
stopifnot(!anyDuplicated(asset_links[c("unit_id", "outcome", "entity_id")]))

cdata <- open_dataset(file.path(source_dir, "contracts_entity_daily_panel.parquet")) |>
  filter(date >= as.Date("2018-12-01"), date < as.Date("2022-04-18")) |>
  select(entity_id, date, source_entity_matched, source_date_observed, contracts_costo, contracts_received_n) |>
  collect() |> mutate(covered = coalesce(source_entity_matched & source_date_observed, FALSE)) |>
  inner_join(asset_links |> filter(outcome == "contracts"), by = "entity_id", relationship = "many-to-many")
stopifnot(!anyDuplicated(cdata[c("unit_id", "entity_id", "date")]))
contracts <- bind_rows(lapply(seq_len(nrow(windows)), function(i) {
  w <- windows[i, ]
  observed <- cdata |> filter(between(date, w$from, w$to)) |> group_by(unit_id) |>
    summarise(contract_value = history_sum(contracts_costo[covered]),
              contract_count = history_sum(contracts_received_n[covered]),
              beneficiary_dates = sum(covered), beneficiaries = n_distinct(entity_id),
              .groups = "drop")
  tibble(unit_id = unique(base$unit_id)) |> left_join(observed, by = "unit_id") |>
    # Restore the original baseline rule: no observed history is NA, not zero.
    # Only audit counts are zero-filled. Observed beneficiaries with no awards
    # in this window retain genuine zeros from the source calendar panel.
    mutate(across(c(beneficiary_dates, beneficiaries), ~ coalesce(.x, 0)), window = w$window)
}))
write.csv(contracts, file.path(out, "contract_histories.csv"), row.names = FALSE)

# The upstream YouTube source is a balanced channel-calendar panel, not an
# independently audited completeness indicator. Unknown channels remain NA.
# Views/likes/comments are saved snapshot engagement for videos PUBLISHED in
# the historical window, not verified engagement measured before the lottery.
ydata <- open_dataset(file.path(source_dir, "youtube_entity_daily_panel.parquet")) |>
  filter(date >= as.Date("2018-12-01"), date < as.Date("2022-04-18")) |>
  select(entity_id, date, source_entity_matched, source_date_observed,
         youtube_n_videos, youtube_views, youtube_likes, youtube_comments,
         youtube_flag_no_2018, youtube_flag_no_2021) |> collect() |>
  mutate(covered = coalesce(source_entity_matched & source_date_observed, FALSE)) |>
  inner_join(asset_links |> filter(outcome == "youtube"), by = "entity_id", relationship = "many-to-many")
stopifnot(!anyDuplicated(ydata[c("unit_id", "entity_id", "date")]))
youtube <- bind_rows(lapply(seq_len(nrow(windows)), function(i) {
  w <- windows[i, ]
  ydata |> filter(between(date, w$from, w$to)) |> group_by(unit_id) |>
    summarise(window = w$window, channels = n_distinct(entity_id),
              expected_channel_days = channels * (as.integer(w$to - w$from) + 1L),
              observed_channel_days = sum(covered), complete_grid = all(covered) & n() == expected_channel_days,
              flagged_no_2018 = any(youtube_flag_no_2018 > 0, na.rm = TRUE),
              flagged_no_2021 = any(youtube_flag_no_2021 > 0, na.rm = TRUE),
              videos = if (complete_grid) sum(youtube_n_videos) else NA_real_,
              views = if (complete_grid) sum(youtube_views) else NA_real_,
              likes = if (complete_grid) sum(youtube_likes) else NA_real_,
              comments = if (complete_grid) sum(youtube_comments) else NA_real_, .groups = "drop") |>
    mutate(interactions = likes + comments,
           views_per_video = ifelse(videos > 0, views / videos, ifelse(videos == 0, 0, NA_real_)),
           likes_per_video = ifelse(videos > 0, likes / videos, ifelse(videos == 0, 0, NA_real_)),
           comments_per_video = ifelse(videos > 0, comments / videos, ifelse(videos == 0, 0, NA_real_)),
           interactions_per_video = ifelse(videos > 0, interactions / videos, ifelse(videos == 0, 0, NA_real_)))
}))
write.csv(youtube, file.path(out, "youtube_histories.csv"), row.names = FALSE)

spec <- tibble(
  metric = c("question_attendance_ratio", "contract_value", "contract_count", "videos", "views",
             "likes", "comments", "interactions", "views_per_video", "likes_per_video",
             "comments_per_video", "interactions_per_video"),
  label = c("Questions / recorded attendance", "Contract value (MXN)", "Contracts received",
            "YouTube videos", "YouTube views", "YouTube likes", "YouTube comments",
            "YouTube interactions", "Views per video", "Likes per video",
            "Comments per video", "Interactions per video"),
  family = c("Access", rep("Contracts", 2), rep("YouTube", 9)),
  transformation = c("Raw ratio", rep("log(1 + x)", 11)))
all_history <- bind_rows(
  old$histories |> filter(unit_id %in% base$unit_id) |>
    transmute(unit_id, window = variable, metric = "question_attendance_ratio", raw = ratio),
  contracts |> select(unit_id, window, contract_value, contract_count) |>
    pivot_longer(-c(unit_id, window), names_to = "metric", values_to = "raw"),
  youtube |> select(unit_id, window, all_of(spec$metric[spec$family == "YouTube"])) |>
    pivot_longer(-c(unit_id, window), names_to = "metric", values_to = "raw")
) |> left_join(spec, by = "metric") |>
  mutate(value = ifelse(transformation == "Raw ratio", raw,
                        ifelse(is.finite(raw) & raw >= 0, log1p(pmax(raw, 0)), NA_real_)))
stopifnot(!anyDuplicated(all_history[c("unit_id", "window", "metric")]))
write.csv(all_history, file.path(out, "historical_values.csv"), row.names = FALSE)
write.csv(spec, file.path(out, "metric_definitions.csv"), row.names = FALSE)
informative <- function(d) d |> group_by(date) |> filter(any(ask == 1), any(ask == 0)) |> ungroup()
models <- list(); samples <- list(); balance_rows <- list(); tests <- list(); joint_rows <- list(); scales_all <- list()
for (m in spec$metric) {
  values <- all_history |> filter(metric == m) |> select(unit_id, window, value) |>
    pivot_wider(names_from = window, values_from = value)
  d <- base |> left_join(values, by = "unit_id", relationship = "many-to-one") |>
    filter(if_all(all_of(windows$window), is.finite)) |> informative()
  stopifnot(nrow(d) > 0, !anyDuplicated(d[c("unit_id", "date")]), all(d$records > 0))
  samples[[m]] <- d
  models[[m]] <- list()
  for (v in windows$window) {
    fit <- feols(as.formula(paste(v, "~ ask | date")), d, cluster = ~unit_id, notes = FALSE)
    models[[m]][[v]] <- fit
    ct <- coeftable(fit)["ask", ]; ci <- confint(fit, "ask")
    balance_rows[[length(balance_rows) + 1L]] <- tibble(
      metric = m, window = v, asking_mean = mean(d[[v]][d$ask == 1]),
      nonasking_mean = mean(d[[v]][d$ask == 0]), estimate = ct[[1]], se = ct[[2]],
      ci_low = ci[[1]], ci_high = ci[[2]], p_value = ct[[4]], n = nrow(d),
      units = n_distinct(d$unit_id), dates = n_distinct(d$date))
  }
  scales <- vapply(d[windows$window], sd, numeric(1))
  stopifnot(all(scales > 0))
  scales_all[[m]] <- scales
  dj <- d
  for (v in windows$window) dj[[v]] <- dj[[v]] / scales[[v]]
  joint <- feols(as.formula(paste("ask ~", paste(windows$window, collapse = " + "), "| date")),
                 dj, cluster = ~unit_id, notes = FALSE)
  models[[m]]$joint <- joint
  wt <- wald(joint, print = FALSE)
  stopifnot(is.list(wt), is.finite(wt$p))
  tests[[m]] <- tibble(metric = m, F = wt$stat, p_value = wt$p, df1 = wt$df1, df2 = wt$df2,
                      n = nrow(d), units = n_distinct(d$unit_id), dates = n_distinct(d$date),
                      within_r2 = r2(joint, "wr2")[[1]],
                      omitted = paste(joint$collin.var, collapse = "; "))
  ct <- as.data.frame(coeftable(joint))
  names(ct) <- c("estimate", "se", "t", "p_value")
  ct$window <- rownames(ct); rownames(ct) <- NULL
  ct$ci_low <- confint(joint)[, 1]; ct$ci_high <- confint(joint)[, 2]
  joint_rows[[m]] <- mutate(ct, metric = m, sd = scales[window])
}
balance <- bind_rows(balance_rows) |> left_join(spec, by = "metric") |>
  left_join(windows |> rename(window_label = label), by = "window")
joint_tests <- bind_rows(tests) |> left_join(spec, by = "metric")
joint_coefficients <- bind_rows(joint_rows) |> left_join(spec, by = "metric") |>
  left_join(windows |> rename(window_label = label), by = "window")
write.csv(balance, file.path(out, "individual_balance.csv"), row.names = FALSE)
write.csv(joint_tests, file.path(out, "joint_tests.csv"), row.names = FALSE)
write.csv(joint_coefficients, file.path(out, "joint_coefficients.csv"), row.names = FALSE)
write.csv(bind_rows(lapply(names(samples), function(m) {
  d <- samples[[m]]
  tibble(metric = m, n = nrow(d), units = n_distinct(d$unit_id), dates = n_distinct(d$date),
         excluded_unit_days = nrow(base) - nrow(d))
})), file.path(out, "sample_audit.csv"), row.names = FALSE)
saveRDS(list(models = models, samples = samples, histories = all_history, spec = spec,
             windows = windows, scales = scales_all, asset_links = asset_links,
             contracts = contracts, youtube = youtube, contract_source = cdata,
             youtube_source = ydata, joint_tests = joint_tests), file.path(out, "models.rds"))

fp <- function(x) ifelse(x < .001, "<0.001", formatC(x, digits = 3, format = "f"))
report <- c("# Historical balance: access, contracts and YouTube", "",
  "12-, 18-, 24-month and full available pre-lottery histories; all end April 17, 2022. Post period: April 18, 2022 to September 27, 2024.", "",
  "Individual regressions: historical measure ~ asked_question | date. Joint tests: asked_question ~ the four windows of ONE measure | date. No metadata predictors or standalone prior attendance/question counts. Cluster SEs by source unit.", "",
  "Same sample across all four windows within each measure. Different measures may have different coverage; do not treat cross-measure changes as same-sample comparisons.", "",
  "The question/attendance ratio is raw. Contract and YouTube variables use log(1+x), without winsorization. Raw amounts and count denominators are saved in the audits.", "",
  "Contracts sum each distinct beneficiary once per outlet unit/window. Dates are contract/order dates; money is nominal MXN. Original baseline missingness is restored: no matched, observed history is NA and excluded from contract tests; observed beneficiaries with no awards in a window retain zero. With multiple beneficiaries, sums use available observed histories. Source matching identifies observed beneficiaries, not eligibility to compete for contracts.", "",
  "YouTube sums each distinct URL-token source once per outlet unit/window. Known archived channels with zero posts contribute 0, including per-video means; unmatched channels or incomplete linked-channel grids remain NA. The upstream coverage flag describes a balanced archive calendar, not independently verified completeness.", "",
  "IMPORTANT: YouTube engagement values are saved snapshot counts for videos published in the historical window. Their measurement date is not established as pre-lottery. Treat engagement balance as descriptive, not valid evidence of balance in strictly pre-treatment covariates. Video publication counts are dated activity, subject to archive coverage.", "",
  "Interactions = likes + comments. Each per-video mean is the window total divided by videos published in that window, not the average of daily per-video means. November 2021 is excluded only from the question/attendance ratio; retained for contracts and YouTube.", "",
  "## Individual balance", "",
  "| Measure | Window | Difference | p-value | N | Units |",
  "|---|---|---:|---:|---:|---:|",
  sprintf("| %s | %s | %.3f | %s | %s | %s |", balance$label, balance$window_label,
          balance$estimate, fp(balance$p_value), balance$n, balance$units), "",
  "## Joint test across the four windows of each measure", "",
  "| Measure | F | p-value | N | Units |",
  "|---|---:|---:|---:|---:|",
  sprintf("| %s | %.3f | %s | %s | %s |", joint_tests$label, joint_tests$F,
          fp(joint_tests$p_value), joint_tests$n, joint_tests$units), "",
  "These are separate joint tests by measure, not one regression containing all metrics. Windows overlap; joint coefficients may be imprecise. All individual p-values are unadjusted for multiple testing. Ratio coverage limitations, five excluded source mappings and pending transcript-attribution corrections remain unchanged.")
writeLines(report, file.path(out, "RESULTS.md"))
writeLines(capture.output(sessionInfo()), file.path(out, "session_info.txt"))
print(joint_tests |> select(label, F, p_value, n, units, dates))
cat("Saved to", out, "\n")

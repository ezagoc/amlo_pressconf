# Same-day YouTube engagement: recorded attendees, post-lottery AMLO sample.
# No raw sources, prior models, or upstream panels are modified.
entry <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)[1])
source(file.path(dirname(entry), "00-config.R"))
suppressPackageStartupMessages({
  library(arrow); library(dplyr); library(tidyr); library(fixest)
})
setFixest_nthreads(1)
old_path <- file.path(root, "output/balance/prior_ratios/models.rds")
old <- readRDS(old_path)
base <- old$base |> select(unit_id, date, ask, records)
histories <- old$histories |> filter(variable == "ratio_12m") |>
  select(unit_id, prior_ratio = ratio, numerator, denominator, common_dates,
         first_common, last_common)
stopifnot(!anyDuplicated(histories$unit_id), all(base$records > 0),
          all(base$date >= FROM & base$date <= TO))

# Establish source pairs as in the balance analysis; ambiguous pairs stay excluded.
cw <- read_parquet(file.path(source_dir, "metadata_outcome_crosswalk.parquet"))
aq <- cw |> filter(outcome %in% c("attendance", "questions")) |>
  select(metadata_id, outcome, entity_id) |> distinct() |>
  pivot_wider(names_from = outcome, values_from = entity_id)
pairs <- aq |> filter(!is.na(attendance), !is.na(questions)) |> distinct(attendance, questions)
bad_a <- pairs |> count(attendance) |> filter(n > 1)
bad_q <- pairs |> count(questions) |> filter(n > 1)
resolved <- pairs |> anti_join(bad_a, by = "attendance") |>
  anti_join(bad_q, by = "questions") |> mutate(unit_id = attendance)
saved_pairs <- read.csv(file.path(root, "output/balance/prior_ratios/source_mapping.csv")) |>
  filter(!excluded) |> select(attendance, questions)
stopifnot(nrow(anti_join(resolved, saved_pairs, by = c("attendance", "questions"))) == 0,
          nrow(anti_join(saved_pairs, resolved, by = c("attendance", "questions"))) == 0)

# Fail on stale balance-source data, rather than silently mixing panel vintages.
a <- open_dataset(file.path(source_dir, "attendance_entity_daily_panel.parquet")) |>
  filter(date >= FROM, date <= TO) |>
  select(entity_id, date, source_entity_matched, source_date_observed,
         attendance_n_journalists_recorded) |> collect() |>
  filter(source_entity_matched, source_date_observed) |>
  transmute(attendance = entity_id, date, records = attendance_n_journalists_recorded)
q <- open_dataset(file.path(source_dir, "questions_entity_daily_panel.parquet")) |>
  filter(date >= FROM, date <= TO) |>
  select(entity_id, date, source_entity_matched, source_date_observed, question_asked) |>
  collect() |> filter(source_entity_matched, source_date_observed) |>
  transmute(questions = entity_id, date, ask = question_asked)
fresh_joined <- a |> inner_join(resolved, by = "attendance", relationship = "many-to-one") |>
  inner_join(q, by = c("questions", "date"), relationship = "one-to-one") |>
  filter(records > 0, is.finite(ask))
fresh <- fresh_joined |> informative() |>
  select(unit_id, date, ask, records) |> arrange(unit_id, date)
stopifnot(isTRUE(all.equal(as.data.frame(fresh),
                          as.data.frame(arrange(base, unit_id, date)), check.attributes = FALSE)))
recorded <- a |> filter(records > 0) |> mutate(unit_id = attendance)
upstream_flow <- bind_rows(
  flow_row(mutate(recorded, ask = NA_real_), "All matched, recorded attendance units"),
  flow_row(recorded |> semi_join(resolved, by = "attendance") |> mutate(ask = NA_real_),
           "Unambiguous attendance-question source pair"),
  flow_row(fresh_joined, "Both sources matched and date observed"),
  flow_row(fresh, "Balance sample: asking and nonasking on same date"))
save_csv(upstream_flow, "upstream_attendance_flow.csv")
save_csv(recorded |> anti_join(resolved, by = "attendance") |>
           count(unit_id, name = "recorded_days"), "unresolved_attendance_units.csv")

# Each channel/source entity must belong to only one resolved source unit.
# Multiple distinct channels within a unit are summed once, never per metadata row.
links <- aq |> inner_join(resolved, by = c("attendance", "questions"), relationship = "many-to-one") |>
  select(metadata_id, unit_id) |>
  inner_join(cw |> filter(outcome == "youtube") |> select(metadata_id, entity_id),
             by = "metadata_id", relationship = "many-to-many") |> distinct(unit_id, entity_id)
shared <- links |> count(entity_id) |> filter(n > 1)
links <- links |> mutate(ambiguous_shared_channel = entity_id %in% shared$entity_id)
save_csv(links, "channel_mapping_audit.csv")
bad_units <- unique(links$unit_id[links$ambiguous_shared_channel])
links <- links |> filter(!unit_id %in% bad_units, unit_id %in% base$unit_id)
stopifnot(!anyDuplicated(links$entity_id))
unit_labels <- aq |> inner_join(resolved, by = c("attendance", "questions")) |>
  inner_join(cw |> distinct(metadata_id, outlet_name), by = "metadata_id", relationship = "many-to-many") |>
  group_by(unit_id) |> summarise(outlet_names = paste(sort(unique(outlet_name)), collapse = " / "),
                                .groups = "drop")

y <- open_dataset(file.path(source_dir, "youtube_entity_daily_panel.parquet")) |>
  filter(date >= FROM, date <= TO) |>
  select(entity_id, date, source_entity_matched, source_date_observed,
         youtube_n_videos, youtube_views, youtube_likes, youtube_comments,
         youtube_channel_ids) |> collect() |>
  inner_join(links, by = "entity_id", relationship = "many-to-one")
stopifnot(!anyDuplicated(y[c("entity_id", "date")]))
channel_ids <- y |> filter(source_entity_matched) |>
  distinct(entity_id, youtube_channel_ids) |>
  mutate(channel_ids = regmatches(youtube_channel_ids,
           gregexpr("UC[A-Za-z0-9_-]{22}", youtube_channel_ids))) |>
  select(entity_id, channel_ids) |> unnest_longer(channel_ids) |> distinct()
stopifnot(!anyDuplicated(channel_ids$channel_ids))
save_csv(channel_ids, "canonical_channel_id_audit.csv")
save_csv(y |> group_by(unit_id, entity_id) |>
           summarise(matched = any(source_entity_matched %in% TRUE),
                     observed_dates = sum(source_date_observed %in% TRUE),
                     total_dates = n(), .groups = "drop"),
         "channel_coverage_audit.csv")
channel_counts <- links |> count(unit_id, name = "expected_channels")
totals <- y |> left_join(channel_counts, by = "unit_id") |> group_by(unit_id, date) |>
  summarise(channels = first(expected_channels),
    observed_channels = sum(source_entity_matched & source_date_observed, na.rm = TRUE),
    covered = n() == first(expected_channels) &
      all(source_entity_matched %in% TRUE & source_date_observed %in% TRUE) &
      all(is.finite(youtube_views) & is.finite(youtube_likes) & is.finite(youtube_comments)),
    likes = if (covered) sum(youtube_likes) else NA_real_,
    comments = if (covered) sum(youtube_comments) else NA_real_,
    views = if (covered) sum(youtube_views) else NA_real_,
    videos = if (covered) sum(youtube_n_videos) else NA_real_, .groups = "drop")
joined <- base |> left_join(totals, by = c("unit_id", "date"), relationship = "one-to-one") |>
  left_join(histories, by = "unit_id", relationship = "many-to-one") |>
  left_join(unit_labels, by = "unit_id", relationship = "many-to-one")
save_csv(joined |> filter(!covered %in% TRUE) |>
           group_by(unit_id, outlet_names) |> summarise(n = n(), .groups = "drop"),
         "excluded_youtube_units.csv")
complete <- joined |> filter(covered %in% TRUE)
d <- informative(complete) |> arrange(unit_id, date) |>
  mutate(quarter = paste0(format(date, "%Y"), "Q", (as.integer(format(date, "%m")) - 1L) %/% 3L + 1L),
         missing_ratio = as.integer(!is.finite(prior_ratio)),
         ratio_filled = ifelse(missing_ratio == 1, 0, prior_ratio),
         sample_day = as.integer(date - FROM) + 1L)
stopifnot(nrow(d) > 0, !anyDuplicated(d[c("unit_id", "date")]),
          all(as.matrix(d[OUTCOMES]) >= 0), all(d$records > 0))

# Fixed baseline histories by calendar quarter, omitting the first quarter.
# Undefined ratios receive a zero estimation placeholder PLUS quarter-varying
# missingness controls; they are not interpreted as true zero participation.
quarters <- sort(unique(d$quarter))
controls <- character()
for (quarter in quarters[-1]) {
  v <- paste0("history_", quarter); m <- paste0("missing_", quarter)
  d[[v]] <- d$ratio_filled * as.integer(d$quarter == quarter)
  d[[m]] <- d$missing_ratio * as.integer(d$quarter == quarter)
  controls <- c(controls, v, m)
}
for (v in OUTCOMES) d[[paste0("log_", v)]] <- log1p(d[[v]])
flow <- bind_rows(flow_row(base, "Audited balance sample"),
                 flow_row(joined |> filter(!is.na(channels)), "Mapped unambiguous YouTube entities"),
                 flow_row(complete, "All mapped channels covered; all outcomes observed"),
                 flow_row(d, "Final: dates with askers and nonaskers"))
save_csv(flow, "sample_flow.csv")
save_csv(d |> distinct(unit_id, outlet_names, prior_ratio, missing_ratio, channels),
         "analysis_units.csv")
save_csv(histories, "prior_ratio_audit.csv")
saveRDS(list(data = d, controls = controls, quarters = quarters, links = links,
             histories = histories, flow = flow), file.path(out, "analysis_panel.rds"))

fits <- list(); results <- list(); diagnostics <- list(); cuts <- list()
extract <- function(fit, data, outcome, model, inference = "Outlet clustered") {
  inference_warnings <- character()
  fs <- withCallingHandlers(
    if (inference == "Outlet + date clustered") summary(fit, vcov = ~unit_id + date) else fit,
    warning = function(w) {
      inference_warnings <<- c(inference_warnings, conditionMessage(w))
      invokeRestart("muffleWarning")
    })
  ct <- coeftable(fs)["ask", ]; ci <- confint(fs, "ask")
  tibble(outcome, model, inference, estimate = ct[[1]], se = ct[[2]],
         ci_low = ci[[1]], ci_high = ci[[2]], p_value = ct[[4]],
         n = nobs(fit), units = n_distinct(data$unit_id[obs(fit)]),
         dates = n_distinct(data$date[obs(fit)]), asking = sum(data$ask[obs(fit)]),
         within_r2 = unname(r2(fit, "wr2")), bootstrap_replications = NA_integer_,
         inference_warning = paste(unique(inference_warnings), collapse = "; "))
}
for (outcome in OUTCOMES) {
  # Main models are not winsorized; bounds for the optional sensitivity use this
  # exact analysis sample and are applied BEFORE log1p.
  bounds <- quantile(d[[outcome]], c(.01, .99), names = FALSE)
  cuts[[outcome]] <- tibble(outcome, lower = bounds[1], upper = bounds[2])
  for (model in c("Baseline", "History adjusted", "Winsorized history adjusted",
                  "Observed-history adjusted", "Date FE only")) {
    ds <- if (model == "Observed-history adjusted") filter(d, missing_ratio == 0) |> informative() else d
    ds$Y <- if (model == "Winsorized history adjusted")
      log1p(pmin(pmax(ds[[outcome]], bounds[1]), bounds[2])) else log1p(ds[[outcome]])
    rhs <- if (model %in% c("Baseline", "Date FE only")) "ask" else paste(c("ask", controls), collapse = " + ")
    fes <- if (model == "Date FE only") "date" else "unit_id + date"
    fit <- feols(as.formula(paste("Y ~", rhs, "|", fes)), ds, cluster = ~unit_id,
                 notes = FALSE, data.save = TRUE)
    key <- paste(outcome, model, sep = ":")
    fits[[key]] <- fit
    results[[key]] <- extract(fit, ds, outcome, model)
    if (model %in% c("Baseline", "History adjusted"))
      results[[paste0(key, ":twoway")]] <- extract(fit, ds, outcome, model, "Outlet + date clustered")
    diagnostics[[key]] <- tibble(outcome, model,
      dropped_collinear = paste(fit$collin.var, collapse = "; "),
      rows_dropped = nrow(ds) - nobs(fit))
  }
}
results <- bind_rows(results)
stopifnot(all(is.finite(results$estimate)), all(is.finite(results$se)))
saveRDS(fits, file.path(out, "regression_fits.rds"))
save_csv(d[-obs(fits[["likes:Baseline"]]), c("unit_id", "date", "ask", "outlet_names")],
         "singleton_exclusions.csv")
save_csv(results, "regression_results.csv")
save_csv(bind_rows(diagnostics), "regression_diagnostics.csv")
save_csv(bind_rows(cuts), "winsorization_bounds.csv")
paths <- c(old_path, file.path(source_dir, c("metadata_outcome_crosswalk.parquet",
  "attendance_entity_daily_panel.parquet", "questions_entity_daily_panel.parquet",
  "youtube_entity_daily_panel.parquet")))
save_csv(data.frame(path = paths, md5 = unname(tools::md5sum(paths)),
                    modified = file.info(paths)$mtime), "input_manifest.csv")
writeLines(capture.output(sessionInfo()), file.path(out, "session_info.txt"))
print(flow)
print(results |> filter(model %in% c("Baseline", "History adjusted"),
                        inference == "Outlet clustered"), width = 160)
cat("Saved to ", out, "\n", sep = "")

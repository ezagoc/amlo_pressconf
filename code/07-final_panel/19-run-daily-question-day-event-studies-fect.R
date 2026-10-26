# Daily interaction event studies: question-day treatment, attendance indicator.
# FEct raw onset 1 = first treated day; raw exit 1 = first untreated day.
# Optional: --transformation=chen_roth_x0 for the minimum-positive log rule.
# Optional: --treatment=plus1 for the question day and next calendar day.
# Optional: --pre-days=14 --post-days=14 to extend the displayed/held-out windows.
# Optional: --plot-only to redraw saved estimates without re-estimating models.
# Optional: --no-winsorize to transform the original interaction counts.
# Optional: --outcome=mean_interactions|likes|comments|views; --skip-plots for batch reports.
# Optional: --split-independent separates metadata opp and unclear (Independent).
# Optional: --transformation=log1p --nboots=1000; --resume reuses completed fits.
args <- commandArgs(trailingOnly = FALSE)
split_independent <- "--split-independent" %in% commandArgs(trailingOnly = TRUE)
plot_only <- "--plot-only" %in% commandArgs(trailingOnly = TRUE)
skip_plots <- "--skip-plots" %in% commandArgs(trailingOnly = TRUE)
resume_fits <- "--resume" %in% commandArgs(trailingOnly = TRUE)
outcome_arg <- grep("^--outcome=", commandArgs(trailingOnly = TRUE), value = TRUE)
outcome <- if (length(outcome_arg)) sub("^--outcome=", "", outcome_arg[[1]]) else "interactions"
outcome_labels <- c(interactions = "Interactions", mean_interactions = "Mean interactions per video",
                    likes = "Likes", comments = "Comments", views = "Views")
stopifnot(outcome %in% names(outcome_labels))
outcome_label <- unname(outcome_labels[[outcome]])
winsorize_outcome <- !("--no-winsorize" %in% commandArgs(trailingOnly = TRUE))
transformation_arg <- grep("^--transformation=", commandArgs(trailingOnly = TRUE), value = TRUE)
transformation <- if (length(transformation_arg)) sub("^--transformation=", "", transformation_arg[[1]]) else "asinh"
stopifnot(transformation %in% c("asinh", "chen_roth_x0", "log1p"))
treatment_arg <- grep("^--treatment=", commandArgs(trailingOnly = TRUE), value = TRUE)
treatment <- if (length(treatment_arg)) sub("^--treatment=", "", treatment_arg[[1]]) else "question_day"
stopifnot(treatment %in% c("question_day", "plus1"))
treatment_column <- if (treatment == "plus1") "treatment_plus_1" else "treatment_day"
onset_last_day <- if (treatment == "plus1") 1L else 0L
treatment_label <- if (treatment == "plus1") "Question day and next calendar day" else "Question day only"
read_day_argument <- function(name, default) {
  option <- grep(paste0("^--", name, "="), commandArgs(trailingOnly = TRUE), value = TRUE)
  value <- if (length(option)) sub(paste0("^--", name, "="), "", option[[1]]) else as.character(default)
  stopifnot(grepl("^[0-9]+$", value))
  value <- as.integer(value)
  stopifnot(!is.na(value), value >= 1L)
  value
}
pre_days <- read_day_argument("pre-days", 4L)
post_days <- read_day_argument("post-days", 4L)
n_boots <- read_day_argument("nboots", 50L)
stopifnot(n_boots >= 2L)
script_arg <- grep("^--file=", args, value = TRUE)
script_path <- if (length(script_arg)) {
  sub("^--file=", "", script_arg[[1]])
} else if (requireNamespace("rstudioapi", quietly = TRUE) && rstudioapi::isAvailable()) {
  rstudioapi::getActiveDocumentContext()$path
} else {
  file.path(getwd(), "code", "07-final_panel", "19-run-daily-question-day-event-studies-fect.R")
}
repository_root <- normalizePath(file.path(dirname(script_path), "../.."), mustWork = TRUE)
suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
  library(ggplot2)
  library(arrow)
  library(fect)
})

transform_slug <- if (transformation == "asinh") "" else paste0(transformation, "_")
run_name <- paste0("daily_question_day_", transform_slug, "events_", n_boots)
pdf_prefix <- paste0("fect_daily_question_day_", transform_slug)
if (treatment == "plus1") {
  run_name <- sub("question_day", "question_day_plus1", run_name, fixed = TRUE)
  pdf_prefix <- sub("question_day", "question_day_plus1", pdf_prefix, fixed = TRUE)
}
if (!winsorize_outcome) {
  run_name <- paste0(run_name, "_unwinsorized")
  pdf_prefix <- paste0(pdf_prefix, "unwinsorized_")
}
if (pre_days != 4L || post_days != 4L) {
  horizon_suffix <- paste0("pre", pre_days, "_post", post_days)
  run_name <- paste0(run_name, "_", horizon_suffix)
  pdf_prefix <- paste0(pdf_prefix, horizon_suffix, "_")
}
if (outcome != "interactions") {
  run_name <- paste0(run_name, "_", outcome)
  pdf_prefix <- paste0(pdf_prefix, outcome, "_")
}
if (split_independent) {
  run_name <- paste0(run_name, "_split_independent")
  pdf_prefix <- paste0(pdf_prefix, "split_independent_")
}
output_dir <- file.path(repository_root, "output", "fect_youtube", run_name)
pdf_dir <- file.path(repository_root, "output", "pdf")
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(pdf_dir, recursive = TRUE, showWarnings = FALSE)
panel_path <- file.path(repository_root, "output", "fect_youtube", "youtube_questions_attendance_daily.parquet")
panel <- read_parquet(panel_path) |> arrange(youtube_entity_id, date)
if (split_independent) {
  stopifnot(all(panel$ideology_4t %in% c("aligned", "opp", "unclear")),
            !anyDuplicated(distinct(panel, youtube_entity_id, ideology_4t)$youtube_entity_id))
  panel <- panel |> mutate(alignment = recode(ideology_4t,
    aligned = "Aligned", opp = "Opp.", unclear = "Independent"))
  write_csv(panel |> group_by(alignment) |> summarise(
    n_outlets = n_distinct(youtube_entity_id), n_outlet_days = n(),
    n_question_days = sum(treatment_day),
    n_question_outlets = n_distinct(youtube_entity_id[treatment_day == 1L]),
    .groups = "drop"), file.path(output_dir, "group_support.csv"))
}
if (outcome == "views") {
  source(file.path(repository_root, "project_paths.R"))
  source_metrics <- read_parquet(
    media_path("data", "06-outcomes", "deduplicated_source_panels", "youtube_entity_daily_panel.parquet"),
    col_select = c("entity_id", "date", "youtube_views", "youtube_likes", "youtube_comments")
  ) |> transmute(youtube_entity_id = entity_id, date, youtube_views,
                 source_likes = youtube_likes, source_comments = youtube_comments,
                 source_row_present = TRUE)
  panel <- left_join(panel, source_metrics, by = c("youtube_entity_id", "date"),
                     relationship = "one-to-one")
  # Verify that views use the same entities/dates and source snapshot as the
  # saved likes/comments panel. No re-expansion to duplicated metadata outlets.
  stopifnot(all(panel$source_row_present %in% TRUE),
            all(coalesce(panel$source_likes, 0) == coalesce(panel$youtube_likes, 0)),
            all(coalesce(panel$source_comments, 0) == coalesce(panel$youtube_comments, 0)))
}
if (outcome == "mean_interactions") {
  source(file.path(repository_root, "project_paths.R"))
  video_counts <- read_parquet(
    media_path("data", "06-outcomes", "deduplicated_source_panels", "youtube_entity_daily_panel.parquet"),
    col_select = c("entity_id", "date", "youtube_n_videos")
  ) |> transmute(youtube_entity_id = entity_id, date, youtube_n_videos)
  panel <- left_join(panel, video_counts, by = c("youtube_entity_id", "date"), relationship = "one-to-one")
  panel$youtube_n_videos <- coalesce(panel$youtube_n_videos, 0)
  stopifnot(all(panel$youtube_n_videos >= 0),
            !any(panel$youtube_n_videos == 0 & panel$youtube_interactions > 0))
  panel$raw_outcome <- ifelse(panel$youtube_n_videos > 0,
                            panel$youtube_interactions / pmax(panel$youtube_n_videos, 1), 0)
} else {
  panel$raw_outcome <- switch(outcome,
    interactions = panel$youtube_interactions,
    likes = coalesce(panel$youtube_likes, 0),
    comments = coalesce(panel$youtube_comments, 0),
    views = coalesce(panel$youtube_views, 0))
}
stopifnot(all(is.finite(panel$raw_outcome)), all(panel$raw_outcome >= 0))
stopifnot(
  !anyDuplicated(panel[c("youtube_entity_id", "date")]),
  all(panel$treatment_day == as.integer(panel$questions > 0)),
  all(panel$attendance_dummy %in% 0:1),
  all(panel$attendance_dummy[panel$treatment_day == 1] == 1),
  all(is.finite(panel$youtube_interactions)),
  all(panel$youtube_interactions >= 0),
  all(panel$sample_day == as.integer(panel$date - min(panel$date)) + 1L)
)
daily_complete <- panel |> group_by(youtube_entity_id) |>
  summarise(complete = all(diff(as.integer(date)) == 1L), .groups = "drop")
stopifnot(all(daily_complete$complete))
expected_treatment <- panel |> group_by(youtube_entity_id) |>
  mutate(expected = as.integer(treatment_day == 1L | lag(treatment_day, default = 0L) == 1L)) |>
  ungroup()
stopifnot(all(panel$treatment_plus_1 == expected_treatment$expected))
cuts <- if (winsorize_outcome) quantile(panel$raw_outcome, c(.01, .99)) else c(NA_real_, NA_real_)
y <- panel$raw_outcome
if (winsorize_outcome) y <- pmin(pmax(y, cuts[[1]]), cuts[[2]])
if (!winsorize_outcome) stopifnot(identical(y, panel$raw_outcome))

if (transformation == "chen_roth_x0") {
  # Chen & Roth (2024), Sections 4.2 and 5.2, Table 7, x=0.
  # Their example is repeated-cross-section DiD. Here we apply its outcome
  # calibration to a panel using one pooled minimum over positive outlet-days.
  # log(y) for y>0, log(y_min) for y=0; subtracting log(y_min) would produce
  # their normalized version and changes only an additive constant in FEct.
  # Use the same fixed scale for every group and bootstrap draw.
  positive_min <- min(y[y > 0])
  stopifnot(is.finite(positive_min), positive_min > 0)
  panel$analysis_outcome <- log(ifelse(y > 0, y, positive_min))
  normalized <- log(ifelse(y > 0, y / positive_min, 1))
  stopifnot(all(is.finite(panel$analysis_outcome)),
            max(abs(panel$analysis_outcome - normalized - log(positive_min))) < 1e-10)
  transform_label <- "Chen-Roth x=0; pooled minimum-positive replacement before log"
  plot_subtitle <- "Interactions | winsorized Chen-Roth x=0 | 50 bootstraps"
  if (!winsorize_outcome) plot_subtitle <- "Interactions | log, no winsorization | 50 bootstraps"
  plot_y_label <- "Effect on calibrated log(interactions)"
  write_csv(tibble(transformation = transform_label, pooled_positive_min = positive_min,
                   value_at_zero = log(positive_min), zero_share = mean(y == 0),
                   winsorized = winsorize_outcome, maximum_before_log = max(y),
                   observations_modified = sum(y != panel$raw_outcome), outcome = outcome_label,
                   start = min(panel$date), end = max(panel$date)),
            file.path(output_dir, "transformation_details.csv"))
} else if (transformation == "log1p") {
  panel$analysis_outcome <- log1p(y)
  stopifnot(all(is.finite(panel$analysis_outcome)))
  positive_min <- NA_real_
  transform_label <- if (winsorize_outcome) "log1p after pooled p1/p99 winsorization" else "log1p of original outcome"
  plot_subtitle <- paste(outcome_label, transform_label, sep = " | ")
  plot_y_label <- "Effect on log(1 + outcome)"
  write_csv(tibble(transformation = transform_label, pooled_positive_min = positive_min,
                   value_at_zero = 0, zero_share = mean(y == 0), winsorized = winsorize_outcome,
                   winsor_p1 = cuts[[1]], winsor_p99 = cuts[[2]], maximum_before_log = max(y),
                   observations_modified = sum(y != panel$raw_outcome), outcome = outcome_label,
                   start = min(panel$date), end = max(panel$date)),
            file.path(output_dir, "transformation_details.csv"))
} else {
  panel$analysis_outcome <- asinh(y)
  positive_min <- NA_real_
  transform_label <- if (winsorize_outcome) "asinh of pooled p1/p99 winsorized interactions" else "asinh of original interactions"
  plot_subtitle <- if (winsorize_outcome) "Daily interactions | winsorized asinh | 50 bootstraps" else "Interactions | asinh, no winsorization | 50 bootstraps"
  plot_y_label <- "Effect on asinh(interactions)"
}
if (outcome != "interactions") {
  plot_subtitle <- paste0(outcome_label, " | ", if (winsorize_outcome) "winsorized" else "uncapped", " | 50 bootstraps")
  plot_y_label <- switch(transformation, chen_roth_x0 = "Effect on calibrated log outcome",
                         log1p = "Effect on log(1 + outcome)", asinh = "Effect on asinh outcome")
}
plot_subtitle <- gsub("50 bootstraps", paste(n_boots, "bootstraps"), plot_subtitle, fixed = TRUE)

groups <- c("Pooled", "Aligned", "Opp. + Independent")
slugs <- c("Pooled" = "pooled", "Aligned" = "aligned", "Opp. + Independent" = "opp_independent")
colors <- c("Pooled" = "#666666", "Aligned" = "#355C7D", "Opp. + Independent" = "#A65D45")
if (split_independent) {
  groups <- c("Pooled", "Aligned", "Opp.", "Independent")
  slugs <- c("Pooled" = "pooled", "Aligned" = "aligned", "Opp." = "opp", "Independent" = "independent")
  colors <- c("Pooled" = "#666666", "Aligned" = "#355C7D", "Opp." = "#A65D45", "Independent" = "#58735C")
}

# Confirm the installed package's indexing and treatment-reentry behavior.
get_term <- get("get_term", asNamespace("fect"))
example_D <- c(0, 0, 0, 0, 1, 0, 0, 1, 0)
example_on <- get_term(example_D, rep(1, length(example_D)), type = "on")
example_off <- get_term(example_D, rep(1, length(example_D)), type = "off")
stopifnot(example_on[5] == 1, example_on[4] == 0,
          example_off[6] == 1, example_off[7] == 2,
          example_off[8] == 0, example_off[9] == 1)
# Verify both treated onset periods are retained for the two-day definition.
two_day_D <- c(0, 0, 0, 0, 1, 1, 0, 0, 0, 0)
two_day_on <- get_term(two_day_D, rep(1, length(two_day_D)), type = "on")
two_day_off <- get_term(two_day_D, rep(1, length(two_day_D)), type = "off")
stopifnot(all(two_day_on[5:6] - 1L == 0:1), all(two_day_off[7:10] == 1:4))

format_event <- function(tab, kind, group) {
  tab <- as.data.frame(tab)
  raw <- as.integer(rownames(tab))
  tibble(
    sample_group = group, event_type = kind, raw_fect_period = raw,
    event_day = if (kind == "Onset") raw - 1L else raw,
    estimate = tab[[1]], standard_error = tab[[2]],
    conf95_low = tab[[3]], conf95_high = tab[[4]], p_value = tab[[5]],
    n_outlet_days = tab[[6]],
    conf90_low = estimate - qnorm(.95) * standard_error,
    conf90_high = estimate + qnorm(.95) * standard_error,
    bootstrap_replications = n_boots,
    counterfactual_fit = if (kind == "Onset") "all untreated cells" else paste("exclude exit days 1 through", post_days)
  ) |>
    filter(if (kind == "Onset") between(event_day, -pre_days, onset_last_day) else between(event_day, 1L, post_days))
}

all_events <- list()
averages <- list()
support <- list()
test_stat <- function(fit, name) {
  value <- fit$test.out[[name]]
  if (is.null(value) || length(value) != 1L) NA_real_ else as.numeric(value)
}
if (!plot_only) for (group in groups) {
  data <- panel
  if (group != "Pooled") data <- filter(data, alignment == group)
  data <- data |>
    transmute(youtube_entity_id = as.character(youtube_entity_id), sample_day,
              Y = analysis_outcome, D = .data[[treatment_column]], X = attendance_dummy) |>
    as.data.frame()
  for (kind in c("Onset", "Carryover")) {
    message(format(Sys.time(), "%H:%M:%S"), " | ", group, " | ", kind, " | ", n_boots, " bootstraps")
    fit_args <- list(
      formula = Y ~ D + X, data = data,
      index = c("youtube_entity_id", "sample_day"), method = "fe", force = "two-way",
      se = TRUE, vartype = "bootstrap", nboots = n_boots, parallel = FALSE,
      seed = 20261006, min.T0 = 5, na.rm = TRUE
    )
    # Hold out every carryover day shown, not only the last day of the window.
    if (kind == "Carryover") {
      fit_args$carryoverTest <- TRUE
      fit_args$carryover.period <- c(1L, post_days)
    }
    fit_path <- file.path(output_dir, paste0(slugs[[group]], "_", tolower(kind), "_fit.rds"))
    if (resume_fits && file.exists(fit_path)) {
      fit <- readRDS(fit_path)
      stopifnot(length(fit$att.avg.boot) == n_boots,
                identical(as.numeric(fit$call$nboots), as.numeric(n_boots)))
      message("Reusing completed fit: ", fit_path)
    } else {
      fit <- do.call(fect, fit_args)
      saveRDS(fit, fit_path)
    }
    stopifnot(all(diff(as.numeric(fit$rawtime)) == 1))
    tab <- if (kind == "Onset") fit$est.att else fit$est.att.off
    events <- format_event(tab, kind, group) |>
      mutate(transformation = transform_label, treatment = treatment_label, winsorized = winsorize_outcome, outcome = outcome_label)
    expected_days <- if (kind == "Onset") seq.int(-pre_days, onset_last_day) else seq_len(post_days)
    stopifnot(setequal(events$event_day, expected_days), all(is.finite(events$estimate)))
    all_events[[paste(group, kind)]] <- events
    avg <- if (kind == "Onset") fit$est.avg else fit$est.carryover
    avg <- as.numeric(avg[1, ])
    averages[[paste(group, kind)]] <- tibble(
      sample_group = group, estimand = if (kind == "Onset") paste(treatment_label, "ATT") else paste0("Mean carryover days 1-", post_days),
      estimate = avg[1], standard_error = avg[2], conf95_low = avg[3],
      conf95_high = avg[4], p_value = avg[5], bootstrap_replications = n_boots,
      transformation = transform_label, treatment = treatment_label, winsorized = winsorize_outcome, outcome = outcome_label
    )
    support[[paste(group, kind)]] <- tibble(
      sample_group = group, model = kind, n_outlet_days = nrow(data),
      n_outlets = n_distinct(data$youtube_entity_id), n_treated_days = sum(data$D),
      n_treated_outlets = n_distinct(data$youtube_entity_id[data$D == 1]),
      fect_n_outlets = fit$N, fect_n_days = fit$T, fect_n_treated_outlets = fit$Ntr,
      fect_n_never_treated_outlets = fit$Nco, rmse = fit$rmse,
      att_bootstrap_valid = sum(is.finite(fit$att.avg.boot)),
      bootstrap_replications = n_boots,
      attendance_estimate = fit$est.beta[1, 1], attendance_se = fit$est.beta[1, 2],
      attendance_p_value = fit$est.beta[1, 5],
      f_statistic = test_stat(fit, "f.stat"), f_p_value = test_stat(fit, "f.p"),
      equivalence_p_value = test_stat(fit, "tost.equiv.p"),
      equivalence_threshold = test_stat(fit, "tost.threshold"),
      carryover_test_p_value = test_stat(fit, "carryover.p"),
      carryover_equivalence_p_value = test_stat(fit, "carryover.equiv.p"),
      diagnostic_pre_day_min = if (length(fit$pre.periods)) min(fit$pre.periods) - 1L else NA_real_,
      diagnostic_pre_day_max = if (length(fit$pre.periods)) max(fit$pre.periods) - 1L else NA_real_,
      start = min(panel$date), end = max(panel$date), winsor_p1 = cuts[[1]], winsor_p99 = cuts[[2]],
      fect_version = as.character(packageVersion("fect")),
      transformation = transform_label, pooled_positive_min = positive_min, treatment = treatment_label,
      pre_days = pre_days, post_days = post_days, winsorized = winsorize_outcome, outcome = outcome_label
    )
    write_csv(bind_rows(all_events), file.path(output_dir, "event_estimates.csv"))
    write_csv(bind_rows(averages), file.path(output_dir, "average_estimates.csv"))
    write_csv(bind_rows(support), file.path(output_dir, "model_diagnostics.csv"))
  }
}

events <- if (plot_only) read_csv(file.path(output_dir, "event_estimates.csv"), show_col_types = FALSE) else bind_rows(all_events)
if (!skip_plots) for (group in groups) {
  for (kind in c("Onset", "Carryover")) {
    plot_data <- events |> filter(sample_group == group, event_type == kind)
    axis_breaks <- if (nrow(plot_data) <= 8L) plot_data$event_day else {
      if (kind == "Onset") sort(unique(c(seq(-pre_days, -2L, by = 2L), -1L, 0L, onset_last_day))) else {
        sort(unique(c(1L, seq(2L, post_days, by = 2L), post_days)))
      }
    }
    p <- ggplot(plot_data, aes(event_day, estimate)) +
      geom_hline(yintercept = 0, color = "#555555", linewidth = .35) +
      geom_errorbar(aes(ymin = conf95_low, ymax = conf95_high), width = 0,
                    linewidth = .4, color = colors[[group]]) +
      geom_errorbar(aes(ymin = conf90_low, ymax = conf90_high), width = 0,
                    linewidth = 1, color = colors[[group]]) +
      geom_line(linewidth = .45, color = colors[[group]]) +
      geom_point(size = 1.7, color = colors[[group]]) +
      scale_x_continuous(breaks = axis_breaks) +
      scale_y_continuous(breaks = seq(-1, 1, by = 0.5), expand = expansion(mult = 0)) +
      coord_cartesian(ylim = c(-1, 1)) +
      labs(
        title = paste0(group, ": ", tolower(kind)),
        subtitle = plot_subtitle,
        x = if (kind == "Onset") "Days relative to first question day" else "Days after treatment ends",
        y = plot_y_label,
        caption = if (kind == "Onset") {
          if (treatment == "plus1") {
            "Days 0 and 1 treated; negative days are pre-treatment fit.\nThick 90% and thin 95% pointwise intervals."
          } else {
            "Day 0 = first question day; negative days are pre-treatment fit.\nThick 90% and thin 95% pointwise intervals."
          }
        } else {
          if (treatment == "plus1") {
            paste0("Exit day 1 = 2 days after last question; days 1-", post_days, " held out.\nThick 90% and thin 95% pointwise intervals.")
          } else {
            paste0("Days 1-", post_days, " held out; follow-up ends at the next question.\nThick 90% and thin 95% pointwise intervals.")
          }
        }
      ) +
      theme_minimal(base_size = 8) +
      theme(plot.title = element_text(face = "bold", size = 10),
            plot.subtitle = element_text(size = 7), plot.caption = element_text(size = 6, hjust = 0),
            panel.grid.minor = element_blank(), plot.margin = margin(8, 8, 8, 8))
    if (kind == "Onset") p <- p + geom_vline(xintercept = 0, linetype = "dashed", linewidth = .3)
    path <- file.path(pdf_dir, paste0(pdf_prefix, tolower(kind), "_", slugs[[group]], ".pdf"))
    ggsave(path, p, width = 4, height = 4, units = "in")
    message("Saved ", path)
  }
}

if (!plot_only) capture.output(sessionInfo(), file = file.path(output_dir, "session_info.txt"))

# FEct estimates of temporary question exposure on weekly YouTube outcomes.
rm(list = ls())

if (requireNamespace("rstudioapi", quietly = TRUE) && rstudioapi::isAvailable()) {
  setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
} else if (dir.exists(file.path(getwd(), "code", "07-final_panel"))) {
  setwd(file.path(getwd(), "code", "07-final_panel"))
}

library(tidyverse)
library(arrow)
library(fect)

repository_root <- normalizePath(file.path(getwd(), "../.."), mustWork = TRUE)
output_dir <- file.path(repository_root, "output", "fect_youtube")
panel_path <- file.path(output_dir, "youtube_questions_attendance_weekly.parquet")
results_path <- file.path(output_dir, "fect_att_results.csv")
event_path <- file.path(output_dir, "fect_event_studies.csv")

randomization_week <- as.Date("2022-04-18")
periods <- tribble(
  ~sample, ~start, ~end,
  "full_2018_2024", as.Date("2018-01-01"), as.Date("2024-12-30"),
  "post_randomization", randomization_week, as.Date("2024-12-30"),
  "randomization_18m", as.Date("2020-10-19"), as.Date("2023-10-16"),
  "post_randomization_18m", randomization_week, as.Date("2023-10-16")
)

treatments <- c(
  question_week_only = "treatment_1week",
  question_week_plus_1 = "treatment_2weeks",
  question_week_plus_2 = "treatment_3weeks"
)
outcomes <- c(
  videos = "log_youtube_videos",
  views = "log_youtube_views",
  interactions = "log_youtube_interactions"
)
controls <- c(
  contemporaneous_attendance = "log_attendance",
  lagged_attendance = "lag_log_attendance"
)

panel <- read_parquet(panel_path) |>
  mutate(youtube_entity_id = as.character(youtube_entity_id)) |>
  as.data.frame()

model_grid <- crossing(
  period_row = seq_len(nrow(periods)),
  treatment_name = names(treatments),
  outcome_name = names(outcomes),
  control_name = names(controls)
)

estimate_one <- function(period_row, treatment_name, outcome_name, control_name) {
  period <- periods[period_row, ]
  treatment <- unname(treatments[[treatment_name]])
  outcome <- unname(outcomes[[outcome_name]])
  control <- unname(controls[[control_name]])

  data <- panel |>
    filter(week >= period$start, week <= period$end) |>
    mutate(sample_week = match(week, sort(unique(week)))) |>
    select(
      youtube_entity_id, sample_week, week,
      all_of(c(outcome, treatment, control))
    ) |>
    rename(Y = all_of(outcome), D = all_of(treatment), X = all_of(control)) |>
    filter(!is.na(Y), !is.na(D), !is.na(X)) |>
    as.data.frame()

  if (sum(data$D) == 0L || n_distinct(data$D) < 2L) {
    stop("No treatment variation in model sample.")
  }

  bootstrap_inference <- control_name == "contemporaneous_attendance"
  fit <- fect(
    Y ~ D + X,
    data = data,
    index = c("youtube_entity_id", "sample_week"),
    method = "fe",
    force = "two-way",
    se = bootstrap_inference,
    vartype = "bootstrap",
    nboots = 100,
    parallel = FALSE,
    seed = 20260928 + period_row,
    min.T0 = 5,
    na.rm = TRUE
  )

  estimate <- if (bootstrap_inference) {
    as.numeric(fit$est.avg[1, ])
  } else {
    c(fit$att.avg, NA_real_, NA_real_, NA_real_, NA_real_)
  }
  result <- tibble(
    sample = period$sample,
    start = period$start,
    end = period$end,
    treatment = treatment_name,
    treatment_weeks = match(treatment_name, names(treatments)),
    outcome = outcome_name,
    outcome_transform = "log1p",
    attendance_control = control_name,
    bootstrap_replications = if_else(bootstrap_inference, 100L, 0L),
    att = estimate[1],
    standard_error = estimate[2],
    conf_low = estimate[3],
    conf_high = estimate[4],
    p_value = estimate[5],
    percent_effect = 100 * (exp(estimate[1]) - 1),
    n_rows_input = nrow(data),
    n_entities_input = n_distinct(data$youtube_entity_id),
    n_treated_cells_input = sum(data$D),
    n_treated_units_fit = fit$Ntr,
    n_control_units_fit = fit$Nco,
    outcome_control_coefficient = as.numeric(fit$beta[1])
  )

  event <- tibble(
    event_time = fit$time,
    att = fit$att,
    treated_cells = fit$count
  ) |>
    mutate(
      sample = period$sample,
      treatment = treatment_name,
      outcome = outcome_name,
      attendance_control = control_name,
      .before = 1
    )

  list(result = result, event = event)
}

all_results <- list()
all_events <- list()

for (row in seq_len(nrow(model_grid))) {
  specification <- model_grid[row, ]
  message(
    sprintf(
      "[%d/%d] %s | %s | %s | %s",
      row, nrow(model_grid),
      periods$sample[specification$period_row],
      specification$treatment_name,
      specification$outcome_name,
      specification$control_name
    )
  )

  estimate <- tryCatch(
    estimate_one(
      specification$period_row,
      specification$treatment_name,
      specification$outcome_name,
      specification$control_name
    ),
    error = function(error) {
      warning(conditionMessage(error), call. = FALSE)
      list(
        result = tibble(
          sample = periods$sample[specification$period_row],
          treatment = specification$treatment_name,
          outcome = specification$outcome_name,
          attendance_control = specification$control_name,
          error = conditionMessage(error)
        ),
        event = tibble()
      )
    }
  )

  all_results[[row]] <- estimate$result
  all_events[[row]] <- estimate$event

  write_csv(bind_rows(all_results), results_path)
  write_csv(bind_rows(all_events), event_path)
}

cat("Results saved to:", results_path, "\n")
cat("Event-study estimates saved to:", event_path, "\n")

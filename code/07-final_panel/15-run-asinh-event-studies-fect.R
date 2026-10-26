# FEct onset and carryover event studies for the winsorized asinh specification.
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
cuts_path <- file.path(output_dir, "post_randomization_winsorization_cutoffs.csv")
results_path <- file.path(output_dir, "fect_asinh_event_studies_1000.csv")
onset_pdf <- file.path(repository_root, "output", "pdf", "fect_asinh_event_study_onset.pdf")
carryover_pdf <- file.path(repository_root, "output", "pdf", "fect_asinh_event_study_carryover.pdf")

outcomes <- c(
  "Videos" = "youtube_videos",
  "Views" = "youtube_views",
  "Interactions" = "youtube_interactions",
  "Mean interactions per video" = "youtube_interactions_per_video"
)
groups <- c("Pooled", "Aligned", "Opp. + Independent")
cutoffs <- read_csv(cuts_path, show_col_types = FALSE)

panel <- read_parquet(panel_path) |>
  filter(week >= as.Date("2022-04-18"), week <= as.Date("2024-12-30")) |>
  mutate(
    youtube_entity_id = as.character(youtube_entity_id),
    sample_week = match(week, sort(unique(week))),
    alignment = if_else(
      ideology_4t == "aligned",
      "Aligned",
      "Opp. + Independent"
    ),
    youtube_interactions_per_video = if_else(
      youtube_videos > 0,
      youtube_interactions / youtube_videos,
      0
    )
  ) |>
  as.data.frame()

for (row in seq_len(nrow(cutoffs))) {
  variable <- cutoffs$variable[row]
  winsorized <- pmin(
    pmax(panel[[variable]], cutoffs$lower_cutoff[row]),
    cutoffs$upper_cutoff[row]
  )
  panel[[paste0(variable, "_asinh")]] <- asinh(winsorized)
}

model_grid <- crossing(sample_group = groups, outcome_label = names(outcomes))

format_event <- function(table, event_type, sample_group, outcome_label) {
  data <- as.data.frame(table)
  tibble(
    sample_group,
    outcome = outcome_label,
    event_type,
    event_time = as.integer(rownames(data)),
    att = data[[1]],
    standard_error = data[[2]],
    conf95_low = data[[3]],
    conf95_high = data[[4]],
    p_value = data[[5]],
    treated_cells = data[[6]],
    conf90_low = att - qnorm(0.95) * standard_error,
    conf90_high = att + qnorm(0.95) * standard_error
  )
}

estimate_one <- function(sample_group, outcome_label) {
  outcome <- paste0(unname(outcomes[[outcome_label]]), "_asinh")
  data <- panel
  if (sample_group != "Pooled") {
    data <- data |> filter(alignment == sample_group)
  }
  data <- data |>
    select(
      youtube_entity_id, sample_week,
      Y = all_of(outcome),
      D = treatment_2weeks,
      X = log_attendance
    ) |>
    filter(!is.na(Y), !is.na(D), !is.na(X)) |>
    as.data.frame()

  fit <- fect(
    Y ~ D + X,
    data = data,
    index = c("youtube_entity_id", "sample_week"),
    method = "fe",
    force = "two-way",
    se = TRUE,
    vartype = "bootstrap",
    nboots = 1000,
    parallel = FALSE,
    seed = 20260928,
    min.T0 = 5,
    na.rm = TRUE,
    carryoverTest = TRUE,
    carryover.period = 6
  )

  onset <- format_event(
    fit$est.att,
    "Treatment onset",
    sample_group,
    outcome_label
  ) |>
    filter(between(event_time, -6L, 1L))

  carryover <- format_event(
    fit$est.att.off,
    "After treatment switches off",
    sample_group,
    outcome_label
  ) |>
    filter(between(event_time, 0L, 6L))

  bind_rows(onset, carryover) |>
    mutate(
      n_entities = n_distinct(data$youtube_entity_id),
      n_treated_cells = sum(data$D),
      bootstrap_replications = 1000L,
      winsorization = "pooled p1/p99",
      transformation = "asinh(winsorized outcome)"
    )
}

results <- vector("list", nrow(model_grid))
for (row in seq_len(nrow(model_grid))) {
  specification <- model_grid[row, ]
  message(
    sprintf(
      "[%d/%d] %s | %s",
      row, nrow(model_grid),
      specification$sample_group,
      specification$outcome_label
    )
  )
  results[[row]] <- estimate_one(
    specification$sample_group,
    specification$outcome_label
  )
  write_csv(bind_rows(results), results_path)
}
results <- bind_rows(results)

plot_event <- function(data, title, subtitle, x_label, path) {
  data <- data |>
    mutate(
      sample_group = factor(sample_group, levels = groups),
      outcome = factor(outcome, levels = names(outcomes))
    )

  dodge <- position_dodge(width = 0.25)
  plot <- ggplot(
    data,
    aes(event_time, att, color = sample_group, group = sample_group)
  ) +
    geom_hline(yintercept = 0, color = "#555555", linewidth = 0.3) +
    geom_vline(xintercept = 0, linetype = "dashed", color = "#555555", linewidth = 0.3) +
    geom_errorbar(
      aes(ymin = conf95_low, ymax = conf95_high),
      position = dodge,
      width = 0,
      linewidth = 0.3
    ) +
    geom_errorbar(
      aes(ymin = conf90_low, ymax = conf90_high),
      position = dodge,
      width = 0,
      linewidth = 0.8
    ) +
    geom_line(position = dodge, linewidth = 0.4) +
    geom_point(position = dodge, size = 1.1) +
    facet_wrap(vars(outcome), ncol = 2, scales = "free_y") +
    scale_color_manual(
      values = c(
        "Pooled" = "#666666",
        "Aligned" = "#355C7D",
        "Opp. + Independent" = "#A65D45"
      )
    ) +
    scale_x_continuous(breaks = sort(unique(data$event_time))) +
    labs(
      title = title,
      subtitle = subtitle,
      x = x_label,
      y = "FEct ATT",
      color = NULL
    ) +
    theme_minimal(base_size = 7) +
    theme(
      plot.title = element_text(face = "bold", size = 8.5),
      plot.subtitle = element_text(size = 6.2),
      strip.text = element_text(face = "bold", size = 6.3),
      axis.text = element_text(size = 5.2),
      axis.title = element_text(size = 6.2),
      legend.position = "bottom",
      legend.text = element_text(size = 6),
      panel.grid.minor = element_blank(),
      plot.margin = margin(4, 4, 3, 4)
    )

  ggsave(path, plot, width = 4, height = 4, units = "in", device = "pdf")
}

plot_event(
  filter(results, event_type == "Treatment onset"),
  "Event study around question exposure",
  "asinh outcomes; thick 90% and thin 95% intervals",
  "Weeks relative to treatment onset",
  onset_pdf
)
plot_event(
  filter(results, event_type == "After treatment switches off"),
  "Carryover after question exposure",
  "Week 0 is the first untreated week after the temporary spell",
  "Weeks since treatment switched off",
  carryover_pdf
)

cat("Results saved to:", results_path, "\n")
cat("Onset PDF saved to:", onset_pdf, "\n")
cat("Carryover PDF saved to:", carryover_pdf, "\n")

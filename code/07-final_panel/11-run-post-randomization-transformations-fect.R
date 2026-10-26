# Post-randomization FEct estimates using winsorized levels and zero-safe transforms.
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
results_path <- file.path(output_dir, "fect_post_randomization_transformations.csv")
cuts_path <- file.path(output_dir, "post_randomization_winsorization_cutoffs.csv")
pdf_path <- file.path(repository_root, "output", "pdf", "fect_post_randomization_transformations.pdf")

treatments <- c(
  "Question week" = "treatment_1week",
  "+1 week" = "treatment_2weeks",
  "+2 weeks" = "treatment_3weeks"
)
outcomes <- c(
  "Videos" = "youtube_videos",
  "Views" = "youtube_views",
  "Interactions" = "youtube_interactions",
  "Mean interactions per video" = "youtube_interactions_per_video"
)

winsorize <- function(x, lower, upper) pmin(pmax(x, lower), upper)
CHEN_ROTH_X <- 4
chen_roth <- function(x, zero_value = -CHEN_ROTH_X) {
  if_else(x == 0, zero_value, log(x))
}

panel <- read_parquet(panel_path) |>
  filter(week >= as.Date("2022-04-18"), week <= as.Date("2024-12-30")) |>
  mutate(
    youtube_entity_id = as.character(youtube_entity_id),
    sample_week = match(week, sort(unique(week))),
    youtube_interactions_per_video = if_else(
      youtube_videos > 0,
      youtube_interactions / youtube_videos,
      0
    )
  ) |>
  as.data.frame()

cutoffs <- imap_dfr(outcomes, function(variable, label) {
  values <- panel[[variable]]
  tibble(
    outcome = label,
    variable = variable,
    lower_percentile = 0.01,
    upper_percentile = 0.99,
    lower_cutoff = as.numeric(quantile(values, 0.01, na.rm = TRUE, type = 7)),
    upper_cutoff = as.numeric(quantile(values, 0.99, na.rm = TRUE, type = 7)),
    zero_share = mean(values == 0, na.rm = TRUE)
  )
})
write_csv(cutoffs, cuts_path)

for (row in seq_len(nrow(cutoffs))) {
  variable <- cutoffs$variable[row]
  winsorized <- winsorize(
    panel[[variable]],
    cutoffs$lower_cutoff[row],
    cutoffs$upper_cutoff[row]
  )
  panel[[paste0(variable, "_winsorized")]] <- winsorized
  panel[[paste0(variable, "_asinh")]] <- asinh(winsorized)
  panel[[paste0(variable, "_chen_roth")]] <- chen_roth(winsorized)
}

model_grid <- crossing(
  treatment_label = names(treatments),
  outcome_label = names(outcomes),
  transformation = c("winsorized_level", "asinh", "chen_roth")
)

estimate_one <- function(treatment_label, outcome_label, transformation) {
  treatment <- unname(treatments[[treatment_label]])
  outcome_base <- unname(outcomes[[outcome_label]])
  outcome <- switch(
    transformation,
    winsorized_level = paste0(outcome_base, "_winsorized"),
    asinh = paste0(outcome_base, "_asinh"),
    chen_roth = paste0(outcome_base, "_chen_roth")
  )

  data <- panel |>
    select(
      youtube_entity_id, sample_week,
      Y = all_of(outcome),
      D = all_of(treatment),
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
    nboots = 100,
    parallel = FALSE,
    seed = 20260928,
    min.T0 = 5,
    na.rm = TRUE
  )

  estimate <- as.numeric(fit$est.avg[1, ])
  tibble(
    sample = "post_randomization",
    start = as.Date("2022-04-18"),
    end = as.Date("2024-12-30"),
    treatment = treatment_label,
    treatment_weeks = match(treatment_label, names(treatments)),
    outcome = outcome_label,
    transformation = transformation,
    att = estimate[1],
    standard_error = estimate[2],
    conf_low = estimate[3],
    conf_high = estimate[4],
    p_value = estimate[5],
    n_rows = nrow(data),
    n_entities = n_distinct(data$youtube_entity_id),
    n_treated_cells = sum(data$D),
    bootstrap_replications = 100L,
    chen_roth_zero_value = if_else(
      transformation == "chen_roth",
      -CHEN_ROTH_X,
      NA_real_
    )
  )
}

results <- pmap_dfr(model_grid, function(treatment_label, outcome_label, transformation) {
  message(treatment_label, " | ", outcome_label, " | ", transformation)
  estimate_one(treatment_label, outcome_label, transformation)
})
write_csv(results, results_path)

plot_data <- results |>
  mutate(
    treatment = factor(treatment, levels = names(treatments)),
    transformation = factor(
      transformation,
      levels = c("winsorized_level", "asinh", "chen_roth"),
      labels = c("Winsorized level", "asinh", "Chen-Roth")
    ),
    outcome = factor(outcome, levels = names(outcomes))
  )

plot <- ggplot(plot_data, aes(treatment, att)) +
  geom_hline(yintercept = 0, color = "#555555", linewidth = 0.3) +
  geom_errorbar(
    aes(ymin = conf_low, ymax = conf_high),
    width = 0.12,
    linewidth = 0.4,
    color = "#355C7D"
  ) +
  geom_point(size = 1.4, color = "#355C7D") +
  facet_grid(rows = vars(outcome), cols = vars(transformation), scales = "free_y") +
  labs(
    title = "Questions and YouTube outcomes after randomization",
    subtitle = "FEct ATT and 95% bootstrap intervals; outcomes winsorized at p1/p99",
    x = NULL,
    y = "ATT in transformed outcome units"
  ) +
  theme_minimal(base_size = 7) +
  theme(
    plot.title = element_text(face = "bold", size = 8.3),
    plot.subtitle = element_text(size = 6.1),
    strip.text = element_text(face = "bold", size = 5.8),
    axis.text = element_text(size = 5.1),
    axis.text.x = element_text(angle = 25, hjust = 1),
    axis.title.y = element_text(size = 6),
    panel.grid.minor = element_blank(),
    plot.margin = margin(4, 4, 3, 4)
  )

ggsave(pdf_path, plot, width = 4, height = 4, units = "in", device = "pdf")
print(cutoffs)
print(results)
cat("Results saved to:", results_path, "\n")
cat("PDF saved to:", pdf_path, "\n")

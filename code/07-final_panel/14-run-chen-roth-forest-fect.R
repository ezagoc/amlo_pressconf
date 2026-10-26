# Post-randomization FEct forest plot: winsorized asinh outcomes.
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
results_path <- file.path(output_dir, "fect_asinh_1000_bootstrap.csv")
pdf_path <- file.path(
  repository_root, "output", "pdf",
  "fect_asinh_1000_bootstrap_forest.pdf"
)

treatments <- c(
  "Question week + 1" = "treatment_2weeks"
)
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

# Pooled cutoffs are applied before the asinh transformation in every group.
for (row in seq_len(nrow(cutoffs))) {
  variable <- cutoffs$variable[row]
  winsorized <- pmin(
    pmax(panel[[variable]], cutoffs$lower_cutoff[row]),
    cutoffs$upper_cutoff[row]
  )
  panel[[paste0(variable, "_asinh")]] <- asinh(winsorized)
}

model_grid <- crossing(
  sample_group = groups,
  treatment_label = names(treatments),
  outcome_label = names(outcomes)
)

estimate_one <- function(sample_group, treatment_label, outcome_label) {
  treatment <- unname(treatments[[treatment_label]])
  outcome <- paste0(unname(outcomes[[outcome_label]]), "_asinh")

  data <- panel
  if (sample_group != "Pooled") {
    data <- data |> filter(alignment == sample_group)
  }
  data <- data |>
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
    nboots = 1000,
    parallel = FALSE,
    seed = 20260928,
    min.T0 = 5,
    na.rm = TRUE
  )

  draws <- as.numeric(fit$att.avg.boot)
  intervals <- quantile(
    draws,
    probs = c(0.025, 0.05, 0.95, 0.975),
    na.rm = TRUE,
    names = FALSE
  )

  tibble(
    sample_group = sample_group,
    treatment = treatment_label,
    outcome = outcome_label,
    att = fit$att.avg,
    conf95_low = intervals[1],
    conf90_low = intervals[2],
    conf90_high = intervals[3],
    conf95_high = intervals[4],
    bootstrap_standard_error = sd(draws, na.rm = TRUE),
    bootstrap_p_value = 2 * min(mean(draws <= 0), mean(draws >= 0)),
    n_rows = nrow(data),
    n_entities = n_distinct(data$youtube_entity_id),
    n_treated_cells = sum(data$D),
    n_treated_units_fit = fit$Ntr,
    n_control_units_fit = fit$Nco,
    bootstrap_replications = length(draws),
    winsorization = "pooled p1/p99",
    transformation = "asinh(winsorized outcome)"
  )
}

results <- vector("list", nrow(model_grid))
for (row in seq_len(nrow(model_grid))) {
  specification <- model_grid[row, ]
  message(
    sprintf(
      "[%d/%d] %s | %s | %s",
      row, nrow(model_grid),
      specification$sample_group,
      specification$treatment_label,
      specification$outcome_label
    )
  )
  results[[row]] <- estimate_one(
    specification$sample_group,
    specification$treatment_label,
    specification$outcome_label
  )
  write_csv(bind_rows(results), results_path)
}
results <- bind_rows(results)

plot_data <- results |>
  mutate(
    sample_group = factor(sample_group, levels = groups),
    treatment = factor(treatment, levels = names(treatments)),
    outcome = factor(outcome, levels = rev(names(outcomes)))
  )

dodge <- position_dodge(width = 0.55)
plot <- ggplot(
  plot_data,
  aes(y = outcome, x = att, color = sample_group, group = sample_group)
) +
  geom_vline(xintercept = 0, color = "#555555", linewidth = 0.35) +
  geom_errorbar(
    aes(xmin = conf95_low, xmax = conf95_high),
    orientation = "y",
    position = dodge,
    width = 0,
    linewidth = 0.35
  ) +
  geom_errorbar(
    aes(xmin = conf90_low, xmax = conf90_high),
    orientation = "y",
    position = dodge,
    width = 0,
    linewidth = 1
  ) +
  geom_point(position = dodge, size = 1.6) +
  scale_color_manual(
    values = c(
      "Pooled" = "#666666",
      "Aligned" = "#355C7D",
      "Opp. + Independent" = "#A65D45"
    )
  ) +
  labs(
    title = "Question exposure and YouTube outcomes",
    subtitle = "Winsorized asinh; thick 90% and thin 95% bootstrap intervals",
    x = "FEct point estimate",
    y = NULL,
    color = NULL
  ) +
  theme_minimal(base_size = 7) +
  theme(
    plot.title = element_text(face = "bold", size = 8.5),
    plot.subtitle = element_text(size = 6.2),
    strip.text = element_text(face = "bold", size = 6.5),
    axis.text = element_text(size = 5.5),
    axis.title.x = element_text(size = 6.2),
    legend.position = "bottom",
    legend.text = element_text(size = 6),
    legend.key.width = unit(0.7, "cm"),
    panel.grid.minor = element_blank(),
    panel.grid.major.y = element_blank(),
    plot.margin = margin(4, 4, 3, 4)
  )

ggsave(pdf_path, plot, width = 4, height = 3.5, units = "in", device = "pdf")
print(results)
cat("Results saved to:", results_path, "\n")
cat("PDF saved to:", pdf_path, "\n")

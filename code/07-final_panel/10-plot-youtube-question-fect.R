# Plot primary FEct estimates with contemporaneous attendance control.
rm(list = ls())

if (requireNamespace("rstudioapi", quietly = TRUE) && rstudioapi::isAvailable()) {
  setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
} else if (dir.exists(file.path(getwd(), "code", "07-final_panel"))) {
  setwd(file.path(getwd(), "code", "07-final_panel"))
}

library(tidyverse)

repository_root <- normalizePath(file.path(getwd(), "../.."), mustWork = TRUE)
results_path <- file.path(repository_root, "output", "fect_youtube", "fect_att_results.csv")
output_path <- file.path(repository_root, "output", "pdf", "fect_youtube_question_effects.pdf")

results <- read_csv(results_path, show_col_types = FALSE) |>
  filter(attendance_control == "contemporaneous_attendance") |>
  mutate(
    period = recode(
      sample,
      full_2018_2024 = "Full: 2018-2024",
      post_randomization = "Post: Apr. 2022-Dec. 2024",
      randomization_18m = "18 months before/after",
      post_randomization_18m = "Post: Apr. 2022-Oct. 2023"
    ),
    period = factor(
      period,
      levels = c(
        "Full: 2018-2024",
        "Post: Apr. 2022-Dec. 2024",
        "18 months before/after",
        "Post: Apr. 2022-Oct. 2023"
      )
    ),
    outcome = recode(
      outcome,
      videos = "Videos",
      views = "Views",
      interactions = "Interactions"
    ),
    treatment = factor(
      treatment,
      levels = c(
        "question_week_only",
        "question_week_plus_1",
        "question_week_plus_2"
      ),
      labels = c("Question week", "+1 week", "+2 weeks")
    ),
    estimate_pct = 100 * (exp(att) - 1),
    low_pct = 100 * (exp(conf_low) - 1),
    high_pct = 100 * (exp(conf_high) - 1)
  )

write_csv(
  results |>
    select(
      period, treatment, outcome, estimate_pct, low_pct, high_pct, p_value,
      n_entities_input, n_treated_cells_input
    ),
  file.path(repository_root, "output", "fect_youtube", "fect_att_results_primary.csv")
)

plot <- ggplot(
  results,
  aes(treatment, estimate_pct, color = outcome, group = outcome)
) +
  geom_hline(yintercept = 0, color = "#555555", linewidth = 0.3) +
  geom_errorbar(
    aes(ymin = low_pct, ymax = high_pct),
    position = position_dodge(width = 0.45),
    width = 0.12,
    linewidth = 0.35
  ) +
  geom_point(position = position_dodge(width = 0.45), size = 1.4) +
  facet_wrap(vars(period), ncol = 2, scales = "free_y") +
  scale_color_manual(
    values = c(Videos = "#666666", Views = "#355C7D", Interactions = "#A65D45")
  ) +
  scale_y_continuous(labels = scales::label_number(suffix = "%", accuracy = 1)) +
  labs(
    title = "Questions and weekly YouTube outcomes",
    subtitle = "FEct ATT and 95% bootstrap intervals; control: journalist attendance",
    x = NULL,
    y = "Estimated percent change",
    color = NULL
  ) +
  theme_minimal(base_size = 7) +
  theme(
    plot.title = element_text(face = "bold", size = 8.5),
    plot.subtitle = element_text(size = 6.2),
    strip.text = element_text(face = "bold", size = 6.2),
    axis.text = element_text(size = 5.4),
    axis.title.y = element_text(size = 6.2),
    legend.position = "bottom",
    legend.text = element_text(size = 6),
    panel.grid.minor = element_blank(),
    plot.margin = margin(4, 4, 3, 4)
  )

ggsave(output_path, plot, width = 4, height = 4, units = "in", device = "pdf")
cat("PDF saved to:", output_path, "\n")

# Four-panel monthly summary around the April 18, 2022 randomization.
rm(list = ls())

if (requireNamespace("rstudioapi", quietly = TRUE) && rstudioapi::isAvailable()) {
  setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
} else if (dir.exists(file.path(getwd(), "code", "07-final_panel"))) {
  setwd(file.path(getwd(), "code", "07-final_panel"))
}

source("../../project_paths.R")

library(tidyverse)
library(arrow)

randomization_date <- as.Date("2022-04-18")
window_start <- floor_date(randomization_date %m-% months(24), "month")
window_end <- ceiling_date(randomization_date %m+% months(24), "month") - days(1)

attendance_path <- media_path(
  "data", "06-outcomes", "deduplicated_source_panels",
  "attendance_entity_daily_panel.parquet"
)
questions_path <- media_path(
  "data", "06-outcomes", "deduplicated_source_panels",
  "questions_entity_daily_panel.parquet"
)
repository_root <- normalizePath(file.path(getwd(), "../.."), mustWork = TRUE)
output_dir <- file.path(repository_root, "output", "desc_stats")
output_path <- file.path(
  output_dir,
  "monthly_attendance_questions_randomization_window_4x4.pdf"
)
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

metric_labels <- c(
  attendance_mean_per_entity = "Mean attendance",
  questions_mean_per_entity = "Mean questions",
  questions_per_attendance = "Questions / attendance",
  questions_total = "Total questions"
)

classify_4t <- function(x) {
  if_else(x == "aligned", "aligned", "opposition + unclear")
}

attendance <- open_dataset(attendance_path) |>
  select(
    entity_id,
    date,
    ideology_4t,
    source_entity_matched,
    source_date_observed,
    attendance_n_journalists
  ) |>
  filter(
    source_entity_matched,
    date >= window_start,
    date <= window_end
  ) |>
  collect() |>
  mutate(group = classify_4t(ideology_4t))

questions <- open_dataset(questions_path) |>
  select(
    entity_id,
    date,
    ideology_4t,
    source_entity_matched,
    source_date_observed,
    questions_n,
    question_reporters_n
  ) |>
  filter(
    source_entity_matched,
    date >= window_start,
    date <= window_end
  ) |>
  collect() |>
  mutate(group = classify_4t(ideology_4t))

attendance_entities <- attendance |>
  distinct(group, entity_id) |>
  count(group, name = "attendance_entities")
question_entities <- questions |>
  distinct(group, entity_id) |>
  count(group, name = "question_entities")

attendance_daily <- attendance |>
  filter(source_date_observed) |>
  group_by(date, group) |>
  summarise(
    attendance_recorded = sum(attendance_n_journalists, na.rm = TRUE),
    .groups = "drop"
  )

questions_daily <- questions |>
  filter(source_date_observed) |>
  group_by(date, group) |>
  summarise(
    questions = sum(questions_n, na.rm = TRUE),
    question_reporters = sum(question_reporters_n, na.rm = TRUE),
    .groups = "drop"
  )

# At group-date level, every identified question reporter supplies a lower bound
# on attendance when the attendance source is missing or incomplete.
monthly <- full_join(attendance_daily, questions_daily, by = c("date", "group")) |>
  mutate(
    questions = replace_na(questions, 0),
    question_reporters = replace_na(question_reporters, 0),
    attendance_corrected = if_else(
      is.na(attendance_recorded),
      question_reporters,
      pmax(attendance_recorded, question_reporters)
    ),
    month = floor_date(date, "month")
  ) |>
  group_by(month, group) |>
  summarise(
    attendance_total = sum(attendance_corrected, na.rm = TRUE),
    questions_total = sum(questions, na.rm = TRUE),
    .groups = "drop"
  ) |>
  left_join(attendance_entities, by = "group") |>
  left_join(question_entities, by = "group") |>
  mutate(
    attendance_mean_per_entity = attendance_total / attendance_entities,
    questions_mean_per_entity = questions_total / question_entities,
    questions_per_attendance = if_else(
      attendance_total > 0,
      questions_total / attendance_total,
      NA_real_
    )
  )

plot_data <- monthly |>
  select(month, group, all_of(names(metric_labels))) |>
  pivot_longer(
    all_of(names(metric_labels)),
    names_to = "metric",
    values_to = "value"
  ) |>
  mutate(
    metric = factor(metric, levels = names(metric_labels), labels = metric_labels),
    value = if_else(
      month == as.Date("2021-11-01") &
        metric %in% c("Mean attendance", "Questions / attendance"),
      NA_real_,
      value
    )
  )

plot <- ggplot(plot_data, aes(month, value, color = group)) +
  geom_vline(
    xintercept = randomization_date,
    linetype = "dashed",
    color = "black",
    linewidth = 0.45
  ) +
  geom_line(linewidth = 0.2, alpha = 0.25, na.rm = TRUE) +
  geom_smooth(
    method = "loess",
    formula = y ~ x,
    span = 0.5,
    se = FALSE,
    linewidth = 0.6,
    na.rm = TRUE
  ) +
  facet_wrap(vars(metric), scales = "free_y", ncol = 2) +
  scale_color_manual(
    values = c(aligned = "#355C7D", `opposition + unclear` = "#8E3B46"),
    labels = c(aligned = "Aligned", `opposition + unclear` = "Opp. + Independent")
  ) +
  scale_x_date(
    limits = c(window_start, window_end),
    date_breaks = "1 year",
    date_labels = "%b\n%Y",
    expand = expansion(mult = c(0, 0))
  ) +
  scale_y_continuous(
    labels = scales::label_number(scale_cut = scales::cut_short_scale())
  ) +
  labs(
    title = NULL,
    subtitle = NULL,
    x = NULL,
    y = NULL,
    color = NULL
  ) +
  theme_minimal(base_size = 9.5) +
  theme(
    strip.text = element_text(face = "bold", size = 7),
    axis.text = element_text(size = 8),
    axis.text.x = element_text(size = 6.5),
    legend.position = "bottom",
    legend.text = element_text(size = 8),
    legend.key.width = unit(0.8, "cm"),
    panel.grid.minor = element_blank(),
    plot.margin = margin(4, 4, 3, 4)
  )

ggsave(
  output_path,
  plot,
  width = 4,
  height = 4,
  units = "in",
  device = "pdf"
)

cat("PDF saved to:", output_path, "\n")

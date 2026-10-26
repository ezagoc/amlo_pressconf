# Monthly journalist attendance and questions by 4T alignment.
rm(list = ls())

if (requireNamespace("rstudioapi", quietly = TRUE) && rstudioapi::isAvailable()) {
  setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
} else if (dir.exists(file.path(getwd(), "code", "07-final_panel"))) {
  setwd(file.path(getwd(), "code", "07-final_panel"))
}

source("../../project_paths.R")
source("../../src/final_panel_helpers.R")

library(tidyverse)
library(arrow)

panel_path <- media_path(
  "data", "06-outcomes", "final_panel", "final_daily_panel_2012_2025.parquet"
)
output_dir <- media_output_path(
  "results", "descriptives", "final_panel", "monthly_attendance_questions", ".keep"
) |>
  dirname()
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

panel <- open_dataset(panel_path) |>
  select(
    metadata_id,
    date,
    names.conference,
    names.transcripts,
    ideology.4t,
    attendance_n_journalists,
    questions_n
  ) |>
  collect() |>
  mutate(
    attendance_key = normalize_panel_key(names.conference),
    questions_key = normalize_panel_key(names.transcripts),
    group_three_way = ideology.4t |>
      replace_na("unclear") |>
      recode("opp" = "opposition"),
    group_binary = if_else(
      group_three_way == "aligned",
      "aligned",
      "opposition + unclear"
    )
  )

# Registry keys can map to multiple metadata rows. Allocate each source count
# equally across those rows so aggregation preserves the original source total.
mapping_count <- function(data, key, count_name) {
  key <- rlang::ensym(key)
  data |>
    distinct(metadata_id, !!key) |>
    filter(!is.na(!!key)) |>
    count(!!key, name = count_name)
}

panel <- panel |>
  left_join(
    mapping_count(panel, attendance_key, "attendance_mapping_n"),
    by = "attendance_key"
  ) |>
  left_join(
    mapping_count(panel, questions_key, "questions_mapping_n"),
    by = "questions_key"
  ) |>
  mutate(
    attendance_mapping_n = replace_na(attendance_mapping_n, 1L),
    questions_mapping_n = replace_na(questions_mapping_n, 1L),
    attendance = attendance_n_journalists / attendance_mapping_n,
    questions = questions_n / questions_mapping_n,
    # A journalist/outlet that asked at least one question must have attended.
    attendance = if_else(questions > 0 & attendance <= 0, 1, attendance),
    attendance_eligible = !is.na(attendance_key) | questions > 0,
    questions_eligible = !is.na(questions_key),
    month = lubridate::floor_date(date, "month")
  )

summarize_monthly <- function(data, group_column, grouping) {
  group_column <- rlang::ensym(group_column)

  outlet_month <- data |>
    mutate(group = !!group_column) |>
    group_by(month, metadata_id, group) |>
    summarise(
      attendance = sum(attendance, na.rm = TRUE),
      questions = sum(questions, na.rm = TRUE),
      attendance_eligible = any(attendance_eligible),
      questions_eligible = any(questions_eligible),
      .groups = "drop"
    )

  outlet_month |>
    group_by(month, group) |>
    summarise(
      attendance_total = sum(attendance[attendance_eligible], na.rm = TRUE),
      questions_total = sum(questions[questions_eligible], na.rm = TRUE),
      attendance_outlets = n_distinct(metadata_id[attendance_eligible]),
      question_outlets = n_distinct(metadata_id[questions_eligible]),
      attendance_mean_per_outlet = if_else(
        attendance_outlets > 0,
        attendance_total / attendance_outlets,
        NA_real_
      ),
      questions_mean_per_outlet = if_else(
        question_outlets > 0,
        questions_total / question_outlets,
        NA_real_
      ),
      questions_per_attendance = if_else(
        attendance_total > 0,
        questions_total / attendance_total,
        NA_real_
      ),
      .groups = "drop"
    ) |>
    mutate(grouping = grouping, .before = group)
}

monthly_three_way <- summarize_monthly(panel, group_three_way, "three_way")
monthly_binary <- summarize_monthly(panel, group_binary, "binary")

readr::write_csv(
  monthly_three_way,
  file.path(output_dir, "monthly_attendance_questions_three_way.csv")
)
readr::write_csv(
  monthly_binary,
  file.path(output_dir, "monthly_attendance_questions_binary.csv")
)

metric_labels <- c(
  attendance_total = "Total journalist attendance",
  questions_total = "Total questions asked",
  attendance_mean_per_outlet = "Mean attendance per eligible outlet",
  questions_mean_per_outlet = "Mean questions per eligible outlet",
  questions_per_attendance = "Questions per attendance"
)

plot_monthly <- function(data, title, filename, colors) {
  plot_data <- data |>
    select(month, group, all_of(names(metric_labels))) |>
    pivot_longer(
      all_of(names(metric_labels)),
      names_to = "metric",
      values_to = "value"
    ) |>
    mutate(metric = factor(metric, names(metric_labels), metric_labels))

  plot <- ggplot(plot_data, aes(month, value, color = group)) +
    geom_vline(
      xintercept = as.Date("2022-04-18"),
      linetype = "dashed",
      color = "black",
      linewidth = 0.7
    ) +
    geom_line(linewidth = 0.7, na.rm = TRUE) +
    facet_wrap(vars(metric), scales = "free_y", ncol = 2) +
    scale_color_manual(values = colors) +
    scale_y_continuous(
      labels = scales::label_number(scale_cut = scales::cut_short_scale())
    ) +
    labs(
      title = title,
      subtitle = "Attendance is set to one when questions are positive but recorded attendance is zero",
      x = NULL,
      y = NULL,
      color = "4T alignment"
    ) +
    theme_minimal(base_size = 11) +
    theme(
      legend.position = "bottom",
      panel.grid.minor = element_blank(),
      strip.text = element_text(face = "bold")
    )

  ggsave(file.path(output_dir, filename), plot, width = 14, height = 9, dpi = 300)
}

plot_monthly(
  monthly_three_way,
  "Monthly attendance and questions: aligned, opposition, and unclear",
  "monthly_attendance_questions_three_way.png",
  c(aligned = "#1B9E77", opposition = "#D95F02", unclear = "#7570B3")
)
plot_monthly(
  monthly_binary,
  "Monthly attendance and questions: aligned versus opposition + unclear",
  "monthly_attendance_questions_binary.png",
  c(aligned = "#1B9E77", `opposition + unclear` = "#D95F02")
)

cat("Monthly summaries saved to:", output_dir, "\n")

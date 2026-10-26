# Plot monthly and yearly outcome series by outlet ideology.
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

APRIL_2022_DATE <- as.Date("2022-04-18")

panel_path <- media_path(
  "data", "06-outcomes", "final_panel", "final_daily_panel_2012_2025.parquet"
)
contract_match_path <- media_path(
  "data", "06-outcomes", "final_panel", "contract_bene_final_match_report.csv"
)
figure_dir <- media_output_path("results", "descriptives", "final_panel", ".keep") |>
  dirname()
dir.create(figure_dir, recursive = TRUE, showWarnings = FALSE)

# Remove outputs from the superseded treatment that separated or excluded
# unclear outlets from the aligned-versus-opposition comparison.
obsolete_outputs <- c(
  "monthly_aligned_vs_opposition_excluding_unclear.png",
  "yearly_aligned_vs_opposition_excluding_unclear.png",
  "monthly_4t_unclear_sensitivity.csv",
  "yearly_4t_unclear_sensitivity.csv",
  "monthly_4t_unclear_sensitivity.png",
  "yearly_4t_unclear_sensitivity.png"
)
unlink(file.path(figure_dir, obsolete_outputs))

outcome_columns <- c(
  "contracts_costo",
  "attendance_n_journalists",
  "questions_n",
  "youtube_n_videos",
  "youtube_likes",
  "youtube_views",
  "youtube_comments"
)

panel <- open_dataset(panel_path) |>
  select(
    metadata_id,
    date,
    bene_final,
    names.conference,
    names.transcripts,
    ideology.leftright,
    ideology.4t,
    youtube_channel_ids,
    all_of(outcome_columns)
  ) |>
  collect()

# Recover the audited canonical contract key for each raw metadata value.
contract_keys <- readr::read_csv(contract_match_path, show_col_types = FALSE) |>
  select(bene_final, contract_key = source_key)

panel <- panel |>
  left_join(contract_keys, by = "bene_final", relationship = "many-to-one") |>
  mutate(
    attendance_key = normalize_panel_key(names.conference),
    questions_key = normalize_panel_key(names.transcripts),
    ideology_lr = replace_na(ideology.leftright, "unclear"),
    # Treat independent/unclear outlets as part of the opposition comparison.
    ideology_4t_group = ideology.4t |>
      replace_na("unclear") |>
      recode(
        "opp" = "opposition",
        "unclear" = "opposition"
      )
  )

# Outcomes attached through group-level registry keys are repeated across the
# member outlets. Divide by the number of mapped metadata rows before summing,
# preserving each source total while allocating it across ideology categories.
mapping_weights <- function(data, key, weight_name) {
  key <- rlang::ensym(key)
  data |>
    distinct(metadata_id, !!key) |>
    filter(!is.na(!!key)) |>
    count(!!key, name = weight_name)
}

contract_weights <- mapping_weights(panel, contract_key, "contract_mapping_n")
attendance_weights <- mapping_weights(panel, attendance_key, "attendance_mapping_n")
questions_weights <- mapping_weights(panel, questions_key, "questions_mapping_n")

# Channel IDs identify the actual YouTube source attached to each outlet. The
# mapping is constant within observed YouTube dates.
youtube_weights <- panel |>
  distinct(metadata_id, youtube_channel_ids) |>
  filter(!is.na(youtube_channel_ids)) |>
  count(youtube_channel_ids, name = "youtube_mapping_n")

panel <- panel |>
  left_join(contract_weights, by = "contract_key") |>
  left_join(attendance_weights, by = "attendance_key") |>
  left_join(questions_weights, by = "questions_key") |>
  left_join(youtube_weights, by = "youtube_channel_ids") |>
  mutate(
    contract_mapping_n = replace_na(contract_mapping_n, 1L),
    attendance_mapping_n = replace_na(attendance_mapping_n, 1L),
    questions_mapping_n = replace_na(questions_mapping_n, 1L),
    youtube_mapping_n = replace_na(youtube_mapping_n, 1L),
    contracts_costo = contracts_costo / contract_mapping_n,
    attendance_n_journalists = attendance_n_journalists / attendance_mapping_n,
    questions_n = questions_n / questions_mapping_n,
    across(
      all_of(outcome_columns[stringr::str_starts(outcome_columns, "youtube_")]),
      ~ .x / youtube_mapping_n
    )
  )

metric_labels <- c(
  contracts_costo = "Government advertising (costo, MXN)",
  attendance_n_journalists = "Journalist attendances",
  questions_n = "Questions asked",
  youtube_n_videos = "YouTube videos published",
  youtube_likes = "YouTube likes",
  youtube_views = "YouTube views",
  youtube_comments = "YouTube comments"
)

long_panel <- panel |>
  select(date, ideology_lr, ideology_4t_group, all_of(outcome_columns)) |>
  pivot_longer(
    cols = all_of(outcome_columns),
    names_to = "metric",
    values_to = "value"
  ) |>
  mutate(metric = factor(metric, levels = names(metric_labels), labels = metric_labels))

aggregate_series <- function(data, frequency = c("monthly", "yearly")) {
  frequency <- match.arg(frequency)
  period_unit <- if (frequency == "monthly") "month" else "year"

  data |>
    mutate(period = lubridate::floor_date(date, unit = period_unit)) |>
    group_by(period, ideology_lr, ideology_4t_group, metric) |>
    summarise(value = sum(value, na.rm = TRUE), .groups = "drop")
}

monthly <- aggregate_series(long_panel, "monthly")
yearly <- aggregate_series(long_panel, "yearly")

readr::write_csv(monthly, file.path(figure_dir, "monthly_outcomes_by_ideology.csv"))
readr::write_csv(yearly, file.path(figure_dir, "yearly_outcomes_by_ideology.csv"))

ideology_colors <- c(
  left = "#2166AC",
  center = "#7F7F7F",
  `center-right` = "#FDAE61",
  right = "#B2182B",
  unclear = "#BDBDBD"
)
alignment_colors <- c(
  aligned = "#1B9E77",
  opposition = "#D95F02"
)

plot_series <- function(data, group_var, colors, frequency, output_file) {
  group_var <- rlang::ensym(group_var)
  group_label <- if (rlang::as_string(group_var) == "ideology_lr") {
    "Left-right ideology"
  } else {
    "4T alignment"
  }

  plot_data <- data |>
    group_by(period, !!group_var, metric) |>
    summarise(value = sum(value, na.rm = TRUE), .groups = "drop")

  plot <- ggplot(plot_data, aes(x = period, y = value, color = !!group_var)) +
    geom_vline(
      xintercept = APRIL_2022_DATE,
      linetype = "dashed",
      color = "black",
      linewidth = 0.7
    ) +
    geom_line(linewidth = 0.65, na.rm = TRUE) +
    facet_wrap(vars(metric), scales = "free_y", ncol = 2) +
    scale_color_manual(values = colors, drop = FALSE) +
    scale_y_continuous(labels = scales::label_number(scale_cut = scales::cut_short_scale())) +
    labs(
      title = paste(stringr::str_to_title(frequency), "media outcomes by", group_label),
      subtitle = "Group-level outcomes are inverse-weighted to preserve source totals",
      x = NULL,
      y = NULL,
      color = group_label,
      caption = "Source: final_daily_panel_2012_2025.parquet"
    ) +
    theme_minimal(base_size = 11) +
    theme(
      legend.position = "bottom",
      panel.grid.minor = element_blank(),
      strip.text = element_text(face = "bold")
    )

  ggsave(
    file.path(figure_dir, output_file),
    plot,
    width = 14,
    height = 11,
    dpi = 300
  )
  plot
}

plot_series(
  monthly,
  ideology_lr,
  ideology_colors,
  "monthly",
  "monthly_outcomes_by_left_right_ideology.png"
)
plot_series(
  monthly,
  ideology_4t_group,
  alignment_colors,
  "monthly",
  "monthly_outcomes_by_4t_alignment.png"
)
plot_series(
  yearly,
  ideology_lr,
  ideology_colors,
  "yearly",
  "yearly_outcomes_by_left_right_ideology.png"
)
plot_series(
  yearly,
  ideology_4t_group,
  alignment_colors,
  "yearly",
  "yearly_outcomes_by_4t_alignment.png"
)

# -----------------------------------------------------------------------------
# Denominator-adjusted summaries
# -----------------------------------------------------------------------------

youtube_first_video <- panel |>
  filter(youtube_n_videos > 0) |>
  group_by(metadata_id) |>
  summarise(youtube_first_video_date = min(date), .groups = "drop")

adjusted_long <- panel |>
  left_join(youtube_first_video, by = "metadata_id") |>
  select(
    metadata_id,
    date,
    ideology_lr,
    ideology_4t_group,
    contract_key,
    attendance_key,
    questions_key,
    youtube_channel_ids,
    youtube_first_video_date,
    all_of(outcome_columns)
  ) |>
  pivot_longer(
    cols = all_of(outcome_columns),
    names_to = "metric_code",
    values_to = "value"
  ) |>
  mutate(
    metric = factor(
      metric_code,
      levels = names(metric_labels),
      labels = metric_labels
    ),
    eligible = case_when(
      metric_code == "contracts_costo" ~ !is.na(contract_key),
      metric_code == "attendance_n_journalists" ~ !is.na(attendance_key),
      metric_code == "questions_n" ~ !is.na(questions_key),
      str_starts(metric_code, "youtube_") ~
        !is.na(youtube_channel_ids) &
          !is.na(youtube_first_video_date) &
          date >= youtube_first_video_date,
      TRUE ~ FALSE
    )
  )

summarize_adjusted <- function(
    data,
    frequency = c("monthly", "yearly"),
    ideology = c("left_right", "4t")) {
  frequency <- match.arg(frequency)
  ideology <- match.arg(ideology)
  period_unit <- if (frequency == "monthly") "month" else "year"
  ideology_column <- if (ideology == "left_right") "ideology_lr" else "ideology_4t_group"

  outlet_period <- data |>
    mutate(
      period = lubridate::floor_date(date, unit = period_unit),
      ideology_group = .data[[ideology_column]]
    ) |>
    group_by(period, metadata_id, ideology_group, metric) |>
    summarise(
      value = sum(value, na.rm = TRUE),
      eligible = any(eligible),
      .groups = "drop"
    )

  outlet_period |>
    group_by(period, ideology_group, metric) |>
    summarise(
      total = sum(value[eligible], na.rm = TRUE),
      eligible_outlets = n_distinct(metadata_id[eligible]),
      active_outlets = n_distinct(metadata_id[eligible & value > 0]),
      mean_per_eligible = if_else(
        eligible_outlets > 0,
        total / eligible_outlets,
        NA_real_
      ),
      mean_conditional = if_else(
        active_outlets > 0,
        mean(value[eligible & value > 0], na.rm = TRUE),
        NA_real_
      ),
      recipient_share = if_else(
        eligible_outlets > 0,
        active_outlets / eligible_outlets,
        NA_real_
      ),
      .groups = "drop"
    ) |>
    group_by(period, metric) |>
    mutate(
      group_share = if (sum(total, na.rm = TRUE) > 0) {
        total / sum(total, na.rm = TRUE)
      } else {
        NA_real_
      },
      frequency = frequency,
      ideology_dimension = ideology
    ) |>
    ungroup()
}

adjusted_monthly <- bind_rows(
  summarize_adjusted(adjusted_long, "monthly", "left_right"),
  summarize_adjusted(adjusted_long, "monthly", "4t")
)
adjusted_yearly <- bind_rows(
  summarize_adjusted(adjusted_long, "yearly", "left_right"),
  summarize_adjusted(adjusted_long, "yearly", "4t")
)

readr::write_csv(
  adjusted_monthly,
  file.path(figure_dir, "monthly_outcomes_denominator_adjusted.csv")
)
readr::write_csv(
  adjusted_yearly,
  file.path(figure_dir, "yearly_outcomes_denominator_adjusted.csv")
)

plot_adjusted_stat <- function(
    data,
    ideology_dimension,
    statistic,
    colors,
    frequency,
    output_file) {
  plot_data <- data |>
    filter(.data$ideology_dimension == !!ideology_dimension)

  statistic_label <- dplyr::recode(
    statistic,
    total = "Total",
    mean_per_eligible = "Mean per eligible outlet",
    group_share = "Share of outcome",
    eligible_outlets = "Eligible outlets"
  )
  ideology_label <- if (ideology_dimension == "left_right") {
    "Left-right ideology"
  } else {
    "4T alignment"
  }

  y_scale <- if (statistic == "group_share") {
    scale_y_continuous(labels = scales::label_percent(accuracy = 1))
  } else {
    scale_y_continuous(labels = scales::label_number(scale_cut = scales::cut_short_scale()))
  }

  plot <- ggplot(
    plot_data,
    aes(x = period, y = .data[[statistic]], color = ideology_group)
  ) +
    geom_vline(
      xintercept = APRIL_2022_DATE,
      linetype = "dashed",
      color = "black",
      linewidth = 0.7
    ) +
    geom_line(linewidth = 0.7, na.rm = TRUE) +
    facet_wrap(vars(metric), scales = "free_y", ncol = 2) +
    scale_color_manual(values = colors, drop = FALSE) +
    y_scale +
    labs(
      title = paste(
        stringr::str_to_title(frequency),
        stringr::str_to_lower(statistic_label),
        "by",
        ideology_label
      ),
      subtitle = "Eligible denominators are outcome-specific; group mappings preserve source totals",
      x = NULL,
      y = NULL,
      color = ideology_label,
      caption = if (ideology_dimension == "left_right") {
        "Unclear is retained as a separate left-right classification"
      } else {
        "Independent/unclear outlets are included in opposition"
      }
    ) +
    theme_minimal(base_size = 11) +
    theme(
      legend.position = "bottom",
      panel.grid.minor = element_blank(),
      strip.text = element_text(face = "bold")
    )

  ggsave(
    file.path(figure_dir, output_file),
    plot,
    width = 14,
    height = 11,
    dpi = 300
  )
}

adjusted_sets <- list(monthly = adjusted_monthly, yearly = adjusted_yearly)
ideology_sets <- list(
  left_right = ideology_colors,
  `4t` = alignment_colors
)

for (frequency_name in names(adjusted_sets)) {
  for (ideology_name in names(ideology_sets)) {
    for (statistic_name in c("total", "mean_per_eligible", "group_share", "eligible_outlets")) {
      plot_adjusted_stat(
        adjusted_sets[[frequency_name]],
        ideology_name,
        statistic_name,
        ideology_sets[[ideology_name]],
        frequency_name,
        paste0(
          frequency_name,
          "_",
          statistic_name,
          "_by_",
          ideology_name,
          ".png"
        )
      )
    }
  }
}

# Direct comparison: opposition includes independent/unclear outlets.
for (frequency_name in names(adjusted_sets)) {
  comparison <- adjusted_sets[[frequency_name]] |>
    filter(
      ideology_dimension == "4t",
      ideology_group %in% c("aligned", "opposition")
    )

  plot <- ggplot(
    comparison,
    aes(x = period, y = mean_per_eligible, color = ideology_group)
  ) +
    geom_vline(
      xintercept = APRIL_2022_DATE,
      linetype = "dashed",
      color = "black",
      linewidth = 0.7
    ) +
    geom_line(linewidth = 0.8, na.rm = TRUE) +
    facet_wrap(vars(metric), scales = "free_y", ncol = 2) +
    scale_color_manual(values = alignment_colors[c("aligned", "opposition")]) +
    scale_y_continuous(labels = scales::label_number(scale_cut = scales::cut_short_scale())) +
    labs(
      title = paste(
        stringr::str_to_title(frequency_name),
        "aligned versus opposition outcomes per eligible outlet"
      ),
      subtitle = "Opposition includes independent/unclear outlets",
      x = NULL,
      y = NULL,
      color = "4T alignment"
    ) +
    theme_minimal(base_size = 11) +
    theme(legend.position = "bottom", panel.grid.minor = element_blank())

  ggsave(
    file.path(
      figure_dir,
      paste0(frequency_name, "_aligned_vs_opposition_including_independents.png")
    ),
    plot,
    width = 14,
    height = 11,
    dpi = 300
  )
}

# Contract extensive and intensive margins.
plot_contract_margins <- function(
    data,
    ideology_dimension,
    colors,
    frequency,
    output_file) {
  plot_data <- data |>
    filter(
      .data$ideology_dimension == !!ideology_dimension,
      metric == metric_labels[["contracts_costo"]]
    ) |>
    select(period, ideology_group, recipient_share, mean_conditional) |>
    pivot_longer(
      c(recipient_share, mean_conditional),
      names_to = "margin",
      values_to = "value"
    ) |>
    mutate(
      margin = recode(
        margin,
        recipient_share = "Outlets receiving a contract (share)",
        mean_conditional = "Mean amount among recipients (MXN)"
      )
    )

  plot <- ggplot(plot_data, aes(period, value, color = ideology_group)) +
    geom_vline(
      xintercept = APRIL_2022_DATE,
      linetype = "dashed",
      color = "black",
      linewidth = 0.7
    ) +
    geom_line(linewidth = 0.75, na.rm = TRUE) +
    facet_wrap(vars(margin), scales = "free_y", ncol = 1) +
    scale_color_manual(values = colors, drop = FALSE) +
    scale_y_continuous(labels = scales::label_number(scale_cut = scales::cut_short_scale())) +
    labs(
      title = paste(stringr::str_to_title(frequency), "contract margins"),
      subtitle = "Extensive margin and conditional intensive margin",
      x = NULL,
      y = NULL,
      color = if_else(ideology_dimension == "left_right", "Left-right ideology", "4T alignment")
    ) +
    theme_minimal(base_size = 11) +
    theme(legend.position = "bottom", panel.grid.minor = element_blank())

  ggsave(file.path(figure_dir, output_file), plot, width = 12, height = 9, dpi = 300)
}

for (frequency_name in names(adjusted_sets)) {
  plot_contract_margins(
    adjusted_sets[[frequency_name]],
    "left_right",
    ideology_colors,
    frequency_name,
    paste0(frequency_name, "_contract_margins_by_left_right.png")
  )
  plot_contract_margins(
    adjusted_sets[[frequency_name]],
    "4t",
    alignment_colors,
    frequency_name,
    paste0(frequency_name, "_contract_margins_by_4t.png")
  )
}

cat("Figures and summaries saved to:", figure_dir, "\n")

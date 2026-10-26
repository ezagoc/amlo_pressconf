# Daily FEct estimates for interactions under alternative temporary treatments.
rm(list = ls())

if (requireNamespace("rstudioapi", quietly = TRUE) && rstudioapi::isAvailable()) {
  setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
} else if (dir.exists(file.path(getwd(), "code", "07-final_panel"))) {
  setwd(file.path(getwd(), "code", "07-final_panel"))
}

source("../../project_paths.R")
library(tidyverse)
library(arrow)
library(fect)

repository_root <- normalizePath(file.path(getwd(), "../.."), mustWork = TRUE)
source_dir <- media_path("data", "06-outcomes", "deduplicated_source_panels")
output_dir <- file.path(repository_root, "output", "fect_youtube")
pdf_dir <- file.path(repository_root, "output", "pdf")
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(pdf_dir, recursive = TRUE, showWarnings = FALSE)

date_from <- as.Date("2022-04-18")
date_to <- as.Date("2024-12-31")
n_boots <- 50L

crosswalk <- read_parquet(file.path(source_dir, "metadata_outcome_crosswalk.parquet")) |>
  select(outcome, metadata_id, entity_id) |>
  distinct()

youtube_links <- crosswalk |>
  filter(outcome == "youtube") |>
  transmute(metadata_id, youtube_entity_id = entity_id)

make_links <- function(outcome_name, id_name) {
  outcome_links <- crosswalk |>
    filter(outcome == outcome_name) |>
    transmute(metadata_id, outcome_entity_id = entity_id)

  youtube_links |>
    inner_join(outcome_links, by = "metadata_id", relationship = "many-to-many") |>
    distinct(youtube_entity_id, outcome_entity_id) |>
    rename(!!id_name := outcome_entity_id)
}

attendance_links <- make_links("attendance", "attendance_entity_id")
question_links <- make_links("questions", "question_entity_id")

attendance <- read_parquet(file.path(source_dir, "attendance_entity_daily_panel.parquet")) |>
  filter(source_entity_matched, source_date_observed, between(date, date_from, date_to)) |>
  select(attendance_entity_id = entity_id, date, attendance_n_journalists) |>
  inner_join(attendance_links, by = "attendance_entity_id", relationship = "many-to-many") |>
  group_by(youtube_entity_id, date) |>
  summarise(attendance_records = sum(attendance_n_journalists, na.rm = TRUE), .groups = "drop")

questions <- read_parquet(file.path(source_dir, "questions_entity_daily_panel.parquet")) |>
  filter(source_entity_matched, source_date_observed, between(date, date_from, date_to)) |>
  select(question_entity_id = entity_id, date, questions_n, question_reporters_n) |>
  inner_join(question_links, by = "question_entity_id", relationship = "many-to-many") |>
  group_by(youtube_entity_id, date) |>
  summarise(
    questions = sum(questions_n, na.rm = TRUE),
    question_reporters = sum(question_reporters_n, na.rm = TRUE),
    .groups = "drop"
  )

panel <- read_parquet(file.path(source_dir, "youtube_entity_daily_panel.parquet")) |>
  filter(source_entity_matched, between(date, date_from, date_to)) |>
  select(
    youtube_entity_id = entity_id, date, outlet_names, ideology_4t,
    youtube_likes, youtube_comments
  ) |>
  left_join(attendance, by = c("youtube_entity_id", "date")) |>
  left_join(questions, by = c("youtube_entity_id", "date")) |>
  mutate(
    youtube_interactions = replace_na(youtube_likes, 0) + replace_na(youtube_comments, 0),
    questions = replace_na(questions, 0),
    question_reporters = replace_na(question_reporters, 0),
    attendance_records = if_else(
      is.na(attendance_records),
      question_reporters,
      pmax(attendance_records, question_reporters)
    ),
    attendance_records = replace_na(attendance_records, 0),
    question_day = as.integer(questions > 0),
    alignment = if_else(ideology_4t == "aligned", "Aligned", "Opp. + Independent")
  ) |>
  arrange(youtube_entity_id, date) |>
  group_by(youtube_entity_id) |>
  mutate(
    treatment_day = question_day,
    treatment_plus_1 = as.integer(question_day == 1L | lag(question_day, 1, default = 0L) == 1L),
    treatment_plus_2 = as.integer(
      question_day == 1L |
        lag(question_day, 1, default = 0L) == 1L |
        lag(question_day, 2, default = 0L) == 1L
    ),
    treatment_plus_3 = as.integer(
      question_day == 1L |
        lag(question_day, 1, default = 0L) == 1L |
        lag(question_day, 2, default = 0L) == 1L |
        lag(question_day, 3, default = 0L) == 1L
    )
  ) |>
  ungroup() |>
  mutate(
    sample_day = match(date, sort(unique(date))),
    attendance_dummy = as.integer(attendance_records > 0)
  )

if (anyDuplicated(panel[c("youtube_entity_id", "date")])) {
  stop("The daily analysis panel has duplicated outlet-day rows.", call. = FALSE)
}

# Apply pooled p1/p99 winsorization before the inverse hyperbolic sine.
cutoffs <- quantile(panel$youtube_interactions, c(0.01, 0.99), na.rm = TRUE)
panel <- panel |>
  mutate(
    interactions_winsorized = pmin(pmax(youtube_interactions, cutoffs[[1]]), cutoffs[[2]]),
    interactions_asinh = asinh(interactions_winsorized)
  )

panel_path <- file.path(output_dir, "youtube_questions_attendance_daily.parquet")
write_parquet(panel, panel_path, compression = "gzip")

treatments <- c(
  "Question day" = "treatment_day",
  "+1 day" = "treatment_plus_1",
  "+2 days" = "treatment_plus_2",
  "+3 days" = "treatment_plus_3"
)
groups <- c("Pooled", "Aligned", "Opp. + Independent")

estimate_one <- function(group_name, treatment_label) {
  treatment <- unname(treatments[[treatment_label]])
  data <- panel
  if (group_name != "Pooled") data <- filter(data, alignment == group_name)

  data <- data |>
    transmute(
      youtube_entity_id = as.character(youtube_entity_id), sample_day,
      Y = interactions_asinh,
      D = .data[[treatment]],
      X = attendance_dummy
    ) |>
    filter(!is.na(Y), !is.na(D), !is.na(X)) |>
    as.data.frame()

  fit <- fect(
    Y ~ D + X,
    data = data,
    index = c("youtube_entity_id", "sample_day"),
    method = "fe",
    force = "two-way",
    se = TRUE,
    vartype = "bootstrap",
    nboots = n_boots,
    parallel = FALSE,
    seed = 20261006,
    min.T0 = 5,
    na.rm = TRUE
  )

  estimate <- as.numeric(fit$est.avg[1, ])
  tibble(
    sample_group = group_name,
    treatment = treatment_label,
    treatment_days = match(treatment_label, names(treatments)),
    att = estimate[1],
    standard_error = estimate[2],
    conf95_low = estimate[3],
    conf95_high = estimate[4],
    conf90_low = estimate[1] - qnorm(0.95) * estimate[2],
    conf90_high = estimate[1] + qnorm(0.95) * estimate[2],
    p_value = estimate[5],
    n_rows = nrow(data),
    n_entities = n_distinct(data$youtube_entity_id),
    n_treated_cells = sum(data$D),
    bootstrap_replications = n_boots,
    winsor_lower = cutoffs[[1]],
    winsor_upper = cutoffs[[2]],
    transformation = "asinh(p1/p99 winsorized daily interactions)",
    attendance_control = "1 if the outlet attended that day; 0 otherwise"
  )
}

model_grid <- crossing(sample_group = groups, treatment = names(treatments))
results <- pmap_dfr(model_grid, function(sample_group, treatment) {
  message(sample_group, " | ", treatment)
  estimate_one(sample_group, treatment)
})

results_path <- file.path(output_dir, "fect_daily_asinh_interactions_50.csv")
write_csv(results, results_path)

colors <- c(
  "Pooled" = "#666666",
  "Aligned" = "#355C7D",
  "Opp. + Independent" = "#A65D45"
)
files <- c(
  "Pooled" = "fect_daily_asinh_interactions_pooled.pdf",
  "Aligned" = "fect_daily_asinh_interactions_aligned.pdf",
  "Opp. + Independent" = "fect_daily_asinh_interactions_opp_independent.pdf"
)

plot_group <- function(group_name) {
  plot_data <- results |>
    filter(sample_group == group_name) |>
    mutate(treatment = factor(treatment, levels = names(treatments)))

  plot <- ggplot(plot_data, aes(treatment, att, group = 1)) +
    geom_hline(yintercept = 0, color = "#555555", linewidth = 0.35) +
    geom_errorbar(
      aes(ymin = conf95_low, ymax = conf95_high),
      width = 0, linewidth = 0.4, color = colors[[group_name]]
    ) +
    geom_errorbar(
      aes(ymin = conf90_low, ymax = conf90_high),
      width = 0, linewidth = 1, color = colors[[group_name]]
    ) +
    geom_line(linewidth = 0.5, color = colors[[group_name]]) +
    geom_point(size = 1.7, color = colors[[group_name]]) +
    labs(
      title = paste0(group_name, ": daily interaction ATT"),
      subtitle = "Winsorized asinh; 50 bootstrap repetitions",
      x = "Temporary treatment definition",
      y = "FEct ATT"
    ) +
    theme_minimal(base_size = 8) +
    theme(
      plot.title = element_text(face = "bold", size = 9),
      plot.subtitle = element_text(size = 7),
      axis.text.x = element_text(size = 6.5),
      panel.grid.minor = element_blank()
    )

  path <- file.path(pdf_dir, files[[group_name]])
  ggsave(path, plot, width = 4, height = 4, units = "in", device = "pdf")
  path
}

pdf_paths <- map_chr(groups, plot_group)
cat("Daily panel:", panel_path, "\n")
cat("Results:", results_path, "\n")
cat(paste("PDF:", pdf_paths, collapse = "\n"), "\n")

# Build a deduplicated outlet-week panel for FEct estimates of question exposure.
rm(list = ls())

if (requireNamespace("rstudioapi", quietly = TRUE) && rstudioapi::isAvailable()) {
  setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
} else if (dir.exists(file.path(getwd(), "code", "07-final_panel"))) {
  setwd(file.path(getwd(), "code", "07-final_panel"))
}

source("../../project_paths.R")
library(tidyverse)
library(arrow)

panel_dir <- media_path("data", "06-outcomes", "deduplicated_source_panels")
attendance_path <- file.path(panel_dir, "attendance_entity_daily_panel.parquet")
questions_path <- file.path(panel_dir, "questions_entity_daily_panel.parquet")
youtube_path <- file.path(panel_dir, "youtube_entity_daily_panel.parquet")
crosswalk_path <- file.path(panel_dir, "metadata_outcome_crosswalk.parquet")

repository_root <- normalizePath(file.path(getwd(), "../.."), mustWork = TRUE)
output_dir <- file.path(repository_root, "output", "fect_youtube")
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

crosswalk <- read_parquet(crosswalk_path) |>
  select(outcome, metadata_id, entity_id) |>
  distinct()

youtube_links <- crosswalk |>
  filter(outcome == "youtube") |>
  transmute(metadata_id, youtube_entity_id = entity_id)

make_links <- function(outcome_name, new_id) {
  source_links <- crosswalk |>
    filter(outcome == outcome_name) |>
    transmute(metadata_id, source_entity_id = entity_id)

  youtube_links |>
    inner_join(source_links, by = "metadata_id", relationship = "many-to-many") |>
    distinct(youtube_entity_id, source_entity_id) |>
    rename(!!new_id := source_entity_id)
}

attendance_links <- make_links("attendance", "attendance_entity_id")
question_links <- make_links("questions", "question_entity_id")

# Each source entity is joined only once to each YouTube entity, even when several
# metadata rows express the same relationship.
attendance <- read_parquet(attendance_path) |>
  filter(source_entity_matched, source_date_observed) |>
  select(
    attendance_entity_id = entity_id,
    date,
    attendance_n_journalists
  ) |>
  inner_join(
    attendance_links,
    by = "attendance_entity_id",
    relationship = "many-to-many"
  ) |>
  group_by(youtube_entity_id, date) |>
  summarise(
    attendance_records = sum(attendance_n_journalists, na.rm = TRUE),
    .groups = "drop"
  )

questions <- read_parquet(questions_path) |>
  filter(source_entity_matched, source_date_observed) |>
  select(
    question_entity_id = entity_id,
    date,
    questions_n,
    question_reporters_n
  ) |>
  inner_join(
    question_links,
    by = "question_entity_id",
    relationship = "many-to-many"
  ) |>
  group_by(youtube_entity_id, date) |>
  summarise(
    questions = sum(questions_n, na.rm = TRUE),
    question_reporters = sum(question_reporters_n, na.rm = TRUE),
    .groups = "drop"
  )

youtube <- read_parquet(youtube_path) |>
  filter(
    source_entity_matched,
    date >= as.Date("2018-01-01"),
    date <= as.Date("2024-12-31")
  ) |>
  select(
    youtube_entity_id = entity_id,
    date,
    outlet_names,
    ideology_4t,
    source_date_observed,
    youtube_n_videos,
    youtube_views,
    youtube_likes,
    youtube_comments
  ) |>
  left_join(attendance, by = c("youtube_entity_id", "date")) |>
  left_join(questions, by = c("youtube_entity_id", "date")) |>
  mutate(
    questions = replace_na(questions, 0),
    question_reporters = replace_na(question_reporters, 0),
    attendance_records = if_else(
      is.na(attendance_records),
      question_reporters,
      pmax(attendance_records, question_reporters)
    ),
    attendance_records = replace_na(attendance_records, 0),
    week = floor_date(date, "week", week_start = 1)
  )

weekly <- youtube |>
  group_by(youtube_entity_id, outlet_names, ideology_4t, week) |>
  summarise(
    youtube_days_observed = sum(source_date_observed, na.rm = TRUE),
    youtube_videos = sum(youtube_n_videos, na.rm = TRUE),
    youtube_views = sum(youtube_views, na.rm = TRUE),
    youtube_likes = sum(youtube_likes, na.rm = TRUE),
    youtube_comments = sum(youtube_comments, na.rm = TRUE),
    attendance_records = sum(attendance_records, na.rm = TRUE),
    questions = sum(questions, na.rm = TRUE),
    .groups = "drop"
  ) |>
  mutate(
    youtube_interactions = youtube_likes + youtube_comments,
    question_week = as.integer(questions > 0)
  ) |>
  arrange(youtube_entity_id, week) |>
  group_by(youtube_entity_id) |>
  mutate(
    treatment_1week = question_week,
    treatment_2weeks = as.integer(question_week == 1L | lag(question_week, 1, default = 0L) == 1L),
    treatment_3weeks = as.integer(
      question_week == 1L |
        lag(question_week, 1, default = 0L) == 1L |
        lag(question_week, 2, default = 0L) == 1L
    ),
    log_attendance = log1p(attendance_records),
    lag_log_attendance = lag(log_attendance, 1),
    across(
      c(youtube_videos, youtube_views, youtube_likes, youtube_comments, youtube_interactions),
      list(log = ~ log1p(.x)),
      .names = "log_{.col}"
    )
  ) |>
  ungroup() |>
  mutate(week_index = as.integer((week - min(week)) / 7) + 1L)

if (anyDuplicated(weekly[c("youtube_entity_id", "week")])) {
  stop("The weekly analysis panel has duplicated outlet-week rows.", call. = FALSE)
}
if (any(weekly$treatment_1week > weekly$treatment_2weeks) ||
    any(weekly$treatment_2weeks > weekly$treatment_3weeks)) {
  stop("Treatment-window nesting failed.", call. = FALSE)
}

write_parquet(
  weekly,
  file.path(output_dir, "youtube_questions_attendance_weekly.parquet"),
  compression = "gzip"
)

diagnostics <- tribble(
  ~statistic, ~value,
  "rows", nrow(weekly),
  "youtube_entities", n_distinct(weekly$youtube_entity_id),
  "weeks", n_distinct(weekly$week),
  "question_weeks", sum(weekly$treatment_1week),
  "treated_cells_2weeks", sum(weekly$treatment_2weeks),
  "treated_cells_3weeks", sum(weekly$treatment_3weeks),
  "videos", sum(weekly$youtube_videos),
  "views", sum(weekly$youtube_views),
  "interactions", sum(weekly$youtube_interactions)
)
write_csv(diagnostics, file.path(output_dir, "weekly_panel_diagnostics.csv"))
print(diagnostics)

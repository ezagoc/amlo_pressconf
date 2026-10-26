# Build the final outlet-day panel from metadata and all daily outcomes.
rm(list = ls())

if (requireNamespace("rstudioapi", quietly = TRUE) && rstudioapi::isAvailable()) {
  setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
} else if (dir.exists(file.path(getwd(), "code", "07-final_panel"))) {
  setwd(file.path(getwd(), "code", "07-final_panel"))
}

source("../../project_paths.R")
source("../../src/balanced_metadata_panel.R")
source("../../src/final_panel_helpers.R")

library(tidyverse)
library(arrow)

DATE_FROM <- as.Date("2012-01-01")
DATE_TO <- as.Date("2025-12-31")

metadata_path <- media_path(
  "data", "00-newspaper_data", "processed", "newspaper_metadata_geocoded.parquet"
)
attendance_path <- media_path(
  "data", "02-conferences", "raw", "attendance", "panel_attendance.parquet.gzip"
)
contracts_path <- media_path(
  "data", "06-outcomes", "comsoc", "contracts_2012_2024_clean.parquet"
)
questions_path <- media_path(
  "data", "02-conferences", "auxiliar", "questions_dataset_dedup.parquet"
)
youtube_path <- media_path(
  "data", "06-outcomes", "youtube", "panel_daily.parquet"
)
output_dir <- media_path("data", "06-outcomes", "final_panel")
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

metadata <- read_parquet(metadata_path) |>
  mutate(metadata_id = as.integer(metadata_id))

# Registry crosswalks. A shared group key may map to multiple metadata rows.
contracts_raw <- read_parquet(contracts_path) |>
  mutate(
    date = as.Date(fecha.de.contratopedido),
    source_key = normalize_panel_key(bene_final),
    source_key = if_else(
      str_detect(source_key, "contralinea"),
      "contralinea",
      source_key
    )
  ) |>
  filter(between(date, DATE_FROM, DATE_TO), !is.na(source_key))

contract_source_keys <- unique(contracts_raw$source_key)

contract_registry_report <- metadata |>
  filter(!is.na(bene_final)) |>
  distinct(bene_final) |>
  mutate(
    raw_key = normalize_panel_key(bene_final),
    cleaned_key = clean_contract_key(bene_final),
    source_key = if_else(raw_key %in% contract_source_keys, raw_key, cleaned_key),
    matched = source_key %in% contract_source_keys
  )

contract_map <- metadata |>
  transmute(
    metadata_id,
    raw_key = normalize_panel_key(bene_final),
    cleaned_key = clean_contract_key(bene_final),
    source_key = if_else(raw_key %in% contract_source_keys, raw_key, cleaned_key)
  ) |>
  select(metadata_id, source_key) |>
  filter(!is.na(source_key)) |>
  distinct()

attendance_map <- metadata |>
  transmute(metadata_id, source_key = normalize_panel_key(names.conference)) |>
  filter(!is.na(source_key)) |>
  distinct()

questions_map <- metadata |>
  transmute(metadata_id, source_key = normalize_panel_key(names.transcripts)) |>
  filter(!is.na(source_key)) |>
  distinct()

youtube_map <- metadata |>
  select(metadata_id, youtube.channel) |>
  tidyr::separate_longer_delim(youtube.channel, delim = ",") |>
  transmute(metadata_id, source_key = youtube_url_token(youtube.channel)) |>
  filter(!is.na(source_key)) |>
  distinct()

# Contracts: aggregate by beneficiary and contract/order date before mapping.
contracts_daily_key <- contracts_raw |>
  group_by(source_key, date) |>
  summarise(
    contracts_n = n(),
    contracts_received_n = n_distinct(no.de.contratopedido, na.rm = TRUE),
    contracts_n_policies = n_distinct(id_poliza, na.rm = TRUE),
    contracts_importe = sum(importe, na.rm = TRUE),
    contracts_iva = sum(iva, na.rm = TRUE),
    contracts_cantidad = sum(cantidad, na.rm = TRUE),
    contracts_costo_unitario = sum(costo.unitario, na.rm = TRUE),
    contracts_costo = sum(costo, na.rm = TRUE),
    contracts_iva_costo = sum(iva.del.costo, na.rm = TRUE),
    contracts_product_types = collapse_unique(producto_clean),
    contracts_beneficiarios = collapse_unique(beneficiario),
    .groups = "drop"
  )

contracts_daily <- contracts_daily_key |>
  inner_join(contract_map, by = "source_key", relationship = "many-to-many") |>
  group_by(metadata_id, date) |>
  summarise(
    across(
      starts_with("contracts_") & where(is.numeric),
      ~ sum(.x, na.rm = TRUE)
    ),
    across(starts_with("contracts_") & where(is.character), collapse_unique),
    .groups = "drop"
  )

# Attendance is already an outlet-date panel; normalize its registry key and collapse aliases.
attendance_raw <- read_parquet(attendance_path) |>
  mutate(
    date = as.Date(fecha),
    source_key = normalize_panel_key(outlet_final)
  ) |>
  filter(between(date, DATE_FROM, DATE_TO), !is.na(source_key))

if (!"n_journalists_assumed" %in% names(attendance_raw)) {
  attendance_raw$n_journalists_assumed <- 0L
  attendance_raw$n_journalists_recorded <- attendance_raw$n_journalists
}
attendance_daily_key <- attendance_raw |>
  group_by(source_key, date) |>
  summarise(
    attendance_n_journalists = sum(n_journalists, na.rm = TRUE),
    attendance_n_journalists_recorded = sum(n_journalists_recorded, na.rm = TRUE),
    attendance_n_journalists_assumed = sum(n_journalists_assumed, na.rm = TRUE),
    attendance_attended = as.integer(any(attended > 0, na.rm = TRUE)),
    attendance_total = max(total_attendance, na.rm = TRUE),
    attendance_after = max(attendance_after, na.rm = TRUE),
    attendance_before = max(attendance_bef, na.rm = TRUE),
    conference_n_total_attend = max(n_total_attend, na.rm = TRUE),
    conference_n_reporters = max(n_reporteros, na.rm = TRUE),
    conference_n_youtubers = max(n_youtubers, na.rm = TRUE),
    .groups = "drop"
  )

attendance_daily <- attendance_daily_key |>
  inner_join(attendance_map, by = "source_key", relationship = "many-to-many") |>
  select(-source_key)

# Questions: count transcript items and reporters by outlet-day.
questions_raw <- read_parquet(questions_path) |>
  mutate(
    date = as.Date(date),
    source_key = normalize_panel_key(outlet_aux)
  ) |>
  filter(between(date, DATE_FROM, DATE_TO), !is.na(source_key))

questions_daily_key <- questions_raw |>
  deduplicate_canonical_question_items("source_key") |>
  group_by(source_key, date) |>
  summarise(
    question_items_n = n(),
    questions_n = sum(item_type == "pregunta", na.rm = TRUE),
    question_opinions_n = sum(item_type == "opinion", na.rm = TRUE),
    question_other_n = sum(!item_type %in% c("pregunta", "opinion"), na.rm = TRUE),
    question_reporters_n = n_distinct(reporter_aux, na.rm = TRUE),
    question_asked = as.integer(any(item_type == "pregunta", na.rm = TRUE)),
    question_reporter_names = collapse_unique(reporter_aux),
    .groups = "drop"
  )

questions_daily <- questions_daily_key |>
  inner_join(questions_map, by = "source_key", relationship = "many-to-many") |>
  group_by(metadata_id, date) |>
  summarise(
    across(
      starts_with("question") & where(is.numeric),
      ~ sum(.x, na.rm = TRUE)
    ),
    question_reporter_names = collapse_unique(question_reporter_names),
    .groups = "drop"
  ) |>
  mutate(question_asked = as.integer(question_asked > 0))

# YouTube: use the channel URL/handle, never the publication name.
youtube_raw <- read_parquet(youtube_path) |>
  mutate(
    date = as.Date(date),
    source_key = youtube_url_token(yt_customUrl)
  ) |>
  filter(between(date, DATE_FROM, DATE_TO), !is.na(source_key))

youtube_daily <- youtube_raw |>
  inner_join(youtube_map, by = "source_key", relationship = "many-to-many") |>
  group_by(metadata_id, date) |>
  summarise(
    youtube_n_channels = n_distinct(channel_id),
    youtube_n_videos = sum(n_videos, na.rm = TRUE),
    youtube_views = sum(viewCount, na.rm = TRUE),
    youtube_likes = sum(likeCount, na.rm = TRUE),
    youtube_comments = sum(commentCount, na.rm = TRUE),
    youtube_published = as.integer(any(published > 0, na.rm = TRUE)),
    youtube_flag_no_2018 = as.integer(any(flag_no_2018, na.rm = TRUE)),
    youtube_flag_no_2021 = as.integer(any(flag_no_2021, na.rm = TRUE)),
    youtube_channel_ids = collapse_unique(channel_id),
    youtube_handles = collapse_unique(yt_handle),
    youtube_custom_urls = collapse_unique(yt_customUrl),
    .groups = "drop"
  ) |>
  mutate(
    youtube_views_per_video = if_else(
      youtube_n_videos > 0,
      youtube_views / youtube_n_videos,
      0
    ),
    youtube_likes_per_video = if_else(
      youtube_n_videos > 0,
      youtube_likes / youtube_n_videos,
      0
    ),
    youtube_comments_per_video = if_else(
      youtube_n_videos > 0,
      youtube_comments / youtube_n_videos,
      0
    )
  )

assert_unique_panel_key(contracts_daily, "contracts_daily")
assert_unique_panel_key(attendance_daily, "attendance_daily")
assert_unique_panel_key(questions_daily, "questions_daily")
assert_unique_panel_key(youtube_daily, "youtube_daily")

# Generate the full metadata-date skeleton, then attach all outcomes.
panel <- metadata_to_balanced_panel(
  metadata,
  frequency = "daily",
  from = DATE_FROM,
  to = DATE_TO,
  date_col = "date"
)

outcome_tables <- list(
  contracts = contracts_daily,
  attendance = attendance_daily,
  questions = questions_daily,
  youtube = youtube_daily
)
numeric_outcomes <- outcome_tables |>
  purrr::map(~ names(.x)[vapply(.x, is.numeric, logical(1))]) |>
  unlist(use.names = FALSE) |>
  setdiff("metadata_id") |>
  unique()

panel <- panel |>
  left_join(contracts_daily, by = c("metadata_id", "date")) |>
  left_join(attendance_daily, by = c("metadata_id", "date")) |>
  left_join(questions_daily, by = c("metadata_id", "date")) |>
  left_join(youtube_daily, by = c("metadata_id", "date")) |>
  mutate(across(all_of(numeric_outcomes), ~ tidyr::replace_na(.x, 0))) |>
  arrange(metadata_id, date)

assert_unique_panel_key(panel, "final panel")

# Auditable key-level match diagnostics.
match_report <- bind_rows(
  make_match_report("contracts", contracts_raw$source_key, contract_map),
  make_match_report("attendance", attendance_raw$source_key, attendance_map),
  make_match_report("questions", questions_raw$source_key, questions_map),
  make_match_report("youtube_url", youtube_raw$source_key, youtube_map)
)

match_summary <- match_report |>
  group_by(source) |>
  summarise(
    source_keys = n(),
    matched_keys = sum(matched),
    unmatched_keys = sum(!matched),
    matched_source_rows = sum(source_rows[matched]),
    source_rows = sum(source_rows),
    .groups = "drop"
  )

write_parquet(
  panel,
  file.path(output_dir, "final_daily_panel_2012_2025.parquet"),
  compression = "zstd"
)
readr::write_csv(match_report, file.path(output_dir, "final_panel_match_report.csv"))
readr::write_csv(match_summary, file.path(output_dir, "final_panel_match_summary.csv"))
readr::write_csv(
  contract_registry_report,
  file.path(output_dir, "contract_bene_final_match_report.csv")
)

print(match_summary)
cat(
  "Metadata bene_final matches:",
  sum(contract_registry_report$matched),
  "of",
  nrow(contract_registry_report),
  "\n"
)
cat("Final panel:", nrow(panel), "rows x", ncol(panel), "columns\n")

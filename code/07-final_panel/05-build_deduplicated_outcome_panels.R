# Build one balanced daily panel per deduplicated outcome source ID.
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

DATE_FROM <- as.Date("2012-01-01")
DATE_TO <- as.Date("2025-12-31")
ALL_DATES <- seq(DATE_FROM, DATE_TO, by = "day")

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
output_dir <- media_path("data", "06-outcomes", "deduplicated_source_panels")
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

metadata <- read_parquet(metadata_path) |>
  mutate(metadata_id = as.integer(metadata_id))

contracts_raw <- read_parquet(contracts_path) |>
  mutate(
    date = as.Date(fecha.de.contratopedido),
    raw_key = normalize_panel_key(bene_final),
    cleaned_key = clean_contract_key(bene_final),
    source_key = if_else(str_detect(raw_key, "contralinea"), "contralinea", raw_key)
  ) |>
  filter(between(date, DATE_FROM, DATE_TO), !is.na(source_key))

contract_source_keys <- unique(contracts_raw$source_key)

# Crosswalks retain every metadata-to-source relationship. Outcome panels never
# duplicate observations across these metadata rows.
contract_crosswalk <- metadata |>
  transmute(
    outcome = "contracts",
    metadata_id,
    outlet_name = name.page,
    owner_group,
    ideology_leftright = ideology.leftright,
    ideology_4t = ideology.4t,
    source_value = bene_final,
    raw_key = normalize_panel_key(bene_final),
    cleaned_key = clean_contract_key(bene_final),
    source_key = if_else(raw_key %in% contract_source_keys, raw_key, cleaned_key),
    entity_id = source_key
  ) |>
  filter(!is.na(entity_id)) |>
  distinct()

attendance_crosswalk <- metadata |>
  transmute(
    outcome = "attendance",
    metadata_id,
    outlet_name = name.page,
    owner_group,
    ideology_leftright = ideology.leftright,
    ideology_4t = ideology.4t,
    source_value = names.conference,
    source_key = normalize_panel_key(names.conference),
    entity_id = source_key
  ) |>
  filter(!is.na(entity_id)) |>
  distinct()

questions_crosswalk <- metadata |>
  transmute(
    outcome = "questions",
    metadata_id,
    outlet_name = name.page,
    owner_group,
    ideology_leftright = ideology.leftright,
    ideology_4t = ideology.4t,
    source_value = names.transcripts,
    source_key = normalize_panel_key(names.transcripts),
    entity_id = source_key
  ) |>
  filter(!is.na(entity_id)) |>
  distinct()

youtube_crosswalk <- metadata |>
  select(
    metadata_id,
    outlet_name = name.page,
    owner_group,
    ideology_leftright = ideology.leftright,
    ideology_4t = ideology.4t,
    youtube.channel
  ) |>
  separate_longer_delim(youtube.channel, delim = ",") |>
  transmute(
    outcome = "youtube",
    metadata_id,
    outlet_name,
    owner_group,
    ideology_leftright,
    ideology_4t,
    source_value = str_squish(youtube.channel),
    source_key = youtube_url_token(youtube.channel),
    entity_id = source_key
  ) |>
  filter(!is.na(entity_id)) |>
  distinct()

crosswalk <- bind_rows(
  contract_crosswalk,
  attendance_crosswalk,
  questions_crosswalk,
  youtube_crosswalk
)

resolve_category <- function(x, unclear_values = c("", "unclear")) {
  values <- x |>
    replace_na("unclear") |>
    str_to_lower() |>
    str_squish()
  informative <- sort(unique(values[!values %in% unclear_values]))
  if (length(informative) == 0L) "unclear"
  else if (length(informative) == 1L) informative[[1L]]
  else paste0("conflict:", paste(informative, collapse = "|"))
}

entity_metadata <- crosswalk |>
  group_by(outcome, entity_id, source_key) |>
  summarise(
    n_metadata_rows = n_distinct(metadata_id),
    metadata_ids = paste(sort(unique(metadata_id)), collapse = " | "),
    outlet_names = collapse_unique(outlet_name),
    owner_groups = collapse_unique(owner_group),
    source_values = collapse_unique(source_value),
    ideology_leftright = resolve_category(ideology_leftright),
    ideology_4t = resolve_category(ideology_4t),
    ideology_leftright_conflict = str_starts(ideology_leftright, "conflict:"),
    ideology_4t_conflict = str_starts(ideology_4t, "conflict:"),
    .groups = "drop"
  ) |>
  group_by(outcome) |>
  arrange(entity_id, .by_group = TRUE) |>
  mutate(entity_number = row_number(), .after = outcome) |>
  ungroup()

build_panel <- function(entity_data, daily_data, observed, numeric_columns) {
  matched_entities <- unique(daily_data$entity_id)
  panel <- crossing(
    entity_data |> select(-source_key),
    date = ALL_DATES
  ) |>
    left_join(daily_data, by = c("entity_id", "date")) |>
    mutate(source_entity_matched = entity_id %in% matched_entities)

  if (is.function(observed)) {
    panel <- panel |> mutate(source_date_observed = observed(entity_id, date))
  } else {
    panel <- panel |> mutate(source_date_observed = date %in% observed)
  }

  panel |>
    mutate(
      across(
        all_of(numeric_columns),
        ~ if_else(source_date_observed, replace_na(.x, 0), NA_real_)
      )
    ) |>
    arrange(entity_number, date)
}

# -----------------------------------------------------------------------------
# Contracts: one observation per cleaned COMSOC beneficiary and contract date.
# -----------------------------------------------------------------------------
contracts_daily <- contracts_raw |>
  group_by(entity_id = source_key, date) |>
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

contract_numeric <- names(contracts_daily)[str_starts(names(contracts_daily), "contracts_")]
contract_numeric <- setdiff(
  contract_numeric,
  c("contracts_product_types", "contracts_beneficiarios")
)
contract_entities <- entity_metadata |> filter(outcome == "contracts")
contracts_panel <- build_panel(
  contract_entities,
  contracts_daily,
  observed = function(entity_id, date) {
    between(date, as.Date("2012-01-01"), as.Date("2024-12-31"))
  },
  numeric_columns = contract_numeric
)

# -----------------------------------------------------------------------------
# Attendance: a missing date in the source is unavailable, not zero attendance.
# -----------------------------------------------------------------------------
attendance_raw <- read_parquet(attendance_path) |>
  mutate(
    date = as.Date(fecha),
    entity_id = normalize_panel_key(outlet_final)
  ) |>
  filter(between(date, DATE_FROM, DATE_TO), !is.na(entity_id))

attendance_dates <- unique(attendance_raw$date)
# Older source panels predate explicit co-affiliation flags.
if (!"n_journalists_assumed" %in% names(attendance_raw)) {
  attendance_raw$n_journalists_assumed <- 0L
  attendance_raw$n_journalists_recorded <- attendance_raw$n_journalists
}
attendance_daily <- attendance_raw |>
  group_by(entity_id, date) |>
  summarise(
    attendance_n_journalists = sum(n_journalists, na.rm = TRUE),
    attendance_n_journalists_recorded = sum(n_journalists_recorded, na.rm = TRUE),
    attendance_n_journalists_assumed = sum(n_journalists_assumed, na.rm = TRUE),
    attendance_attended = as.integer(any(attended > 0, na.rm = TRUE)),
    attendance_total = max(total_attendance, na.rm = TRUE),
    conference_n_total_attend = max(n_total_attend, na.rm = TRUE),
    conference_n_reporters = max(n_reporteros, na.rm = TRUE),
    conference_n_youtubers = max(n_youtubers, na.rm = TRUE),
    .groups = "drop"
  )

attendance_entities <- entity_metadata |> filter(outcome == "attendance")
attendance_panel <- build_panel(
  attendance_entities,
  attendance_daily,
  observed = attendance_dates,
  numeric_columns = setdiff(names(attendance_daily), c("entity_id", "date"))
)

# -----------------------------------------------------------------------------
# Questions: one observation per transcript outlet and date.
# -----------------------------------------------------------------------------
questions_raw <- read_parquet(questions_path) |>
  mutate(
    date = as.Date(date),
    entity_id = normalize_panel_key(outlet_aux)
  ) |>
  filter(between(date, DATE_FROM, DATE_TO), !is.na(entity_id))

question_dates <- unique(questions_raw$date)
questions_daily <- questions_raw |>
  deduplicate_canonical_question_items("entity_id") |>
  group_by(entity_id, date) |>
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

question_numeric <- setdiff(
  names(questions_daily),
  c("entity_id", "date", "question_reporter_names")
)
question_entities <- entity_metadata |> filter(outcome == "questions")
questions_panel <- build_panel(
  question_entities,
  questions_daily,
  observed = question_dates,
  numeric_columns = question_numeric
)

# -----------------------------------------------------------------------------
# YouTube: use the channel URL token as the source ID.
# -----------------------------------------------------------------------------
youtube_raw <- read_parquet(youtube_path) |>
  mutate(
    date = as.Date(date),
    entity_id = youtube_url_token(yt_customUrl)
  ) |>
  filter(between(date, DATE_FROM, DATE_TO), !is.na(entity_id))

youtube_daily <- youtube_raw |>
  group_by(entity_id, date) |>
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
      youtube_n_videos > 0, youtube_views / youtube_n_videos, 0
    ),
    youtube_likes_per_video = if_else(
      youtube_n_videos > 0, youtube_likes / youtube_n_videos, 0
    ),
    youtube_comments_per_video = if_else(
      youtube_n_videos > 0, youtube_comments / youtube_n_videos, 0
    )
  )

youtube_observed <- youtube_daily |> distinct(entity_id, date) |> mutate(observed = TRUE)
youtube_matched_entities <- unique(youtube_daily$entity_id)
youtube_entities <- entity_metadata |> filter(outcome == "youtube")
youtube_panel <- crossing(
  youtube_entities |> select(-source_key),
  date = ALL_DATES
) |>
  left_join(youtube_daily, by = c("entity_id", "date")) |>
  left_join(youtube_observed, by = c("entity_id", "date")) |>
  mutate(
    source_entity_matched = entity_id %in% youtube_matched_entities,
    source_date_observed = replace_na(observed, FALSE),
    across(
      starts_with("youtube_") & where(is.numeric),
      ~ if_else(source_date_observed, replace_na(.x, 0), NA_real_)
    )
  ) |>
  select(-observed) |>
  arrange(entity_number, date)

panels <- list(
  contracts = contracts_panel,
  attendance = attendance_panel,
  questions = questions_panel,
  youtube = youtube_panel
)

for (outcome_name in names(panels)) {
  panel <- panels[[outcome_name]]
  if (anyDuplicated(panel[c("entity_id", "date")])) {
    stop(outcome_name, " panel has duplicated entity_id-date rows.", call. = FALSE)
  }
  write_parquet(
    panel,
    file.path(output_dir, paste0(outcome_name, "_entity_daily_panel.parquet")),
    compression = "gzip"
  )
}

write_parquet(crosswalk, file.path(output_dir, "metadata_outcome_crosswalk.parquet"))
write_parquet(entity_metadata, file.path(output_dir, "outcome_entity_metadata.parquet"))
readr::write_csv(
  entity_metadata |>
    count(outcome, name = "deduplicated_entities") |>
    left_join(
      crosswalk |> count(outcome, name = "metadata_links"),
      by = "outcome"
    ),
  file.path(output_dir, "panel_build_summary.csv")
)

cat("Deduplicated outcome panels saved to:", output_dir, "\n")
print(
  entity_metadata |>
    count(outcome, name = "deduplicated_entities") |>
    left_join(crosswalk |> count(outcome, name = "metadata_links"), by = "outcome")
)

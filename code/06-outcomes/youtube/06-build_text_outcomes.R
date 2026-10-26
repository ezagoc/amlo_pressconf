# Classify individual YouTube videos by topic and build a channel-day panel.
rm(list = ls())

if (requireNamespace("rstudioapi", quietly = TRUE) && rstudioapi::isAvailable()) {
  setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
} else if (dir.exists(file.path(getwd(), "code", "06-outcomes", "youtube"))) {
  setwd(file.path(getwd(), "code", "06-outcomes", "youtube"))
}

source("../../../project_paths.R")
source("../../../src/final_panel_helpers.R")

library(tidyverse)
library(arrow)

DATE_FROM <- as.Date("2018-01-01")
DATE_TO <- as.Date("2024-12-31")

channel_path <- media_path(
  "data", "06-outcomes", "youtube", "mexican_newspapers_youtube.xlsx"
)
source_folders <- c(
  media_path("data", "06-outcomes", "youtube", "videos"),
  media_path("data", "06-outcomes", "youtube", "big_channels"),
  media_path("data", "06-outcomes", "youtube", "playlists", "videos")
)
deduplicated_panel_path <- media_path(
  "data", "06-outcomes", "deduplicated_source_panels",
  "youtube_entity_daily_panel.parquet"
)
output_dir <- media_path("data", "06-outcomes", "youtube", "text_outcomes")
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

video_files <- source_folders |>
  map(~ list.files(.x, pattern = "[.]parquet$", full.names = TRUE)) |>
  unlist(use.names = FALSE) |>
  sort()

if (length(video_files) == 0L) {
  stop("No individual YouTube video parquet files were found.", call. = FALSE)
}

wanted_columns <- c(
  "videoId", "channel_id", "channelId", "publishedAt", "publishedAt_dt",
  "title", "description", "playlist_itemTitle", "yt_handle", "channelTitle"
)

read_video_file <- function(path) {
  available <- names(open_dataset(path))
  selected <- intersect(wanted_columns, available)
  data <- read_parquet(path, col_select = all_of(selected)) |> as_tibble()

  for (column in setdiff(wanted_columns, names(data))) {
    data[[column]] <- NA_character_
  }

  data |>
    transmute(
      video_id = as.character(videoId),
      channel_id = coalesce(as.character(channel_id), as.character(channelId)),
      published_at = coalesce(as.character(publishedAt_dt), as.character(publishedAt)),
      title = coalesce(as.character(title), as.character(playlist_itemTitle)),
      description = as.character(description),
      yt_handle = as.character(yt_handle),
      channel_title = as.character(channelTitle),
      source_file = basename(path)
    )
}

videos <- video_files |>
  map(read_video_file) |>
  bind_rows() |>
  filter(!is.na(video_id), nzchar(video_id)) |>
  mutate(
    text_length = nchar(coalesce(title, "")) + nchar(coalesce(description, ""))
  ) |>
  arrange(video_id, desc(text_length)) |>
  distinct(video_id, .keep_all = TRUE) |>
  mutate(
    # as.character(POSIXct) can omit the time at midnight. Accept date-only
    # strings as 00:00:00 instead of silently dropping those valid videos.
    published_at = suppressWarnings(lubridate::ymd_hms(
      published_at, quiet = TRUE, truncated = 3L, tz = "UTC"
    )),
    date = as.Date(published_at)
  ) |>
  filter(between(date, DATE_FROM, DATE_TO))

channel_dimension <- readxl::read_xlsx(channel_path) |>
  transmute(
    channel_id = as.character(channelId),
    yt_custom_url = as.character(yt_customUrl),
    entity_id = youtube_url_token(yt_customUrl),
    channel_outlet_name = as.character(name.page)
  ) |>
  filter(!is.na(channel_id)) |>
  arrange(channel_id, desc(!is.na(entity_id))) |>
  distinct(channel_id, .keep_all = TRUE)

normalize_search_text <- function(x) {
  x |>
    replace_na("") |>
    str_to_lower() |>
    stringi::stri_trans_general("Latin-ASCII") |>
    str_replace_all("[^a-z0-9]+", " ") |>
    str_squish()
}

morning_conference_pattern <- paste0(
  "\\bmananeras?\\b|",
  "\\bconferencias?(?: de prensa)? matutinas?\\b|",
  "\\bconferencias? mananeras?\\b"
)
amlo_morena_pattern <- "\\b(amlo|morena)\\b"

videos_classified <- videos |>
  left_join(channel_dimension, by = "channel_id", relationship = "many-to-one") |>
  mutate(
    title_normalized = normalize_search_text(title),
    description_normalized = normalize_search_text(description),
    text_available = nzchar(title_normalized) | nzchar(description_normalized),
    morning_conference_title = str_detect(title_normalized, morning_conference_pattern),
    morning_conference_description = str_detect(
      description_normalized, morning_conference_pattern
    ),
    morning_conference_mention =
      morning_conference_title | morning_conference_description,
    amlo_morena_title = str_detect(title_normalized, amlo_morena_pattern),
    amlo_morena_description = str_detect(description_normalized, amlo_morena_pattern),
    amlo_morena_mention = amlo_morena_title | amlo_morena_description,
    both_topics_mention = morning_conference_mention & amlo_morena_mention
  ) |>
  select(
    video_id,
    channel_id,
    entity_id,
    date,
    published_at,
    channel_outlet_name,
    yt_handle,
    channel_title,
    title,
    description,
    text_available,
    morning_conference_title,
    morning_conference_description,
    morning_conference_mention,
    amlo_morena_title,
    amlo_morena_description,
    amlo_morena_mention,
    both_topics_mention,
    source_file
  )

daily_observed <- videos_classified |>
  filter(!is.na(entity_id)) |>
  group_by(entity_id, date) |>
  summarise(
    youtube_total_videos = n_distinct(video_id),
    youtube_text_available_videos = n_distinct(video_id[text_available]),
    youtube_morning_conference_videos = n_distinct(
      video_id[morning_conference_mention]
    ),
    youtube_morning_conference_title_videos = n_distinct(
      video_id[morning_conference_title]
    ),
    youtube_amlo_morena_videos = n_distinct(video_id[amlo_morena_mention]),
    youtube_amlo_morena_title_videos = n_distinct(
      video_id[amlo_morena_title]
    ),
    youtube_both_topics_videos = n_distinct(video_id[both_topics_mention]),
    youtube_both_topics_title_videos = n_distinct(
      video_id[morning_conference_title & amlo_morena_title]
    ),
    .groups = "drop"
  ) |>
  mutate(
    youtube_text_coverage = youtube_text_available_videos / youtube_total_videos,
    youtube_morning_conference_share =
      youtube_morning_conference_videos / youtube_total_videos,
    youtube_morning_conference_title_share =
      youtube_morning_conference_title_videos / youtube_total_videos,
    youtube_amlo_morena_share = youtube_amlo_morena_videos / youtube_total_videos,
    youtube_amlo_morena_title_share =
      youtube_amlo_morena_title_videos / youtube_total_videos,
    youtube_both_topics_share = youtube_both_topics_videos / youtube_total_videos,
    youtube_both_topics_title_share =
      youtube_both_topics_title_videos / youtube_total_videos
  )

# Reuse the deduplicated YouTube skeleton so source IDs and metadata links stay
# compatible with every other outcome panel.
youtube_skeleton <- open_dataset(deduplicated_panel_path) |>
  select(
    outcome,
    entity_number,
    entity_id,
    n_metadata_rows,
    metadata_ids,
    outlet_names,
    owner_groups,
    source_values,
    ideology_leftright,
    ideology_4t,
    ideology_leftright_conflict,
    ideology_4t_conflict,
    date,
    source_entity_matched,
    source_date_observed
  ) |>
  filter(date >= DATE_FROM, date <= DATE_TO) |>
  collect()

count_columns <- c(
  "youtube_total_videos",
  "youtube_text_available_videos",
  "youtube_morning_conference_videos",
  "youtube_morning_conference_title_videos",
  "youtube_amlo_morena_videos",
  "youtube_amlo_morena_title_videos",
  "youtube_both_topics_videos",
  "youtube_both_topics_title_videos"
)
share_columns <- c(
  "youtube_text_coverage",
  "youtube_morning_conference_share",
  "youtube_morning_conference_title_share",
  "youtube_amlo_morena_share",
  "youtube_amlo_morena_title_share",
  "youtube_both_topics_share",
  "youtube_both_topics_title_share"
)

daily_panel <- youtube_skeleton |>
  left_join(daily_observed, by = c("entity_id", "date")) |>
  mutate(
    across(
      all_of(count_columns),
      ~ if_else(source_date_observed, replace_na(.x, 0), NA_real_)
    ),
    across(
      all_of(share_columns),
      ~ if_else(
        source_date_observed & youtube_total_videos == 0,
        0,
        .x
      )
    )
  ) |>
  arrange(entity_number, date)

if (anyDuplicated(videos_classified$video_id)) {
  stop("The classified video file contains duplicated video IDs.", call. = FALSE)
}
if (anyDuplicated(daily_panel[c("entity_id", "date")])) {
  stop("The text outcome panel contains duplicated entity-date rows.", call. = FALSE)
}

write_parquet(
  videos_classified,
  file.path(output_dir, "youtube_video_text_classified.parquet"),
  compression = "gzip"
)
write_parquet(
  daily_observed,
  file.path(output_dir, "youtube_text_outcomes_daily_observed.parquet"),
  compression = "gzip"
)
write_parquet(
  daily_panel,
  file.path(output_dir, "youtube_text_outcomes_entity_daily_panel.parquet"),
  compression = "gzip"
)

pattern_dictionary <- tribble(
  ~outcome, ~definition, ~search_scope, ~normalized_regex,
  "morning_conference", "primary", "title or description", morning_conference_pattern,
  "morning_conference", "title-only sensitivity", "title", morning_conference_pattern,
  "amlo_morena", "primary", "title or description", amlo_morena_pattern,
  "amlo_morena", "title-only sensitivity", "title", amlo_morena_pattern
)
readr::write_csv(
  pattern_dictionary,
  file.path(output_dir, "youtube_text_pattern_dictionary.csv")
)

summary <- tibble(
  statistic = c(
    "source_files",
    "unique_videos",
    "videos_with_text",
    "videos_without_text",
    "videos_matched_to_entity",
    "morning_conference_title_mentions",
    "morning_conference_any_text_mentions",
    "amlo_morena_title_mentions",
    "amlo_morena_any_text_mentions",
    "both_topic_title_mentions",
    "both_topic_any_text_mentions"
  ),
  value = c(
    length(video_files),
    nrow(videos_classified),
    sum(videos_classified$text_available),
    sum(!videos_classified$text_available),
    sum(!is.na(videos_classified$entity_id)),
    sum(videos_classified$morning_conference_title),
    sum(videos_classified$morning_conference_mention),
    sum(videos_classified$amlo_morena_title),
    sum(videos_classified$amlo_morena_mention),
    sum(
      videos_classified$morning_conference_title &
        videos_classified$amlo_morena_title
    ),
    sum(videos_classified$both_topics_mention)
  )
)
readr::write_csv(summary, file.path(output_dir, "youtube_text_pipeline_summary.csv"))

cat("YouTube text outcomes saved to:", output_dir, "\n")
print(summary)

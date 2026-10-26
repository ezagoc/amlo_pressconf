# Read-only audit of candidate title outcomes in the current FEct sample.
script_arg <- grep("^--file=", commandArgs(FALSE), value = TRUE)
script_path <- if (length(script_arg)) sub("^--file=", "", script_arg[[1]]) else
  file.path(getwd(), "code/07-final_panel/23-audit-youtube-title-outcomes.R")
root <- normalizePath(file.path(dirname(script_path), "../.."), mustWork = TRUE)
source(file.path(root, "project_paths.R"))
suppressPackageStartupMessages({library(arrow); library(dplyr); library(readr)})
source_dir <- media_path("data", "06-outcomes", "youtube", "text_outcomes")
analysis <- read_parquet(file.path(root, "output/fect_youtube/youtube_questions_attendance_daily.parquet")) |>
  transmute(entity_id = youtube_entity_id, date, question_day = treatment_day,
            group = recode(ideology_4t, aligned = "Aligned", opp = "Opp.", unclear = "Independent"))
text <- read_parquet(file.path(source_dir, "youtube_text_outcomes_entity_daily_panel.parquet"))
stopifnot(!anyDuplicated(analysis[c("entity_id", "date")]), !anyDuplicated(text[c("entity_id", "date")]))
panel <- left_join(analysis, text |> select(entity_id, date, starts_with("youtube_"), source_date_observed),
                   by = c("entity_id", "date"), relationship = "one-to-one")
stopifnot(all(panel$source_date_observed %in% TRUE), !anyNA(panel$youtube_total_videos))
candidates <- c("Mañanera (title)" = "youtube_morning_conference_title_videos",
                "AMLO or MORENA (title)" = "youtube_amlo_morena_title_videos",
                "Both topics (title)" = "youtube_both_topics_title_videos",
                "Mañanera (title or description)" = "youtube_morning_conference_videos",
                "AMLO or MORENA (title or description)" = "youtube_amlo_morena_videos")
audit <- bind_rows(lapply(c("Pooled", "Aligned", "Opp.", "Independent"), function(g) {
  x <- if (g == "Pooled") panel else filter(panel, group == g)
  bind_rows(lapply(names(candidates), function(label) {
    y <- x[[candidates[[label]]]]
    stopifnot(!anyNA(y), all(y >= 0 & y <= x$youtube_total_videos))
    tibble(group = g, outcome = label, variable = candidates[[label]],
           outlets = n_distinct(x$entity_id), outlet_days = nrow(x),
           total_videos = sum(x$youtube_total_videos), matching_videos = sum(y),
           share_all_videos = sum(y) / sum(x$youtube_total_videos),
           posting_days = sum(x$youtube_total_videos > 0), positive_days = sum(y > 0),
           question_days = sum(x$question_day), positive_question_days = sum(y > 0 & x$question_day == 1),
           positive_question_outlets = n_distinct(x$entity_id[y > 0 & x$question_day == 1]))
  }))
}))
date_from <- min(analysis$date)
date_to <- max(analysis$date)
videos <- open_dataset(file.path(source_dir, "youtube_video_text_classified.parquet")) |>
  select(video_id, entity_id, date, title, morning_conference_title, amlo_morena_title) |>
  filter(date >= date_from, date <= date_to) |> collect() |>
  semi_join(distinct(analysis, entity_id), by = "entity_id")
stopifnot(!anyDuplicated(videos$video_id), nrow(videos) == sum(panel$youtube_total_videos))
quality <- videos |> summarise(videos = n(), title_missing = sum(is.na(title) | !nzchar(trimws(title))),
                               title_missing_share = mean(is.na(title) | !nzchar(trimws(title))))
after_rebuild <- "--after-rebuild" %in% commandArgs(TRUE)
out <- file.path(root, "output/youtube_text_outcomes",
                 if (after_rebuild) "fect_candidate_audit_after_timestamp_fix" else "fect_candidate_audit")
dir.create(out, recursive = TRUE, showWarnings = FALSE)
write_csv(audit, file.path(out, "candidate_support.csv"))
write_csv(quality, file.path(out, "title_completeness.csv"))
source_counts <- read_parquet(media_path("data", "06-outcomes", "deduplicated_source_panels",
                                        "youtube_entity_daily_panel.parquet"),
                             col_select = c("entity_id", "date", "youtube_n_videos"))
comparison <- panel |> select(entity_id, date, youtube_total_videos) |>
  left_join(source_counts, by = c("entity_id", "date"), relationship = "one-to-one") |>
  mutate(difference = youtube_n_videos - youtube_total_videos)
write_csv(filter(comparison, difference != 0), file.path(out, "video_count_discrepancies.csv"))
# Audit a suspected timestamp parsing loss; do not alter the upstream data.
source(file.path(root, "src/final_panel_helpers.R"))
channel_map <- readxl::read_xlsx(media_path("data", "06-outcomes", "youtube", "mexican_newspapers_youtube.xlsx")) |>
  transmute(channel_id = as.character(channelId), entity_id = youtube_url_token(yt_customUrl)) |>
  distinct(channel_id, .keep_all = TRUE)
folders <- lapply(c("videos", "big_channels", "playlists/videos"), function(x)
  media_path("data", "06-outcomes", "youtube", x))
files <- unlist(lapply(folders, list.files, pattern = "[.]parquet$", full.names = TRUE))
midnight <- bind_rows(lapply(files, function(path) {
  wanted <- intersect(c("videoId", "channel_id", "channelId", "publishedAt_dt"), names(open_dataset(path)))
  if (!all(c("videoId", "publishedAt_dt") %in% wanted)) return(NULL)
  x <- read_parquet(path, col_select = all_of(wanted))
  channel <- if ("channel_id" %in% names(x)) as.character(x$channel_id) else as.character(x$channelId)
  tibble(video_id = as.character(x$videoId), channel_id = channel,
         timestamp_text = as.character(x$publishedAt_dt)) |>
    filter(grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", timestamp_text)) |>
    mutate(date = as.Date(timestamp_text)) |> filter(date >= date_from, date <= date_to)
})) |> distinct(video_id, .keep_all = TRUE) |>
  anti_join(videos |> select(video_id), by = "video_id") |>
  left_join(channel_map, by = "channel_id", relationship = "many-to-one") |>
  semi_join(distinct(analysis, entity_id), by = "entity_id")
midnight_counts <- midnight |> count(entity_id, date, name = "midnight_excluded")
check <- comparison |> left_join(midnight_counts, by = c("entity_id", "date")) |>
  mutate(midnight_excluded = coalesce(midnight_excluded, 0L))
write_csv(midnight, file.path(out, "midnight_timestamp_exclusions.csv"))
count_check <- check |> summarise(engagement_videos = sum(youtube_n_videos), text_videos = sum(youtube_total_videos),
                         count_discrepancies = sum(difference), midnight_exclusions = sum(midnight_excluded),
                         all_discrepancies_explained = all(difference == midnight_excluded))
write_csv(count_check, file.path(out, "video_count_reconciliation.csv"))
if (after_rebuild) stopifnot(all(check$difference == 0L), nrow(midnight) == 0L)
print(count_check, width = Inf)
print(audit |> filter(group == "Pooled") |> select(outcome, matching_videos, share_all_videos, positive_question_days))
print(audit |> filter(group != "Pooled", grepl("\\(title\\)", outcome)) |>
        select(group, outcome, question_days, positive_question_days, positive_question_outlets))
print(quality)

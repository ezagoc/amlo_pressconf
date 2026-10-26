# Monthly views and interactions for videos that mention each topic.
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
window_start <- floor_date(randomization_date %m-% months(18), "month")
window_end <- ceiling_date(randomization_date %m+% months(18), "month") - days(1)

source_folders <- c(
  media_path("data", "06-outcomes", "youtube", "videos"),
  media_path("data", "06-outcomes", "youtube", "big_channels"),
  media_path("data", "06-outcomes", "youtube", "playlists", "videos")
)
classified_path <- media_path(
  "data", "06-outcomes", "youtube", "text_outcomes",
  "youtube_video_text_classified.parquet"
)
entity_panel_path <- media_path(
  "data", "06-outcomes", "youtube", "text_outcomes",
  "youtube_text_outcomes_entity_daily_panel.parquet"
)
repository_root <- normalizePath(file.path(getwd(), "../.."), mustWork = TRUE)
data_output_dir <- file.path(repository_root, "output", "youtube_text_outcomes")
pdf_output_dir <- file.path(repository_root, "output", "pdf")
dir.create(data_output_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(pdf_output_dir, recursive = TRUE, showWarnings = FALSE)

video_files <- source_folders |>
  map(~ list.files(.x, pattern = "[.]parquet$", full.names = TRUE)) |>
  unlist(use.names = FALSE) |>
  sort()

read_metrics <- function(path) {
  available <- names(open_dataset(path))
  wanted <- intersect(c("videoId", "viewCount", "likeCount", "commentCount"), available)
  data <- read_parquet(path, col_select = all_of(wanted)) |> as_tibble()
  for (column in setdiff(c("videoId", "viewCount", "likeCount", "commentCount"), names(data))) {
    data[[column]] <- NA_real_
  }
  data |>
    transmute(
      video_id = as.character(videoId),
      views = suppressWarnings(as.numeric(viewCount)),
      likes = suppressWarnings(as.numeric(likeCount)),
      comments = suppressWarnings(as.numeric(commentCount))
    )
}

# A video may occur in more than one source file. YouTube counters are cumulative,
# so retain the largest observed value rather than summing duplicate snapshots.
metrics <- video_files |>
  map(read_metrics) |>
  bind_rows() |>
  filter(!is.na(video_id), nzchar(video_id)) |>
  group_by(video_id) |>
  summarise(
    views = if (all(is.na(views))) NA_real_ else max(views, na.rm = TRUE),
    likes = if (all(is.na(likes))) NA_real_ else max(likes, na.rm = TRUE),
    comments = if (all(is.na(comments))) NA_real_ else max(comments, na.rm = TRUE),
    .groups = "drop"
  ) |>
  mutate(interactions = likes + comments)

ideology <- read_parquet(entity_panel_path) |>
  distinct(entity_id, ideology_4t) |>
  mutate(
    group = if_else(
      ideology_4t == "aligned",
      "Aligned",
      "Opp. + Independent"
    )
  ) |>
  select(entity_id, group)

videos <- read_parquet(classified_path) |>
  filter(date >= window_start, date <= window_end) |>
  select(
    video_id, entity_id, date,
    morning_conference_mention, amlo_morena_mention
  ) |>
  left_join(metrics, by = "video_id", relationship = "one-to-one") |>
  left_join(ideology, by = "entity_id", relationship = "many-to-one") |>
  mutate(month = floor_date(date, "month"))

if (anyDuplicated(videos$video_id)) {
  stop("Duplicated video IDs remain after joining metrics.", call. = FALSE)
}

topic_videos <- videos |>
  pivot_longer(
    c(morning_conference_mention, amlo_morena_mention),
    names_to = "topic",
    values_to = "mention"
  ) |>
  filter(mention, !is.na(group)) |>
  mutate(
    topic = recode(
      topic,
      morning_conference_mention = "Morning press conference",
      amlo_morena_mention = "AMLO or MORENA"
    )
  )

summarize_metrics <- function(data, grouping) {
  data |>
    group_by(month, topic, group = {{ grouping }}) |>
    summarise(
      videos = n_distinct(video_id),
      videos_with_views = n_distinct(video_id[!is.na(views)]),
      videos_with_interactions = n_distinct(video_id[!is.na(interactions)]),
      views = sum(views, na.rm = TRUE),
      interactions = sum(interactions, na.rm = TRUE),
      likes = sum(likes, na.rm = TRUE),
      comments = sum(comments, na.rm = TRUE),
      .groups = "drop"
    )
}

monthly <- bind_rows(
  summarize_metrics(topic_videos, "All outlets"),
  summarize_metrics(topic_videos, group)
) |>
  arrange(month, topic, factor(group, c("All outlets", "Aligned", "Opp. + Independent")))

write_csv(
  monthly,
  file.path(data_output_dir, "youtube_topic_engagement_monthly.csv")
)

plot_data <- monthly |>
  filter(group == "All outlets") |>
  select(month, topic, group, views, interactions) |>
  pivot_longer(
    c(views, interactions),
    names_to = "metric",
    values_to = "value"
  ) |>
  mutate(
    metric = recode(metric, views = "Views", interactions = "Interactions"),
    panel = factor(
      paste(topic, metric, sep = " - "),
      levels = c(
        "AMLO or MORENA - Views",
        "AMLO or MORENA - Interactions",
        "Morning press conference - Views",
        "Morning press conference - Interactions"
      )
    ),
    group = factor(group, c("All outlets", "Aligned", "Opp. + Independent"))
  )

plot <- ggplot(plot_data, aes(month, value, color = group)) +
  geom_vline(
    xintercept = randomization_date,
    linetype = "dashed",
    color = "#4D4D4D",
    linewidth = 0.35
  ) +
  geom_line(linewidth = 0.2, alpha = 0.25, na.rm = TRUE) +
  geom_smooth(
    method = "loess",
    formula = y ~ x,
    span = 0.5,
    se = FALSE,
    linewidth = 0.55,
    na.rm = TRUE
  ) +
  facet_wrap(vars(panel), scales = "free_y", ncol = 2) +
  scale_color_manual(
    values = c(
      "All outlets" = "#666666",
      "Aligned" = "#355C7D",
      "Opp. + Independent" = "#A65D45"
    )
  ) +
  scale_x_date(date_breaks = "1 year", date_labels = "%Y") +
  scale_y_continuous(labels = scales::label_number(scale_cut = scales::cut_short_scale())) +
  labs(
    title = "Engagement with topic-mentioning videos - all outlets",
    subtitle = "Monthly totals; Oct. 2020-Oct. 2023; interactions = likes + comments",
    x = NULL,
    y = NULL,
    color = NULL
  ) +
  theme_minimal(base_size = 7) +
  theme(
    plot.title = element_text(face = "bold", size = 8.5),
    plot.subtitle = element_text(size = 6.2),
    strip.text = element_text(face = "bold", size = 6.2),
    axis.text = element_text(size = 5.3),
    legend.position = "bottom",
    legend.text = element_text(size = 6),
    legend.key.width = unit(0.7, "cm"),
    panel.grid.minor = element_blank(),
    plot.margin = margin(4, 4, 3, 4)
  )

output_path <- file.path(
  pdf_output_dir,
  "youtube_topic_engagement_monthly_18m_4x4.pdf"
)
ggsave(output_path, plot, width = 4, height = 4, units = "in", device = "pdf")

coverage <- videos |>
  summarise(
    videos = n(),
    videos_with_views = sum(!is.na(views)),
    videos_with_interactions = sum(!is.na(interactions))
  )
print(coverage)
cat("Monthly data saved to:", file.path(data_output_dir, "youtube_topic_engagement_monthly.csv"), "\n")
cat("PDF saved to:", output_path, "\n")

# Conference-only monthly descriptive figure. No metadata-row expansion.
# --scope=title_or_description (earlier definition, default) or --scope=title.
# --plot-only reuses the saved monthly file after checking input fingerprints.
entry <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)[1])
root <- normalizePath(file.path(dirname(entry), "../../.."), mustWork = TRUE)
source(file.path(root, "project_paths.R"))
suppressPackageStartupMessages({library(arrow); library(dplyr); library(tidyr);
  library(lubridate); library(ggplot2); library(patchwork)})
arg <- grep("^--scope=", commandArgs(TRUE), value = TRUE)
scope <- if (length(arg)) sub("^--scope=", "", arg[1]) else "title_or_description"
stopifnot(scope %in% c("title", "title_or_description"))
lottery <- as.Date("2022-04-18")
from <- as.Date("2020-10-01"); to <- as.Date("2023-10-31")
base <- media_path("data", "06-outcomes", "youtube")
classified_path <- file.path(base, "text_outcomes/youtube_video_text_classified.parquet")
panel_path <- file.path(base, "text_outcomes/youtube_text_outcomes_entity_daily_panel.parquet")
data_out <- media_path("results", "descriptive_stats", "youtube_conference")
dir.create(data_out, recursive = TRUE, showWarnings = FALSE)
pdf_out <- file.path(root, "output/pdf")
overleaf_out <- file.path(root, "overleaf/figures/descriptive_stats")
dir.create(overleaf_out, recursive = TRUE, showWarnings = FALSE)
stem <- paste0("youtube_conference_monthly_18m_", scope)
month_path <- file.path(data_out, paste0(stem, ".rds"))
manifest_path <- file.path(data_out, paste0(stem, "_inputs.csv"))

if (!"--plot-only" %in% commandArgs(TRUE)) {
  skeleton <- open_dataset(panel_path) |>
    filter(date >= from, date <= to, source_entity_matched, source_date_observed) |>
    select(entity_id, date, youtube_total_videos, youtube_morning_conference_videos,
           youtube_morning_conference_title_videos) |> collect()
  videos <- open_dataset(classified_path) |>
    filter(date >= from, date <= to) |>
    select(video_id, entity_id, date, morning_conference_title, morning_conference_mention) |>
    collect() |> semi_join(skeleton, by = c("entity_id", "date")) |>
    mutate(month = floor_date(date, "month"))
  stopifnot(!anyDuplicated(videos$video_id), !anyDuplicated(skeleton[c("entity_id", "date")]),
    !anyNA(videos$morning_conference_title), !anyNA(videos$morning_conference_mention))
  flag <- if (scope == "title") "morning_conference_title" else "morning_conference_mention"
  expected_flag <- if (scope == "title") "youtube_morning_conference_title_videos" else "youtube_morning_conference_videos"
  counts <- videos |> group_by(month) |>
    summarise(total_videos_all_topics = n(), conference_videos = sum(.data[[flag]]),
      outlets_posting = n_distinct(entity_id), conference_outlets = n_distinct(entity_id[.data[[flag]]]),
      .groups = "drop")
  expected <- skeleton |> mutate(month = floor_date(date, "month")) |>
    group_by(month) |> summarise(total = sum(youtube_total_videos),
      conference = sum(.data[[expected_flag]]), .groups = "drop")
  check <- inner_join(counts, expected, by = "month", relationship = "one-to-one")
  stopifnot(nrow(check) == 37L, all(check$total_videos_all_topics == check$total),
            all(check$conference_videos == check$conference))
  topic <- videos |> filter(.data[[flag]])
  files <- sort(unlist(lapply(file.path(base, c("videos", "big_channels", "playlists/videos")),
    list.files, pattern = "[.]parquet$", full.names = TRUE)))
  stopifnot(length(files) > 0)
  message("Reading metric snapshots from ", length(files), " files for ", nrow(topic), " conference videos.")
  pieces <- lapply(seq_along(files), function(i) {
    available <- names(open_dataset(files[i]))
    wanted <- intersect(c("videoId", "viewCount", "likeCount", "commentCount"), available)
    if (!"videoId" %in% wanted) {
      stopifnot(read_parquet(files[i], as_data_frame = FALSE)$num_rows == 0L)
      message("Skipping empty source placeholder: ", basename(files[i]))
      return(NULL)
    }
    z <- read_parquet(files[i], col_select = all_of(wanted))
    z <- z[as.character(z$videoId) %in% topic$video_id, ]
    for (v in setdiff(c("viewCount", "likeCount", "commentCount"), names(z))) z[[v]] <- NA_real_
    if (i %% 40 == 0) message("Read ", i, "/", length(files), " files.")
    transmute(z, video_id = as.character(videoId), views = as.numeric(viewCount),
      likes = as.numeric(likeCount), comments = as.numeric(commentCount))
  })
  max_observed <- function(x) if (all(is.na(x))) NA_real_ else max(x, na.rm = TRUE)
  metrics <- bind_rows(pieces) |> group_by(video_id) |>
    summarise(across(c(views, likes, comments), max_observed), snapshots = n(), .groups = "drop")
  stopifnot(all(as.matrix(metrics[c("views", "likes", "comments")]) >= 0, na.rm = TRUE),
            !anyDuplicated(metrics$video_id))
  topic <- topic |> left_join(metrics, by = "video_id", relationship = "one-to-one")
  # Missing counters remain missing: sum only reported counters and audit coverage.
  # Total interactions is the sum of the displayed monthly likes and comments.
  sum_observed <- function(x) if (all(is.na(x))) NA_real_ else sum(x, na.rm = TRUE)
  engagement <- topic |> group_by(month) |>
    summarise(videos_with_views = sum(!is.na(views)), videos_with_likes = sum(!is.na(likes)),
      videos_with_comments = sum(!is.na(comments)),
      videos_missing_any_metric = sum(is.na(views) | is.na(likes) | is.na(comments)),
      duplicated_snapshot_videos = sum(snapshots > 1, na.rm = TRUE),
      across(c(views, likes, comments), sum_observed), .groups = "drop")
  monthly <- counts |> left_join(engagement, by = "month", relationship = "one-to-one") |>
    mutate(share = conference_videos / total_videos_all_topics,
           interactions = likes + comments) |> arrange(month)
  stopifnot(nrow(monthly) == 37L, all(monthly$share >= 0 & monthly$share <= 1),
    all(monthly$interactions == monthly$likes + monthly$comments),
    sum(monthly$conference_videos) == nrow(topic))
  saveRDS(monthly, month_path)
  write.csv(monthly, file.path(data_out, paste0(stem, ".csv")), row.names = FALSE)
  inputs <- c(classified_path, panel_path, files)
  write.csv(data.frame(path = inputs, md5 = unname(tools::md5sum(inputs))), manifest_path, row.names = FALSE)
} else {
  inputs <- read.csv(manifest_path)
  stopifnot(identical(unname(tools::md5sum(inputs$path)), inputs$md5))
  monthly <- readRDS(month_path)
}

# Descriptive totals: no winsorization, regression transformation, or subgroup filter.
# A shared LOESS span makes the six panels comparable; monthly lines remain visible.
ink <- "#284E67"; monthly_color <- "#90A5B2"; rule <- "#777777"
x_breaks <- as.Date(c("2021-01-01", "2022-01-01", "2023-01-01"))
make_panel <- function(variable, label, percent = FALSE, lottery_label = FALSE) {
  z <- transmute(monthly, month, value = .data[[variable]])
  stopifnot(all(is.finite(z$value)))
  fit <- loess(value ~ as.numeric(month), data = z, span = .5, degree = 2,
               control = loess.control(surface = "direct"))
  # Do not extrapolate outside observed months. Negative fitted totals are clipped
  # only for display, and raw fitted values are retained in the saved smooth audit.
  z$smooth_raw <- as.numeric(predict(fit, newdata = z))
  z$smooth <- pmax(z$smooth_raw, 0)
  if (percent) z$smooth <- pmin(z$smooth, 1)
  write.csv(z, file.path(data_out, paste0(stem, "_", variable, "_smooth.csv")), row.names = FALSE)
  p <- ggplot(z, aes(month, value)) +
    geom_vline(xintercept = lottery, linetype = "dashed", linewidth = .35, colour = rule) +
    geom_line(linewidth = .35, colour = monthly_color) +
    geom_point(size = .7, colour = monthly_color) +
    geom_line(aes(y = smooth), linewidth = .75, colour = ink) +
    scale_x_date(breaks = x_breaks, date_labels = "%Y", limits = c(from, to),
                 expand = expansion(mult = c(.015, .015))) +
    scale_y_continuous(labels = if (percent) scales::label_percent(accuracy = 1) else
      scales::label_number(scale_cut = scales::cut_short_scale()),
      limits = c(0, NA), expand = expansion(mult = c(0, .1))) +
    labs(title = label, x = NULL, y = NULL) +
    theme_minimal(base_size = 10, base_family = "sans") +
    theme(plot.title = element_text(size = 10, face = "bold", colour = "#273741"),
      axis.text = element_text(size = 8.5, colour = "#4B5358"),
      panel.grid.minor = element_blank(), panel.grid.major.x = element_blank(),
      panel.grid.major.y = element_line(colour = "#E3E7E9", linewidth = .25),
      plot.margin = margin(8, 10, 5, 6))
  if (lottery_label) p <- p + annotate("text", x = lottery, y = Inf, label = "Lottery\nApr. 2022",
    hjust = -.1, vjust = 1.2, size = 2.7, colour = rule)
  p
}
panels <- list(
  make_panel("conference_videos", "A. Conference videos", lottery_label = TRUE),
  make_panel("share", "B. Share of all videos", percent = TRUE),
  make_panel("views", "C. Total views"),
  make_panel("interactions", "D. Total interactions"),
  make_panel("likes", "E. Likes"),
  make_panel("comments", "F. Comments"))
figure <- wrap_plots(panels, ncol = 2)
pdf_path <- file.path(pdf_out, paste0(stem, ".pdf"))
ggsave(pdf_path, figure, width = 7.2, height = 7.1, units = "in", device = "pdf", useDingbats = FALSE)
ggsave(file.path(pdf_out, paste0(stem, ".png")), figure, width = 7.2, height = 7.1, units = "in", dpi = 220)
stopifnot(file.exists(pdf_path), file.info(pdf_path)$size > 0,
  file.copy(pdf_path, file.path(overleaf_out, paste0(stem, ".pdf")), overwrite = TRUE))
print(monthly |> summarise(all_videos = sum(total_videos_all_topics), conference_videos = sum(conference_videos),
  weighted_share = sum(conference_videos)/sum(total_videos_all_topics),
  missing_metrics = sum(videos_missing_any_metric), views = sum(views), likes = sum(likes), comments = sum(comments)))
cat("PASS: video IDs deduplicated, counts match the rebuilt text panel, interactions = likes + comments.\n")
cat("Definition:", scope, "| Monthly totals, October 2020-October 2023 | All outlets\n")
cat("Monthly light lines; LOESS span .5 dark lines; dashed lottery date.\n")
cat("Snapshot metrics attributed to publication month, not engagement received that month.\n")
cat("PDF:", pdf_path, "\n")

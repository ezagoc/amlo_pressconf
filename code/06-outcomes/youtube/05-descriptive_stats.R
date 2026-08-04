# =========================
# CONFIG
# =========================

source("../../../project_paths.R")

PANEL_PATH  <- media_path('data', '06-outcomes', 'youtube', 'panel_daily.parquet')
DIM_PATH    <- media_path('data', '06-outcomes', 'youtube', 'mexican_newspapers_youtube.xlsx')
OUT_FOLDER  <- dirname(media_output_path('data', '06-outcomes', 'youtube', 'graphs', '.keep'))

# =========================
# Libraries
# =========================

suppressPackageStartupMessages({
  library(arrow)
  library(readxl)
  library(dplyr)
  library(tidyr)
  library(lubridate)
  library(ggplot2)
  library(scales)
  library(patchwork)
  library(forcats)
})

dir.create(OUT_FOLDER, recursive = TRUE, showWarnings = FALSE)

theme_set(theme_minimal(base_size = 11) +
  theme(plot.title = element_text(face = "bold"),
        panel.grid.minor = element_blank()))

panel_sep_theme <- function() {
  theme(
    panel.border = element_rect(colour = "grey70", fill = NA, linewidth = 0.6),
    plot.background = element_rect(fill = "white", colour = NA),
    plot.margin = margin(10, 12, 10, 12)
  )
}

# =========================
# Load data
# =========================

cat("Loading panel...\n")
panel <- read_parquet(PANEL_PATH) |>
  mutate(date = as.Date(date))

cat(sprintf("  %s rows, %s channels, %s to %s\n",
  format(nrow(panel), big.mark = ","),
  n_distinct(panel$channel_id),
  min(panel$date), max(panel$date)))

cat("Loading channel dimension table...\n")
dim_ch <- read_excel(DIM_PATH) |>
  select(channel_id = channelId,
         name_page   = `name.page`,
         yt_handle,
         yt_subscriberCount,
         yt_videoCount,
         yt_viewCount,
         yt_createdAt) |>
  filter(!is.na(channel_id)) |>
  distinct(channel_id, .keep_all = TRUE) |>
  mutate(created_year = year(as.Date(substr(yt_createdAt, 1, 10))))

# =========================
# Descriptive stats (console)
# =========================

cat("\n========== DESCRIPTIVE STATS ==========\n")

panel_active <- panel |> filter(n_videos > 0)

ch_totals <- panel |>
  group_by(channel_id, `name.page`) |>
  summarise(
    total_videos    = sum(n_videos, na.rm = TRUE),
    total_views     = sum(viewCount, na.rm = TRUE),
    total_likes     = sum(likeCount, na.rm = TRUE),
    total_comments  = sum(commentCount, na.rm = TRUE),
    active_days     = sum(published, na.rm = TRUE),
    .groups = "drop"
  )

stats_vars <- c("total_videos", "total_views", "total_likes", "total_comments", "active_days")
cat("\nChannel-level totals (2018-2024):\n")
for (v in stats_vars) {
  x <- ch_totals[[v]]
  cat(sprintf("  %-20s  mean=%s  median=%s  p25=%s  p75=%s  max=%s\n",
    v,
    format(round(mean(x, na.rm=TRUE)), big.mark=","),
    format(round(median(x, na.rm=TRUE)), big.mark=","),
    format(round(quantile(x, .25, na.rm=TRUE)), big.mark=","),
    format(round(quantile(x, .75, na.rm=TRUE)), big.mark=","),
    format(round(max(x, na.rm=TRUE)), big.mark=",")))
}

cat("\nPer-video metrics (days with at least 1 video):\n")
pv_vars <- c("viewCount_per_video", "likeCount_per_video", "commentCount_per_video")
for (v in pv_vars) {
  x <- panel_active[[v]]
  cat(sprintf("  %-28s  mean=%s  median=%s  p75=%s  p95=%s  max=%s\n",
    v,
    format(round(mean(x, na.rm=TRUE)), big.mark=","),
    format(round(median(x, na.rm=TRUE)), big.mark=","),
    format(round(quantile(x, .75, na.rm=TRUE)), big.mark=","),
    format(round(quantile(x, .95, na.rm=TRUE)), big.mark=","),
    format(round(max(x, na.rm=TRUE)), big.mark=",")))
}
cat("========================================\n\n")

# =========================
# Helper: save figure
# =========================

save_fig <- function(p, name, w = 12, h = 7) {
  path <- file.path(OUT_FOLDER, name)
  ggsave(path, p, width = w, height = h, dpi = 300, bg = "white")
  cat(sprintf("Saved: %s\n", path))
}

# =========================
# Fig 1 — Time series (weekly + monthly)
# =========================

make_timeseries_plot <- function(df_agg, freq_label) {
  p1 <- ggplot(df_agg, aes(x = period, y = n_videos)) +
    geom_line(colour = "#2C7BB6", linewidth = 0.6) +
    geom_area(fill = "#2C7BB6", alpha = 0.15) +
    scale_y_continuous(labels = comma) +
    scale_x_date(date_breaks = "1 year", date_labels = "%Y") +
    labs(title = "Videos published", x = NULL, y = "# videos") +
    panel_sep_theme()

  p2 <- ggplot(df_agg, aes(x = period, y = viewCount)) +
    geom_line(colour = "#1A9641", linewidth = 0.6) +
    geom_area(fill = "#1A9641", alpha = 0.15) +
    scale_y_continuous(labels = label_number(scale_cut = cut_short_scale())) +
    scale_x_date(date_breaks = "1 year", date_labels = "%Y") +
    labs(title = "Total views", x = NULL, y = "views") +
    panel_sep_theme()

  df_eng <- df_agg |> mutate(engagement = likeCount + commentCount)
  p3 <- ggplot(df_eng, aes(x = period, y = engagement)) +
    geom_line(colour = "#D7191C", linewidth = 0.6) +
    geom_area(fill = "#D7191C", alpha = 0.15) +
    scale_y_continuous(labels = label_number(scale_cut = cut_short_scale())) +
    scale_x_date(date_breaks = "1 year", date_labels = "%Y") +
    labs(title = "Likes + comments", x = NULL, y = "count") +
    panel_sep_theme()

  (p1 / p2 / p3) +
    plot_layout(heights = c(1, 1, 1)) &
    theme(panel.spacing = unit(10, "mm")) +
    plot_annotation(
      title    = sprintf("Mexican newspaper YouTube channels — %s aggregate", freq_label),
      subtitle = "All channels combined, 2018–2024",
      theme    = theme(plot.title = element_text(face = "bold", size = 13))
    )
}

# Weekly
weekly <- panel |>
  mutate(period = floor_date(date, "week")) |>
  group_by(period) |>
  summarise(
    n_videos     = sum(n_videos, na.rm = TRUE),
    viewCount    = sum(viewCount, na.rm = TRUE),
    likeCount    = sum(likeCount, na.rm = TRUE),
    commentCount = sum(commentCount, na.rm = TRUE),
    .groups = "drop"
  )

save_fig(make_timeseries_plot(weekly, "weekly"), "fig1_timeseries_weekly.png", w = 13, h = 9)

# Monthly
monthly <- panel |>
  mutate(period = floor_date(date, "month")) |>
  group_by(period) |>
  summarise(
    n_videos     = sum(n_videos, na.rm = TRUE),
    viewCount    = sum(viewCount, na.rm = TRUE),
    likeCount    = sum(likeCount, na.rm = TRUE),
    commentCount = sum(commentCount, na.rm = TRUE),
    .groups = "drop"
  )

save_fig(make_timeseries_plot(monthly, "monthly"), "fig1_timeseries_monthly.png", w = 13, h = 9)

# =========================
# Fig 2 — Channel-level distributions (from dim table)
# =========================

dim_plot <- dim_ch |> filter(!is.na(yt_subscriberCount) | !is.na(yt_videoCount))

p_subs <- ggplot(dim_plot |> filter(!is.na(yt_subscriberCount), yt_subscriberCount > 0),
    aes(x = yt_subscriberCount)) +
  geom_histogram(bins = 30, fill = "#2C7BB6", colour = "white", linewidth = 0.2) +
  scale_x_log10(labels = label_number(scale_cut = cut_short_scale())) +
  labs(title = "Subscriber count", x = "subscribers (log scale)", y = "channels") +
  panel_sep_theme()

p_vids <- ggplot(dim_plot |> filter(!is.na(yt_videoCount), yt_videoCount > 0),
    aes(x = yt_videoCount)) +
  geom_histogram(bins = 30, fill = "#1A9641", colour = "white", linewidth = 0.2) +
  scale_x_log10(labels = comma) +
  labs(title = "Total videos on channel", x = "videos (log scale)", y = "channels") +
  panel_sep_theme()

p_views <- ggplot(dim_plot |> filter(!is.na(yt_viewCount), yt_viewCount > 0),
    aes(x = yt_viewCount)) +
  geom_histogram(bins = 30, fill = "#D7191C", colour = "white", linewidth = 0.2) +
  scale_x_log10(labels = label_number(scale_cut = cut_short_scale())) +
  labs(title = "Total channel views", x = "views (log scale)", y = "channels") +
  panel_sep_theme()

year_counts <- dim_ch |>
  filter(!is.na(created_year)) |>
  count(created_year)

p_year <- ggplot(year_counts, aes(x = factor(created_year), y = n)) +
  geom_col(fill = "#756BB1", colour = "white", linewidth = 0.2) +
  labs(title = "Channel creation year", x = NULL, y = "channels") +
  theme(axis.text.x = element_text(angle = 45, hjust = 1)) +
  panel_sep_theme()

fig2 <- (p_subs | p_vids) / (p_views | p_year) +
  plot_layout(guides = "collect") &
  theme(panel.spacing = unit(10, "mm")) +
  plot_annotation(
    title    = "Channel-level descriptive statistics",
    subtitle = "From YouTube Data API channel metadata",
    theme    = theme(plot.title = element_text(face = "bold", size = 13))
  )

save_fig(fig2, "fig2_channel_distributions.png", w = 13, h = 8)

# =========================
# Fig 3 — Top 20 by total videos
# =========================

# Aggregate by name.page first (a newspaper may have multiple channels)
# so fct_reorder sorts on the true group total, not the per-channel median
top_videos <- ch_totals |>
  group_by(`name.page`) |>
  summarise(total_videos = sum(total_videos, na.rm = TRUE), .groups = "drop") |>
  slice_max(total_videos, n = 20, with_ties = FALSE) |>
  mutate(`name.page` = fct_reorder(`name.page`, total_videos))

fig3 <- ggplot(top_videos, aes(x = total_videos, y = `name.page`)) +
  geom_col(fill = "#2C7BB6") +
  geom_text(aes(label = comma(total_videos)), hjust = -0.1, size = 3) +
  scale_x_continuous(labels = comma,
                     expand = expansion(mult = c(0, 0.15))) +
  labs(title = "Top 20 channels by total videos published (2018–2024)",
       x = "total videos", y = NULL)

save_fig(fig3, "fig3_top20_videos.png", w = 11, h = 7)

# =========================
# Fig 4 — Top 20 by total views
# =========================

top_views <- ch_totals |>
  group_by(`name.page`) |>
  summarise(total_views = sum(total_views, na.rm = TRUE), .groups = "drop") |>
  slice_max(total_views, n = 20, with_ties = FALSE) |>
  mutate(`name.page` = fct_reorder(`name.page`, total_views))

fig4 <- ggplot(top_views, aes(x = total_views, y = `name.page`)) +
  geom_col(fill = "#1A9641") +
  geom_text(aes(label = label_number(scale_cut = cut_short_scale())(total_views)),
            hjust = -0.1, size = 3) +
  scale_x_continuous(labels = label_number(scale_cut = cut_short_scale()),
                     expand = expansion(mult = c(0, 0.15))) +
  labs(title = "Top 20 channels by total views (2018–2024)",
       x = "total views", y = NULL)

save_fig(fig4, "fig4_top20_views.png", w = 11, h = 7)

# =========================
# Fig 5 — Per-video engagement distributions (channel medians)
# =========================

ch_pv <- panel |>
  filter(n_videos > 0) |>
  group_by(channel_id, `name.page`) |>
  summarise(
    med_views    = median(viewCount_per_video,    na.rm = TRUE),
    med_likes    = median(likeCount_per_video,    na.rm = TRUE),
    med_comments = median(commentCount_per_video, na.rm = TRUE),
    .groups = "drop"
  ) |>
  pivot_longer(cols = starts_with("med_"),
               names_to = "metric", values_to = "value") |>
  mutate(metric = recode(metric,
    "med_views"    = "Views / video",
    "med_likes"    = "Likes / video",
    "med_comments" = "Comments / video"
  ))

fig5 <- ggplot(ch_pv |> filter(value > 0),
    aes(x = metric, y = value, fill = metric)) +
  geom_violin(alpha = 0.4, colour = NA) +
  geom_boxplot(width = 0.15, outlier.size = 0.8, alpha = 0.8) +
  scale_y_log10(labels = label_number(scale_cut = cut_short_scale())) +
  scale_fill_manual(values = c("Views / video" = "#2C7BB6",
                               "Likes / video" = "#1A9641",
                               "Comments / video" = "#D7191C")) +
  guides(fill = "none") +
  labs(title = "Per-video engagement: channel-level medians",
       subtitle = "Each point = one channel's median over days it published (log scale)",
       x = NULL, y = "median value per video (log scale)")

save_fig(fig5, "fig5_engagement_distributions.png", w = 9, h = 7)

# =========================
# Fig 6 — Publishing heatmap by day-of-week × week-of-year
# =========================

heat_df <- panel |>
  mutate(
    year    = year(date),
    week    = isoweek(date),
    dow     = wday(date, label = TRUE, abbr = TRUE, week_start = 1)
  ) |>
  group_by(year, week, dow) |>
  summarise(n_videos = sum(n_videos, na.rm = TRUE), .groups = "drop")

fig6 <- ggplot(heat_df, aes(x = week, y = fct_rev(dow), fill = n_videos)) +
  geom_tile(colour = "white", linewidth = 0.3) +
  facet_wrap(~year, ncol = 1) +
  scale_fill_distiller(palette = "YlOrRd", direction = 1,
                       labels = comma, name = "videos") +
  scale_x_continuous(breaks = c(1, 13, 26, 39, 52),
                     labels = c("Jan", "Apr", "Jul", "Oct", "Dec")) +
  labs(title = "Publishing frequency heatmap — all channels combined",
       subtitle = "Total videos published by day-of-week and week-of-year",
       x = NULL, y = NULL) +
  theme(strip.text = element_text(face = "bold"),
        panel.spacing.y = unit(4, "pt"),
        legend.position = "bottom")

save_fig(fig6, "fig6_publishing_heatmap.png", w = 13, h = 10)

cat("\nAll done. 7 figures saved to:\n")
cat(sprintf("  %s\n", OUT_FOLDER))

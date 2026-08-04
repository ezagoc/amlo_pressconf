# --- Packages (comments in English) ---
if (!requireNamespace("pacman", quietly = TRUE)) install.packages("pacman")
pacman::p_load(
  arrow, dplyr, lubridate, tibble
)

# --- 1) Read data ---
source("../../project_paths.R")

path <- media_path('data', '02-conferences', 'auxiliar', 'mananeras_playlist.parquet')
yt <- arrow::read_parquet(path) |> as.data.frame() |> tibble::as_tibble()

# --- Helper: force POSIXct in UTC safely ---
to_posix_utc <- function(x) {
  if (inherits(x, "POSIXct")) return(as.POSIXct(x, tz = "UTC"))
  if (inherits(x, "POSIXt"))  return(as.POSIXct(x, tz = "UTC"))
  if (is.numeric(x))         return(as.POSIXct(x, origin = "1970-01-01", tz = "UTC"))
  # character (or anything else coercible)
  suppressWarnings(lubridate::ymd_hms(x, tz = "UTC", quiet = TRUE))
}

# --- 2) Build date ONLY from live_actualStartTime; drop non-live + drop clips ---
yt2 <- yt |>
  transmute(
    videoId,
    title,
    
    # Live start time (must exist)
    live_dt = dplyr::coalesce(
      to_posix_utc(live_actualStartTime_dt),
      to_posix_utc(live_actualStartTime)
    ),
    
    date = as.Date(live_dt),
    
    # Outcomes
    views    = suppressWarnings(as.numeric(viewCount)),
    likes    = suppressWarnings(as.numeric(likeCount)),
    comments = suppressWarnings(as.numeric(commentCount)),
    
    # Duration (seconds)
    duration_seconds = suppressWarnings(as.numeric(duration_seconds))
  ) |>
  filter(
    !is.na(live_dt),
    !is.na(date),
    !is.na(views),
    !is.na(duration_seconds),
    duration_seconds >= 15 * 60
  ) |>
  arrange(date, live_dt) |>
  tibble::as_tibble()

# --- 3) Identify days with multiple videos (diagnostic) ---
day_counts <- yt2 |>
  dplyr::count(date, name = "n_videos")

multi_days <- day_counts |>
  filter(n_videos > 1) |>
  arrange(desc(n_videos), date)

print(multi_days)

# --- 4) Keep ONLY the first live video per day (earliest live_dt) ---
yt_keep <- yt2 |>
  group_by(date) |>
  arrange(live_dt, .by_group = TRUE) |>
  slice(1) |>
  ungroup() |>
  left_join(day_counts, by = "date") |>
  arrange(date)

# --- 5) Videos that appeared AFTER (the ones you want to drop) ---
yt_drop <- yt2 |>
  group_by(date) |>
  arrange(live_dt, .by_group = TRUE) |>
  slice(-1) |>
  ungroup() |>
  left_join(day_counts, by = "date") |>
  arrange(date, live_dt)

print(yt_drop |> select(date, live_dt, videoId, title, n_videos))

# --- 6) Daily dataset (exactly 1 row per day) ---
daily <- yt_keep |> arrange(date)


# --- Packages (comments in English) ---
if (!requireNamespace("pacman", quietly = TRUE)) install.packages("pacman")
pacman::p_load(dplyr, lubridate, ggplot2, scales, slider)

# --- 0) Key date (lottery starts) ---
lottery_date <- as.Date("2022-04-18")

# --- 1) Add pre/post indicator + 14-day rolling mean (smooth + transparent) ---
k <- 7
daily_plot <- daily |>
  mutate(
    period = if_else(date < lottery_date, "Pre (before 2022-04-18)", "Post (after 2022-04-18)"),
    views_roll    = slider::slide_dbl(views,    mean, .before = k - 1, .complete = FALSE, na.rm = TRUE),
    likes_roll    = slider::slide_dbl(likes,    mean, .before = k - 1, .complete = FALSE, na.rm = TRUE),
    comments_roll = slider::slide_dbl(comments, mean, .before = k - 1, .complete = FALSE, na.rm = TRUE)
  )

subtitle <- sprintf(
  "Dots: daily videos. Line: %d-day rolling mean. Dashed line: seat lottery (2022-04-18).",
  k
)


# --- 2) Helper plotting function ---
plot_pretrend <- function(df, y, y_roll, ylab) {
  ggplot(df, aes(x = date)) +
    # raw daily points
    geom_point(aes(y = .data[[y]]), alpha = 0.15, size = 0.8) +
    # rolling mean
    geom_line(aes(y = .data[[y_roll]]), linewidth = 1) +
    # vertical line at lottery date
    geom_vline(xintercept = lottery_date, linetype = "dashed") +
    # pre-period linear fit (visual “declining before”)
    #geom_smooth(
    #  data = df |> filter(date < lottery_date),
    #  aes(y = .data[[y]]),
    #  method = "lm", se = TRUE, linewidth = 0.9
    #) +
    #scale_x_date(date_breaks = "1 year", date_labels = "%Y") +
    scale_y_continuous(labels = scales::comma) +
    labs(
      x = NULL,
      y = ylab,
      title = paste0(ylab, " over time (AMLO Youtube channel)"),
      subtitle = subtitle
    ) +
    theme_minimal(base_size = 12)
}

# --- 3) Plots ---
p_views    <- plot_pretrend(daily_plot, "views",    "views_roll",    "Views")
p_likes    <- plot_pretrend(daily_plot, "likes",    "likes_roll",    "Likes")
p_comments <- plot_pretrend(daily_plot, "comments", "comments_roll", "Comments")

print(p_views)
print(p_likes)
print(p_comments)


# --- Packages for multi-panel output ---
if (!requireNamespace("patchwork", quietly = TRUE)) install.packages("patchwork")
library(patchwork)

# --- X-axis breaks (exact years you asked for) ---
year_breaks <- as.Date(c(
  "2018-01-01", "2019-01-01", "2020-01-01", "2021-01-01",
  "2022-01-01", "2023-01-01", "2024-01-01"
))

# --- Limits for x-axis (so it doesn't zoom weirdly) ---
x_min <- as.Date("2018-01-01")
x_max <- max(daily_plot$date, na.rm = TRUE)

# --- Y-axis breaks/labels exactly as requested ---
views_breaks    <- 1e6 * 1:6                       # 1M ... 6M
likes_breaks    <- c(25000, 50000, 75000, 100000)  # 25k ... 100k
comments_breaks <- c(2000, 4000, 6000, 8000)       # 2k ... 8k

fmt_M <- function(x) paste0(x / 1e6, "M")
fmt_k <- function(x) paste0(x / 1e3, "k")

# --- Clean theme (no background grid) ---
theme_clean <- theme_classic(base_size = 12) +
  theme(
    plot.title = element_text(face = "bold"),
    plot.subtitle = element_text(margin = margin(b = 10)),
    axis.title.x = element_blank()
  )

# --- Generic panel maker (control title + subtitle + x label text only) ---
make_panel <- function(df, y, y_roll, ylab,
                       show_title = FALSE, show_subtitle = FALSE,
                       y_breaks = waiver(), y_labels = waiver()) {
  ggplot(df, aes(x = date)) +
    geom_point(aes(y = .data[[y]]), alpha = 0.15, size = 0.8) +
    geom_line(aes(y = .data[[y_roll]]), linewidth = 1) +
    geom_vline(xintercept = lottery_date, linetype = "dashed") +
    scale_x_date(
      limits = c(x_min, x_max),
      breaks = year_breaks,
      labels = scales::date_format("%Y")
    ) +
    scale_y_continuous(breaks = y_breaks, labels = y_labels) +
    labs(
      x = NULL,
      y = ylab,
      title = if (show_title) "Engagement over time (AMLO YouTube channel)" else NULL,
      subtitle = if (show_subtitle) subtitle else NULL
    ) +
    theme_clean
}

# --- Build panels (years ticks in ALL; year labels ONLY in comments) ---
p_views <- make_panel(daily_plot, "views", "views_roll", "Views",
                      show_title = TRUE, show_subtitle = TRUE,
                      y_breaks = views_breaks, y_labels = fmt_M)

p_likes <- make_panel(daily_plot, "likes", "likes_roll", "Likes",
                      y_breaks = likes_breaks, y_labels = fmt_k)

p_comments <- make_panel(daily_plot, "comments", "comments_roll", "Comments",
                         y_breaks = comments_breaks, y_labels = fmt_k)


# --- Combine side-by-side ---
p_all <- p_views | p_likes | p_comments

# --- Save to working directory ---
out_file <- sprintf("engagement_three_panels_side_by_side_k%d.png", k)
ggsave(filename = out_file, plot = p_all, width = 14, height = 4.8, dpi = 300)

print(p_all)
cat("Saved figure to:", file.path(getwd(), out_file), "\n")

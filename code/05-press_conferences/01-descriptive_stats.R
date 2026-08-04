# 0.0 Set up the environment
rm(list = ls())
if (requireNamespace("rstudioapi", quietly = TRUE) && rstudioapi::isAvailable()) {
  setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
} else {
  setwd(getwd())
}
source("../../project_paths.R")

library(arrow)
library(tidyverse)
library(lubridate)
library(scales)
library(patchwork)

path_da  <- paste0(media_path('data', '02-conferences', 'raw', 'attendance'), '/')
fig_path <- paste0(path_da, 'figures/')
dir.create(fig_path, showWarnings = FALSE, recursive = TRUE)

# ─────────────────────────────────────────────────────────────────────────────
# 0.1  Read data
# ─────────────────────────────────────────────────────────────────────────────
panel <- read_parquet(paste0(path_da, 'panel_attendance.parquet.gzip'))

panel <- panel |>
  mutate(fecha = as.Date(fecha))

lottery_date <- as.Date("2022-04-12")

# ─────────────────────────────────────────────────────────────────────────────
# 0.2  Helper functions
# ─────────────────────────────────────────────────────────────────────────────
my_theme <- function() {
  theme_minimal() +
    theme(
      plot.title    = element_text(hjust = 0.5, face = "bold"),
      plot.subtitle = element_text(hjust = 0.5),
      axis.text.x   = element_text(angle = 45, hjust = 1)
    )
}

save_plot <- function(p, filename, w = 12, h = 7) {
  print(p)
  ggsave(paste0(fig_path, filename), plot = p, width = w, height = h, dpi = 150)
}

# ─────────────────────────────────────────────────────────────────────────────
# 1. TIME SERIES: CONFERENCE-LEVEL ATTENDANCE
# ─────────────────────────────────────────────────────────────────────────────

# Collapse to one row per conference date
conf_daily <- panel |>
  distinct(fecha, n_total_attend, n_reporteros, n_youtubers) |>
  arrange(fecha)

# 1a. Daily total attendance over time
p1a <- ggplot(conf_daily, aes(fecha, n_total_attend)) +
  geom_line(colour = "steelblue", linewidth = 0.4, alpha = 0.7) +
  geom_smooth(method = "loess", span = 0.15, colour = "firebrick",
              se = FALSE, linewidth = 0.9) +
  geom_vline(xintercept = lottery_date, linetype = "dashed",
             colour = "firebrick", linewidth = 0.7) +
  annotate("text", x = lottery_date + 30, y = max(conf_daily$n_total_attend, na.rm = TRUE) * 0.95,
           label = "Lottery cutoff\n(2022-04-12)", colour = "firebrick",
           hjust = 0, size = 3) +
  scale_x_date(date_breaks = "1 year", date_labels = "%Y") +
  scale_y_continuous(labels = comma) +
  labs(title = "Daily Total Attendance at Mañaneras",
       x = NULL, y = "Total attendees") +
  my_theme()

# 1b. Monthly average attendance
conf_monthly <- conf_daily |>
  mutate(month_date = floor_date(fecha, "month")) |>
  group_by(month_date) |>
  summarise(avg_attend = mean(n_total_attend, na.rm = TRUE), .groups = "drop")

p1b <- ggplot(conf_monthly, aes(month_date, avg_attend)) +
  geom_line(colour = "steelblue", linewidth = 0.8) +
  geom_point(colour = "steelblue", size = 1.5) +
  geom_vline(xintercept = lottery_date, linetype = "dashed",
             colour = "firebrick", linewidth = 0.7) +
  scale_x_date(date_breaks = "1 year", date_labels = "%Y") +
  scale_y_continuous(labels = comma) +
  labs(title = "Monthly Average Attendance",
       x = NULL, y = "Avg. attendees") +
  my_theme()

# 1c. Reporter vs YouTuber count over time (monthly)
conf_monthly_types <- conf_daily |>
  mutate(month_date = floor_date(fecha, "month")) |>
  group_by(month_date) |>
  summarise(
    Reporters  = mean(n_reporteros, na.rm = TRUE),
    YouTubers  = mean(n_youtubers,  na.rm = TRUE),
    .groups = "drop"
  ) |>
  pivot_longer(c(Reporters, YouTubers), names_to = "type", values_to = "avg_count")

p1c <- ggplot(conf_monthly_types, aes(month_date, avg_count, colour = type)) +
  geom_line(linewidth = 0.8) +
  geom_vline(xintercept = lottery_date, linetype = "dashed",
             colour = "firebrick", linewidth = 0.7) +
  scale_x_date(date_breaks = "1 year", date_labels = "%Y") +
  scale_y_continuous(labels = comma) +
  scale_colour_manual(values = c("Reporters" = "steelblue", "YouTubers" = "darkorange")) +
  labs(title = "Monthly Avg. Reporters vs YouTubers",
       x = NULL, y = "Avg. count", colour = NULL) +
  my_theme()

fig1 <- (p1a / p1b / p1c) +
  plot_annotation(
    title = "Conference Attendance Over Time",
    theme = theme(plot.title = element_text(hjust = 0.5, face = "bold"))
  )

save_plot(fig1, "01_conference_attendance_timeseries.png", w = 12, h = 16)

# ─────────────────────────────────────────────────────────────────────────────
# 2. OUTLET-LEVEL ATTENDANCE RATE
# ─────────────────────────────────────────────────────────────────────────────

n_conferences_total <- n_distinct(panel$fecha)
n_conf_bef          <- panel |> filter(fecha < lottery_date)  |> distinct(fecha) |> nrow()
n_conf_aft          <- panel |> filter(fecha >= lottery_date) |> distinct(fecha) |> nrow()

outlet_rates <- panel |>
  group_by(outlet_final) |>
  summarise(
    total_att  = sum(attended, na.rm = TRUE),
    att_bef    = sum(attended[fecha < lottery_date],  na.rm = TRUE),
    att_aft    = sum(attended[fecha >= lottery_date], na.rm = TRUE),
    .groups    = "drop"
  ) |>
  mutate(
    rate_total = total_att / n_conferences_total,
    rate_bef   = att_bef  / n_conf_bef,
    rate_aft   = att_aft  / n_conf_aft
  )

# 2a. Top 30 outlets by total attendance
top30 <- outlet_rates |>
  slice_max(total_att, n = 30) |>
  mutate(outlet_final = fct_reorder(outlet_final, total_att))

p2a <- ggplot(top30, aes(total_att, outlet_final)) +
  geom_col(fill = "steelblue") +
  scale_x_continuous(labels = comma) +
  labs(title = "Top 30 Outlets by Total Conferences Attended",
       x = "Total conferences attended", y = NULL) +
  my_theme() +
  theme(axis.text.x = element_text(angle = 45, hjust = 1))

save_plot(p2a, "02a_top30_outlets.png", w = 11, h = 9)

# 2b. Before vs after lottery scatter
p2b <- ggplot(outlet_rates, aes(rate_bef, rate_aft)) +
  geom_point(colour = "steelblue", alpha = 0.5, size = 1.8) +
  geom_abline(slope = 1, intercept = 0, linetype = "dashed", colour = "grey40") +
  scale_x_continuous(labels = percent_format(accuracy = 1), limits = c(0, 1)) +
  scale_y_continuous(labels = percent_format(accuracy = 1), limits = c(0, 1)) +
  labs(title = "Outlet Attendance Rate: Pre vs Post Lottery",
       subtitle = "Dashed line = no change; points above = more attendance after lottery",
       x = "Attendance rate before 2022-04-12",
       y = "Attendance rate from 2022-04-12") +
  my_theme()

save_plot(p2b, "02b_lottery_scatter.png", w = 9, h = 8)

# 2c. Distribution of attendance rates (pre vs post)
rates_long <- outlet_rates |>
  select(outlet_final, rate_bef, rate_aft) |>
  pivot_longer(c(rate_bef, rate_aft),
               names_to  = "period",
               values_to = "rate") |>
  mutate(period = recode(period,
                         rate_bef = "Pre-lottery (before 2022-04-12)",
                         rate_aft = "Post-lottery (from 2022-04-12)"))

p2c <- ggplot(rates_long, aes(rate, fill = period)) +
  geom_density(alpha = 0.4, colour = NA) +
  scale_x_continuous(labels = percent_format(accuracy = 1), limits = c(0, 1)) +
  scale_fill_manual(values = c("Pre-lottery (before 2022-04-12)"  = "steelblue",
                               "Post-lottery (from 2022-04-12)" = "darkorange")) +
  labs(title = "Distribution of Outlet Attendance Rates",
       x = "Attendance rate", y = "Density", fill = NULL) +
  my_theme()

save_plot(p2c, "02c_rate_distribution.png", w = 10, h = 6)

# ─────────────────────────────────────────────────────────────────────────────
# 3. COMPOSITION OVER TIME
# ─────────────────────────────────────────────────────────────────────────────

# 3a. Share of YouTubers vs reporters per conference (monthly stacked area)
composition_monthly <- conf_daily |>
  mutate(month_date = floor_date(fecha, "month")) |>
  group_by(month_date) |>
  summarise(
    reporters = sum(n_reporteros, na.rm = TRUE),
    youtubers = sum(n_youtubers,  na.rm = TRUE),
    .groups   = "drop"
  ) |>
  mutate(total = reporters + youtubers) |>
  filter(total > 0) |>
  mutate(
    share_reporters = reporters / total,
    share_youtubers = youtubers / total
  ) |>
  select(month_date, share_reporters, share_youtubers) |>
  pivot_longer(c(share_reporters, share_youtubers),
               names_to  = "type",
               values_to = "share") |>
  mutate(type = recode(type,
                       share_reporters = "Reporters",
                       share_youtubers = "YouTubers"))

p3a <- ggplot(composition_monthly, aes(month_date, share, fill = type)) +
  geom_area(alpha = 0.8) +
  geom_vline(xintercept = lottery_date, linetype = "dashed",
             colour = "firebrick", linewidth = 0.7) +
  scale_x_date(date_breaks = "1 year", date_labels = "%Y") +
  scale_y_continuous(labels = percent_format(accuracy = 1)) +
  scale_fill_manual(values = c("Reporters" = "steelblue", "YouTubers" = "darkorange")) +
  labs(title = "Monthly Share: Reporters vs YouTubers",
       x = NULL, y = "Share of attendees", fill = NULL) +
  my_theme()

# 3b. Number of unique outlets per conference (monthly)
outlets_monthly <- panel |>
  filter(attended == 1) |>
  mutate(month_date = floor_date(fecha, "month")) |>
  group_by(month_date, fecha) |>
  summarise(n_outlets = n_distinct(outlet_final), .groups = "drop") |>
  group_by(month_date) |>
  summarise(avg_outlets = mean(n_outlets, na.rm = TRUE), .groups = "drop")

p3b <- ggplot(outlets_monthly, aes(month_date, avg_outlets)) +
  geom_line(colour = "steelblue", linewidth = 0.8) +
  geom_point(colour = "steelblue", size = 1.5) +
  geom_vline(xintercept = lottery_date, linetype = "dashed",
             colour = "firebrick", linewidth = 0.7) +
  annotate("text", x = lottery_date + 30, y = max(outlets_monthly$avg_outlets, na.rm = TRUE) * 0.95,
           label = "Lottery cutoff", colour = "firebrick", hjust = 0, size = 3) +
  scale_x_date(date_breaks = "1 year", date_labels = "%Y") +
  scale_y_continuous(labels = comma) +
  labs(title = "Avg. Unique Outlets per Conference (Monthly)",
       x = NULL, y = "Avg. outlets") +
  my_theme()

fig3 <- (p3a / p3b) +
  plot_annotation(
    title = "Composition of Press Conference Attendance Over Time",
    theme = theme(plot.title = element_text(hjust = 0.5, face = "bold"))
  )

save_plot(fig3, "03_composition_timeseries.png", w = 12, h = 12)

# ─────────────────────────────────────────────────────────────────────────────
# 4. SUMMARY STATISTICS TABLE
# ─────────────────────────────────────────────────────────────────────────────
stat_cols <- c("n_journalists", "attended", "n_total_attend",
               "n_reporteros", "n_youtubers",
               "total_attendance", "attendance_bef", "attendance_after")

summary_tbl <- panel |>
  select(all_of(stat_cols)) |>
  pivot_longer(everything(), names_to = "variable") |>
  group_by(variable) |>
  summarise(
    n      = sum(!is.na(value)),
    n_miss = sum(is.na(value)),
    mean   = mean(value,              na.rm = TRUE),
    sd     = sd(value,                na.rm = TRUE),
    min    = min(value,               na.rm = TRUE),
    p25    = quantile(value, 0.25,    na.rm = TRUE),
    median = median(value,            na.rm = TRUE),
    p75    = quantile(value, 0.75,    na.rm = TRUE),
    max    = max(value,               na.rm = TRUE),
    .groups = "drop"
  )

print(summary_tbl)
write_csv(summary_tbl, paste0(path_da, 'descriptive_stats_summary.csv'))

message("Done. Figures saved to: ", fig_path)

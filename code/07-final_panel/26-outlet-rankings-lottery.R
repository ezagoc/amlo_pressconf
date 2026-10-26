# Outlet rankings and the distribution of question-days per attendance-day.
# Read-only source data; all outputs live in output/desc_stats.
script_arg <- grep("^--file=", commandArgs(FALSE), value = TRUE)
script_path <- if (length(script_arg)) sub("^--file=", "", script_arg[[1]]) else
  file.path(getwd(), "code/07-final_panel/26-outlet-rankings-lottery.R")
root <- normalizePath(file.path(dirname(script_path), "../.."), mustWork = TRUE)
distribution_only <- "--distribution-only" %in% commandArgs(TRUE)
source(file.path(root, "project_paths.R"))
source(file.path(root, "src/final_panel_helpers.R"))
suppressPackageStartupMessages({
  library(arrow); library(dplyr); library(tidyr); library(readr)
  library(stringr); library(lubridate); library(ggplot2); library(patchwork)
})
out <- file.path(root, "output/desc_stats")
audit <- file.path(out, "outlet_lottery_tables")
dir.create(audit, recursive = TRUE, showWarnings = FALSE)
lottery <- as.Date("2022-04-18")
start <- lottery %m-% years(1)
end <- lottery %m+% years(1) - days(1)
periods <- c("Before lottery", "After lottery")
period_of <- function(x) factor(if_else(x < lottery, periods[1], periods[2]), levels = periods)
bad_attendance_month <- function(x) format(x, "%Y-%m") == "2021-11"
paths <- c(
  a = media_path("data/02-conferences/raw/attendance/merged/attendance_clean.parquet"),
  q = media_path("data/02-conferences/auxiliar/questions_dataset.parquet"),
  q_names = media_path("data/02-conferences/auxiliar/questions_dataset_dedup.parquet"),
  m = media_path("data/00-newspaper_data/processed/newspaper_metadata_geocoded.parquet")
)
hashes <- tools::md5sum(paths)
a <- read_parquet(paths[["a"]]) |>
  mutate(date = as.Date(fecha), a_id = normalize_panel_key(outlet_final))
if (!"attendance_assumed" %in% names(a)) a$attendance_assumed <- FALSE
q_all <- read_parquet(paths[["q"]]) |> distinct() |> mutate(date = as.Date(date))
q_names <- read_parquet(paths[["q_names"]]) |> mutate(date = as.Date(date))
m <- read_parquet(paths[["m"]]) |>
  mutate(a_id = normalize_panel_key(names.conference), q_id = normalize_panel_key(names.transcripts))
key <- c("date", "reporter", "outlet", "turn_index", "item_index", "item_type", "text")
name_map <- q_names |>
  select(all_of(key), clean_outlet = outlet_aux, clean_reporter = reporter_aux) |> distinct()
stopifnot(!anyDuplicated(name_map[key]), !anyDuplicated(q_all[key]))
q <- q_all |> left_join(name_map, by = key, relationship = "one-to-one") |>
  filter(item_type %in% c("pregunta", "question")) |>
  mutate(q_id = normalize_panel_key(clean_outlet),
    reporter_id = normalize_panel_key(coalesce(clean_reporter, reporter_aux)))

# Many question IDs may map to one attendance ID, never vice versa. Metadata
# duplicates cannot multiply counts. Add exact normalized source-name matches
# only when metadata supplies no mapping; no fuzzy matching is performed.
links_meta <- m |> filter(!is.na(a_id), !is.na(q_id)) |> distinct(a_id, q_id)
stopifnot(!anyDuplicated(links_meta$q_id))
links_exact <- tibble(q_id = intersect(na.omit(a$a_id), na.omit(q$q_id))) |>
  anti_join(links_meta, by = "q_id") |> mutate(a_id = q_id)
links <- bind_rows(mutate(links_meta, match_method = "metadata"),
                    mutate(links_exact, match_method = "exact source name"))
stopifnot(!anyDuplicated(links$q_id))
q <- q |> left_join(links, by = "q_id", relationship = "many-to-one") |>
  mutate(unit_id = if_else(!is.na(a_id), paste0("a:", a_id), paste0("q:", q_id)),
         unit_id = if_else(is.na(q_id), NA_character_, unit_id))
a <- a |> mutate(unit_id = if_else(is.na(a_id), NA_character_, paste0("a:", a_id)))

# Human-readable names, never URL labels. Shared IDs retain the source's group
# name rather than being relabeled as an arbitrary subsidiary.
pretty_name <- function(x) {
  x <- str_to_title(x)
  replacements <- c("Sdp" = "SDP", "Spr" = "SPR", "Tv" = "TV", "Epme" = "EPME",
    "Oem" = "OEM", "Efe" = "EFE", "Mvs" = "MVS", "Mmm" = "MMM", "Cnn" = "CNN")
  for (word in names(replacements)) x <- str_replace_all(x, paste0("\\b", word, "\\b"), replacements[[word]])
  x <- str_replace_all(x, "\\b(De|Del|La|El|En|Y)\\b", function(z) str_to_lower(z))
  str_replace(x, "^.", function(z) str_to_upper(z))
}
meta_names <- m |> filter(!is.na(a_id)) |> group_by(a_id) |>
  summarise(n_names = n_distinct(name.page, na.rm = TRUE),
    metadata_name = first(na.omit(name.page)), source_name = first(na.omit(names.conference)),
    .groups = "drop")
roster_a <- a |> filter(!is.na(a_id)) |> distinct(unit_id, a_id) |>
  left_join(meta_names, by = "a_id", relationship = "many-to-one") |>
  mutate(outlet_name = case_when(n_names == 1 ~ metadata_name,
    !is.na(source_name) ~ pretty_name(source_name), TRUE ~ pretty_name(a_id))) |>
  select(unit_id, outlet_name)
roster_q <- q |> filter(!is.na(unit_id)) |> distinct(unit_id, q_id) |>
  anti_join(roster_a, by = "unit_id") |> group_by(unit_id) |>
  summarise(outlet_name = pretty_name(first(q_id)), .groups = "drop")
roster <- bind_rows(roster_a, roster_q)
stopifnot(!anyDuplicated(roster$unit_id), !anyNA(roster$outlet_name),
  !any(str_detect(roster$outlet_name, "https?://|www\\.")))
a_dates <- sort(unique(a$date[between(a$date, start, end) & !bad_attendance_month(a$date)]))
q_dates <- sort(unique(q_all$date[between(q_all$date, start, end)]))
common_dates <- intersect(a_dates, q_dates) |> as.Date(origin = "1970-01-01")
a_daily <- a |> filter(between(date, start, end), !is.na(unit_id), !bad_attendance_month(date)) |>
  group_by(unit_id, date) |>
  summarise(attendance_recorded = sum(!attendance_assumed),
    attendance_assigned = sum(attendance_assumed), .groups = "drop")
q_daily <- q |> filter(between(date, start, end), !is.na(unit_id)) |>
  group_by(unit_id, date) |> summarise(questions = n(),
    reporters = n_distinct(reporter_id, na.rm = TRUE), .groups = "drop") |>
  # Even an unidentified questioner establishes at least one attendance.
  mutate(attendance_lower_bound = pmax(1L, reporters))
daily <- full_join(a_daily, q_daily, by = c("unit_id", "date"), relationship = "one-to-one") |>
  mutate(attendance_recorded = coalesce(attendance_recorded, 0L),
    attendance_assigned = coalesce(attendance_assigned, 0L),
    questions = coalesce(questions, 0L), attendance_lower_bound = coalesce(attendance_lower_bound, 0L),
    attendance = pmax(attendance_recorded + attendance_assigned, attendance_lower_bound), period = period_of(date))
stopifnot(sum(q_daily$questions) == sum(between(q$date, start, end) & !is.na(q$unit_id)),
  sum(a_daily$attendance_recorded) + sum(a_daily$attendance_assigned) ==
    sum(between(a$date, start, end) & !is.na(a$unit_id) & !bad_attendance_month(a$date)))

# Rankings use all available dates for each source, not only the ratio sample.
# Question rankings count distinct outlet-days with any question, not items.
# Attendance corrections are applied only on dates with a recorded list.
totals <- bind_rows(
  daily |> filter(date %in% a_dates) |> group_by(unit_id, period) |>
    summarise(value = sum(attendance), .groups = "drop") |> mutate(metric = "Journalist attendance"),
  daily |> group_by(unit_id, period) |> summarise(value = sum(questions > 0), .groups = "drop") |>
    mutate(metric = "Days asking a question")
) |> left_join(roster, by = "unit_id", relationship = "many-to-one")
question_day_check <- q |> filter(between(date, start, end), !is.na(unit_id)) |>
  distinct(unit_id, date) |> mutate(period = period_of(date)) |>
  count(unit_id, period, name = "expected_days")
stopifnot(!anyDuplicated(daily[c("unit_id", "date")]))
stopifnot(all((totals |> filter(metric == "Days asking a question") |>
  left_join(question_day_check, by = c("unit_id", "period"), relationship = "one-to-one") |>
  mutate(valid = value == coalesce(expected_days, 0L)))$valid))
top <- totals |> filter(value > 0) |> group_by(metric, period) |>
  arrange(desc(value), outlet_name, .by_group = TRUE) |> slice_head(n = 10) |> ungroup()
stopifnot(nrow(top) == 40, !anyNA(top$outlet_name))
palette <- setNames(c("#315B77", "#8E3B46"), periods)
base_theme <- theme_minimal(base_size = 11, base_family = "sans") + theme(
  panel.grid.minor = element_blank(), plot.title = element_text(face = "bold", size = 12),
  axis.title = element_text(size = 10), axis.text = element_text(size = 9),
  plot.margin = margin(10, 18, 8, 8))
rank_plot <- function(metric_name, period_name) {
  df <- top |> filter(metric == metric_name, period == period_name) |>
    arrange(value, desc(outlet_name)) |> mutate(outlet_name = factor(outlet_name, levels = unique(outlet_name)))
  upper <- max(top$value[top$metric == metric_name]) * 1.18
  ggplot(df, aes(value, outlet_name)) +
    geom_col(fill = palette[[period_name]], width = .62) +
    geom_text(aes(label = scales::comma(value)), hjust = -.2, size = 3.1, color = "#303030") +
    scale_x_continuous(limits = c(0, upper), labels = scales::label_comma(), expand = expansion(mult = c(0, 0))) +
    scale_y_discrete(labels = function(x) str_wrap(x, 25)) +
    labs(title = paste(metric_name, "|", period_name),
      x = if (metric_name == "Days asking a question") "Days with at least one question" else "Journalist attendance records",
      y = NULL) +
    base_theme + theme(panel.grid.major.y = element_blank())
}
ranking <- (rank_plot("Journalist attendance", periods[1]) | rank_plot("Journalist attendance", periods[2])) /
  (rank_plot("Days asking a question", periods[1]) | rank_plot("Days asking a question", periods[2]))
if (!distribution_only && "--legacy-count-rankings" %in% commandArgs(TRUE)) {
  ggsave(file.path(out, "top10_outlets_before_after_lottery.pdf"), ranking,
    width = 12, height = 9, device = "pdf")
}

# Distribution: common source-covered dates; fixed roster with positive
# attendance in BOTH periods. Retain zero-question outlets. The numerator and
# denominator cover exactly the same dates. One observation per outlet-period.
# Both components are binary at outlet-date level: a question implies attendance.
eligible <- roster_a |> filter(unit_id %in% paste0("a:", links$a_id)) |> select(unit_id)
ratio_daily <- daily |> filter(date %in% common_dates) |> semi_join(eligible, by = "unit_id") |>
  transmute(unit_id, date, period, asked = as.integer(questions > 0),
    attended_recorded = as.integer(attendance_recorded > 0),
    attended_assigned = as.integer(attendance_assigned > 0),
    attended = as.integer(attendance_recorded > 0 | attendance_assigned > 0 | questions > 0))
stopifnot(!anyDuplicated(ratio_daily[c("unit_id", "date")]),
  all(ratio_daily$asked <= ratio_daily$attended),
  all(ratio_daily$asked %in% 0:1), all(ratio_daily$attended %in% 0:1))
ratio_all <- ratio_daily |>
  group_by(unit_id, period) |> summarise(question_days = sum(asked),
    attendance_days = sum(attended), recorded_attendance_days = sum(attended_recorded),
    assigned_attendance_days = sum(attended_assigned), .groups = "drop") |>
  complete(unit_id, period, fill = list(question_days = 0L, attendance_days = 0L,
    recorded_attendance_days = 0L, assigned_attendance_days = 0L))
cohort <- ratio_all |> group_by(unit_id) |> summarise(keep = all(attendance_days > 0), .groups = "drop") |>
  filter(keep) |> select(unit_id)
ratios <- ratio_all |> semi_join(cohort, by = "unit_id") |>
  mutate(ratio = question_days / attendance_days) |>
  left_join(roster, by = "unit_id", relationship = "many-to-one")
stopifnot(nrow(ratios) == 2 * nrow(cohort), all(is.finite(ratios$ratio)),
  all(between(ratios$ratio, 0, 1)))
gini <- function(x) {
  x <- sort(x); n <- length(x)
  if (!n || sum(x) == 0) return(NA_real_)
  sum((2 * seq_len(n) - n - 1) * x) / (n * sum(x))
}
summarize_ratios <- function(df) df |> group_by(period) |> summarise(
  outlets = n(), mean = mean(ratio), median = median(ratio), sd = sd(ratio),
  coefficient_of_variation = sd(ratio) / mean(ratio), gini = gini(ratio),
  zero_question_outlets = sum(question_days == 0), attendance_days = sum(attendance_days),
  question_days = sum(question_days), pooled_question_day_share = question_days / attendance_days, .groups = "drop")
stats <- summarize_ratios(ratios)
# A prespecified support sensitivity, not a replacement for the main sample.
frequent <- ratio_all |> group_by(unit_id) |> summarise(keep = all(attendance_days >= 10), .groups = "drop") |>
  filter(keep) |> select(unit_id)
stats_frequent <- ratios |> semi_join(frequent, by = "unit_id") |> summarize_ratios()
bin_width <- .05
breaks <- seq(0, 1, by = bin_width)
annotations <- stats |> mutate(label = sprintf("%s outlets\nMedian: %.1f%%", outlets, 100 * median))
# Explicit shares normalize within each facet, not across the entire figure.
binned <- ratios |> mutate(bin = cut(ratio, breaks = breaks, include.lowest = TRUE, right = TRUE)) |>
  count(period, bin, .drop = FALSE) |> group_by(period) |> mutate(share = n / sum(n)) |> ungroup() |>
  mutate(midpoint = (breaks[as.integer(bin)] + breaks[as.integer(bin) + 1L]) / 2)
stopifnot(all(abs((binned |> group_by(period) |> summarise(total = sum(share)))$total - 1) < 1e-10))
distribution <- ggplot(binned, aes(midpoint, share, fill = period)) +
  geom_col(width = bin_width, color = "white", linewidth = .3, show.legend = FALSE) +
  geom_vline(data = stats, aes(xintercept = median, color = period),
    linetype = "dashed", linewidth = .6, show.legend = FALSE) +
  geom_text(data = annotations, aes(x = Inf, y = Inf, label = label),
    inherit.aes = FALSE, hjust = 1.1, vjust = 1.3, lineheight = 1.25, size = 3.5, color = "#303030") +
  facet_wrap(vars(period), nrow = 1) + scale_fill_manual(values = palette) + scale_color_manual(values = palette) +
  scale_x_continuous(limits = c(0, 1), breaks = seq(0, 1, by = .2),
    labels = scales::label_percent(accuracy = 1), expand = expansion(mult = c(0, .02))) +
  scale_y_continuous(labels = scales::label_percent(accuracy = 1), expand = expansion(mult = c(0, .12))) +
  labs(x = "Share of attended days with at least one question", y = "Share of outlets") +
  base_theme + theme(strip.text = element_text(face = "bold", size = 12),
    panel.grid.major.x = element_blank(), panel.spacing.x = unit(1.2, "lines"))
ggsave(file.path(out, "questions_per_attendance_distribution_before_after_lottery.pdf"),
  distribution, width = 10, height = 4.5, device = "pdf")

coverage <- tibble(date = sort(unique(c(a_dates, q_dates)))) |> mutate(period = period_of(date),
  attendance_observed = date %in% a_dates, question_extraction_observed = date %in% q_dates,
  common_date = date %in% common_dates) |> group_by(period) |> summarise(
    attendance_dates = sum(attendance_observed), extraction_dates = sum(question_extraction_observed),
    common_dates = sum(common_date), .groups = "drop")
for (nm in c("top", "totals", "links", "roster", "ratios", "ratio_all", "ratio_daily", "stats", "stats_frequent", "coverage"))
  write_csv(get(nm), file.path(audit, paste0(nm, ".csv")))
writeLines(c(
  paste("Window:", start, "to", end, "; lottery:", lottery),
  "Before: 2021-04-18 through 2022-04-17. After: 2022-04-18 through 2023-04-17.",
  "Rankings use full-source data, not only metadata/YouTube matches. Exactly duplicated question items removed.",
  "Questions include pregunta and question items. Unknown outlet questions excluded from outlet ranks.",
  "Question rankings count outlet-days with at least one question: multiple question items, reporters or linked IDs on the same day count once.",
  "Attendance RANKINGS count journalist attendance records, NOT distinct people or binary outlet-date visits.",
  "User-specified co-affiliation: The Mexico News receives one assumed attendance on each Sin Censura date unless already recorded. Sin Censura remains unchanged; this does not imply another physical attendee.",
  "ratio_daily.csv and ratios.csv distinguish recorded attendance from assigned co-affiliation attendance. The denominator includes both and the question-based lower bound.",
  "Attendance is raised to the number of distinct identified questioners if higher, with a minimum of one when questions exist.",
  "Ranked attendance uses dates with attendance lists, excluding November 2021. Questions retain November 2021.",
  "Ratio sample uses only dates observed in both sources, excluding November 2021 from numerator AND denominator.",
  "Ratios = days with at least one question / days with at least one attendance on these common dates.",
  "For the distribution, both counts are binary per outlet-day; any question-day is also an attendance-day. Ratios lie between zero and one.",
  "Same linked outlet roster before and after; positive attendance in both periods; zero questions retained.",
  "Links use metadata or exact normalized source names. Multiple question IDs sharing attendance ID are combined before merging.",
  "Shared metadata subsidiary IDs counted once. Shared entities retain their source group name, not an arbitrary subsidiary label.",
  "Outlets without a reliable cross-source link are omitted from ratios, but can appear in rankings.",
  "Histogram bins have width 0.05 (five percentage points), equal outlet weights, common axes; dashed lines mark medians.",
  "Lower Gini/CV indicates greater equality of outlet question-to-attendance rates, not a flatter histogram.",
  "Descriptive only: incomplete extraction, attendance reporting and period changes prevent a causal lottery interpretation.",
  "stats_frequent.csv repeats summaries requiring at least ten attendance DAYS in BOTH periods.",
  paste("Question items with unknown outlet in window:", sum(between(q$date, start, end) & is.na(q$unit_id))),
  paste("Attendance records added by correction on ranked dates:", sum(daily$attendance - daily$attendance_recorded,
    na.rm = TRUE) - sum((daily$attendance - daily$attendance_recorded)[!daily$date %in% a_dates], na.rm = TRUE))
), file.path(audit, "README.txt"))
stopifnot(identical(hashes, tools::md5sum(paths)))
print(top |> select(metric, period, outlet_name, value), n = 40)
print(stats, width = 180)
print(stats_frequent, width = 180)
print(coverage)

# Run after 26-outlet-rankings-lottery.R. Replaces count-based top-10 figures
# with named high-ratio outlets and the largest increases AND decreases.
script_arg <- grep("^--file=", commandArgs(FALSE), value = TRUE)
script_path <- if (length(script_arg)) sub("^--file=", "", script_arg[[1]]) else
  file.path(getwd(), "code/07-final_panel/27-ratio-distributions-top10-changes.R")
root <- normalizePath(file.path(dirname(script_path), "../.."), mustWork = TRUE)
changes_only <- "--changes-only" %in% commandArgs(TRUE)
source(file.path(root, "project_paths.R"))
suppressPackageStartupMessages({
  library(dplyr); library(tidyr); library(readr); library(stringr)
  library(ggplot2); library(patchwork)
})
out <- file.path(root, "output/desc_stats")
audit <- file.path(out, "outlet_lottery_tables")
periods <- c("Before lottery", "After lottery")
palette <- setNames(c("#315B77", "#8E3B46"), periods)
ratios <- read_csv(file.path(audit, "ratios.csv"), show_col_types = FALSE) |>
  mutate(period = factor(period, levels = periods))
stopifnot(!anyDuplicated(ratios[c("unit_id", "period")]),
  all(is.finite(ratios$ratio)), all(between(ratios$ratio, 0, 1)))

# Descriptive change rankings, not causal estimates. Apply the same sample and
# selection size in both directions; retain counts to expose small denominators.
before <- ratios |> filter(period == periods[1]) |>
  transmute(unit_id, outlet_name, ratio_before = ratio,
    questions_before = question_days, attendance_before = attendance_days)
after <- ratios |> filter(period == periods[2]) |>
  transmute(unit_id, ratio_after = ratio,
    questions_after = question_days, attendance_after = attendance_days)
changes <- inner_join(before, after, by = "unit_id", relationship = "one-to-one") |>
  mutate(change_pp = 100 * (ratio_after - ratio_before),
    before_label = sprintf("%.1f%% (%d/%d)", 100 * ratio_before, questions_before, attendance_before),
    after_label = sprintf("%.1f%% (%d/%d)", 100 * ratio_after, questions_after, attendance_after),
    change_label = sprintf("%+.1f", change_pp))
rank_changes <- function(changes) {
decreases <- changes |> filter(change_pp < 0) |>
  arrange(change_pp, desc(attendance_before + attendance_after), outlet_name, unit_id) |>
  slice_head(n = 10) |> mutate(direction = "Largest decreases", rank = row_number(), y = 11 - rank)
increases <- changes |> filter(change_pp > 0) |>
  arrange(desc(change_pp), desc(attendance_before + attendance_after), outlet_name, unit_id) |>
  slice_head(n = 10) |> mutate(direction = "Largest increases", rank = row_number(), y = 11 - rank)
top_changes <- bind_rows(decreases, increases)
stopifnot(nrow(decreases) <= 10L, nrow(increases) <= 10L,
  !anyDuplicated(top_changes$unit_id))
list(decreases = decreases, increases = increases, top = top_changes)
}
ranked <- rank_changes(changes)
stopifnot(
  all(abs(changes$ratio_before - changes$questions_before / changes$attendance_before) < 1e-12),
  all(abs(changes$ratio_after - changes$questions_after / changes$attendance_after) < 1e-12))
write_csv(ranked$top |> select(-y), file.path(audit, "top10_increases_decreases.csv"))

base_theme <- theme_minimal(base_size = 11, base_family = "sans") + theme(
  panel.grid.minor = element_blank(), axis.title = element_text(size = 10),
  axis.text = element_text(size = 10), plot.title = element_text(size = 12, face = "bold"),
  plot.margin = margin(9, 10, 9, 10))
make_distribution <- function(ratios, group = NULL, y_max = NULL) {
stats <- ratios |> group_by(period) |>
  summarise(outlets = n_distinct(unit_id), median = median(ratio), .groups = "drop")
breaks <- seq(0, 1, by = .05)
binned <- ratios |>
  mutate(bin = cut(ratio, breaks = breaks, include.lowest = TRUE, right = TRUE)) |>
  count(period, bin, .drop = FALSE) |> group_by(period) |>
  mutate(share = n / sum(n)) |> ungroup() |>
  mutate(midpoint = (breaks[as.integer(bin)] + breaks[as.integer(bin) + 1L]) / 2)
# "Outlier" labels use the explicitly stated >=40% descriptive threshold,
# not a statistical outlier test. Stagger names vertically for legibility.
high_ratios <- ratios |> filter(ratio >= .4) |>
  mutate(bin = cut(ratio, breaks = breaks, include.lowest = TRUE, right = TRUE)) |>
  left_join(binned |> select(period, bin, share), by = c("period", "bin")) |>
  group_by(period) |> arrange(ratio, outlet_name, .by_group = TRUE) |>
  mutate(label_y = seq(.14, .49, length.out = n()),
    label_x = pmin(ratio, .98), label_hjust = if_else(ratio > .85, 1, .5),
    label = paste0(str_wrap(outlet_name, 23), "\n",
      sprintf("%.1f%% (%d/%d)", 100 * ratio, question_days, attendance_days))) |>
  ungroup()
distribution <- ggplot(binned, aes(midpoint, share, fill = period)) +
  geom_col(width = .05, color = "white", linewidth = .3, show.legend = FALSE) +
  geom_vline(data = stats, aes(xintercept = median, color = period),
    linetype = "dashed", linewidth = .55, show.legend = FALSE) +
  geom_text(data = stats, aes(x = Inf, y = Inf,
    label = sprintf("%d outlets\nMedian: %.1f%%", outlets, 100 * median)),
    inherit.aes = FALSE, hjust = 1.1, vjust = 1.2, size = 3.3, lineheight = 1.2) +
  geom_segment(data = high_ratios,
    aes(x = ratio, xend = label_x, y = share + .007, yend = label_y),
    inherit.aes = FALSE, color = "#A8ADB3", linewidth = .35) +
  geom_point(data = high_ratios, aes(x = ratio, y = share + .007, color = period),
    inherit.aes = FALSE, size = 1.5, show.legend = FALSE) +
  geom_label(data = high_ratios,
    aes(x = label_x, y = label_y, label = label, hjust = label_hjust, color = period),
    inherit.aes = FALSE, fill = "white", linewidth = 0, label.padding = grid::unit(.12, "lines"),
    size = 2.9, lineheight = 1.05, show.legend = FALSE) +
  facet_wrap(vars(period), nrow = 1,
    labeller = labeller(period = function(x) if (is.null(group)) x else paste(group, x, sep = " - "))) +
  scale_fill_manual(values = palette) + scale_color_manual(values = palette) +
  scale_x_continuous(limits = c(0, 1), breaks = seq(0, 1, .2),
    labels = scales::label_percent(accuracy = 1), expand = expansion(mult = c(0, .02))) +
  scale_y_continuous(limits = if (is.null(y_max)) NULL else c(0, y_max),
    labels = scales::label_percent(accuracy = 1), expand = expansion(mult = c(0, .15))) +
  labs(x = "Share of attended days with at least one question", y = "Share of outlets",
    caption = "Named outlets: ratios of 40% or higher; parentheses show question-days / attendance-days.") +
  base_theme + theme(strip.text = element_text(face = "bold", size = 11),
    panel.grid.major.x = element_blank(), panel.spacing.x = grid::unit(1.2, "lines"),
    plot.caption = element_text(size = 9, hjust = 0, color = "#555555"))
list(plot = distribution, high = high_ratios, stats = stats)
}

paired_plot <- function(selected, title) {
row_count <- max(1L, nrow(selected))
selected <- selected |> mutate(y = row_count + 1L - rank)
points <- bind_rows(
  selected |> transmute(unit_id, y, ratio = ratio_before, period = periods[1]),
  selected |> transmute(unit_id, y, ratio = ratio_after, period = periods[2])) |>
  mutate(period = factor(period, levels = periods))
labels <- paste0(str_wrap(selected$outlet_name, 23), "\n",
  selected$questions_before, "/", selected$attendance_before, " to ",
  selected$questions_after, "/", selected$attendance_after)
ggplot(selected, aes(y = y)) +
  geom_segment(aes(x = ratio_before, xend = ratio_after, yend = y),
    color = "#A8ADB3", linewidth = .65) +
  geom_point(data = points, aes(x = ratio, color = period, shape = period), size = 2.8) +
  geom_text(aes(x = 1.17, label = change_label), size = 3, color = "#303030") +
  annotate("text", x = 1.17, y = row_count + .9, label = "Change\n(p.p.)", size = 3, fontface = "bold") +
  scale_color_manual(values = palette) + scale_shape_manual(values = c(16, 17)) +
  scale_x_continuous(limits = c(0, 1.30), breaks = seq(0, 1, .25),
    labels = scales::label_percent(accuracy = 1), expand = expansion(mult = .04)) +
  scale_y_continuous(limits = c(.5, row_count + 1.4), breaks = selected$y,
    labels = labels, expand = expansion(mult = 0)) +
  labs(title = title, x = "Question-days / attendance-days", y = NULL,
    color = NULL, shape = NULL) + base_theme +
  theme(panel.grid.major.y = element_blank(), legend.position = "bottom",
    legend.text = element_text(size = 10), axis.text.y = element_text(color = "#303030", size = 9))
}
make_combined <- function(distribution, ranked) {
paired <- paired_plot(ranked$decreases, sprintf("%d largest decreases", nrow(ranked$decreases))) |
  paired_plot(ranked$increases, sprintf("%d largest increases", nrow(ranked$increases)))
distribution / paired + plot_layout(heights = c(1, 1.65), guides = "collect") &
  theme(legend.position = "bottom")
}
if (!changes_only && !"--groups-only" %in% commandArgs(TRUE)) {
all_distribution <- make_distribution(ratios)
write_csv(all_distribution$high |> select(outlet_name, period, question_days, attendance_days, ratio),
  file.path(audit, "named_high_ratio_outlets.csv"))
combined <- make_combined(all_distribution$plot, ranked)
ggsave(file.path(out, "questions_per_attendance_distribution_and_top10_changes.pdf"),
  combined, width = 14, height = 11, device = "pdf")
ggsave(file.path(out, "questions_per_attendance_distribution_before_after_lottery.pdf"),
  all_distribution$plot, width = 12, height = 5.5, device = "pdf")
}

# Use one metadata row per attendance entity, not subsidiary-level records.
# Strict opposition only: independent/unclear and unmatched entities are excluded.
ideology <- arrow::read_parquet(media_path(
  "data/06-outcomes/deduplicated_source_panels/outcome_entity_metadata.parquet")) |>
  filter(outcome == "attendance") |>
  transmute(unit_id = paste0("a:", entity_id), ideology_4t)
stopifnot(!anyDuplicated(ideology$unit_id))
classified <- ratios |> left_join(ideology, by = "unit_id", relationship = "many-to-one") |>
  filter(ideology_4t %in% c("opp", "aligned")) |>
  mutate(group = if_else(ideology_4t == "opp", "Opposition", "Aligned"))
classified_changes <- changes |> inner_join(
  classified |> distinct(unit_id, group), by = "unit_id", relationship = "one-to-one")
write_csv(classified, file.path(audit, "ratios_opposition_aligned.csv"))
write_csv(classified_changes, file.path(audit, "changes_opposition_aligned.csv"))
groups <- c("Opposition", "Aligned")
group_distributions <- lapply(groups, function(g)
  make_distribution(filter(classified, group == g), group = g, y_max = 1))
group_rankings <- lapply(groups, function(g)
  rank_changes(filter(classified_changes, group == g)))
write_csv(bind_rows(lapply(seq_along(groups), function(i)
  group_rankings[[i]]$top |> mutate(group = groups[i]) |> select(-y))),
  file.path(audit, "top10_changes_opposition_aligned.csv"))
write_csv(bind_rows(lapply(seq_along(groups), function(i)
  group_distributions[[i]]$stats |> mutate(group = groups[i]))),
  file.path(audit, "stats_opposition_aligned.csv"))
# Overlay identical 5-percentage-point bins, with each period normalized within
# group. Transparent fills plus colored borders keep overlap visible.
overlay_distribution <- function(g) {
  sample <- filter(classified, group == g)
  breaks <- seq(0, 1, .05)
  bins <- sample |>
    mutate(bin = cut(ratio, breaks, include.lowest = TRUE, right = TRUE)) |>
    count(period, bin, .drop = FALSE) |> group_by(period) |>
    mutate(share = n / sum(n)) |> ungroup() |>
    mutate(midpoint = (breaks[as.integer(bin)] + breaks[as.integer(bin) + 1L]) / 2)
  stopifnot(all(abs(tapply(bins$share, bins$period, sum) - 1) < 1e-12))
  i <- match(g, groups)
  summary <- group_distributions[[i]]$stats |>
    mutate(label_y = c(.89, .79),
      label = sprintf("%s: median %.1f%%", period, 100 * median))
  high <- group_distributions[[i]]$high |>
    mutate(label = paste0(label, "\n", period))
  ggplot(bins, aes(midpoint, share, fill = period, color = period)) +
    geom_col(position = "identity", width = .05, alpha = .35, linewidth = .45) +
    geom_vline(data = summary, aes(xintercept = median, color = period, linetype = period),
      linewidth = .5, show.legend = FALSE) +
    geom_text(data = summary, aes(x = .98, y = label_y, label = label, color = period),
      inherit.aes = FALSE, hjust = 1, size = 3.4, show.legend = FALSE) +
    annotate("text", x = .98, y = 1, label = sprintf("%d outlets", n_distinct(sample$unit_id)),
      hjust = 1, size = 3.4, color = "#333333") +
    geom_segment(data = high,
      aes(x = ratio, xend = label_x, y = share + .007, yend = label_y),
      inherit.aes = FALSE, color = "#A8ADB3", linewidth = .35) +
    geom_label(data = high,
      aes(x = label_x, y = label_y, label = label, hjust = label_hjust, color = period),
      inherit.aes = FALSE, fill = "white", linewidth = 0, size = 3,
      label.padding = grid::unit(.12, "lines"), show.legend = FALSE) +
    scale_fill_manual(values = palette, name = NULL) +
    scale_color_manual(values = palette, name = NULL) +
    scale_linetype_manual(values = c("dashed", "dotted")) +
    scale_x_continuous(limits = c(0, 1), breaks = seq(0, 1, .2),
      labels = scales::label_percent(accuracy = 1), expand = expansion(mult = c(0, .02))) +
    scale_y_continuous(limits = c(0, 1.04), breaks = seq(0, 1, .2),
      labels = scales::label_percent(accuracy = 1), expand = expansion(mult = c(0, .02))) +
    labs(title = g, x = "Share of attended days with at least one question", y = "Share of outlets") +
    base_theme + theme(panel.grid.major.x = element_blank(), legend.position = "bottom")
}
overlays <- lapply(groups, overlay_distribution)
if (!changes_only) {
ggsave(file.path(out, "questions_per_attendance_distribution_opposition_aligned.pdf"),
  (overlays[[1]] / overlays[[2]] + plot_layout(guides = "collect")) &
    theme(legend.position = "bottom"),
  width = 10, height = 9, device = "pdf")
}

# Combine both change directions into one named before/after chart per group.
# Retain the previous selection (up to ten per direction), not a new ranking.
change_plots <- vector("list", length(groups))
for (i in seq_along(groups)) {
  selected <- group_rankings[[i]]$top |>
    arrange(change_pp, outlet_name) |> mutate(rank = row_number())
  n_increases <- sum(selected$change_pp > 0)
  change_plot <- paired_plot(selected, "Largest decreases and increases") +
    geom_hline(yintercept = n_increases + .5, linetype = "dotted",
      color = "#A8ADB3", linewidth = .4)
  change_plots[[i]] <- change_plot
  # Single-page vector PDFs for independent inclusion/captioning in Overleaf.
  ggsave(file.path(out, paste0("questions_per_attendance_changes_", tolower(groups[i]), ".pdf")),
    change_plot + labs(title = NULL), width = 10,
    height = 1.6 + .40 * nrow(selected), device = "pdf", useDingbats = FALSE)
}
if (!changes_only) {
  pdf(file.path(out, "questions_per_attendance_distribution_and_changes_opposition_aligned.pdf"),
    width = 12, height = 13, onefile = TRUE)
  for (i in seq_along(groups)) {
    print((overlays[[i]] / change_plots[[i]] + plot_layout(heights = c(1, 2.5))) &
      theme(legend.position = "bottom"))
  }
  dev.off()
}
print(classified_changes |> group_by(group) |>
  summarise(outlets = n(), increases = sum(change_pp > 0), decreases = sum(change_pp < 0),
    unchanged = sum(change_pp == 0), .groups = "drop"))

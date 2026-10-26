# Run script 19 for --outcome=likes, comments, and views, each with:
# --transformation=chen_roth_x0 --treatment=question_day --pre-days=14
# --post-days=6 --no-winsorize --skip-plots
# This figure combines two explicitly labeled fits; it is not a single
# uninterrupted onset event study. Positive days are exit/carryover effects.
# Pass --split-independent to both scripts 19 and 21 for four separate rows.
split_independent <- "--split-independent" %in% commandArgs(trailingOnly = TRUE)
option_value <- function(name, default) {
  x <- grep(paste0("^--", name, "="), commandArgs(trailingOnly = TRUE), value = TRUE)
  if (length(x)) sub(paste0("^--", name, "="), "", x[[1]]) else default
}
transformation <- option_value("transformation", "chen_roth_x0")
n_boots <- as.integer(option_value("nboots", "50"))
winsorized <- "--winsorize" %in% commandArgs(trailingOnly = TRUE)
stopifnot(transformation %in% c("chen_roth_x0", "log1p"), n_boots >= 2L)
transform_title <- if (transformation == "log1p") "log(1 + y)" else "Chen-Roth calibrated log"
variant_label <- if (winsorized) "Pooled p1/p99 winsorization before transformation" else "No winsorization"
script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
script_path <- if (length(script_arg)) sub("^--file=", "", script_arg[[1]]) else {
  file.path(getwd(), "code", "07-final_panel", "21-plot-daily-likes-comments-views-grid.R")
}
repository_root <- normalizePath(file.path(dirname(script_path), "../.."), mustWork = TRUE)
suppressPackageStartupMessages({library(dplyr); library(readr); library(ggplot2)})
outcomes <- c(likes = "Likes", comments = "Comments", views = "Views")
groups <- c("Pooled", "Aligned", "Opp. + Independent")
if (split_independent) groups <- c("Pooled", "Aligned", "Opp.", "Independent")
run_suffix <- if (split_independent) "_split_independent" else ""
base_dir <- file.path(repository_root, "output", "fect_youtube")
prefix <- paste0("daily_question_day_", transformation, "_events_", n_boots,
                 if (!winsorized) "_unwinsorized" else "", "_pre14_post6_")
read_results <- function(filename) {
  bind_rows(lapply(names(outcomes), function(outcome) {
    x <- read_csv(file.path(base_dir, paste0(prefix, outcome, run_suffix), filename), show_col_types = FALSE)
    stopifnot(all(x$outcome == outcomes[[outcome]]))
    x
  }))
}
events <- read_results("event_estimates.csv")
details <- read_results("transformation_details.csv")
diagnostics <- read_results("model_diagnostics.csv")
stopifnot(nrow(events) == length(groups) * 3L * 21L, nrow(details) == 3L,
          nrow(diagnostics) == length(groups) * 3L * 2L,
          all(events$winsorized == winsorized), all(events$bootstrap_replications == n_boots),
          all(events$treatment == "Question day only"),
          all(grepl(if (transformation == "log1p") "log1p" else "Chen-Roth x=0", events$transformation, fixed = TRUE)),
          winsorized || all(details$observations_modified == 0),
          all(diagnostics$pre_days == 14L), all(diagnostics$post_days == 6L),
          n_distinct(diagnostics$start) == 1L, n_distinct(diagnostics$end) == 1L,
          !anyDuplicated(events[c("sample_group", "outcome", "event_day")]),
          all(is.finite(as.matrix(events[c("estimate", "conf95_low", "conf95_high")]))))
for (group in groups) for (outcome in unname(outcomes)) {
  d <- events |> filter(sample_group == group, .data$outcome == .env$outcome)
  stopifnot(setequal(d$event_day[d$event_type == "Onset"], -14:0),
            setequal(d$event_day[d$event_type == "Carryover"], 1:6),
            all(d$raw_fect_period[d$event_type == "Onset"] ==
                  d$event_day[d$event_type == "Onset"] + 1L),
            all(d$raw_fect_period[d$event_type == "Carryover"] ==
                  d$event_day[d$event_type == "Carryover"]))
}
phases <- c("Pre-question (-14 to -1)", "Question day (0)", "Carryover (+1 to +6)")
events <- events |>
  mutate(sample_group = factor(sample_group, levels = groups),
         outcome = factor(outcome, levels = unname(outcomes)),
         phase = factor(case_when(event_day < 0 ~ phases[1], event_day == 0 ~ phases[2],
                                  TRUE ~ phases[3]), levels = phases))
colors <- setNames(c("#81858B", "#B73535", "#365F7D"), phases)
new_variant <- !(transformation == "chen_roth_x0" && n_boots == 50L && !winsorized)
variant_suffix <- if (new_variant) paste0("_", transformation, if (winsorized) "_winsorized" else "_raw") else ""
output_dir <- file.path(base_dir, paste0("daily_likes_comments_views_grid_pre14_post6_", n_boots, variant_suffix, run_suffix))
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
write_csv(events, file.path(output_dir, "event_estimates.csv"))
write_csv(read_results("average_estimates.csv"), file.path(output_dir, "average_estimates.csv"))
write_csv(details, file.path(output_dir, "transformation_details.csv"))
write_csv(diagnostics, file.path(output_dir, "model_diagnostics.csv"))
split_caption <- ""
if (split_independent) {
  group_support <- read_csv(file.path(base_dir, paste0(prefix, "likes", run_suffix),
                                     "group_support.csv"), show_col_types = FALSE)
  write_csv(group_support, file.path(output_dir, "group_support.csv"))
  opp_support <- filter(group_support, alignment == "Opp.")
  stopifnot(nrow(opp_support) == 1L)
  split_caption <- paste0("\nIndependent = metadata unclear. Opp.: ", opp_support$n_outlets,
    " outlets, ", opp_support$n_question_outlets, " with question days (",
    opp_support$n_question_days, " treated days); interpret this small subgroup cautiously.")
}
# Row-specific display limits only; exported/model estimates are unchanged.
events <- events |> mutate(axis_limit = if_else(sample_group == "Opp.", 2.5, 1))
clipped <- any(events$conf95_low < -events$axis_limit | events$conf95_high > events$axis_limit)
plot_data <- events |> mutate(across(c(estimate, conf95_low, conf95_high, conf90_low, conf90_high),
                                     ~ pmax(-axis_limit, pmin(axis_limit, .x))))
axis_anchors <- bind_rows(
  distinct(events, sample_group, outcome, axis_limit) |> mutate(event_day = 0, estimate = -axis_limit),
  distinct(events, sample_group, outcome, axis_limit) |> mutate(event_day = 0, estimate = axis_limit)
)
caption <- paste0(
  "Outlet and date fixed effects; same-day attendance dummy; ", n_boots,
  " outlet bootstraps. Thick 90% / thin 95% pointwise intervals. ", variant_label, ".",
  "\nPre-question/day-0 and carryover use separate fits. Carryover days +1 to +6 are held out; follow-up stops at the next question.",
  if (transformation == "log1p") "\nOutcome = log(1 + y); zeros remain zero. Metrics assigned to video publication date." else
    "\nChen-Roth x=0 calibration: log(y) if positive; log(pooled minimum positive) at zero, separately by outcome. Metrics assigned to video publication date.",
  split_caption,
  if (split_independent) "\nY-axis: Opp. -2.5 to +2.5; other groups -1 to +1." else "",
  if (clipped) "\nTriangles mark intervals beyond the displayed range; filled triangles also mark out-of-range point estimates." else ""
)
p <- ggplot(plot_data, aes(event_day, estimate, color = phase)) +
  geom_blank(data = axis_anchors, aes(event_day, estimate), inherit.aes = FALSE) +
  annotate("rect", xmin = .5, xmax = 6.6, ymin = -Inf, ymax = Inf,
           fill = "#365F7D", alpha = .045) +
  geom_hline(yintercept = 0, color = "#767676", linewidth = .3) +
  geom_vline(xintercept = 0, color = "#B73535", linetype = "dashed", linewidth = .3) +
  geom_errorbar(aes(ymin = conf95_low, ymax = conf95_high), width = 0, linewidth = .35) +
  geom_errorbar(aes(ymin = conf90_low, ymax = conf90_high), width = 0, linewidth = .8) +
  geom_line(data = filter(plot_data, event_day != 0), aes(group = phase), linewidth = .4) +
  geom_point(size = 1.35) +
  geom_point(data = filter(plot_data, event_day == 0), size = 2.2) +
  facet_grid(sample_group ~ outcome, switch = "y", scales = "free_y") +
  scale_color_manual(values = colors, drop = FALSE) +
  scale_x_continuous(breaks = c(-14, -10, -6, 0, 3, 6),
                     labels = c("-14", "-10", "-6", "0", "+3", "+6"),
                     expand = expansion(mult = 0)) +
  scale_y_continuous(breaks = function(limits) {
                       bound <- max(abs(limits))
                       seq(-bound, bound, length.out = 5)
                     },
                     labels = function(x) ifelse(x > 0, paste0("+", x), as.character(x)),
                     expand = expansion(mult = 0)) +
  coord_cartesian(xlim = c(-14.6, 6.6)) +
  labs(title = "Question-day effects on YouTube engagement",
       subtitle = paste0(transform_title, " | ", if (winsorized) "Winsorized | " else "", "18 Apr 2022 - 31 Dec 2024 | Question-day treatment"),
       x = "Event day: negative = pre-question; 0 = question day; positive = days after last question",
       y = if (transformation == "log1p") "Effect on log(1 + outcome)" else "Effect on calibrated log outcome", color = NULL, caption = caption) +
  theme_minimal(base_size = 10) +
  theme(panel.grid.minor = element_blank(),
        panel.grid.major.x = element_blank(),
        panel.grid.major.y = element_line(color = "#E7E7E7", linewidth = .3),
        panel.spacing = grid::unit(12, "pt"),
        strip.placement = "outside", strip.text = element_text(face = "bold", size = 11),
        strip.text.y.left = element_text(angle = 0, hjust = 1, size = 10),
        axis.text = element_text(color = "#444444", size = 8.5),
        axis.title = element_text(size = 9),
        plot.title = element_text(face = "bold", size = 17),
        plot.subtitle = element_text(size = 10, margin = margin(b = 12)),
        plot.caption = element_text(size = 7.4, hjust = 0, lineheight = 1.2),
        legend.position = "bottom", legend.text = element_text(size = 9),
        plot.margin = margin(16, 18, 14, 12))
if (clipped) {
  p <- p + geom_point(data = filter(events, conf95_high > axis_limit), aes(y = .96 * axis_limit),
                      shape = 24, fill = "white", size = 1.8, show.legend = FALSE) +
    geom_point(data = filter(events, conf95_low < -axis_limit), aes(y = -.96 * axis_limit),
               shape = 25, fill = "white", size = 1.8, show.legend = FALSE)
  p <- p + geom_point(data = filter(events, estimate > axis_limit), aes(y = .96 * axis_limit, fill = phase),
                      shape = 24, size = 1.8, show.legend = FALSE) +
    geom_point(data = filter(events, estimate < -axis_limit), aes(y = -.96 * axis_limit, fill = phase),
               shape = 25, size = 1.8, show.legend = FALSE) +
    scale_fill_manual(values = colors, guide = "none")
}
pdf_name <- if (split_independent) "fect_daily_likes_comments_views_4x3_pre14_post6_split_independent.pdf" else
  "fect_daily_likes_comments_views_3x3_pre14_post6.pdf"
if (new_variant) pdf_name <- sub("[.]pdf$", paste0(variant_suffix, "_", n_boots, ".pdf"), pdf_name)
pdf_path <- file.path(repository_root, "output", "pdf", pdf_name)
layout <- ggplot_build(p)$layout
for (i in seq_along(layout$panel_scales_y)) {
  row_group <- as.character(layout$layout$sample_group[match(i, layout$layout$SCALE_Y)])
  expected_limit <- if (row_group == "Opp.") 2.5 else 1
  stopifnot(isTRUE(all.equal(layout$panel_scales_y[[i]]$range$range,
                            c(-expected_limit, expected_limit))))
}
ggsave(pdf_path, p, width = 12, height = if (split_independent) 12 else 9.5, units = "in")
message("Saved ", pdf_path)
message("95% interval range: ", paste(range(c(events$conf95_low, events$conf95_high)), collapse = " to "))

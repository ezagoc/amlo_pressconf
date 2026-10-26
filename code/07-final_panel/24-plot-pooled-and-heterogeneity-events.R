# Presentation-only revision: read saved estimates; never run FEct or bootstrap.
# Creates pooled 1x3 and heterogeneity 3x3 figures for all three saved variants.
# Tables and the previous combined figures are deliberately left unchanged.
script_arg <- grep("^--file=", commandArgs(FALSE), value = TRUE)
script_path <- if (length(script_arg)) sub("^--file=", "", script_arg[[1]]) else
  file.path(getwd(), "code/07-final_panel/24-plot-pooled-and-heterogeneity-events.R")
root <- normalizePath(file.path(dirname(script_path), "../.."), mustWork = TRUE)
suppressPackageStartupMessages({library(dplyr); library(readr); library(ggplot2)})
base_dir <- file.path(root, "output/fect_youtube")
pdf_dir <- file.path(root, "output/pdf/event_studies_main_heterogeneity")
dir.create(pdf_dir, recursive = TRUE, showWarnings = FALSE)
variants <- tibble::tribble(
  ~variant, ~folder, ~n_boots, ~y_label,
  "chen_roth_50", "daily_likes_comments_views_grid_pre14_post6_50_split_independent", 50L,
  "Effect on calibrated log outcome",
  "log1p_raw_1000", "daily_likes_comments_views_grid_pre14_post6_1000_log1p_raw_split_independent", 1000L,
  "Effect on log(1 + outcome)",
  "log1p_winsorized_1000", "daily_likes_comments_views_grid_pre14_post6_1000_log1p_winsorized_split_independent", 1000L,
  "Effect on log(1 + outcome)"
)
groups <- c("Pooled", "Aligned", "Opp.", "Independent")
outcomes <- c("Likes", "Comments", "Views")
phases <- c("Pre-question (-14 to -1)", "Question day (0)", "Carryover (+1 to +6)")
colors <- setNames(c("#81858B", "#B73535", "#365F7D"), phases)
y_limits <- c(-2, 2.5)
manifest <- list()
input_paths <- file.path(base_dir, variants$folder, "event_estimates.csv")
protected_paths <- c(input_paths,
  file.path(root, "output/latex/fect_likes_comments_views_log1p_1000.tex"),
  file.path(base_dir, "log1p_comparison_1000/att_and_diagnostics.csv"))
before_hashes <- tools::md5sum(protected_paths)
stopifnot(!anyNA(before_hashes))

draw_events <- function(d, y_label) {
  p <- ggplot(d, aes(event_day, estimate, color = phase)) +
    annotate("rect", xmin = .5, xmax = 6.6, ymin = -Inf, ymax = Inf,
             fill = "#365F7D", alpha = .045) +
    geom_hline(yintercept = 0, color = "#767676", linewidth = .3) +
    geom_vline(xintercept = 0, color = "#B73535", linetype = "dashed", linewidth = .3) +
    geom_errorbar(aes(ymin = conf95_low, ymax = conf95_high), width = 0, linewidth = .35) +
    geom_errorbar(aes(ymin = conf90_low, ymax = conf90_high), width = 0, linewidth = .8) +
    geom_line(data = filter(d, event_day != 0), aes(group = phase), linewidth = .4) +
    geom_point(size = 1.5) +
    geom_point(data = filter(d, event_day == 0), size = 2.4) +
    facet_grid(sample_group ~ outcome, switch = "y") +
    scale_color_manual(values = colors, drop = FALSE) +
    scale_fill_manual(values = colors, guide = "none") +
    scale_x_continuous(breaks = c(-14, -10, -6, 0, 3, 6),
      labels = c("-14", "-10", "-6", "0", "+3", "+6"), expand = expansion(mult = 0)) +
    scale_y_continuous(breaks = seq(y_limits[1], y_limits[2], by = .5),
      labels = function(x) ifelse(x > 0, paste0("+", x), as.character(x)),
      expand = expansion(mult = 0)) +
    coord_cartesian(xlim = c(-14.6, 6.6), ylim = y_limits) +
    labs(x = "Event day: negative = pre-question; 0 = question day; positive = days after last question",
         y = y_label, color = NULL, title = NULL, subtitle = NULL, caption = NULL) +
    theme_minimal(base_size = 14) +
    theme(panel.grid.minor = element_blank(), panel.grid.major.x = element_blank(),
      panel.grid.major.y = element_line(color = "#E7E7E7", linewidth = .3),
      panel.spacing = grid::unit(15, "pt"), strip.placement = "outside",
      strip.text = element_text(face = "bold", size = 16),
      strip.text.y.left = element_text(angle = 0, hjust = 1, size = 15),
      axis.text = element_text(color = "#444444", size = 12.5),
      axis.title = element_text(size = 14),
      axis.title.x = element_text(margin = margin(t = 10)),
      axis.title.y = element_text(margin = margin(r = 10)),
      legend.position = "bottom", legend.text = element_text(size = 14),
      legend.margin = margin(t = 10), plot.margin = margin(12, 18, 12, 12))
  # Coordinate zoom leaves every estimate/interval unchanged. Open triangles
  # flag truncated CIs; filled triangles would flag out-of-range estimates.
  for (side in c("low", "high")) {
    below <- side == "low"
    boundary <- if (below) y_limits[1] else y_limits[2]
    marker_y <- boundary + if (below) .045 else -.045
    ci_rows <- if (below) filter(d, conf95_low < boundary) else filter(d, conf95_high > boundary)
    point_rows <- if (below) filter(d, estimate < boundary) else filter(d, estimate > boundary)
    p <- p + geom_point(data = ci_rows, y = marker_y,
      shape = if (below) 25 else 24, fill = "white", size = 2, show.legend = FALSE) +
      geom_point(data = point_rows, aes(fill = phase), y = marker_y,
      shape = if (below) 25 else 24, size = 2, show.legend = FALSE)
  }
  built <- ggplot_build(p)
  stopifnot(all(vapply(built$layout$panel_params, function(x)
    isTRUE(all.equal(x$y.range, y_limits)), logical(1))))
  p
}

for (i in seq_len(nrow(variants))) {
  d <- read_csv(input_paths[i], show_col_types = FALSE)
  stopifnot(nrow(d) == 252L, all(d$bootstrap_replications == variants$n_boots[i]),
    setequal(d$sample_group, groups), setequal(d$outcome, outcomes),
    !anyDuplicated(d[c("sample_group", "outcome", "event_day")]),
    all(is.finite(as.matrix(d[c("estimate", "conf95_low", "conf95_high", "conf90_low", "conf90_high")]))))
  for (group in groups) for (outcome_name in outcomes) {
    z <- filter(d, sample_group == group, outcome == outcome_name)
    stopifnot(setequal(z$event_day, -14:6),
      all(z$event_type[z$event_day <= 0] == "Onset"),
      all(z$event_type[z$event_day > 0] == "Carryover"))
  }
  d <- d |> mutate(sample_group = factor(sample_group, levels = groups),
    outcome = factor(outcome, levels = outcomes),
    phase = factor(case_when(event_day < 0 ~ phases[1], event_day == 0 ~ phases[2],
                             TRUE ~ phases[3]), levels = phases))
  for (section in c("pooled", "heterogeneity")) {
    selected <- if (section == "pooled") filter(d, sample_group == "Pooled") else
      filter(d, sample_group != "Pooled")
    stopifnot(nrow(selected) == if (section == "pooled") 63L else 189L)
    p <- draw_events(selected, variants$y_label[i])
    filename <- paste0("fect_", section, "_", variants$variant[i], ".pdf")
    path <- file.path(pdf_dir, filename)
    ggsave(path, p, width = 14, height = if (section == "pooled") 5 else 10,
           units = "in", device = "pdf")
    manifest[[length(manifest) + 1L]] <- tibble::tibble(
      variant = variants$variant[i], section, filename, source = input_paths[i],
      bootstrap_replications = variants$n_boots[i], panels = nrow(selected) / 21L,
      y_min = y_limits[1], y_max = y_limits[2],
      ci95_below_axis = sum(selected$conf95_low < y_limits[1]),
      ci95_above_axis = sum(selected$conf95_high > y_limits[2]))
    message("Saved ", path)
  }
}
stopifnot(identical(before_hashes, tools::md5sum(protected_paths)))
write_csv(bind_rows(manifest), file.path(pdf_dir, "figure_manifest.csv"))
message("Verified: input estimates and tables unchanged. No models re-estimated.")

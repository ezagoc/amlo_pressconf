# Three outcome pages per PDF, separately by sample and event-study type.
# First run script 19 with --outcome=mean_interactions, likes, and comments,
# using --transformation=chen_roth_x0 --treatment=question_day --pre-days=14
# --post-days=14 --no-winsorize --skip-plots.
script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
script_path <- if (length(script_arg)) sub("^--file=", "", script_arg[[1]]) else {
  file.path(getwd(), "code", "07-final_panel", "20-plot-daily-log-engagement-outcomes.R")
}
repository_root <- normalizePath(file.path(dirname(script_path), "../.."), mustWork = TRUE)
suppressPackageStartupMessages({library(dplyr); library(readr); library(ggplot2)})
outcomes <- c(mean_interactions = "Mean interactions per video", likes = "Likes", comments = "Comments")
base_dir <- file.path(repository_root, "output", "fect_youtube")
prefix <- "daily_question_day_chen_roth_x0_events_50_unwinsorized_pre14_post14_"
read_results <- function(filename) {
  bind_rows(lapply(names(outcomes), function(outcome) {
    x <- read_csv(file.path(base_dir, paste0(prefix, outcome), filename), show_col_types = FALSE)
    stopifnot(all(x$outcome == outcomes[[outcome]]))
    x
  }))
}
events <- read_results("event_estimates.csv")
averages <- read_results("average_estimates.csv")
details <- read_results("transformation_details.csv")
stopifnot(nrow(events) == 261L, nrow(averages) == 18L,
          all(!events$winsorized), all(events$bootstrap_replications == 50L),
          all(details$observations_modified == 0), all(is.finite(events$estimate)),
          !anyDuplicated(events[c("sample_group", "outcome", "event_type", "event_day")]))

output_dir <- file.path(base_dir, "daily_log_engagement_outcomes_50")
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
write_csv(events, file.path(output_dir, "event_estimates.csv"))
write_csv(averages, file.path(output_dir, "average_estimates.csv"))
write_csv(details, file.path(output_dir, "transformation_details.csv"))
groups <- c("Pooled", "Aligned", "Opp. + Independent")
slugs <- c("Pooled" = "pooled", "Aligned" = "aligned", "Opp. + Independent" = "opp_independent")
colors <- c("Pooled" = "#666666", "Aligned" = "#355C7D", "Opp. + Independent" = "#A65D45")

for (group in groups) {
  for (kind in c("Onset", "Carryover")) {
    path <- file.path(repository_root, "output", "pdf",
                      paste0("fect_daily_log_engagement_pre14_post14_", tolower(kind), "_", slugs[[group]], ".pdf"))
    pdf(path, width = 4, height = 4, onefile = TRUE)
    for (outcome_label in unname(outcomes)) {
      data <- events |> filter(sample_group == group, event_type == kind, outcome == outcome_label)
      expected <- if (kind == "Onset") -14:0 else 1:14
      stopifnot(setequal(data$event_day, expected))
      zero_value <- details$value_at_zero[details$outcome == outcome_label]
      breaks <- if (kind == "Onset") c(seq(-14, -2, 2), -1, 0) else c(1, seq(2, 14, 2))
      caption <- paste0(
        if (kind == "Onset") "Day 0 = question day; negative days are pre-treatment fit." else
          "Days 1-14 held out; follow-up ends at the next question.",
        "\n50 bootstraps; thick 90%, thin 95% pointwise intervals.",
        "\nZero replacement on log scale: ", format(round(zero_value, 3), trim = TRUE), "."
      )
      clipped <- any(data$conf95_low < -1 | data$conf95_high > 1)
      if (clipped) caption <- paste0(caption, " Triangles mark clipped intervals.")
      p <- ggplot(data, aes(event_day, estimate)) +
        geom_hline(yintercept = 0, color = "#555555", linewidth = .35) +
        geom_errorbar(aes(ymin = conf95_low, ymax = conf95_high), width = 0,
                      linewidth = .4, color = colors[[group]]) +
        geom_errorbar(aes(ymin = conf90_low, ymax = conf90_high), width = 0,
                      linewidth = 1, color = colors[[group]]) +
        geom_line(linewidth = .45, color = colors[[group]]) +
        geom_point(size = 1.5, color = colors[[group]]) +
        scale_x_continuous(breaks = breaks) +
        scale_y_continuous(breaks = seq(-1, 1, .5), expand = expansion(mult = 0)) +
        coord_cartesian(ylim = c(-1, 1)) +
        labs(title = paste0(group, ": ", tolower(kind)),
             subtitle = paste0(outcome_label, " | unwinsorized log"),
             x = if (kind == "Onset") "Days relative to first question day" else "Days after last question day",
             y = "Effect on calibrated log outcome", caption = caption) +
        theme_minimal(base_size = 8) +
        theme(plot.title = element_text(face = "bold", size = 10),
              plot.subtitle = element_text(size = 7),
              plot.caption = element_text(size = 5.6, hjust = 0),
              panel.grid.minor = element_blank(), plot.margin = margin(8, 8, 8, 8))
      if (kind == "Onset") p <- p + geom_vline(xintercept = 0, linetype = "dashed", linewidth = .3)
      if (clipped) {
        p <- p + geom_point(data = filter(data, conf95_high > 1), aes(y = .98),
                            shape = 24, size = 1.5, color = colors[[group]], fill = colors[[group]]) +
          geom_point(data = filter(data, conf95_low < -1), aes(y = -.98),
                     shape = 25, size = 1.5, color = colors[[group]], fill = colors[[group]])
      }
      print(p)
    }
    dev.off()
    message("Saved ", path)
  }
}

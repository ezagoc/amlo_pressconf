# Separate event-study figures for interactions, with four pre-treatment weeks.
rm(list = ls())

if (requireNamespace("rstudioapi", quietly = TRUE) && rstudioapi::isAvailable()) {
  setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
} else if (dir.exists(file.path(getwd(), "code", "07-final_panel"))) {
  setwd(file.path(getwd(), "code", "07-final_panel"))
}

library(tidyverse)

repository_root <- normalizePath(file.path(getwd(), "../.."), mustWork = TRUE)
results_path <- file.path(
  repository_root, "output", "fect_youtube",
  "fect_asinh_event_studies_1000.csv"
)
pdf_dir <- file.path(repository_root, "output", "pdf")

groups <- c("Pooled", "Aligned", "Opp. + Independent")
group_colors <- c(
  "Pooled" = "#666666",
  "Aligned" = "#355C7D",
  "Opp. + Independent" = "#A65D45"
)
group_files <- c(
  "Pooled" = "fect_asinh_event_interactions_pooled.pdf",
  "Aligned" = "fect_asinh_event_interactions_aligned.pdf",
  "Opp. + Independent" = "fect_asinh_event_interactions_opp_independent.pdf"
)

data <- read_csv(results_path, show_col_types = FALSE) |>
  filter(
    event_type == "Treatment onset",
    outcome %in% c("Interactions", "Mean interactions per video"),
    between(event_time, -4L, 1L)
  ) |>
  mutate(
    outcome = factor(
      outcome,
      levels = c("Interactions", "Mean interactions per video")
    )
  )

plot_group <- function(group_name) {
  plot_data <- data |> filter(sample_group == group_name)

  plot <- ggplot(plot_data, aes(event_time, att)) +
    geom_hline(yintercept = 0, color = "#555555", linewidth = 0.35) +
    geom_vline(xintercept = 0, linetype = "dashed", color = "#555555", linewidth = 0.35) +
    geom_errorbar(
      aes(ymin = conf95_low, ymax = conf95_high),
      width = 0,
      linewidth = 0.4,
      color = group_colors[[group_name]]
    ) +
    geom_errorbar(
      aes(ymin = conf90_low, ymax = conf90_high),
      width = 0,
      linewidth = 1,
      color = group_colors[[group_name]]
    ) +
    geom_line(linewidth = 0.5, color = group_colors[[group_name]]) +
    geom_point(size = 1.5, color = group_colors[[group_name]]) +
    facet_wrap(vars(outcome), ncol = 1, scales = "free_y") +
    scale_x_continuous(breaks = -4:1) +
    labs(
      title = paste0(group_name, ": interactions around question exposure"),
      subtitle = "Winsorized asinh; thick 90% and thin 95% bootstrap intervals",
      x = "Weeks relative to treatment onset",
      y = "FEct ATT"
    ) +
    theme_minimal(base_size = 7) +
    theme(
      plot.title = element_text(face = "bold", size = 8.5),
      plot.subtitle = element_text(size = 6.2),
      strip.text = element_text(face = "bold", size = 6.5),
      axis.text = element_text(size = 5.5),
      axis.title = element_text(size = 6.2),
      panel.grid.minor = element_blank(),
      plot.margin = margin(4, 4, 3, 4)
    )

  output_path <- file.path(pdf_dir, group_files[[group_name]])
  ggsave(output_path, plot, width = 4, height = 4, units = "in", device = "pdf")
  output_path
}

output_paths <- map_chr(groups, plot_group)
cat(paste("PDF saved to:", output_paths, collapse = "\n"), "\n")

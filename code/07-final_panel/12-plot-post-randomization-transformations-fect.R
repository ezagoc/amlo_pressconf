# Plot saved post-randomization FEct transformation results.
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
  "fect_post_randomization_transformations.csv"
)
pdf_path <- file.path(
  repository_root, "output", "pdf",
  "fect_post_randomization_transformations.pdf"
)

plot_data <- read_csv(results_path, show_col_types = FALSE) |>
  mutate(
    treatment = factor(
      treatment,
      levels = c("Question week", "+1 week", "+2 weeks")
    ),
    transformation = factor(
      transformation,
      levels = c("winsorized_level", "asinh", "chen_roth"),
      labels = c("Winsorized level", "asinh", "Chen-Roth")
    ),
    outcome = factor(
      outcome,
      levels = c("Videos", "Views", "Interactions", "Mean interactions per video")
    )
  )

plot <- ggplot(plot_data, aes(treatment, att)) +
  geom_hline(yintercept = 0, color = "#555555", linewidth = 0.3) +
  geom_errorbar(
    aes(ymin = conf_low, ymax = conf_high),
    width = 0.12,
    linewidth = 0.4,
    color = "#355C7D"
  ) +
  geom_point(size = 1.4, color = "#355C7D") +
  facet_wrap(vars(outcome, transformation), ncol = 3, scales = "free_y") +
  labs(
    title = "Questions and YouTube outcomes after randomization",
    subtitle = "FEct ATT and 95% bootstrap intervals; outcomes winsorized at p1/p99",
    x = NULL,
    y = "ATT in transformed outcome units"
  ) +
  theme_minimal(base_size = 7) +
  theme(
    plot.title = element_text(face = "bold", size = 8.3),
    plot.subtitle = element_text(size = 6.1),
    strip.text = element_text(face = "bold", size = 5.2),
    axis.text = element_text(size = 5),
    axis.text.x = element_text(angle = 25, hjust = 1),
    axis.title.y = element_text(size = 6),
    panel.grid.minor = element_blank(),
    plot.margin = margin(4, 4, 3, 4)
  )

ggsave(pdf_path, plot, width = 4, height = 5, units = "in", device = "pdf")
cat("PDF saved to:", pdf_path, "\n")

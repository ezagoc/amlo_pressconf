# Full-period COMSOC contract values with election markers and LOESS trends.
rm(list = ls())

if (requireNamespace("rstudioapi", quietly = TRUE) && rstudioapi::isAvailable()) {
  setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
} else if (dir.exists(file.path(getwd(), "code", "07-final_panel"))) {
  setwd(file.path(getwd(), "code", "07-final_panel"))
}

source("../../project_paths.R")

library(tidyverse)

input_path <- media_path(
  "data", "06-outcomes", "deduplicated_source_panels",
  "contracts_entity_daily_panel.parquet"
)
repository_root <- normalizePath(file.path(getwd(), "../.."), mustWork = TRUE)
output_dir <- file.path(repository_root, "output", "pdf")
output_path <- file.path(output_dir, "comsoc_contract_values_full_period_4x4.pdf")
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

metric_labels <- c(
  total = "Total contract value",
  mean_per_eligible = "Mean per eligible company"
)

company_month <- arrow::open_dataset(input_path) |>
  select(entity_id, date, ideology_4t, source_date_observed, contracts_costo) |>
  filter(
    source_date_observed,
    date >= as.Date("2012-01-01"),
    date <= as.Date("2024-12-31")
  ) |>
  collect() |>
  mutate(
    period = floor_date(date, "month"),
    ideology_group = if_else(ideology_4t == "aligned", "aligned", "opposition")
  ) |>
  group_by(period, entity_id, ideology_group) |>
  summarise(contracts_costo = sum(contracts_costo, na.rm = TRUE), .groups = "drop")

plot_data <- company_month |>
  group_by(period, ideology_group) |>
  summarise(
    total = sum(contracts_costo, na.rm = TRUE),
    eligible_companies = n_distinct(entity_id),
    mean_per_eligible = total / eligible_companies,
    .groups = "drop"
  ) |>
  select(period, ideology_group, all_of(names(metric_labels))) |>
  pivot_longer(
    all_of(names(metric_labels)),
    names_to = "measure",
    values_to = "value"
  ) |>
  mutate(
    measure = factor(measure, levels = names(metric_labels), labels = metric_labels)
  )

events <- tribble(
  ~date, ~label,
  as.Date("2018-07-01"), "2018 election",
  as.Date("2021-06-06"), "2021 midterms",
  as.Date("2024-06-02"), "2024 election"
)

plot <- ggplot(plot_data, aes(period, value, color = ideology_group)) +
  geom_vline(
    data = events,
    aes(xintercept = date),
    inherit.aes = FALSE,
    linetype = "dashed",
    color = "#555555",
    linewidth = 0.35
  ) +
  geom_line(linewidth = 0.45, alpha = 0.85, na.rm = TRUE) +
  geom_text(
    data = events,
    aes(x = date, y = Inf, label = label),
    inherit.aes = FALSE,
    angle = 90,
    hjust = 1.05,
    vjust = -0.25,
    size = 2.1,
    color = "#444444",
    lineheight = 0.85
  ) +
  facet_wrap(vars(measure), scales = "free_y", ncol = 1) +
  scale_color_manual(
    values = c(aligned = "#355C7D", opposition = "#8E3B46"),
    labels = c(aligned = "Aligned", opposition = "Opp. + Independent")
  ) +
  scale_x_date(
    limits = c(as.Date("2012-01-01"), as.Date("2024-12-31")),
    date_breaks = "3 years",
    date_labels = "%Y",
    expand = expansion(mult = c(0, 0))
  ) +
  scale_y_continuous(
    labels = scales::label_number(prefix = "$", scale_cut = scales::cut_short_scale()),
    expand = expansion(mult = c(0.03, 0.17))
  ) +
  labs(
    title = "COMSOC contract values by 4T alignment",
    subtitle = "Monthly values, 2012-2024 (MXN)",
    x = NULL,
    y = NULL,
    color = NULL
  ) +
  theme_minimal(base_size = 7) +
  theme(
    plot.title = element_text(face = "bold", size = 9),
    plot.subtitle = element_text(size = 6.5),
    strip.text = element_text(face = "bold", size = 7),
    axis.text = element_text(size = 5.5),
    legend.position = "bottom",
    legend.text = element_text(size = 6),
    legend.key.width = unit(0.8, "cm"),
    panel.grid.minor = element_blank(),
    plot.margin = margin(4, 5, 3, 4)
  )

ggsave(
  output_path,
  plot,
  width = 4,
  height = 4,
  units = "in",
  device = "pdf"
)

cat("PDF saved to:", output_path, "\n")

# Monthly proportions of YouTube videos mentioning political topics.
rm(list = ls())

if (requireNamespace("rstudioapi", quietly = TRUE) && rstudioapi::isAvailable()) {
  setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
} else if (dir.exists(file.path(getwd(), "code", "07-final_panel"))) {
  setwd(file.path(getwd(), "code", "07-final_panel"))
}

source("../../project_paths.R")

library(tidyverse)
library(arrow)

randomization_date <- as.Date("2022-04-18")
window_start <- floor_date(randomization_date %m-% months(18), "month")
window_end <- ceiling_date(randomization_date %m+% months(18), "month") - days(1)
panel_path <- media_path(
  "data", "06-outcomes", "youtube", "text_outcomes",
  "youtube_text_outcomes_entity_daily_panel.parquet"
)
repository_root <- normalizePath(file.path(getwd(), "../.."), mustWork = TRUE)
data_output_dir <- file.path(repository_root, "output", "youtube_text_outcomes")
pdf_output_dir <- file.path(repository_root, "output", "pdf")
dir.create(data_output_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(pdf_output_dir, recursive = TRUE, showWarnings = FALSE)

panel <- read_parquet(panel_path) |>
  filter(
    source_entity_matched,
    !is.na(youtube_total_videos),
    date >= window_start,
    date <= window_end
  ) |>
  mutate(
    month = floor_date(date, "month"),
    group = if_else(
      ideology_4t == "aligned",
      "Aligned",
      "Opp. + Independent"
    )
  )

summarize_monthly <- function(data, grouping) {
  data |>
    group_by(month, group = {{ grouping }}) |>
    summarise(
      total_videos = sum(youtube_total_videos),
      morning_conference_mentions = sum(youtube_morning_conference_videos),
      amlo_morena_mentions = sum(youtube_amlo_morena_videos),
      .groups = "drop"
    ) |>
    mutate(
      morning_conference_share = if_else(
        total_videos > 0,
        morning_conference_mentions / total_videos,
        NA_real_
      ),
      amlo_morena_share = if_else(
        total_videos > 0,
        amlo_morena_mentions / total_videos,
        NA_real_
      )
    )
}

monthly_groups <- summarize_monthly(panel, group)
monthly_all <- summarize_monthly(panel, "All outlets")
monthly <- bind_rows(monthly_all, monthly_groups) |>
  arrange(month, factor(group, c("All outlets", "Aligned", "Opp. + Independent")))

write_csv(
  monthly,
  file.path(data_output_dir, "youtube_mentions_monthly.csv")
)

plot_data <- monthly |>
  filter(group == "All outlets") |>
  select(month, group, morning_conference_share, amlo_morena_share) |>
  pivot_longer(
    ends_with("_share"),
    names_to = "topic",
    values_to = "proportion"
  ) |>
  mutate(
    topic = recode(
      topic,
      morning_conference_share = "Morning press conference",
      amlo_morena_share = "AMLO or MORENA"
    ),
    group = factor(
      group,
      levels = c("All outlets", "Aligned", "Opp. + Independent")
    )
  )

plot <- ggplot(plot_data, aes(month, proportion, color = group)) +
  geom_vline(
    xintercept = randomization_date,
    linetype = "dashed",
    color = "#4D4D4D",
    linewidth = 0.35
  ) +
  geom_line(linewidth = 0.2, alpha = 0.25, na.rm = TRUE) +
  geom_smooth(
    method = "loess",
    formula = y ~ x,
    span = 0.35,
    se = FALSE,
    linewidth = 0.55,
    na.rm = TRUE
  ) +
  annotate(
    "text",
    x = randomization_date,
    y = Inf,
    label = "Randomization",
    angle = 90,
    hjust = 1.05,
    vjust = -0.25,
    size = 2,
    color = "#4D4D4D"
  ) +
  facet_wrap(vars(topic), ncol = 1, scales = "free_y") +
  scale_color_manual(
    values = c(
      "All outlets" = "#666666",
      "Aligned" = "#355C7D",
      "Opp. + Independent" = "#A65D45"
    )
  ) +
  scale_x_date(
    date_breaks = "1 year",
    date_labels = "%Y",
    expand = expansion(mult = c(0, 0.01))
  ) +
  scale_y_continuous(labels = scales::label_percent(accuracy = 1)) +
  labs(
    title = "YouTube topic mentions - all outlets",
    subtitle = "Monthly pooled proportions; Oct. 2020-Oct. 2023; title or description",
    x = NULL,
    y = "Proportion of videos",
    color = NULL
  ) +
  theme_minimal(base_size = 7) +
  theme(
    plot.title = element_text(face = "bold", size = 9),
    plot.subtitle = element_text(size = 6.5),
    strip.text = element_text(face = "bold", size = 7),
    axis.text = element_text(size = 5.5),
    axis.title.y = element_text(size = 6.5),
    legend.position = "bottom",
    legend.text = element_text(size = 6),
    legend.key.width = unit(0.75, "cm"),
    panel.grid.minor = element_blank(),
    plot.margin = margin(4, 5, 3, 4)
  )

output_path <- file.path(
  pdf_output_dir,
  "youtube_mentions_monthly_trends_4x4.pdf"
)
ggsave(output_path, plot, width = 4, height = 4, units = "in", device = "pdf")

cat("Monthly data saved to:", file.path(data_output_dir, "youtube_mentions_monthly.csv"), "\n")
cat("PDF saved to:", output_path, "\n")

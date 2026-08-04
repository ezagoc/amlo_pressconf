# 0.0 Set up the environment
rm(list = ls())
if (requireNamespace("rstudioapi", quietly = TRUE) && rstudioapi::isAvailable()) {
  setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
} else {
  setwd(dirname(normalizePath(sys.frame(1)$ofile, winslash = "/", mustWork = FALSE)))
}
source("../../project_paths.R")

library(arrow)
library(tidyverse)
library(lubridate)
library(scales)
library(patchwork)
library(knitr)

path_da  <- paste0(media_path('data', '06-outcomes', 'comsoc'), '/')
fig_path <- paste0(path_da, 'figures/')
dir.create(fig_path, showWarnings = FALSE, recursive = TRUE)

# ─────────────────────────────────────────────────────────────────────────────
# 0.1  Read data & ensure date columns
# ─────────────────────────────────────────────────────────────────────────────
fix_dates <- function(df) {
  df |>
    mutate(
      fecha.de.contratopedido = if_else(
        !is.na(year.contrato) & !is.na(month.contrato) & !is.na(day.contrato),
        make_date(year.contrato, month.contrato, day.contrato),
        as.Date(fecha.de.contratopedido)
      ),
      fecha.de.gasto = if_else(
        !is.na(year.gasto) & !is.na(month.gasto) & !is.na(day.gasto),
        make_date(year.gasto, month.gasto, day.gasto),
        as.Date(fecha.de.gasto)
      )
    )
}

df      <- read_parquet(paste0(path_da, 'contracts_2018_2024.parquet')) |> fix_dates()
df_full <- read_parquet(paste0(path_da, 'contracts_2012_2024.parquet')) |> fix_dates()

amlo_date <- as.Date("2019-01-01")

election_events <- tibble(
  date  = as.Date(c("2021-06-06", "2022-04-10", "2024-06-02")),
  label = c("Intermediate elections", "Presidential Recall Referendum", "General Election"),
  vjust = c(1.5, 5.5, 1.5)   # stagger 2022 label down to avoid overlap with 2021
)

# ─────────────────────────────────────────────────────────────────────────────
# Helper theme
# ─────────────────────────────────────────────────────────────────────────────
my_theme <- function() {
  theme_minimal() +
    theme(
      plot.title   = element_text(hjust = 0.5, face = "bold"),
      plot.subtitle = element_text(hjust = 0.5),
      axis.text.x  = element_text(angle = 45, hjust = 1)
    )
}

save_plot <- function(p, filename, w = 12, h = 7) {
  print(p)
  ggsave(paste0(fig_path, filename), plot = p, width = w, height = h, dpi = 150)
}

add_events <- function(p, events) {
  for (i in seq_len(nrow(events))) {
    p <- p +
      geom_vline(xintercept = events$date[i], linetype = "dotted",
                 colour = "grey40", linewidth = 0.6) +
      annotate("text", x = events$date[i] + 25, y = Inf,
               vjust = events$vjust[i], hjust = 0,
               label = events$label[i], colour = "grey40", size = 2.5)
  }
  p
}

# ─────────────────────────────────────────────────────────────────────────────
# 1. TIME SERIES: NUMBER OF CONTRACTS (weekly)
# ─────────────────────────────────────────────────────────────────────────────

ts_count_weekly <- function(data, date_col, date_label, year_min, year_max,
                            vline = NULL) {
  p <- data |>
    filter(!is.na(.data[[date_col]])) |>
    mutate(.week = floor_date(.data[[date_col]], "week", week_start = 1)) |>
    count(.week) |>
    filter(.week >= as.Date(paste0(year_min, "-01-01")),
           .week <= as.Date(paste0(year_max, "-12-31"))) |>
    ggplot(aes(.week, n)) +
    geom_col(fill = "#1F78B4", width = 5) +
    scale_x_date(date_breaks = "1 year", date_labels = "%Y") +
    scale_y_continuous(labels = comma) +
    labs(title = paste("Weekly contracts —", date_label),
         x = NULL, y = "# contracts") +
    my_theme()

  p <- add_events(p, election_events)

  if (!is.null(vline))
    p <- p +
      geom_vline(xintercept = vline, linetype = "dashed",
                 colour = "grey20", linewidth = 0.7) +
      annotate("text", x = vline + 25, y = Inf, vjust = 9.5, hjust = 0,
               label = "AMLO takes office", colour = "grey20", size = 2.5)
  p
}

# 2018–2024
p_count_contrato <- ts_count_weekly(df, "fecha.de.contratopedido", "Contract date", 2018, 2024)
p_count_gasto    <- ts_count_weekly(df, "fecha.de.gasto",          "Expense date",  2018, 2024)

fig1 <- (p_count_contrato / p_count_gasto) +
  plot_annotation(title = "Weekly Number of Contracts (2018–2024)",
                  theme = theme(plot.title = element_text(hjust = 0.5, face = "bold")))

save_plot(fig1, "01_count_weekly.png", w = 12, h = 10)

# 2012–2024 (full period, AMLO vline)
p_count_contrato_full <- ts_count_weekly(df_full, "fecha.de.contratopedido", "Contract date", 2012, 2024, vline = amlo_date)
p_count_gasto_full    <- ts_count_weekly(df_full, "fecha.de.gasto",          "Expense date",  2012, 2024, vline = amlo_date)

fig1_full <- (p_count_contrato_full / p_count_gasto_full) +
  plot_annotation(title = "Weekly Number of Contracts (2012–2024)",
                  theme = theme(plot.title = element_text(hjust = 0.5, face = "bold")))

save_plot(fig1_full, "01_count_weekly_full.png", w = 12, h = 10)

# ─────────────────────────────────────────────────────────────────────────────
# 2. TIME SERIES: TOTAL COSTO (quarterly + monthly, total & log)
# ─────────────────────────────────────────────────────────────────────────────

ts_costo_panels <- function(data, date_col, date_label, year_min, year_max,
                            vline = NULL) {

  d <- data |>
    filter(!is.na(.data[[date_col]]), !is.na(costo)) |>
    mutate(.date = .data[[date_col]])

  quarterly <- d |>
    mutate(.q     = quarter(.date),
           .year  = year(.date),
           .qdate = yq(paste0(.year, ": Q", .q))) |>
    filter(.year >= year_min, .year <= year_max) |>
    group_by(.qdate, .year) |>
    summarise(total = sum(costo, na.rm = TRUE), .groups = "drop")

  monthly <- d |>
    mutate(.month = floor_date(.date, "month"),
           .year  = year(.date)) |>
    filter(.year >= year_min, .year <= year_max) |>
    group_by(.month, .year) |>
    summarise(total = sum(costo, na.rm = TRUE), .groups = "drop")

  add_vline <- function(p) {
    p <- add_events(p, election_events)
    if (is.null(vline)) return(p)
    p +
      geom_vline(xintercept = vline, linetype = "dashed",
                 colour = "grey20", linewidth = 0.7) +
      annotate("text", x = vline + 25, y = Inf, vjust = 9.5, hjust = 0,
               label = "AMLO takes office", colour = "grey20", size = 2.5)
  }

  p_quarterly <- add_vline(
    ggplot(quarterly, aes(.qdate, total)) +
      geom_col(fill = "#1F78B4") +
      geom_line(aes(group = 1), colour = "grey30", linewidth = 0.5) +
      scale_x_date(date_breaks = "1 year", date_labels = "%Y") +
      scale_y_continuous(labels = dollar_format(prefix = "$")) +
      labs(title = paste("Quarterly spending —", date_label),
           x = NULL, y = "Total costo (MXN)") +
      my_theme()
  )

  p_quarterly_log <- add_vline(
    ggplot(quarterly, aes(.qdate, total)) +
      geom_col(fill = "#1F78B4") +
      geom_line(aes(group = 1), colour = "grey30", linewidth = 0.5) +
      scale_x_date(date_breaks = "1 year", date_labels = "%Y") +
      scale_y_log10(labels = dollar_format(prefix = "$")) +
      labs(title = paste("Quarterly spending (log) —", date_label),
           x = NULL, y = "Total costo (MXN, log scale)") +
      my_theme()
  )

  p_monthly <- add_vline(
    ggplot(monthly, aes(.month, total)) +
      geom_col(fill = "#1F78B4") +
      scale_x_date(date_breaks = "1 year", date_labels = "%Y") +
      scale_y_continuous(labels = dollar_format(prefix = "$")) +
      labs(title = paste("Monthly spending —", date_label),
           x = NULL, y = "Total costo (MXN)") +
      my_theme()
  )

  p_monthly_log <- add_vline(
    ggplot(monthly, aes(.month, total)) +
      geom_col(fill = "#1F78B4") +
      scale_x_date(date_breaks = "1 year", date_labels = "%Y") +
      scale_y_log10(labels = dollar_format(prefix = "$")) +
      labs(title = paste("Monthly spending (log) —", date_label),
           x = NULL, y = "Total costo (MXN, log scale)") +
      my_theme()
  )

  list(quarterly     = p_quarterly,
       quarterly_log = p_quarterly_log,
       monthly       = p_monthly,
       monthly_log   = p_monthly_log)
}

assemble_and_save_costo <- function(panels, title_base, file_base) {
  fig_total <- (panels$quarterly / panels$monthly) +
    plot_annotation(title = paste(title_base, "— total scale"),
                    theme = theme(plot.title = element_text(hjust = 0.5, face = "bold")))
  fig_log <- (panels$quarterly_log / panels$monthly_log) +
    plot_annotation(title = paste(title_base, "— log scale"),
                    theme = theme(plot.title = element_text(hjust = 0.5, face = "bold")))
  save_plot(fig_total, paste0(file_base, ".png"),     w = 12, h = 12)
  save_plot(fig_log,   paste0(file_base, "_log.png"), w = 12, h = 12)
}

# 2018–2024
panels_costo_contrato <- ts_costo_panels(df, "fecha.de.contratopedido", "Contract date", 2018, 2024)
panels_costo_gasto    <- ts_costo_panels(df, "fecha.de.gasto",          "Expense date",  2018, 2024)

assemble_and_save_costo(panels_costo_contrato, "Total Spending (2018–2024) — Contract date", "02a_costo_contract_date")
assemble_and_save_costo(panels_costo_gasto,    "Total Spending (2018–2024) — Expense date",  "02b_costo_expense_date")

# 2012–2024 (full period, AMLO vline)
panels_costo_contrato_full <- ts_costo_panels(df_full, "fecha.de.contratopedido", "Contract date", 2012, 2024, vline = amlo_date)
panels_costo_gasto_full    <- ts_costo_panels(df_full, "fecha.de.gasto",          "Expense date",  2012, 2024, vline = amlo_date)

assemble_and_save_costo(panels_costo_contrato_full, "Total Spending (2012–2024) — Contract date", "02a_costo_contract_date_full")
assemble_and_save_costo(panels_costo_gasto_full,    "Total Spending (2012–2024) — Expense date",  "02b_costo_expense_date_full")

# ─────────────────────────────────────────────────────────────────────────────
# 3a. TOP 20 BENEFICIARIES BY TOTAL SPENDING
# ─────────────────────────────────────────────────────────────────────────────

df <- read_parquet(paste0(path_da, 'contracts_2018_2024_clean.parquet'))

top20 <- df |>
  filter(!is.na(bene_final), !is.na(costo)) |>
  group_by(bene_final) |>
  summarise(total = sum(costo, na.rm = TRUE), .groups = "drop") |>
  slice_max(total, n = 20) |>
  mutate(bene_final = fct_reorder(bene_final, total))

p3a <- ggplot(top20, aes(total, bene_final)) +
  geom_col(fill = "#1F78B4") +
  scale_x_continuous(labels = dollar_format(prefix = "$")) +
  labs(title = "Top 20 Beneficiaries by Total Spending",
       x = "Total costo (MXN)", y = NULL) +
  my_theme() +
  theme(axis.text.x = element_text(angle = 45, hjust = 1))

save_plot(p3a, "03a_top20_beneficiaries.png", w = 11, h = 8)

# ─────────────────────────────────────────────────────────────────────────────
# 3b. DISTRIBUTION OF CONTRACT SIZES (log10)
# ─────────────────────────────────────────────────────────────────────────────
df_pos <- df |> filter(costo > 0, !is.na(costo))

p3b <- ggplot(df_pos, aes(costo)) +
  geom_histogram(bins = 80, fill = "#1F78B4", colour = "white", linewidth = 0.2) +
  scale_x_log10(labels = dollar_format(prefix = "$")) +
  scale_y_continuous(labels = comma) +
  labs(title = "Distribution of Contract Sizes (log10 scale)",
       x = "Contract amount — costo (MXN, log scale)", y = "Count") +
  my_theme()

save_plot(p3b, "03b_contract_size_distribution.png", w = 10, h = 6)

# ─────────────────────────────────────────────────────────────────────────────
# 3c. SPENDING BY PRODUCT TYPE (top 15)
# ─────────────────────────────────────────────────────────────────────────────
prod_col <- if ("descripcion.producto" %in% colnames(df)) "descripcion.producto" else "producto"

top_prod <- df |>
  filter(!is.na(.data[[prod_col]]), !is.na(costo)) |>
  group_by(producto = .data[[prod_col]]) |>
  summarise(total = sum(costo, na.rm = TRUE), .groups = "drop") |>
  slice_max(total, n = 15) |>
  mutate(producto = fct_reorder(producto, total))

p3c <- ggplot(top_prod, aes(total, producto)) +
  geom_col(fill = "#1F78B4") +
  scale_x_continuous(labels = dollar_format(prefix = "$")) +
  labs(title = "Top 15 Product Types by Total Spending",
       x = "Total costo (MXN)", y = NULL) +
  my_theme() +
  theme(axis.text.x = element_text(angle = 45, hjust = 1))

save_plot(p3c, "03c_spending_by_product.png", w = 11, h = 7)

# ─────────────────────────────────────────────────────────────────────────────
# 4. SUMMARY STATISTICS TABLE
# ─────────────────────────────────────────────────────────────────────────────
amount_cols <- intersect(c("costo", "importe", "iva", "costo.unitario", "iva.del.costo"),
                         colnames(df))

summary_tbl <- df |>
  select(all_of(amount_cols)) |>
  pivot_longer(everything(), names_to = "variable") |>
  group_by(variable) |>
  summarise(
    n        = sum(!is.na(value)),
    n_miss   = sum(is.na(value)),
    mean     = mean(value, na.rm = TRUE),
    sd       = sd(value,   na.rm = TRUE),
    min      = min(value,  na.rm = TRUE),
    p25      = quantile(value, 0.25, na.rm = TRUE),
    median   = median(value, na.rm = TRUE),
    p75      = quantile(value, 0.75, na.rm = TRUE),
    max      = max(value,  na.rm = TRUE),
    n_neg    = sum(value < 0, na.rm = TRUE),
    .groups  = "drop"
  )

latex_tbl <- kable(
  summary_tbl,
  format   = "latex",
  booktabs = TRUE,
  digits   = 2,
  format.args = list(big.mark = ","),
  caption  = "Summary statistics for monetary variables",
  col.names = c("Variable", "N", "Missing", "Mean", "SD",
                "Min", "P25", "Median", "P75", "Max", "N neg.")
)

cat(latex_tbl)
writeLines(latex_tbl, paste0(path_da, 'descriptive_stats_summary.tex'))

message("Done. Figures saved to: ", fig_path)

rm(list = ls())

get_script_dir <- function() {
  cmd_args <- commandArgs(trailingOnly = FALSE)
  file_arg <- "--file="
  script_path <- sub(file_arg, "", cmd_args[grep(file_arg, cmd_args)])

  if (!length(script_path)) {
    return(getwd())
  }

  normalizePath(dirname(script_path[1]), winslash = "/", mustWork = TRUE)
}

setwd(get_script_dir())
source("../../project_paths.R")

library(arrow)
library(tidyverse)
library(lubridate)
library(scales)
library(patchwork)
library(stringi)
library(stringr)

RESULTS_DIR <- dirname(media_output_path('results', 'descriptive_stats', 'comsoc_more', '.keep'))
dir.create(RESULTS_DIR, showWarnings = FALSE, recursive = TRUE)

path_comsoc <- paste0(media_path('data', '06-outcomes', 'comsoc'), '/')

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

my_theme <- function() {
  theme_minimal(base_size = 11) +
    theme(
      plot.title = element_text(hjust = 0.5, face = "bold"),
      plot.subtitle = element_text(hjust = 0.5),
      axis.text.x = element_text(angle = 45, hjust = 1),
      legend.position = "bottom"
    )
}

save_plot <- function(p, filename, w = 12, h = 8, bg = "white") {
  ggsave(
    filename = file.path(RESULTS_DIR, paste0(tools::file_path_sans_ext(filename), ".pdf")),
    plot = p,
    width = w,
    height = h,
    device = grDevices::cairo_pdf,
    bg = bg
  )
}

clean_nombre <- function(x) {
  x |>
    str_to_lower() |>
    stri_trans_general("Latin-ASCII") |>
    str_replace_all("[[:punct:]]", " ") |>
    str_replace_all("\\bsa de cv\\b|\\bs a de c v\\b|\\b s a de c v\\b", " ") |>
    str_replace_all("\\s+", " ") |>
    str_trim()
}

harmonize_nombre <- function(x) {
  case_when(
    str_detect(x, "seguro|imss") ~ "imss",
    str_detect(x, "petroleos mexicanos") ~ "pemex",
    str_detect(x, "cfe") ~ "cfe",
    str_detect(x, "lot|pronosticos") ~ "loteria nacional",
    str_detect(x, "instituto de seguridad y servicios") ~ "issste",
    str_detect(x, "defensa nacional") ~ "sedena",
    str_detect(x, "ipn") ~ "ipn",
    str_detect(x, "agri") ~ "secretaria de agricultura",
    str_detect(x, "bellas") ~ "instituto nacional de bellas artes",
    str_detect(x, "agua") ~ "conagua",
    str_detect(x, "hacienda") ~ "secretaria de hacienda",
    str_detect(x, "consumo") ~ "fonacot",
    str_detect(x, "pueblos indigenas") ~ "inpi",
    str_detect(x, "nacional financiera") ~ "nacional financiera",
    str_detect(x, "comercio") ~ "bancomext",
    str_detect(x, "ciudad de mex") ~ "grupo aeropuertario cdmx",
    str_detect(x, "nacional de las mujeres") ~ "inmujeres",
    str_detect(x, "obras") ~ "banobras",
    str_detect(x, "relaciones") ~ "secretaria de relaciones exteriores",
    str_detect(x, "transportes") ~ "secretaria de comunicacion y transportes",
    str_detect(x, "fondo de cultura") ~ "fondo de cultura economica",
    str_detect(x, "retiro") ~ "consar",
    TRUE ~ x
  )
}

pretty_institution <- function(x) {
  out <- str_to_title(x)
  recode(
    out,
    "Imss" = "IMSS",
    "Pemex" = "PEMEX",
    "Cfe" = "CFE",
    "Issste" = "ISSSTE",
    "Ipn" = "IPN",
    "Inpi" = "INPI",
    "Sedena" = "SEDENA",
    "Conagua" = "CONAGUA",
    "Fonacot" = "FONACOT",
    "Consar" = "CONSAR",
    "Inmujeres" = "INMUJERES",
    .default = out
  )
}

slugify_name <- function(x) {
  x |>
    str_to_lower() |>
    str_replace_all("[^a-z0-9]+", "_") |>
    str_replace_all("^_|_$", "")
}

money_short <- label_dollar(prefix = "$", scale_cut = cut_short_scale())
START_DATE <- as.Date("2018-01-01")
END_DATE <- as.Date("2024-12-31")

df <- read_parquet(paste0(path_comsoc, "contracts_2018_2024.parquet")) |>
  fix_dates() |>
  mutate(
    nombre_clean = nombre |> clean_nombre() |> harmonize_nombre()
  ) |>
  filter(
    (is.na(fecha.de.contratopedido) | fecha.de.contratopedido >= START_DATE),
    (is.na(fecha.de.gasto) | fecha.de.gasto >= START_DATE),
    (is.na(fecha.de.contratopedido) | fecha.de.contratopedido <= END_DATE),
    (is.na(fecha.de.gasto) | fecha.de.gasto <= END_DATE)
  ) |>
  filter(!is.na(nombre_clean), nombre_clean != "")

institution_stats <- df |>
  group_by(nombre_clean) |>
  summarise(
    n_contracts_total = n(),
    total_spent = sum(costo, na.rm = TRUE),
    avg_contract_value = total_spent / n_contracts_total,
    first_contract_date = min(fecha.de.contratopedido, na.rm = TRUE),
    last_contract_date = max(fecha.de.contratopedido, na.rm = TRUE),
    first_spend_date = min(fecha.de.gasto, na.rm = TRUE),
    last_spend_date = max(fecha.de.gasto, na.rm = TRUE),
    .groups = "drop"
  ) |>
  arrange(desc(total_spent))

# Assumption: the "top 25 institutions" are defined by total spending over 2018-2024.
top25_stats <- institution_stats |>
  slice_max(total_spent, n = 25, with_ties = FALSE) |>
  mutate(
    display_name = pretty_institution(nombre_clean),
    facet_label = paste0(
      display_name,
      "\nContracts: ", comma(n_contracts_total),
      " | Spent: ", money_short(total_spent),
      "\nAvg/contract: ", money_short(avg_contract_value)
    )
  )

top25_names <- top25_stats$nombre_clean
top10_names <- top25_stats |>
  slice_head(n = 10) |>
  pull(nombre_clean)

daily_contracts <- df |>
  filter(nombre_clean %in% top25_names, !is.na(fecha.de.contratopedido)) |>
  transmute(
    nombre_clean,
    contract_day = as.Date(fecha.de.contratopedido)
  ) |>
  count(nombre_clean, contract_day, name = "n_contracts")

day_grid <- seq(
  START_DATE,
  END_DATE,
  by = "day"
)

daily_contracts <- daily_contracts |>
  group_by(nombre_clean) |>
  complete(contract_day = day_grid, fill = list(n_contracts = 0)) |>
  ungroup() |>
  left_join(
    top25_stats |>
      select(nombre_clean, display_name, facet_label),
    by = "nombre_clean"
  ) |>
  mutate(
    display_name = factor(display_name, levels = top25_stats$display_name),
    facet_label = factor(facet_label, levels = top25_stats$facet_label)
  )

monthly_spending <- df |>
  filter(nombre_clean %in% top25_names, !is.na(fecha.de.gasto), !is.na(costo)) |>
  transmute(
    nombre_clean,
    spend_month = floor_date(as.Date(fecha.de.gasto), "month"),
    costo
  ) |>
  group_by(nombre_clean, spend_month) |>
  summarise(
    total_spent = sum(costo, na.rm = TRUE),
    n_contracts_in_month = n(),
    .groups = "drop"
  )

month_grid <- seq(
  floor_date(START_DATE, "month"),
  floor_date(END_DATE, "month"),
  by = "month"
)

monthly_spending <- monthly_spending |>
  group_by(nombre_clean) |>
  complete(
    spend_month = month_grid,
    fill = list(total_spent = 0, n_contracts_in_month = 0)
  ) |>
  ungroup() |>
  left_join(
    top25_stats |>
      select(nombre_clean, display_name, facet_label),
    by = "nombre_clean"
  ) |>
  mutate(
    display_name = factor(display_name, levels = top25_stats$display_name),
    facet_label = factor(facet_label, levels = top25_stats$facet_label)
  )

p_total_contracts <- top25_stats |>
  mutate(display_name = fct_reorder(display_name, n_contracts_total)) |>
  ggplot(aes(x = n_contracts_total, y = display_name)) +
  geom_col(fill = "#1F78B4") +
  scale_x_continuous(labels = comma) +
  labs(
    title = "Top 25 Institutions by Total Contracts",
    subtitle = "Ranking uses institutions selected by total spending over 2018-2024",
    x = "Contracts in the full period",
    y = NULL
  ) +
  my_theme()

p_total_spending <- top25_stats |>
  mutate(display_name = fct_reorder(display_name, total_spent)) |>
  ggplot(aes(x = total_spent, y = display_name)) +
  geom_col(fill = "#E31A1C") +
  scale_x_continuous(labels = money_short) +
  labs(
    title = "Top 25 Institutions by Total Spending",
    subtitle = "Same top-25 selection used in the time-series plots",
    x = "Total spent in the full period",
    y = NULL
  ) +
  my_theme()

summary_panel <- p_total_contracts / p_total_spending +
  plot_annotation(
    title = "Overall COMSOC Statistics for Top 25 Institutions",
    theme = theme(plot.title = element_text(hjust = 0.5, face = "bold"))
  )

save_plot(summary_panel, "top25_institutions_overall_stats", w = 12, h = 12)

make_overlay_panel <- function(chunk_names, chunk_id) {
  chunk_stats <- top25_stats |>
    filter(nombre_clean %in% chunk_names)

  chunk_levels <- chunk_stats$display_name

  daily_chunk <- daily_contracts |>
    filter(nombre_clean %in% chunk_names) |>
    mutate(display_name = factor(display_name, levels = chunk_levels))

  monthly_chunk <- monthly_spending |>
    filter(nombre_clean %in% chunk_names) |>
    mutate(display_name = factor(display_name, levels = chunk_levels))

  p_daily_overlay <- ggplot(
    daily_chunk,
    aes(x = contract_day, y = n_contracts, colour = display_name)
  ) +
    geom_line(linewidth = 0.35, alpha = 0.85) +
    scale_x_date(date_breaks = "1 year", date_labels = "%Y") +
    scale_y_continuous(labels = comma) +
    guides(colour = guide_legend(ncol = 3)) +
    labs(
      title = "Daily Number of Contracts by Institution",
      subtitle = paste0(
        "Institutions ",
        min(which(top25_stats$nombre_clean %in% chunk_names)),
        "-",
        max(which(top25_stats$nombre_clean %in% chunk_names)),
        " of top 25 by total spending"
      ),
      x = NULL,
      y = "Contracts per day",
      colour = NULL
    ) +
    my_theme() +
    theme(
      legend.text = element_text(size = 8),
      legend.key.width = unit(14, "pt")
    )

  p_monthly_overlay <- ggplot(
    monthly_chunk,
    aes(x = spend_month, y = total_spent, colour = display_name)
  ) +
    geom_line(linewidth = 0.45, alpha = 0.9) +
    geom_point(size = 0.7, alpha = 0.9) +
    scale_x_date(date_breaks = "1 year", date_labels = "%Y") +
    scale_y_continuous(labels = money_short) +
    guides(colour = guide_legend(ncol = 3)) +
    labs(
      title = "Monthly Spending by Institution",
      subtitle = paste0(
        "Institutions ",
        min(which(top25_stats$nombre_clean %in% chunk_names)),
        "-",
        max(which(top25_stats$nombre_clean %in% chunk_names)),
        " of top 25 by total spending"
      ),
      x = NULL,
      y = "Total spent per month",
      colour = NULL
    ) +
    my_theme() +
    theme(
      legend.text = element_text(size = 8),
      legend.key.width = unit(14, "pt")
    )

  overlay_panel <- p_daily_overlay / p_monthly_overlay +
    plot_annotation(
      title = paste0("Top 25 Institution Time Series - Group ", chunk_id),
      theme = theme(plot.title = element_text(hjust = 0.5, face = "bold"))
    )

  save_plot(
    overlay_panel,
    paste0("top25_institutions_overlay_timeseries_group_", chunk_id),
    w = 14,
    h = 14
  )

  invisible(overlay_panel)
}

top25_groups <- split(top25_stats$nombre_clean, ceiling(seq_along(top25_names) / 5))
purrr::iwalk(top25_groups, make_overlay_panel)

daily_contracts_top10 <- daily_contracts |>
  filter(nombre_clean %in% top10_names) |>
  mutate(
    facet_label = factor(
      facet_label,
      levels = top25_stats |>
        filter(nombre_clean %in% top10_names) |>
        pull(facet_label)
    )
  )

monthly_spending_top10 <- monthly_spending |>
  filter(nombre_clean %in% top10_names) |>
  mutate(
    facet_label = factor(
      facet_label,
      levels = top25_stats |>
        filter(nombre_clean %in% top10_names) |>
        pull(facet_label)
    )
  )

walk(top10_names, function(inst_name) {
  inst_stats <- top25_stats |>
    filter(nombre_clean == inst_name)

  inst_data <- daily_contracts_top10 |>
    filter(nombre_clean == inst_name)

  p_inst_daily <- ggplot(inst_data, aes(x = contract_day, y = n_contracts)) +
    geom_line(colour = "#1F78B4", linewidth = 0.35) +
    scale_x_date(date_breaks = "1 year", date_labels = "%Y") +
    scale_y_continuous(labels = comma) +
    labs(
      title = paste0(inst_stats$display_name, " - Daily Number of Contracts"),
      subtitle = paste0(
        "2018-2024 | Contracts: ", comma(inst_stats$n_contracts_total),
        " | Spent: ", money_short(inst_stats$total_spent)
      ),
      x = NULL,
      y = "Contracts per day"
    ) +
    my_theme()

  save_plot(
    p_inst_daily,
    paste0(
      "top10_daily_contracts_",
      sprintf("%02d", match(inst_name, top10_names)),
      "_",
      slugify_name(inst_name)
    ),
    w = 14,
    h = 5
  )
})

p_daily_facets <- ggplot(daily_contracts_top10, aes(x = contract_day, y = n_contracts)) +
  geom_line(colour = "#1F78B4", linewidth = 0.28) +
  scale_x_date(date_breaks = "2 years", date_labels = "%Y") +
  scale_y_continuous(labels = comma) +
  facet_wrap(~facet_label, ncol = 5, scales = "free_y") +
  labs(
    title = "Daily Number of Contracts - Faceted Top 10 Institutions",
    subtitle = "Top 10 by total spending; facet labels include full-period totals",
    x = NULL,
    y = "Contracts per day"
  ) +
  my_theme() +
  theme(
    legend.position = "none",
    strip.text = element_text(face = "bold", size = 8),
    axis.text.x = element_text(angle = 45, hjust = 1, size = 7),
    panel.spacing = unit(0.7, "lines")
  )

save_plot(p_daily_facets, "top10_institutions_daily_contracts_faceted", w = 24, h = 10)

p_monthly_facets <- ggplot(monthly_spending_top10, aes(x = spend_month, y = total_spent)) +
  geom_col(fill = "#E31A1C", width = 25) +
  scale_x_date(date_breaks = "2 years", date_labels = "%Y") +
  scale_y_continuous(labels = money_short) +
  facet_wrap(~facet_label, ncol = 5, scales = "free_y") +
  labs(
    title = "Monthly Spending - Faceted Top 10 Institutions",
    subtitle = "Top 10 by total spending; facet labels include full-period totals",
    x = NULL,
    y = "Total spent per month"
  ) +
  my_theme() +
  theme(
    legend.position = "none",
    strip.text = element_text(face = "bold", size = 8),
    axis.text.x = element_text(angle = 45, hjust = 1, size = 7),
    panel.spacing = unit(0.7, "lines")
  )

save_plot(p_monthly_facets, "top10_institutions_monthly_spending_faceted", w = 24, h = 10)

top25_stats |>
  select(
    Institution = display_name,
    Contracts = n_contracts_total,
    TotalSpent = total_spent,
    AvgContractValue = avg_contract_value
  ) |>
  arrange(desc(TotalSpent))

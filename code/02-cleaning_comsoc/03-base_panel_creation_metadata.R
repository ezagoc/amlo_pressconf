# Create the geocoded newspaper metadata and balanced panels.
rm(list = ls())

# Works with "Source" in RStudio and with Rscript from the repository root.
if (requireNamespace("rstudioapi", quietly = TRUE) && rstudioapi::isAvailable()) {
  setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
} else if (dir.exists(file.path(getwd(), "code", "02-cleaning_comsoc"))) {
  setwd(file.path(getwd(), "code", "02-cleaning_comsoc"))
}

source("../../project_paths.R")
source("../../src/metadata_helpers.R")
source("../../src/balanced_metadata_panel.R")

library(tidyverse)
library(arrow)

data_path <- media_path("data", "00-newspaper_data")
output_path <- file.path(data_path, "processed")
dir.create(output_path, recursive = TRUE, showWarnings = FALSE)

meta <- readxl::read_xlsx(
  file.path(data_path, "newspaper_metadata.xlsx"),
  sheet = "Hoja1"
)
news <- readxl::read_xlsx(
  file.path(data_path, "mexican_newspapers.xlsx"),
  sheet = "Periodicos"
)

# Repeated columns always come from meta, the more complete source.
metadata <- merge_newspaper_metadata(meta, news) |>
  apply_reviewed_conference_keys() |>
  add_metadata_dummies()

metadata <- add_office_geocodes(
  metadata,
  cache_file = file.path(output_path, "nominatim_office_geocodes_v3.csv")
)

panel_weekly_2021_2022 <- metadata_to_balanced_panel(
  metadata,
  frequency = "weekly",
  from = "2021-01-01",
  to = "2022-12-31"
)

panel_daily_2021_2022 <- metadata_to_balanced_panel(
  metadata,
  frequency = "daily",
  from = "2021-01-01",
  to = "2022-12-31"
)

write_parquet(metadata, file.path(output_path, "newspaper_metadata_geocoded.parquet"))
write_parquet(
  panel_weekly_2021_2022,
  file.path(output_path, "newspaper_metadata_panel_weekly_2021_2022.parquet")
)
write_parquet(
  panel_daily_2021_2022,
  file.path(output_path, "newspaper_metadata_panel_daily_2021_2022.parquet")
)

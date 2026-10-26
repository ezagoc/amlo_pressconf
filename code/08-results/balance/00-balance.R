# Starter dataset for baseline balance / future covariate adjustment. No models.
# Run from the repo root: Rscript code/08-results/balance/00-balance.R
# Or open this file in RStudio and source it. Outputs remain in memory by default.
suppressPackageStartupMessages({library(dplyr); library(tidyr); library(arrow)})
script_arg <- grep("^--file=", commandArgs(FALSE), value = TRUE)
script_path <- if (length(script_arg)) sub("^--file=", "", script_arg[[1]]) else
  if (requireNamespace("rstudioapi", quietly = TRUE) && rstudioapi::isAvailable())
    rstudioapi::getActiveDocumentContext()$path else
    file.path(getwd(), "code/08-results/balance/00-balance.R")
root <- normalizePath(file.path(dirname(script_path), "../../.."), mustWork = TRUE)
source(file.path(root, "project_paths.R"))
source(file.path(root, "src/baseline_history.R"))

# ---- Change these settings ---------------------------------------------------
LOTTERY_DATE <- as.Date("2022-04-18")
ANALYSIS_FROM <- LOTTERY_DATE
ANALYSIS_TO <- as.Date("2024-12-31")  # Current daily FEct analysis window.
HISTORY_FROM <- as.Date("2018-12-01") # Presidency years begin every December 1.
EXCLUDE_ATTENDANCE_MONTHS <- "2021-11" # Exclude recorded attendance/ratios; keep questions.
SAVE_OUTPUTS <- FALSE
stopifnot(ANALYSIS_FROM <= ANALYSIS_TO, HISTORY_FROM < LOTTERY_DATE)
source_dir <- media_path("data/06-outcomes/deduplicated_source_panels")

# ---- Full metadata and source IDs --------------------------------------------
metadata <- read_parquet(media_path("data/00-newspaper_data/processed/newspaper_metadata_geocoded.parquet"))
crosswalk <- read_parquet(file.path(source_dir, "metadata_outcome_crosswalk.parquet")) |>
  select(metadata_id, outcome, entity_id) |> distinct()
history_links <- filter(crosswalk, outcome %in% c("attendance", "questions", "contracts"))
stopifnot(!anyDuplicated(metadata$metadata_id), !anyNA(metadata$metadata_id),
          !anyDuplicated(history_links[c("metadata_id", "outcome")]))
# Keep the full crosswalk separately: an outlet may have multiple YouTube IDs.
# Attendance/questions/contracts have the one-ID-per-metadata-row mapping used here.
source_ids <- history_links |>
  pivot_wider(names_from = outcome, values_from = entity_id, names_glue = "{outcome}_entity_id")

# ---- Histories BEFORE restricting the analysis panel -------------------------
# Do not use zero-filled full-panel columns for histories: source panels retain
# flags distinguishing unavailable dates / unmatched outlets from observed zeros.
attendance_history <- open_dataset(file.path(source_dir, "attendance_entity_daily_panel.parquet")) |>
  filter(date >= HISTORY_FROM, date < LOTTERY_DATE) |>
  select(entity_id, date, source_entity_matched, source_date_observed,
         attendance_n_journalists_recorded, attendance_n_journalists_assumed) |>
  collect() |>
  rename(attendance_entity_id = entity_id, attendance_matched = source_entity_matched,
         attendance_observed = source_date_observed,
         attendance_recorded = attendance_n_journalists_recorded,
         attendance_assumed = attendance_n_journalists_assumed)
question_history <- open_dataset(file.path(source_dir, "questions_entity_daily_panel.parquet")) |>
  filter(date >= HISTORY_FROM, date < LOTTERY_DATE) |>
  select(entity_id, date, source_entity_matched, source_date_observed, questions_n) |>
  collect() |>
  rename(questions_entity_id = entity_id, questions_matched = source_entity_matched,
         questions_observed = source_date_observed, questions = questions_n)
stopifnot(!anyDuplicated(attendance_history[c("attendance_entity_id", "date")]),
          !anyDuplicated(question_history[c("questions_entity_id", "date")]))
history_days <- crossing(metadata_id = metadata$metadata_id,
                         date = seq(HISTORY_FROM, LOTTERY_DATE - 1, by = "day")) |>
  left_join(source_ids, by = "metadata_id", relationship = "many-to-one") |>
  left_join(attendance_history, by = c("attendance_entity_id", "date"), relationship = "many-to-one") |>
  left_join(question_history, by = c("questions_entity_id", "date"), relationship = "many-to-one") |>
  prepare_baseline_days(EXCLUDE_ATTENDANCE_MONTHS)

# year1 = Dec 2018-Nov 2019; year2 = Dec 2019-Nov 2020; year3 = Dec 2020-Nov 2021;
# year4 = partial Dec 2021-Apr 17, 2022. last_year / last_2years end Apr 17, 2022.
windows <- baseline_windows(LOTTERY_DATE, HISTORY_FROM)
baseline_long <- summarise_baseline_history(history_days, windows, LOTTERY_DATE)

# Contracts use fecha.de.contratopedido upstream, not payment/policy dates.
# costo = money measure used in existing graphs (nominal MXN, not deflated).
# importe is retained separately; do not add it to costo.
# received_n = sum of daily distinct contract/order IDs; n = source line items.
# Thus received_n is NOT a re-deduplication of IDs over the entire window, and
# contracts with missing IDs may contribute line items/value but not received_n.
# Unlike attendance, November 2021 is retained for every contract measure.
contract_history <- open_dataset(file.path(source_dir, "contracts_entity_daily_panel.parquet")) |>
  filter(date >= HISTORY_FROM, date < LOTTERY_DATE) |>
  select(entity_id, date, source_entity_matched, source_date_observed,
         contracts_costo, contracts_importe, contracts_received_n, contracts_n) |>
  collect() |> rename(contracts_entity_id = entity_id)
contract_baseline_entities <- summarise_contract_history(contract_history, windows, LOTTERY_DATE)
contract_baseline_metadata <- source_ids |>
  select(metadata_id, contracts_entity_id) |>
  filter(!is.na(contracts_entity_id)) |>
  inner_join(contract_baseline_entities, by = "contracts_entity_id", relationship = "many-to-many") |>
  select(-contracts_entity_id)
stopifnot(!anyDuplicated(contract_baseline_metadata[c("metadata_id", "window")]))
baseline_long <- baseline_long |>
  left_join(contract_baseline_metadata, by = c("metadata_id", "window"), relationship = "one-to-one") |>
  mutate(contracts_observed_days = coalesce(contracts_observed_days, 0L))
baseline_covariates <- baseline_long |>
  pivot_wider(id_cols = metadata_id, names_from = window,
              values_from = -c(metadata_id, window), names_glue = "pre_{.value}_{window}")

# Main objects: one row per metadata outlet, and one row per outlet-day.
# Preserve every metadata column (including ideology/type/coverage dummies).
balance_outlets <- metadata |>
  left_join(source_ids, by = "metadata_id", relationship = "one-to-one") |>
  left_join(baseline_covariates, by = "metadata_id", relationship = "one-to-one")
balance_panel <- open_dataset(media_path("data/06-outcomes/final_panel/final_daily_panel_2012_2025.parquet")) |>
  filter(date >= ANALYSIS_FROM, date <= ANALYSIS_TO) |> collect()
stopifnot(setequal(balance_panel$metadata_id, metadata$metadata_id))
balance_panel <- balance_panel |>
  # Replace embedded metadata with the full processed metadata, avoiding .x/.y.
  select(-any_of(setdiff(names(metadata), "metadata_id")),
         # Legacy cumulative fields mix periods / use another cutoff; not controls.
         -any_of(c("attendance_total", "attendance_before", "attendance_after"))) |>
  left_join(balance_outlets, by = "metadata_id", relationship = "many-to-one") |>
  arrange(metadata_id, date)
stopifnot(!anyDuplicated(balance_outlets$metadata_id),
          !anyDuplicated(balance_panel[c("metadata_id", "date")]),
          nrow(balance_panel) == nrow(metadata) * (as.integer(ANALYSIS_TO - ANALYSIS_FROM) + 1L),
          all(windows$to < LOTTERY_DATE))

# Counts are observed-history totals, not complete histories when sources have
# gaps. Use *_observed_days alongside them. No observed days -> NA; ratio with
# zero attendance -> NA. November 2021 questions remain in question totals.
# Corrected attendance may include explicitly flagged question-based lower
# bounds on unavailable dates (including November); recorded attendance does not.
# Shared source IDs intentionally give identical histories to multiple metadata
# rows. Never sum these rows to get source totals; deduplicate by source entity.
# Current metadata are NOT automatically pre-lottery characteristics. Frozen
# histories/metadata are absorbed by outlet FE unless interacted with time, etc.
# Question speaker-attribution audit corrections are still pending upstream.
print(windows)
cat("Balance data:", nrow(balance_outlets), "metadata outlets;", nrow(balance_panel),
    "daily rows;", ncol(baseline_covariates) - 1L, "historical covariates.\n")

if (SAVE_OUTPUTS) {
  output_dir <- media_path("data/06-outcomes/balance")
  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
  write_parquet(balance_panel, file.path(output_dir, "balance_daily_panel.parquet"), compression = "zstd")
  write_parquet(balance_outlets, file.path(output_dir, "balance_outlets.parquet"), compression = "zstd")
  saveRDS(list(windows = windows, lottery = LOTTERY_DATE, analysis_from = ANALYSIS_FROM,
               analysis_to = ANALYSIS_TO, excluded_attendance_months = EXCLUDE_ATTENDANCE_MONTHS),
          file.path(output_dir, "balance_settings.rds"))
}

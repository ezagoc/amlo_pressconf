# Full post-lottery balance, 18-month histories and freshly read metadata.
# Run from the repository root. Does not modify upstream workbooks or panels.
suppressPackageStartupMessages({library(dplyr); library(tidyr); library(arrow); library(fixest)})
source("project_paths.R")
source("src/metadata_helpers.R")
setFixest_nthreads(1)
out <- "output/balance/full_post_18m_metadata"
dir.create(out, recursive = TRUE, showWarnings = FALSE)
h <- readRDS("output/balance/historical_outcomes/models.rds")
j <- readRDS("output/balance/joint_by_window/models.rds")
base <- j$raw_samples$ratio_18m
meta_file <- media_path("data/00-newspaper_data/newspaper_metadata.xlsx")
news_file <- media_path("data/00-newspaper_data/mexican_newspapers.xlsx")
meta <- merge_newspaper_metadata(
  readxl::read_xlsx(meta_file, sheet = "Hoja1"),
  readxl::read_xlsx(news_file, sheet = "Periodicos")) |>
  apply_reviewed_conference_keys() |> add_metadata_dummies()
old <- read_parquet(media_path("data/00-newspaper_data/processed/newspaper_metadata_geocoded.parquet"))
# Sequential IDs are safe only if the source rows have not been reordered.
stopifnot(identical(meta$name.page, old$name.page), identical(meta$metadata_id, old$metadata_id))
cw <- read_parquet(media_path("data/06-outcomes/deduplicated_source_panels/metadata_outcome_crosswalk.parquet"))
resolved <- read.csv("output/balance/prior_ratios/source_mapping.csv") |>
  filter(!excluded) |> select(attendance, questions) |> mutate(unit_id = attendance)
links <- cw |> filter(outcome %in% c("attendance", "questions")) |>
  select(metadata_id, outcome, entity_id) |> distinct() |>
  pivot_wider(names_from = outcome, values_from = entity_id) |>
  inner_join(resolved, by = c("attendance", "questions"), relationship = "many-to-one") |>
  filter(unit_id %in% base$unit_id) |> select(metadata_id, unit_id)

meta <- meta |> mutate(
  founding_year_numeric = ifelse(grepl("^[0-9]{4}$", trimws(year_founded)),
                                suppressWarnings(as.numeric(year_founded)), NA_real_),
  age_2022 = ifelse(founding_year_numeric <= 2022, 2022 - founding_year_numeric, NA_real_),
  media_print_any = pmax(media_print, media_periodico),
  # Whole-word matches avoid treating 'international' as national or
  # 'multistate' alone as state coverage. No upstream dummy is changed.
  coverage_national = as.integer(grepl("\\bnational\\b", tolower(coalesce(coverage.scope, "")))),
  coverage_state = as.integer(grepl("\\bstate\\b", tolower(coalesce(coverage.scope, "")))))

# Geographic definitions are configured explicitly below after user review.
geo_file <- "code/08-results/balance/metadata_geography.R"
if (!file.exists(geo_file)) stop("Geographic definitions must be resolved before running this report.")
source(geo_file)
meta <- add_balance_geography(meta)
writeLines(geography_definition, file.path(out, "geography_definition.txt"))
meta_labels <- c(age_2022 = "Age in 2022 (years)", media_print_any = "Print / newspaper",
  media_digital = "Digital", media_social_media = "Social media", media_radio = "Radio",
  media_television = "Television", coverage_national = "National coverage",
  coverage_state = "State coverage", mexico_city = "Mexico City outlet",
  metropolitan_area = "Metropolitan-area outlet")
flags <- setdiff(names(meta_labels), "age_2022")
consensus <- function(x) { z <- unique(x[is.finite(x)]); if (length(z) == 1) z else NA_real_ }
rows <- links |> left_join(meta, by = "metadata_id", relationship = "many-to-one")
units <- rows |> group_by(unit_id) |> summarise(
  outlet_names = paste(sort(unique(name.page)), collapse = " / "),
  metadata_ids = paste(sort(unique(metadata_id)), collapse = " | "),
  founding_age_conflict = n_distinct(age_2022, na.rm = TRUE) > 1,
  age_2022 = consensus(age_2022),
  across(all_of(flags), ~ as.numeric(any(.x == 1, na.rm = TRUE))), .groups = "drop")
stopifnot(setequal(units$unit_id, base$unit_id), !anyDuplicated(units$unit_id))
raw <- base |> left_join(units, by = "unit_id", relationship = "many-to-one")
stopifnot(nrow(raw) == nrow(base), !anyDuplicated(raw[c("unit_id", "date")]),
          all(raw$records > 0), all(raw$date >= as.Date("2022-04-18")),
          all(raw$date <= as.Date("2024-09-30")), all(raw$ask %in% 0:1))
informative <- function(d) d |> group_by(date) |> filter(any(ask == 1), any(ask == 0)) |> ungroup()
spec <- bind_rows(h$spec, tibble(metric = names(meta_labels), label = unname(meta_labels),
                               family = "Metadata", transformation = "Raw"))
individual_fits <- individual_samples <- list()
individual <- bind_rows(lapply(spec$metric, function(v) {
  if (v %in% h$spec$metric) {
    # Retain the established observed-history cohorts, common across windows.
    d <- h$samples[[v]] |> mutate(x = ratio_18m)
  } else d <- raw |> mutate(x = .data[[v]]) |> filter(is.finite(x)) |> informative()
  fit <- feols(x ~ ask | date, d, cluster = ~unit_id, notes = FALSE)
  ct <- coeftable(fit)["ask", ]; ci <- confint(fit, "ask")
  individual_fits[[v]] <<- fit; individual_samples[[v]] <<- d
  tibble(metric = v, estimate = ct[[1]], se = ct[[2]], ci_low = ci[[1]], ci_high = ci[[2]],
         p_value = ct[[4]], n = nobs(fit), units = n_distinct(d$unit_id), dates = n_distinct(d$date))
})) |> left_join(spec, by = "metric")

# Test histories alone, metadata alone, and all requested covariates jointly.
# Missingness indicators remain unrestricted; zero placeholders are model-only.
joint_fits <- joint_samples <- missing_maps <- list()
groups <- list(histories = h$spec$metric, metadata = names(meta_labels),
               combined = spec$metric)
joint <- bind_rows(lapply(names(groups), function(g) {
  vars <- groups[[g]]; d <- raw; patterns <- list(); map <- list()
  for (v in vars) {
    miss <- !is.finite(d[[v]]); scale <- sd(d[[v]][!miss])
    stopifnot(is.finite(scale), scale > 0)
    indicator <- NA_character_
    if (any(miss)) {
      same <- names(patterns)[vapply(patterns, identical, logical(1), miss)]
      indicator <- if (length(same)) same[[1]] else paste0("missing_", v)
      if (!length(same)) { patterns[[indicator]] <- miss; d[[indicator]] <- as.integer(miss) }
    }
    d[[v]] <- ifelse(miss, 0, d[[v]] / scale)
    map[[v]] <- tibble(metric = v, indicator = indicator, scale = scale,
                      missing_days = sum(miss), missing_units = n_distinct(d$unit_id[miss]))
  }
  terms <- c(vars, names(patterns))
  fml <- as.formula(paste("ask ~", paste(terms, collapse = " + "), "| date"))
  fit <- feols(fml, d, cluster = ~unit_id, notes = FALSE)
  # Never silently change the requested null when a column is collinear.
  stopifnot(is.null(fit$collin.var), all(terms %in% names(coef(fit))))
  V <- vcov(fit)[vars, vars, drop = FALSE]; b <- coef(fit)[vars]
  C <- cov2cor(V); ev <- eigen(C, symmetric = TRUE, only.values = TRUE)$values
  stopifnot(min(ev) > .Machine$double.eps * length(vars) * 100)
  wt <- wald(fit, keep = paste0("^(", paste(vars, collapse = "|"), ")$"), print = FALSE)
  z <- b / sqrt(diag(V)); independent_F <- drop(crossprod(z, solve(C, z))) / length(vars)
  stopifnot(isTRUE(all.equal(wt$stat, independent_F, tolerance = 1e-6)),
            wt$df1 == length(vars), wt$df2 == n_distinct(d$unit_id) - 1)
  # Check invariance to centering observed entries while missing placeholders stay 0.
  centered <- d
  for (v in vars) { ok <- is.finite(raw[[v]]); centered[[v]][ok] <- d[[v]][ok] - mean(d[[v]][ok]) }
  refit <- feols(fml, centered, cluster = ~unit_id, notes = FALSE)
  check <- wald(refit, keep = paste0("^(", paste(vars, collapse = "|"), ")$"), print = FALSE)
  stopifnot(abs(check$stat - wt$stat) / max(1, abs(wt$stat)) < 1e-5)
  joint_fits[[g]] <<- fit; joint_samples[[g]] <<- d; missing_maps[[g]] <<- bind_rows(map)
  tibble(test = g, F = wt$stat, df1 = wt$df1, df2 = wt$df2, p_value = wt$p,
         n = nobs(fit), units = n_distinct(d$unit_id), dates = n_distinct(d$date),
         missingness_controls = length(patterns), covariance_condition = max(ev) / min(ev))
}))
stopifnot(isTRUE(all.equal(joint$F[joint$test == "histories"],
  j$tests$F[j$tests$window == "ratio_18m" & j$tests$test == "histories"], tolerance = 1e-6)))
audit <- rows |> select(unit_id, metadata_id, name.page, year_founded, age_2022,
                       city.headq, municipality, coverage.scope, type.media, all_of(flags))
changes <- meta |> select(metadata_id, name.page, year_founded) |>
  left_join(old |> select(metadata_id, previous_year_founded = year_founded), by = "metadata_id") |>
  filter(coalesce(year_founded, "<NA>") != coalesce(previous_year_founded, "<NA>"))
source_info <- tibble(path = c(meta_file, news_file),
                     md5 = unname(tools::md5sum(c(meta_file, news_file))),
                     modified = as.character(file.info(c(meta_file, news_file))$mtime))
for (v in c("individual", "joint", "units", "audit", "changes", "source_info"))
  write.csv(get(v), file.path(out, paste0(v, ".csv")), row.names = FALSE)
saveRDS(list(individual = individual, joint = joint, individual_fits = individual_fits,
             individual_samples = individual_samples, joint_fits = joint_fits,
             joint_samples = joint_samples, missing_maps = missing_maps, raw = raw,
             units = units, audit = audit, spec = spec, source_info = source_info,
             geography_definition = geography_definition), file.path(out, "models.rds"))
writeLines(capture.output(sessionInfo()), file.path(out, "session_info.txt"))
print(individual |> select(label, estimate, p_value, n, units), n = 30)
print(joint, width = 160)
cat("Updated founding entries:", nrow(changes), "\n")

# Joint balance of all twelve histories, separately for each pre-lottery window.
# Requires the current (contract NA-preserving) 05-historical_outcome_balance.R run.
suppressPackageStartupMessages({library(dplyr); library(tidyr); library(fixest)})
arg <- grep("^--file=", commandArgs(FALSE), value = TRUE)
script <- if (length(arg)) sub("^--file=", "", arg[[1]]) else
  file.path(getwd(), "code/08-results/balance/07-joint_balance_by_window.R")
root <- normalizePath(file.path(dirname(script), "../../.."), mustWork = TRUE)
prior <- readRDS(file.path(root, "output/balance/prior_ratios/models.rds"))
hist <- readRDS(file.path(root, "output/balance/historical_outcomes/models.rds"))
base <- prior$base |> select(unit_id, date, ask, records)
vars <- hist$spec$metric
out <- file.path(root, "output/balance/joint_by_window")
dir.create(out, recursive = TRUE, showWarnings = FALSE)
setFixest_nthreads(1)
stopifnot(!anyDuplicated(base[c("unit_id", "date")]), all(base$records > 0),
          all(base$date >= as.Date("2022-04-18")),
          all(base$date <= as.Date("2024-09-27")), all(hist$windows$to < as.Date("2022-04-18")),
          all(is.na(hist$contracts$contract_value[hist$contracts$beneficiary_dates == 0])))
models <- samples <- raw_samples <- scales <- missing_maps <- list()
test_rows <- coefficient_rows <- audit_rows <- diagnostics <- list()
for (w in hist$windows$window) {
  h <- hist$histories |> filter(window == w) |> select(unit_id, metric, value) |>
    pivot_wider(names_from = metric, values_from = value)
  d <- base |> left_join(h, by = "unit_id", relationship = "many-to-one")
  raw_samples[[w]] <- d
  missing_patterns <- list(); map <- list(); sds <- numeric()
  for (v in vars) {
    missing <- !is.finite(d[[v]])
    observed <- d[[v]][!missing]
    stopifnot(length(observed) > 1, is.finite(sd(observed)), sd(observed) > 0)
    sds[[v]] <- sd(observed)
    indicator <- NA_character_
    if (any(missing)) {
      same <- names(missing_patterns)[vapply(missing_patterns, identical, logical(1), missing)]
      indicator <- if (length(same)) same[[1]] else paste0("missing_", v)
      if (!length(same)) {
        missing_patterns[[indicator]] <- missing
        d[[indicator]] <- as.integer(missing)
      }
    }
    # Placeholders are estimation-only; raw histories retain NA. Scaling uses
    # the observed outlet-day SD, matching the existing joint-model convention.
    d[[v]] <- ifelse(missing, 0, d[[v]] / sds[[v]])
    map[[v]] <- tibble(metric = v, indicator = indicator)
    audit_rows[[length(audit_rows) + 1L]] <- tibble(
      window = w, metric = v, indicator = indicator, observed_sd = sds[[v]],
      observed_unit_days = sum(!missing), missing_unit_days = sum(missing),
      observed_units = n_distinct(d$unit_id[!missing]), missing_units = n_distinct(d$unit_id[missing]))
  }
  missing_vars <- names(missing_patterns)
  regressors <- c(vars, missing_vars)
  fit <- feols(as.formula(paste("ask ~", paste(regressors, collapse = " + "), "| date")),
               data = d, cluster = ~unit_id, notes = FALSE)
  stopifnot(length(coef(fit)) == length(regressors), is.null(fit$collin.var), nobs(fit) == nrow(base))
  V <- vcov(fit)
  eigenvalues <- eigen(cov2cor(V), symmetric = TRUE, only.values = TRUE)$values
  stopifnot(qr(V)$rank == ncol(V), min(eigenvalues) > 0)
  diagnostics[[w]] <- tibble(window = w, predictors = length(regressors),
    missing_indicators = length(missing_vars), covariance_rank = qr(V)$rank,
    covariance_correlation_condition = max(eigenvalues) / min(eigenvalues),
    minimum_correlation_eigenvalue = min(eigenvalues), within_r2 = r2(fit, "wr2")[[1]])
  for (kind in c("histories", "histories_and_missingness")) {
    selected <- if (kind == "histories") vars else regressors
    wt <- wald(fit, keep = paste0("^(", paste(selected, collapse = "|"), ")$"), print = FALSE)
    stopifnot(is.finite(wt$stat), is.finite(wt$p), wt$df1 == length(selected))
    test_rows[[length(test_rows) + 1L]] <- tibble(window = w, test = kind,
      F = wt$stat, p_value = wt$p, df1 = wt$df1, df2 = wt$df2,
      n = nobs(fit), units = n_distinct(d$unit_id), dates = n_distinct(d$date),
      asking_unit_days = sum(d$ask), within_r2 = r2(fit, "wr2")[[1]])
  }
  ct <- as.data.frame(coeftable(fit)); names(ct) <- c("estimate", "se", "t", "p_value")
  ct$term <- rownames(ct); rownames(ct) <- NULL
  ci <- confint(fit)
  coefficient_rows[[w]] <- ct |> mutate(window = w, ci_low = ci[, 1], ci_high = ci[, 2],
    kind = if_else(term %in% vars, "history_per_observed_sd", "missingness_indicator"))
  models[[w]] <- fit; samples[[w]] <- d; scales[[w]] <- sds
  missing_maps[[w]] <- bind_rows(map)
}
tests <- bind_rows(test_rows) |> left_join(hist$windows, by = "window")
# Four primary tests constitute one exploratory family; show Holm adjustment too.
tests <- tests |> group_by(test) |> mutate(p_holm_four_windows = p.adjust(p_value, "holm")) |> ungroup()
coefficients <- bind_rows(coefficient_rows)
audit <- bind_rows(audit_rows) |> left_join(hist$spec, by = "metric")
diagnostics <- bind_rows(diagnostics)
write.csv(tests, file.path(out, "joint_tests.csv"), row.names = FALSE)
write.csv(coefficients, file.path(out, "coefficients.csv"), row.names = FALSE)
write.csv(audit, file.path(out, "missingness_audit.csv"), row.names = FALSE)
write.csv(diagnostics, file.path(out, "diagnostics.csv"), row.names = FALSE)
write.csv(base, file.path(out, "sample.csv"), row.names = FALSE)
saveRDS(list(models = models, samples = samples, raw_samples = raw_samples, scales = scales,
             missing_maps = missing_maps, tests = tests, audit = audit, diagnostics = diagnostics,
             vars = vars, windows = hist$windows, spec = hist$spec), file.path(out, "models.rds"))
writeLines(capture.output(sessionInfo()), file.path(out, "session_info.txt"))
print(tests |> select(label, test, F, df1, df2, p_value, p_holm_four_windows, n, units))
print(diagnostics)
cat("Saved to", out, "\n")

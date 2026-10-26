# Current specification: separate metadata (without age) and history tests.
# Uses the previously audited metadata/source-ID snapshot, without upstream writes.
# Run with --months=12 (default) or --months=18 to reproduce the earlier version.
suppressPackageStartupMessages({library(dplyr); library(fixest)})
setFixest_nthreads(1)
previous <- "output/balance/full_post_18m_metadata"
args <- commandArgs(TRUE)
stopifnot(all(args %in% c("--months=12", "--months=18")), length(args) <= 1)
months <- if (length(args)) as.integer(sub("--months=", "", args)) else 12L
window <- paste0("ratio_", months, "m")
out <- paste0("output/balance/separate_", months, "m_no_age")
dir.create(out, recursive = TRUE, showWarnings = FALSE)
x <- readRDS(file.path(previous, "models.rds"))
h <- readRDS("output/balance/historical_outcomes/models.rds")
j <- readRDS("output/balance/joint_by_window/models.rds")
# Use the already estimated selected window, retaining the same post-period and
# established observed-history cohorts. Metadata is independent of the window.
stopifnot(identical(x$raw[c("unit_id", "date", "ask", "records")],
                    j$raw_samples[[window]][c("unit_id", "date", "ask", "records")]))
x$raw[h$spec$metric] <- j$raw_samples[[window]][h$spec$metric]
history_individual <- bind_rows(lapply(h$spec$metric, function(v) {
  f <- h$models[[v]][[window]]
  ds <- h$samples[[v]] |> mutate(x = .data[[window]])
  ct <- coeftable(f)["ask", ]; ci <- confint(f, "ask")
  x$individual_fits[[v]] <<- f
  x$individual_samples[[v]] <<- ds
  tibble(metric = v, estimate = ct[[1]], se = ct[[2]], ci_low = ci[[1]], ci_high = ci[[2]],
         p_value = ct[[4]], n = nobs(f), units = n_distinct(ds$unit_id), dates = n_distinct(ds$date))
})) |> left_join(h$spec, by = "metric")
x$individual <- bind_rows(history_individual, filter(x$individual, family == "Metadata"))
x$joint_fits$histories <- j$models[[window]]
x$joint_samples$histories <- j$samples[[window]]
x$missing_maps$histories <- j$missing_maps[[window]]
history_joint <- j$tests |> filter(.data$window == .env$window, test == "histories") |>
  select(test, F, df1, df2, p_value, n, units, dates) |>
  mutate(missingness_controls = length(grep("^missing_", names(coef(j$models[[window]])))),
         covariance_condition = j$diagnostics$covariance_correlation_condition[j$diagnostics$window == window])
x$history_window <- h$windows |> filter(.data$window == .env$window)
vars <- setdiff(x$spec$metric[x$spec$family == "Metadata"], "age_2022")
d <- x$raw
stopifnot(length(vars) == 9, all(is.finite(as.matrix(d[vars]))),
          all(as.matrix(d[vars]) %in% 0:1), all(d$records > 0),
          !anyDuplicated(d[c("unit_id", "date")]))
# All nine flags are observed under the existing missing-flag -> 0 convention.
# No missingness indicator and no history control enter the metadata regression.
fml <- as.formula(paste("ask ~", paste(vars, collapse = " + "), "| date"))
fit <- feols(fml, d, cluster = ~unit_id, notes = FALSE)
stopifnot(is.null(fit$collin.var), setequal(names(coef(fit)), vars), nobs(fit) == nrow(d))
wt <- wald(fit, print = FALSE)
V <- vcov(fit); z <- coef(fit) / sqrt(diag(V)); C <- cov2cor(V)
check_F <- drop(crossprod(z, solve(C, z))) / length(vars)
stopifnot(isTRUE(all.equal(wt$stat, check_F, tolerance = 1e-7)))
ev <- eigen(C, symmetric = TRUE, only.values = TRUE)$values
metadata <- tibble(test = "metadata", F = wt$stat, df1 = wt$df1, df2 = wt$df2,
                   p_value = wt$p, n = nobs(fit), units = n_distinct(d$unit_id),
                   dates = n_distinct(d$date), missingness_controls = 0L,
                   covariance_condition = max(ev) / min(ev))
x$joint <- bind_rows(metadata, history_joint)
x$individual <- x$individual |> filter(metric != "age_2022")
x$spec <- x$spec |> filter(metric != "age_2022")
x$individual_fits$age_2022 <- x$individual_samples$age_2022 <- NULL
x$joint_fits <- list(metadata = fit, histories = x$joint_fits$histories)
x$joint_samples <- list(metadata = d, histories = x$joint_samples$histories)
x$missing_maps <- list(metadata = tibble(metric = vars, indicator = NA_character_),
                       histories = x$missing_maps$histories)
x$age_excluded <- TRUE
saveRDS(x, file.path(out, "models.rds"))
write.csv(x$individual, file.path(out, "individual.csv"), row.names = FALSE)
write.csv(x$joint, file.path(out, "joint.csv"), row.names = FALSE)
write.csv(x$source_info, file.path(out, "source_info.csv"), row.names = FALSE)
write.csv(x$history_window, file.path(out, "window.csv"), row.names = FALSE)
writeLines(x$geography_definition, file.path(out, "geography_definition.txt"))
writeLines(capture.output(sessionInfo()), file.path(out, "session_info.txt"))
print(x$joint, width = 160)

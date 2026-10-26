# Same historical-balance specifications within metadata-defined subgroups.
# Keep all 12 restrictions for the joint null: never replace it with a reduced
# test when the full model or cluster covariance cannot support them.
suppressPackageStartupMessages({library(dplyr); library(tidyr); library(fixest)})
arg <- grep("^--file=", commandArgs(FALSE), value = TRUE)
script <- if (length(arg)) sub("^--file=", "", arg[[1]]) else
  file.path(getwd(), "code/08-results/balance/10-subgroup_balance.R")
root <- normalizePath(file.path(dirname(script), "../../.."), mustWork = TRUE)
second_year <- "--second-year" %in% commandArgs(trailingOnly = TRUE)
from_2023 <- "--from-2023" %in% commandArgs(trailingOnly = TRUE)
stopifnot(!(second_year && from_2023))
period <- if (from_2023) as.Date(c("2023-01-01", "2024-09-30")) else
  if (second_year) as.Date(c("2023-04-18", "2024-04-17")) else
  as.Date(c("2022-04-18", "2024-09-27"))
h <- readRDS(file.path(root, "output/balance/historical_outcomes/models.rds"))
j <- readRDS(file.path(root, "output/balance/joint_by_window/models.rds"))
end_audit <- NULL
if (from_2023 && period[2] > max(j$raw_samples[[1]]$date)) {
  # The saved sample previously ended September 27. Verify that extending the
  # requested range does not silently omit newly available source observations.
  source(file.path(root, "project_paths.R"))
  last_saved <- max(j$raw_samples[[1]]$date)
  end_audit <- bind_rows(lapply(c("attendance", "questions"), function(outcome) {
    arrow::open_dataset(media_path("data/06-outcomes/deduplicated_source_panels",
      paste0(outcome, "_entity_daily_panel.parquet"))) |>
      filter(date > last_saved, date <= period[2]) |> group_by(date) |>
      summarise(observed = any(source_date_observed), .groups = "drop") |>
      collect() |> mutate(outcome = outcome)
  }))
  if (any(end_audit$observed)) stop("New source dates exist beyond the saved sample; rebuild baseline balance inputs first.")
}
h$samples <- lapply(h$samples, function(d) filter(d, between(date, period[1], period[2])))
j$raw_samples <- lapply(j$raw_samples, function(d) filter(d, between(date, period[1], period[2])))
j$samples <- lapply(j$samples, function(d) filter(d, between(date, period[1], period[2])))
u <- read.csv(file.path(root, "output/balance/analysis_unit_covariates.csv"))
groups <- tibble(group = c("print", "digital", "aligned", "opposition", "independent"),
  label = c("Print / newspapers", "Digital", "Aligned", "Opposition", "Independent"),
  flag = c("media_print_any", "media_digital", "ideology_4t_aligned",
           "ideology_4t_opposition", "ideology_4t_unclear"))
if (second_year || from_2023) groups <- bind_rows(tibble(group = "pooled", label = "All outlets", flag = NA_character_), groups)
out <- file.path(root, if (from_2023) "output/balance/from_2023" else
  if (second_year) "output/balance/second_year" else "output/balance/subgroups")
dir.create(out, recursive = TRUE, showWarnings = FALSE)
write.csv(data.frame(from = period[1], to = period[2]), file.path(out, "period.csv"), row.names = FALSE)
if (!is.null(end_audit)) write.csv(end_audit, file.path(out, "end_date_coverage.csv"), row.names = FALSE)
setFixest_nthreads(1)
stopifnot(!anyDuplicated(u$unit_id))
informative <- function(d) d |> group_by(date) |> filter(any(ask == 1), any(ask == 0)) |> ungroup()
members <- bind_rows(lapply(seq_len(nrow(groups)), function(i) {
  if (groups$group[i] == "pooled") return(u |>
    transmute(group = "pooled", label = "All outlets", unit_id, outlet_names))
  u |> filter(.data[[groups$flag[i]]] == 1) |>
    transmute(group = groups$group[i], label = groups$label[i], unit_id, outlet_names)
})) |> filter(unit_id %in% j$samples[[1]]$unit_id)
individual <- joint <- individual_fits <- joint_fits <- joint_samples <- list()
for (g in groups$group) {
  ids <- members$unit_id[members$group == g]
  for (m in h$spec$metric) {
    # Preserve the original common-across-windows observed-history cohort.
    d <- h$samples[[m]] |> filter(unit_id %in% ids) |> informative()
    for (w in h$windows$window) {
      r <- tibble(group = g, metric = m, window = w, n = nrow(d),
        units = n_distinct(d$unit_id), dates = n_distinct(d$date),
        p_value = NA_real_, estimate = NA_real_, se = NA_real_,
        ci_low = NA_real_, ci_high = NA_real_, status = "not_estimable")
      if (nrow(d) && n_distinct(d$unit_id) >= 3) {
        fit <- tryCatch(feols(as.formula(paste(w, "~ ask | date")), d,
                             cluster = ~unit_id, notes = FALSE), error = function(e) NULL)
        if (!is.null(fit) && "ask" %in% names(coef(fit))) {
          ct <- coeftable(fit)["ask", ]
          if (is.finite(ct[[2]]) && ct[[2]] > 0 && is.finite(ct[[4]])) {
            r$p_value <- ct[[4]]; r$estimate <- ct[[1]]; r$se <- ct[[2]]; r$status <- "ok"
            ci <- confint(fit, "ask"); r$ci_low <- ci[[1]]; r$ci_high <- ci[[2]]
            individual_fits[[paste(g, m, w, sep = "__")]] <- fit
          }
        }
      }
      individual[[length(individual) + 1L]] <- r
    }
  }
  for (w in j$windows$window) {
    d <- j$raw_samples[[w]] |> filter(unit_id %in% ids) |> informative()
    r <- tibble(group = g, window = w, n = nrow(d), units = n_distinct(d$unit_id),
      dates = n_distinct(d$date), p_value = NA_real_, F = NA_real_, df1 = 12L,
      df2 = n_distinct(d$unit_id) - 1L, covariance_rank = NA_integer_,
      correlation_condition = NA_real_, recenter_F_relative_error = NA_real_,
      status = "not_estimable", reason = "Insufficient within-day support")
    if (!nrow(d)) { joint[[length(joint) + 1L]] <- r; next }
    patterns <- list(); impossible <- character()
    for (v in j$vars) {
      missing <- !is.finite(d[[v]])
      s <- sd(d[[v]][!missing])
      if (!is.finite(s) || s == 0) { impossible <- c(impossible, v); next }
      if (any(missing) && !all(missing) &&
          !any(vapply(patterns, identical, logical(1), missing))) {
        nm <- paste0("missing_", v); patterns[[nm]] <- missing; d[[nm]] <- as.integer(missing)
      }
      d[[v]] <- ifelse(missing, 0, d[[v]] / s)
    }
    if (length(impossible)) {
      r$reason <- paste("Unavailable or constant histories:", paste(impossible, collapse = ", "))
      joint[[length(joint) + 1L]] <- r; next
    }
    # With G clusters, the 12-restriction cluster covariance has rank <= G-1.
    if (r$units <= length(j$vars)) {
      r$reason <- "Too few outlet clusters for the 12-restriction clustered test"
      joint[[length(joint) + 1L]] <- r; next
    }
    terms <- c(j$vars, names(patterns))
    fit <- tryCatch(feols(as.formula(paste("ask ~", paste(terms, collapse = "+"), "| date")),
                         d, cluster = ~unit_id, notes = FALSE), error = function(e) NULL)
    if (is.null(fit)) { joint[[length(joint) + 1L]] <- r; next }
    key <- paste(g, w, sep = "__")
    joint_fits[[key]] <- fit; joint_samples[[key]] <- d
    if (!all(j$vars %in% names(coef(fit)))) {
      r$reason <- "Some historical coefficients are unidentified because of collinearity"
      joint[[length(joint) + 1L]] <- r; next
    }
    V <- vcov(fit)[j$vars, j$vars]
    ev <- eigen(cov2cor(V), symmetric = TRUE, only.values = TRUE)$values
    # Assess rank on the correlation scale at floating-point tolerance; the
    # default qr(V) tolerance confounds coefficient scales with rank here.
    r$covariance_rank <- sum(ev > max(ev) * length(ev) * .Machine$double.eps * 100)
    r$correlation_condition <- max(ev) / min(ev)
    if (r$covariance_rank < 12 || min(ev) <= 0) {
      r$reason <- "Rank-deficient clustered covariance for the 12 historical coefficients"
      joint[[length(joint) + 1L]] <- r; next
    }
    wt <- wald(fit, keep = paste0("^(", paste(j$vars, collapse = "|"), ")$"), print = FALSE)
    if (!is.finite(wt$p) || !is.finite(wt$stat)) {
      r$reason <- "Joint Wald calculation is unavailable"
      joint[[length(joint) + 1L]] <- r; next
    }
    centered <- d
    for (v in j$vars) {
      raw <- j$raw_samples[[w]][[v]][match(paste(d$unit_id, d$date),
                    paste(j$raw_samples[[w]]$unit_id, j$raw_samples[[w]]$date))]
      observed <- is.finite(raw)
      centered[[v]][observed] <- centered[[v]][observed] - mean(centered[[v]][observed])
    }
    alternate <- feols(as.formula(paste("ask ~", paste(terms, collapse = "+"), "| date")),
                        centered, cluster = ~unit_id, notes = FALSE)
    alt <- wald(alternate, keep = paste0("^(", paste(j$vars, collapse = "|"), ")$"), print = FALSE)
    r$recenter_F_relative_error <- abs(alt$stat - wt$stat) / max(abs(wt$stat), 1)
    if (!is.finite(r$recenter_F_relative_error) || r$recenter_F_relative_error > 1e-5) {
      r$reason <- "Joint statistic fails numerical re-centering invariance check"
      joint[[length(joint) + 1L]] <- r; next
    }
    r$p_value <- wt$p; r$F <- wt$stat; r$df1 <- wt$df1; r$df2 <- wt$df2
    r$status <- "ok"; r$reason <- ""
    joint[[length(joint) + 1L]] <- r
  }
}
individual <- bind_rows(individual) |> left_join(groups |> select(group, group_label = label), by = "group") |>
  left_join(h$spec, by = "metric")
joint <- bind_rows(joint) |> left_join(groups |> select(group, label), by = "group")
write.csv(members, file.path(out, "subgroup_membership.csv"), row.names = FALSE)
write.csv(individual, file.path(out, "individual_pvalues.csv"), row.names = FALSE)
write.csv(joint, file.path(out, "joint_pvalues.csv"), row.names = FALSE)
saveRDS(list(individual = individual, joint = joint, individual_fits = individual_fits,
             joint_fits = joint_fits, joint_samples = joint_samples, members = members,
             groups = groups, windows = h$windows, vars = j$vars, period = period,
             end_date_coverage = end_audit), file.path(out, "models.rds"))
writeLines(capture.output(sessionInfo()), file.path(out, "session_info.txt"))
print(joint |> select(label, window, p_value, units, n, status, reason), n = 24, width = 180)

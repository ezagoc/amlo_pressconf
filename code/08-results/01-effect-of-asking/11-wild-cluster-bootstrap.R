# Null-imposed outlet wild cluster bootstrap-t: combined model, or --pooled.
# No changes to estimation sample, outcomes, coefficients, controls or prior outputs.
entry <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)[1])
source(file.path(dirname(entry), "00-config.R"))
local_lib <- file.path(root, "tmp/Rlibs/wildclusterboot")
if (dir.exists(local_lib)) .libPaths(c(local_lib, .libPaths()))
suppressPackageStartupMessages({library(fixest); library(fwildclusterboot); library(dplyr)})
setFixest_nthreads(1)
arg <- grep("^--B=", commandArgs(TRUE), value = TRUE)
B <- if (length(arg)) as.integer(sub("^--B=", "", arg[1])) else 9999L
stopifnot(B >= 100L)
weekly <- "--weekly" %in% commandArgs(TRUE)
pooled <- "--pooled" %in% commandArgs(TRUE)
if ("--winsor99" %in% commandArgs(TRUE)) {
  stopifnot(!weekly)
  out <- file.path(out, paste0("daily_winsor99_six_outcomes", DAILY_TRANSFORMATION_SUFFIX))
  OUTCOMES <- c(OUTCOMES, "videos", "interactions", "mean_interactions")
}
stopifnot(!(weekly && pooled))
source_out <- if (pooled) out else file.path(out, if (weekly) "weekly_interactions_combined" else "pooled_interactions_combined")
panel_path <- file.path(source_out, "analysis_panel.rds")
fit_path <- file.path(source_out, if (pooled) "regression_fits.rds" else "fits.rds")
manifest <- read.csv(file.path(source_out, "input_manifest.csv"))
stopifnot(identical(unname(tools::md5sum(manifest$path)), manifest$md5))
panel <- readRDS(panel_path)
original <- readRDS(fit_path)
if (pooled) {
  effects <- read.csv(file.path(source_out, "regression_results.csv")) |>
    filter(inference == "Outlet clustered", model %in% c("Baseline", "History adjusted")) |>
    mutate(label = "Asked a question")
  differences <- effects[0, ]
  estimation_rows <- obs(original[["likes:Baseline"]])
} else {
  effects <- read.csv(file.path(source_out, "group_effects.csv"))
  differences <- read.csv(file.path(source_out, "pairwise_differences.csv"))
  estimation_rows <- panel$estimation_rows
}
d <- as.data.frame(panel$data[estimation_rows, ])
stopifnot(!anyDuplicated(d[c("unit_id", "date")]), all(d$records > 0), all(d$covered))
# Drop the five singleton rows BEFORE refitting: boottest correctly refuses
# fixest models that have internally discarded nonmissing observations.
# Explicit factors avoid the package's Date-class get_cluster incompatibility.
row_keys <- d[c("unit_id", "date")]
d$unit_id <- factor(d$unit_id)
d$date <- factor(d$date)
out <- file.path(source_out, paste0("wild_cluster_", B))
dir.create(out, recursive = TRUE, showWarnings = FALSE)
hypotheses <- list(
  combined = list(label = "Opp. + Independent", param = "ask", R = 1),
  aligned = list(label = "Aligned", param = c("ask", "ask_aligned"), R = c(1,1)),
  difference = list(label = "Aligned - (Opp. + Independent)", param = "ask_aligned", R = 1))
if (pooled) hypotheses <- list(asking = list(label = "Asked a question", param = "ask", R = 1))
rows <- list()
refits <- list()
for (o in OUTCOMES) for (adjusted in c(FALSE, TRUE)) {
  model <- if (adjusted) "History adjusted" else "Baseline"
  rhs <- c("ask", if (!pooled) "ask_aligned", if (adjusted) panel$controls)
  fml <- as.formula(paste0("log_", o, " ~ ", paste(rhs, collapse = " + "), " | unit_id + date"))
  # Keep explicit data in this script's scope: fwildclusterboot 0.14.3 cannot
  # resolve fixest 0.14.1's DATA_SAVED call placeholder when data.save = TRUE.
  f <- feols(fml, data = d, cluster = ~unit_id, notes = FALSE)
  key <- paste(o, model, sep = ":")
  old <- original[[key]]
  stopifnot(nobs(f) == nrow(d), nobs(old) == nobs(f),
            max(abs(coef(f) - coef(old))) < 1e-9,
            max(abs(vcov(f) - vcov(old))) < 1e-9,
            identical(obs(f), seq_len(nrow(d))))
  refits[[key]] <- f
  for (h in names(hypotheses)) {
    spec <- hypotheses[[h]]
    reference <- bind_rows(effects, differences) |>
      filter(outcome == o, .data$model == .env$model, label == spec$label)
    stopifnot(nrow(reference) == 1)
    # Common random weights across tests; both generators explicitly seeded.
    set.seed(SEED); dqrng::dqset.seed(SEED)
    message(o, " / ", model, " / ", spec$label, ": ", B, " draws")
    bt <- boottest(f, param = spec$param, R = spec$R, r = 0,
      B = B, clustid = "unit_id", bootcluster = "unit_id", fe = "unit_id",
      type = "rademacher", impose_null = TRUE, bootstrap_type = "fnw11",
      p_val_type = "two-tailed", conf_int = FALSE, engine = "R", nthreads = 1,
      ssc = boot_ssc(adj = TRUE, cluster.adj = TRUE, fixef.K = "none"))
    t_draws <- as.numeric(bt$t_boot)
    tail_fraction <- mean(abs(t_draws) >= abs(as.numeric(bt$t_stat)))
    stopifnot(bt$N == nrow(d), unname(bt$N_G) == nlevels(d$unit_id),
      bt$boot_iter == B, length(t_draws) == B, all(is.finite(t_draws)),
      isTRUE(bt$impose_null), bt$r == 0,
      abs(bt$point_estimate - reference$estimate) < 1e-8,
      abs(bt$p_val - tail_fraction) < 1e-10)
    tag <- paste(o, if (adjusted) "adjusted" else "baseline", h, sep = "_")
    saveRDS(list(test = bt, spec = spec, seed = SEED, B = B,
                 package_version = as.character(packageVersion("fwildclusterboot"))),
            file.path(out, paste0(tag, ".rds")))
    rows[[tag]] <- data.frame(outcome = o, model, label = spec$label,
      estimate = reference$estimate, conventional_se = reference$se,
      conventional_ci_low = reference$ci_low, conventional_ci_high = reference$ci_high,
      conventional_p = reference$p_value, wild_p = as.numeric(bt$p_val),
      monte_carlo_se = sqrt(bt$p_val * (1-bt$p_val) / B),
      bootstrap_t = as.numeric(bt$t_stat), valid_draws = sum(is.finite(t_draws)),
      B, n = nrow(d), clusters = nlevels(d$unit_id), dates = nlevels(d$date),
      seed = SEED, weights = "Rademacher", impose_null = TRUE, bootstrap_type = "WCR11/fnw11")
    save_csv(bind_rows(rows), "results.csv")
  }
}
stopifnot(length(rows) == 2 * length(OUTCOMES) * length(hypotheses))
saveRDS(refits, file.path(out, "refits.rds"))
save_csv(row_keys, "estimation_rows.csv")
paths <- c(panel_path, fit_path, manifest$path)
save_csv(data.frame(path = paths, md5 = unname(tools::md5sum(paths))), "input_manifest.csv")
capture.output(sessionInfo(), file = file.path(out, "session_info.txt"))
print(bind_rows(rows) |> filter(model == "History adjusted") |>
        select(outcome, label, estimate, conventional_p, wild_p, monte_carlo_se), width = 160)
cat("PASS: ", length(rows), " tests; unchanged point estimates, covariance and sample; null imposed;\n",
    "all requested draws finite; every bootstrap p-value reproduced from saved t draws.\n", sep = "")

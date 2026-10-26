# Full-calendar FEct ATT, six asinh(p99-capped) outcomes, attendance in both
# baseline and history-adjusted models. Outlet/entity bootstrap, NOT wild bootstrap.
# --outcome=videos (repeatable), --nboots=1000, --resume.
entry <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)[1])
source(file.path(dirname(entry), "00-config.R"))
suppressPackageStartupMessages({library(fect); library(fixest); library(dplyr)})
setFixest_nthreads(1)
out <- file.path(out, "legacy_full_calendar_asinh_winsor99_history")
nb <- grep("^--nboots=", commandArgs(TRUE), value = TRUE)
nboots <- if (length(nb)) as.integer(sub("^--nboots=", "", nb[1])) else 1000L
stopifnot(nboots >= 2L)
manifest <- read.csv(file.path(out, "input_manifest.csv"))
stopifnot(identical(unname(tools::md5sum(manifest$path)), manifest$md5))
panel_path <- file.path(out, "panel.rds")
x <- readRDS(panel_path)
requested <- grep("^--outcome=", commandArgs(TRUE), value = TRUE)
outcomes <- if (length(requested)) sub("^--outcome=", "", requested) else x$outcomes
stopifnot(all(outcomes %in% x$outcomes))
resume <- "--resume" %in% commandArgs(TRUE)
fd <- file.path(out, paste0("fect_", nboots))
dir.create(fd, recursive = TRUE, showWarnings = FALSE)
atomic_rds <- function(object, path) {
  temp <- tempfile(tmpdir = dirname(path)); saveRDS(object, temp)
  stopifnot(file.rename(temp, path))
}
run_model <- function(outcome, adjusted) {
  model <- if (adjusted) "History adjusted" else "Baseline"
  tag <- paste(outcome, if (adjusted) "adjusted" else "baseline", sep = "_")
  path <- file.path(fd, paste0(tag, ".rds"))
  controls <- c("attendance_dummy", if (adjusted) x$history_controls)
  d <- x$data
  d$Y <- d[[paste0("Y_", outcome)]]
  fml <- as.formula(paste("Y ~", paste(c("ask", controls), collapse = " + ")))
  input <- list(data = as.data.frame(d[c("unit_id", "sample_day", "Y", "ask", controls)]),
    formula = deparse(fml), nboots = nboots, seed = SEED,
    transformation = "asinh after pooled full-calendar upper-p99 cap", version = as.character(packageVersion("fect")),
    panel_md5 = unname(tools::md5sum(panel_path)))
  saved <- if (resume && file.exists(path)) readRDS(path) else NULL
  if (!is.null(saved) && identical(saved$input, input)) {
    fit <- saved$fit
    message("Reusing validated input: ", tag)
  } else {
    message("START ", tag, " | ", nboots, " outlet bootstraps")
    log_path <- file.path(fd, paste0(tag, ".log"))
    con <- file(log_path, open = "wt")
    fit <- tryCatch({
      sink(con); sink(con, type = "message")
      fect(fml, data = input$data, index = c("unit_id", "sample_day"),
        method = "fe", force = "two-way", se = TRUE, vartype = "bootstrap",
        nboots = nboots, parallel = FALSE, seed = SEED, min.T0 = 5, na.rm = TRUE)
    }, finally = {sink(type = "message"); sink(); close(con)})
    atomic_rds(list(fit = fit, input = input), path)
  }
  # Independent untreated-regression imputation check, on exactly the same cells.
  cf <- feols(as.formula(paste("Y ~", paste(controls, collapse = " + "), "| unit_id + date")),
    d[d$ask == 0, ], notes = FALSE)
  prediction <- predict(cf, newdata = d[d$ask == 1, ])
  manual <- mean(d$Y[d$ask == 1] - prediction)
  avg <- as.numeric(fit$est.avg[1, 1:5])
  stopifnot(all(is.finite(prediction)), abs(manual - as.numeric(fit$att.avg)) < 1e-4,
    fit$N == n_distinct(d$unit_id), fit$T == n_distinct(d$date), sum(fit$I.dat) == nrow(d),
    sum(fit$D.dat[fit$I.dat == 1]) == sum(d$ask), all(is.finite(avg)),
    length(fit$att.avg.boot) == nboots, all(is.finite(fit$att.avg.boot)),
    abs(sd(as.numeric(fit$att.avg.boot)) - avg[2]) < 1e-8)
  fit_att <- as.numeric(fit$est.beta[1, 1:5])
  stopifnot(abs(fit_att[1] - coef(cf)[["attendance_dummy"]]) < 1e-4)
  row <- data.frame(outcome, model, estimate = avg[1], se = avg[2], ci_low = avg[3],
    ci_high = avg[4], p_value = avg[5], n = sum(fit$I.dat), units = fit$N,
    dates = fit$T, asking = sum(d$ask), ever_treated = n_distinct(d$unit_id[d$ask == 1]),
    history_observed_units = n_distinct(d$unit_id[d$missing_ratio == 0]),
    history_controls = if (adjusted) length(x$history_controls) else 0L,
    attendance_estimate = fit_att[1], attendance_se = fit_att[2], attendance_p = fit_att[5],
    rmse = fit$rmse, bootstrap_replications = nboots, valid_bootstraps = length(fit$att.avg.boot),
    manual_imputation_att = manual, starts = min(d$date), ends = max(d$date))
  temp <- tempfile(tmpdir = fd); write.csv(row, temp, row.names = FALSE)
  stopifnot(file.rename(temp, file.path(fd, paste0("results_", tag, ".csv"))))
  message("PASS ", tag, ": ATT=", round(avg[1], 4), "; p=", round(avg[5], 4),
    "; all ", nboots, " draws finite; exact sample; independent ATT/attendance checks.")
}
for (o in outcomes) for (a in c(FALSE, TRUE)) run_model(o, a)
results <- bind_rows(lapply(list.files(fd, pattern = "^results_.*[.]csv$", full.names = TRUE), read.csv))
temp <- tempfile(tmpdir = fd); write.csv(results, temp, row.names = FALSE)
stopifnot(file.rename(temp, file.path(fd, "results.csv")))
print(results, width = 160)

# New comparable-sample FEct estimates plus clearly separate legacy estimates.
# Default: 1,000 outlet bootstrap replications, serial, reproducible seed.
# --nboots=20 is for smoke testing only; --resume reuses exact matching inputs.
entry <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)[1])
source(file.path(dirname(entry), "00-config.R"))
suppressPackageStartupMessages({library(dplyr); library(fixest); library(fect)})
setFixest_nthreads(1)
args <- commandArgs(TRUE)
nb <- grep("^--nboots=", args, value = TRUE)
nboots <- if (length(nb)) as.integer(sub("^--nboots=", "", nb[1])) else 1000L
stopifnot(is.finite(nboots), nboots >= 2)
resume <- "--resume" %in% args
outcome_arg <- grep("^--outcome=", args, value = TRUE)
requested_outcomes <- if (length(outcome_arg)) sub("^--outcome=", "", outcome_arg) else OUTCOMES
stopifnot(all(requested_outcomes %in% OUTCOMES))
x <- readRDS(file.path(out, "analysis_panel.rds"))
d <- x$data
fd <- file.path(out, paste0("fect_", nboots))
dir.create(fd, recursive = TRUE, showWarnings = FALSE)

# Apply common support explicitly, before any fect fit. Nonattending days remain
# absent/missing; no nonattendee is introduced as an untreated observation.
support <- d |> group_by(unit_id) |>
  summarise(n = n(), asking = sum(ask), untreated = sum(ask == 0), .groups = "drop")
save_csv(support |> mutate(eligible = untreated >= 5), "fect_unit_support.csv")
ds <- d |> semi_join(filter(support, untreated >= 5), by = "unit_id") |> informative()
repeat {
  eligible <- ds |> group_by(unit_id) |> summarise(n0 = sum(ask == 0), .groups = "drop") |> filter(n0 >= 5)
  # Missing-history x quarter cells must have at least one untreated attendee.
  # Otherwise dropping the unidentifiable interaction changes the model for
  # treated cells: do not extrapolate an unrestricted missing-history effect.
  control_cells <- ds |> filter(ask == 0) |> distinct(quarter, missing_ratio)
  next_ds <- ds |> semi_join(eligible, by = "unit_id") |>
    semi_join(control_cells, by = c("quarter", "missing_ratio")) |> informative()
  if (nrow(next_ds) == nrow(ds)) break
  ds <- next_ds
}
save_csv(anti_join(d, ds, by = c("unit_id", "date")) |>
           select(unit_id, date, ask, missing_ratio, quarter), "fect_support_exclusions.csv")
stopifnot(!anyDuplicated(ds[c("unit_id", "date")]),
          all(ds$records > 0), all(ds$ask %in% 0:1))
# Select a full-rank basis of history controls in the UNTREATED estimation
# sample. fect 2.4.5 can mishandle controls absorbed by FE; guard explicitly.
untreated <- filter(ds, ask == 0)
X <- as.matrix(untreated[x$controls])
Xd <- fixest::demean(X, f = list(untreated$unit_id, untreated$date), nthreads = 1)
z <- qr(Xd, tol = 1e-7)
controls <- if (z$rank) x$controls[z$pivot[seq_len(z$rank)]] else character()
# Verify that redundant control columns remain redundant on TREATED rows too.
# This distinguishes harmless rank reduction from unsupported extrapolation.
for (v in setdiff(x$controls, controls)) {
  if (sd(untreated[[v]]) < 1e-12) {
    stopifnot(all(abs(ds[[v]] - untreated[[v]][1]) < 1e-12))
    next
  }
  probe <- feols(as.formula(paste(v, "~", paste(controls, collapse = " + "),
                                  "| unit_id + date")), untreated, notes = FALSE)
  stopifnot(max(abs(predict(probe, newdata = ds) - ds[[v]])) < 1e-5)
}
save_csv(data.frame(control = x$controls, retained = x$controls %in% controls),
         "fect_control_rank_audit.csv")
saveRDS(list(data = ds, controls = controls), file.path(fd, "sample.rds"))
save_csv(bind_rows(flow_row(d, "Main input"),
                  flow_row(ds, "FEct support: >=5 untreated dates + quarter/history overlap")),
         "fect_sample_flow.csv")

rows <- list()
for (outcome in requested_outcomes) for (adjusted in c(FALSE, TRUE)) {
  model <- if (adjusted) "History adjusted" else "Baseline"
  rhs <- c("ask", if (adjusted) controls)
  df <- ds |> mutate(Y = log1p(.data[[outcome]])) |> as.data.frame()
  fml <- as.formula(paste("Y ~", paste(rhs, collapse = " + ")))
  tag <- paste(outcome, if (adjusted) "adjusted" else "baseline", sep = "_")
  input <- list(data = df[c("unit_id", "sample_day", "Y", rhs)], controls = rhs,
                nboots = nboots, seed = SEED, version = as.character(packageVersion("fect")))
  path <- file.path(fd, paste0(tag, ".rds"))
  saved <- if (resume && file.exists(path)) readRDS(path) else NULL
  if (!is.null(saved) && identical(saved$input, input)) {
    fit <- saved$fit
    message("Reusing ", tag)
  } else {
    message(format(Sys.time(), "%H:%M:%S"), " ", tag, " ", nboots, " bootstraps")
    fit <- fect(fml, data = df, index = c("unit_id", "sample_day"),
                method = "fe", force = "two-way", min.T0 = 5,
                na.rm = TRUE, se = TRUE, vartype = "bootstrap",
                nboots = nboots, parallel = FALSE, seed = SEED)
    saveRDS(list(fit = fit, input = input), path)
  }
  # Independent point-estimate check: untreated-only FE regression and average
  # residual on treated attendee cells must agree with FEct imputation.
  cf <- feols(as.formula(paste("Y ~", if (length(rhs) > 1) paste(rhs[-1], collapse = " + ") else "1",
                              "| unit_id + date")), df[df$ask == 0, ], notes = FALSE)
  prediction <- predict(cf, newdata = df[df$ask == 1, ])
  manual <- mean(df$Y[df$ask == 1] - prediction)
  stopifnot(all(is.finite(prediction)), abs(manual - as.numeric(fit$att.avg)) < 1e-4,
            sum(fit$I.dat) == nrow(df),
            sum(fit$D.dat[fit$I.dat == 1]) == sum(df$ask))
  avg <- as.numeric(fit$est.avg[1, ])
  rows[[tag]] <- tibble(outcome, model, estimator = "FEct",
    estimate = avg[1], se = avg[2], ci_low = avg[3], ci_high = avg[4], p_value = avg[5],
    n = sum(fit$I.dat), units = fit$N, dates = n_distinct(df$date), asking = sum(df$ask),
    bootstrap_replications = nboots, valid_bootstraps = sum(is.finite(fit$att.avg.boot)),
    manual_imputation_att = manual)
  paired <- feols(as.formula(paste("Y ~", paste(rhs, collapse = " + "), "| unit_id + date")),
                  df, cluster = ~unit_id, notes = FALSE)
  ct <- coeftable(paired)["ask", ]; ci <- confint(paired, "ask")
  rows[[paste0(tag, "_paired")]] <- tibble(outcome, model, estimator = "Paired-sample TWFE",
    estimate = ct[[1]], se = ct[[2]], ci_low = ci[[1]], ci_high = ci[[2]], p_value = ct[[4]],
    n = nobs(paired), units = n_distinct(df$unit_id[obs(paired)]),
    dates = n_distinct(df$date[obs(paired)]), asking = sum(df$ask[obs(paired)]),
    bootstrap_replications = NA_integer_, valid_bootstraps = NA_integer_,
    manual_imputation_att = NA_real_)
  # Per-outcome checkpoints allow independent outcome processes without clobbering.
  output_rows <- bind_rows(rows) |> filter(.data$outcome == .env$outcome)
  temp <- tempfile(pattern = paste0(outcome, "_"), tmpdir = fd)
  write.csv(output_rows, temp, row.names = FALSE)
  stopifnot(file.rename(temp, file.path(fd, paste0("results_", outcome, ".csv"))))
}
available <- file.path(fd, paste0("results_", OUTCOMES, ".csv"))
combined <- bind_rows(lapply(available[file.exists(available)], read.csv))
temp <- tempfile(pattern = "combined_", tmpdir = fd)
write.csv(combined, temp, row.names = FALSE)
stopifnot(file.rename(temp, file.path(fd, "results.csv")))

# Do not describe these legacy full-calendar, channel-level models as the same
# sample. Copy only scalar estimates and provenance, not huge fit call objects.
legacy <- list()
for (outcome in OUTCOMES) {
  location <- file.path(root, "output/fect_youtube",
    paste0("daily_question_day_log1p_events_1000_unwinsorized_pre14_post6_",
           outcome, "_split_independent"), "pooled_onset_fit.rds")
  if (!file.exists(location)) next
  f <- readRDS(location); a <- as.numeric(f$est.avg[1, ])
  legacy[[outcome]] <- tibble(outcome, estimate = a[1], se = a[2],
    ci_low = a[3], ci_high = a[4], p_value = a[5], channels = f$N, periods = f$T,
    n = sum(f$I.dat), asking = sum(f$D.dat[f$I.dat == 1]),
    bootstrap_replications = length(f$att.avg.boot),
    valid_bootstraps = sum(is.finite(f$att.avg.boot)),
    first_time_index = min(f$call$data$sample_day),
    last_time_index = max(f$call$data$sample_day),
    source = location,
    comparability = "Legacy full-calendar channel panel; attendance dummy; not attendee-only")
}
save_csv(bind_rows(legacy), "legacy_fect_reference.csv")
print(bind_rows(rows), width = 180)

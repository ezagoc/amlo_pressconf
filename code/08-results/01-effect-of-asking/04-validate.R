# Read-only checks for the completed 1,000-bootstrap run.
entry <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)[1])
source(file.path(dirname(entry), "00-config.R"))
suppressPackageStartupMessages({library(dplyr); library(fixest)})
p <- readRDS(file.path(out, "analysis_panel.rds"))
d <- p$data
fits <- readRDS(file.path(out, "regression_fits.rds"))
results <- read.csv(file.path(out, "regression_results.csv"))
stopifnot(!anyDuplicated(d[c("unit_id", "date")]), !anyDuplicated(p$links$entity_id),
          all(d$covered), all(d$records > 0), all(d$ask %in% 0:1),
          all(d$date >= FROM & d$date <= TO),
          all(d$last_common[!is.na(d$last_common)] < FROM))
for (o in OUTCOMES) {
  stopifnot(identical(d[[paste0("log_", o)]], log1p(d[[o]])))
  b <- fits[[paste(o, "Baseline", sep = ":")]]
  a <- fits[[paste(o, "History adjusted", sep = ":")]]
  stopifnot(identical(obs(b), obs(a)), nobs(b) == 5303)
  for (m in c("Baseline", "History adjusted")) {
    f <- fits[[paste(o, m, sep = ":")]]
    r <- filter(results, outcome == o, model == m, inference == "Outlet clustered")
    stopifnot(nrow(r) == 1, abs(coef(f)[["ask"]] - r$estimate) < 1e-12,
              abs(sqrt(vcov(f)["ask", "ask"]) - r$se) < 1e-12)
  }
}
stopifnot(all(d$ratio_filled[d$missing_ratio == 1] == 0),
          all(d$ratio_filled[d$missing_ratio == 0] == d$prior_ratio[d$missing_ratio == 0]))
for (v in p$controls) {
  quarter <- sub("^(history|missing)_", "", v)
  z <- if (startsWith(v, "history_")) d$ratio_filled else d$missing_ratio
  stopifnot(all(d[[v]] == z * (d$quarter == quarter)))
}
manifest <- read.csv(file.path(out, "input_manifest.csv"))
stopifnot(identical(unname(tools::md5sum(manifest$path)), manifest$md5))
if ("--main-only" %in% commandArgs(TRUE)) {
  cat("PASS: source fingerprints, unique sources, coverage, transformations,\n",
      "identical main-model samples, history interactions, and saved regressions.\n", sep = "")
  quit(status = 0)
}
fdir <- file.path(out, "fect_1000")
fr <- read.csv(file.path(fdir, "results.csv"))
stopifnot(nrow(fr) == 12, all(is.finite(fr$estimate)))
for (o in OUTCOMES) for (adjusted in c(FALSE, TRUE)) {
  tag <- paste(o, if (adjusted) "adjusted" else "baseline", sep = "_")
  f <- readRDS(file.path(fdir, paste0(tag, ".rds")))
  r <- filter(fr, outcome == o, model == if (adjusted) "History adjusted" else "Baseline",
              estimator == "FEct")
  matched <- f$input$data |> select(unit_id, sample_day) |>
    left_join(d, by = c("unit_id", "sample_day"), relationship = "one-to-one")
  stopifnot(all(f$input$data$Y == log1p(matched[[o]])),
            all(vapply(f$input$controls, function(v)
              all(f$input$data[[v]] == matched[[v]]), logical(1))))
  stopifnot(nrow(r) == 1, r$valid_bootstraps == 1000,
            sum(f$fit$I.dat) == nrow(f$input$data),
            abs(as.numeric(f$fit$att.avg) - r$estimate) < 1e-12,
            abs(r$estimate - r$manual_imputation_att) < 1e-4,
            all(f$input$data$unit_id %in% d$unit_id),
            nrow(anti_join(f$input$data, d, by = c("unit_id", "sample_day", "ask"))) == 0)
}
cat("PASS: source fingerprints, source-unit uniqueness, coverage, transformations,\n",
    "identical main-model samples, fixed-history interactions, six independent FEct\n",
    "imputation checks, 1,000 valid bootstrap draws per fit, and saved estimates.\n", sep = "")

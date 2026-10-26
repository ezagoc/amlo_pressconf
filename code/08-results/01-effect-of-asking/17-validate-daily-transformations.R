# Read-only checks of all six-outcome daily transformations and their inference.
entry <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)[1])
source(file.path(dirname(entry), "00-config.R"))
suppressPackageStartupMessages(library(fixest))
setFixest_nthreads(1)
OUTCOMES <- c(OUTCOMES, "videos", "interactions", "mean_interactions")
reference <- readRDS(file.path(out, "analysis_panel.rds"))
reference_inter <- readRDS(file.path(out, "pooled_interactions_combined/analysis_panel.rds"))
total_tests <- 0L
for (transformation in c("log1p", "asinh", "chen_roth_x0")) {
  suffix <- if (transformation == "log1p") "" else paste0("_", transformation)
  location <- file.path(out, paste0("daily_winsor99_six_outcomes", suffix))
  pooled <- readRDS(file.path(location, "analysis_panel.rds"))
  for (interaction in c(FALSE, TRUE)) {
    folder <- if (interaction) file.path(location, "pooled_interactions_combined") else location
    panel <- readRDS(file.path(folder, "analysis_panel.rds"))
    fits <- readRDS(file.path(folder, if (interaction) "fits.rds" else "regression_fits.rds"))
    old <- if (interaction) reference_inter else reference
    d <- panel$data
    vars <- c("unit_id", "date", "ask", "records", "likes", "comments", "views", "videos", old$controls)
    stopifnot(identical(d[vars], old$data[vars]), identical(panel$controls, old$controls),
      all(d$interactions == d$likes + d$comments),
      all(d$mean_interactions[d$videos == 0] == 0),
      all(d$mean_interactions[d$videos > 0] == d$interactions[d$videos > 0] / d$videos[d$videos > 0]))
    for (o in OUTCOMES) {
      raw <- pooled$data[[o]][pooled$estimation_rows]
      upper <- unname(quantile(raw, .99, type = 7))
      y <- pmin(d[[o]], upper)
      minimum <- min(pmin(raw[raw > 0], upper))
      expected <- switch(transformation, log1p = log1p(y), asinh = asinh(y),
        chen_roth_x0 = log(ifelse(y > 0, y, minimum)))
      stopifnot(identical(d[[paste0("winsor_", o)]], y),
                identical(d[[paste0("log_", o)]], expected))
      for (model in c("Baseline", "History adjusted")) {
        f <- fits[[paste(o, model, sep = ":")]]
        stopifnot(identical(obs(f), panel$estimation_rows))
        if (transformation == "chen_roth_x0") {
          # Normalized paper-style version differs only by one global constant.
          d$normalized <- log(ifelse(y > 0, y / minimum, 1))
          terms <- c("ask", if (interaction) "ask_aligned",
            if (model == "History adjusted") panel$controls)
          alt <- feols(as.formula(paste("normalized ~", paste(terms, collapse = " + "),
            "| unit_id + date")), d, cluster = ~unit_id, notes = FALSE)
          stopifnot(identical(obs(alt), obs(f)), max(abs(coef(alt) - coef(f))) < 1e-9,
                    max(abs(vcov(alt) - vcov(f))) < 1e-9)
        }
      }
    }
    bdir <- file.path(folder, "wild_cluster_9999")
    manifest <- read.csv(file.path(bdir, "input_manifest.csv"))
    stopifnot(identical(unname(tools::md5sum(manifest$path)), manifest$md5))
    res <- read.csv(file.path(bdir, "results.csv"))
    stopifnot(nrow(res) == if (interaction) 36L else 12L,
              all(res$B == 9999), all(res$valid_draws == 9999))
    files <- list.files(bdir, pattern = "_(asking|combined|aligned|difference)\\.rds$", full.names = TRUE)
    stopifnot(length(files) == nrow(res))
    for (path in files) {
      bt <- readRDS(path)$test
      stopifnot(isTRUE(bt$impose_null), all(is.finite(bt$t_boot)), length(bt$t_boot) == 9999L,
        abs(bt$p_val - mean(abs(bt$t_boot) >= abs(as.numeric(bt$t_stat)))) < 1e-10)
    }
    total_tests <- total_tests + length(files)
    cat("PASS:", transformation, if (interaction) "interaction" else "pooled",
        "- raw data, samples, cap-before-transform, fixed calibration, bootstrap.\n")
  }
}
stopifnot(total_tests == 144L)
cat("PASS: all 144 tests / 1,439,856 bootstrap draws; normalized Chen-Roth coefficients and covariances match.\n")

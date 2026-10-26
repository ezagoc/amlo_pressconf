# Read-only validation of saved subgroup models, mapping and FEct draws.
entry <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)[1])
source(file.path(dirname(entry), "00-config.R"))
suppressPackageStartupMessages({library(dplyr); library(fixest)})
setFixest_nthreads(1)
pooled <- readRDS(file.path(out, "analysis_panel.rds"))
out <- file.path(out, "heterogeneity")
manifest <- read.csv(file.path(out, "input_manifest.csv"))
stopifnot(identical(unname(tools::md5sum(manifest$path)), manifest$md5))
audit <- read.csv(file.path(out, "classification_audit.csv"))
stopifnot(!anyDuplicated(audit$unit_id),
          all(is.na(audit$group) == !audit$codes %in% c("opp", "aligned", "unclear")))
fits <- readRDS(file.path(out, "regression_fits.rds"))
reg <- read.csv(file.path(out, "regression_results.csv"))
stopifnot(nrow(reg) == 18, length(fits) == 18)
for (g in c("Opposition", "Aligned", "Independent")) {
  x <- readRDS(file.path(out, paste0(tolower(g), "_panel.rds")))
  d <- x$data
  stopifnot(all(d$group == g), all(d$records > 0), all(d$covered),
            all(d$date >= FROM & d$date <= TO),
            !anyDuplicated(d[c("unit_id", "date")]),
            nrow(d) == nrow(informative(d)))
  before <- pooled$data |> semi_join(d, by = c("unit_id", "date")) |> arrange(unit_id, date)
  stopifnot(isTRUE(all.equal(as.data.frame(before),
              as.data.frame(d |> arrange(unit_id, date) |> select(all_of(names(before)))), check.attributes = FALSE)))
  fd <- file.path(out, tolower(g), "fect_1000")
  sample <- readRDS(file.path(fd, "sample.rds"))
  ds <- sample$data
  stopifnot(nrow(ds) == nrow(informative(ds)), all(ds$records > 0),
            all((ds |> group_by(unit_id) |> summarise(n0 = sum(ask == 0)))$n0 >= 5))
  for (o in OUTCOMES) {
    stopifnot(all(d[[paste0("log_", o)]] == log1p(d[[o]])))
    b <- fits[[paste(g, o, "Baseline", sep = ":")]]
    a <- fits[[paste(g, o, "History adjusted", sep = ":")]]
    stopifnot(identical(obs(a), obs(b)))
    for (adjusted in c(FALSE, TRUE)) {
      m <- if (adjusted) "History adjusted" else "Baseline"
      f <- fits[[paste(g, o, m, sep = ":")]]
      r <- reg |> filter(group == g, outcome == o, model == m)
      stopifnot(nrow(r) == 1, abs(r$estimate - coef(f)[["ask"]]) < 1e-10,
                r$n == nobs(f), r$units == n_distinct(d$unit_id[obs(f)]))
      saved <- readRDS(file.path(fd, paste0(o, if (adjusted) "_adjusted" else "_baseline", ".rds")))
      ff <- saved$fit; input <- saved$input
      stopifnot(input$nboots == 1000, length(ff$att.avg.boot) == 1000,
                all(is.finite(ff$att.avg.boot)), sum(ff$I.dat) == nrow(ds),
                sum(ff$D.dat[ff$I.dat == 1]) == sum(ds$ask),
                identical(input$data$unit_id, ds$unit_id), identical(input$data$sample_day, ds$sample_day),
                identical(input$data$ask, ds$ask), all(input$data$Y == log1p(ds[[o]])))
      dd <- ds |> mutate(Y = log1p(.data[[o]]))
      ctrl <- if (adjusted) sample$controls else character()
      if (length(ctrl)) stopifnot(all(as.matrix(input$data[ctrl]) == as.matrix(ds[ctrl])))
      fml <- as.formula(paste("Y ~", if (length(ctrl)) paste(ctrl, collapse = " + ") else "1", "| unit_id + date"))
      cf <- feols(fml, dd[dd$ask == 0, ], fixef.rm = "none", notes = FALSE)
      prediction <- predict(cf, newdata = dd[dd$ask == 1, ])
      stopifnot(all(is.finite(prediction)), abs(mean(dd$Y[dd$ask == 1] - prediction) - ff$att.avg) < 1e-4)
    }
  }
  cat(g, ": 6 regressions and 6 FEct fits validated.\n")
}
cat("PASS: classification, source rows, outcomes, 18 FE regressions, 18 FEct fits and all 18,000 bootstrap draws.\n")

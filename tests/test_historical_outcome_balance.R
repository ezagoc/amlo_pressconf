suppressPackageStartupMessages({library(dplyr); library(fixest)})
source("src/baseline_history.R")
stopifnot(is.na(history_sum(numeric())), is.na(history_sum(c(NA_real_, NA_real_))),
          identical(history_sum(c(0, NA_real_)), 0), history_sum(c(2, 3, NA_real_)) == 5)
z <- readRDS("output/balance/historical_outcomes/models.rds")
stopifnot(!anyDuplicated(z$asset_links[c("unit_id", "outcome", "entity_id")]),
          !anyDuplicated(z$contract_source[c("unit_id", "entity_id", "date")]),
          !anyDuplicated(z$youtube_source[c("unit_id", "entity_id", "date")]),
          all(z$contract_source$date < as.Date("2022-04-18")),
          all(z$youtube_source$date < as.Date("2022-04-18")),
          all(z$windows$to < as.Date("2022-04-18")))
# Independently recompute all per-unit/window contract and YouTube sums.
for (i in seq_len(nrow(z$windows))) {
  w <- z$windows[i, ]
  cs <- z$contract_source |> filter(covered, between(date, w$from, w$to)) |>
    group_by(unit_id) |> summarise(value = history_sum(contracts_costo),
                                 count = history_sum(contracts_received_n), .groups = "drop")
  ca <- z$contracts |> filter(window == w$window) |> left_join(cs, by = "unit_id")
  stopifnot(isTRUE(all.equal(ca$contract_value, ca$value, tolerance = 1e-6)),
            isTRUE(all.equal(ca$contract_count, ca$count)),
            all(is.na(ca$contract_value[ca$beneficiary_dates == 0])),
            all(is.na(ca$contract_count[ca$beneficiary_dates == 0])))
  ys <- z$youtube_source |> filter(between(date, w$from, w$to)) |>
    group_by(unit_id) |> summarise(complete = all(covered),
      nv = sum(youtube_n_videos), vv = sum(youtube_views), ll = sum(youtube_likes), cc = sum(youtube_comments),
      .groups = "drop")
  ya <- z$youtube |> filter(window == w$window) |> left_join(ys, by = "unit_id")
  valid <- ya$complete_grid
  stopifnot(all(ya$videos[valid] == ya$nv[valid]),
            all(ya$views[valid] == ya$vv[valid]), all(ya$likes[valid] == ya$ll[valid]),
            all(ya$comments[valid] == ya$cc[valid]),
            all(ya$interactions[valid] == ya$ll[valid] + ya$cc[valid]),
            all(is.na(ya$videos[!valid])))
  positive <- valid & ya$videos > 0
  stopifnot(isTRUE(all.equal(ya$interactions_per_video[positive],
                           ya$interactions[positive] / ya$videos[positive])),
            all(ya$interactions_per_video[valid & ya$videos == 0] == 0))
}
for (m in z$spec$metric) {
  d <- z$samples[[m]]
  stopifnot(!anyDuplicated(d[c("unit_id", "date")]), all(d$records > 0),
            all(d$date >= as.Date("2022-04-18")), !anyNA(d[z$windows$window]))
  if (m %in% c("contract_value", "contract_count")) {
    observed_units <- unique(z$contract_source$unit_id[z$contract_source$covered])
    stopifnot(all(d$unit_id %in% observed_units))
  }
  for (v in z$windows$window) {
    x <- d$ask - ave(d$ask, d$date)
    y <- d[[v]] - ave(d[[v]], d$date)
    manual <- sum(x * y) / sum(x * x)
    fit <- z$models[[m]][[v]]
    stopifnot(nobs(fit) == nrow(d),
              isTRUE(all.equal(unname(coef(fit)[["ask"]]), manual, tolerance = 1e-8)))
  }
  joint <- z$models[[m]]$joint
  stopifnot(all(names(coef(joint)) %in% z$windows$window), nobs(joint) == nrow(d))
  b <- coef(joint); V <- vcov(joint)
  manual_F <- as.numeric(crossprod(b, solve(V, b))) / length(b)
  expected <- z$joint_tests |> filter(metric == m)
  stopifnot(isTRUE(all.equal(manual_F, expected$F, tolerance = 1e-7)))
}
old <- readRDS("output/balance/prior_ratios/models.rds")
stopifnot(identical(z$samples$question_attendance_ratio$unit_id, old$sample$unit_id),
          isTRUE(all.equal(coef(z$models$question_attendance_ratio$ratio_12m),
                           coef(old$individual$ratio_12m))))
cat("PASS: contract NA versus observed-zero rules, deduplicated assets, pre-cutoff inputs, window sums and per-video means,\n",
    "48 same-sample individual coefficients, 12 ratio/metric-only joint Wald tests, prior-ratio reconciliation.\n")

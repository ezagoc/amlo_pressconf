suppressPackageStartupMessages({library(dplyr); library(fixest)})
z <- readRDS("output/balance/prior_ratios/models.rds")
d <- z$sample
w <- z$windows
stopifnot(identical(as.character(w$from), c("2021-04-18", "2020-10-18", "2020-04-18", "2018-12-01")),
          all(w$to == as.Date("2022-04-17")), all(d$date >= as.Date("2022-04-18")),
          all(d$date <= as.Date("2024-09-27")), all(d$records > 0),
          !anyDuplicated(d[c("unit_id", "date")]), !anyNA(d[w$variable]),
          setequal(names(coef(z$joint)), w$variable))
stopifnot(!any(format(z$history$date[z$history$common], "%Y-%m") == "2021-11"))
for (i in seq_len(nrow(w))) {
  window <- w[i, ]
  h <- z$history |> filter(common, between(date, window$from, window$to)) |>
    group_by(unit_id) |> summarise(n = sum(questions_n), denom = sum(records), .groups = "drop")
  actual <- z$histories |> filter(variable == window$variable) |> left_join(h, by = "unit_id")
  good <- is.finite(actual$denom) & actual$denom > 0
  stopifnot(isTRUE(all.equal(actual$ratio[good], actual$n[good] / actual$denom[good])),
            all(is.na(actual$ratio[!good])))
  x <- d$ask - ave(d$ask, d$date)
  y <- d[[window$variable]] - ave(d[[window$variable]], d$date)
  manual <- sum(x * y) / sum(x * x)
  fit <- z$individual[[window$variable]]
  stopifnot(nobs(fit) == nrow(d),
            isTRUE(all.equal(unname(coef(fit)[["ask"]]), manual, tolerance = 1e-8)))
}
b <- coef(z$joint); V <- vcov(z$joint)
manual_F <- as.numeric(crossprod(b, solve(V, b))) / length(b)
stopifnot(isTRUE(all.equal(manual_F, z$joint_test$stat, tolerance = 1e-8)),
          isTRUE(all.equal(pf(manual_F, length(b), n_distinct(d$unit_id)-1, lower.tail=FALSE),
                           z$joint_test$p, tolerance = 1e-8)))
# Reconciliation with the previous 12-month definition, not a different ratio.
old <- readRDS("output/balance/balance_models.rds")$sample |>
  distinct(unit_id, pre_questions_per_recorded_attendance_last_year)
check <- d |> distinct(unit_id, ratio_12m) |> left_join(old, by = "unit_id")
stopifnot(isTRUE(all.equal(check$ratio_12m, check$pre_questions_per_recorded_attendance_last_year)))
cat("PASS: four windows, count denominators, coverage, no post-cutoff leakage,\n",
    "same-sample individual tests, ratio-only joint Wald test, and old 12-month reconciliation.\n")

suppressPackageStartupMessages({library(dplyr); library(fixest)})
from_2023 <- "--from-2023" %in% commandArgs(trailingOnly = TRUE)
z <- readRDS(if (from_2023) "output/balance/from_2023/models.rds" else "output/balance/second_year/models.rds")
h <- readRDS("output/balance/historical_outcomes/models.rds")
j <- readRDS("output/balance/joint_by_window/models.rds")
expected_period <- if (from_2023) as.Date(c("2023-01-01", "2024-09-30")) else as.Date(c("2023-04-18", "2024-04-17"))
stopifnot(identical(z$period, expected_period),
          identical(z$windows, h$windows), nrow(z$individual) == 288, nrow(z$joint) == 24)
if (from_2023) stopifnot(nrow(z$end_date_coverage) == 6, !any(z$end_date_coverage$observed))
informative <- function(d) d |> group_by(date) |> filter(any(ask == 1), any(ask == 0)) |> ungroup()
for (key in names(z$individual_fits)) {
  k <- strsplit(key, "__", fixed = TRUE)[[1]]
  ids <- z$members$unit_id[z$members$group == k[1]]
  d <- h$samples[[k[2]]] |> filter(unit_id %in% ids, between(date, z$period[1], z$period[2])) |> informative()
  f <- z$individual_fits[[key]]
  r <- z$individual |> filter(group == k[1], metric == k[2], window == k[3])
  x <- d$ask - ave(d$ask, d$date); y <- d[[k[3]]] - ave(d[[k[3]]], d$date)
  b <- sum(x * y) / sum(x * x)
  stopifnot(nobs(f) == nrow(d), r$n == nrow(d), all(d$records > 0),
            isTRUE(all.equal(b, r$estimate, tolerance = 1e-7)),
            isTRUE(all.equal(unname(coeftable(f)["ask", 4]), r$p_value)))
}
for (key in names(z$joint_fits)) {
  k <- strsplit(key, "__", fixed = TRUE)[[1]]
  d <- z$joint_samples[[key]]; f <- z$joint_fits[[key]]
  ids <- z$members$unit_id[z$members$group == k[1]]
  expected <- j$raw_samples[[k[2]]] |>
    filter(unit_id %in% ids, between(date, z$period[1], z$period[2])) |> informative()
  stopifnot(identical(d$date, expected$date), identical(d$unit_id, expected$unit_id),
            all(d$records > 0), all(between(d$date, z$period[1], z$period[2])),
            !anyDuplicated(d[c("unit_id", "date")]))
  for (v in z$vars) {
    m <- !is.finite(expected[[v]])
    stopifnot(all(d[[v]][m] == 0),
              isTRUE(all.equal(d[[v]][!m], expected[[v]][!m] / sd(expected[[v]][!m]))))
  }
  r <- z$joint |> filter(group == k[1], window == k[2])
  if (r$status != "ok") next
  V <- vcov(f)[z$vars, z$vars]; b <- coef(f)[z$vars] / sqrt(diag(V))
  manual <- as.numeric(crossprod(b, solve(cov2cor(V), b))) / 12
  stopifnot(isTRUE(all.equal(manual, r$F, tolerance = 1e-5)),
            r$recenter_F_relative_error <= 1e-5,
            isTRUE(all.equal(pf(r$F, 12, r$df2, lower.tail = FALSE), r$p_value)))
}
stopifnot(all(is.na(z$joint$p_value[z$joint$status != "ok"])),
          all(z$joint$status[z$joint$group == "opposition"] == "not_estimable"))
cat("PASS: exact requested period, unchanged histories, 288 individual tests, full joint nulls, missingness rules and numerical checks.\n")

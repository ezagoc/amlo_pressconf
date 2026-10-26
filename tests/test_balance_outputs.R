# Validate the saved run without rebuilding the input panel.
# Run from repository root after 01-run_balance.R.
suppressPackageStartupMessages({library(dplyr); library(fixest)})
path <- "output/balance"
z <- readRDS(file.path(path, "balance_models.rds"))
d <- z$sample
stopifnot(!anyDuplicated(d[c("unit_id", "date")]),
          all(d$attendance_n_journalists_recorded > 0),
          all(d$attendance_observed & d$questions_observed),
          all(d$attendance_matched & d$questions_matched),
          all(d$date >= z$period[1] & d$date <= z$period[2]),
          all(d$ask %in% 0:1), nobs(z$joint) == nrow(d))
source_pairs <- d |> distinct(unit_id, attendance_entity_id, questions_entity_id)
stopifnot(!anyDuplicated(source_pairs$unit_id),
          !anyDuplicated(source_pairs$attendance_entity_id),
          !anyDuplicated(source_pairs$questions_entity_id))

# Requested coding is consistent in individual and joint samples.
zero_flags <- c("coverage_national", "media_radio", "media_television",
                "media_print_any", "media_digital", "media_social_media", "media_personal",
                "subscription_binary")
stopifnot(all(unlist(d[zero_flags]) %in% 0:1),
          !anyNA(d$pre_contracts_costo_last_year),
          !anyNA(d$pre_contracts_received_n_last_year),
          "pre_questions_per_recorded_attendance_last_year" %in% names(coef(z$joint)),
          !any(c("log_pre_questions", "log_pre_attendance") %in% names(coef(z$joint))),
          !z$ratio_variable %in% names(z$individual),
          !"ideology_4t_unclear" %in% names(coef(z$joint)),
          "ideology_4t_unclear" %in% names(z$individual))
iv <- c("ideology_4t_aligned", "ideology_4t_unclear", "ideology_4t_opposition")
known <- complete.cases(d[iv])
stopifnot(all(rowSums(d[known, iv]) == 1),
          all(rowSums(is.na(d[!known, iv])) == 3))
denom <- d$pre_common_attendance_recorded_last_year
ratio <- d$pre_questions_per_recorded_attendance_last_year
ok <- is.finite(denom) & denom > 0
stopifnot(isTRUE(all.equal(ratio[ok], d$pre_common_questions_last_year[ok] / denom[ok])),
          all(is.na(ratio[is.finite(denom) & denom == 0])))
contract_audit <- read.csv(file.path(path, "contract_beneficiary_audit.csv"))
stopifnot(!anyDuplicated(contract_audit[c("unit_id", "contracts_entity_id", "window")]))
money <- contract_audit |> filter(window == "last_year") |> group_by(unit_id) |>
  summarise(expected = sum(contracts_costo, na.rm = TRUE), .groups = "drop")
actual <- d |> distinct(unit_id, pre_contracts_costo_last_year) |> left_join(money, by = "unit_id")
# CSV round-tripping can change sub-micro-peso floating-point precision.
stopifnot(all(abs(actual$pre_contracts_costo_last_year - coalesce(actual$expected, 0)) < 1e-6))

# Independent FWL check: partial out date AND prior ratio from X and ask.
for (v in names(z$individual)) {
  s <- d |> filter(is.finite(.data[[v]]), is.finite(.data[[z$ratio_variable]])) |>
    group_by(date) |> filter(any(ask == 1), any(ask == 0)) |> ungroup()
  y <- s[[v]] - ave(s[[v]], s$date)
  x <- s$ask - ave(s$ask, s$date)
  r <- s[[z$ratio_variable]] - ave(s[[z$ratio_variable]], s$date)
  unadjusted <- sum(x * y) / sum(x * x)
  qr_control <- qr(matrix(r, ncol = 1))
  y <- qr.resid(qr_control, y)
  x <- qr.resid(qr_control, x)
  manual <- sum(x * y) / sum(x * x)
  stopifnot(isTRUE(all.equal(unname(coef(z$individual[[v]])[["ask"]]), manual, tolerance = 1e-8)),
            nobs(z$individual[[v]]) == nrow(s))
  stopifnot(isTRUE(all.equal(unname(coef(z$unadjusted[[v]])[["ask"]]), unadjusted, tolerance = 1e-8)),
            nobs(z$unadjusted[[v]]) == nrow(s))
}

# Independent joint Wald calculation using the saved clustered covariance.
keep <- intersect(z$core, names(coef(z$joint)))
b <- coef(z$joint)[keep]
V <- vcov(z$joint)[keep, keep, drop = FALSE]
stopifnot(min(eigen(V, symmetric = TRUE, only.values = TRUE)$values) > 0)
manual_F <- as.numeric(crossprod(b, solve(V, b))) / length(b)
stopifnot(isTRUE(all.equal(manual_F, z$joint_wald$stat, tolerance = 1e-8)),
          isTRUE(all.equal(pf(manual_F, length(b), n_distinct(d$unit_id) - 1, lower.tail = FALSE),
                           z$joint_wald$p, tolerance = 1e-8)))
tab <- read.csv(file.path(path, "individual_balance_all_windows.csv"))
stopifnot(all(tab$ci_low <= tab$estimate, na.rm = TRUE),
          all(tab$ci_high >= tab$estimate, na.rm = TRUE),
          all(tab$p_value >= 0 & tab$p_value <= 1, na.rm = TRUE))
cat("PASS: unique source units, recorded attendance, coverage, dates,",
    length(z$individual), "within-day coefficients, clustered joint Wald test, and intervals.\n")

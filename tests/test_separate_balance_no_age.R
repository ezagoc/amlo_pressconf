suppressPackageStartupMessages({library(dplyr);library(fixest)})
args <- commandArgs(TRUE)
months <- if (length(args)) as.integer(sub("--months=", "", args)) else 12L
window <- paste0("ratio_", months, "m")
x <- readRDS(paste0("output/balance/separate_", months, "m_no_age/models.rds"))
old <- readRDS("output/balance/full_post_18m_metadata/models.rds")
j <- readRDS("output/balance/joint_by_window/models.rds")
h <- readRDS("output/balance/historical_outcomes/models.rds")
stopifnot(nrow(x$individual) == 21, nrow(x$joint) == 2,
          !"age_2022" %in% x$spec$metric, !"combined" %in% names(x$joint_fits),
          all(x$joint$n == 7976), all(x$joint$units == 81), all(x$joint$dates == 318),
          all(x$individual$n[x$individual$family == "Metadata"] == 7976),
          identical(coef(x$joint_fits$histories), coef(j$models[[window]])),
          identical(vcov(x$joint_fits$histories), vcov(j$models[[window]])),
          identical(filter(x$individual, family == "Metadata"),
                    filter(old$individual, family == "Metadata", metric != "age_2022")),
          identical(x$joint$missingness_controls, c(0L,3L)))
stopifnot(identical(x$raw[h$spec$metric], j$raw_samples[[window]][h$spec$metric]),
          x$history_window$to == as.Date("2022-04-17"),
          x$history_window$from == as.Date(if (months == 12) "2021-04-18" else "2020-10-18"))
for (v in h$spec$metric) {
  stopifnot(identical(x$individual_samples[[v]]$x, h$samples[[v]][[window]]),
            identical(coef(x$individual_fits[[v]]), coef(h$models[[v]][[window]])))
}
fit <- x$joint_fits$metadata
stopifnot(length(coef(fit)) == 9, !any(grepl("^age_2022$|^missing_", names(coef(fit)))))
V <- vcov(fit); z <- coef(fit) / sqrt(diag(V))
F <- drop(crossprod(z, solve(cov2cor(V), z))) / 9
r <- filter(x$joint, test == "metadata")
stopifnot(isTRUE(all.equal(F, r$F, tolerance = 1e-7)),
          abs(pf(F,9,80,lower.tail=FALSE) - r$p_value) < 1e-10)
cat("PASS: metadata unchanged, no age; selected", months, "month histories; separate tests; full metadata N.\n")

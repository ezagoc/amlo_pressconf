suppressPackageStartupMessages({library(dplyr);library(fixest)})
x <- readRDS("output/balance/full_post_18m_metadata/models.rds")
h <- readRDS("output/balance/historical_outcomes/models.rds")
j <- readRDS("output/balance/joint_by_window/models.rds")
stopifnot(nrow(x$individual) == 22, nrow(x$joint) == 3, nrow(x$raw) == 7976,
          n_distinct(x$raw$unit_id) == 81, n_distinct(x$raw$date) == 318,
          !anyDuplicated(x$raw[c("unit_id", "date")]), all(x$raw$records > 0),
          all(x$raw$ask %in% 0:1), min(x$raw$date) == as.Date("2022-04-19"),
          max(x$raw$date) == as.Date("2024-09-27"))
for (v in h$spec$metric) {
  stopifnot(identical(x$individual_samples[[v]]$ratio_18m, h$samples[[v]]$ratio_18m),
            isTRUE(all.equal(coef(x$individual_fits[[v]])[["ask"]],
                             coef(h$models[[v]]$ratio_18m)[["ask"]])))
}
for (g in names(x$joint_fits)) {
  fit <- x$joint_fits[[g]]
  terms <- setdiff(names(coef(fit)), grep("^missing_", names(coef(fit)), value = TRUE))
  V <- vcov(fit)[terms, terms]; z <- coef(fit)[terms] / sqrt(diag(V))
  F <- drop(crossprod(z, solve(cov2cor(V), z))) / length(terms)
  r <- x$joint |> filter(test == g)
  stopifnot(isTRUE(all.equal(F, r$F, tolerance = 1e-6)),
            abs(pf(F, length(terms), 80, lower.tail = FALSE) - r$p_value) < 1e-8)
}
a <- x$audit
valid <- grepl("^[0-9]{4}$", trimws(a$year_founded)) & !is.na(a$year_founded)
year <- suppressWarnings(as.numeric(a$year_founded))
stopifnot(all(a$age_2022[valid & year <= 2022] == 2022 - year[valid & year <= 2022]),
          all(is.na(a$age_2022[!valid])), all(is.na(x$units$age_2022[x$units$founding_age_conflict])),
          all(a$mexico_city == as.integer(!is.na(a$city.headq) & a$city.headq == 9)),
          all(a$metropolitan_area == as.integer(grepl("\\bmetropolitan\\b", tolower(coalesce(a$coverage.scope, ""))))))
stopifnot(all(is.na(x$raw$contract_value) == is.na(j$raw_samples$ratio_18m$contract_value)))
cat("22 individual tests; 3 independently checked joint tests; metadata coding and source-ID checks passed.\n")

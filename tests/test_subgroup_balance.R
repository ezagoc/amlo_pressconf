suppressPackageStartupMessages({library(dplyr); library(fixest)})
z <- readRDS("output/balance/subgroups/models.rds")
u <- read.csv("output/balance/analysis_unit_covariates.csv")
stopifnot(nrow(z$individual) == 240, nrow(z$joint) == 20,
          !anyDuplicated(z$members[c("group", "unit_id")]))
for (g in z$groups$group) {
  flag <- z$groups$flag[z$groups$group == g]
  ids <- z$members$unit_id[z$members$group == g]
  stopifnot(all(u[[flag]][match(ids, u$unit_id)] == 1))
}
for (key in names(z$joint_fits)) {
  d <- z$joint_samples[[key]]; f <- z$joint_fits[[key]]
  keys <- strsplit(key, "__", fixed = TRUE)[[1]]
  r <- z$joint |> filter(group == keys[1], window == keys[2])
  stopifnot(all(d$records > 0), !anyDuplicated(d[c("unit_id", "date")]),
            all(tapply(d$ask, d$date, function(x) all(c(0, 1) %in% x))),
            all(d$unit_id %in% z$members$unit_id[z$members$group == keys[1]]))
  if (r$status != "ok") next
  V <- vcov(f)[z$vars, z$vars]; b <- coef(f)[z$vars]
  # Solve the standardized covariance system as an independent Wald check.
  se <- sqrt(diag(V)); C <- cov2cor(V); bs <- b / se
  independent <- as.numeric(crossprod(bs, solve(C, bs))) / 12
  stopifnot(isTRUE(all.equal(independent, r$F, tolerance = 1e-5)),
            r$covariance_rank == 12, r$recenter_F_relative_error <= 1e-5,
            isTRUE(all.equal(pf(r$F, 12, r$df2, lower.tail = FALSE), r$p_value)))
}
for (key in names(z$individual_fits)) {
  keys <- strsplit(key, "__", fixed = TRUE)[[1]]
  r <- z$individual |> filter(group == keys[1], metric == keys[2], window == keys[3])
  f <- z$individual_fits[[key]]
  stopifnot(isTRUE(all.equal(unname(coeftable(f)["ask", 4]), r$p_value)))
}
stopifnot(all(is.na(z$joint$p_value[z$joint$status != "ok"])),
          all(z$joint$status[z$joint$group == "opposition"] == "not_estimable"))
cat("PASS: subgroup membership, within-day recorded attendance, 240 individual tests, full historical joint nulls, numerical checks and non-estimable opposition.\n")

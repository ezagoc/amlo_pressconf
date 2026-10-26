suppressPackageStartupMessages({library(dplyr); library(fixest)})
z <- readRDS("output/balance/joint_by_window/models.rds")
base <- readRDS("output/balance/prior_ratios/models.rds")$base
for (w in z$windows$window) {
  d <- z$samples[[w]]; raw <- z$raw_samples[[w]]; fit <- z$models[[w]]
  stopifnot(identical(d$unit_id, base$unit_id), identical(d$date, base$date),
            all(d$records > 0), nobs(fit) == nrow(base),
            !anyDuplicated(d[c("unit_id", "date")]))
  map <- z$missing_maps[[w]]
  for (v in z$vars) {
    m <- !is.finite(raw[[v]])
    stopifnot(all(d[[v]][m] == 0),
              isTRUE(all.equal(d[[v]][!m], raw[[v]][!m] / sd(raw[[v]][!m]))))
    indicator <- map$indicator[map$metric == v]
    if (any(m)) stopifnot(identical(d[[indicator]], as.integer(m)))
  }
  # Independently recover all coefficients after removing day means.
  terms <- names(coef(fit))
  X <- as.matrix(d[terms]); y <- d$ask - ave(d$ask, d$date)
  for (j in seq_along(terms)) X[, j] <- X[, j] - ave(X[, j], d$date)
  independent <- qr.solve(X, y)
  stopifnot(isTRUE(all.equal(unname(independent), unname(coef(fit)), tolerance = 1e-6)))
  for (kind in c("histories", "histories_and_missingness")) {
    selected <- if (kind == "histories") z$vars else terms
    b <- coef(fit)[selected]; V <- vcov(fit)[selected, selected]
    F <- as.numeric(crossprod(b, solve(V, b))) / length(b)
    r <- z$tests |> filter(window == w, test == kind)
    stopifnot(qr(V)$rank == length(b), isTRUE(all.equal(F, r$F, tolerance = 1e-6)),
              isTRUE(all.equal(pf(F, r$df1, r$df2, lower.tail = FALSE), r$p_value, tolerance = 1e-6)))
  }
  # Center observed histories: changing missing placeholders must not change
  # fitted values or either joint null when missing indicators are included.
  centered <- d
  for (v in z$vars) {
    m <- !is.finite(raw[[v]])
    centered[[v]][!m] <- centered[[v]][!m] - mean(centered[[v]][!m])
  }
  other <- feols(as.formula(paste("ask ~", paste(terms, collapse = "+"), "| date")),
                 centered, cluster = ~unit_id)
  stopifnot(isTRUE(all.equal(fitted(fit), fitted(other), tolerance = 1e-7)))
  for (kind in c("histories", "histories_and_missingness")) {
    selected <- if (kind == "histories") z$vars else terms
    wt <- wald(other, keep = paste0("^(", paste(selected, collapse = "|"), ")$"), print = FALSE)
    r <- z$tests |> filter(window == w, test == kind)
    stopifnot(isTRUE(all.equal(wt$stat, r$F, tolerance = 1e-5)))
  }
}
cat("PASS: common sample, original missingness, indicator coding, all coefficients, eight Wald tests, placeholder invariance.\n")

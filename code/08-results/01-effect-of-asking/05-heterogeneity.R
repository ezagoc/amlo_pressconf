# Recorded-attendee heterogeneity; preserve all pooled and source files.
entry <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)[1])
source(file.path(dirname(entry), "00-config.R"))
suppressPackageStartupMessages({library(arrow); library(dplyr); library(fixest)})
setFixest_nthreads(1)
x <- readRDS(file.path(out, "analysis_panel.rds"))
out <- file.path(out, "heterogeneity")
dir.create(out, recursive = TRUE, showWarnings = FALSE)
groups <- c("Opposition", "Aligned", "Independent")
cw_path <- file.path(source_dir, "metadata_outcome_crosswalk.parquet")
cw <- read_parquet(cw_path) |> filter(outcome == "attendance") |>
  transmute(unit_id = entity_id, metadata_id, outlet_name, ideology_4t) |> distinct()
save_csv(cw |> filter(unit_id %in% x$data$unit_id), "metadata_members.csv")
classifications <- cw |> group_by(unit_id) |>
  summarise(codes = paste(sort(unique(na.omit(ideology_4t))), collapse = " | "),
            n_codes = n_distinct(ideology_4t, na.rm = TRUE),
            .groups = "drop") |>
  mutate(group = case_when(codes == "opp" ~ "Opposition",
                           codes == "aligned" ~ "Aligned",
                           codes == "unclear" ~ "Independent", TRUE ~ NA_character_))
d <- x$data |> left_join(classifications, by = "unit_id", relationship = "many-to-one")
stopifnot(nrow(d) == nrow(x$data), !anyDuplicated(d[c("unit_id", "date")]))
save_csv(d |> distinct(unit_id, outlet_names, codes, n_codes, group), "classification_audit.csv")
save_csv(data.frame(path = cw_path, md5 = unname(tools::md5sum(cw_path))), "input_manifest.csv")
rows <- fits <- inputs <- flows <- list()
for (g in groups) {
  before <- d |> filter(group == g)
  dg <- informative(before)
  stopifnot(nrow(dg) > 0, all(dg$records > 0))
  flows[[g]] <- bind_rows(flow_row(before, "Classified main input"),
                          flow_row(dg, "Within-group same-day asking variation")) |> mutate(group = g)
  gx <- x; gx$data <- dg
  inputs[[g]] <- dg
  saveRDS(gx, file.path(out, paste0(tolower(g), "_panel.rds")))
  for (outcome in OUTCOMES) for (adjusted in c(FALSE, TRUE)) {
    model <- if (adjusted) "History adjusted" else "Baseline"
    rhs <- c("ask", if (adjusted) x$controls)
    f <- feols(as.formula(paste0("log_", outcome, " ~ ", paste(rhs, collapse = " + "),
                                 " | unit_id + date")), dg, cluster = ~unit_id, notes = FALSE)
    stopifnot("ask" %in% names(coef(f)))
    dd <- dg[obs(f), ]
    ct <- coeftable(f)["ask", ]; ci <- confint(f, "ask")
    key <- paste(g, outcome, model, sep = ":")
    fits[[key]] <- f
    rows[[key]] <- data.frame(group = g, outcome, model, estimate = ct[1], se = ct[2],
      ci_low = as.numeric(ci[[1]]), ci_high = as.numeric(ci[[2]]), p_value = ct[4], n = nobs(f),
      units = n_distinct(dd$unit_id), dates = n_distinct(dd$date),
      asking = sum(dd$ask), asking_units = n_distinct(dd$unit_id[dd$ask == 1]),
      within_r2 = as.numeric(fitstat(f, "wr2")[[1]]),
      dropped_controls = paste(f$collin.var, collapse = " | "))
    flows[[key]] <- flow_row(dd, paste(outcome, model, "after singleton removal")) |> mutate(group = g)
  }
}
save_csv(bind_rows(rows), "regression_results.csv")
save_csv(bind_rows(flows), "sample_flow.csv")
saveRDS(fits, file.path(out, "regression_fits.rds"))

# Formal contrasts: a fully interacted stack exactly reproduces the separate
# point estimates, with group-by-date FE and group-specific history slopes.
# Inference clusters by source unit; common CRV finite-sample adjustment and
# conservative t/F denominator min(number of units in compared groups)-1.
stack <- bind_rows(inputs)
stack$group_date <- interaction(stack$group, stack$date, drop = TRUE)
all_rhs <- base_rhs <- character()
for (g in groups) {
  a <- paste0("ask_", tolower(g))
  stack[[a]] <- stack$ask * (stack$group == g)
  base_rhs <- c(base_rhs, a)
  for (v in x$controls) {
    nm <- paste0(v, "_", tolower(g))
    stack[[nm]] <- stack[[v]] * (stack$group == g)
    all_rhs <- c(all_rhs, nm)
  }
}
contrasts <- stacked <- list()
for (outcome in OUTCOMES) for (adjusted in c(FALSE, TRUE)) {
  model <- if (adjusted) "History adjusted" else "Baseline"
  rhs <- c(base_rhs, if (adjusted) all_rhs)
  f <- feols(as.formula(paste0("log_", outcome, " ~ ", paste(rhs, collapse = " + "),
                               " | unit_id + group_date")), stack, cluster = ~unit_id, notes = FALSE)
  b <- coef(f)[base_rhs]; V <- vcov(f)[base_rhs, base_rhs, drop = FALSE]
  nn <- vapply(groups, function(g) rows[[paste(g, outcome, model, sep = ":")]]$units, numeric(1))
  for (i in seq_along(groups)) stopifnot(abs(b[i] - rows[[paste(groups[i], outcome, model, sep = ":")]]$estimate) < 1e-7)
  for (pair in combn(seq_along(groups), 2, simplify = FALSE)) {
    L <- numeric(3); L[pair] <- c(1, -1)
    delta <- sum(L * b); se <- sqrt(as.numeric(t(L) %*% V %*% L))
    df <- min(nn[pair]) - 1
    contrasts[[paste(outcome, model, paste(pair, collapse = ""))]] <- data.frame(
      outcome, model, test = paste(groups[pair], collapse = " - "), estimate = delta, se,
      ci_low = delta - qt(.975, df) * se, ci_high = delta + qt(.975, df) * se,
      statistic = (delta / se)^2, df_num = 1, df_den = df,
      p_value = 2 * pt(-abs(delta / se), df))
  }
  L <- rbind(c(1,-1,0), c(1,0,-1)); lb <- L %*% b
  stat <- as.numeric(t(lb) %*% solve(L %*% V %*% t(L), lb)) / 2
  contrasts[[paste(outcome, model, "joint")]] <- data.frame(outcome, model,
    test = "All three effects equal", estimate = NA_real_, se = NA_real_,
    ci_low = NA_real_, ci_high = NA_real_, statistic = stat,
    df_num = 2, df_den = min(nn) - 1, p_value = pf(stat, 2, min(nn)-1, lower.tail = FALSE))
  stacked[[paste(outcome, model, sep = ":")]] <- f
}
save_csv(bind_rows(contrasts), "effect_difference_tests.csv")
saveRDS(stacked, file.path(out, "stacked_fits.rds"))
print(bind_rows(rows) |> select(group, outcome, model, estimate, p_value, n, units, dates, asking, asking_units), width = 180)
print(bind_rows(contrasts) |> filter(test == "All three effects equal"))

# Main heterogeneity: asking x ideology, shared date FE and common history slopes.
# Separate subgroup regressions and FEct files remain untouched.
entry <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)[1])
source(file.path(dirname(entry), "00-config.R"))
suppressPackageStartupMessages({library(arrow); library(dplyr); library(fixest)})
setFixest_nthreads(1)
combine <- "--combine" %in% commandArgs(TRUE)
panel_path <- file.path(out, "analysis_panel.rds")
x <- readRDS(panel_path)
manifest <- read.csv(file.path(out, "input_manifest.csv"))
stopifnot(identical(unname(tools::md5sum(manifest$path)), manifest$md5))
previous_panel <- file.path(out, "pooled_interactions", "analysis_panel.rds")
out <- file.path(out, if (combine) "pooled_interactions_combined" else "pooled_interactions")
dir.create(out, recursive = TRUE, showWarnings = FALSE)
cw_path <- file.path(source_dir, "metadata_outcome_crosswalk.parquet")
cw <- read_parquet(cw_path) |> filter(outcome == "attendance") |>
  transmute(unit_id = entity_id, metadata_id, outlet_name, ideology_4t) |> distinct()
classes <- cw |> group_by(unit_id) |>
  summarise(codes = paste(sort(unique(na.omit(ideology_4t))), collapse = " | "), .groups = "drop") |>
  mutate(group = case_when(codes == "opp" ~ "Opposition", codes == "aligned" ~ "Aligned",
                           codes == "unclear" ~ "Independent", TRUE ~ NA_character_))
all <- x$data |> left_join(classes, by = "unit_id", relationship = "many-to-one")
if (combine) all <- all |> mutate(group_original = group,
  group = ifelse(group %in% c("Opposition", "Independent"), "Opp. + Independent", group))
classified <- all |> filter(!is.na(group))
d <- informative(classified) |> mutate(ask_aligned = ask * (group == "Aligned"),
                                      ask_independent = ask * (group == "Independent"))
stopifnot(nrow(d) > 0, !anyDuplicated(d[c("unit_id", "date")]), all(d$records > 0),
          all(d$covered), all(d$date >= FROM & d$date <= TO))
for (o in OUTCOMES) stopifnot(identical(d[[paste0("log_", o)]], log1p(d[[o]])))
save_csv(all |> distinct(unit_id, outlet_names, codes, group), "classification_audit.csv")
save_csv(anti_join(all, d, by = c("unit_id", "date")) |>
           select(unit_id, date, ask, group, codes), "sample_exclusions.csv")
paths <- c(panel_path, cw_path)
save_csv(data.frame(path = paths, md5 = unname(tools::md5sum(paths))), "input_manifest.csv")

fits <- effects <- interactions <- differences <- joint <- samples <- list()
terms <- c("ask", "ask_aligned", "ask_independent")
weights <- rbind(Opposition = c(1,0,0), Aligned = c(1,1,0), Independent = c(1,0,1))
if (combine) {
  terms <- c("ask", "ask_aligned")
  weights <- rbind("Opp. + Independent" = c(1,0), Aligned = c(1,1))
}
slope_names <- setNames(paste0("slope_", seq_len(nrow(weights))), rownames(weights))
first_obs <- NULL
for (o in OUTCOMES) for (adjusted in c(FALSE, TRUE)) {
  m <- if (adjusted) "History adjusted" else "Baseline"
  rhs <- c(terms, if (adjusted) x$controls)
  f <- feols(as.formula(paste0("log_", o, " ~ ", paste(rhs, collapse = " + "),
                               " | unit_id + date")), d, cluster = ~unit_id, notes = FALSE)
  key <- paste(o, m, sep = ":")
  fits[[key]] <- f
  used <- d[obs(f), ]
  if (is.null(first_obs)) first_obs <- obs(f)
  stopifnot(identical(first_obs, obs(f)), all(terms %in% names(coef(f))))
  b <- coef(f)[terms]; V <- vcov(f)[terms, terms, drop = FALSE]
  df <- degrees_freedom(f, "t")
  stopifnot(df == n_distinct(used$unit_id) - 1)
  contrast <- function(w, label) {
    beta <- as.numeric(w %*% b)
    se <- sqrt(as.numeric(w %*% V %*% w))
    data.frame(outcome = o, model = m, label, estimate = beta, se,
      ci_low = beta - qt(.975, df)*se, ci_high = beta + qt(.975, df)*se,
      p_value = 2*pt(-abs(beta/se), df), df = df)
  }
  for (g in rownames(weights)) effects[[paste(key, g)]] <- contrast(weights[g, ], g)
  for (i in seq_along(terms)) interactions[[paste(key, terms[i])]] <- contrast(diag(length(terms))[i, ], terms[i])
  pair_weights <- rbind("Aligned - Opposition" = c(0,1,0),
                       "Independent - Opposition" = c(0,0,1),
                       "Aligned - Independent" = c(0,1,-1))
  if (combine) pair_weights <- rbind("Aligned - (Opp. + Independent)" = c(0,1))
  for (label in rownames(pair_weights)) differences[[paste(key, label)]] <- contrast(pair_weights[label, ], label)
  w <- wald(f, keep = "^ask_(aligned|independent)$", print = FALSE)
  restrictions <- length(terms) - 1L
  manual_F <- as.numeric(t(b[-1]) %*% solve(V[-1,-1, drop = FALSE], b[-1])) / restrictions
  stopifnot(abs(w$stat - manual_F) < 1e-9, w$df1 == restrictions, w$df2 == df)
  joint[[key]] <- data.frame(outcome = o, model = m, F = w$stat,
    df_num = w$df1, df_den = w$df2, p_value = w$p)
  samples[[key]] <- data.frame(outcome = o, model = m, n = nobs(f),
    units = n_distinct(used$unit_id), dates = n_distinct(used$date), asking = sum(used$ask),
    from = min(used$date), to = max(used$date), df = df,
    dropped_controls = paste(f$collin.var, collapse = " | "))
  # Independent equivalent parameterization: one asking slope per group, with
  # the SAME shared FE and history controls (not separate subgroup regressions).
  dd <- d
  for (g in rownames(weights)) dd[[slope_names[[g]]]] <- dd$ask * (dd$group == g)
  other <- feols(as.formula(paste0("log_", o, " ~ ",
      paste(c(unname(slope_names), if (adjusted) x$controls), collapse = " + "),
      " | unit_id + date")), dd, cluster = ~unit_id, notes = FALSE)
  stopifnot(identical(obs(f), obs(other)))
  for (g in rownames(weights)) {
    r <- effects[[paste(key, g)]]
    stopifnot(abs(r$estimate - coef(other)[[slope_names[[g]]]]) < 1e-8,
              abs(r$se - se(other)[[slope_names[[g]]]]) < 1e-8)
  }
}
used <- d[first_obs, ]
if (combine) {
  previous <- readRDS(previous_panel)
  old_used <- previous$data[previous$estimation_rows, ]
  compare <- c("unit_id", "date", "ask", "records", OUTCOMES, x$controls)
  stopifnot(identical(previous$controls, x$controls),
            isTRUE(all.equal(as.data.frame(used[compare]), as.data.frame(old_used[compare]))))
  cat("PASS: two-group model uses exactly the previous three-group sample and controls.\n")
}
save_csv(bind_rows(effects), "group_effects.csv")
save_csv(bind_rows(interactions), "interaction_coefficients.csv")
save_csv(bind_rows(differences), "pairwise_differences.csv")
save_csv(bind_rows(joint), "joint_tests.csv")
save_csv(bind_rows(samples), "model_samples.csv")
save_csv(used |> group_by(group) |> summarise(n = n(), units = n_distinct(unit_id),
  dates = n_distinct(date), asking = sum(ask), asking_units = n_distinct(unit_id[ask == 1]),
  .groups = "drop"), "group_sample_sizes.csv")
save_csv(bind_rows(flow_row(x$data, "Pooled input"), flow_row(classified, "Unambiguous ideology"),
                  flow_row(d, "Pooled within-date variation"), flow_row(used, "After FE singleton removal")), "sample_flow.csv")
save_csv(anti_join(d, used, by = c("unit_id", "date")) |> select(unit_id, date, group, ask), "singleton_exclusions.csv")
saveRDS(list(data = d, estimation_rows = first_obs, controls = x$controls), file.path(out, "analysis_panel.rds"))
saveRDS(fits, file.path(out, "fits.rds"))
capture.output(sessionInfo(), file = file.path(out, "session_info.txt"))
print(bind_rows(effects) |> filter(model == "History adjusted"))
print(bind_rows(joint))
print(read.csv(file.path(out, "group_sample_sizes.csv")))
cat("PASS: common sample across six fits; all group effects and clustered SEs verified\n",
    "against equivalent direct-slope models; all six joint tests independently verified.\n", sep = "")

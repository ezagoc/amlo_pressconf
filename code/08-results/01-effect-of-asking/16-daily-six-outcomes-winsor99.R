# Extend the SAME daily samples to six outcomes; upper-only p99 BEFORE transformation.
# Optional --transform=asinh or --transform=chen_roth_x0 (default log1p).
# Preserve all original raw-outcome models. Common cutoffs come from the pooled
# estimation sample, not separately by ideology or treatment.
entry <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)[1])
source(file.path(dirname(entry), "00-config.R"))
suppressPackageStartupMessages({library(arrow); library(dplyr); library(fixest)})
setFixest_nthreads(1)
original_out <- out
OUTCOMES <- c(OUTCOMES, "videos", "interactions", "mean_interactions")
check_manifest <- function(folder) {
  z <- read.csv(file.path(folder, "input_manifest.csv"))
  stopifnot(identical(unname(tools::md5sum(z$path)), z$md5))
  z$path
}
paths <- check_manifest(original_out)
main_path <- file.path(original_out, "analysis_panel.rds")
main_fit_path <- file.path(original_out, "regression_fits.rds")
x <- readRDS(main_path)
old_main <- readRDS(main_fit_path)
main_rows <- obs(old_main[["likes:Baseline"]])
old_inter_dir <- file.path(original_out, "pooled_interactions_combined")
paths <- c(paths, check_manifest(old_inter_dir), main_path, main_fit_path,
           file.path(old_inter_dir, c("analysis_panel.rds", "fits.rds")))
ix <- readRDS(file.path(old_inter_dir, "analysis_panel.rds"))
old_inter <- readRDS(file.path(old_inter_dir, "fits.rds"))
stopifnot(identical(x$controls, ix$controls))

# Independent source check for newly used video counts, using unique source links.
y <- open_dataset(file.path(source_dir, "youtube_entity_daily_panel.parquet")) |>
  filter(date >= FROM, date <= TO) |>
  select(entity_id, date, youtube_n_videos) |> collect() |>
  inner_join(x$links |> select(unit_id, entity_id), by = "entity_id", relationship = "many-to-one")
stopifnot(!anyDuplicated(y[c("entity_id", "date")]))
fresh <- y |> group_by(unit_id, date) |>
  summarise(source_videos = sum(youtube_n_videos), .groups = "drop")
audit <- x$data |> select(unit_id, date, videos) |>
  left_join(fresh, by = c("unit_id", "date"), relationship = "one-to-one")
stopifnot(all(is.finite(audit$source_videos)), all(audit$videos == audit$source_videos))
augment <- function(d) {
  stopifnot(all(is.finite(d$videos)), all(d$videos >= 0), all(d$videos == floor(d$videos)))
  d$interactions <- d$likes + d$comments
  stopifnot(!any(d$videos == 0 & d$interactions > 0))
  d$mean_interactions <- ifelse(d$videos > 0, d$interactions / pmax(d$videos, 1), 0)
  stopifnot(all(is.finite(as.matrix(d[OUTCOMES]))), all(as.matrix(d[OUTCOMES]) >= 0))
  d
}
x$data <- augment(x$data)
ix$data <- augment(ix$data)
cuts <- bind_rows(lapply(OUTCOMES, function(o) {
  raw <- x$data[[o]][main_rows]
  upper <- unname(quantile(raw, .99, type = 7))
  positive_min <- min(pmin(raw[raw > 0], upper))
  stopifnot(is.finite(positive_min), positive_min > 0)
  data.frame(outcome = o, percentile = .99, upper, quantile_type = 7L,
    positive_min, chen_roth_value_at_zero = log(positive_min),
    cutoff_sample_n = length(raw), n_capped_pooled = sum(raw > upper),
    n_capped_interaction = sum(ix$data[[o]][ix$estimation_rows] > upper))
}))
cap <- function(d) {
  for (o in OUTCOMES) {
    upper <- cuts$upper[cuts$outcome == o]
    d[[paste0("winsor_", o)]] <- pmin(d[[o]], upper)
    y <- d[[paste0("winsor_", o)]]
    positive_min <- cuts$positive_min[cuts$outcome == o]
    # log_ is a legacy model-column prefix, not a claim about the transformation.
    d[[paste0("log_", o)]] <- switch(DAILY_TRANSFORMATION,
      log1p = log1p(y), asinh = asinh(y),
      chen_roth_x0 = log(ifelse(y > 0, y, positive_min)))
    if (DAILY_TRANSFORMATION == "chen_roth_x0") {
      normalized <- log(ifelse(y > 0, y / positive_min, 1))
      stopifnot(max(abs(d[[paste0("log_", o)]] - normalized - log(positive_min))) < 1e-10)
    }
    stopifnot(all(is.finite(d[[paste0("log_", o)]])))
    stopifnot(all(d[[paste0("winsor_", o)]] <= upper),
      all(d[[o]][d[[o]] <= upper] == d[[paste0("winsor_", o)]][d[[o]] <= upper]))
  }
  d
}
x$data <- cap(x$data)
ix$data <- cap(ix$data)
out <- file.path(original_out, paste0("daily_winsor99_six_outcomes", DAILY_TRANSFORMATION_SUFFIX))
dir.create(out, recursive = TRUE, showWarnings = FALSE)
save_csv(cuts, "winsorization_cutoffs.csv")
save_csv(data.frame(sample = c("Pooled", "Interaction"),
  n = c(length(main_rows), length(ix$estimation_rows)),
  zero_video_days = c(sum(x$data$videos[main_rows] == 0), sum(ix$data$videos[ix$estimation_rows] == 0))),
  "outcome_definition_audit.csv")
new_root <- out

for (interaction in c(FALSE, TRUE)) {
  panel <- if (interaction) ix else x
  d <- panel$data
  expected <- if (interaction) ix$estimation_rows else main_rows
  old <- if (interaction) old_inter else old_main
  out <- if (interaction) file.path(new_root, "pooled_interactions_combined") else new_root
  dir.create(out, recursive = TRUE, showWarnings = FALSE)
  terms <- c("ask", if (interaction) "ask_aligned")
  fits <- results <- effects <- differences <- samples <- list()
  for (o in OUTCOMES) for (adjusted in c(FALSE, TRUE)) {
    model <- if (adjusted) "History adjusted" else "Baseline"
    rhs <- c(terms, if (adjusted) panel$controls)
    fml <- as.formula(paste0("log_", o, " ~ ", paste(rhs, collapse = " + "), " | unit_id + date"))
    f <- feols(fml, d, cluster = ~unit_id, notes = FALSE)
    key <- paste(o, model, sep = ":")
    fits[[key]] <- f
    stopifnot(identical(obs(f), expected), nobs(f) == nobs(old[[paste("likes", model, sep = ":")]]))
    b <- coef(f)[terms]; V <- vcov(f)[terms, terms, drop = FALSE]
    df <- degrees_freedom(f, "t")
    contrast <- function(w, label) {
      beta <- as.numeric(w %*% b); s <- sqrt(as.numeric(w %*% V %*% w))
      data.frame(outcome = o, model, label, estimate = beta, se = s,
        ci_low = beta - qt(.975, df)*s, ci_high = beta + qt(.975, df)*s,
        p_value = 2*pt(-abs(beta/s), df))
    }
    if (interaction) {
      effects[[paste(key, "combined")]] <- contrast(c(1,0), "Opp. + Independent")
      effects[[paste(key, "aligned")]] <- contrast(c(1,1), "Aligned")
      differences[[key]] <- contrast(c(0,1), "Aligned - (Opp. + Independent)")
      # Verify the Aligned sum and its covariance through a direct-slope model.
      dd <- d; dd$ask_combined <- dd$ask - dd$ask_aligned
      alternative <- feols(as.formula(paste0("log_", o, " ~ ",
        paste(c("ask_combined", "ask_aligned", if (adjusted) panel$controls), collapse = " + "),
        " | unit_id + date")), dd, cluster = ~unit_id, notes = FALSE)
      r <- effects[[paste(key, "aligned")]]
      stopifnot(identical(obs(alternative), expected),
        abs(coef(alternative)[["ask_aligned"]] - r$estimate) < 1e-8,
        abs(se(alternative)[["ask_aligned"]] - r$se) < 1e-8)
    } else {
      results[[key]] <- contrast(1, "Asked a question") |>
        mutate(inference = "Outlet clustered")
    }
    samples[[key]] <- data.frame(outcome = o, model, n = nobs(f),
      units = n_distinct(d$unit_id[expected]), dates = n_distinct(d$date[expected]),
      asking = sum(d$ask[expected]), within_r2 = unname(r2(f, "wr2")))
  }
  panel$estimation_rows <- expected
  panel$transformation <- DAILY_TRANSFORMATION
  panel$transformation_calibration <- cuts
  panel$outcome_definitions <- c(interactions = "likes + comments",
    mean_interactions = "raw interactions / raw videos; zero when videos=0",
    transform = paste(DAILY_TRANSFORMATION, "after pooled estimation sample upper-p99 cap; fixed pooled positive minimum for Chen-Roth x=0"))
  saveRDS(panel, file.path(out, "analysis_panel.rds"))
  saveRDS(fits, file.path(out, if (interaction) "fits.rds" else "regression_fits.rds"))
  if (interaction) {
    save_csv(bind_rows(effects), "group_effects.csv")
    save_csv(bind_rows(differences), "pairwise_differences.csv")
  } else save_csv(bind_rows(results), "regression_results.csv")
  save_csv(bind_rows(samples), "model_samples.csv")
  deps <- unique(c(paths, file.path(new_root, "winsorization_cutoffs.csv")))
  save_csv(data.frame(path = deps, md5 = unname(tools::md5sum(deps))), "input_manifest.csv")
  capture.output(sessionInfo(), file = file.path(out, "session_info.txt"))
  message("PASS: 12 ", if (interaction) "interaction" else "pooled", " fits; unchanged sample and controls.")
}
print(cuts)

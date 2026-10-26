# Preserve the earlier full-calendar FEct panel; append six upper-p99 asinh
# outcomes and the audited pre-lottery 12-month participation history.
entry <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)[1])
source(file.path(dirname(entry), "00-config.R"))
suppressPackageStartupMessages({library(arrow); library(dplyr); library(tidyr); library(fixest)})
setFixest_nthreads(1)
legacy_path <- file.path(root, "output/fect_youtube/youtube_questions_attendance_daily.parquet")
history_path <- file.path(root, "output/balance/prior_ratios/models.rds")
mapping_path <- file.path(root, "output/balance/prior_ratios/source_mapping.csv")
cw_path <- file.path(source_dir, "metadata_outcome_crosswalk.parquet")
metrics_path <- file.path(source_dir, "youtube_entity_daily_panel.parquet")
# Histories and crosswalks must still correspond to their audited source vintage.
manifest <- read.csv(file.path(out, "input_manifest.csv"))
stopifnot(identical(unname(tools::md5sum(manifest$path)), manifest$md5))
out <- file.path(out, "legacy_full_calendar_asinh_winsor99_history")
dir.create(out, recursive = TRUE, showWarnings = FALSE)
legacy <- read_parquet(legacy_path) |> arrange(youtube_entity_id, date)
stopifnot(!anyDuplicated(legacy[c("youtube_entity_id", "date")]),
  all(legacy$attendance_dummy %in% 0:1),
  all(legacy$treatment_day == as.integer(legacy$questions > 0)),
  all(legacy$attendance_dummy[legacy$treatment_day == 1] == 1),
  min(legacy$date) == as.Date("2022-04-18"), max(legacy$date) == as.Date("2024-12-31"))
legacy_from <- min(legacy$date); legacy_to <- max(legacy$date)
metrics <- open_dataset(metrics_path) |>
  filter(date >= legacy_from, date <= legacy_to) |>
  select(entity_id, date, youtube_views, youtube_n_videos,
    source_likes = youtube_likes, source_comments = youtube_comments,
    source_entity_matched, source_date_observed) |> collect() |>
  mutate(source_row = TRUE)
d <- legacy |> left_join(metrics, by = c("youtube_entity_id" = "entity_id", "date"), relationship = "one-to-one")
stopifnot(all(d$source_row %in% TRUE),
  all(coalesce(d$source_likes, 0) == coalesce(d$youtube_likes, 0)),
  all(coalesce(d$source_comments, 0) == coalesce(d$youtube_comments, 0)))
save_csv(d |> summarise(rows = n(), matched = sum(source_entity_matched %in% TRUE),
  covered = sum(source_date_observed %in% TRUE), missing_views = sum(is.na(youtube_views)),
  missing_videos = sum(is.na(youtube_n_videos)), missing_likes = sum(is.na(youtube_likes)),
  missing_comments = sum(is.na(youtube_comments))), "legacy_outcome_coverage.csv")
d <- d |> mutate(unit_id = as.character(youtube_entity_id), ask = treatment_day,
  videos = coalesce(youtube_n_videos, 0), likes = coalesce(youtube_likes, 0),
  comments = coalesce(youtube_comments, 0), views = coalesce(youtube_views, 0),
  interactions = likes + comments,
  mean_interactions = if_else(videos > 0, interactions / pmax(videos, 1), 0))
stopifnot(all(d$interactions == d$youtube_interactions),
  !any(d$videos == 0 & d$interactions > 0))

# Link unique source IDs, never expand the calendar panel by metadata row.
cw <- read_parquet(cw_path) |> select(metadata_id, outcome, entity_id) |> distinct()
aq <- cw |> filter(outcome %in% c("attendance", "questions")) |>
  pivot_wider(names_from = outcome, values_from = entity_id)
pairs <- read.csv(mapping_path) |> filter(!excluded) |> select(attendance, questions)
links <- aq |> inner_join(pairs, by = c("attendance", "questions"), relationship = "many-to-one") |>
  inner_join(cw |> filter(outcome == "youtube") |> select(metadata_id, entity_id),
    by = "metadata_id", relationship = "many-to-many") |>
  distinct(unit_id = entity_id, history_unit_id = attendance) |>
  filter(unit_id %in% d$unit_id)
ambiguous <- links |> count(unit_id) |> filter(n > 1)
stopifnot(nrow(ambiguous) == 0L)
h <- readRDS(history_path)$histories |> filter(variable == "ratio_12m") |>
  select(history_unit_id = unit_id, prior_ratio = ratio, numerator, denominator,
         common_dates, first_common, last_common)
history <- d |> distinct(unit_id, outlet_names) |>
  left_join(links, by = "unit_id", relationship = "one-to-one") |>
  left_join(h, by = "history_unit_id", relationship = "many-to-one") |>
  mutate(history_status = case_when(is.na(history_unit_id) ~ "No unambiguous source-pair link",
    !is.finite(prior_ratio) ~ "Undefined prior ratio", TRUE ~ "Observed prior ratio"))
save_csv(history, "history_mapping_audit.csv")
d <- d |> left_join(history |> select(unit_id, prior_ratio, history_status),
  by = "unit_id", relationship = "many-to-one") |>
  mutate(quarter = paste0(format(date, "%Y"), "Q", (as.integer(format(date, "%m"))-1L)%/%3L+1L),
    missing_ratio = as.integer(!is.finite(prior_ratio)),
    ratio_filled = if_else(missing_ratio == 1L, 0, prior_ratio))
controls <- character()
quarters <- sort(unique(d$quarter))
for (q in quarters[-1]) {
  v <- paste0("history_", q); m <- paste0("missing_", q)
  d[[v]] <- d$ratio_filled * as.integer(d$quarter == q)
  d[[m]] <- d$missing_ratio * as.integer(d$quarter == q)
  controls <- c(controls, v, m)
}
outcomes <- c("videos", "interactions", "mean_interactions", "likes", "comments", "views")
stopifnot(all(is.finite(as.matrix(d[outcomes]))), all(as.matrix(d[outcomes]) >= 0))
cuts <- bind_rows(lapply(outcomes, function(o) {
  upper <- unname(quantile(d[[o]], .99, type = 7))
  d[[paste0("Y_", o)]] <<- asinh(pmin(d[[o]], upper))
  data.frame(outcome = o, upper, percentile = .99, quantile_type = 7L,
    n = nrow(d), capped = sum(d[[o]] > upper), zero_days = sum(d[[o]] == 0))
}))
save_csv(cuts, "winsorization_cutoffs.csv")
support <- d |> group_by(unit_id) |> summarise(n = n(), n0 = sum(ask == 0),
  asking = sum(ask), history = first(history_status), .groups = "drop")
save_csv(support, "unit_support.csv")
stopifnot(all(support$n0 >= 5), all(support$n == 989), nrow(support) == 165,
  nrow(d) == nrow(legacy), identical(d$sample_day, legacy$sample_day),
  identical(d$attendance_dummy, legacy$attendance_dummy), identical(d$ask, legacy$treatment_day))
# With two-way FE the history levels are absorbed; identify quarterly slopes on
# untreated cells, while checking every reduced column also fits treated cells.
untreated <- filter(d, ask == 0)
all_controls <- c("attendance_dummy", controls)
Xd <- demean(as.matrix(untreated[all_controls]), f = list(untreated$unit_id, untreated$date), nthreads = 1)
rank <- qr(Xd, tol = 1e-7)
retained <- all_controls[rank$pivot[seq_len(rank$rank)]]
stopifnot("attendance_dummy" %in% retained)
for (v in setdiff(all_controls, retained)) {
  probe <- feols(as.formula(paste(v, "~", paste(retained, collapse = " + "), "| unit_id + date")),
    untreated, notes = FALSE)
  stopifnot(max(abs(predict(probe, newdata = d) - d[[v]])) < 1e-6)
}
save_csv(data.frame(control = all_controls, retained = all_controls %in% retained), "control_rank_audit.csv")
saveRDS(list(data = d, outcomes = outcomes, history_controls = setdiff(retained, "attendance_dummy"),
  cutoffs = cuts, history = history, seed = SEED, legacy_panel_path = legacy_path), file.path(out, "panel.rds"))
inputs <- unique(c(legacy_path, history_path, mapping_path, cw_path, metrics_path, manifest$path))
save_csv(data.frame(path = inputs, md5 = unname(tools::md5sum(inputs))), "input_manifest.csv")
print(history |> count(history_status)); print(cuts)
cat("PASS: exact earlier calendar, treatment, attendance and outcome snapshots; unique history links;\n",
  nrow(d), " rows, ", n_distinct(d$unit_id), " entities, ", n_distinct(d$date), " days, ", sum(d$ask), " question-days; ",
  length(retained)-1, " identified history controls.\n", sep = "")

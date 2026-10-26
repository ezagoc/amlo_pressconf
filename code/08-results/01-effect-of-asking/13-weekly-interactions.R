# Weekly check on the daily comparison's outlet roster, using ALL usable weeks.
# Treatment is observed asking; partially covered weeks are retained per user.
entry <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)[1])
source(file.path(dirname(entry), "00-config.R"))
suppressPackageStartupMessages({library(arrow); library(dplyr); library(fixest)})
setFixest_nthreads(1)
base_out <- out
manifest <- read.csv(file.path(base_out, "input_manifest.csv"))
stopifnot(identical(unname(tools::md5sum(manifest$path)), manifest$md5))
daily_path <- file.path(base_out, "pooled_interactions_combined/analysis_panel.rds")
daily <- readRDS(daily_path)
base_path <- file.path(base_out, "analysis_panel.rds")
base <- readRDS(base_path)
roster <- daily$data[daily$estimation_rows, ] |>
  distinct(unit_id, group, prior_ratio, ratio_filled, missing_ratio)
stopifnot(!anyDuplicated(roster$unit_id))
links <- base$links |> semi_join(roster, by = "unit_id") |> select(unit_id, entity_id) |> distinct()
stopifnot(!anyDuplicated(links$entity_id), setequal(links$unit_id, roster$unit_id))
mapping_path <- file.path(root, "output/balance/prior_ratios/source_mapping.csv")
pairs <- read.csv(mapping_path) |> filter(!excluded) |>
  transmute(unit_id = attendance, questions) |> semi_join(roster, by = "unit_id")
stopifnot(!anyDuplicated(pairs$unit_id), !anyDuplicated(pairs$questions), nrow(pairs) == nrow(roster))
out <- file.path(base_out, "weekly_interactions_combined")
dir.create(out, recursive = TRUE, showWarnings = FALSE)
week_start <- function(date) date - (as.integer(format(date, "%u")) - 1L)
a <- open_dataset(file.path(source_dir, "attendance_entity_daily_panel.parquet")) |>
  filter(date >= FROM, date <= TO) |>
  select(entity_id, date, source_entity_matched, source_date_observed, attendance_n_journalists_recorded) |>
  collect() |> transmute(unit_id = entity_id, date, a_matched = source_entity_matched,
                        a_observed = source_date_observed, records = attendance_n_journalists_recorded)
q <- open_dataset(file.path(source_dir, "questions_entity_daily_panel.parquet")) |>
  filter(date >= FROM, date <= TO) |>
  select(entity_id, date, source_entity_matched, source_date_observed, question_asked) |>
  collect() |> transmute(questions = entity_id, date, q_matched = source_entity_matched,
                        q_observed = source_date_observed, question_asked)
# Calendar coverage means dates observed in either conference source, not an
# independently verified census of every actual conference.
ca <- a |> distinct(date, a_observed)
cq <- q |> distinct(date, q_observed)
stopifnot(!anyDuplicated(ca$date), !anyDuplicated(cq$date))
calendar <- full_join(ca, cq, by = "date") |>
  mutate(week = week_start(date), known_conference = a_observed | q_observed)
week_calendar <- calendar |> group_by(week) |>
  summarise(window_days = n(), period_end = max(date), known_conference_days = sum(known_conference),
    attendance_covered_days = sum(a_observed), question_covered_days = sum(q_observed),
    joint_covered_days = sum(a_observed & q_observed),
    complete_conference_coverage = all(!known_conference | (a_observed & q_observed)), .groups = "drop")
save_csv(calendar, "daily_source_coverage.csv")
save_csv(week_calendar, "weekly_source_coverage.csv")
qa <- a |> inner_join(pairs, by = "unit_id", relationship = "many-to-one") |>
  inner_join(q, by = c("questions", "date"), relationship = "one-to-one") |>
  mutate(week = week_start(date), a_known = a_matched & a_observed & is.finite(records),
         q_known = q_matched & q_observed & is.finite(question_asked))
stopifnot(!anyDuplicated(qa[c("unit_id", "date")]),
          all(qa$question_asked[qa$q_known] %in% 0:1), all(qa$records[qa$a_known] >= 0))
aw <- qa |> group_by(unit_id, week) |>
  summarise(attendance_days_covered = sum(a_known), question_days_covered = sum(q_known),
    attended_days = sum(a_known & records > 0, na.rm = TRUE),
    records = if (any(a_known)) sum(records[a_known]) else NA_real_,
    ask = if (any(q_known)) as.integer(any(question_asked[q_known] == 1)) else NA_integer_,
    observed_question_days = if (any(q_known)) sum(question_asked[q_known]) else NA_integer_, .groups = "drop")

# Seven-day publication totals, NOT sums of the daily attendee regression rows.
# The last week has five in-window days (Sep 23-27) and is retained explicitly.
y <- open_dataset(file.path(source_dir, "youtube_entity_daily_panel.parquet")) |>
  filter(date >= FROM, date <= TO) |>
  select(entity_id, date, source_entity_matched, source_date_observed,
         youtube_likes, youtube_comments, youtube_views, youtube_n_videos) |>
  collect() |> inner_join(links, by = "entity_id", relationship = "many-to-one") |>
  mutate(week = week_start(date), valid = source_entity_matched & source_date_observed &
    is.finite(youtube_likes) & is.finite(youtube_comments) & is.finite(youtube_views) & is.finite(youtube_n_videos))
stopifnot(!anyDuplicated(y[c("entity_id", "date")]),
          all(as.matrix(y[y$valid, c("youtube_likes", "youtube_comments", "youtube_views", "youtube_n_videos")]) >= 0))
expected <- links |> count(unit_id, name = "channels")
yw <- y |> left_join(expected, by = "unit_id") |>
  left_join(week_calendar |> select(week, window_days), by = "week") |>
  group_by(unit_id, week) |>
  summarise(channels = first(channels), valid_channel_days = sum(valid),
    expected_channel_days = first(channels) * first(window_days),
    covered = n() == expected_channel_days & all(valid),
    likes = if (covered) sum(youtube_likes) else NA_real_,
    comments = if (covered) sum(youtube_comments) else NA_real_,
    views = if (covered) sum(youtube_views) else NA_real_,
    videos = if (covered) sum(youtube_n_videos) else NA_real_, .groups = "drop")
joined <- aw |> left_join(yw, by = c("unit_id", "week"), relationship = "one-to-one") |>
  left_join(roster, by = "unit_id", relationship = "many-to-one") |>
  left_join(week_calendar, by = "week", relationship = "many-to-one") |>
  mutate(date = week) |> arrange(unit_id, date)
eligible <- joined |> filter(records > 0, is.finite(ask), covered %in% TRUE)
d <- informative(eligible) |>
  mutate(ask_aligned = ask * (group == "Aligned"),
    quarter = paste0(format(date, "%Y"), "Q", (as.integer(format(date, "%m"))-1L) %/% 3L + 1L))
controls <- base$controls
for (v in controls) {
  quarter <- sub("^(history|missing)_", "", v)
  z <- if (startsWith(v, "history_")) d$ratio_filled else d$missing_ratio
  d[[v]] <- z * (d$quarter == quarter)
}
for (o in OUTCOMES) d[[paste0("log_",o)]] <- log1p(d[[o]])
stopifnot(nrow(d) > 0, all(d$records > 0), all(d$covered), !anyDuplicated(d[c("unit_id","date")]),
          setequal(unique(d$unit_id), roster$unit_id))
save_csv(joined |> mutate(in_regression_input = paste(unit_id,week) %in% paste(d$unit_id,d$week)), "weekly_coverage_audit.csv")
save_csv(roster, "outlet_roster.csv")

fits <- effects <- differences <- samples <- joint <- list()
weights <- rbind("Opp. + Independent" = c(1,0), Aligned = c(1,1),
                 "Aligned - (Opp. + Independent)" = c(0,1))
first_obs <- NULL
for (o in OUTCOMES) for (adjusted in c(FALSE,TRUE)) {
  model <- if (adjusted) "History adjusted" else "Baseline"
  rhs <- c("ask","ask_aligned", if (adjusted) controls)
  f <- feols(as.formula(paste0("log_",o," ~ ",paste(rhs,collapse=" + ")," | unit_id + date")),
             d, cluster = ~unit_id, notes = FALSE)
  key <- paste(o,model,sep=":"); fits[[key]] <- f
  if (is.null(first_obs)) first_obs <- obs(f)
  stopifnot(identical(first_obs,obs(f)))
  used <- d[obs(f), ]; b <- coef(f)[c("ask","ask_aligned")]
  V <- vcov(f)[names(b),names(b),drop=FALSE]; df <- degrees_freedom(f,"t")
  for (label in rownames(weights)) {
    w <- weights[label,]; estimate <- as.numeric(w %*% b)
    se <- sqrt(as.numeric(w %*% V %*% w))
    r <- data.frame(outcome=o,model,label,estimate,se,ci_low=estimate-qt(.975,df)*se,
                    ci_high=estimate+qt(.975,df)*se,p_value=2*pt(-abs(estimate/se),df),df)
    if (label == "Aligned - (Opp. + Independent)") differences[[key]] <- r
    else effects[[paste(key,label)]] <- r
  }
  w <- wald(f,keep="^ask_aligned$",print=FALSE)
  stopifnot(abs(w$stat-(b[2]^2/V[2,2]))<1e-9)
  joint[[key]] <- data.frame(outcome=o,model,F=w$stat,df_num=w$df1,df_den=w$df2,p_value=w$p)
  samples[[key]] <- data.frame(outcome=o,model,n=nobs(f),units=n_distinct(used$unit_id),
    weeks=n_distinct(used$date),asking=sum(used$ask),from=min(used$date),to=max(used$period_end),
    df,dropped_controls=paste(f$collin.var,collapse=" | "))
  # Verify the group-sum coefficient and SE by switching the reference group.
  dd <- d |> mutate(ask_combined = ask * (group == "Opp. + Independent"))
  other <- feols(as.formula(paste0("log_",o," ~ ask + ask_combined",
    if (adjusted) paste0(" + ",paste(controls,collapse=" + ")) else "", " | unit_id + date")),
    dd,cluster=~unit_id,notes=FALSE)
  target <- effects[[paste(key,"Aligned")]]
  stopifnot(abs(coef(other)[["ask"]]-target$estimate)<1e-8,
            abs(se(other)[["ask"]]-target$se)<1e-8)
}
used <- d[first_obs, ]
stopifnot(all(used$attended_days >= 1), all(used$attended_days <= used$attendance_days_covered),
          all(used$question_days_covered >= 1), all(used$ask == (used$observed_question_days > 0)))
save_csv(used |> distinct(week,period_end,window_days,known_conference_days,
  attendance_covered_days,question_covered_days,joint_covered_days,complete_conference_coverage),
  "estimation_week_coverage.csv")
saveRDS(list(data=d,estimation_rows=first_obs,controls=controls,frequency="weekly",
             source_coverage="all usable weeks; partial conference coverage retained"), file.path(out,"analysis_panel.rds"))
saveRDS(fits,file.path(out,"fits.rds"))
save_csv(bind_rows(effects),"group_effects.csv")
save_csv(bind_rows(differences),"pairwise_differences.csv")
save_csv(bind_rows(joint),"joint_tests.csv")
save_csv(bind_rows(samples),"model_samples.csv")
save_csv(used |> group_by(group) |> summarise(n=n(),units=n_distinct(unit_id),weeks=n_distinct(date),
  asking=sum(ask),asking_units=n_distinct(unit_id[ask==1]),.groups="drop"),"group_sample_sizes.csv")
save_csv(bind_rows(flow_row(joined,"All roster outlet-weeks"),
  flow_row(joined |> filter(records>0),"Recorded attendance in week"),
  flow_row(eligible,"Some question coverage and complete in-window YouTube coverage"),
  flow_row(d,"Pooled asking/nonasking variation"),flow_row(used,"After FE singleton removal")),"sample_flow.csv")
save_csv(anti_join(d,used,by=c("unit_id","date")),"singleton_exclusions.csv")
paths <- unique(c(daily_path,base_path,mapping_path,manifest$path))
save_csv(data.frame(path=paths,md5=unname(tools::md5sum(paths))),"input_manifest.csv")
capture.output(sessionInfo(),file=file.path(out,"session_info.txt"))
print(bind_rows(effects) |> filter(model=="History adjusted"))
print(bind_rows(differences) |> filter(model=="History adjusted"))
print(bind_rows(samples))
print(read.csv(file.path(out,"sample_flow.csv")))
cat("PASS: raw weekly totals before log; unique source units; coverage audited; common sample; contrasts validated.\n")

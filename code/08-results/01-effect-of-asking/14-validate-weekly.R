# Independent read-only aggregation and saved-bootstrap checks.
entry <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)[1])
source(file.path(dirname(entry), "00-config.R"))
suppressPackageStartupMessages({library(arrow);library(dplyr)})
base <- readRDS(file.path(out,"analysis_panel.rds"))
out <- file.path(out,"weekly_interactions_combined")
panel <- readRDS(file.path(out,"analysis_panel.rds"))
d <- panel$data[panel$estimation_rows,]
mf <- read.csv(file.path(out,"input_manifest.csv"))
stopifnot(identical(unname(tools::md5sum(mf$path)),mf$md5),
          !anyDuplicated(d[c("unit_id","date")]),all(d$records>0),
          all(d$ask == (d$observed_question_days>0)),all(d$question_days_covered>0))
links <- base$links |> filter(unit_id %in% d$unit_id) |> select(unit_id,entity_id) |> distinct()
y <- open_dataset(file.path(source_dir,"youtube_entity_daily_panel.parquet")) |>
  filter(date>=FROM,date<=TO) |>
  select(entity_id,date,youtube_likes,youtube_comments,youtube_views,source_entity_matched,source_date_observed) |>
  collect() |> inner_join(links,by="entity_id",relationship="many-to-one")
y$week <- y$date-(as.integer(format(y$date,"%u"))-1L)
yy <- y |> semi_join(d |> select(unit_id,week),by=c("unit_id","week"))
stopifnot(all(yy$source_entity_matched),all(yy$source_date_observed))
manual <- aggregate(yy[c("youtube_likes","youtube_comments","youtube_views")],
                    by=yy[c("unit_id","week")],FUN=sum)
check <- inner_join(d,manual,by=c("unit_id","week"),relationship="one-to-one")
stopifnot(nrow(check)==nrow(d))
for (o in OUTCOMES) stopifnot(all(check[[o]]==check[[paste0("youtube_",o)]]),
                              all(check[[paste0("log_",o)]]==log1p(check[[o]])))
window_dates <- split(seq(FROM,TO,by="day"),
                      seq(FROM,TO,by="day")-(as.integer(format(seq(FROM,TO,by="day"),"%u"))-1L))
counts <- yy |> count(unit_id,week,name="actual_channel_days") |>
  inner_join(d |> select(unit_id,week,channels,window_days),by=c("unit_id","week"))
stopifnot(all(counts$actual_channel_days==counts$channels*counts$window_days))
qa <- open_dataset(file.path(source_dir,"attendance_entity_daily_panel.parquet")) |>
  filter(date>=FROM,date<=TO) |>
  select(entity_id,date,source_entity_matched,source_date_observed,attendance_n_journalists_recorded) |>
  collect() |> filter(source_entity_matched,source_date_observed) |>
  transmute(unit_id=entity_id,week=date-(as.integer(format(date,"%u"))-1L),
    records=attendance_n_journalists_recorded,attended=as.integer(attendance_n_journalists_recorded>0))
ma <- aggregate(qa[c("records","attended")],by=qa[c("unit_id","week")],FUN=sum)
chk <- d |> inner_join(ma,by=c("unit_id","week"),suffix=c("","_manual"))
stopifnot(nrow(chk)==nrow(d),all(chk$records==chk$records_manual),all(chk$attended_days==chk$attended))
fd <- file.path(out,"wild_cluster_9999")
bm <- read.csv(file.path(fd,"input_manifest.csv"))
stopifnot(identical(unname(tools::md5sum(bm$path)),bm$md5))
results <- read.csv(file.path(fd,"results.csv"))
stopifnot(nrow(results)==18,all(results$valid_draws==9999),all(results$n==nrow(d)))
for(o in OUTCOMES) for(m in c("baseline","adjusted")) for(h in c("combined","aligned","difference")) {
  z <- readRDS(file.path(fd,paste0(o,"_",m,"_",h,".rds")))
  b <- z$test
  stopifnot(b$impose_null,b$r==0,b$N==nrow(d),b$N_G==n_distinct(d$unit_id),
    length(b$t_boot)==9999,all(is.finite(b$t_boot)),
    abs(mean(abs(b$t_boot)>=abs(b$t_stat))-b$p_val)<1e-10)
}
cat("PASS: independent raw calendar-week outcome/attendance sums, full in-window channel coverage,\n",
    "log after sum, fixed input fingerprints, and all 18 saved weekly bootstrap tests.\n",sep="")

# Identity inputs only: never build panels or reports in this review step.
suppressPackageStartupMessages({library(arrow);library(dplyr);library(readr)})
root <- normalizePath(getwd())
stage <- file.path(root,"outputs/frecuencia-cad-20261026/staged")
source("project_paths.R")
live <- media_root()
run <- function(script,transform=identity) {
  setwd(root); env <- new.env(); code <- readLines(script,warn=FALSE)
  code <- code[!grepl("^rm\\(list",code)]
  invisible(capture.output(eval(parse(text=transform(code)),envir=env)))
  setwd(root);env
}
q <- run("code/03-cleaning_conf/question_class/sheinbaum/05_deduplicate_outlets_periodistas.R",
         function(x)sub("^WRITE_OUTPUT <-.*","WRITE_OUTPUT <- FALSE",x))
write_parquet(q$df,file.path(stage,"journalist_media_mapped_records.parquet"))
write_parquet(q$df_dedup,file.path(stage,"periodistas_v2_all_years_dedup.parquet"))
write_csv(q$df_dedup,file.path(stage,"journalists_and_media_dedup.csv"))
write_csv(q$alias_audit,file.path(stage,"manual_alias_audit.csv"))
write_csv(q$before_after,file.path(stage,"manual_dedup_counts.csv"))
write_csv(q$df,"/tmp/sheinbaum-current-mapped.csv")
# Stop before Generate panels; retain physical attendance rows unchanged.
a <- run("code/05-press_conferences/00-preprocessing_attendance.R",function(x){
  x <- x[seq_len(grep("^#### Generate panels",x)-1L)]
  x <- gsub("media_output_path(","staged_output_path(",x,fixed=TRUE)
  x[grepl("writexl::write_xlsx",x,fixed=TRUE)] <- paste0('jsonlite::write_json(final_dedup,"',file.path(stage,"bridge.json"),'",dataframe="rows")')
  c(paste0('staged_output_path <- function(...) file.path("',stage,'",tail(c(...),1))'),x)
})
amlo <- run("code/03-cleaning_conf/question_class/05_deduplicate_outlets_periodistas.R.R",function(x){
  x <- x[seq_len(grep("^write_parquet",x))]
  x <- sub("write_parquet(df, paste0(pfo, 'questions_dataset_dedup.parquet'))",
      paste0('write_parquet(df,"',file.path(stage,"questions_dataset_dedup.parquet"),'")'),x,fixed=TRUE)
  # Its descriptive directory is unused in this identity-only step.
  x[grepl("^res_dir <-",x)] <- paste0('res_dir <- "',stage,'"')
  x
})
oldq <- read_parquet(file.path(live,"data/02-conferences-sheinbaum/api_extraction/official-through-2026-10-15/auxiliar/journalist_media_mapped_records.parquet"))
olda <- read_parquet(file.path(live,"data/02-conferences/raw/attendance/merged/attendance_clean.parquet"))
expected <- oldq$outlet_aux;expected[expected %in% c("frecuencia cad","es ahora am")] <- "jaime farias informa"
expected_reporter <- oldq$reporter_aux
expected_reporter[which(expected_reporter=="alberto marroquin espinosa")] <- "alberto marroquin espinoza"
stopifnot(identical(q$df$record_id,oldq$record_id),identical(q$df$evidence_text,oldq$evidence_text),
          identical(q$df$reporter_aux,expected_reporter),identical(q$df$outlet_aux,expected),
          !anyDuplicated(q$df_dedup[c("date","reporter_aux","outlet_aux")]),
          nrow(a$df)==nrow(olda),identical(a$df$medios,olda$medios),identical(a$df$fecha,olda$fecha))
group <- q$df_dedup |> filter(outlet_aux=="jaime farias informa")
stopifnot(nrow(group)==21L,n_distinct(group$date)==21L,
          sum(grepl("frecuencia cad",group$outlet_brands))==9L,
          sum(q$df$outlet_aux=="10 am mx",na.rm=TRUE)==sum(oldq$outlet_aux=="10 am mx",na.rm=TRUE))
dates <- group |> filter(date<=as.Date("2025-09-30")) |> distinct(date)
att <- a$df |> filter(outlet_final=="jaime farias informa",!attendance_assumed) |>
  transmute(date=as.Date(fecha)) |> distinct()
missing <- anti_join(dates,att,by="date")
write_csv(missing,file.path(stage,"frecuencia_cad_unmatched_attendance_dates.csv"))
frecuencia <- group |> filter(grepl("frecuencia cad",outlet_brands)) |> distinct(date)
frecuencia_missing <- anti_join(frecuencia,att,by="date")
stopifnot(nrow(frecuencia_missing)==1L,frecuencia_missing$date==as.Date("2024-11-06"))
checks <- list(conference_dates=n_distinct(group$date),identification_rows=nrow(group),
  joint_brand_identifications_collapsed=nrow(filter(oldq,outlet_aux %in% c("jaime farias informa","es ahora am","frecuencia cad")))-nrow(group),
  attendance_window_dates=nrow(dates),matched_dates=nrow(dates)-nrow(missing),
  unmatched_dates=as.character(missing$date),frecuencia_dates=9,frecuencia_matched_dates=8,
  reporter_spelling_rows_corrected=sum(oldq$reporter_aux=="alberto marroquin espinosa",na.rm=TRUE),
  physical_attendance_rows_preserved=TRUE,panels_built=FALSE)
jsonlite::write_json(checks,file.path(stage,"checks.json"),pretty=TRUE,auto_unbox=TRUE)
print(checks)
cat("Frecuencia CAD identity checks passed. No panels rebuilt.\n")

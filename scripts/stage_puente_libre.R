# Identity inputs only: never build panels or reports in this review step.
suppressPackageStartupMessages({library(arrow);library(dplyr);library(readr)})
root <- normalizePath(getwd())
stage <- file.path(root,"outputs/puente-libre-20261026/staged")
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
expected <- oldq$outlet_aux;expected[expected %in% "puente libre mx"] <- "tiempo la noticia digital"
stopifnot(identical(q$df$record_id,oldq$record_id),identical(q$df$evidence_text,oldq$evidence_text),
          identical(q$df$reporter_aux,oldq$reporter_aux),identical(q$df$outlet_aux,expected),
          !anyDuplicated(q$df_dedup[c("date","reporter_aux","outlet_aux")]),
          nrow(a$df)==nrow(olda),identical(a$df$medios,olda$medios),identical(a$df$fecha,olda$fecha))
group <- q$df_dedup |> filter(outlet_aux=="tiempo la noticia digital")
stopifnot(nrow(group)==25L,sum(grepl("puente libre mx",group$outlet_brands))==24L)
dates <- group |> filter(date<=as.Date("2025-09-30")) |> distinct(date)
att <- a$df |> filter(outlet_final=="tiempo la noticia digital",!attendance_assumed) |>
  transmute(date=as.Date(fecha)) |> distinct()
stopifnot(nrow(dates)==15L,nrow(anti_join(dates,att,by="date"))==0L)
jsonlite::write_json(list(question_dates=25,overlapping_brand_records_removed=24,in_period_dates=15,
  all_matched=TRUE,physical_attendance_rows_preserved=TRUE,panels_built=FALSE),
  file.path(stage,"checks.json"),pretty=TRUE,auto_unbox=TRUE)
cat("Identity checks passed; no panel builds performed.\n")

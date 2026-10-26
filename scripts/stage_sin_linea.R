# Rebuild complete current inputs and downstream panels in staging.
root <- normalizePath(getwd())
stage <- file.path(root, "outputs/sin-linea-20261026/staged")
suppressPackageStartupMessages({library(arrow);library(dplyr);library(readr)})
source("project_paths.R")
live <- media_root()
run <- function(script, transform=identity, overrides=FALSE) {
  setwd(root)
  env <- new.env()
  code <- readLines(script, warn=FALSE)
  code <- code[!grepl("^rm\\(list",code)]
  if(overrides) {
    # Only redirect outputs and use staged dependencies when they exist.
    env$stage_paths <- function() {
      env$media_path <- function(...) {
        relative <- do.call(file.path,as.list(c(...)))
        flat <- file.path(stage,basename(relative))
        nested <- file.path(stage,relative)
        if (file.exists(flat) && !dir.exists(flat)) return(flat)
        if (startsWith(relative,"data/06-outcomes/final_panel") ||
            startsWith(relative,"data/06-outcomes/deduplicated_source_panels") ||
            startsWith(relative,"results/")) return(nested)
        file.path(live, relative)
      }
      env$media_output_path <- function(...) {
        path <- file.path(stage,do.call(file.path,as.list(c(...))))
        dir.create(dirname(path),recursive=TRUE,showWarnings=FALSE); path
      }
    }
    i <- grep('source\\(.*project_paths.R',code)
    stopifnot(length(i)==1L)
    code[i] <- paste(code[i],"stage_paths()",sep="\n")
  }
  code <- transform(code)
  cat("Running",script,"\n")
  invisible(capture.output(eval(parse(text=code),envir=env)))
  setwd(root)
  env
}
q <- run("code/03-cleaning_conf/question_class/sheinbaum/05_deduplicate_outlets_periodistas.R",
         function(x) sub("^WRITE_OUTPUT <-.*","WRITE_OUTPUT <- FALSE",x))
write_parquet(q$df,file.path(stage,"journalist_media_mapped_records.parquet"))
write_parquet(q$df_dedup,file.path(stage,"periodistas_v2_all_years_dedup.parquet"))
write_csv(q$df_dedup,file.path(stage,"journalists_and_media_dedup.csv"))
write_csv(q$alias_audit,file.path(stage,"manual_alias_audit.csv"))
write_csv(q$before_after,file.path(stage,"manual_dedup_counts.csv"))
write_csv(q$df,"/tmp/sheinbaum-current-mapped.csv")
stopifnot(!any(q$df$outlet_aux %in% "el politico en las redes"),
          !anyDuplicated(q$df_dedup[c("date","reporter_aux","outlet_aux")]))

a <- run("code/05-press_conferences/00-preprocessing_attendance.R",function(x) {
  x <- gsub("media_output_path(","staged_output_path(",x,fixed=TRUE)
  x[grepl("writexl::write_xlsx",x,fixed=TRUE)] <- paste0(
    'jsonlite::write_json(final_dedup,"',file.path(stage,"bridge.json"),'",dataframe="rows")')
  c(paste0('staged_output_path <- function(...) file.path("',stage,'",tail(c(...),1))'),x)
})
stopifnot(!anyDuplicated(a$panel[c("outlet_final","fecha")]))
raw <- readxl::read_excel(file.path(live,"data/02-conferences/raw/attendance/merged/attendance_merged_dedup.xlsx"))
raw$eligible_role <- keep_attendance_role(raw$cargo)
write_csv(raw,"/tmp/attendance-original.csv")

file.copy(file.path(live,"data/00-newspaper_data/processed/nominatim_office_geocodes_v3.csv"),
          file.path(stage,"nominatim_office_geocodes_v3.csv"),overwrite=TRUE)
m <- run("code/02-cleaning_comsoc/03-base_panel_creation_metadata.R",function(x){
  x <- sub('output_path <- file.path(data_path, "processed")',paste0('output_path <- "',stage,'"'),x,fixed=TRUE)
  for(f in c("mexican_newspapers.xlsx","newspaper_metadata.xlsx"))
    x <- gsub(paste0('file.path(data_path, "',f,'")'),paste0('"',file.path(stage,f),'"'),x,fixed=TRUE)
  x
})
stopifnot(sum(m$metadata$names.conference %in% "sin linea")==1L,
          !any(m$metadata$name.page %in% "El Politico en las Redes"))

amlo <- run("code/03-cleaning_conf/question_class/05_deduplicate_outlets_periodistas.R.R",function(x){
  sub("write_parquet(df, paste0(pfo, 'questions_dataset_dedup.parquet'))",
      paste0('write_parquet(df,"',file.path(stage,"questions_dataset_dedup.parquet"),'")'),x,fixed=TRUE)
},overrides=TRUE)
if ("--build-panels" %in% commandArgs(TRUE)) {
  run("code/07-final_panel/00-build_final_daily_panel.R",overrides=TRUE)
  gc()
  run("code/07-final_panel/05-build_deduplicated_outcome_panels.R",overrides=TRUE)
}

old <- read_parquet(file.path(live,"data/02-conferences-sheinbaum/api_extraction/official-through-2026-10-15/auxiliar/periodistas_v2_all_years_dedup.parquet"))
before <- old |> filter(outlet_aux %in% c("sin linea","el politico en las redes")) |>
  group_by(outlet_aux) |> summarise(records=n(),dates=n_distinct(date),.groups="drop")
after <- q$df_dedup |> filter(outlet_aux=="sin linea") |>
  summarise(records=n(),dates=n_distinct(date),in_attendance_window=n_distinct(date[date<=as.Date("2025-09-30")]))
att <- a$df |> filter(outlet_final=="sin linea") |>
  summarise(records=n(),dates=n_distinct(fecha),sheinbaum_dates=n_distinct(fecha[fecha>=as.Date("2024-10-01")]))
jsonlite::write_json(list(before=before,after=after,attendance=att,metadata_rows=nrow(m$metadata)),
  file.path(stage,"merge_checks.json"),pretty=TRUE,dataframe="rows",auto_unbox=TRUE)
cat("Complete staged rebuild passed.\n")

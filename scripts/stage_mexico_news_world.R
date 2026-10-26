# Rebuild immediate analysis inputs in a staging directory before publication.
root <- normalizePath(getwd())
stage <- file.path(root, "outputs/mexico-news-world-20261024/staged")
dir.create(stage, recursive=TRUE, showWarnings=FALSE)
suppressPackageStartupMessages({library(arrow);library(dplyr);library(readr)})

qenv <- new.env()
qcode <- readLines("code/03-cleaning_conf/question_class/sheinbaum/05_deduplicate_outlets_periodistas.R")
qcode <- sub("^WRITE_OUTPUT <-.*", "WRITE_OUTPUT <- FALSE", qcode)
invisible(capture.output(eval(parse(text=qcode), envir=qenv)))
write_parquet(qenv$df, file.path(stage,"journalist_media_mapped_records.parquet"))
write_parquet(qenv$df_dedup, file.path(stage,"periodistas_v2_all_years_dedup.parquet"))
write_csv(qenv$df_dedup, file.path(stage,"journalists_and_media_dedup.csv"))
write_csv(qenv$alias_audit, file.path(stage,"manual_alias_audit.csv"))
write_csv(qenv$before_after, file.path(stage,"manual_dedup_counts.csv"))
write_csv(qenv$df, "/tmp/sheinbaum-current-mapped.csv")
stopifnot(!any(qenv$df_dedup$outlet_aux %in% c("hidalgo news","marco olvera oficial")),
          !anyDuplicated(qenv$df_dedup[c("date","reporter_aux","outlet_aux")]))
print(qenv$name_table_after |> filter(outlet_aux == "mexico news world"))

setwd(root)
aenv <- new.env()
aenv$staged_output_path <- function(...) file.path(stage,tail(c(...),1))
acode <- readLines("code/05-press_conferences/00-preprocessing_attendance.R")
acode <- gsub("media_output_path(", "staged_output_path(", acode, fixed=TRUE)
acode[grepl("writexl::write_xlsx",acode,fixed=TRUE)] <- paste0(
  'jsonlite::write_json(final_dedup, "',file.path(stage,"bridge.json"), '", dataframe="rows")')
invisible(capture.output(eval(parse(text=acode),envir=aenv)))
stopifnot(!any(aenv$panel$outlet_final %in% "hidalgo news"),
          !anyDuplicated(aenv$panel[c("outlet_final","fecha")]))
print(aenv$df |> filter(outlet_final=="mexico news world") |>
        summarise(records=n(),dates=n_distinct(fecha),sheinbaum_dates=n_distinct(fecha[fecha>=as.Date("2024-10-01")])) )
# The working cleaner contains unrelated pending edits. Publish only this
# approved identity migration; keep every other existing attendance row intact.
targets <- c("mexico news world", "hidalgo news", "marco olvera oficial")
old_clean <- read_parquet(media_path("data/02-conferences/raw/attendance/merged/attendance_clean.parquet"))
clean <- bind_rows(old_clean |> filter(!outlet_final %in% targets),
                   aenv$df |> filter(outlet_final=="mexico news world"))
stopifnot(nrow(clean)==nrow(old_clean))
write_parquet(clean,file.path(stage,"attendance_clean.parquet"))
old_panel <- read_parquet(media_path("data/02-conferences/raw/attendance/panel_attendance.parquet.gzip"))
panel <- bind_rows(old_panel |> filter(!outlet_final %in% targets),
                  aenv$panel |> filter(outlet_final=="mexico news world")) |>
  arrange(outlet_final,fecha)
stopifnot(!anyDuplicated(panel[c("outlet_final","fecha")]))
write_parquet(panel,file.path(stage,"panel_attendance.parquet.gzip"),compression="gzip")
old_bridge <- readxl::read_excel(media_path("data/02-conferences/raw/attendance/merged/bridge_outlets.xlsx"))
bridge <- bind_rows(old_bridge |> filter(!outlet_final %in% targets),
                   aenv$final_dedup |> filter(outlet_final=="mexico news world")) |>
  arrange(desc(total_attendance))
jsonlite::write_json(bridge,file.path(stage,"bridge.json"),dataframe="rows")
raw_attendance <- readxl::read_excel(file.path(media_root(),"data/02-conferences/raw/attendance/merged/attendance_merged_dedup.xlsx"))
raw_attendance$eligible_role <- keep_attendance_role(raw_attendance$cargo)
write_csv(raw_attendance,"/tmp/attendance-original.csv")

setwd(root)
menv <- new.env()
mcode <- readLines("code/02-cleaning_comsoc/03-base_panel_creation_metadata.R")
mcode <- mcode[!grepl("^rm\\(list",mcode)]
mcode <- sub('output_path <- file.path(data_path, "processed")',
             paste0('output_path <- "',stage,'"'),mcode,fixed=TRUE)
for(f in c("newspaper_metadata.xlsx","mexican_newspapers.xlsx"))
  mcode <- gsub(paste0('file.path(data_path, "',f,'")'),paste0('"',file.path(stage,f),'"'),mcode,fixed=TRUE)
cache <- file.path(media_root(),"data/00-newspaper_data/processed/nominatim_office_geocodes_v3.csv")
file.copy(cache,file.path(stage,basename(cache)),overwrite=TRUE)
invisible(capture.output(eval(parse(text=mcode),envir=menv)))
stopifnot(sum(menv$metadata$names.conference %in% "mexico news world")==1L,
          !any(menv$metadata$name.page %in% "Hidalgo News"))
print(menv$metadata |> filter(names.conference=="mexico news world") |>
        select(metadata_id,name.page,names.conference,names.transcripts))
# Preserve existing geocodes, types and unrelated metadata edits in live outputs.
existing <- read_parquet(media_path("data/00-newspaper_data/processed/newspaper_metadata_geocoded.parquet"))
canonical_id <- existing$metadata_id[normalize_outlet_name(existing$name.page) %in% "mexico news world"]
alias_ids <- existing$metadata_id[normalize_outlet_name(existing$name.page) %in% "hidalgo news"]
stopifnot(length(canonical_id)==1L)
metadata <- existing |> filter(!metadata_id %in% alias_ids)
updated <- menv$metadata |> filter(metadata_id==canonical_id)
fields <- c("name.page","names.conference","names.transcripts","name.page2",
            "owner_group","verification.reason","outlet_aliases","analysis_merged_into")
for (field in fields) {
  if (!field %in% names(metadata)) metadata[[field]] <- NA_character_
  metadata[[field]][metadata$metadata_id==canonical_id] <- updated[[field]]
}
write_parquet(metadata,file.path(stage,"newspaper_metadata_geocoded.parquet"))
for (frequency in c("weekly","daily")) {
  balanced <- metadata_to_balanced_panel(metadata,frequency=frequency,
                  from="2021-01-01",to="2022-12-31")
  write_parquet(balanced,file.path(stage,paste0("newspaper_metadata_panel_",frequency,"_2021_2022.parquet")))
}
setwd(root)

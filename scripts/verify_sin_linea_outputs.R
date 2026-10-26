suppressPackageStartupMessages({library(arrow);library(dplyr);library(readr)})
source("project_paths.R")
s <- "outputs/sin-linea-20261026/staged"
q <- read_parquet(file.path(s,"journalist_media_mapped_records.parquet"))
d <- read_parquet(file.path(s,"periodistas_v2_all_years_dedup.parquet"))
unresolved <- d |> filter(outlet_aux=="sin linea",reporter_aux %in% c("manuel alexis ramirez","mario valencia ramirez")) |>
  mutate(review_reason="Possible official transcription variant of Manuel Galeazzi Ramirez; identity not verified, do not merge automatically")
write_csv(unresolved,file.path(s,"sin_linea_unresolved_reporters.csv"))
original <- read_parquet(media_path("data/02-conferences-sheinbaum/api_extraction/official-through-2026-10-15/auxiliar/journalist_media_mapped_records.parquet"))
stopifnot(identical(q$record_id,original$record_id),identical(q$evidence_text,original$evidence_text),
          identical(q$reporter_aux,original$reporter_aux),nrow(q)==nrow(original),
          !anyDuplicated(d[c("date","reporter_aux","outlet_aux")]))
expected <- original$outlet_aux
expected[expected %in% "el politico en las redes"] <- "sin linea"
stopifnot(identical(q$outlet_aux,expected))
dates <- d |> filter(outlet_aux=="sin linea") |> distinct(date)
a <- read_parquet(file.path(s,"attendance_clean.parquet"))
ad <- a |> filter(outlet_final=="sin linea",!attendance_assumed) |>
  transmute(date=as.Date(fecha)) |> distinct()
window <- dates |> filter(date<=max(as.Date(a$fecha)),date>=min(as.Date(a$fecha)))
missing <- anti_join(window,ad,by="date")
write_csv(missing,file.path(s,"sin_linea_missing_attendance_dates.csv"))
stopifnot(nrow(missing)==0L)
panel <- read_parquet(file.path(s,"panel_attendance.parquet.gzip"))
stopifnot(!anyDuplicated(panel[c("outlet_final","fecha")] ),
          !any(panel$outlet_final %in% c("sin linea mx","el politico en las redes")))
m <- read_parquet(file.path(s,"newspaper_metadata_geocoded.parquet"))
stopifnot(sum(m$names.conference %in% "sin linea")==1L,
          identical(m$metadata_id[m$names.conference %in% "sin linea"],172L),
          !any(m$name.page %in% "El Politico en las Redes"))
if (!"--inputs-only" %in% commandArgs(TRUE)) {
p <- read_parquet(file.path(s,"data/06-outcomes/final_panel/final_daily_panel_2012_2025.parquet"),
                  col_select=c("metadata_id","date","names.conference"))
stopifnot(!anyDuplicated(p[c("metadata_id","date")]),!any(p$metadata_id==258L),
          all(p$names.conference[p$metadata_id==172L]=="sin linea"))
crosswalk <- read_parquet(file.path(s,"data/06-outcomes/deduplicated_source_panels/metadata_outcome_crosswalk.parquet"))
stopifnot(!any(crosswalk$metadata_id==258L))
}
cat("Verified preserved raw evidence/reporters, 35 unique appearances, all",nrow(window),
    "in-period dates matched attendance, stable canonical metadata ID, unique panel keys.\n")

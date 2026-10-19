# Run from repository root; no pipeline writes.
source("src/attendance_roles.R")
excluded <- c("FOTÓGRAFO", "FOTOGRAFO", "fotógrafo", "Fotógrafa", "FOTÓGRAFOS",
  "FOTO\u0301GRAFO", "CAMARÓGRAFO", "camarografo", "Camarógrafa", "CAMARÓGRAFOS",
  "TÉCNICO", "tecnico", "TÉCNICA", "ESTUDIANTE", "estudiante", "INGENIERO KU",
  "AUDIO", "audio", "REPORTERO / FOTÓGRAFO", NA_character_)
retained <- c("REPORTERO", "REPORTETO", "reportera", "YOUTUBER", "PERIODISTA",
  "CORRESPONSAL", "DIRECTOR", "  Reportero  ")
stopifnot(!any(keep_attendance_role(excluded)), all(keep_attendance_role(retained)))

# Exercise the production filtering expression, not a separate test-only copy.
suppressPackageStartupMessages(library(dplyr))
expressions <- parse("code/05-press_conferences/00-preprocessing_attendance.R")
match <- vapply(expressions, function(e)
  grepl("filter(keep_attendance_role(cargo))", paste(deparse(e), collapse = " "), fixed = TRUE),
  logical(1))
stopifnot(sum(match) == 1L)
df <- tibble(cargo = c(excluded, retained), source_row = seq_along(c(excluded, retained)))
eval(expressions[[which(match)]])
stopifnot(identical(df$cargo, retained))
cat("Attendance role filter tests passed.\n")

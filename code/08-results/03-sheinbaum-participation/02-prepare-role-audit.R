# Apply the production outlet cleaner to ALL original roles, read-only.
# No changes to production eligibility, attendance, or identity datasets.
root <- normalizePath(getwd())
source(file.path(root, "project_paths.R"))
script <- file.path(root, "code/05-press_conferences/00-preprocessing_attendance.R")
expressions <- parse(script)
audit_env <- new.env(parent = globalenv())
skip_roles <- 0L
skip_government <- 0L
stopped <- FALSE
for (expr in expressions) {
  text <- paste(deparse(expr), collapse = " ")
  if (grepl("add_mexico_news_coattendance(df)", text, fixed = TRUE)) {
    stopped <- TRUE
    break
  }
  if (grepl("filter(keep_attendance_role(cargo))", text, fixed = TRUE)) {
    skip_roles <- skip_roles + 1L
    next
  }
  if (grepl("!outlet_clean %in% gov_entities", text, fixed = TRUE)) {
    skip_government <- skip_government + 1L
    next
  }
  stopifnot(!grepl("write_|write\\.", text))
  eval(expr, envir = audit_env)
}
setwd(root)
stopifnot(stopped, skip_roles == 1L, skip_government == 1L)
raw <- readxl::read_excel(media_path(
  "data/02-conferences/raw/attendance/merged/attendance_merged_dedup.xlsx"))
df <- audit_env$df
stopifnot(nrow(raw) == nrow(df), identical(raw$cargo, df$cargo),
          identical(raw$medios, df$medios), identical(raw$fecha, df$fecha))
df$raw_row_id <- seq_len(nrow(df))
df$role_kept <- keep_attendance_role(df$cargo)
df$role_normalized <- stringi::stri_trans_general(as.character(df$cargo), "Latin-ASCII") |>
  stringr::str_to_upper() |> stringr::str_squish()
df$date <- as.Date(df$fecha, tz = "UTC")
df <- df[df$date >= as.Date("2024-10-01"), ]
out <- file.path(root, "outputs/sheinbaum-cargo-audit-20261026")
dir.create(out, recursive = TRUE, showWarnings = FALSE)
arrow::write_parquet(df, file.path(out, "raw_attendance_all_roles.parquet"))
print(table(df$cargo, df$role_kept, useNA = "ifany"))
cat("Original role rows preserved; no production files modified.\n")

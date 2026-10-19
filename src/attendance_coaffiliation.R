# User-specified co-affiliation assumption, not evidence of an additional person.
# Preserve observed rows and add at most one target-outlet record per date.
add_mexico_news_coattendance <- function(attendance) {
  stopifnot(all(c("fecha", "outlet_final") %in% names(attendance)))
  if (!"attendance_assumed" %in% names(attendance)) {
    attendance$attendance_assumed <- FALSE
    attendance$attendance_basis <- "recorded"
    attendance$attendance_source_outlet <- NA_character_
  }
  target_dates <- as.Date(attendance$fecha[attendance$outlet_final %in% "mexico news"])
  added <- attendance[
    attendance$outlet_final %in% "sin censura" &
      !as.Date(attendance$fecha) %in% target_dates, , drop = FALSE
  ]
  added <- added[!duplicated(as.Date(added$fecha)), , drop = FALSE]
  added$outlet_final <- rep("mexico news", nrow(added))
  for (column in intersect(c("outlet_clean", "canonical_outlet"), names(added))) {
    added[[column]] <- rep("mexico news", nrow(added))
  }
  if ("medios" %in% names(added)) {
    added$medios <- rep("THE MEXICO NEWS [ASSUMED FROM SIN CENSURA]", nrow(added))
  }
  added$attendance_assumed <- rep(TRUE, nrow(added))
  added$attendance_basis <- rep("assumed_coaffiliation", nrow(added))
  added$attendance_source_outlet <- rep("sin censura", nrow(added))
  dplyr::bind_rows(attendance, added)
}

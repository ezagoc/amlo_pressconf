# Exact reviewed labels override broad legacy rules, using the ORIGINAL label.
# Do not strip business words or use fuzzy matching here.
normalize_reviewed_label <- function(x) {
  x <- stringi::stri_trans_general(tolower(x), "Latin-ASCII")
  trimws(gsub(" +", " ", gsub("[^a-z0-9]+", " ", x)))
}

read_outlet_aliases <- function(path) {
  aliases <- read.delim(path, stringsAsFactors = FALSE, check.names = FALSE,
                        na.strings = "", quote = "", fileEncoding = "UTF-8")
  stopifnot(all(c("alias", "canonical_id") %in% names(aliases)))
  aliases$key <- normalize_reviewed_label(aliases$alias)
  if (anyNA(aliases$key) || any(!nzchar(aliases$key)) || anyDuplicated(aliases$key)) {
    stop("Reviewed alias keys must be nonempty and unique")
  }
  if ("status" %in% names(aliases)) {
    stopifnot(all(aliases$status %in% c("reviewed", "needs_review")),
              !anyNA(aliases$canonical_id[aliases$status == "reviewed"]),
              all(is.na(aliases$canonical_id[aliases$status == "needs_review"])))
  } else if (anyNA(aliases$canonical_id)) stop("Question aliases require an ID")
  aliases
}

apply_reviewed_attendance_linkage <- function(attendance, aliases) {
  stopifnot(all(c("medios", "outlet_final") %in% names(attendance)))
  if (!"outlet_before_review" %in% names(attendance)) {
    attendance$outlet_before_review <- attendance$outlet_final
  }
  index <- match(normalize_reviewed_label(attendance$medios), aliases$key)
  found <- !is.na(index)
  attendance$outlet_linkage_status <- rep("legacy_unreviewed", nrow(attendance))
  attendance$outlet_linkage_reason <- rep(NA_character_, nrow(attendance))
  attendance$outlet_linkage_source <- rep(NA_character_, nrow(attendance))
  attendance$outlet_linkage_status[found] <- aliases$status[index[found]]
  attendance$outlet_linkage_reason[found] <- aliases$reason[index[found]]
  attendance$outlet_linkage_source[found] <- aliases$source[index[found]]
  # Ambiguous labels stay in the audit/clean data, but cannot enter outlet panels.
  attendance$outlet_final[found] <- aliases$canonical_id[index[found]]
  attendance
}

apply_reviewed_question_linkage <- function(original, legacy_id, aliases) {
  stopifnot(length(original) == length(legacy_id))
  index <- match(normalize_reviewed_label(original), aliases$key)
  found <- !is.na(index)
  legacy_id[found] <- aliases$canonical_id[index[found]]
  legacy_id
}

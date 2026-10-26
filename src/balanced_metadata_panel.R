#' Expand outlet metadata into a balanced time panel
#'
#' Every metadata row is repeated once for every period between `from` and `to`,
#' inclusive. Periods are anchored on `from`; for example, a weekly panel that
#' starts on a Friday will contain Fridays.
#'
#' @param metadata A data frame with one row per panel unit.
#' @param frequency One of "daily", "weekly", "monthly", "semester", or
#'   "yearly".
#' @param from,to Values coercible to Date. Both endpoints are inclusive.
#' @param id_cols Columns that uniquely identify rows in `metadata`.
#' @param date_col Name of the generated period column.
#'
#' @return A tibble sorted by `id_cols` and the generated date column.
metadata_to_balanced_panel <- function(
    metadata,
    frequency = c("daily", "weekly", "monthly", "semester", "yearly"),
    from,
    to,
    id_cols = "metadata_id",
    date_col = "period_start") {
  frequency <- match.arg(frequency)
  from <- as.Date(from)
  to <- as.Date(to)

  if (length(from) != 1L || is.na(from) || length(to) != 1L || is.na(to)) {
    stop("`from` and `to` must each be one valid date.", call. = FALSE)
  }
  if (from > to) {
    stop("`from` must be on or before `to`.", call. = FALSE)
  }
  if (!is.data.frame(metadata) || nrow(metadata) == 0L) {
    stop("`metadata` must be a non-empty data frame.", call. = FALSE)
  }
  missing_ids <- setdiff(id_cols, names(metadata))
  if (length(missing_ids) > 0L) {
    stop(
      "Missing ID column(s): ", paste(missing_ids, collapse = ", "),
      call. = FALSE
    )
  }
  if (date_col %in% names(metadata)) {
    stop("`date_col` already exists in `metadata`: ", date_col, call. = FALSE)
  }

  id_frame <- metadata[id_cols]
  if (any(!stats::complete.cases(id_frame))) {
    stop("The panel ID columns cannot contain missing values.", call. = FALSE)
  }
  if (anyDuplicated(id_frame)) {
    stop("`id_cols` must uniquely identify every metadata row.", call. = FALSE)
  }

  interval <- switch(
    frequency,
    daily = "day",
    weekly = "week",
    monthly = "month",
    semester = "6 months",
    yearly = "year"
  )
  periods <- seq.Date(from = from, to = to, by = interval)
  period_grid <- stats::setNames(data.frame(periods), date_col)

  panel <- tidyr::crossing(tibble::as_tibble(metadata), period_grid)
  dplyr::arrange(panel, dplyr::across(dplyr::all_of(c(id_cols, date_col))))
}

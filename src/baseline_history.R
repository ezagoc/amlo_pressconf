# Historical counts are frozen before the lottery, never rolled forward.
baseline_windows <- function(cutoff, history_start = as.Date("2018-12-01")) {
  cutoff <- as.Date(cutoff)
  history_start <- as.Date(history_start)
  stopifnot(length(cutoff) == 1L, length(history_start) == 1L,
            !is.na(cutoff), !is.na(history_start), history_start < cutoff)
  starts <- seq(history_start, cutoff - 1, by = "year")
  ends <- c(starts[-1] - 1, cutoff - 1)
  tibble::tibble(
    window = c("total", paste0("year", seq_along(starts)), "last_year", "last_2years"),
    from = c(history_start, starts,
             max(history_start, lubridate::`%m-%`(cutoff, lubridate::years(1))),
             max(history_start, lubridate::`%m-%`(cutoff, lubridate::years(2)))),
    to = c(cutoff - 1, ends, cutoff - 1, cutoff - 1)
  )
}

# No observed values -> NA, rather than a fabricated historical zero.
history_sum <- function(x) if (all(is.na(x))) NA_real_ else sum(x, na.rm = TRUE)
history_ratio <- function(numerator, denominator) {
  ifelse(!is.na(denominator) & denominator > 0, numerator / denominator, NA_real_)
}

# Aggregate once per cleaned beneficiary BEFORE mapping shared IDs to metadata.
# Dates and monetary/count definitions come from the deduplicated COMSOC panel.
summarise_contract_history <- function(days, windows, cutoff) {
  measures <- c("contracts_costo", "contracts_importe", "contracts_received_n", "contracts_n")
  stopifnot(!anyDuplicated(days[c("contracts_entity_id", "date")]),
            all(days$date < as.Date(cutoff)), all(windows$to < as.Date(cutoff)),
            all(windows$from <= windows$to), !anyDuplicated(windows$window))
  days <- days |>
    dplyr::mutate(
      contracts_observed = dplyr::coalesce(source_entity_matched & source_date_observed, FALSE),
      dplyr::across(dplyr::all_of(measures),
                    ~ dplyr::if_else(contracts_observed, .x, NA_real_)))
  dplyr::bind_rows(lapply(seq_len(nrow(windows)), function(i) {
    w <- windows[i, ]
    days |>
      dplyr::filter(dplyr::between(date, w$from, w$to)) |>
      dplyr::group_by(contracts_entity_id) |>
      dplyr::summarise(
        window = w$window,
        contracts_observed_days = sum(contracts_observed),
        contracts_award_days = history_sum(as.integer(contracts_n > 0)),
        dplyr::across(dplyr::all_of(measures), history_sum),
        .groups = "drop")
  }))
}

prepare_baseline_days <- function(days, excluded_attendance_months = "2021-11") {
  stopifnot(!anyDuplicated(days[c("metadata_id", "date")]))
  days |>
    dplyr::mutate(
      attendance_observed = dplyr::coalesce(attendance_matched & attendance_observed, FALSE) &
        !format(date, "%Y-%m") %in% excluded_attendance_months,
      questions_observed = dplyr::coalesce(questions_matched & questions_observed, FALSE),
      attendance_recorded = dplyr::if_else(attendance_observed, attendance_recorded, NA_real_),
      attendance_assumed = dplyr::if_else(attendance_observed, attendance_assumed, NA_real_),
      questions = dplyr::if_else(questions_observed, questions, NA_real_),
      asked = dplyr::if_else(questions_observed, as.integer(questions > 0), NA_integer_),
      # At least ONE attendee when a question is recorded, not one per question.
      # A zero question count does not establish zero attendance on an unobserved day.
      attendance_corrected = dplyr::case_when(
        attendance_observed ~ pmax(attendance_recorded + attendance_assumed,
                                  dplyr::coalesce(asked, 0L)),
        asked == 1L ~ 1,
        TRUE ~ NA_real_),
      attendance_inferred = dplyr::if_else(!is.na(attendance_corrected),
        attendance_corrected - dplyr::coalesce(attendance_recorded, 0) -
          dplyr::coalesce(attendance_assumed, 0), NA_real_),
      common_observed = attendance_observed & questions_observed
    )
}

summarise_baseline_history <- function(days, windows, cutoff) {
  stopifnot(all(windows$to < as.Date(cutoff)), all(windows$from <= windows$to),
            all(days$date < as.Date(cutoff)), !anyDuplicated(windows$window))
  dplyr::bind_rows(lapply(seq_len(nrow(windows)), function(i) {
    w <- windows[i, ]
    days |>
      dplyr::filter(dplyr::between(date, w$from, w$to)) |>
      dplyr::group_by(metadata_id) |>
      dplyr::summarise(
        window = w$window,
        # Compute common-date quantities before reusing daily column names
        # (e.g. questions) for totals below: summarise evaluates sequentially.
        common_questions = history_sum(questions[common_observed]),
        common_attendance = history_sum(attendance_corrected[common_observed]),
        common_attendance_recorded = history_sum(attendance_recorded[common_observed]),
        common_attendance_days = history_sum(as.integer(attendance_corrected[common_observed] > 0)),
        common_question_days = history_sum(asked[common_observed]),
        attendance = history_sum(attendance_recorded),
        attendance_assumed = history_sum(attendance_assumed),
        attendance_inferred = history_sum(attendance_inferred),
        attendance_corrected = history_sum(attendance_corrected),
        questions = history_sum(questions),
        attendance_days = history_sum(as.integer(attendance_recorded > 0)),
        question_days = history_sum(asked),
        attendance_observed_days = sum(attendance_observed),
        questions_observed_days = sum(questions_observed),
        common_observed_days = sum(common_observed),
        .groups = "drop"
      ) |>
      dplyr::mutate(
        # Main ratio: question counts / corrected journalist attendance records.
        questions_per_attendance = history_ratio(common_questions, common_attendance),
        questions_per_recorded_attendance = history_ratio(common_questions, common_attendance_recorded),
        # Separate binary-day ratio used in the earlier descriptive figures.
        question_day_share = history_ratio(common_question_days, common_attendance_days)
      )
  }))
}

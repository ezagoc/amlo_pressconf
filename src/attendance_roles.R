# Preserve cargo for auditing; normalize only the value used for eligibility.
# This is a role filter, not a claim that retained rows identify unique people.
attendance_role_group <- function(cargo) {
  role <- stringi::stri_trans_general(as.character(cargo), "Latin-ASCII") |>
    stringr::str_to_upper() |>
    stringr::str_squish()
  # User-approved pool: reporters and YouTubers only. REPORTETO is an observed
  # typo. Exact matching deliberately rejects mixed roles and other job titles.
  dplyr::case_when(
    role %in% c("REPORTERO", "REPORTERA", "REPORTEROS", "REPORTERAS", "REPORTETO") ~ "reportero",
    role %in% c("YOUTUBER", "YOUTUBERS") ~ "youtuber",
    TRUE ~ NA_character_
  )
}

keep_attendance_role <- function(cargo) {
  !is.na(attendance_role_group(cargo))
}

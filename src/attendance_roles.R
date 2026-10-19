# Preserve cargo for auditing; normalize only the value used for exclusion.
# This is a role filter, not a claim that retained rows identify unique people.
keep_attendance_role <- function(cargo) {
  role <- stringi::stri_trans_general(as.character(cargo), "Latin-ASCII") |>
    stringr::str_to_upper() |>
    stringr::str_squish()
  # Stems cover gender/plural variants, with and without accents/capitalization.
  excluded <- "CAMAROGRAF|ESTUDIANTE|TECNIC|INGENIERO KU|FOTOGRAF|AUDIO"
  # The old dplyr filter also dropped missing cargo; retain that behavior.
  !is.na(role) & !stringr::str_detect(role, excluded)
}

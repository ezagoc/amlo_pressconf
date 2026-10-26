# Provisional, source-literal definitions pending the user's geographic choice.
# Do not infer Mexico City metro membership from all of Estado de Mexico.
add_balance_geography <- function(metadata) {
  metadata |>
    dplyr::mutate(
      mexico_city = as.integer(dplyr::coalesce(city.headq == 9, FALSE)),
      metropolitan_area = as.integer(grepl("\\bmetropolitan\\b",
        tolower(dplyr::coalesce(coverage.scope, "")))))
}
geography_definition <- paste(
  "Provisional geographic coding, pending confirmation: Mexico City outlet means",
  "headquarters-state code city.headq = 9. Metropolitan-area outlet means an explicit",
  "'metropolitan' label in coverage.scope, regardless of which metropolitan area.",
  "The latter is NOT a Mexico City metropolitan-area headquarters indicator.",
  "These are separate metadata concepts, not nested location categories.",
  "An absent code or label is zero under the requested binary-covariate convention.")

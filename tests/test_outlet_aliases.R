# Run from the repository root: Rscript tests/test_outlet_aliases.R
# Evaluate only the actual name-cleaning expressions; never run pipeline writes.
suppressPackageStartupMessages({library(dplyr); library(stringr)})
source("src/attendance_coaffiliation.R")
get_rule <- function(path) {
  expressions <- parse(path)
  matches <- vapply(expressions, function(e) {
    txt <- paste(deparse(e), collapse = " ")
    grepl("case_when", txt, fixed = TRUE) &&
      grepl("mexico news world", txt, fixed = TRUE)
  }, logical(1))
  stopifnot(sum(matches) == 1L)
  expressions[[which(matches)]]
}
labels <- c("quadratin veracruz", "sol quintana roo", "el sol de quintana roo",
  "sol yucatan", "el sol de yucatan", "grupo sol campeche", "el sol de mexico",
  "mexico news world", "canal mexico news world", "the mexico news",
  "mexico news daily", "sin censura")
expected <- c("quadratin", rep("grupo sol", 5), "oem mexico",
  "mexico news world", "mexico news world", "mexico news", "mexico news daily", "sin censura")
env <- new.env()
env$df <- tibble(outlet_clean = labels)
eval(get_rule("code/05-press_conferences/00-preprocessing_attendance.R"), env)
stopifnot(identical(env$df$outlet_clean, expected))
env$df <- tibble(outlet_aux = labels)
expected[10] <- "the mexico news"
eval(get_rule("code/03-cleaning_conf/question_class/05_deduplicate_outlets_periodistas.R.R"), env)
stopifnot(identical(env$df$outlet_aux, expected))

# The user intentionally groups broad BCS labels, not just BCS Noticias.
for (column in c("outlet_clean", "outlet_aux")) {
  env$df <- tibble(value = c("bcs noticias", "nbcs noticias", "monitorbcs"))
  names(env$df) <- column
  path <- if (column == "outlet_clean")
    "code/05-press_conferences/00-preprocessing_attendance.R" else
    "code/03-cleaning_conf/question_class/05_deduplicate_outlets_periodistas.R.R"
  eval(get_rule(path), env)
  stopifnot(all(env$df[[column]] == "medios digitales del pacifico"))
}

# Once Noticias shares Canal Once's ID, while ON Noticias stays separate.
for (column in c("outlet_clean", "outlet_aux")) {
  env$df <- tibble(value = c("once noticias", "oncenoticias.digital", "canal once",
    "canal 11", "on noticias"))
  names(env$df) <- column
  path <- if (column == "outlet_clean")
    "code/05-press_conferences/00-preprocessing_attendance.R" else
    "code/03-cleaning_conf/question_class/05_deduplicate_outlets_periodistas.R.R"
  eval(get_rule(path), env)
  stopifnot(identical(env$df[[column]], c(rep("canal 11", 4), "on noticias")))
}

# Marco Olvera's personal brand shares News World's ID in both source cleaners.
for (column in c("outlet_clean", "outlet_aux")) {
  env$df <- tibble(value = c("marco olvera oficial", "marco antonio olvera",
    "marco olvera mexico news", "mexico news world", "bajo palabra"))
  names(env$df) <- column
  path <- if (column == "outlet_clean")
    "code/05-press_conferences/00-preprocessing_attendance.R" else
    "code/03-cleaning_conf/question_class/05_deduplicate_outlets_periodistas.R.R"
  eval(get_rule(path), env)
  stopifnot(identical(env$df[[column]], c(rep("mexico news world", 4), "bajo palabra")))
}

# Two Sin Censura records still add only one attendance; existing target records
# and News World remain intact. Reapplying the rule must not add more rows.
a <- tibble(fecha = as.Date(c("2022-01-01", "2022-01-01", "2022-01-02",
  "2022-01-02", "2022-01-03")),
  outlet_final = c("sin censura", "sin censura", "sin censura", "mexico news", "mexico news world"))
result <- add_mexico_news_coattendance(a)
stopifnot(nrow(result) == 6L, sum(result$attendance_assumed) == 1L,
  identical(result[!result$attendance_assumed, names(a)], a),
  identical(add_mexico_news_coattendance(result), result),
  nrow(add_mexico_news_coattendance(a[FALSE, ])) == 0L,
  sum(!result$attendance_assumed) == nrow(a))
cat("Outlet alias and co-affiliation tests passed.\n")

source("src/metadata_helpers.R")
env$df <- tibble(outlet_aux = c("informando la transformacion", "sin puntos ni comas",
  "sin puntos, ni comas", "ni puntos ni comas", "julio omar gomez sanchez",
  "julioomargs.com", "juliomargs.com", "medios digitales del pacifico", "el astillero"))
eval(get_rule("code/03-cleaning_conf/question_class/05_deduplicate_outlets_periodistas.R.R"), env)
stopifnot(identical(env$df$outlet_aux, c(rep("medios digitales del pacifico", 8), "el astillero")))
m <- tibble(name.page = c("Grupo Sol Campeche", "Los Reporteros MX", "El Quintana Roo MX"),
  names.conference = c("GRUPO SOL", "REPORTEROS MX", "losreporterosmx"),
  names.transcripts = c(NA_character_, "losreporterosmx", "reporterosmx"))
m <- apply_reviewed_conference_keys(m)
stopifnot(identical(m$names.conference, c("grupo sol", "reporteros mx", "reporteros mx")),
  identical(m$names.transcripts, c("grupo sol", "losreporterosmx", "losreporterosmx")))
source("src/final_panel_helpers.R")
items <- tibble(entity_id = c("grupo sol", "grupo sol", "another outlet"),
  date = as.Date("2022-04-05"), reporter_aux = "manuel lopez",
  turn_index = 1L, item_index = 1L, item_type = "pregunta", text = "A question",
  outlet = c("Sol Yucatan", "Sol Quintana Roo", "Another outlet"))
stopifnot(nrow(deduplicate_canonical_question_items(items, "entity_id")) == 2L)
cat("Metadata crosswalk and canonical-item deduplication tests passed.\n")

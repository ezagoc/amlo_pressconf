# Manual journalist/outlet harmonization: Claudia Sheinbaum
# Adapted from ../05_deduplicate_outlets_periodistas.R.R
#
# Review workflow:
#   1. Run this file with WRITE_OUTPUT <- FALSE.
#   2. View(outlet_table), View(reporter_table), View(name_table).
#   3. Inspect candidate_pairs and the source evidence with inspect_names().
#   4. Edit the case_when() sections below and rerun. Inspect changed_rows,
#      alias_audit, collapsed_rows, and before_after before exporting.
#   5. Set WRITE_OUTPUT <- TRUE and rerun when the mappings are ready.
#
# Unit: observed identification, NOT an individual question or attendance count.
# Missing names stay missing. No AMLO-specific outlet assignments are imported.
# Original extraction files and the existing PDF are not overwritten.

WRITE_OUTPUT <- FALSE
DATA_VERSION <- "official_full" # alternatives: "api_full" or "original_reviewed"

suppressPackageStartupMessages({
  library(dplyr)
  library(stringr)
  library(arrow)
  library(readr)
  library(tibble)
})

# Work from the repo root, Rscript, or this file open in RStudio.
find_project_root <- function() {
  starts <- getwd()
  args <- commandArgs(trailingOnly = FALSE)
  script_arg <- args[startsWith(args, "--file=")]
  if (length(script_arg)) starts <- c(starts, dirname(sub("^--file=", "", script_arg[1])))
  if (requireNamespace("rstudioapi", quietly = TRUE) && rstudioapi::isAvailable()) {
    active <- rstudioapi::getActiveDocumentContext()$path
    if (nzchar(active)) starts <- c(starts, dirname(active))
  }
  for (start in starts) {
    path <- normalizePath(start, mustWork = TRUE)
    repeat {
      if (file.exists(file.path(path, "project_paths.R"))) return(path)
      parent <- dirname(path)
      if (identical(parent, path)) break
      path <- parent
    }
  }
  stop("Run from the amlo_pressconf repository or open this file in RStudio.")
}

project_root <- find_project_root()
source(file.path(project_root, "project_paths.R"), chdir = TRUE)
stopifnot(DATA_VERSION %in% c("official_full", "api_full", "original_reviewed"))
pfo <- if (DATA_VERSION == "official_full") {
  media_path("data", "02-conferences-sheinbaum", "api_extraction", "official-full", "auxiliar")
} else if (DATA_VERSION == "api_full") {
  media_path("data", "02-conferences-sheinbaum", "api_extraction", "full", "auxiliar")
} else {
  media_path("data", "02-conferences-sheinbaum", "auxiliar")
}
message("Reviewing ", DATA_VERSION, " data in ", pfo)

# Inspection notes only; no record is automatically removed by these flags.
review_flags <- if (file.exists(file.path(pfo, "full_run_review_flags.csv"))) {
  read_csv(file.path(pfo, "full_run_review_flags.csv"), show_col_types = FALSE)
} else {
  tibble()
}
# View(review_flags)

raw <- read_parquet(file.path(pfo, "periodistas_v2_all_years.parquet")) |>
  mutate(date = as.Date(date), record_id = row_number())

# Frequencies use distinct dates, so multi-outlet introductions do not inflate
# the journalist-day count. n_records is provided separately for inspection.
outlet_table <- raw |>
  filter(!is.na(outlet_aux)) |>
  group_by(outlet_aux) |>
  summarise(outlet_spellings = paste(sort(unique(outlet)), collapse = " | "),
            n_days = n_distinct(date), n_records = n(),
            n_named_reporters = n_distinct(reporter_aux, na.rm = TRUE),
            first_date = min(date), last_date = max(date), .groups = "drop") |>
  arrange(desc(n_days), outlet_aux)

reporter_table <- raw |>
  filter(!is.na(reporter_aux)) |>
  group_by(reporter_aux) |>
  summarise(reporter_spellings = paste(sort(unique(reporter)), collapse = " | "),
            outlets = paste(sort(unique(na.omit(outlet_aux))), collapse = " | "),
            n_days = n_distinct(date), n_records = n(),
            first_date = min(date), last_date = max(date), .groups = "drop") |>
  arrange(desc(n_days), reporter_aux)

name_table <- raw |>
  group_by(outlet_aux, reporter_aux) |>
  summarise(n_days = n_distinct(date), n_records = n(), .groups = "drop") |>
  arrange(outlet_aux, reporter_aux)
df_rep_out <- name_table # familiar AMLO inspection object

# Review leads unless explicitly marked confirmed: neither similarity nor
# shared ownership proves an alias.
candidate_pairs <- tribble(
  ~type, ~labels, ~reason,
  "reporter", "tere mora | tere mora guillen", "Same date (2025-04-14), same outlet, repeated self-introduction.",
  "reporter", "citlali guerrero | citlalli guerrero", "Both identify with Bajo Palabra; likely spelling variation.",
  "reporter", "manuel galeazzi | manuel galeazzi ramirez", "Both identify with Sin Linea; shortened/full name.",
  "reporter", "haydee ramirez | reyna haydee ramirez", "Possible shortened/full name; inspect both introductions.",
  "reporter", "yusbel carolina | yusbel rada", "Both identify with Codigo Libre; verify identity before merging.",
  "outlet", "atiempocommx | tiempocommx", "Both appear alongside Puente Libre/Ciudad Juarez; verify transcription.",
  "outlet", "canal once | once noticias | once digital | once noticias digital", "Decide channel-level vs program/platform-level grouping.",
  "outlet", "maxima | maxima fm", "The short label alone does not establish the same outlet.",
  "outlet", "grupo canton | diario basta | tabasco hoy | campeche hoy | quintana roo hoy", "AMLO used group-level aggregation; choose the same level only if intended.",
  "outlet", "grupo healy | el imparcial de sonora | la cronica de mexicali | frontera de tijuana", "Parent group vs distinct titles; not simply spelling aliases.",
  "confirmed outlet", "grupo transmedia | la chispa", "User confirmed one combined name: Grupo Transmedia La Chispa. Active rule below.",
  "keep distinct unless verified", "sandra aguilar | sandra aguilera", "Similar names, but different stated affiliations.",
  "keep distinct unless verified", "codigo libre | codigo rojo", "Do not copy the broad AMLO 'codigo' rule.",
  "keep distinct unless verified", "dalila escobar | dalila sarabia", "Do not copy the broad AMLO 'dalila' rule.",
  "keep distinct unless verified", "el financiero | bloomberg linea | bloomberg news", "Do not automatically collapse every Bloomberg label into El Financiero."
)

inspect_names <- function(pattern, type = c("outlet", "reporter")) {
  type <- match.arg(type)
  column <- paste0(type, "_aux")
  raw |>
    filter(str_detect(coalesce(.data[[column]], ""), pattern)) |>
    select(record_id, date, reporter, outlet, reporter_aux, outlet_aux,
           source_rows, evidence_text, source_path) |>
    arrange(date, record_id)
}
# Example: View(inspect_names("once|tiempocommx", "outlet"))
# Example: View(inspect_names("tere mora|citlal", "reporter"))

if (interactive()) View(inspect_names("noticias", "outlet"))
if (interactive()) View(inspect_names("victor", "reporter"))

df <- raw |>
  mutate(
    outlet_aux_before = outlet_aux,
    reporter_aux_before = reporter_aux,
    outlet_aux = case_when(
      is.na(outlet_aux) ~ NA_character_,
      outlet_aux %in% c("canal de las noticias", "el canal de las noticias") ~ "canal de las noticias",
      outlet_aux %in% c("grupo ae informativo", "ae grupo informativo") ~ "ae grupo informativo",
      outlet_aux %in% c("posta", "posta ciudad de mexico") ~ "posta",
      outlet_aux %in% c("ecos media mx", "ecos media", "ecos media mexico") ~ "ecos media",
      outlet_aux %in% c("la hoguera", "la hoguera mx") ~ "la hoguera",
      outlet_aux %in% c("luces del siglo", "luces mananeras", "luces de siglo",
                        "multimedia luces del siglo") ~ "luces del siglo",
      outlet_aux %in% c("noticiasdefrentecom", "noticias de frente", 
                        "noticias de frentecom") ~ "noticias de frente",
      outlet_aux %in% c("33 de tijuana", "canal 66", "33", "canal 44 de ciudad juarez", 
                        "66", "canal 66 de mexicali") ~ "canales norte (tijuana, juarez, etc)",
      outlet_aux %in% c("el charro politico") ~ "el charro politico",
      outlet_aux %in% c("grupo intermedia") ~ "grupo intermedia",
      outlet_aux %in% c("canal 44 de la universidad de guadalajara", 
                        "radio universidad de guadalajara", 
                        "radio universidad de guadalajara en puerto vallarta") ~ "universidad de guadalajara",
      outlet_aux %in% c("plaza juarez", "diario plaza juarez") ~ "diario plaza juarez",
      outlet_aux %in% c("quatro media telecomunicaciones", "cuatromedia telecomunicaciones", 
                        "cuatromedia telecomunicaciones veracruz", "cuatro media",
                        "quatro media telecomunicaciones veracruz", "avanoticias", 
                        "ava noticias", "cuatro media telecomunicaciones") ~ "avan noticias",
      outlet_aux %in% c("el universal") ~ "el universal",
      outlet_aux %in% c("debate", "el debate") ~ "debate",
      outlet_aux %in% c("iztaccihuatl en el sendero de la luna") ~ "sendero de la luna",
      outlet_aux %in% c("radio relax 1045 fm", "relax 1045 fm", 
                        "relax 1045 fm noticias") ~ "relax",
      outlet_aux %in% c("noticieros el reloj", "la tlaxiaquena", "la tlaxiaquena 915",
                        "noticieros el reloj de tlaxiaquena 915") ~ "noticieros el reloj de la tlaxiaquena",
      outlet_aux %in% c("meganoticias", "meganoticias queretaro") ~ "meganoticias",
      outlet_aux %in% c("once noticias", "canal 11", "el once", 
                        "once noticias digital", "once", "canal once", 
                        "once digital") ~ "canal 11",
      outlet_aux %in% c("hctv noticias", "hctv", "hc noticias", "hct noticias",
                        "hc") ~ "noticieros hctv",
      outlet_aux %in% c("capital 21", "capital 21 el corazon de la capital", 
                        "capital 21 corazon de la capital") ~ "capital 21",
      outlet_aux %in% c("la razon", "periodico la razon") ~ "la razon",
      outlet_aux %in% c("perspectivasmx", "perspectivas mx", "perspectivas") ~ "perspectivas",
      outlet_aux %in% c("noticias del movimiento conciencia") ~ "movimiento conciencia",
      outlet_aux %in% c("el centinela informa", "centinela informa") ~ "el centinela informa",
      outlet_aux %in% c("noticiero en redes") ~ "noticiero en redes",
      outlet_aux %in% c("eli tv oficial") ~ "eli tv oficial",
      outlet_aux %in% c("bajo palabra") ~ "bajo palabra",
      outlet_aux %in% c("canal 14 spr", "spr canal 14", "canal 14", "spr", "sistema publico", 
                        "sistema publico de radiodifusion del estado mexicano",
                        "altavoz radio", 
                        "altavoz radio del sistema publico de radiodifusion del estado mexicano")  ~ "canal 14 spr",
      outlet_aux %in% c("medios digitales del pacifico", "agencia de medios digitales del pacifico", 
                        "el reportero urbano", "medio digitales del pacifico", "mdp", "medios del pacifico",
                         "julioomargscom") ~ "medios digitales del pacifico",
      outlet_aux %in% c("los reporteros mx", "reporteros mx", "reporterosmx", "elquintanaroomx", 
                        "quintana roo mx", "reporteros mx",
                        "quintanaroomx", "el quintana roo mx") ~ "losreporterosmx",
      outlet_aux %in% c("codigolibremx",  "codigo libre") ~ "codigo libre",
      outlet_aux %in% c("agencia ap",  "ap") ~ "associated press",
      outlet_aux %in% c("polemon", "revista polemon") ~ "polemon",
      outlet_aux %in% c("grupo transmedia", "la chispa",
                        "grupo transmedia la chispa") ~ "grupo transmedia la chispa",
      outlet_aux %in% c("el imparcial", "grupo healy", "la cronica",
                        "frontera", "la cronica de mexicali") ~ "healy",
      outlet_aux %in% c("el sol de mexico") ~ "oem mexico",
      outlet_aux %in% c("business energy", "gaceta business energy", 
                        "gaceta petrolera de tabasco") ~ "business energy", #Yesenia Peralta -> business energy
      outlet_aux %in% c("pie de pagina") ~ "alianza de medios independientes",
      outlet_aux %in% c("sin censura", "sin censura tv") ~ "sin censura",
      outlet_aux %in% c("lm noticias", "informativo lm", "lord molecula", 
                        "lord molecula oficial") ~ "lord molecula oficial",
      outlet_aux %in% c("diario red") ~ "diario red latinoamerica",
      outlet_aux %in% c("vanguardia veracruz", "vanguardia") ~ "mmm vanguardia",
      outlet_aux %in% c("sin linea", "sin linea mx", "grupo sin linea") ~ "sin linea",
      outlet_aux %in% c("mexico news world", "mexico network", "news world", "mexiconetwork") ~ "mexico news world",
      outlet_aux %in% c("w radio") ~ "w radio",
      outlet_aux %in% c("puentelibremx", "puente libre", "puentelibre mx") ~ "puente libre mx",
      outlet_aux %in% c("miled mexico", "radio miled", "grupo miled") ~ "miled",
      outlet_aux %in% c("amarc", "asociacion mundial de radios comunitarias", 
                        "radio tepoztlan") ~ "amarc",
      outlet_aux %in% c("agencia sputnik", "sputnik") ~ "sputnik",
      outlet_aux %in% c("sonora power", "telemax", "noticias telemax") ~ "sonora power",
      outlet_aux %in% c("politica y rock and roll", "politica y rock and roll radio") ~ "politica y rock radio",
      outlet_aux %in% c("imer", "instituto mexicano de la radio", "imer noticias") ~ "imer",
      outlet_aux %in% c("el heraldo", "el heraldo media group", 
                        "heraldo media group", "el heraldo de mexico", 
                        "heraldo usa", "el heraldo usa") ~ "el heraldo",
      outlet_aux %in% c("milenio", "grupo milenio") ~ "milenio",
      outlet_aux %in% c("polemon", "revista polemon") ~ "polemon",
      outlet_aux %in% c("lanzate canal 73", "cnr de lanzate") ~ "cnr canal 73",
      outlet_aux %in% c("unotv", "uno tv") ~ "uno tv",
      outlet_aux %in% c("diario 24 horas", "24 horas") ~ "diario 24 horas",
      outlet_aux %in% c("reforma", "grupo reforma") ~ "reforma",
      outlet_aux %in% c("mvs noticias", "mvs noticias los cabos") ~ "mvs noticias",
      outlet_aux %in% c("la jornada") ~ "la jornada",
      outlet_aux %in% c("esahoraam") ~ "es ahora am",
      outlet_aux %in% c("sdp", "sdp noticias", "sdpnoche", "deforma") ~ "sdpnoticias",
      outlet_aux %in% c("adn 40", "azteca", "television azteca") ~ "tv azteca",
      outlet_aux %in% c("formula", "grupo formula") ~ "grupo formula",
      outlet_aux %in% c("el financiero", "el financiero bloomberg", "bloomberg", "bloomberg news",
                        "financiero bloomberg",
                        "bloomberg linea", "el financiero bloomberg television") ~ "el financiero",
      outlet_aux %in% c("basta", "canton", "tabasco hoy", "grupo canton", "diario basta",
                        "quintana roo hoy", "campeche hoy", "quintana roo") ~ "grupo canton",
      outlet_aux %in% c("jf informa") ~ "jaime farias informa",
      outlet_aux %in% c("atiempocommx", "tiempocommx", "tiempo") ~ "tiempo la noticia digital",
      outlet_aux %in% c("canal once", "once noticias", "once digital",
                        "once noticias digital") ~ "canal once",
      outlet_aux %in% c("imagen del golfo", "imagen de veracruz", "grupo imagen del golfo", 
                        "imagen veracruz", "la imagen de veracruz",
                        "corporativo imagen", "diario del istmo", "el diario del istmo") ~ "imagen del golfo",
      outlet_aux %in% c("contralinea", "revista contralinea") ~ "contralinea",
      outlet_aux %in% c("imagen", "grupo imagen", "grupo imagen radio", 
                        "imagen radio") ~ "grupo imagen",
      outlet_aux %in% c("fm", "la poderosa", "radio resultados") ~ "radio resultados",
      outlet_aux %in% c("el politico", "el politico en las redes") ~ "el politico en las redes",
      outlet_aux %in% c("comunicantemx", "comunicante mx") ~ "comunicante mx",
      TRUE ~ outlet_aux
    ),
    reporter_aux = case_when(
      is.na(reporter_aux) ~ NA_character_,
      reporter_aux %in% c("tere mora", "tere mora guillen") ~ "tere mora guillen",
      reporter_aux %in% c("citlali guerrero", "citlalli guerrero") ~ "citlalli guerrero",
      reporter_aux %in% c("manuel galeazzi", "manuel galeazzi ramirez") ~ "manuel galeazzi ramirez",
      reporter_aux %in% c("eli", "eliane valadez") ~ "eliane valadez",
      TRUE ~ reporter_aux
    )
  )

df <- df %>%
  mutate(
    outlet_aux = case_when(
      str_detect(outlet_aux, "telemundo") ~ "telemundo",
      str_detect(outlet_aux, "albavision") ~ "albavision",
      str_detect(outlet_aux, "blogs|mexico informa") ~ "mexico informa",
      str_detect(outlet_aux, "embargo") ~ "sin embargo",
      str_detect(outlet_aux, "transmitiendo") ~ "desde la frontera",
      str_detect(outlet_aux, "tvbaja|tv baja") ~ "tv baja",
      str_detect(outlet_aux, "maxima") ~ "maxima fm",
      str_detect(outlet_aux, "nx noticias|mx noticias") ~ "nx noticias",
      str_detect(outlet_aux, "tubos") ~ "los tubos",
      str_detect(outlet_aux, "pop|labo") ~ "laboratorio de periodismo y opinion publica",
      str_detect(outlet_aux, "jornada") ~ "la jornada",
      str_detect(outlet_aux, "excelsior") ~ "excelsior",
      str_detect(outlet_aux, "hidalgo news|hidalgo noticias") ~ "hidalgo news",
      str_detect(outlet_aux, "xinhua") ~ "xinhua",
      str_detect(outlet_aux, "angulo 7|angulo siete") ~ "angulo 7",
      str_detect(outlet_aux, "telesur") ~ "telesur",
      str_detect(outlet_aux, "animales") ~ "animales con derechos",
      str_detect(outlet_aux, "exclusiva") ~ "exclusivas puebla",
      str_detect(outlet_aux, "chapucero") ~ "el chapucero",
      str_detect(outlet_aux, "grupo 7|grupo siete") ~ "grupo siete noticias",
      str_detect(outlet_aux, "human") ~ "el centinela informa",
      str_detect(outlet_aux, "lobos cadena|cadena 7") ~ "lobos cadena 7",
      str_detect(outlet_aux, "la mont") ~ "asi lo dice la mont",
      str_detect(outlet_aux, "publimetro") ~ "publimetro",
      str_detect(outlet_aux, "diario basta|grupo canton") ~ "grupo canton",
      str_detect(outlet_aux, "puntos suspensivos") ~ "puntos suspensivos",
      str_detect(outlet_aux, "frecuencia") ~ "frecuencia cad",
      str_detect(outlet_aux, "billboard") ~ "billboard", 
      str_detect(outlet_aux, "tribu") ~ "grupo tribu", 
      str_detect(outlet_aux, "enlace me") ~ "enlace mesoamerica", 
      str_detect(outlet_aux, "sand") ~ "sandraaguileracom", 
      str_detect(outlet_aux, "postdata|posdata") ~ "revista posdata",
      str_detect(outlet_aux, "youtube") ~ "eli tv oficial", 
      str_detect(outlet_aux, "voces|club") ~ "voces del periodista", 
      str_detect(outlet_aux, "tijuana comunica") ~ "mexico comunica", 
      str_detect(outlet_aux, "canal 5") ~ "canal 5 tv cozumel", 
      str_detect(outlet_aux, "capital 21") ~ "capital 21", 
      str_detect(outlet_aux, "canal 13|albavision") ~ "albavision", 
      str_detect(outlet_aux, "enfoque noticias|nrm") ~ "enfoque noticias",
      str_detect(outlet_aux, "red perio") ~ "red periodistica de puerto vallarta",
      str_detect(outlet_aux, "nopal") ~ "nopal times",
      TRUE ~ outlet_aux
    ))

if (interactive()) View(inspect_names("minuto|angeles|chiapas", "outlet"))
if (interactive()) View(inspect_names("cristina", "reporter"))

df <- df %>%
  mutate(reporter_aux = ifelse(is.na(reporter_aux) == T, '', reporter_aux)) |>
  mutate(
    outlet_aux = ifelse(str_detect(reporter_aux, "victor barcenas") == T, 
                        'radio educacion', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "lizbeth") == T, 
                        'sem mexico', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "juan felipe") == T, 
                        'desde la frontera', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "lozada") == T, 
                        'maxima fm', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "janet galindo") == T, 
                        'grupo transmedia la chispa', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "alejandro patron") == T, 
                        'medios digitales del pacifico', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "federico la mont") == T, 
                        'asi lo dice la mont', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "adrian esquivel") == T, 
                        'enlace 13 television', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "zujey") == T, 
                        'tiempo y espacio', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "olga ojeda") == T, 
                        'imagen del golfo', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "yesenia") == T, 
                        'business energy', outlet_aux), 
    outlet_aux = ifelse(str_detect(reporter_aux, "shaila") == T, 
                        'healy', outlet_aux), 
    outlet_aux = ifelse(str_detect(reporter_aux, "reyna|haydee") == T, 
                        'reyna haydee (independiente)', outlet_aux), 
    outlet_aux = ifelse(str_detect(reporter_aux, "dalila escobar") == T, 
                        'proceso', outlet_aux), 
    outlet_aux = ifelse(str_detect(reporter_aux, "luis guillermo") == T, 
                        'luis guillermo hernandez sexta w', outlet_aux), 
    outlet_aux = ifelse(str_detect(reporter_aux, "ramon ramirez") == T, 
                        'noticias el reloj de la tlaxiaquena', outlet_aux), 
    outlet_aux = ifelse(str_detect(reporter_aux, "meme yamel") == T, 
                        'the mexico news', outlet_aux)
  )

df <- df %>%
  mutate(
    outlet_aux = ifelse(str_detect(reporter_aux, "tere") == T & 
                          str_detect(reporter_aux, "canal 44") == T, 
                        'canales norte (tijuana, juarez, etc)', outlet_aux), 
    outlet_aux = ifelse(str_detect(reporter_aux, "demian") == T & 
                          is.na(outlet_aux) == T, 
                        'lobos cadena 7', outlet_aux)
  )


dfna <- df |> filter(is.na(outlet_aux) == T)
###################################################
# OPTIONAL: evidence-specific corrections (date + source row)
###################################################
# Prefer a specific source record to a blanket reassignment by reporter.
# A journalist can genuinely represent several outlets or change affiliation.
# df <- df |> mutate(outlet_aux = case_when(
#   date == as.Date("YYYY-MM-DD") & source_row == 123L ~ "verified outlet",
#   TRUE ~ outlet_aux
# ))

# # Use normalized lowercase targets consistently; keep missing identities NA.
# stopifnot(!any(df$outlet_aux == "", na.rm = TRUE),
#           !any(df$reporter_aux == "", na.rm = TRUE),
#           identical(is.na(df$reporter_aux), is.na(raw$reporter_aux)),
#           identical(is.na(df$outlet_aux), is.na(raw$outlet_aux)))

changed_rows <- df |>
  filter(coalesce(outlet_aux != outlet_aux_before, FALSE) |
           coalesce(reporter_aux != reporter_aux_before, FALSE))
alias_audit <- changed_rows |>
  count(reporter_aux_before, reporter_aux, outlet_aux_before, outlet_aux,
        name = "n_records", sort = TRUE)

# Preserve all mapped rows separately, then deduplicate the corrected keys.
# Raw reporter/outlet columns stay as-transcribed; use *_aux for analysis.
df <- df |>
  group_by(date, reporter_aux, outlet_aux) |>
  mutate(n_source_records = n(),
         source_record_ids = paste(sort(record_id), collapse = ";")) |>
  ungroup()
collapsed_rows <- df |> filter(n_source_records > 1L) |>
  arrange(date, reporter_aux, outlet_aux, record_id)
df_dedup <- df |>
  arrange(date, source_row, record_id) |>
  distinct(date, reporter_aux, outlet_aux, .keep_all = TRUE)

count_units <- function(x, stage) {
  tibble(stage = stage, records = nrow(x),
         reporter_forms = n_distinct(x$reporter_aux, na.rm = TRUE),
         outlet_labels = n_distinct(x$outlet_aux, na.rm = TRUE),
         reporter_days = x |> filter(!is.na(reporter_aux)) |>
           distinct(date, reporter_aux) |> nrow(),
         outlet_days = x |> filter(!is.na(outlet_aux)) |>
           distinct(date, outlet_aux) |> nrow())
}
before_after <- bind_rows(count_units(raw, "Before"), count_units(df_dedup, "After"))
print(before_after)
print(candidate_pairs, n = Inf, width = 120)

name_table_after <- df_dedup |>
  group_by(outlet_aux) |>
  summarise(n_days = n_distinct(date), .groups = "drop") |>
  arrange(desc(n_days))

if (WRITE_OUTPUT) {
  # Separate outputs: the original 602-record export is never overwritten.
  # The mapped-records table preserves evidence from every collapsed record.
  write_parquet(df, file.path(pfo, "journalist_media_mapped_records.parquet"))
  write_parquet(df_dedup, file.path(pfo, "periodistas_v2_all_years_dedup.parquet"))
  write_csv(df_dedup, file.path(pfo, "journalists_and_media_dedup.csv"))
  write_csv(alias_audit, file.path(pfo, "manual_alias_audit.csv"))
  write_csv(before_after, file.path(pfo, "manual_dedup_counts.csv"))
  message("Saved reviewed outputs under ", pfo)
} else {
  message("Review mode: no data files written. Edit mappings, then set WRITE_OUTPUT <- TRUE.")
}

# Familiar AMLO-style checks:
# check  <- name_table_after |> filter(str_detect(outlet_aux, "once"))
# check2 <- name_table_after |> filter(str_detect(reporter_aux, "tere mora"))
# View(changed_rows)
# View(collapsed_rows)

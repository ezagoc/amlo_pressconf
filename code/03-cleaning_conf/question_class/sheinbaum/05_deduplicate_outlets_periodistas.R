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
DATA_VERSION <- "official_latest" # alternatives: "official_full", "api_full", "original_reviewed"
OFFICIAL_THROUGH <- "2026-10-15" # completed 503-conference snapshot

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
stopifnot(DATA_VERSION %in% c("official_latest", "official_full", "api_full", "original_reviewed"))
pfo <- if (DATA_VERSION == "official_latest") {
  latest <- media_path("data", "02-conferences-sheinbaum", "api_extraction",
                       paste0("official-through-", OFFICIAL_THROUGH), "auxiliar")
  if (!file.exists(file.path(latest, "periodistas_v2_all_years.parquet"))) {
    stop("The selected expanded extraction has not finished. Use official_full for the original 221 dates.")
  }
  latest
} else if (DATA_VERSION == "official_full") {
  media_path("data", "02-conferences-sheinbaum", "api_extraction", "official-full", "auxiliar")
} else if (DATA_VERSION == "api_full") {
  media_path("data", "02-conferences-sheinbaum", "api_extraction", "full", "auxiliar")
} else {
  media_path("data", "02-conferences-sheinbaum", "auxiliar")
}
message("Reviewing ", DATA_VERSION, " data in ", pfo)

# Labels first observed in the expanded corpus; no automatic alias assignments.
new_labels_for_review <- if (file.exists(file.path(pfo, "new_labels_for_manual_review.csv"))) {
  read_csv(file.path(pfo, "new_labels_for_manual_review.csv"), show_col_types = FALSE)
} else {
  tibble()
}
# View(new_labels_for_review)

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

# Remaining outlet decisions: these are NOT active merge rules. Similar labels,
# a shared reporter, or an explicit parent group do not set the analysis unit.
outlet_review_pending <- tribble(
  ~labels, ~reason,
  "enfoque (Esau Gonzalez) | enfoque noticias", "Mara Rivera's short Enfoque label is resolved below; Esau Gonzalez also states Enfoque alongside Notus in Guanajuato. Verify that outlet separately.",
  "imagen informativa cancun | grupo imagen", "The introduction explicitly says Grupo Imagen Radio; decide whether this program should use the parent-group category.",
  "culturas 22 | canal 22", "Explicitly identified as Canal 22's newscast; decide program-level versus channel-level counting.",
  "el horizonte | el horizonte de baja california sur", "Both introduced by Santiago de Llano; geographic qualification needs verification before a blanket merge.",
  "canal red | diario red latinoamerica", "Ricardo Perez states both; television channel versus newspaper requires a grouping decision.",
  "24 horas quintana roo | diario 24 horas", "Verified regional edition at https://www.24-horas.mx/qroo/; grouping question pending.",
  "1045 noticias | relax", "Oscar Gonzalez explicitly calls 104.5 Noticias their program at Radio Relax (2025-12-11); grouping question pending.",
  "hidalgo noticias | radio y television de hidalgo", "Flor Ivonne Hernandez explicitly introduces the RTH newscast (2025-01-10). It is not Hidalgo News; program grouping question pending.",
  "la grande de tabasco | grupo vx", "Same introduction and publisher identity: https://apps.apple.com/us/app/grupo-vx/id1545643441 ; grouping question pending.",
  "esto | el sudcaliforniano | oem mexico", "OEM titles; https://www.linkedin.com/company/organizacioneditorialmexicana . Grouping question pending; affiliations retained as stated in transcript.",
  "cultura colectiva | ecosfera | el fildeo | grupo tribu", "Cristian Galarza explicitly states Grupo Tribu in both 2025-02-21 and 2025-03-13 introductions; grouping question pending.",
  "la verdad | raichali | libera radio | politica y rock radio", "2025-11-14 row 520: Reyna lists places where she publishes (rows 510-522), but extraction missed her name. Apply existing independent grouping only after user decision; do not treat these as unrelated outlet mentions.",
  "el momento | el momento chiapas", "Regional brand relationship suggested by https://elmomentochiapas.mx/directorio/; no merge applied.",
  "ecos de la meseta | ecos de michoacan", "Same reporter, Manuel Morales Ordaz; not enough evidence that these are the same title.",
  "notisur | olmeca multimedios", "Publisher relationship at https://olmecamultimedios.com.mx/; Notisur/Diario Notisur alias resolved, parent-group aggregation not applied.",
  "stereo cien | enfoque noticias", "Possible NRM group aggregation, not a spelling alias; retain distinct without a grouping decision.",
  "revista migrante | noticiero en redes", "Hans Salazar mentions both projects; shared journalist does not establish an alias.",
  "tv migrante | canal 14 spr", "Verified SPR channel: https://www.spr.gob.mx/comunicados/2022/comunicado26.html . Could extend the existing SPR/Altavoz grouping; no merge applied.",
  "radio publica", "Generic Chicago affiliation; do not infer a specific station from the reporter's other outlet."
)
# View(outlet_review_pending)
# AP Noticias remains separate from Associated Press: no verified affiliation.
# LJA is not merged with La Jornada based only on its historical name: the UAA
# study reports that it ended that franchise relationship.
# https://libros.uaa.mx/uaa/catalog/download/156/146/695?inline=1
# KSDY Canal 50 and Sintesis TV have an affiliation agreement, not proven identity:
# https://ksdy50.com/about-us/ . Keep both, and never map Canal 50 to Canal 5.
# Example: View(inspect_names("once|tiempocommx", "outlet"))
# Example: View(inspect_names("tere mora|citlal", "reporter"))

df <- raw |>
  mutate(
    outlet_aux_before = outlet_aux,
    reporter_aux_before = reporter_aux,
    outlet_aux = case_when(
      is.na(outlet_aux) ~ NA_character_,
      outlet_aux %in% c("neurona digital noticias", "neuronadigitalcom",
                        "neuronadigitalnoticiascom") ~ "neurona digital noticias",
      # Additional spelling, website and shortened-name variants checked against
      # the stated introductions in the official corpus (2026-10-19).
      # Rare-label review: same introduction bundle for Claudia Reina/Reyna.
      outlet_aux %in% c("el noreste", "el portal del noreste") ~ "el portal del noreste",
      # Misael Habana's Acapulco program: official Audiorama schedule confirms name.
      # https://audiorama.mx/estacion/vida-acapulco-89-7-fm
      outlet_aux %in% c("acapulco al tanto", "al tanto guerrero") ~ "al tanto guerrero",
      # Newspaper's own site uses both forms; retain Olmeca Multimedios separately.
      # https://olmecamultimedios.com.mx/2026/05/25/reconocen-labor-de-periodistas-del-sur/
      outlet_aux %in% c("notisur", "diario notisur") ~ "diario notisur",
      # Same station in Carlos Rosanoff's introduction and the INE station catalog.
      # https://repositoriodocumental.ine.mx/xmlui/bitstream/handle/123456789/152299/CGex202307-07-ap-1-a2.pdf
      outlet_aux %in% c("canal 6 bajio", "multimedios television bajio") ~ "multimedios television bajio",
      outlet_aux %in% c("afp", "agencia francepresse") ~ "afp",
      outlet_aux %in% c("alcanzado el conocimiento", "alcanzando el conocimiento") ~ "alcanzando el conocimiento",
      # User confirmed one ACI outlet across Hidalgo and Mexico labels.
      outlet_aux %in% c("aci de hidalgo", "aci hidalgo", "acid de hidalgo",
                        "aci de mexico", "aci mexico", "aci") ~ "aci",
      outlet_aux %in% c("asi lo dice la mont", "asi lo dice lamont") ~ "asi lo dice la mont",
      outlet_aux %in% c("el mexicano", "el mexicano diario regional de baja california") ~ "el mexicano",
      # User confirmed aggregation of Jorge Franco's El Diario regional titles.
      outlet_aux %in% c("el diario", "el diario de chihuahua", "el diario de juarez",
                        "el diario de el paso") ~ "el diario",
      outlet_aux %in% c("enfoque oportuno", "enfoqueoportunocom") ~ "enfoque oportuno",
      outlet_aux %in% c("enlace 13", "enlace 13 television") ~ "enlace 13 television",
      outlet_aux %in% c("fusion latina chicago", "fundacion fusion latina chicago") ~ "fusion latina chicago",
      outlet_aux %in% c("fortuna", "revista fortuna") ~ "revista fortuna",
      outlet_aux %in% c("hidalgo news", "hidalgonewsmx") ~ "mexico news world",
      outlet_aux %in% c("la orquesta", "la orquesta mx") ~ "la orquesta mx",
      outlet_aux %in% c("la pancarta", "la pancarta de quintana roo") ~ "la pancarta de quintana roo",
      outlet_aux %in% c("nbc", "nbc news") ~ "nbc news",
      outlet_aux %in% c("radio hit la explosiva", "radio hit la xplosiva") ~ "radio hit la xplosiva",
      outlet_aux %in% c("radio tosepan", "radio tosepan limakxtum") ~ "radio tosepan limakxtum",
      # User confirmed Seguridad Informa belongs in the Sin Linea category.
      outlet_aux %in% c("seguridad informa", "seguridad informa de grupo sin linea") ~ "sin linea",
      outlet_aux %in% c("siker", "sikercom") ~ "siker",
      outlet_aux %in% c("sonora power", "sonorapowercom") ~ "sonora power",
      outlet_aux %in% c("teleurban", "grupo teleurban", "tele urban", "grupo tele urban") ~ "teleurban",
      outlet_aux %in% c("revista zocalo", "zocalo") ~ "revista zocalo",
      outlet_aux %in% c("red america latina", "canal red", "red latinoamerica") ~ "diario red latinoamerica",
      # The bare names are ambiguous; use only the stated introduction context.
      outlet_aux == "enfoque" & reporter_aux == "mara rivera" ~ "enfoque noticias",
      outlet_aux == "canal 44" &
        str_detect(str_to_lower(evidence_text), "universidad de guadalajara") ~ "universidad de guadalajara",
      outlet_aux == "canal 44" &
        str_detect(str_to_lower(evidence_text), "ciudad ju[aá]rez|grupo intermedia") ~ "canales norte (tijuana, juarez, etc)",
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
      outlet_aux %in% c("debate", "el debate", "el debate de sinaloa") ~ "debate",
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
      outlet_aux %in% c("la razon", "periodico la razon", "la razon de mexico") ~ "la razon",
      outlet_aux %in% c("perspectivasmx", "perspectivas mx", "perspectivas") ~ "perspectivas",
      outlet_aux %in% c("noticias del movimiento conciencia",
                        "noticias del movimiento consciencia") ~ "movimiento conciencia",
      outlet_aux %in% c("el centinela informa", "centinela informa", "el centinela") ~ "el centinela informa",
      outlet_aux %in% c("noticiero en redes") ~ "noticiero en redes",
      outlet_aux %in% c("eli tv oficial", "eli") ~ "eli tv oficial",
      outlet_aux %in% c("bajo palabra") ~ "bajo palabra",
      outlet_aux %in% c("canal 14 spr", "spr canal 14", "canal 14", "spr", "sistema publico",
                        "sistema publico de radiodifusion",
                        "sistema publico de radiodifusion del estado mexicano",
                        "altavoz radio",
                        "altavoz radio del sistema publico de radiodifusion del estado mexicano")  ~ "canal 14 spr",
      outlet_aux %in% c("medios digitales del pacifico", "agencia de medios digitales del pacifico",
                        "mdp medios del pacifico",
                        "el reportero urbano", "medio digitales del pacifico", "mdp", "medios del pacifico",
                         "julioomargscom") ~ "medios digitales del pacifico",
      outlet_aux %in% c("los reporteros mx", "reporteros mx", "reporterosmx", "elquintanaroomx",
                        "quintana roo mx", "reporteros mx",
                        "quintanaroomx", "el quintana roo mx") ~ "losreporterosmx",
      outlet_aux %in% c("codigolibremx",  "codigo libre") ~ "codigo libre",
      outlet_aux %in% c("agencia ap",  "ap", "ap noticias") ~ "associated press",
      outlet_aux %in% c("polemon", "revista polemon") ~ "polemon",
      outlet_aux %in% c("grupo transmedia", "la chispa",
                        "grupo transmedia la chispa") ~ "grupo transmedia la chispa",
      outlet_aux %in% c("el imparcial", "grupo healy", "la cronica",
                        "frontera", "la cronica de mexicali") ~ "healy",
      outlet_aux %in% c("el sol de mexico") ~ "oem mexico",
      outlet_aux %in% c("business energy", "gaceta business energy",
                        "gaceta petrolera de tabasco") ~ "business energy", #Yesenia Peralta -> business energy
      outlet_aux %in% c("pie de pagina", "raichali") ~ "alianza de medios independientes",
      outlet_aux %in% c("sin censura", "sin censura tv") ~ "sin censura",
      outlet_aux %in% c("lm noticias", "informativo lm", "lord molecula",
                        "lord molecula oficial", "lm news", "lm noticias lord molecula") ~ "lord molecula oficial",
      outlet_aux %in% c("diario red") ~ "diario red latinoamerica",
      outlet_aux %in% c("vanguardia veracruz", "vanguardia") ~ "mmm vanguardia",
      outlet_aux %in% c("sin linea", "sin linea mx", "grupo sin linea") ~ "sin linea",
      # User-approved analysis unit (2026-10-24): Olvera's newspaper and channel.
      # Original outlet/evidence fields remain unchanged; deduplication follows below.
      outlet_aux %in% c("mexico news world", "mexico network", "news world", "mexiconetwork",
                        "hidalgo news", "marco olvera oficial", "marco antonio olvera oficial") ~ "mexico news world",
      outlet_aux %in% c("w radio") ~ "w radio",
      outlet_aux %in% c("puentelibremx", "puente libre", "puentelibre mx") ~ "puente libre mx",
      outlet_aux %in% c("miled mexico", "radio miled", "grupo miled",
                        "grupo stereo miled", "super stereo miled", "radio millet") ~ "miled",
      outlet_aux %in% c("amarc", "asociacion mundial de radios comunitarias",
                        "radio tepoztlan") ~ "amarc",
      outlet_aux %in% c("agencia sputnik", "sputnik") ~ "sputnik",
      outlet_aux %in% c("sonora power", "telemax", "noticias telemax") ~ "sonora power",
      outlet_aux %in% c("politica y rock and roll", "politica y rock and roll radio",
                        "politica de rock and roll radio") ~ "politica y rock radio",
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
                        "imagen radio", "grupo imagen mexicali") ~ "grupo imagen",
      outlet_aux %in% c("fm", "la poderosa", "radio resultados",
                        'la poderosa 953 fm') ~ "radio resultados",
    # User-approved 2026-10-26: same analysis outlet as Sin Linea.
    # The final date/reporter/outlet dedup collapses introductions naming both.
    outlet_aux %in% c("el politico", "el politico en las redes", "revista el politico", "revistaelpolitico.com") ~ "sin linea",
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
      # Match POPLab itself; "pop" also matched the distinct newspaper El Popular.
      str_detect(outlet_aux, "^poplab$|^laboratorio de periodismo y opinion publica") ~ "laboratorio de periodismo y opinion publica",
      str_detect(outlet_aux, "jornada") ~ "la jornada",
      str_detect(outlet_aux, "excelsior") ~ "excelsior",
      # Flor Ivonne's Hidalgo Noticias is RTH's newscast, not Hidalgo News.
      str_detect(outlet_aux, "hidalgo news") ~ "mexico news world",
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
      str_detect(outlet_aux, "puntos suspensivos|suspensivos") ~ "puntos suspensivos",
      str_detect(outlet_aux, "amarc|radios comunitarias") ~ "amarc",
      outlet_aux %in% c("frecuencia cad", "frecuenciacad", "frecuenciacadcom",
                        "frecuencia cadcom") ~ "frecuencia cad",
      str_detect(outlet_aux, "billboard") ~ "billboard",
      str_detect(outlet_aux, "tribu") ~ "grupo tribu",
      str_detect(outlet_aux, "enlace me") ~ "enlace mesoamerica",
      str_detect(outlet_aux, "sand") ~ "sandraaguileracom",
      str_detect(outlet_aux, "postdata|posdata") ~ "revista posdata",
      str_detect(outlet_aux, "youtube") ~ "eli tv oficial",
      str_detect(outlet_aux, "voces|club") ~ "voces del periodista",
      str_detect(outlet_aux, "tijuana comunica") ~ "mexico comunica",
      str_detect(outlet_aux, "^canal 5($| )") ~ "canal 5 tv cozumel",
      str_detect(outlet_aux, "capital 21") ~ "capital 21",
      str_detect(outlet_aux, "canal 13|albavision") ~ "albavision",
      str_detect(outlet_aux, "enfoque noticias|nrm") ~ "enfoque noticias",
      str_detect(outlet_aux, "red perio") ~ "red periodistica de puerto vallarta",
      str_detect(outlet_aux, "nopal") ~ "nopal times",
      str_detect(outlet_aux, "quadratin") ~ "quadratin",
      str_detect(outlet_aux, "esahora") ~ "es ahora am",
      str_detect(outlet_aux, "quatro|cuatromedia|cuatro media|avan") ~ "avan noticias",
      str_detect(outlet_aux, "mvs") ~ "mvs noticias",
      str_detect(outlet_aux, "el universal") ~ "el universal",
      str_detect(outlet_aux, "24 horas") ~ "diario 24 horas",
      str_detect(outlet_aux, "azteca") ~ "tv azteca",
      str_detect(outlet_aux, "diario red|red latino") ~ "diario red latinoamerica",
      str_detect(outlet_aux, "formula") ~ "grupo formula",
      str_detect(outlet_aux, "posta") ~ "posta",
      str_detect(outlet_aux, "agua quemada|aguaquemada") ~ "agua quemada",
      str_detect(outlet_aux, "ahora noticias") ~ "ahora tabasco",
      str_detect(outlet_aux, "alerta multi") ~ "alerta multimedia",
      str_detect(outlet_aux, "financiero") ~ "el financiero",
      str_detect(outlet_aux, "10am|10ammx|10 am") ~ "10 am mx",
      # User confirmed this grouping directly in outlet_aux for attendance.
      str_detect(outlet_aux, "chiwas|chivas") ~ "efecto colateral",
      str_detect(outlet_aux, "efecto colateral") ~ "efecto colateral",
      str_detect(outlet_aux, "subjetivo") ~ "subjetivo mx",
      str_detect(outlet_aux, "heraldo") ~ "el heraldo",
      str_detect(outlet_aux, "dime") ~ "dime noticias",
      str_detect(outlet_aux, "1045") ~ "relax",
      str_detect(outlet_aux, "agora") ~ "agora digital",
      str_detect(outlet_aux, "radiorama") ~ "radiorama",
      str_detect(outlet_aux, "el horizonte") ~ "el horizonte",
      str_detect(outlet_aux, "debate") ~ "el debate",
      str_detect(outlet_aux, "notisur") ~ "notisur",
      str_detect(outlet_aux, "ecos de michoacan|ecos de la meseta") ~ "ecos de michoacan",
      str_detect(outlet_aux, "el momento") ~ "el momento",
      TRUE ~ outlet_aux
    ))

if (interactive()) View(inspect_names("puente", "outlet"))
if (interactive()) View(inspect_names("yusbel", "reporter"))

df <- df %>%
  mutate(reporter_aux = ifelse(is.na(reporter_aux) == T, '', reporter_aux)) |>
  mutate(
    outlet_aux = ifelse(str_detect(reporter_aux, "victor barcenas") == T,
                        'radio educacion', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "yusbel") == T,
                        'codigo libre', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "amanda") == T,
                        'pridemx', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "laura avila") == T,
                        'posta', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "vicente serrano") == T,
                        'sin censura', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "juan bautista") == T,
                        'voces del periodista', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "yulia") == T,
                        'la razon', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "carlos padilla") == T,
                        'revista zocalo', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "saul santana") == T,
                        'diario plaza juarez', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "zosimo") == T,
                        'luces del siglo', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "daniel robles") == T,
                        'yo tambien', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "mariana madrid") == T,
                        'albavision', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "carlos guzman") == T,
                        'avan noticias', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "norma") == T,
                        'miled', outlet_aux),
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
    # User confirmed the same outlet assignment for these La Mont variants.
    outlet_aux = ifelse(reporter_aux %in% c("federico la mont", "federico lamont",
                                           "lamont", "la mont"),
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
    # Claudia Reyna is a different reporter; retain her stated affiliations.
    outlet_aux = ifelse(reporter_aux %in% c("haydee ramirez", "reyna haydee ramirez",
                                           "reyna haydee ramirez hernandez"),
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
                          str_detect(outlet_aux, "^canal 44$") == T,
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

# BEGIN flagged outlet corrections 2026-10-26
# Restore distinct identities before preserving each brand.
df <- df |> mutate(outlet_aux = case_when(
  outlet_aux_before == "ap noticias" ~ "ap noticias",
  outlet_aux_before %in% c("bloomberg linea", "bloomberg news", "bloomberg") ~ outlet_aux_before,
  reporter_aux == "gabriela montejano" & outlet_aux_before == "agora" ~ "agora celaya",
  reporter_aux == "abel cuapa" & outlet_aux_before == "capital" ~ "capital puebla",
  TRUE ~ outlet_aux))
# END flagged outlet corrections 2026-10-26

# Keep the brands visible while combining their conference records (2026-10-26).
df <- df |>
  mutate(reporter_aux = if_else(reporter_aux == "alberto marroquin espinosa",
                               "alberto marroquin espinoza", reporter_aux),
         outlet_brand_aux = outlet_aux,
         outlet_aux = case_when(
           outlet_aux == "puente libre mx" ~ "tiempo la noticia digital",
           outlet_aux == "teleurban" ~ "w radio", # approved 2026-10-26
           outlet_aux %in% c("frecuencia cad", "es ahora am") ~ "jaime farias informa",
           outlet_aux == "empuje migrante" ~ "oro solido", # approved 2026-10-26
           # BEGIN approved flagged groups 2026-10-26
           outlet_aux %in% c("sin puntos ni comas") ~ "medios digitales del pacifico",
           outlet_aux %in% c("animales con derechos", "sendero de la luna") ~ "movimiento conciencia",
           outlet_aux %in% c("lobos cadena 7") ~ "sonora power",
           outlet_aux %in% c("alerta multimedia") ~ "comunicante mx",
           outlet_aux %in% c("los tubos", "revista posdata", "el portal del noreste") ~ "agua quemada",
           outlet_aux %in% c("cultura colectiva", "ecosfera", "el fildeo") ~ "grupo tribu",
           outlet_aux %in% c("excelsior") ~ "grupo imagen",
           outlet_aux %in% c("poder mexico") ~ "global energy",
           outlet_aux %in% c("el chapucero") ~ "efecto colateral",
           outlet_aux %in% c("red periodistica de puerto vallarta") ~ "universidad de guadalajara",
           outlet_aux %in% c("politica y rock radio") ~ "amarc",
           outlet_aux %in% c("el regreso de donald trump") ~ "alcanzando el conocimiento",
           outlet_aux %in% c("el charro politico") ~ "nopal times",
           outlet_aux %in% c("bloomberg news", "bloomberg linea") ~ "el financiero",
           outlet_aux %in% c("asi lo dice la mont", "abc radio", "grupo audiorama comunicaciones") ~ "audiorama",
           # END approved flagged groups 2026-10-26
           TRUE ~ outlet_aux))

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
  mutate(outlet_brands = paste(sort(unique(outlet_brand_aux[!is.na(outlet_brand_aux)])), collapse = " | "),
         n_source_records = n(),
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

# Rare outlets after the current rules: appearances mean distinct conference
# dates, not source rows. Use the evidence table to check every identification.
rare_outlet_table <- df |>
  filter(!is.na(outlet_aux)) |>
  group_by(outlet_aux) |>
  summarise(n_days = n_distinct(date), n_records = n(),
            dates = paste(sort(unique(date)), collapse = "; "),
            reporters = paste(sort(unique(reporter_aux[nzchar(reporter_aux)])), collapse = " | "),
            extracted_labels = paste(sort(unique(outlet_aux_before)), collapse = " | "),
            .groups = "drop") |>
  filter(n_days <= 2L) |>
  arrange(n_days, outlet_aux)
rare_outlet_evidence <- df |>
  semi_join(rare_outlet_table, by = "outlet_aux") |>
  select(outlet_aux, outlet_aux_before, date, reporter, reporter_aux,
         source_rows, evidence_text, source_url, record_id) |>
  arrange(outlet_aux, date, record_id)
# View(rare_outlet_table)
# View(rare_outlet_evidence)

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

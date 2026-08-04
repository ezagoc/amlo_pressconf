###################################################
## Export: photo list + unidentified-question dates
## Author: Eduardo Zago-Cuevas
## Run after: 05_deduplicate_outlets_periodistas.R
##
## Sheet 1 – "periodistas_foto":
##   One row per unique reporter_aux × outlet_aux pair
##   with an example date where they asked a pregunta.
##
## Sheet 2 – "sin_nombre_o_medio":
##   Two sources combined:
##   (a) Preguntas in questions_dataset where reporter_aux or outlet_aux
##       is blank after all dedup cleaning.
##   (b) Every (date, reporter_aux) in questions_failed.csv — these are
##       journalists that were in the periodistas list but whose name
##       was NOT FOUND in the raw transcript (or transcript was missing /
##       GPT failed), joined back to periodistas for outlet info.
###################################################

pacman::p_load(tidyverse, arrow, openxlsx)

rm(list = ls())
rstudioapi::getActiveDocumentContext
setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
source("../../../project_paths.R")

pfo     <- paste0(media_path('data', '02-conferences', 'auxiliar'), '/')
res_dir <- paste0(dirname(media_output_path('results', 'descriptives', '.keep')), '/')
dir.create(res_dir, recursive = TRUE, showWarnings = FALSE)

# ── 1. Deduplicated dataset (already cleaned) ─────────────────────────────────

df_dedup <- read_parquet(paste0(pfo, 'questions_dataset_dedup.parquet')) |>
  mutate(date = as.Date(date))

# Sheet 1: one example date per reporter × outlet, preguntas only
sheet1 <- df_dedup |>
  filter(item_type == 'pregunta') |>
  group_by(reporter_aux, outlet_aux) |>
  summarise(
    n_preguntas  = n(),
    n_dias       = n_distinct(date),
    ejemplo_fecha = min(date),         # earliest date as canonical example
    .groups = 'drop'
  ) |>
  arrange(outlet_aux, reporter_aux)

# ── 2. Raw dataset – find questions with no name / no newspaper ───────────────

df_raw <- read_parquet(paste0(pfo, 'questions_dataset.parquet')) |>
  mutate(date = as.Date(date))

# Apply the same outlet_aux normalisation from script 05
df_raw <- df_raw %>%
  mutate(
    outlet_aux = case_when(
      str_detect(outlet_aux, "diario basta|canton|tabasco hoy|quintana roo hoy|basta") ~ "grupo canton",
      str_detect(outlet_aux, "jaime farias|jf informa") ~ "jaime farias informa",
      str_detect(outlet_aux, "periodico imagen|corporativo imagen|imagen de ver") ~ "imagen del golfo",
      str_detect(outlet_aux, "frecuencia magica") ~ "891 frec magica",
      str_detect(outlet_aux, "frecuencia") ~ "frecuencia cad",
      str_detect(outlet_aux, "financiero|bloomberg") ~ "el financiero",
      str_detect(outlet_aux, "healy|imparcial|frontera|cronica") ~ "healy",
      str_detect(outlet_aux, "contralinea") ~ "contralinea",
      str_detect(outlet_aux, "jornada") ~ "la jornada",
      str_detect(outlet_aux, "proceso") ~ "proceso",
      str_detect(outlet_aux, "sdp|analisis economico") ~ "sdpnoticias",
      str_detect(outlet_aux, "formula") ~ "grupo formula",
      str_detect(outlet_aux, "ahora") ~ "es ahora am",
      str_detect(outlet_aux, "azteca|adn 40") ~ "tv azteca",
      str_detect(outlet_aux, "sol de|organizacion editorial") ~ "oem mexico",
      str_detect(outlet_aux, "elefante") ~ "elefante blanco",
      str_detect(outlet_aux, "sputnik") ~ "sputnik",
      str_detect(outlet_aux, "mvs") ~ "mvs noticias",
      str_detect(outlet_aux, "imer|instituto mexicano") ~ "imer",
      str_detect(outlet_aux, "tiempotv|tiempo tv") ~ "a tiempo tv",
      str_detect(outlet_aux, "tiempocom") ~ "tiempo la noticia digital",
      str_detect(outlet_aux, "unomasuno|uno mas uno") ~ "uno mas uno",
      str_detect(outlet_aux, "mexico news") ~ "the mexico news",
      str_detect(outlet_aux, "amarc|red de radios") ~ "amarc",
      str_detect(outlet_aux, "rock|politica") ~ "politica y rock radio",
      str_detect(outlet_aux, "sonora power") ~ "sonora power",
      str_detect(outlet_aux, "radio sonora") ~ "radio sonora",
      str_detect(outlet_aux, "telemax") ~ "telemax",
      str_detect(outlet_aux, "proyecto puente") ~ "proyecto puente",
      str_detect(outlet_aux, "molecula") ~ "lord molecula oficial",
      str_detect(outlet_aux, "petroleo y energia|revista pe") ~ "petroleo y energia",
      str_detect(outlet_aux, "lideres mexicanos|lideres") ~ "lideres mexicanos",
      str_detect(outlet_aux, "radiorama") ~ "grupo radiorama",
      str_detect(outlet_aux, "vanguardia") ~ "mmm vanguardia",
      str_detect(outlet_aux, "sin censura") ~ "sin censura",
      str_detect(outlet_aux, "informando") ~ "informando la transformacion",
      str_detect(outlet_aux, "abc") ~ "abc",
      str_detect(outlet_aux, "business") ~ "business energy",
      str_detect(outlet_aux, "sin linea|sinlinea") ~ "sin linea",
      str_detect(outlet_aux, "w radio|wradio") ~ "w radio",
      str_detect(outlet_aux, "enfoque") ~ "enfoque noticias",
      str_detect(outlet_aux, "el lead") ~ "el lead",
      str_detect(outlet_aux, "heraldo") ~ "el heraldo",
      str_detect(outlet_aux, "noreste") ~ "noreste",
      str_detect(outlet_aux, "24 horas") ~ "diario 24 horas",
      str_detect(outlet_aux, "canal 73|cnr") ~ "cnr canal 73",
      str_detect(outlet_aux, "polemon") ~ "polemon",
      str_detect(outlet_aux, "medios digitales") ~ "medios digitales del pacifico",
      str_detect(outlet_aux, "canal 14|spr") ~ "canal 14 spr",
      str_detect(outlet_aux, "codigo") ~ "codigo libre",
      str_detect(outlet_aux, "quintana roo mx|quintanaroomx") ~ "quintana roo mx",
      str_detect(outlet_aux, "quadratin") ~ "quadratin",
      str_detect(outlet_aux, "zmg") ~ "trafico zmg",
      str_detect(outlet_aux, "reportero urbano") ~ "reportero urbano",
      str_detect(outlet_aux, "noticias del movimiento") ~ "movimiento conciencia",
      str_detect(outlet_aux, "noticiero en redes|noticieros en redes") ~ "noticiero en redes",
      str_detect(outlet_aux, "bajo palabra") ~ "bajo palabra",
      str_detect(outlet_aux, "eli tv") ~ "eli tv",
      str_detect(outlet_aux, "puente libre|puentelibre") ~ "puente libre mx",
      str_detect(outlet_aux, "marco olvera|canal de youtube") ~ "marco olvera oficial",
      str_detect(outlet_aux, "revista en|enfasis") ~ "revista enfasis",
      str_detect(outlet_aux, "verdad noticias") ~ "verdad noticias",
      str_detect(outlet_aux, "defensor") ~ "el defensor de la verdad",
      str_detect(outlet_aux, "charro") ~ "el charro politico",
      str_detect(outlet_aux, "audio") ~ "grupo audiorama",
      str_detect(outlet_aux, "perspectivas") ~ "perspectivas",
      str_detect(outlet_aux, "razon") ~ "la razon",
      str_detect(outlet_aux, "el pais") ~ "el pais",
      str_detect(outlet_aux, "relax") ~ "relax",
      str_detect(outlet_aux, "on noticias|onoticias|o noticias") ~ "on noticias",
      str_detect(outlet_aux, "sistema public|spr") ~ "canal 14 spr",
      str_detect(outlet_aux, "rompeviento") ~ "rompeviento tv",
      str_detect(outlet_aux, "canal 11|canal once") ~ "canal 11",
      str_detect(outlet_aux, "meganoticias") ~ "meganoticias",
      str_detect(outlet_aux, "reuters") ~ "reuters",
      str_detect(outlet_aux, "la mejor") ~ "la mejor noticias",
      str_detect(outlet_aux, "hctv|hotv") ~ "noticieros hctv",
      str_detect(outlet_aux, "sendero") ~ "sendero de la luna",
      str_detect(outlet_aux, "esfera") ~ "esfera noticias",
      str_detect(outlet_aux, "pie d|alianza de medios|de a pie") ~ "alianza de medios independientes",
      str_detect(outlet_aux, "despierta") ~ "despierta quintana roo",
      str_detect(outlet_aux, "indep") ~ "reportero independiente",
      str_detect(outlet_aux, "debate") ~ "debate",
      str_detect(outlet_aux, "univision") ~ "univision",
      str_detect(outlet_aux, "elias") ~ "elias medina en las redes",
      str_detect(outlet_aux, "naturopatia") ~ "naturopatia",
      TRUE ~ outlet_aux
    )
  ) %>%
  mutate(
    reporter_aux = case_when(
      str_detect(reporter_aux, "eduardo esqui") ~ "eduardo esquivel",
      str_detect(reporter_aux, "ramon ramir") ~ "ramon gutierrez",
      str_detect(reporter_aux, "hayd") ~ "reyna haydee",
      str_detect(reporter_aux, "alberto martin|alberto marroquin") ~ "alberto marroquin",
      str_detect(reporter_aux, "cedillo") ~ "diego elias cedillo",
      str_detect(reporter_aux, "dalila") ~ "dalila escobar",
      str_detect(reporter_aux, "vittor|blogs|victor buendia") ~ "victor buendia (blogs)",
      TRUE ~ reporter_aux
    )
  ) %>%
  mutate(
    outlet_aux = ifelse(str_detect(reporter_aux, "carlos guzman"),       'avan noticias',          outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "roberto cruz"),        'impacto diario',          outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "valentina peralta"),   'reportero independiente', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "frida guerrera") & outlet_aux != 'rompeviento tv', 'frida guerrera', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "juan hernandez"),      'grupo canton',            outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "amir ibrahim"),        'quintana roo mx',         outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "maria luisa estrada"), 'la grillotina',           outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "elianne"),             'eli tv',                  outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "arturo pavon"),        'el chapucero',            outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "michelle rivera"),     'grupo formula',           outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "luis guillermo|sexta w"), 'luis guillermo hernandez sexta w', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "arturo paramo"),       'grupo imagen',            outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "ramon flo"),           'el centinela informa',    outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "janet galindo|janeth galindo"), 'la chispa',     outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "diego elias cedillo"), 'grupo canton',            outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "wenceslao"),           'sin censura',             outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "luis ignacio velasquez"), 'voz e imagen de oaxaca', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "victor buendia"),      'mexico informa',          outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "ramon guti|ramon ramirez"), 'noticieros el reloj de la tlaxiaquena', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "carlos dominguez"),    'mvs noticias',            outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "carlos olvera"),       'portal guanajuato',       outlet_aux)
  ) %>%
  mutate(
    outlet_aux = ifelse(str_detect(reporter_aux, "sandra aguilera") & outlet_aux == 'grupo',
                        'ae grupo informativo', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "carlos pozos") & str_detect(outlet_aux, "outlet"),
                        'lord molecula oficial', outlet_aux)
  ) %>%
  mutate(
    outlet_aux = ifelse(str_detect(reporter_aux, "olvera") & outlet_aux == '',
                        'marco olvera oficial', outlet_aux)
  )

# ── Sheet 2a: preguntas where reporter_aux or outlet_aux is blank ─────────────

sheet2a <- df_raw |>
  filter(item_type == 'pregunta') |>
  filter(is.na(reporter_aux) | reporter_aux == '' |
         is.na(outlet_aux)   | outlet_aux   == '') |>
  mutate(
    reporter_aux = replace_na(reporter_aux, ''),
    outlet_aux   = replace_na(outlet_aux,   ''),
    reporter     = replace_na(reporter,     ''),
    outlet       = replace_na(outlet,       ''),
    motivo       = 'campo_vacio',
    text         = as.character(text)
  ) |>
  select(date, reporter, reporter_aux, outlet, outlet_aux, text, motivo)

# ── Sheet 2b: failed extractions – name not found in transcript ───────────────

periodistas <- read_parquet(paste0(pfo, 'periodistas_v2_all_years.parquet')) |>
  mutate(date = as.Date(date))

failed_raw <- read_csv(paste0(pfo, 'questions_failed.csv'), show_col_types = FALSE) |>
  separate(failed_key, into = c('date_str', 'reporter_aux_failed'),
           sep = '\\|', extra = 'merge') |>
  mutate(date = as.Date(date_str)) |>
  select(-date_str) |>
  distinct()

# Join to periodistas to recover outlet fields
sheet2b <- failed_raw |>
  left_join(
    periodistas |>
      select(date, reporter_aux, reporter, outlet, outlet_aux) |>
      distinct(),
    by = c('date' = 'date', 'reporter_aux_failed' = 'reporter_aux')
  ) |>
  mutate(
    reporter_aux = reporter_aux_failed,
    reporter     = replace_na(reporter,   ''),
    outlet       = replace_na(outlet,     ''),
    outlet_aux   = replace_na(outlet_aux, ''),
    motivo       = 'nombre_no_encontrado_en_transcript',
    text         = NA_character_
  ) |>
  select(date, reporter, reporter_aux, outlet, outlet_aux, text, motivo)

# ── Combine ───────────────────────────────────────────────────────────────────

sheet2 <- bind_rows(sheet2a, sheet2b) |>
  arrange(date, reporter_aux)

# ── 3. Write Excel ─────────────────────────────────────────────────────────────

wb <- createWorkbook()

addWorksheet(wb, 'periodistas_foto')
writeDataTable(wb, 'periodistas_foto', sheet1, tableStyle = 'TableStyleMedium2')
setColWidths(wb, 'periodistas_foto', cols = 1:5,
             widths = c(30, 30, 12, 10, 14))

addWorksheet(wb, 'sin_nombre_o_medio')
writeDataTable(wb, 'sin_nombre_o_medio', sheet2, tableStyle = 'TableStyleMedium3')
setColWidths(wb, 'sin_nombre_o_medio', cols = 1:7,
             widths = c(12, 25, 25, 25, 25, 60, 35))

out_path <- paste0(res_dir, 'foto_y_sin_nombre.xlsx')
saveWorkbook(wb, out_path, overwrite = TRUE)
cat('Saved →', out_path, '\n')
cat('Sheet 1 rows (periodistas_foto):  ', nrow(sheet1), '\n')
cat('Sheet 2 rows (sin_nombre_o_medio):', nrow(sheet2), '\n')

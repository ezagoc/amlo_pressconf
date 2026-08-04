library(tidyverse)
library(arrow)
library(stringi)
library(stringr)

if (requireNamespace("rstudioapi", quietly = TRUE)) {
  setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
}
source("../../project_paths.R")

## Read panel data 

df <- readxl::read_excel(media_path('data', '02-conferences', 'raw', 'attendance', 'merged', 'attendance_merged_dedup.xlsx'))

# Analyze the data:

df_cargo <- df |> distinct(cargo) 

## REMOVE: CAMARÓGRAFO, ESTUDIANTE, TÉCNICO, INGENIERO KU, FOTOGRAFO, AUDIO

df <- df %>%
  filter(!str_detect(cargo, "CAMARÓGRAFO|ESTUDIANTE|TÉCNICO|INGENIERO KU|FOTOGRAFO|AUDIO"))

df <- df %>%
  mutate(
    sede = str_to_lower(sede),
    sede = stri_trans_general(sede, "Latin-ASCII"),  # remove accents
    sede = str_remove_all(sede, "[,\\.]"),# remove commas and periods
    sede = str_squish(sede)
    )

df_sede <- df |> distinct(sede, fecha) |> 
  group_by(sede) |> summarise(sede_n = n()) |> ungroup() |> arrange(desc(sede_n))

# NO ISSUE HERE

library(dplyr)
library(stringr)
library(stringi)

df <- df %>%
  mutate(
    outlet_clean = medios |>
      str_to_lower() |>
      stri_trans_general("Latin-ASCII") |>
      str_replace_all("[[:punct:]]", " ") |>
      str_replace_all("\\bsa de cv\\b|\\bs a de c v\\b", " ") |>
      str_replace_all("\\btv\\b", "television") |>
      str_replace_all("\\s+", " ") |>
      str_trim()
  )

## Deduplication of outlets:

# 1. first standardize the most common ones:

gov_entities <- c('profeco', 'pemex', 'insabi', 'gobierno cdmx', 'infonavit', 
                  'loteria nacional', 'sspc', 'dif', 'gobierno del estado de mexico', 
                  'issste', 'sat', 'sedena', 'inmujeres', 'instituto politecnico nacional', 
                  'imss', 'cfe')

df <- df |> filter(!outlet_clean %in% gov_entities) |> 
  filter(!str_detect(outlet_clean, "secretaria|gobierno|ayuntamiento"))

check <- df |> filter(str_detect(medios, "ZA")) |>
  count(medios, sort = TRUE)

# To check: centinela -> human hoy and contrapeso digital, mexico informa is also vittor blogs

df <- df %>%
  mutate(outlet_clean = str_to_lower(outlet_clean)) %>%
  mutate(
    outlet_clean = case_when(
      str_detect(outlet_clean, "milenio") ~ "milenio",
      str_detect(outlet_clean, "plaza juarez") ~ "diario plaza juarez",
      str_detect(outlet_clean, "imparcial oax|imparcial oaxaca") ~ "imparcial oaxaca",
      str_detect(outlet_clean, "aljazeera|jazeera") ~ "al jazeera",
      str_detect(outlet_clean, "aristegui") ~ "aristegui noticias",
      str_detect(outlet_clean, "nvi|voz e imagen|nvinoticias|voz e i") ~ "noticias voz e imagen",
      str_detect(outlet_clean, "azteca") ~ "tv azteca",
      str_detect(outlet_clean, "noroeste") ~ "periodico noroeste",
      str_detect(outlet_clean, "astillero") ~ "el astillero",
      str_detect(outlet_clean, "el sol de mexico") ~ "oem mexico",
      str_detect(outlet_clean, "mexico informa|mexicoinforma") ~ "mexico informa",
      str_detect(outlet_clean, "7 24|siete24|siete 24|724") ~ "siete24 noticias",
      str_detect(outlet_clean, "business energy|bussiness energy") ~ "business energy",
      str_detect(outlet_clean, "acustik") ~ "acustik noticias",
      str_detect(outlet_clean, "adn|adn40|ad notcias") ~ "adn 40",
      str_detect(outlet_clean, "abc") ~ "abc",
      str_detect(outlet_clean, "telemundo") ~ "telemundo",
      str_detect(outlet_clean, "canton") ~ "grupo canton",
      str_detect(outlet_clean, "vanguardia") ~ "mmm vanguardia",
      str_detect(outlet_clean, "animal politico|anima politico") ~ "animal politico",
      str_detect(outlet_clean, "formula") ~ "formula",
      str_detect(outlet_clean, "televisa|n mas") ~ "televisa",
      str_detect(outlet_clean, "jornada") ~ "la jornada",
      str_detect(outlet_clean, "universal") ~ "el universal",
      str_detect(outlet_clean, "tabasco hoy") ~ "tabasco hoy",
      str_detect(outlet_clean, "quintana roo hoy") ~ "quintana roo hoy",
      str_detect(outlet_clean, "campeche hoy") ~ "campeche hoy",
      str_detect(outlet_clean, "basta") ~ "diario basta",
      str_detect(outlet_clean, "financiero|bloomberg|bloomber") ~ "el financiero",
      str_detect(outlet_clean, "unomasuno|uno mas uno|unomas uno|uno masuno") ~ "uno mas uno",
      str_detect(outlet_clean, "expansion") ~ "expansion",
      str_detect(outlet_clean, "economista") ~ "el economista",
      str_detect(outlet_clean, "chapucero") ~ "el chapucero",
      str_detect(outlet_clean, "imparcial oaxaca") ~ "imparoaxaca",
      str_detect(outlet_clean, "imagen del golfo|imagen del giolfo|diario del istmo|imagen de veracruz") ~ "mmm imagen del golfo",
      str_detect(outlet_clean, "healy|frontera|el imparcial") ~ "healy",
      str_detect(outlet_clean, "mvs |mvs|mv noticias") ~ "mvs noticias",
      str_detect(outlet_clean, "multimedios|canal 6") ~ "multimedios",
      str_detect(outlet_clean, "contralinea") ~ "contralinea",
      str_detect(outlet_clean, "mega noticias|meganoticias|meganoticas") ~ "meganoticias",
      str_detect(outlet_clean, "reuters") ~ "reuters",
      str_detect(outlet_clean, "mexico publica") ~ "mexico publica",
      str_detect(outlet_clean, "forbes") ~ "forbes",
      str_detect(outlet_clean, "expansion|expaansion") ~ "expansion",
      str_detect(outlet_clean, "w radio") ~ "w radio",
      str_detect(outlet_clean, "infobae") ~ "infobae",
      str_detect(outlet_clean, "vice") ~ "vice",
      str_detect(outlet_clean, "sdp") ~ "sdp noticias",
      str_detect(outlet_clean, "cnn") ~ "cnn",
      str_detect(outlet_clean, "acir") ~ "acir",
      str_detect(outlet_clean, "imer") ~ "imer",
      str_detect(outlet_clean, "acir") ~ "acir",
      str_detect(outlet_clean, "amarc") ~ "amarc",
      str_detect(outlet_clean, "24 horas") ~ "diario 24 horas",
      str_detect(outlet_clean, "canal 13|trece") ~ "canal 13",
      str_detect(outlet_clean, "publimetro") ~ "publimetro",
      str_detect(outlet_clean, "proceso") ~ "proceso",
      str_detect(outlet_clean, "spr|catorce|canal 14|sistema publico") ~ "canal 14 spr",
      str_detect(outlet_clean, "nacion 14|nacion14") ~ "nacion 14",
      str_detect(outlet_clean, "deutsche|welle") ~ "deutsche welle",
      str_detect(outlet_clean, "la razon") ~ "la razon",
      str_detect(outlet_clean, "calorpolitico|calor politico") ~ "al calorpolitico",
      str_detect(outlet_clean, "pie de pagina|piedepagina") ~ "pie de pagina",
      str_detect(outlet_clean, "cuartooscuro|cuartoscuro") ~ "cuartoscuro",
      str_detect(outlet_clean, "tribuna") ~ "tribuna",
      str_detect(outlet_clean, "mexico informa|mexicoinforma") ~ "mexico informa",
      str_detect(outlet_clean, "embargo|sinembargo|sinembargomx|sin embargomx") ~ "sin embargo",
      str_detect(outlet_clean, "sintesis|sintesistv|sintes s") ~ "sintesis",
      str_detect(outlet_clean, "mural|muralchiapas") ~ "mural",
      str_detect(outlet_clean, "entre lineas|entrelineas") ~ "entre lineas",
      str_detect(outlet_clean, "sudcaliforniano|sud californiano") ~ "sudcaliforniano",
      str_detect(outlet_clean, "censura") ~ "sin censura",
      str_detect(outlet_clean, "unotv|uno tv|uno television") ~ "unotv",
      str_detect(outlet_clean, "chamuco") ~ "el chamuco",
      str_detect(outlet_clean, "enfas s|enfasis") ~ "enfasis",
      str_detect(outlet_clean, "charritotv|canal22|canal 22|canal22demayo|charrito tv") ~ "charrito tv",
      str_detect(outlet_clean, "canal red|canal r e d") ~ "canal red",
      str_detect(outlet_clean, "relax") ~ "relax",
      str_detect(outlet_clean, "a tiempotv|a tiempo") ~ "a tiempo tv",
      str_detect(outlet_clean, "pulsosaludable|pulso saludable") ~ "pulso saludable",
      str_detect(outlet_clean, "enfoque|enfoquenoticias") ~ "enfoque noticias",
      str_detect(outlet_clean, "grupo sol|sol de campeche") ~ "grupo sol",
      str_detect(outlet_clean, "sputnik") ~ "sputnik",
      str_detect(outlet_clean, "agencia efe|efe | efe |efe") ~ "agencia efe",
      str_detect(outlet_clean, "ombligo") ~ "ombligo",
      str_detect(outlet_clean, "expresion") ~ "expresion",
      str_detect(outlet_clean, "rock") ~ "rock and roll",
      str_detect(outlet_clean, "noreste") ~ "noreste",
      str_detect(outlet_clean, "jf informa|jaime farias") ~ "jf informa",
      str_detect(outlet_clean, "lanzate") ~ "lanzate",
      str_detect(outlet_clean, "latitudes") ~ "latitudes",
      str_detect(outlet_clean, "france|afp") ~ "agencia france press",
      str_detect(outlet_clean, "blogs") ~ "vittor blogs",
      str_detect(outlet_clean, "lord|petroleo") ~ "lord molecula oficial",
      str_detect(outlet_clean, "tromedia|qatromed") ~ "quatromedia telecomunicaciones",
      str_detect(outlet_clean, "quadratin") ~ "quadratin",
      str_detect(outlet_clean, "radiorama|radio rama") ~ "grupo radiorama",
      str_detect(outlet_clean, "radiocentro|radio centro") ~ "grupo radio centro",
      str_detect(outlet_clean, "mexico news|mexico newa") ~ "mexico news",
      str_detect(outlet_clean, "zmg") ~ "noticias zmg",
      str_detect(outlet_clean, "centinela") ~ "el centinela informa",
      str_detect(outlet_clean, "hoguera") ~ "la hoguera",
      str_detect(outlet_clean, "presente") ~ "diario presente del sureste",
      str_detect(outlet_clean, "cuarto poder") ~ "cuarto poder",
      str_detect(outlet_clean, "quinto poder|5to") ~ "quinto poder",
      str_detect(outlet_clean, "bajo palabra") ~ "bajo palabra",
      str_detect(outlet_clean, "chispa") ~ "la chispa",
      str_detect(outlet_clean, "tj comunica|tijuana comunica|tjcomunica") ~ "tijuana comunica",
      str_detect(outlet_clean, "larsa") ~ "grupo larsa comunicaciones",
      str_detect(outlet_clean, "equilibrio") ~ "equilibrio",
      str_detect(outlet_clean, "canal 44") ~ "canal 44",
      str_detect(outlet_clean, "rt | rt ") ~ "rt",
      str_detect(outlet_clean, "la hora de la ve") ~ "gaceta del aire",
      str_detect(outlet_clean, "diario la verdad|la verdad") ~ "diario la verdad",
      str_detect(outlet_clean, "on noticias|on notcias") ~ "on noticias",
      str_detect(outlet_clean, "reportero urbano|reporte urbano") ~ "reportero urbano",
      str_detect(outlet_clean, "antitesis") ~ "antitesis",
      str_detect(outlet_clean, "xinhua") ~ "xinhua",
      str_detect(outlet_clean, "ae grupo informativo|ae informativo") ~ "ae grupo informativo",
      str_detect(outlet_clean, "el sol|sol de") ~ "oem otros",
      str_detect(outlet_clean, "elitv|eli television") ~ "eli television",
      str_detect(outlet_clean, "obtu") ~ "agencia obturador",
      str_detect(outlet_clean, "sur de guerrero|periodico el sur|noticias de queretaro") ~ "mmm otros",
      str_detect(outlet_clean, "desde la frontera") ~ "desde la frontera",
      str_detect(outlet_clean, "diario de juarez") ~ "el diario de juarez",
      str_detect(outlet_clean, "meridiano") ~ "meridiano",
      str_detect(outlet_clean, "sonora power|sonorapower") ~ "sonora power",
      str_detect(outlet_clean, "vigiliasonora|vigilia sonora") ~ "sonora power",
      str_detect(outlet_clean, "la prensa") ~ "la prensa",
      str_detect(outlet_clean, "audiorama") ~ "audiorama",
      str_detect(outlet_clean, "reforma|el norte|mural") ~ "reforma",
      str_detect(outlet_clean, "noticieros el reloj") ~ "noticieros el reloj de la tlaxiaquena",
      str_detect(outlet_clean, "perspectivas") ~ "perspectivas",
      str_detect(outlet_clean, "sipse|novedades de yucatan|novedades|novedades de quintana roo") ~ "novedades de yucatan",
      str_detect(outlet_clean, "esahora|es ahora") ~ "",
      str_detect(outlet_clean, "ahora tabasco|ahora noticias") ~ "ahora tabasco",
      str_detect(outlet_clean, "tiempo com") ~ "tiempo la noticial digital",
      str_detect(outlet_clean, "movimiento cons") ~ "movimiento consciencia",
      str_detect(outlet_clean, "puente libre|puentelibre") ~ "movimiento consciencia",
      str_detect(outlet_clean, "latino") ~ "radio latino",
      str_detect(outlet_clean, "charro") ~ "charro politico",
      str_detect(outlet_clean, "despierta q|despierta tv") ~ "despierta qroo",
      str_detect(outlet_clean, "impacto") ~ "impacto diario",
      TRUE ~ outlet_clean
    )
  )



name_table <- df %>%
  count(outlet_clean, sort = TRUE)

check <- name_table |> filter(str_detect(outlet_clean, "emb")) |>
    count(outlet_clean, sort = TRUE)

# Dictionary for weird cases:

dictionary_media <- list(
  "televisa" = c(
    "televisa",
    "n+", "ni1+"
    
  ),
  "associated press" = c(
    "ap", "the associated press", "excelsior y the associated press",
    "a p", "the associated press ap", "associated press"
    
  ), 
  "sdp noticias" = c(
    "sdp noticias",
    "el deforma", 'deforma'
  ),
  "imagen television" = c(
    "grupo imagen", "grupo imagen television", "imagen radio", "imagen radio mexicali",
    "imagen television", "imagen television puebla", "imagen telecision",
    'grupo imagen puebla', 'imagen de veracruz'
  ),
  "grupo canton" = c(
    "grupo canton", 'grupo cantoin',
    "yucatan hoy", 'diario basta',
    "quintana roo hoy", 'tabasco hoy',
    "campeche hoy"
  ), 
  "el heraldo de mexico" = c(
    "el heraldo de mexico", 'heraldo de mexico', 'el heraldo',
    "el heraldo radio", 'el heraldo radio 92 5 fm', 'heraldo television'
  ), 
  "el heraldo de veracruz" = c(
    "el heraldo de veracruz", 'heraldo de veracruz', 'el heraldo de xalapa'
  ), 
  "oem otros" = c('oem otros',
    "el heraldo de tabasco", 'el heraldo de tabasco oem', 'el occidental',
    'el occidental oem', 'periodico el occidental', 'el heraldo de chihuahua', 
    'el heraldodechihuahua', 'diario de queretaro', 'sudcaliforniano'
    
  ), 
  "mmm otros" = c('mmm otros',
                  'diario de chiapas',
                  'diario de colima', 'el informador', 'imparoaxaca', 
                  'novedades de yucatan', 'el debate', 'tribuna', 
                  'el diario de sonora', 'avance tabasco', 
                  'dia a dia avance tabasco informa', 'el diario de juarez'
                  
  ), 
  "avan noticias" = c(
    "avan noticias", "quatromedia telecomunicaciones", 
    "qatromedia telecomunicaciones"
  ), 
  "epme" = c(
    "el siglo de torreon", "diario de yucatan", 
    "periodico noroeste", 'el siglo de durango', 'plaza de armas'
  ),
  "reporteros mx" = c(
    "fotorreporteros mx", "reporteros mx", "fotoreporterosmx", "los reporteros mx"
  ), 
  "el quintana roo mx" = c(
    "el quintana roo mx", "el quintana roo", "el quintanaroo"
  )
)

dictionary_tbl <- imap_dfr(
  dictionary_media,
  ~ tibble(
    canonical_outlet = .y,
    variant = .x
  )
)

df <- df %>%
  left_join(dictionary_tbl, by = c("outlet_clean" = "variant")) %>%
  mutate(outlet_final = coalesce(canonical_outlet, outlet_clean))

check <- df |> filter(str_detect(outlet_final, "contra")) |>
  count(outlet_final, sort = TRUE)

name_table <- df %>%
  count(outlet_final, sort = TRUE)

final_dedup <- name_table |> filter(n>4)

final_dedup <- final_dedup |> rename(total_attendance = n)

writexl::write_xlsx(final_dedup, media_output_path('data', '02-conferences', 'raw', 'attendance', 'merged', 'bridge_outlets.xlsx'))

write_parquet(df, media_output_path('data', '02-conferences', 'raw', 'attendance', 'merged', 'attendance_clean.parquet'))

#### Generate panels:

# 1 get all unique dates:
library(lubridate)

dates <- df |>
  distinct(fecha) |>
  mutate(
    fecha = as.Date(fecha),
    year  = year(fecha),
    month = month(fecha),
    day   = day(fecha)
  )

# 2 Generate the panel:

panel <- tidyr::crossing(final_dedup |> select(outlet_final), dates) |>
  arrange(outlet_final, fecha)

# 3 Group the attendance on the outlet final (for merge) and on date

df_g <- df |> mutate(
  fecha = as.Date(fecha)) |> group_by(fecha, outlet_final) |> summarise(n_journalists = n()) |> 
  ungroup()

panel <- panel |> left_join(df_g, by = c('fecha', 'outlet_final')) |> 
  mutate(n_journalists = ifelse(is.na(n_journalists) == T, 0, n_journalists), 
         attended = ifelse(n_journalists > 0, 1, 0))


# Add covariates (media): total attendance before lottery, total attendance after, total attendance,

before <- df %>% mutate(fecha = as.Date(fecha)) |>
  filter(fecha < as.Date('2022-04-12')) |>
  count(outlet_final, sort = TRUE) |> rename(attendance_bef = n)
  
after <- df %>% mutate(fecha = as.Date(fecha)) |>
  filter(fecha >= as.Date('2022-04-12')) |>
  count(outlet_final, sort = TRUE) |> rename(attendance_after = n)

panel <- panel |> left_join(final_dedup) |> left_join(after) |> left_join(before) |> 
  mutate(attendance_after = ifelse(is.na(attendance_after) == T, 0, attendance_after), 
         attendance_bef = ifelse(is.na(attendance_bef) == T, 0, attendance_bef))


# Add covariates (press conference): total number of journalists, camarographers, etc

df_attendees <- df |> 
  mutate(cargos = case_when(str_detect(cargo, "REPORTERO|REPORTETO") ~ "reportero",
                            str_detect(cargo, "YOUTUBER") ~ "youtuber",
                            TRUE ~ 'otro')) |>
  fastDummies::dummy_cols(
    select_columns = "cargos",
    remove_first_dummy = FALSE,
    remove_selected_columns = FALSE
  ) |> group_by(fecha) |> summarise(n_total_attend = n(), 
                                    n_reporteros = sum(cargos_reportero),
                                    n_youtubers = sum(cargos_youtuber)) |>
  ungroup()

panel <- panel |> left_join(df_attendees)

# Export:

write_parquet(panel, media_output_path('data', '02-conferences', 'raw', 'attendance', 'panel_attendance.parquet.gzip'),
              compression = 'gzip')

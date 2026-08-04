###################################################
## Descriptive statistics: journalist alignment at mañaneras
## Author: Eduardo Zago-Cuevas (all errors are my own)
## Run after: 05_classify_alignment.py
## Unit of analysis: reporter-day (preguntas only)
##   opp_day = 1 if reporter asked >= 1 oppositional pregunta that day
## Window: ±1 year around the April 14 2022 lottery
##   Pre-lottery : 2021-04-14 – 2022-04-13
##   Post-lottery: 2022-04-14 – 2023-04-13
###################################################

# install.packages('pacman')

pacman::p_load(tidyverse, arrow, patchwork, zoo, scales, xtable)

rm(list = ls())
rstudioapi::getActiveDocumentContext
setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
source("../../../project_paths.R")

LOTTERY_DATE <- as.Date('2022-04-18')

pfo     <- paste0(media_path('data', '02-conferences', 'auxiliar'), '/')
res_dir <- paste0(dirname(media_output_path('results', 'descriptives', '.keep')), '/')
dir.create(res_dir, recursive = TRUE, showWarnings = FALSE)

df <- read_parquet(paste0(pfo, 'questions_dataset.parquet')) |>
  mutate(date = as.Date(date)) |>
  mutate(period = factor(if_else(date < LOTTERY_DATE,
                                 'Pre-lottery', 'Post-lottery'),
                         levels = c('Pre-lottery', 'Post-lottery')))

df_rep_out <- df |> group_by(reporter_aux, outlet_aux) |> summarise(n_t = n()) |>
  ungroup()

# Dedup code:

df <- df %>%
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
    ))
  

df <- df %>%
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
  )

df <- df %>%
  mutate(
    outlet_aux = ifelse(str_detect(reporter_aux, "carlos guzman") == T, 
                        'avan noticias', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "roberto cruz") == T, 
                        'impacto diario', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "valentina peralta") == T, 
                        'reportero independiente', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "frida guerrera") == T & outlet_aux != 'rompeviento tv', 
                        'frida guerrera', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "juan hernandez") == T, 
                        'grupo canton', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "amir ibrahim") == T, 
                        'quintana roo mx', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "maria luisa estrada") == T, 
                        'la grillotina', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "elianne") == T, 
                        'eli tv', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "arturo pavon") == T, 
                        'el chapucero', outlet_aux), 
    outlet_aux = ifelse(str_detect(reporter_aux, "michelle rivera") == T, 
                        'grupo formula', outlet_aux), 
    outlet_aux = ifelse(str_detect(reporter_aux, "luis guillermo|sexta w") == T, 
                        'luis guillermo hernandez sexta w', outlet_aux), 
    outlet_aux = ifelse(str_detect(reporter_aux, "arturo paramo") == T, 
                        'grupo imagen', outlet_aux), 
    outlet_aux = ifelse(str_detect(reporter_aux, "ramon flo") == T, 
                        'el centinela informa', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "janet galindo|janeth galindo") == T, 
                        'la chispa', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "diego elias cedillo") == T, 
                        'grupo canton', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "wenceslao") == T, 
                        'sin censura', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "luis ignacio velasquez") == T, 
                        'voz e imagen de oaxaca', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "victor buendia") == T, 
                        'mexico informa', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "ramon guti|ramon ramirez") == T, 
                        'noticieros el reloj de la tlaxiaquena', outlet_aux), 
    outlet_aux = ifelse(str_detect(reporter_aux, "carlos dominguez") == T, 
                        'mvs noticias', outlet_aux), 
    outlet_aux = ifelse(str_detect(reporter_aux, "carlos olvera") == T, 
                        'portal guanajuato', outlet_aux)
    )

df <- df %>%
  mutate(
    outlet_aux = ifelse(str_detect(reporter_aux, "sandra aguilera") == T & 
                          outlet_aux == 'grupo', 
                        'ae grupo informativo', outlet_aux),
    outlet_aux = ifelse(str_detect(reporter_aux, "carlos pozos") == T & 
                          str_detect(outlet_aux, "outlet") == T, 
                        'lord molecula oficial', outlet_aux)
  )

df <- df %>%
  mutate(
    outlet_aux = ifelse(str_detect(reporter_aux, "olvera") == T & 
                          outlet_aux == '', 
                        'marco olvera oficial', outlet_aux)
  )

df_rep_out <- df |> group_by(reporter_aux, outlet_aux) |> summarise(n_t = n()) |>
  ungroup()

name_table <- df %>%
  count(outlet_aux, reporter_aux, sort = TRUE)

df <- df |> filter(outlet_aux!='')

contra <- df |> filter(outlet_aux == 'sdpnoticias')

write_parquet(df, paste0(pfo, 'questions_dataset_dedup.parquet'))

################################################### For further checks:

none <- df |> filter(outlet_aux == '')


#### We went over the cases in the Excel. Now lets see the weird cases

weird <- df |> 
  count(outlet_aux, sort = TRUE) |> filter(n<15)


#Outlet

check <- name_table |> filter(str_detect(outlet_aux, "ahora")) |>
  count(outlet_aux, reporter_aux, sort = TRUE)


#Reporter

check2 <- name_table |>  filter(str_detect(reporter_aux, "alberto")) |>
  count(outlet_aux, reporter_aux, sort = TRUE)


# 0.0 Set up the environment, clean it and set paths to the Dropbox project
rm(list = ls())

project_root <- Sys.getenv("MEDIA_PROJECT_ROOT", unset = NA_character_)
if (is.na(project_root) || !nzchar(project_root)) {
  dropbox_root <- path.expand("~/Dropbox/Media")
  dell_root <- "C:/Users/Dell/Dropbox/Media"
  if (dir.exists(dropbox_root)) {
    project_root <- dropbox_root
  } else if (dir.exists(dell_root)) {
    project_root <- dell_root
  } else {
    stop("Set MEDIA_PROJECT_ROOT to the local Dropbox/Media folder before running this script.")
  }
}

project_root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
setwd(file.path(project_root, "code", "02-cleaning_comsoc"))

library(purrr)
library(tidyverse)
library(arrow)

path_co <- file.path(project_root, "data", "01-social_communication")
path_da <- file.path(project_root, "data", "06-outcomes", "comsoc")
dir.create(path_da, showWarnings = FALSE, recursive = TRUE)

## Bridges: 

read_data <- function(year){
  df <- read_parquet(file.path(path_co, '01-intermediate',
                         paste0('polizas_clean_', year, '.parquet')))
  return(df)
}

df <- c(2012:2024) |> map_dfr(~read_data(.x))

df <- df |> mutate(across(where(is.character), ~str_squish(.x)))

write_parquet(df, file.path(path_da, 'contracts_2012_2024.parquet'))

# df <- df |> 
#   filter(year.contrato>2017 & year.contrato<2025)
# 
# write_parquet(df, file.path(path_da, 'contracts_2018_2024.parquet'))


library(stringr)
library(stringi)

clean_outlet <- function(x) {
  
  x |>
    str_to_lower() |> stringi::stri_trans_general("Latin-ASCII") |>
    # remove punctuation
    str_remove_all("[[:punct:]]") |>
    # trim spaces
    str_squish()
}


clean_outlet2 <- function(x) {
  
  x |>
    # remove legal company suffixes
    str_remove_all("\\b(s\\.?a\\.?\\s*de\\s*c\\.?v\\.?|s\\.?a\\.?|s\\.?\\s*de\\s*r\\.?l\\.?\\s*de\\s*c\\.?v\\.?|s\\.?\\s*de\\s*r\\.?l\\.?|s\\.?\\s*c\\.?|a\\.?c\\.?)\\b") |>
    
    # remove generic media terms
    str_remove_all("\\b(periodico?s?|diario?s?|editorial|revista?s?|grupo|medios?|comunicacion|noticias|informativo|informativa|online|television|tv|radio|canal)\\b") |>
    
    # trim spaces
    str_squish()
}

name_ini <- df %>%
  count(beneficiario, sort = TRUE)

df$bene_clean <- clean_outlet(df$beneficiario)

name_table <- df %>%
  count(bene_clean, sort = TRUE)

check <- name_table |> filter(str_detect(bene_clean, "reforma|editora el sol")) |>
  count(bene_clean, sort = TRUE)

# Let's clean up the beneficiarios and see the distinct. I just need to clean the ones 
# that I found on the mañanera

df <- df %>%
  mutate(bene_clean = str_to_lower(bene_clean)) %>%
  mutate(
    bene_clean = case_when(
      str_detect(bene_clean, "grupo formula|radio formula|teleformula|informula") ~ "formula",
      str_detect(bene_clean, "grupo expansion|5m2|expansion sa") ~ "expansion",
      str_detect(bene_clean, "tv azteca|operadora mexicana") ~ "azteca",
      str_detect(bene_clean, "milenio diario|diario milenio|agencia digital|editorial milenio") ~ "milenio",
      str_detect(bene_clean, "medios del caribe") ~ "demos caribe",
      TRUE ~ bene_clean
    )
  )

df$bene_clean <- clean_outlet2(df$bene_clean)

name_table2 <- df %>%
  count(bene_clean, sort = TRUE)

check2 <- name_table2 |> filter(str_detect(bene_clean, "sipse|novedades|novedades del sureste")) |>
  count(bene_clean, sort = TRUE)

df <- df %>%
  mutate(bene_clean = str_to_lower(bene_clean)) %>%
  mutate(
    bene_final = case_when(
      str_detect(bene_clean, "proabri") ~ "quinto poder",
      str_detect(bene_clean, "debate") ~ "debate",
      str_detect(bene_clean, "sistema de tabasco") ~ "diario presente",
      str_detect(bene_clean, "ofem|estrictamente") ~ "eje central",
      str_detect(bene_clean, "difusion de info|libertad") ~ "eje central",
      str_detect(bene_clean, "hojas") ~ "el chapucero",
      str_detect(bene_clean, "financiero|lauman") ~ "el financiero",
      str_detect(bene_clean, "voz del istmo") ~ "voz del istmo",
      str_detect(bene_clean, "editora offset") ~ "noticias de queretaro",
      str_detect(bene_clean, "yucateca") ~ "diario de yucatan",
      str_detect(bene_clean, "sistema periodistico de sinaloa") ~ "noroeste",
      str_detect(bene_clean, "editora de la laguna") ~ "el siglo de torreon",
      str_detect(bene_clean, "excelsior|gim compania") ~ "excelsior",
      str_detect(bene_clean, "contrareplica") ~ "contrareplica",
      str_detect(bene_clean, "nrm") ~ "nrm comunicaciones",
      str_detect(bene_clean, "economista|especializado en economia") ~ "el economista",
      str_detect(bene_clean, "masivos mexicanos") ~ "medios masivos mexicanos",
      str_detect(bene_clean, "demos|al fin verde") ~ "la jornada demos",
      str_detect(bene_clean, "sendero") ~ "sdp noticias",
      str_detect(bene_clean, "angulo 7") ~ "angulo 7",
      str_detect(bene_clean, "imagen comercial|gim nacional") ~ "imagen",
      str_detect(bene_clean, "comunitarias de mexico|comunitarias demexico") ~ "amarc",
      str_detect(bene_clean, "televisa") ~ "televisa",
      str_detect(bene_clean, "el universal") ~ "el universal",
      str_detect(bene_clean, "lrhg") ~ "la razon mexico",
      str_detect(bene_clean, "canton|acuario|campeche hoy|prosperidad") ~ "grupo canton",
      str_detect(bene_clean, "informacion integral") ~ "diario 24 horas",
      str_detect(bene_clean, "imparcial") ~ "grupo healy",
      str_detect(bene_clean, "stereorey|mvs") ~ "mvs noticias",
      str_detect(bene_clean, "publimetro") ~ "publimetro",
      str_detect(bene_clean, "mayann") ~ "mayann",
      str_detect(bene_clean, "reforma|editora el sol") ~ "reforma",
      str_detect(bene_clean, "cifo multimedios") ~ "cifo",
      str_detect(bene_clean, "multimedios oro") ~ "grupo oro",
      str_detect(bene_clean, "sipse|novedades de quintana|novedades del sureste|novedades de campeche|novedades de merida") ~ "sipse",
      TRUE ~ bene_clean
    )
  )


df <- df |> 
  mutate(
    producto_clean = descripcion.producto |>
      str_to_lower() |>
      stringi::stri_trans_general("Latin-ASCII") |>
      str_remove_all("[.,]")
  ) 

name_table_prod <- df %>%
  count(producto_clean, sort = TRUE)

df <- df |> mutate(
  producto_clean = case_when(
    str_detect(producto_clean, "diarios editados") ~ "Newspapers Published in States",
    str_detect(producto_clean, "internet") ~ "Internet",
    str_detect(producto_clean, "radio") ~ "Radio Broadcasters",
    str_detect(producto_clean, "television abierta") ~ "Broadcast TV",
    str_detect(producto_clean, "television restringida") ~ "Pay TV",
    str_detect(producto_clean, "revista") ~ "Magazines",
    str_detect(producto_clean, "internacionales") ~ "International Media",
    str_detect(producto_clean, "estudios") ~ "Polling Companies",
    str_detect(producto_clean, "urbano|espectaculares") ~ "Urban Advertising",
    str_detect(producto_clean, "Urbano") ~ "Urban Advertising",
    TRUE ~ 'Other'
  ))

write_parquet(df, file.path(path_da, 'contracts_2012_2024_clean.parquet'))




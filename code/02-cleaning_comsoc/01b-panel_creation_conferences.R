# 0.0 Set up the environment, clean it and set working directory to the code path
rm(list = ls())
rstudioapi::getActiveDocumentContext
setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
source("../../project_paths.R")

library(purrr)
library(tidyverse)
library(arrow)

path_co <- paste0(media_path('data', '01-social_communication'), '/')
path_da <- paste0(media_path('data', '06-outcomes', 'comsoc'), '/')

## Bridges: 

read_data <- function(year){
  df <- read_parquet(paste0(path_co, '01-intermediate/polizas_clean_',
                            year, '.parquet'))
  return(df)
}

df <- c(2012:2024) |> map_dfr(~read_data(.x))

df <- df |> mutate(across(where(is.character), ~str_squish(.x)))

write_parquet(df, paste0(path_da, 'contracts_2012_2024.parquet'))

df <- df |> 
  filter(year.contrato>2017 & year.contrato<2025)

write_parquet(df, paste0(path_da, 'contracts_2018_2024.parquet'))


library(stringr)
library(stringi)

clean_outlet <- function(x) {
  
  x |>
    str_to_lower() |>
    stringi::stri_trans_general("Latin-ASCII") |>
    
    # remove legal company suffixes
    str_remove_all("\\b(s\\.?a\\.?\\s*de\\s*c\\.?v\\.?|s\\.?a\\.?|s\\.?\\s*de\\s*r\\.?l\\.?\\s*de\\s*c\\.?v\\.?|s\\.?\\s*de\\s*r\\.?l\\.?|s\\.?\\s*c\\.?|a\\.?c\\.?)\\b") |>
    
    # remove generic media terms
    str_remove_all("\\b(periodico?s?|diario?s?|editorial|revista?s?|grupo|medios?|comunicacion|noticias|informativo|informativa|online|television|tv|radio|canal)\\b") |>
    
    # remove punctuation
    str_remove_all("[[:punct:]]") |>
    
    # trim spaces
    str_squish()
}

name_ini <- df %>%
  count(beneficiario, sort = TRUE)

check2 <- name_ini |> filter(str_detect(beneficiario, "PAIS")) |>
  count(beneficiario, sort = TRUE)

# Let's clean up the beneficiarios and see the distinct. I just need to clean the ones 
# that I found on the mañanera

df$bene_clean <- clean_outlet(df$beneficiario)

name_table <- df %>%
  count(bene_clean, sort = TRUE)

check <- name_table |> filter(str_detect(bene_clean, "pais")) |>
  count(bene_clean, sort = TRUE)

df <- df %>%
  mutate(bene_clean = str_to_lower(bene_clean)) %>%
  mutate(
    bene_final = case_when(
      str_detect(bene_clean, "hojas") ~ "el chapucero",
      str_detect(bene_clean, "excelsior") ~ "excelsior",
      str_detect(bene_clean, "contrareplica") ~ "contrareplica",
      str_detect(bene_clean, "nrm") ~ "nrm comunicaciones",
      str_detect(bene_clean, "milenio|agencia digital") ~ "milenio",
      str_detect(bene_clean, "estudios azteca|tv azteca") ~ "azteca",
      str_detect(bene_clean, "economista|especializado en economia") ~ "el economista",
      str_detect(bene_clean, "masivos mexicanos") ~ "medios masivos mexicanos",
      str_detect(bene_clean, "demos") ~ "la jornada demos",
      str_detect(bene_clean, "sendero") ~ "sdp noticias",
      str_detect(bene_clean, "angulo") ~ "angulo 7",
      str_detect(bene_clean, "informula|c v formula|regional formula") ~ "formula noticias",
      str_detect(bene_clean, "imagen comercial|gim nacional") ~ "formula noticias",
      str_detect(bene_clean, "comunitarias de mexico|comunitarias demexico") ~ "amarc",
      str_detect(bene_clean, "televisa") ~ "televisa",
      str_detect(bene_clean, "universal") ~ "el universal",
      str_detect(bene_clean, "lrhg") ~ "la razon mexico",
      str_detect(bene_clean, "canton|acuario|campeche hoy") ~ "grupo canton",
      str_detect(bene_clean, "informacion integral") ~ "diario 24 horas",
      str_detect(bene_clean, "imparcial") ~ "grupo healy",
      str_detect(bene_clean, "stereorey|mvs") ~ "mvs noticias",
      str_detect(bene_clean, "publimetro") ~ "publimetro",
      str_detect(bene_clean, "mayann") ~ "mayann",
      str_detect(bene_clean, "cifo multimedios") ~ "cifo",
      str_detect(bene_clean, "multimedios oro") ~ "grupo oro",
      str_detect(bene_clean, "sipse|novedades de quintana") ~ "sipse",
      TRUE ~ bene_clean
    )
  )


df <- df |> 
  mutate(
    clase_clean = clase.de.beneficiario |>
      str_to_lower() |>
      stringi::stri_trans_general("Latin-ASCII") |>
      str_remove_all("[.,]")
  ) 

name_table_prod <- df %>%
  count(clase_clean, sort = TRUE)

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

dfdd <- df |> filter(clase_clean == 'p')

write_parquet(df, paste0(path_da, 'contracts_2018_2024_clean.parquet'))




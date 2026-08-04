# 0.0 Set up the environment, clean it and set working directory to the code path
rm(list = ls())
rstudioapi::getActiveDocumentContext
setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
source("../../project_paths.R")

library(purrr)
library(tidyverse)
library(arrow)

path_co <- paste0(media_path('data', '01-social_communication'), '/')

## Bridges: 

read_data <- function(year){
  df <- read_parquet(paste0(path_co, '01-intermediate/polizas_clean_',
                            year, '.parquet'))
  return(df)
}

df <- c(2012:2023) |> map_dfr(~read_data(.x))

df <- df |> mutate(across(where(is.character), ~str_squish(.x)))

colnames(df)

news_words <- c('DIARIOS EDITADOS EN LOS ESTADOS', 'DIARIOS EDITADOS EN EL D.F.', 
                'REVISTAS', 'INTERNET', 'DIARIOS EDITADOS EN LA CD. DE MÉXICO', 
                'DIARIOS EDITADOS EN LA CIUDAD DE MÉXICO', 
                'DIARIOS EDITADOS EN LA CD. DE MEXICO', 
                'DIARIOS EDITADOS EN LA CD DE MÉXICO')

df1 <- df |> filter(descripcion.producto %in% news_words) |> 
  filter(year.contrato>2016 & year.contrato<2022)

bene_2016 <- df1 |> filter(year.gasto == 2016) |> distinct(beneficiario)

bene_2017 <- df1 |> filter(year.gasto == 2017) |> distinct(beneficiario) |> 
  mutate(dm = 1)

bene_2018 <- df1 |> filter(year.gasto == 2018) |> distinct(beneficiario) |> 
  mutate(dm1 = 1)

bene_2019 <- df1 |> filter(year.gasto == 2019) |> distinct(beneficiario) |> 
  mutate(dm2 = 1)

bene_2020 <- df1 |> filter(year.gasto == 2020) |> distinct(beneficiario) |> 
  mutate(dm3 = 1)

bene_2021 <- df1 |> filter(year.gasto == 2021) |> distinct(beneficiario) |> 
  mutate(dm4 = 1)

benet <- bene_2016 |> left_join(bene_2017) |> left_join(bene_2018) |> 
  left_join(bene_2019) |> left_join(bene_2020) |> left_join(bene_2021) |>
  filter(is.na(dm) == F & is.na(dm1) == F & is.na(dm2) == F & 
           is.na(dm3) == F & is.na(dm4) == F) |> select(-c(dm:dm4))

months <- 1:12
years <- 2016:2021
month_year <- expand_grid(year = years, month = months)

# Expand the dataset to include all municipality-month-year combinations
panel_df <- benet %>%
  expand_grid(month_year) |> rename(month.contrato = month, 
                                    year.contrato = year)

#Summarise the full dataset, aggregating by year-month and beneficiario, the foll
# variables: importe, iva, costo.unitario, costo, iva.del.costo

df1_ag <- df1 |> group_by(beneficiario, year.contrato, month.contrato) |> 
  summarise(across(c(importe, iva, costo.unitario, costo, iva.del.costo), 
                   ~sum(.x, na.rm = T)))


panel_df <- panel_df |> left_join(df1_ag, by = c('month.contrato', 
                                                 'year.contrato', 
                                                 'beneficiario')) |> 
  mutate(across(c(importe, iva, costo.unitario, costo, iva.del.costo), 
                ~ifelse(is.na(.x) == T, 0, .x)))


write_parquet(panel_df, paste0(path_co, 
                               '01-intermediate/beneficiarios_panel_2016_2021.parquet'))

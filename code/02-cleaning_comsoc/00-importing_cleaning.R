# 0.0 Set up the environment, clean it and set working directory to the code path
rm(list = ls())
rstudioapi::getActiveDocumentContext
setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
source("../../project_paths.R")

library(purrr)
library(tidyverse)
library(stringi)
library(lubridate)
library(arrow)

path_co <- paste0(media_path('data', '01-social_communication'), '/')

## Script to clean up the COMSOC files

clean_polizas <- function(df){
  ind <- which(df[,1] == "Sector")
  # Set that row as the column names
  colnames(df) <- df[ind[1], ]
  
  colnames(df) <- gsub("\\\\|\\.|/", "", colnames(df))  # Remove backslashes and periods
  colnames(df) <- tolower(colnames(df))  # Convert to lowercase
  colnames(df) <- gsub(" ", ".", colnames(df))
  colnames(df) <- stringi::stri_trans_general(colnames(df), "Latin-ASCII")
  
  df <- df |> select(sector:notas.aclaratorias)
  
  df <- df |> filter(entidad != 'Entidad') |> filter(is.na(nombre) == F) |> 
    filter(nombre != 'IVA:') |> filter(is.na(fecha.de.gasto)==F)
  
  df$fecha.de.gasto <- as.Date(as.numeric(df$fecha.de.gasto), 
                               origin = "1899-12-30")
  
  df$day.gasto <- day(df$fecha.de.gasto)
  df$month.gasto <- month(df$fecha.de.gasto)
  df$year.gasto <- year(df$fecha.de.gasto)
  
  df$fecha.de.contratopedido <- as.Date(as.numeric(df$fecha.de.contratopedido), 
                                        origin = "1899-12-30")
  
  df$day.contrato <- day(df$fecha.de.contratopedido)
  df$month.contrato <- month(df$fecha.de.contratopedido)
  df$year.contrato <- year(df$fecha.de.contratopedido)
  
  df <- df |> mutate(id_poliza = paste0(poliza, cons))
  
  iva <- df |> select(id_poliza, importe, iva) |>
    filter(is.na(importe) == F) |> distinct(id_poliza, .keep_all = T)
  
  q <- df |> select(id_poliza, unidad.de.medida:notas.aclaratorias) |>
    filter(is.na(cantidad) == F) |> distinct(id_poliza, .keep_all = T)
  
  df <- df |> select(-c(importe, iva, unidad.de.medida:notas.aclaratorias)) |>
    distinct(id_poliza, .keep_all = T) |> left_join(iva) |> left_join(q)
  
  df <- df |> mutate(across(c(importe, iva, unidad.de.medida, 
                              cantidad:iva.del.costo), ~as.numeric(.x)))
    
  return(df)
}


export <- function(year){
  df <- readxl::read_excel(paste0(path_co, '00-raw/polizas_', year, '.xlsx'), 
                           sheet = 1)
  
  partida1 <- clean_polizas(df)
  
  df <- readxl::read_excel(paste0(path_co, '00-raw/polizas_', year,'.xlsx'), 
                           sheet = 2)
  
  partida2 <- clean_polizas(df)
  
  final <- bind_rows(partida1, partida2)
  
  write_parquet(final, paste0(path_co, '01-intermediate/polizas_clean_',
                              year, '.parquet'))
  
  print(year)
}

read_data <- function(year){
  df <- read_parquet(file.path(path_co, '01-intermediate',
                               paste0('polizas_clean_', year, '.parquet')))
  return(df)
}

c(2012:2023) |> map(~export(.x))

# Diff processing for 2024
df3 <- df
year <- 2024

df <- readxl::read_excel(paste0(path_co, '00-raw/polizas_', year, '.xlsx'), 
                         sheet = 1)

ind <- which(df[,1] == "Sector")
# Set that row as the column names
colnames(df) <- df[ind[1], ]

colnames(df) <- gsub("\\\\|\\.|/", "", colnames(df))  # Remove backslashes and periods
colnames(df) <- tolower(colnames(df))  # Convert to lowercase
colnames(df) <- gsub(" ", ".", colnames(df))
colnames(df) <- stringi::stri_trans_general(colnames(df), "Latin-ASCII")

df <- df |> select(sector:notas.aclaratorias)

df <- df |> filter(is.na(nombre.del.proveedor) == F) |> 
  filter(sector != 'Sector')

df2 <- readxl::read_excel(paste0(path_co, '00-raw/polizas_', year,'.xlsx'), 
                         sheet = 2)

ind <- which(df2[,1] == "Sector")
# Set that row as the column names
colnames(df2) <- df2[ind[1], ]

colnames(df2) <- gsub("\\\\|\\.|/", "", colnames(df2))  # Remove backslashes and periods
colnames(df2) <- tolower(colnames(df2))  # Convert to lowercase
colnames(df2) <- gsub(" ", ".", colnames(df2))
colnames(df2) <- stringi::stri_trans_general(colnames(df2), "Latin-ASCII")

df2 <- df2 |> select(sector:notas.aclaratorias)

df2 <- df2 |> filter(is.na(nombre.del.proveedor) == F) |> 
  filter(sector != 'Sector')

df <- bind_rows(df, df2)

df$fecha.de.gasto <- as.Date(df$fecha.de.gasto, format = "%d/%m/%Y")

df$day.gasto <- day(df$fecha.de.gasto)
df$month.gasto <- month(df$fecha.de.gasto)
df$year.gasto <- year(df$fecha.de.gasto)

df$fecha.de.contrato <- as.Date(df$fecha.de.contrato, 
                                      format = "%d/%m/%Y")

df$day.contrato <- day(df$fecha.de.contrato)
df$month.contrato <- month(df$fecha.de.contrato)
df$year.contrato <- year(df$fecha.de.contrato)

df <- df |> rename(
  entidad = clave.de.la.entidad, 
  beneficiario = nombre.del.proveedor, 
  descripcion.producto = clase.de.beneficiario,
  nombre = institucion,
  fecha.de.contratopedido = fecha.de.contrato,
  producto = clave.del.producto,
  campana = clave.de.campana, 
  descripcion.unidad = descripcion.de.la.unidad, 
  costo = monto
) |> select(-descripcion.del.producto)

df <- df |> mutate(across(c(costo, unidad.de.medida, 
                          cantidad:iva), ~as.numeric(.x)))

write_parquet(df, paste0(path_co, '01-intermediate/polizas_clean_',
                         year, '.parquet'))

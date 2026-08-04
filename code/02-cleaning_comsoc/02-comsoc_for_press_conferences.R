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

read_data <- function(year){
  df <- read_parquet(paste0(path_co, '01-intermediate/polizas_clean_',
                            year, '.parquet'))
  return(df)
}

path_co <- paste0(media_path('data', '01-social_communication'), '/')

panel <- c(2019:2023) |> map_dfr(~read_data(.x))

panel <- panel |> mutate(across(where(is.character), ~str_squish(.x)))

panel_ind <- panel |> group_by(beneficiario) |> 
  summarise(total_spent = sum(importe, na.rm = T)) |> 
  ungroup() |> arrange(desc(total_spent))

panel_ind <- panel |> distinct(beneficiario, .keep_all = T)

panel_givers <- panel |> group_by(nombre) |> summarise(count = n(), 
                                                       total_spent = sum(importe, 
                                                                         na.rm = T)) |>
  ungroup()

panel_givers <- panel_givers |> arrange(desc(count)) |> 
  mutate(total_spent = total_spent/1000000)

ggplot(panel_givers, aes(x = count)) +
  geom_histogram(fill = "darkred", alpha = 0.7) +  # Smooth density plot with color
  labs(
    title = "Density Plot of Spending",
    x = "Count (Assigned Contracts)",
    y = "Density"
  ) +
  theme_minimal() +  # Clean theme with readable text
  theme(
    plot.title = element_text(hjust = 0.5, face = "bold")  # Center and bold title
  )


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

c(2012:2023) |> map(~export(.x))


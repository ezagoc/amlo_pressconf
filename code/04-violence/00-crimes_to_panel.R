# 0.0 Set up the environment, clean it and set working directory to the code path
rm(list = ls())
rstudioapi::getActiveDocumentContext
setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
source("../../project_paths.R")

library(purrr)
library(tidyverse)
library(arrow)

path_co <- paste0(media_path('data', '04-violence', '01-crime_violence'), '/')

cr <- read.csv(paste0(path_co, 'raw/Municipal-Delitos-2015-2023_oct2023.csv'), 
                         fileEncoding="latin1")

del <- c('Homicidio', 'Narcomenudeo')

cr <- cr |> rename(year = Año, code_inegi = Cve..Municipio) |> 
  filter(Tipo.de.delito %in% del) |>
  filter(between(year, 2015, 2023)) |> 
  mutate(Tipo.de.delito = case_when(Tipo.de.delito == 'Homicidio' ~ 'homicide', 
                                    Tipo.de.delito == 'Narcomenudeo' ~ 'drugs')) 

del <- cr |> distinct(Tipo.de.delito) |> as_vector()

cr <- cr |> group_by(Tipo.de.delito, year, code_inegi, Entidad, Municipio) |> 
  summarise(across(c(Enero:Diciembre), ~sum(.x))) |> ungroup()

## Function for all variablesE

wide_to_panel <- function(deli){
  cr2 <- cr |> filter(Tipo.de.delito == deli) |> 
    select(year, code_inegi, Municipio, Entidad, Enero:Diciembre)
  
  cr2_long <- cr2 |> pivot_longer(cols = c(Enero:Diciembre), names_to = 'month',
                                  values_to = deli)
  
  cr2_long <- cr2_long |> group_by(year, code_inegi) |> 
    mutate(month = row_number()) |> ungroup()
  
  return(cr2_long)
}

list_frames <- del |> map(~wide_to_panel(.x))

panel_final <- list_frames %>% reduce(left_join, by = c('year', 'code_inegi', 
                                                        'month', 'Municipio', 
                                                        'Entidad'))

# panel_final <- panel_final |> mutate(code_inegi = ifelse(Entidad == 'Ciudad de México', 
#                                                          9, code_inegi),
#                                      Municipio = ifelse(Entidad == 'Ciudad de México', 
#                                                         'Ciudad de México', Municipio)) |>
#   group_by(year, month, code_inegi, Entidad, Municipio) |> summarise(across(c(homicide:drugs),
#                                                                             ~sum(.x))) |>
#   ungroup()


writexl::write_xlsx(panel_final, 
                    paste0(path_co, 'final/panel_homicides_2015_2023.xlsx'))

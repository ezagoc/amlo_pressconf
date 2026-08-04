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


# Is there a way to know if contracts were cancelled?
# Check initial polizas with respect to the final ones (the ones with date of payment)
# Then those had contracts cancelled

df <- readxl::read_excel(paste0(path_co, '00-raw/P_lizas__Comsoc_enero_a_marzo__2024.xlsx'), 
                         sheet = 1)

P_lizas__Comsoc_enero_a_marzo__2024

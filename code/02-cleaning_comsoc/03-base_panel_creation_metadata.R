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

path_co <- file.path(project_root, "data", "00-newspaper_data")
file.path(path_co, '01-intermediate',
          paste0('polizas_clean_', year, '.parquet'))
meta <- readxl::read_xlsx(file.path(path_co, 'newspaper_metadata.xlsx'))
news <- readxl::read_xlsx(path_co, 'mexican_newspapers.xlsx')


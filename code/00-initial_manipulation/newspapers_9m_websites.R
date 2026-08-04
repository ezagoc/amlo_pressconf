library(tidyverse)
source("../../project_paths.R")

df <- read.csv(media_path('data', '00-newspaper_data', 'jr_code', 'merged_final_cleaned.csv'))

df_news <- df |> distinct()
